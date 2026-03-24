import React, { useEffect, useMemo, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import './ControlPage.css'

const LAYOUT_FILEPATH = 'data/control_layouts.json'

const defaultLayouts = {
  version: '1.0.0',
  layouts: [{ id: 'layout-1', name: 'Раскладка 1', buttons: [] }],
}

function normalizeTargetList(button) {
  const raw = button.targetIps ?? (button.targetIp ? [button.targetIp] : ['LOCAL'])
  const list = Array.isArray(raw) ? raw : [raw]
  return [...new Set(list.map((t) => String(t).trim()).filter(Boolean))]
}

function ControlPage() {
  const [layoutData, setLayoutData] = useState(defaultLayouts)
  const [layoutIndex, setLayoutIndex] = useState(0)
  const [commandsMap, setCommandsMap] = useState({})
  const [availableIps, setAvailableIps] = useState([])
  const [localIps, setLocalIps] = useState([])
  const [cameraIds, setCameraIds] = useState([])
  const [cameraIndex, setCameraIndex] = useState(0)
  const [info, setInfo] = useState('')
  const [error, setError] = useState('')
  const touchStartX = useRef(null)

  const layouts = layoutData.layouts?.length ? layoutData.layouts : defaultLayouts.layouts
  const activeLayout = layouts[Math.min(layoutIndex, layouts.length - 1)] || defaultLayouts.layouts[0]
  const currentCameraId = cameraIds[cameraIndex] || null

  const unavailableTargets = useMemo(() => {
    const set = new Set(availableIps.map((ip) => String(ip).trim()))
    const localSet = new Set(localIps.map((ip) => String(ip).trim()))
    const pageHost = typeof window !== 'undefined' ? String(window.location.hostname || '').replace(/^::ffff:/i, '').trim() : ''
    const missing = new Set()
    for (const button of activeLayout?.buttons || []) {
      const targets = normalizeTargetList(button)
      for (const target of targets) {
        if (target === 'LOCAL' || localSet.has(target) || (pageHost && target === pageHost)) continue
        if (!set.has(target)) missing.add(target)
      }
    }
    return Array.from(missing)
  }, [activeLayout, availableIps, localIps])

  useEffect(() => {
    const loadAll = async () => {
      setError('')
      try {
        const [layoutsResp, commandsResp, ipsResp, camerasResp, statusResp] = await Promise.all([
          fetch(`/api/files/read?filepath=${encodeURIComponent(LAYOUT_FILEPATH)}`),
          fetch('/api/robot/commands'),
          fetch('/api/network/scanned_ips'),
          fetch('/api/cameras/list'),
          fetch('/api/status'),
        ])

        const layoutsJson = await layoutsResp.json()
        const commandsJson = await commandsResp.json()
        const ipsJson = await ipsResp.json()
        const camerasJson = await camerasResp.json()
        const statusJson = await statusResp.json()

        if (layoutsJson.success && layoutsJson.content) {
          try {
            const parsed = JSON.parse(layoutsJson.content)
            if (Array.isArray(parsed.layouts) && parsed.layouts.length) {
              setLayoutData(parsed)
            }
          } catch (_e) {
            setLayoutData(defaultLayouts)
          }
        }

        if (commandsJson.success && Array.isArray(commandsJson.commands)) {
          const nextMap = {}
          for (const cmd of commandsJson.commands) nextMap[cmd.id] = cmd
          setCommandsMap(nextMap)
        }

        if (ipsJson.success && Array.isArray(ipsJson.ips)) {
          setAvailableIps(ipsJson.ips)
        }

        const detectedLocalIps = []
        const ipA = statusJson?.network?.local_ip
        const ipB = statusJson?.network?.interface_ip
        if (ipA) detectedLocalIps.push(ipA)
        if (ipB && ipB !== ipA) detectedLocalIps.push(ipB)
        setLocalIps(detectedLocalIps)

        if (camerasJson.success && Array.isArray(camerasJson.cameras)) {
          const ids = camerasJson.cameras.map((camera) => camera.id).filter(Boolean)
          setCameraIds(ids)
        }
      } catch (e) {
        setError(e.message || 'Не удалось загрузить данные')
      }
    }

    loadAll()
    const timer = setInterval(loadAll, 5000)
    return () => clearInterval(timer)
  }, [])

  useEffect(() => {
    setLayoutIndex((idx) => Math.min(idx, Math.max(layouts.length - 1, 0)))
  }, [layouts.length])

  useEffect(() => {
    setCameraIndex((idx) => Math.min(idx, Math.max(cameraIds.length - 1, 0)))
  }, [cameraIds.length])

  const switchLayout = (direction) => {
    if (!layouts.length) return
    setLayoutIndex((prev) => {
      const next = prev + direction
      if (next < 0) return layouts.length - 1
      if (next >= layouts.length) return 0
      return next
    })
  }

  const switchCamera = (direction) => {
    if (!cameraIds.length) return
    setCameraIndex((prev) => {
      const next = prev + direction
      if (next < 0) return cameraIds.length - 1
      if (next >= cameraIds.length) return 0
      return next
    })
  }

  const onSwipeTouchStart = (event) => {
    touchStartX.current = event.touches?.[0]?.clientX ?? null
  }

  const onSwipeTouchEnd = (event) => {
    const startX = touchStartX.current
    const endX = event.changedTouches?.[0]?.clientX ?? null
    touchStartX.current = null
    if (startX == null || endX == null) return

    const left = window.innerWidth * 0.25
    const right = window.innerWidth * 0.75
    const delta = endX - startX
    if (startX >= left && startX <= right && delta < -40) {
      switchCamera(1)
      if (cameraIds.length <= 1) {
        setInfo('Доступна только одна камера')
      }
    } else if (startX >= left && startX <= right && delta > 40) {
      switchCamera(-1)
      if (cameraIds.length <= 1) {
        setInfo('Доступна только одна камера')
      }
    }
  }

  const runButton = async (button) => {
    setError('')
    setInfo('')
    const command = commandsMap[button.commandId]
    if (!command) {
      setError(`Команда ${button.commandId} не найдена`)
      return
    }

    try {
      const targets = normalizeTargetList(button)
      const localSet = new Set(localIps.map((ip) => String(ip).trim()).filter(Boolean))
      // Страница открыта с этого хоста — считаем его «локальным» роботом (важно при двух NIC:
      // /api/status может отдать только один local_ip, а в раскладке указан другой адрес этой же машины).
      const pageHost = String(window.location.hostname || '')
        .replace(/^::ffff:/i, '')
        .trim()

      const isLocalTarget = (target) => {
        if (target === 'LOCAL') return true
        if (localSet.has(target)) return true
        if (pageHost && (target === pageHost || target === `[${pageHost}]`)) return true
        return false
      }

      const hasLocal = targets.some(isLocalTarget)
      const remoteTargets = [...new Set(targets.filter((t) => !isLocalTarget(t)))]

      if (hasLocal) {
        const localResponse = await fetch('/api/robot/execute', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ command: command.command, args: command.args || [] }),
        })
        const localResult = await localResponse.json()
        if (!localResult.success) throw new Error(localResult.message || 'Локальная команда не выполнена')
      }

      const payload = {
        command: command.command,
        args: command.args || [],
      }

      const remoteResults = await Promise.all(
        remoteTargets.map(async (targetIp) => {
          try {
            const response = await fetch('/api/network/send', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({
                target_ip: targetIp,
                endpoint: '/api/robot/execute',
                data: payload,
              }),
            })
            const result = await response.json()
            if (!result.success) {
              return { targetIp, ok: false, message: result.message || 'сеть' }
            }
            const remoteResponse = result.response
            if (remoteResponse && typeof remoteResponse === 'object' && remoteResponse.success === false) {
              return {
                targetIp,
                ok: false,
                message: remoteResponse.message || 'команда отклонена',
              }
            }
            const hasReturnCode =
              remoteResponse &&
              remoteResponse.return_code !== undefined &&
              remoteResponse.return_code !== null
            if (
              hasReturnCode &&
              (remoteResponse.success === false || remoteResponse.return_code !== 0)
            ) {
              return {
                targetIp,
                ok: false,
                message: remoteResponse.message || remoteResponse.stderr || 'команда завершилась с ошибкой',
              }
            }
            return { targetIp, ok: true, message: null }
          } catch (err) {
            return { targetIp, ok: false, message: err.message || 'ошибка запроса' }
          }
        }),
      )

      const failed = remoteResults.filter((r) => !r.ok)
      if (failed.length) {
        setError(
          failed.map((f) => `${f.targetIp}: ${f.message}`).join(' · '),
        )
      }
      const okLabel = [
        ...(hasLocal ? ['LOCAL'] : []),
        ...remoteResults.filter((r) => r.ok).map((r) => r.targetIp),
      ]
      if (okLabel.length) {
        setInfo(`Отправлено: ${okLabel.join(', ')}${failed.length ? ` (ошибок: ${failed.length})` : ''}`)
      }
    } catch (e) {
      setError(e.message || 'Ошибка выполнения команды')
    }
  }

  return (
    <div className="control-page">
      <div className="control-camera-layer">
        {currentCameraId ? (
          <img
            src={`/api/cameras/${currentCameraId}/mjpeg`}
            alt={currentCameraId}
            className="control-camera"
            draggable={false}
            onDragStart={(event) => event.preventDefault()}
          />
        ) : (
          <div className="control-camera-empty">Камера не найдена</div>
        )}
      </div>

      <div className="control-overlay">
        <div className="control-top">
          <button className="overlay-chip" onClick={() => switchLayout(-1)}>Предыдущая</button>
          <div className="overlay-chip layout-name">{activeLayout?.name || 'Раскладка'}</div>
          <button className="overlay-chip" onClick={() => switchLayout(1)}>Следующая</button>
          <div className="overlay-chip camera-name">{currentCameraId || 'no-cam'}</div>
        </div>

        <div className="control-top-right">
          {unavailableTargets.length > 0 && (
            <div className="warning-badge" title={`Недоступны: ${unavailableTargets.join(', ')}`}>!</div>
          )}
          <Link className="settings-link" to="/editctl">⚙</Link>
        </div>

        <div className="control-buttons-layer">
          {(activeLayout?.buttons || []).map((button) => {
            const command = commandsMap[button.commandId]
            const label = button.label || command?.name || button.commandId
            return (
              <button
                key={button.id}
                className="control-action-button"
                style={{
                  left: `${(button.x || 0.5) * 100}%`,
                  top: `${(button.y || 0.5) * 100}%`,
                  width: `${button.size || 72}px`,
                  height: `${button.size || 72}px`,
                }}
                onClick={() => runButton(button)}
                title={`${label} (${(button.targetIps || [button.targetIp || 'LOCAL']).join(', ')})`}
              >
                <span className="button-emoji">{button.icon || '●'}</span>
                <span className="button-label">{label}</span>
              </button>
            )
          })}
        </div>

        <div
          className="control-swipe-zone"
          onTouchStart={onSwipeTouchStart}
          onTouchEnd={onSwipeTouchEnd}
        />

        {(info || error) && (
          <div className={`control-toast ${error ? 'error' : 'info'}`}>
            {[info, error].filter(Boolean).join(' — ')}
          </div>
        )}

        <div className="control-camera-hint">Свайп в центральной половине экрана: камера</div>
      </div>
    </div>
  )
}

export default ControlPage
