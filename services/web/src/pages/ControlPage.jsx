import React, { useEffect, useMemo, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  normalizeProgramFromButton,
  collectAllTargetsFromButton,
  derivePrimaryCommandId,
  normalizeTargetList,
  validateProgram,
} from '../utils/controlProgram'
import { executeButtonScenario } from '../utils/controlScenarioExecution'
import IconGlyph from '../components/IconGlyph'
import { buildDefaultControlLayouts } from '../utils/defaultControlLayouts'
import WebRTCVideo from '../components/WebRTCVideo'
import './ControlPage.css'

const LAYOUT_FILEPATH = 'data/control_layouts.json'

const defaultLayouts = {
  version: '1.0.0',
  layouts: [{ id: 'layout-1', name: 'Раскладка 1', buttons: [] }],
}

function hexToRgba(hex, a) {
  const h = String(hex || '').replace('#', '')
  if (h.length !== 6) return `rgba(33,150,243,${a})`
  const r = parseInt(h.slice(0, 2), 16)
  const g = parseInt(h.slice(2, 4), 16)
  const b = parseInt(h.slice(4, 6), 16)
  return `rgba(${r},${g},${b},${a})`
}

function iconToShape(icon) {
  if (icon === '■') return 'square'
  if (icon === '▲') return 'triangle'
  return 'circle'
}

function resolveShape(button) {
  return button?.shape || iconToShape(button?.icon)
}

