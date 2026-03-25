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
import './ControlPage.css'

const LAYOUT_FILEPATH = 'data/control_layouts.json'

const defaultLayouts = {
  version: '1.0.0',
  layouts: [{ id: 'layout-1', name: 'Раскладка 1', buttons: [] }],
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
    return () => {
      mountedRef.current = false
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
            const prog = normalizeProgramFromButton(button)
            const primaryId = derivePrimaryCommandId(prog)
            const command = commandsMap[primaryId] || commandsMap[button.commandId]
            const label = button.label || command?.name || primaryId || button.commandId
            const isBusy = inFlightKeys.has(button.id)
            const hasParallel = prog.some((b) => b.type === 'parallel')
            const scenarioHint = hasParallel ? `${prog.length} бл. · ‖` : `${prog.length} бл.`
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
                }}
                disabled={isBusy}
                onClick={() => runButton(button)}
                title={`${label} · ${scenarioHint} · цели: ${normalizeTargetList(button).join(', ')}`}
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
