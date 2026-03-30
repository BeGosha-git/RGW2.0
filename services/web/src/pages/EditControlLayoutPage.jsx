import React, { useEffect, useMemo, useRef, useState } from 'react'
import './EditControlLayoutPage.css'
import LayoutToolbar from '../components/editctl/LayoutToolbar'
import WorkspaceCanvas from '../components/editctl/WorkspaceCanvas'
import NodeProgramEditor from '../components/editctl/NodeProgramEditor'
import { normalizeProgramFromButton, derivePrimaryCommandId } from '../utils/controlProgram'

const LAYOUT_FILEPATH = 'data/control_layouts.json'

const defaultData = {
  version: '1.0.0',
  layouts: [{ id: 'layout-1', name: 'Раскладка 1', buttons: [] }],
}

function uid(prefix) {
  return `${prefix}-${Date.now()}-${Math.random().toString(16).slice(2, 6)}`
}

function EditControlLayoutPage() {
  const [layoutData, setLayoutData] = useState(defaultData)
  const [layoutIndex, setLayoutIndex] = useState(0)
  const [commands, setCommands] = useState([])
  const [targetIps, setTargetIps] = useState(['LOCAL'])
  const [draggingId, setDraggingId] = useState(null)
  const [selectedButtonId, setSelectedButtonId] = useState(null)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const [scenarioBusy, setScenarioBusy] = useState(false)
  const [confirmDelete, setConfirmDelete] = useState(null) // { id }
  const [ipMeta, setIpMeta] = useState({})
  const [localIps, setLocalIps] = useState([])
  const pageHost = typeof window !== 'undefined'
    ? String(window.location.hostname || '').replace(/^::ffff:/i, '').trim()
    : ''
  const splitWrapRef = useRef(null)
  const loadedOnceRef = useRef(false)
  const nodesWidthPctRef = useRef(33)
  const [nodesWidthPct, setNodesWidthPct] = useState(() => {
    const raw = typeof window !== 'undefined' ? window.localStorage.getItem('rgw2_editctl_nodesWidthPct') : null
    const n = raw != null ? Number(raw) : NaN
    // по умолчанию: телефон 2/3, ноды 1/3
    if (Number.isFinite(n) && n >= 18 && n <= 60) return n
    return 33
  })

  useEffect(() => {
    nodesWidthPctRef.current = nodesWidthPct
    try {
      document.documentElement.dataset.rgw2NodesWidthPct = String(nodesWidthPct)
    } catch (_e) {}
  }, [nodesWidthPct])

  const layouts = layoutData.layouts?.length ? layoutData.layouts : defaultData.layouts
  const activeLayout = layouts[Math.min(layoutIndex, layouts.length - 1)] || defaultData.layouts[0]

  const commandsMap = useMemo(() => {
    const map = {}
    for (const command of commands) map[command.id] = command
    return map
  }, [commands])

  const selectedButton = useMemo(
    () => (activeLayout?.buttons || []).find((button) => button.id === selectedButtonId) || null,
    [activeLayout, selectedButtonId],
  )

  useEffect(() => {
    const load = async () => {
      try {
        setError('')
        // Не блокируем загрузку раскладок медленными сетевыми запросами (find_robots может быть долгим)
        const [layoutsResp, commandsResp, ipsResp, statusResp] = await Promise.all([
          fetch(`/api/files/read?filepath=${encodeURIComponent(LAYOUT_FILEPATH)}`),
          fetch('/api/robot/commands'),
          fetch('/api/network/scanned_ips'),
          fetch('/api/status'),
        ])
        const layoutsJson = await layoutsResp.json()
        const commandsJson = await commandsResp.json()
        const ipsJson = await ipsResp.json()
        const statusJson = await statusResp.json().catch(() => ({}))

        // layouts file can come as string or already-parsed object (tolerate both)
        let loadedLayouts = null
        if (layoutsJson?.success && layoutsJson.content != null) {
          try {
            const raw = layoutsJson.content
            const parsed = typeof raw === 'string' ? JSON.parse(raw) : raw
            const normalized =
              Array.isArray(parsed)
                ? { version: '1.0.0', layouts: parsed }
                : parsed && typeof parsed === 'object'
                  ? parsed
                  : null

            if (Array.isArray(normalized?.layouts) && normalized.layouts.length) {
              loadedLayouts = {
                version: String(normalized.version || '1.0.0'),
                layouts: normalized.layouts.map((l, idx) => ({
                  id: String(l?.id || `layout-${idx + 1}`),
                  name: String(l?.name || `Раскладка ${idx + 1}`),
                  buttons: Array.isArray(l?.buttons) ? l.buttons : [],
                })),
              }
            }
          } catch (_e) {
            loadedLayouts = null
          }
        }

        if (loadedLayouts) {
          setLayoutData(loadedLayouts)
          // ensure a sane selection on load (always clamp index to avoid "updates only after click")
          setLayoutIndex((idx) => Math.max(0, Math.min(Number.isFinite(idx) ? idx : 0, loadedLayouts.layouts.length - 1)))
          if (!loadedOnceRef.current) {
            setSelectedButtonId(null)
            setDraggingId(null)
          }
          loadedOnceRef.current = true
        } else {
          // If file read failed or content invalid, keep current state but show error once.
          if (!loadedOnceRef.current) {
            setLayoutData(defaultData)
            setLayoutIndex(0)
            loadedOnceRef.current = true
          }
          if (!layoutsJson?.success) setError(layoutsJson?.message || 'Не удалось загрузить раскладки')
        }

        if (commandsJson.success && Array.isArray(commandsJson.commands)) {
          setCommands(commandsJson.commands)
        }

        // localIps: IP этой машины — используем вместо LOCAL
        const detectedLocalIps = []
        {
          const ipA = statusJson?.network?.local_ip
          const ipB = statusJson?.network?.interface_ip
          if (ipA) detectedLocalIps.push(String(ipA).trim())
          if (ipB && String(ipB).trim() !== String(ipA).trim()) detectedLocalIps.push(String(ipB).trim())
          if (detectedLocalIps.length) setLocalIps(detectedLocalIps)
        }

        if (ipsJson.success && Array.isArray(ipsJson.ips)) {
          // LOCAL заменяем на реальный IP этой машины (первый из detectedLocalIps)
          // Если IP этой машины уже есть в списке — не дублируем
          const scanned = ipsJson.ips.map((x) => String(x).trim()).filter(Boolean)
          const selfIp = detectedLocalIps[0] || null
          const all = selfIp
            ? [selfIp, ...scanned.filter((ip) => ip !== selfIp)]
            : scanned
          setTargetIps(all.length ? all : (selfIp ? [selfIp] : ['LOCAL']))
        } else if (detectedLocalIps.length) {
          setTargetIps(detectedLocalIps)
        }

        // meta: ip -> color by group (как на RobotsPage) — грузим отдельно, чтобы не тормозить раскладки
        ;(async () => {
          try {
            const robotsResp = await fetch('/api/network/find_robots')
            const robotsJson = await robotsResp.json().catch(() => ({}))
            const COMMAND_COLORS = {
              red: '#f44336',
              blue: '#2196f3',
              green: '#4caf50',
              white: '#ffffff',
              black: '#000000',
            }
            const pickFg = (hex) => {
              const h = String(hex || '').replace('#', '')
              if (h.length !== 6) return '#fff'
              const r = parseInt(h.slice(0, 2), 16)
              const g = parseInt(h.slice(2, 4), 16)
              const b = parseInt(h.slice(4, 6), 16)
              const lum = (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255
              return lum > 0.62 ? '#111' : '#fff'
            }
            const nextMeta = {}
            // Помечаем IP этой машины как "Этот робот"
            for (const selfIp of detectedLocalIps) {
              nextMeta[selfIp] = { bg: 'rgba(255,255,255,0.15)', fg: '#fff', name: 'Этот робот' }
            }
            const robots = Array.isArray(robotsJson?.robots) ? robotsJson.robots : []
            for (const item of robots) {
              const ip = String(item?.ip || '').trim()
              if (!ip) continue
              const info = item?.info || {}
              const nameRaw =
                info?.robot?.name ??
                info?.robot?.robot_name ??
                info?.robot?.robotName ??
                info?.network?.hostname ??
                info?.network?.host ??
                info?.settings?.RobotName ??
                info?.settings?.robot_name
              const groupRaw =
                info?.robot?.robot_group ??
                info?.robot?.robotGroup ??
                info?.settings?.RobotGroup ??
                info?.settings?.robot_group
              const group = String(groupRaw || '').toLowerCase().trim()
              const base = COMMAND_COLORS[group] || '#64748b'
              nextMeta[ip] = {
                bg: base,
                fg: pickFg(base),
                group,
                name: String(nameRaw || '').trim() || null,
              }
            }
            setIpMeta(nextMeta)
          } catch (_e) {
            // не критично для загрузки раскладок
          }
        })()
      } catch (e) {
        setError(e.message || 'Ошибка загрузки')
      }
    }
    load()
  }, [])

  const updateActiveLayout = (mutator) => {
    setLayoutData((prev) => {
      const nextLayouts = [...(prev.layouts || [])]
      const idx = Math.min(layoutIndex, nextLayouts.length - 1)
      if (idx < 0) return prev
      nextLayouts[idx] = mutator(nextLayouts[idx])
      return { ...prev, layouts: nextLayouts }
    })
  }

  const toRelativePoint = (event, rect) => {
    const clientX = event.clientX ?? event.touches?.[0]?.clientX ?? event.changedTouches?.[0]?.clientX ?? 0
    const clientY = event.clientY ?? event.touches?.[0]?.clientY ?? event.changedTouches?.[0]?.clientY ?? 0
    return {
      x: Math.min(1, Math.max(0, (clientX - rect.left) / rect.width)),
      y: Math.min(1, Math.max(0, (clientY - rect.top) / rect.height)),
    }
  }

  const clickWorkspace = (event) => {
    const defaultCommandId = commands[0]?.id || ''
    if (!defaultCommandId) {
      setError('Нет команд для создания кнопки')
      return
    }
    const rect = event.currentTarget.getBoundingClientRect()
    const { x, y } = toRelativePoint(event, rect)

    const command = commandsMap[defaultCommandId]
    const nextButton = {
      id: uid('btn'),
      commandId: defaultCommandId,
      label: command?.name || defaultCommandId,
      icon: '●', // круг по умолчанию
      shape: 'circle',
      color: '#2196f3',
      x,
      y,
      size: 64,
      targetIps: localIps.length ? [localIps[0]] : [],
      program: [
        {
          type: 'command',
          id: uid('step'),
          commandId: defaultCommandId,
          delayBeforeMs: 0,
          delayAfterMs: 0,
          targetIps: localIps.length ? [localIps[0]] : [],
        },
      ],
    }

    updateActiveLayout((layout) => ({
      ...layout,
      buttons: [...(layout.buttons || []), nextButton],
    }))
    setSelectedButtonId(nextButton.id)
    setMessage('Кнопка добавлена')
    setError('')
  }

  const moveButton = (event) => {
    if (!draggingId) return
    const rect = event.currentTarget.getBoundingClientRect()
    const { x, y } = toRelativePoint(event, rect)
    updateActiveLayout((layout) => ({
      ...layout,
      buttons: (layout.buttons || []).map((button) => (button.id === draggingId ? { ...button, x, y } : button)),
    }))
  }

  useEffect(() => {
    const onKey = (e) => {
      if (e.key !== 'Delete' && e.key !== 'Backspace') return
      const tag = String(e.target?.tagName || '').toLowerCase()
      if (tag === 'input' || tag === 'textarea' || e.target?.isContentEditable) return
      deleteSelectedButton()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [selectedButtonId, layoutIndex, layoutData])

  const updateSelectedButton = (patch) => {
    if (!selectedButtonId) return
    updateActiveLayout((layout) => ({
      ...layout,
      buttons: (layout.buttons || []).map((button) =>
        button.id === selectedButtonId ? { ...button, ...patch } : button,
      ),
    }))
  }

  const deleteSelectedButton = (id = null) => {
    const delId = id || selectedButtonId
    if (!delId) return
    setConfirmDelete({ id: delId })
  }

  const confirmDeleteNow = () => {
    const delId = confirmDelete?.id
    if (!delId) return
    updateActiveLayout((layout) => ({
      ...layout,
      buttons: (layout.buttons || []).filter((button) => button.id !== delId),
    }))
    if (delId === selectedButtonId) setSelectedButtonId(null)
    setMessage('Кнопка удалена')
    setConfirmDelete(null)
  }

  const cancelDelete = () => setConfirmDelete(null)

  const saveLayouts = async () => {
    try {
      setMessage('')
      setError('')
      const round5 = (v) => {
        const n = Number(v)
        if (!Number.isFinite(n)) return v
        return Number(n.toFixed(5))
      }
      const sanitized = {
        ...layoutData,
        layouts: (layoutData.layouts || []).map((l) => ({
          ...l,
          buttons: (l.buttons || []).map((b) => ({
            ...b,
            x: round5(b.x),
            y: round5(b.y),
          })),
        })),
      }
      const payload = {
        filepath: LAYOUT_FILEPATH,
        content: JSON.stringify(sanitized, null, 2),
      }
      const response = await fetch('/api/files/write', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })
      const json = await response.json()
      if (!json.success) throw new Error(json.message || 'Не удалось сохранить')
      setMessage('Сохранено')
    } catch (e) {
      setError(e.message || 'Ошибка сохранения')
    }
  }

  const runSelectedScenario = async () => {
    if (!selectedButton) {
      setError('Сначала выбери кнопку на экране телефона')
      return
    }
    if (scenarioBusy) return
    setScenarioBusy(true)
    setError('')
    setMessage('Запуск сценария…')
    try {
      const startResp = await fetch('/api/robot/run_scenario', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ button: selectedButton, scenarioKey: selectedButton.id, pageHost, localIps }),
      })
      const startJson = await startResp.json()
      if (!startJson?.success) throw new Error(startJson?.message || 'Не удалось запустить')
      const jobId = startJson.jobId
      if (!jobId) throw new Error('jobId отсутствует')

      while (true) {
        const stResp = await fetch(`/api/robot/scenario/${encodeURIComponent(jobId)}`)
        const stJson = await stResp.json()
        if (!stJson?.success) throw new Error(stJson?.message || 'Ошибка статуса')
        const job = stJson.job || {}
        const prog = job.progress || {}
        if (prog?.message) setMessage(prog.message)
        if (job.status === 'done') break
        if (job.status === 'error') throw new Error(job.error || 'Ошибка сценария')
        await new Promise((r) => setTimeout(r, 650))
      }
      setMessage('Сценарий завершён')
    } catch (e) {
      setError(e.message || 'Ошибка запуска сценария')
    } finally {
      setScenarioBusy(false)
    }
  }

  const addLayout = () => {
    setLayoutData((prev) => {
      const base = prev.layouts?.length ? prev.layouts : defaultData.layouts
      const nextIndex = base.length
      const nextLayout = { id: uid('layout'), name: `Раскладка ${nextIndex + 1}`, buttons: [] }
      // selecting after state update: use functional set below
      setLayoutIndex(nextIndex)
      return { ...prev, layouts: [...base, nextLayout] }
    })
  }

  const deleteLayout = () => {
    if (layouts.length <= 1) {
      setError('Должна остаться хотя бы одна раскладка')
      return
    }
    setLayoutData((prev) => {
      const next = [...prev.layouts]
      next.splice(layoutIndex, 1)
      return { ...prev, layouts: next }
    })
    setLayoutIndex((idx) => Math.max(0, idx - 1))
    setSelectedButtonId(null)
  }

  const switchLayout = (direction) => {
    if (!layouts.length) return
    setLayoutIndex((prev) => {
      const next = prev + direction
      if (next < 0) return layouts.length - 1
      if (next >= layouts.length) return 0
      return next
    })
  }

  return (
    <div className="editctl-page" onContextMenu={(e) => e.preventDefault()}>
      <LayoutToolbar
        layouts={layouts}
        activeIndex={layoutIndex}
        onSelectIndex={(idx) => setLayoutIndex(Math.max(0, Math.min(idx, layouts.length - 1)))}
        activeLayoutName={activeLayout?.name || ''}
        onActiveLayoutNameChange={(name) => updateActiveLayout((layout) => ({ ...layout, name }))}
        onAddLayout={addLayout}
        onSave={saveLayouts}
      />

      <div className="editctl-split" ref={splitWrapRef}>
        <div className="editctl-phone editctl-phone--full" style={{ width: `${100 - nodesWidthPct}%` }}>
          <WorkspaceCanvas
            buttons={activeLayout?.buttons || []}
            selectedButtonId={selectedButtonId}
            draggingId={draggingId}
            onWorkspaceClick={(event) => {
              if (draggingId) return
              clickWorkspace(event)
            }}
            onPointerMove={moveButton}
            onPointerUp={() => setDraggingId(null)}
            onSelectButton={setSelectedButtonId}
            onStartDrag={(id) => {
              setDraggingId(id)
              setSelectedButtonId(id)
            }}
            onPatchButton={updateSelectedButton}
            onDeleteButton={deleteSelectedButton}
          />
        </div>

        <div
          className="editctl-resizer"
          role="separator"
          aria-orientation="vertical"
          title="Потяни, чтобы изменить ширину"
          onPointerDown={(e) => {
            e.preventDefault()
            const el = splitWrapRef.current
            if (!el) return
            const startX = e.clientX
            const rect = el.getBoundingClientRect()
            const startPct = nodesWidthPct
            const onMove = (ev) => {
              const dx = ev.clientX - startX
              const width = rect.width || 1
              // Инверсия: тянем вправо => телефон шире (ноды уже)
              const deltaPct = (dx / width) * 100
              const next = Math.min(60, Math.max(18, startPct - deltaPct))
              setNodesWidthPct(next)
            }
            const onUp = () => {
              window.removeEventListener('pointermove', onMove)
              window.removeEventListener('pointerup', onUp)
              try {
                window.localStorage.setItem('rgw2_editctl_nodesWidthPct', String(nodesWidthPctRef.current))
              } catch (_e) {}
            }
            window.addEventListener('pointermove', onMove)
            window.addEventListener('pointerup', onUp)
          }}
        >
          <div className="editctl-resizer__grab" />
        </div>

        <div className="editctl-nodes editctl-nodes--right" style={{ width: `${nodesWidthPct}%` }}>
          <div className="editctl-nodes__head">
            <div className="editctl-nodes__head-row">
              <span className="editctl-nodes__ttl">Ноды</span>
              <button
                type="button"
                className={`node-play-btn ${scenarioBusy ? 'is-busy' : ''}`}
                onClick={runSelectedScenario}
                disabled={scenarioBusy}
                title="Проиграть сценарий на роботах"
              >
                ▶
              </button>
            </div>
            <span className="editctl-nodes__sub"></span>
          </div>

          {selectedButton ? (
            <NodeProgramEditor
              program={normalizeProgramFromButton(selectedButton)}
              programEdges={selectedButton.programEdges || null}
              commands={commands}
              targetIps={targetIps}
              targetMeta={ipMeta}
              scenarioKey={selectedButton.id}
              onError={(msg) => setError(String(msg || 'Ошибка графа'))}
              onChangeProgram={(steps, edges) =>
                updateSelectedButton({
                  program: steps,
                  programEdges: edges,
                  commandId: derivePrimaryCommandId(steps) || selectedButton.commandId || '',
                })
              }
            />
          ) : (
            <p className="panel-hint">Выбери кнопку на экране, чтобы редактировать ноды.</p>
          )}
        </div>
      </div>

      {(message || error) && <div className={`editor-toast ${error ? 'error' : ''}`}>{error || message}</div>}

      {confirmDelete ? (
        <div className="center-modal" role="dialog" aria-modal="true" onMouseDown={cancelDelete}>
          <div className="center-modal__card" onMouseDown={(e) => e.stopPropagation()}>
            <div className="center-modal__ttl">Удалить кнопку?</div>
            <div className="center-modal__sub">Действие нельзя отменить.</div>
            <div className="center-modal__btns">
              <button type="button" className="center-modal__btn" onClick={cancelDelete}>
                Отмена
              </button>
              <button type="button" className="center-modal__btn center-modal__btn--danger" onClick={confirmDeleteNow} autoFocus>
                Удалить
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  )
}

export default EditControlLayoutPage