function resolveColor(button) {
  return button?.color || '#2196f3'
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
  const [telemetry, setTelemetry] = useState(null)
  const [camDebug, setCamDebug] = useState(null)
  // Safety: require double click to run any scenario button
  const lastClickRef = useRef(new Map()) // buttonId -> ts
  const touchStartX = useRef(null)
  const actionInFlightRef = useRef(new Set())
  const [inFlightKeys, setInFlightKeys] = useState(() => new Set())
  const mountedRef = useRef(true)

  const layouts = layoutData.layouts?.length ? layoutData.layouts : defaultLayouts.layouts
  const activeLayout = layouts[Math.min(layoutIndex, layouts.length - 1)] || defaultLayouts.layouts[0]
  const currentCameraId = cameraIds[cameraIndex] || null

  const unavailableTargets = useMemo(() => {
    const set = new Set(availableIps.map((ip) => String(ip).trim()))
    const localSet = new Set(localIps.map((ip) => String(ip).trim()))
    const pageHost = typeof window !== 'undefined' ? String(window.location.hostname || '').replace(/^::ffff:/i, '').trim() : ''
    const missing = new Set()
    for (const button of activeLayout?.buttons || []) {
      const targets = collectAllTargetsFromButton(button)
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
          // UI may control remote robots of other types; don't hide commands by local RobotType.
          fetch('/api/robot/commands?all=1'),
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
        } else if (!layoutsJson?.success && String(layoutsJson?.message || '').toLowerCase().includes('not found')) {
          // First-run bootstrap: create base layouts file
          try {
            const created = buildDefaultControlLayouts()
            await fetch('/api/files/create', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ filepath: LAYOUT_FILEPATH, content: JSON.stringify(created, null, 2) }),
            })
            setLayoutData(created)
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
    let alive = true
    const tick = async () => {
      const controller = new AbortController()
      const timeout = setTimeout(() => controller.abort(), 1200)
      try {
        const r = await fetch('/api/robot/telemetry', { signal: controller.signal })
        const j = await r.json().catch(() => null)
        if (!alive) return
        if (j && typeof j === 'object') setTelemetry(j)
      } catch (_e) {
        // keep previous telemetry; don't spam errors
      } finally {
        clearTimeout(timeout)
      }
    }
    tick()
    const t = setInterval(tick, 2500)
    return () => {
      alive = false
      clearInterval(t)
    }
  }, [])

  useEffect(() => {
    return () => {
      mountedRef.current = false
    }
  }, [])

  // Best-effort: on mobile landscape try to hide browser UI by nudging scroll.
  useEffect(() => {
    const nudge = () => {
      try {
        window.scrollTo(0, 1)
      } catch (_e) {}
    }
    nudge()
    window.addEventListener('orientationchange', nudge)
    window.addEventListener('resize', nudge)
    return () => {
      window.removeEventListener('orientationchange', nudge)
      window.removeEventListener('resize', nudge)
    }
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
    const actionKey = button.id
    if (actionInFlightRef.current.has(actionKey)) {
      if (mountedRef.current) setInfo('Это действие уже выполняется')
      return
    }

    // Double-click safety gate
    const now = Date.now()
    const last = lastClickRef.current.get(actionKey) || 0
    lastClickRef.current.set(actionKey, now)
    if (now - last > 700) {
      if (mountedRef.current) setInfo('Для безопасности нажми ещё раз')
      return
    }

    const program = normalizeProgramFromButton(button)
    const v = validateProgram(program, commandsMap)
    if (!v.ok) {
      if (mountedRef.current) setError(v.errors.join(' · '))
      return
    }

    actionInFlightRef.current.add(actionKey)
    if (mountedRef.current) setInFlightKeys(new Set(actionInFlightRef.current))

    if (mountedRef.current) setError('')
    if (mountedRef.current) setInfo('Запуск сценария…')

    const pageHost = String(window.location.hostname || '')
      .replace(/^::ffff:/i, '')
      .trim()

    try {
      await executeButtonScenario({
        button,
        commandsMap,
        localIps,
        pageHost,
        onProgress: ({ message }) => {
          if (message && mountedRef.current) setInfo(message)
        },
      })
    } catch (e) {
      if (mountedRef.current) setError(e.message || 'Ошибка сценария')
    } finally {
      actionInFlightRef.current.delete(actionKey)
      if (mountedRef.current) setInFlightKeys(new Set(actionInFlightRef.current))
    }
  }

  return (
    <div className="control-page">
      <div className="control-camera-layer">
        {currentCameraId ? (
          <div className="control-camera control-camera--webrtc">
            <WebRTCVideo
              signalingUrl={`/api/cameras/${currentCameraId}/webrtc/offer`}
              label={currentCameraId}
              qualityMode="high"
              onDebug={setCamDebug}
            />
          </div>
        ) : (
          <div className="control-camera-empty">Камера не найдена</div>
        )}
      </div>

      <div className="control-overlay">
        <div className="control-top-left">
          {telemetry?.soc != null ? (
            <div className={`telemetry-chip${Number(telemetry.soc) <= 15 ? ' telemetry-warn' : ''}`} title="Заряд батареи">
              <b>🔋</b> {Math.round(Number(telemetry.soc))}%
            </div>
          ) : (
            <div className="telemetry-chip" title={telemetry?.message || 'нет данных'}>
              <b>🔋</b> —
            </div>
          )}
        </div>

        <div className="control-top">
          <button className="overlay-chip" onClick={() => switchLayout(-1)} title="Предыдущая раскладка">
            <span className="nav-arrow" aria-hidden="true">◀</span>
            <span className="nav-arrow-text">Предыдущая</span>
          </button>
          <div className="overlay-chip layout-name">{activeLayout?.name || 'Раскладка'}</div>
          <button className="overlay-chip" onClick={() => switchLayout(1)} title="Следующая раскладка">
            <span className="nav-arrow" aria-hidden="true">▶</span>
            <span className="nav-arrow-text">Следующая</span>
          </button>
          <div className="overlay-chip camera-name">{currentCameraId || 'no-cam'}</div>
        </div>

        <div className="control-top-right">
          {telemetry?.motor_temps?.max != null ? (
            <div
              className={`telemetry-chip${Number(telemetry.motor_temps.max) >= 70 ? ' telemetry-warn' : ''}`}
              title="Температура: 1-я цифра — самый высокий максимум среди всех моторов/датчиков, 2-я — средняя по всем"
            >
              <b>🌡</b> {Math.round(Number(telemetry.motor_temps.max))}° /{' '}
              {telemetry.motor_temps.avg != null ? Math.round(Number(telemetry.motor_temps.avg)) : '—'}°
            </div>
          ) : (
            <div className="telemetry-chip" title={telemetry?.message || 'нет данных'}>
              <b>🌡</b> —
            </div>
          )}
          {unavailableTargets.length > 0 && (
            <div className="warning-badge" title={`Недоступны: ${unavailableTargets.join(', ')}`}>!</div>
          )}
          <Link className="settings-link" to="/editctl">⚙</Link>
        </div>

        <div className="control-buttons-layer">
          {(activeLayout?.buttons || []).map((button) => {
            const prog = normalizeProgramFromButton(button)
            const primaryId = derivePrimaryCommandId(prog)
            const command = commandsMap[primaryId] || commandsMap[button.commandId]
            const label = button.label || command?.name || primaryId || button.commandId
            const isBusy = inFlightKeys.has(button.id)
            const hasParallel = prog.some((b) => b.type === 'parallel')
            const scenarioHint = hasParallel ? `${prog.length} бл. · ‖` : `${prog.length} бл.`
            const shape = resolveShape(button)
            const color = resolveColor(button)
            const bg = hexToRgba(color, 0.28)
            const border = hexToRgba(color, 0.8)
            const clipPath = shape === 'triangle' ? 'polygon(50% 0%, 0% 100%, 100% 100%)' : undefined
            const borderRadius = shape === 'square' ? '12px' : '50%'
            return (
              <button
                key={button.id}
                type="button"
                className={`control-action-button${isBusy ? ' control-action-button--busy' : ''}`}
                style={{
                  left: `${(button.x || 0.5) * 100}%`,
                  top: `${(button.y || 0.5) * 100}%`,
                  width: `${button.size || 72}px`,
                  height: `${button.size || 72}px`,
                  background: bg,
                  borderColor: border,
                  borderRadius,
                  clipPath,
                }}
                disabled={isBusy}
                onClick={() => runButton(button)}
                title={`${label} · ${scenarioHint} · цели: ${normalizeTargetList(button).join(', ')}`}
              >
                <span className="button-emoji">
                  <IconGlyph name={button.icon || '●'} size={18} />
                </span>
                <span className="button-label">{label}</span>
              </button>
            )
          })}
        </div>

        <div className="control-debug">
          <div className="telemetry-chip" title="Debug: WebRTC качество и FPS">
            <b>dbg</b>{' '}
            {camDebug?.fps != null ? `${Math.round(Number(camDebug.fps))}fps` : '—fps'}
            {camDebug?.captureFps != null ? (
              <span className="control-desktop-only">{` cap ${Math.round(Number(camDebug.captureFps))}fps`}</span>
            ) : null}
            {camDebug?.net?.fps != null ? `/${Math.round(Number(camDebug.net.fps))}` : ''}
            {' '}·{' '}
            {camDebug?.qualityPct != null ? `${Math.round(Number(camDebug.qualityPct))}%` : (camDebug?.quality || '—')} ·{' '}
            {camDebug?.resPct != null ? `${Math.round(Number(camDebug.resPct))}%` : '—'}{' '}
            {camDebug?.res?.w && camDebug?.res?.h ? `(${camDebug.res.w}×${camDebug.res.h})` : ''} ·{' '}
            {camDebug?.net?.lossPct != null ? `loss ${camDebug.net.lossPct.toFixed(1)}%` : 'loss —'} ·{' '}
            {camDebug?.net?.jitterMs != null ? `jit ${Math.round(Number(camDebug.net.jitterMs))}ms` : 'jit —'} ·{' '}
            {camDebug?.state || '—'}
          </div>
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
