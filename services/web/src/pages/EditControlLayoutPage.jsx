import React, { useEffect, useMemo, useState } from 'react'
import './EditControlLayoutPage.css'
import LayoutToolbar from '../components/editctl/LayoutToolbar'
import AddPanel from '../components/editctl/AddPanel'
import ButtonPropertiesPanel from '../components/editctl/ButtonPropertiesPanel'
import WorkspaceCanvas from '../components/editctl/WorkspaceCanvas'

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
  const [selectedCommandId, setSelectedCommandId] = useState('')
  const [selectedTargetIps, setSelectedTargetIps] = useState(['LOCAL'])
  const [draggingId, setDraggingId] = useState(null)
  const [selectedButtonId, setSelectedButtonId] = useState(null)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')

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
        const [layoutsResp, commandsResp, ipsResp] = await Promise.all([
          fetch(`/api/files/read?filepath=${encodeURIComponent(LAYOUT_FILEPATH)}`),
          fetch('/api/robot/commands'),
          fetch('/api/network/scanned_ips'),
        ])
        const layoutsJson = await layoutsResp.json()
        const commandsJson = await commandsResp.json()
        const ipsJson = await ipsResp.json()

        if (layoutsJson.success && layoutsJson.content) {
          try {
            const parsed = JSON.parse(layoutsJson.content)
            if (Array.isArray(parsed.layouts) && parsed.layouts.length) {
              setLayoutData(parsed)
            }
          } catch (_e) {
            setLayoutData(defaultData)
          }
        }

        if (commandsJson.success && Array.isArray(commandsJson.commands)) {
          setCommands(commandsJson.commands)
          if (!selectedCommandId && commandsJson.commands[0]) {
            setSelectedCommandId(commandsJson.commands[0].id)
          }
        }

        if (ipsJson.success && Array.isArray(ipsJson.ips)) {
          setTargetIps(['LOCAL', ...ipsJson.ips])
        }
      } catch (e) {
        setError(e.message || 'Ошибка загрузки')
      }
    }
    load()
  }, [selectedCommandId])

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
    if (!selectedCommandId) {
      setError('Сначала выбери команду слева')
      return
    }
    const rect = event.currentTarget.getBoundingClientRect()
    const { x, y } = toRelativePoint(event, rect)

    const command = commandsMap[selectedCommandId]
    const nextButton = {
      id: uid('btn'),
      commandId: selectedCommandId,
      label: command?.name || selectedCommandId,
      icon: '●',
      x,
      y,
      size: 64,
      targetIps: selectedTargetIps.length ? selectedTargetIps : ['LOCAL'],
    }

    updateActiveLayout((layout) => ({
      ...layout,
      buttons: [...(layout.buttons || []), nextButton],
    }))
    setSelectedButtonId(nextButton.id)
    setMessage('Кнопка добавлена')
    setError('')
  }

  const toggleTargetIpForNewButton = (ip) => {
    setSelectedTargetIps((prev) => {
      const set = new Set(prev)
      if (set.has(ip)) set.delete(ip)
      else set.add(ip)
      const next = Array.from(set)
      return next.length ? next : ['LOCAL']
    })
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

  const updateSelectedButton = (patch) => {
    if (!selectedButtonId) return
    updateActiveLayout((layout) => ({
      ...layout,
      buttons: (layout.buttons || []).map((button) =>
        button.id === selectedButtonId ? { ...button, ...patch } : button,
      ),
    }))
  }

  const deleteSelectedButton = () => {
    if (!selectedButtonId) return
    updateActiveLayout((layout) => ({
      ...layout,
      buttons: (layout.buttons || []).filter((button) => button.id !== selectedButtonId),
    }))
    setSelectedButtonId(null)
    setMessage('Кнопка удалена')
  }

  const saveLayouts = async () => {
    try {
      setMessage('')
      setError('')
      const payload = {
        filepath: LAYOUT_FILEPATH,
        content: JSON.stringify(layoutData, null, 2),
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

  const addLayout = () => {
    const nextLayout = { id: uid('layout'), name: `Раскладка ${layouts.length + 1}`, buttons: [] }
    setLayoutData((prev) => ({ ...prev, layouts: [...(prev.layouts || []), nextLayout] }))
    setLayoutIndex(layouts.length)
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
    <div className="editctl-page">
      <LayoutToolbar
        layoutName={activeLayout?.name || ''}
        onLayoutNameChange={(name) => updateActiveLayout((layout) => ({ ...layout, name }))}
        onPrevLayout={() => switchLayout(-1)}
        onNextLayout={() => switchLayout(1)}
        onAddLayout={addLayout}
        onDeleteLayout={deleteLayout}
        onSave={saveLayouts}
      />

      <div className="editctl-body">
        <AddPanel
          commands={commands}
          selectedCommandId={selectedCommandId}
          onSelectCommand={setSelectedCommandId}
          selectedTargetIps={selectedTargetIps}
          targetIps={targetIps}
          onToggleTargetIp={toggleTargetIpForNewButton}
        />

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
        />

        <ButtonPropertiesPanel
          selectedButton={selectedButton}
          targetIps={targetIps}
          onPatchButton={updateSelectedButton}
          onDeleteButton={deleteSelectedButton}
        />
      </div>

      {(message || error) && <div className={`editor-toast ${error ? 'error' : ''}`}>{error || message}</div>}
    </div>
  )
}

export default EditControlLayoutPage
