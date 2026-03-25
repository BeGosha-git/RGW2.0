import { normalizeProgramFromButton, normalizeTargetList } from './controlProgram'

export function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, Math.max(0, Number(ms) || 0)))
}

function inferNetworkTimeout(cmdEntry) {
  if (!cmdEntry) return undefined
  const { id, command, args } = cmdEntry
  if (id === 'update_system' || id === 'force_update_system') return 300
  if (
    command === 'python3' &&
    Array.isArray(args) &&
    args.some((a) => String(a).includes('upgrade.py') || String(a).includes('update.py'))
  ) {
    return 300
  }
  return undefined
}

function buildIsLocalTarget(localIps, pageHost) {
  const localSet = new Set(localIps.map((ip) => String(ip).trim()).filter(Boolean))
  return (target) => {
    if (target === 'LOCAL') return true
    if (localSet.has(target)) return true
    if (pageHost && (target === pageHost || target === `[${pageHost}]`)) return true
    return false
  }
}

/**
 * Выполнить одну команду на наборе целей (LOCAL + сеть параллельно).
 */
export async function runCommandOnTargets({
  cmdEntry,
  targets,
  isLocalTarget,
  fetchImpl = fetch,
  timeoutSec,
}) {
  if (!cmdEntry) throw new Error('Команда не найдена')
  const payload = { command: cmdEntry.command, args: cmdEntry.args || [] }
  const hasLocal = targets.some(isLocalTarget)
  const remoteTargets = [...new Set(targets.filter((t) => !isLocalTarget(t)))]

  const timeout = timeoutSec ?? inferNetworkTimeout(cmdEntry)

  const tasks = []

  if (hasLocal) {
    tasks.push(
      (async () => {
        const localResponse = await fetchImpl('/api/robot/execute', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ command: payload.command, args: payload.args }),
        })
        const localResult = await localResponse.json()
        if (!localResult.success) throw new Error(localResult.message || 'Локальная команда не выполнена')
        return { kind: 'local' }
      })(),
    )
  }

  tasks.push(
    ...remoteTargets.map((targetIp) =>
      (async () => {
        try {
          const body = {
            target_ip: targetIp,
            endpoint: '/api/robot/execute',
            data: payload,
          }
          if (timeout != null) body.timeout = timeout

          const response = await fetchImpl('/api/network/send', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
          })
          const result = await response.json()
          if (!result.success) {
            return { kind: 'remote', targetIp, ok: false, message: result.message || 'сеть' }
          }
          const remoteResponse = result.response
          if (remoteResponse && typeof remoteResponse === 'object' && remoteResponse.success === false) {
            return {
              kind: 'remote',
              targetIp,
              ok: false,
              message: remoteResponse.message || 'команда отклонена',
            }
          }
          const hasReturnCode =
            remoteResponse &&
            remoteResponse.return_code !== undefined &&
            remoteResponse.return_code !== null
          if (hasReturnCode && (remoteResponse.success === false || remoteResponse.return_code !== 0)) {
            return {
              kind: 'remote',
              targetIp,
              ok: false,
              message: remoteResponse.message || remoteResponse.stderr || 'команда завершилась с ошибкой',
            }
          }
          return { kind: 'remote', targetIp, ok: true, message: null }
        } catch (err) {
          return { kind: 'remote', targetIp, ok: false, message: err.message || 'ошибка запроса' }
        }
      })(),
    ),
  )

  const merged = await Promise.all(tasks)
  const remoteResults = merged.filter((x) => x.kind === 'remote')
  const failed = remoteResults.filter((r) => !r.ok)
  if (failed.length) {
    throw new Error(failed.map((f) => `${f.targetIp}: ${f.message}`).join(' · '))
  }
}

/**
 * Выполнить полный сценарий кнопки.
 * @param {object} options
 * @param {function} options.onProgress — { phase, message, blockIndex, blockCount }
 */
export async function executeButtonScenario({
  button,
  commandsMap,
  localIps,
  pageHost,
  onProgress,
  fetchImpl,
}) {
  const fp = fetchImpl || fetch
  const scenarioKey = button?.id || undefined

  const startResp = await fp('/api/robot/run_scenario', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      button,
      pageHost,
      localIps,
      scenarioKey,
    }),
  })

  const startJson = await startResp.json().catch(() => ({}))
  if (!startJson?.success) {
    throw new Error(startJson?.message || 'Не удалось запустить сценарий')
  }

  const jobId = startJson.jobId
  if (!jobId) throw new Error('Сервер не вернул jobId')

  if (typeof onProgress === 'function') {
    onProgress({ phase: 'queue', message: 'Сценарий поставлен в очередь…' })
  }

  // Polling статуса job на сервере.
  // Важно: выполнение сценария продолжается на сервере даже если UI размонтировался.
  while (true) {
    const stResp = await fp(`/api/robot/scenario/${encodeURIComponent(jobId)}`, { method: 'GET' })
    const stJson = await stResp.json().catch(() => ({}))

    if (!stJson?.success) {
      throw new Error(stJson?.message || 'Ошибка polling сценария')
    }

    const job = stJson.job || {}
    const progress = job.progress || {}
    if (typeof onProgress === 'function' && progress?.message) {
      onProgress({ phase: progress.phase, message: progress.message, blockIndex: progress.blockIndex, blockCount: progress.blockCount })
    }

    if (job.status === 'done') return
    if (job.status === 'error') throw new Error(job.error || 'Ошибка сценария')

    await sleep(650)
  }
}
