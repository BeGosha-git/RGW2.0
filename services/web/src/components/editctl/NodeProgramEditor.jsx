import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import ReactFlow, {
  addEdge,
  Background,
  Controls,
  MiniMap,
  Handle,
  Position,
  useEdgesState,
  useNodesState,
} from 'reactflow'
import 'reactflow/dist/style.css'

import CustomSelect from '../CustomSelect'

function uid(prefix) {
  return `${prefix}-${Date.now()}-${Math.random().toString(16).slice(2, 6)}`
}

function clampMs(v) {
  const n = Number(v)
  if (!Number.isFinite(n)) return 0
  return Math.max(0, Math.round(n))
}

function IntField({ value, onChange, min = 0, ariaLabel }) {
  const [raw, setRaw] = useState(String(value ?? 0))

  useEffect(() => {
    setRaw(String(value ?? 0))
  }, [value])

  const commit = (nextRaw) => {
    const cleaned = String(nextRaw ?? '').replace(/[^\d]/g, '')
    const n = cleaned === '' ? 0 : Math.max(min, parseInt(cleaned, 10) || 0)
    onChange(n)
  }

  return (
    <input
      className="int-field"
      inputMode="numeric"
      pattern="[0-9]*"
      aria-label={ariaLabel}
      value={raw}
      onChange={(e) => {
        const nextRaw = e.target.value
        setRaw(nextRaw)
        commit(nextRaw)
      }}
      onBlur={() => commit(raw)}
      onKeyDown={(e) => {
        if (e.key === 'e' || e.key === 'E' || e.key === '+' || e.key === '-' || e.key === '.' || e.key === ',') {
          e.preventDefault()
        }
      }}
    />
  )
}

function TargetsEditor({ allTargets, valueTargets, onPatchTargets, targetMeta }) {
  const set = new Set(valueTargets || [])

  const toggle = (ip) => {
    const next = new Set(valueTargets || [])
    if (next.has(ip)) next.delete(ip)
    else next.add(ip)
    const arr = Array.from(next)
    onPatchTargets(arr.length ? arr : [])
  }

  return (
    <div className="node-targets">
      <div className="node-targets__list">
        {(allTargets || []).map((ip) => (
          (() => {
            const meta = targetMeta?.[ip]
            const bg = meta?.bg
            const fg = meta?.fg
            return (
          <label
            key={ip}
            className={`node-targets__chip ${set.has(ip) ? 'on' : ''}`}
            style={bg ? { backgroundColor: bg, color: fg || undefined, borderColor: 'rgba(255,255,255,0.14)' } : undefined}
            onPointerDown={(e) => e.stopPropagation()}
            onMouseDown={(e) => e.stopPropagation()}
            onClick={(e) => e.stopPropagation()}
          >
            <input
              type="checkbox"
              checked={set.has(ip)}
              onPointerDown={(e) => e.stopPropagation()}
              onMouseDown={(e) => e.stopPropagation()}
              onChange={() => toggle(ip)}
            />
            <span>{ip}</span>
          </label>
            )
          })()
        ))}
      </div>
    </div>
  )
}

function StartNode() {
  return (
    <div className="node node--start">
      <div className="node__head">START</div>
      <div className="node__body">
        <div className="node__note">Отсюда начинается сценарий. Соедини с первым блоком.</div>
      </div>
      <Handle type="source" position={Position.Bottom} className="node-handle node-handle--out" />
    </div>
  )
}

function SimpleSignalNode({ title, className, hint }) {
  return (
    <div className={`node ${className || ''}`}>
      <Handle type="target" position={Position.Top} className="node-handle node-handle--in" />
      <div className="node__head">{title}</div>
      <div className="node__body">
        <div className="node__note">{hint}</div>
      </div>
      <Handle type="source" position={Position.Bottom} className="node-handle node-handle--out" />
    </div>
  )
}

function CommandNode({ id, data }) {
  const { commandOptions, value, onPatch, allTargets, targetMeta, scenarioUi } = data
  const stepIndex = Number.isFinite(Number(scenarioUi?.stepIndexByNodeId?.[id])) ? Number(scenarioUi.stepIndexByNodeId[id]) : null
  const participants = scenarioUi?.participants || null
  const readyByStep = scenarioUi?.readyByStep || null
  const paused = !!scenarioUi?.paused
  const continueSet = !!scenarioUi?.continueSet
  const isWait = !!value.waitContinue
  const readySet = stepIndex != null && readyByStep ? new Set(readyByStep[String(stepIndex)] || readyByStep[stepIndex] || []) : null
  const readyCount = readySet && participants ? participants.filter((p) => readySet.has(p)).length : null
  const totalCount = participants ? participants.length : null

  return (
    <div className="node node--command">
      <Handle type="target" position={Position.Top} className="node-handle node-handle--in" />
      <div className="node__head">
        Команда
        {scenarioUi?.active ? (
          <span className="node__status">
            {paused ? 'PAUSE' : isWait && !continueSet ? 'Ждём ПРОДОЛЖИТЬ' : ''}
            {readyCount != null && totalCount != null ? ` ${readyCount}/${totalCount}` : ''}
          </span>
        ) : null}
      </div>
      <div className="node__body">
        <CustomSelect
          value={value.commandId || commandOptions[0]?.value || ''}
          options={commandOptions}
          onChange={(v) => onPatch(id, { commandId: v })}
        />
        <div className="node__grid">
          <label>
            <span>до (мс)</span>
            <IntField value={value.delayBeforeMs ?? 0} ariaLabel="delay before ms" onChange={(n) => onPatch(id, { delayBeforeMs: clampMs(n) })} />
          </label>
          <label>
            <span>после (мс)</span>
            <IntField value={value.delayAfterMs ?? 0} ariaLabel="delay after ms" onChange={(n) => onPatch(id, { delayAfterMs: clampMs(n) })} />
          </label>
        </div>

        <TargetsEditor
          allTargets={allTargets || ['LOCAL']}
          valueTargets={value.targetIps ?? null}
          onPatchTargets={(v) => onPatch(id, { targetIps: v })}
          targetMeta={targetMeta}
        />

        <label className="node__wait-continue" onPointerDown={(e) => e.stopPropagation()} onMouseDown={(e) => e.stopPropagation()}>
          <input
            type="checkbox"
            checked={!!value.waitContinue}
            onPointerDown={(e) => e.stopPropagation()}
            onMouseDown={(e) => e.stopPropagation()}
            onChange={(e) => onPatch(id, { waitContinue: !!e.target.checked })}
          />
          <span>Ждать «ПРОДОЛЖИТЬ» + готовность всех</span>
        </label>
      </div>
      <Handle type="source" position={Position.Bottom} className="node-handle node-handle--out" />
    </div>
  )
}

function DelayNode({ id, data }) {
  const { value, onPatch } = data
  return (
    <div className="node node--delay">
      <Handle type="target" position={Position.Top} className="node-handle node-handle--in" />
      <div className="node__head">Задержка</div>
      <div className="node__body">
        <label className="node__single">
          <span>мс</span>
          <IntField value={value.ms ?? 0} ariaLabel="delay ms" onChange={(n) => onPatch(id, { ms: clampMs(n) })} />
        </label>
      </div>
      <Handle type="source" position={Position.Bottom} className="node-handle node-handle--out" />
    </div>
  )
}

const nodeTypes = {
  start: StartNode,
  command: CommandNode,
  delay: DelayNode,
  stop: () => <SimpleSignalNode title="СТОП" className="node--stop" hint="Пауза: все ждут «ПРОДОЛЖИТЬ»." />,
  continue: () => <SimpleSignalNode title="ПРОДОЛЖИТЬ" className="node--continue" hint="Снимает паузу и разрешает ожидания." />,
  abort: () => <SimpleSignalNode title="ПРЕРВАТЬ" className="node--abort" hint="Прерывает сценарий и очищает список." />,
}

function programToGraph(program, commandOptions) {
  const nodes = [
    {
      id: 'start',
      type: 'start',
      position: { x: 0, y: 0 },
      data: { value: {} },
    },
  ]
  const edges = []

  const baseX = 0
  let y = 140
  const gapY = 140

  for (let i = 0; i < (program || []).length; i++) {
    const b = program[i]
    if (!b || (b.type !== 'command' && b.type !== 'delay' && b.type !== 'stop' && b.type !== 'continue' && b.type !== 'abort'))
      continue

    const id = b.id || uid(b.type === 'delay' ? 'd' : 'c')
    const posX = Number.isFinite(Number(b.x)) ? Number(b.x) : baseX
    const posY = Number.isFinite(Number(b.y)) ? Number(b.y) : y
    const node = {
      id,
      type: b.type,
      position: { x: posX, y: posY },
      data: {
        value:
          b.type === 'command'
            ? {
                commandId: b.commandId || commandOptions[0]?.value || '',
                delayBeforeMs: b.delayBeforeMs ?? 0,
                delayAfterMs: b.delayAfterMs ?? 0,
                targetIps: b.targetIps ?? null,
                waitContinue: !!b.waitContinue,
              }
            : b.type === 'delay'
              ? { ms: b.ms ?? 0 }
              : {},
      },
    }
    nodes.push(node)
    // if positions are from file, keep a stable auto-layout gap for next nodes
    y = posY + gapY
  }

  for (let i = 0; i < nodes.length - 1; i++) {
    edges.push({
      id: `e-${nodes[i].id}-${nodes[i + 1].id}`,
      source: nodes[i].id,
      target: nodes[i + 1].id,
      type: 'smoothstep',
      animated: false,
    })
  }

  return { nodes, edges }
}

function graphToProgram(nodes, edges) {
  const round2 = (v) => {
    const n = Number(v)
    if (!Number.isFinite(n)) return 0
    return Number(n.toFixed(2))
  }
  const byId = new Map(nodes.map((n) => [n.id, n]))
  const incoming = new Map()
  const outgoing = new Map()

  for (const n of nodes) {
    incoming.set(n.id, [])
    outgoing.set(n.id, [])
  }
  for (const e of edges) {
    if (!incoming.has(e.target) || !outgoing.has(e.source)) continue
    incoming.get(e.target).push(e)
    outgoing.get(e.source).push(e)
  }

  // Одноцепочечный граф (как большинство простых flow): максимум 1 вход и 1 выход у узла.
  for (const n of nodes) {
    const inc = incoming.get(n.id) || []
    const out = outgoing.get(n.id) || []
    if (inc.length > 1) throw new Error('У узла может быть только одно входящее соединение')
    if (out.length > 1) throw new Error('У узла может быть только одно исходящее соединение')
  }

  const start = byId.get('start') || null
  if (!start) return []

  const ordered = []
  const seen = new Set()
  let cur = start
  while (cur && !seen.has(cur.id)) {
    seen.add(cur.id)
    ordered.push(cur)
    const out = outgoing.get(cur.id) || []
    if (!out.length) break
    cur = byId.get(out[0].target) || null
  }

  // Если есть несвязанные узлы — считаем ошибкой (иначе “потеряются”).
  if (seen.size !== nodes.length) {
    throw new Error('Есть несвязанные ноды. Соедини все блоки в одну цепочку.')
  }

  const program = ordered
    .filter((n) => n.id !== 'start')
    .map((n) => {
    if (n.type === 'delay') {
      return {
        type: 'delay',
        id: n.id,
        ms: clampMs(n.data?.value?.ms),
        x: round2(n.position?.x),
        y: round2(n.position?.y),
      }
    }
    if (n.type === 'stop' || n.type === 'continue' || n.type === 'abort') {
      return {
        type: n.type,
        id: n.id,
        x: round2(n.position?.x),
        y: round2(n.position?.y),
      }
    }
    return {
      type: 'command',
      id: n.id,
      commandId: n.data?.value?.commandId || '',
      delayBeforeMs: clampMs(n.data?.value?.delayBeforeMs),
      delayAfterMs: clampMs(n.data?.value?.delayAfterMs),
      targetIps: n.data?.value?.targetIps ?? null,
      waitContinue: !!n.data?.value?.waitContinue,
      x: round2(n.position?.x),
      y: round2(n.position?.y),
    }
  })

  return program
}

export default function NodeProgramEditor({ program, commands, targetIps, targetMeta, scenarioKey, onChangeProgram, onError }) {
  const commandOptions = useMemo(
    () => (commands || []).map((c) => ({ value: c.id, label: c.name || c.id })),
    [commands],
  )
  const allTargets = useMemo(() => (Array.isArray(targetIps) && targetIps.length ? targetIps : ['LOCAL']), [targetIps])

  const patchNode = useCallback((nodeId, patch) => {
    setNodes((prev) =>
      prev.map((n) =>
        n.id === nodeId ? { ...n, data: { ...n.data, value: { ...(n.data?.value || {}), ...patch } } } : n,
      ),
    )
  }, [])

  const { nodes: initialNodes, edges: initialEdges } = useMemo(
    () => programToGraph(program, commandOptions),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [JSON.stringify(program || []), JSON.stringify(commandOptions || [])],
  )

  const [nodes, setNodes, onNodesChange] = useNodesState(
    initialNodes.map((n) => ({
      ...n,
      data: { ...n.data, commandOptions, allTargets, targetMeta, onPatch: patchNode },
    })),
  )
  const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges)

  const lastEmitRef = useRef(0)

  // Реинициализация при переключении кнопки (program меняется)
  useEffect(() => {
    setNodes(
      initialNodes.map((n) => ({
        ...n,
        data: { ...n.data, commandOptions, allTargets, targetMeta, onPatch: patchNode },
      })),
    )
    setEdges(initialEdges)
  }, [initialNodes, initialEdges, commandOptions, allTargets, targetMeta, patchNode, setNodes, setEdges])

  // --- scenario state polling (for "готов/ждём") ---
  const [scenarioUi, setScenarioUi] = useState({ active: false })

  const stepIndexByNodeId = useMemo(() => {
    // index according to current ordered program (start excluded)
    try {
      const orderedProgram = graphToProgram(nodes, edges)
      const map = {}
      for (let i = 0; i < orderedProgram.length; i++) {
        const id = orderedProgram[i]?.id
        if (id) map[id] = i
      }
      return map
    } catch (_e) {
      return {}
    }
  }, [nodes, edges])

  useEffect(() => {
    let alive = true
    const tick = async () => {
      try {
        if (!scenarioKey) {
          if (alive) setScenarioUi({ active: false })
          return
        }
        const resp = await fetch('/api/robot/scenario/state')
        const json = await resp.json()
        const sid = String(json?.scenarioId || '')
        const active = !!sid && sid === String(scenarioKey)
        if (!alive) return
        if (!active) {
          setScenarioUi({ active: false })
          return
        }
        const selfId = String(json?.selfId || 'LOCAL')
        const peers = Array.isArray(json?.peers) ? json.peers.map((x) => String(x)) : []
        const participants = Array.from(new Set([selfId, ...peers])).filter(Boolean)
        setScenarioUi({
          active: true,
          paused: !!json?.paused,
          continueSet: !!json?.continueSet,
          readyByStep: json?.readyByStep || {},
          participants,
          stepIndexByNodeId,
        })
      } catch (_e) {
        if (alive) setScenarioUi({ active: false })
      }
    }

    tick()
    const t = window.setInterval(tick, 600)
    return () => {
      alive = false
      window.clearInterval(t)
    }
  }, [scenarioKey, stepIndexByNodeId])

  // inject scenarioUi into node data
  useEffect(() => {
    setNodes((prev) =>
      prev.map((n) => ({
        ...n,
        data: { ...n.data, scenarioUi },
      })),
    )
  }, [scenarioUi, setNodes])

  const emit = useCallback(
    (nextNodes, nextEdges) => {
      const now = Date.now()
      if (now - lastEmitRef.current < 120) return
      lastEmitRef.current = now

      const nextProgram = graphToProgram(nextNodes, nextEdges)
      onChangeProgram(nextProgram)
    },
    [onChangeProgram],
  )

  const onConnect = useCallback(
    (params) => {
      setEdges((eds) => {
        const src = String(params.source || '')
        const tgt = String(params.target || '')
        if (!src || !tgt) return eds

        // Toggle: повторное соединение тех же нод удаляет ребро
        const existsIdx = eds.findIndex((e) => String(e.source) === src && String(e.target) === tgt)
        if (existsIdx >= 0) {
          return eds.filter((_, i) => i !== existsIdx)
        }

        return addEdge({ ...params, type: 'smoothstep' }, eds)
      })
    },
    [setEdges],
  )

  const selectedIds = useMemo(() => new Set(nodes.filter((n) => n.selected).map((n) => n.id)), [nodes])

  const deleteSelected = useCallback(() => {
    const ids = Array.from(selectedIds).filter((id) => id !== 'start')
    if (!ids.length) return
    const ok = window.confirm(`Удалить нод(ы): ${ids.length}?`)
    if (!ok) return
    setNodes((prev) => prev.filter((n) => !ids.includes(n.id)))
    setEdges((prev) => prev.filter((e) => !ids.includes(e.source) && !ids.includes(e.target) && !e.selected))
  }, [selectedIds, setNodes, setEdges])

  useEffect(() => {
    const onKey = (e) => {
      if (e.key !== 'Delete' && e.key !== 'Backspace') return
      // не ломаем ввод в полях
      const tag = String(e.target?.tagName || '').toLowerCase()
      if (tag === 'input' || tag === 'textarea' || e.target?.isContentEditable) return
      deleteSelected()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [deleteSelected])

  const addCommand = () => {
    const id = uid('c')
    const maxY = Math.max(0, ...nodes.map((n) => n.position?.y ?? 0))
    const next = {
      id,
      type: 'command',
      position: { x: 0, y: maxY + 120 },
      data: {
        value: { commandId: commandOptions[0]?.value || '', delayBeforeMs: 0, delayAfterMs: 0, targetIps: null },
        commandOptions,
        allTargets,
        onPatch: patchNode,
      },
    }
    setNodes((prev) => [...prev, next])
    if (nodes.length) {
      const last = [...nodes].sort((a, b) => (a.position?.y ?? 0) - (b.position?.y ?? 0)).at(-1)
      if (last) {
        setEdges((prev) => [
          ...prev,
          { id: `e-${last.id}-${id}`, source: last.id, target: id, type: 'smoothstep' },
        ])
      }
    }
  }

  const addStop = () => {
    const id = uid('s')
    const maxY = Math.max(0, ...nodes.map((n) => n.position?.y ?? 0))
    const next = { id, type: 'stop', position: { x: 0, y: maxY + 120 }, data: { value: {} } }
    setNodes((prev) => [...prev, next])
  }

  const addContinue = () => {
    const id = uid('k')
    const maxY = Math.max(0, ...nodes.map((n) => n.position?.y ?? 0))
    const next = { id, type: 'continue', position: { x: 0, y: maxY + 120 }, data: { value: {} } }
    setNodes((prev) => [...prev, next])
  }

  const addAbort = () => {
    const id = uid('a')
    const maxY = Math.max(0, ...nodes.map((n) => n.position?.y ?? 0))
    const next = { id, type: 'abort', position: { x: 0, y: maxY + 120 }, data: { value: {} } }
    setNodes((prev) => [...prev, next])
  }

  const addDelay = () => {
    const id = uid('d')
    const maxY = Math.max(0, ...nodes.map((n) => n.position?.y ?? 0))
    const next = {
      id,
      type: 'delay',
      position: { x: 0, y: maxY + 120 },
      data: {
        value: { ms: 500 },
        commandOptions,
        allTargets,
        onPatch: patchNode,
      },
    }
    setNodes((prev) => [...prev, next])
    if (nodes.length) {
      const last = [...nodes].sort((a, b) => (a.position?.y ?? 0) - (b.position?.y ?? 0)).at(-1)
      if (last) {
        setEdges((prev) => [
          ...prev,
          { id: `e-${last.id}-${id}`, source: last.id, target: id, type: 'smoothstep' },
        ])
      }
    }
  }

  // Авто-сохранение в program при любых изменениях графа
  useEffect(() => {
    try {
      emit(nodes, edges)
    } catch (_e) {
      if (typeof onError === 'function') onError(_e?.message || 'Ошибка графа')
    }
  }, [nodes, edges, emit])

  return (
    <div className="node-editor">
      <div className="node-editor__bar">
        <button type="button" className="node-editor__btn" onClick={addCommand}>
          + Команда
        </button>
        <button type="button" className="node-editor__btn node-editor__btn--accent" onClick={addDelay}>
          + Задержка
        </button>
        <button type="button" className="node-editor__btn" onClick={addStop} title="Пауза (ждём ПРОДОЛЖИТЬ)">
          + СТОП
        </button>
        <button type="button" className="node-editor__btn" onClick={addContinue} title="Разрешить продолжение">
          + ПРОДОЛЖИТЬ
        </button>
        <button type="button" className="node-editor__btn node-editor__btn--danger" onClick={addAbort} title="Прервать сценарий">
          + ПРЕРВАТЬ
        </button>
        <button
          type="button"
          className="node-editor__btn node-editor__btn--danger"
          onClick={deleteSelected}
          disabled={Array.from(selectedIds).filter((id) => id !== 'start').length === 0}
          title="Удалить выбранную ноду (Delete)"
        >
          Удалить
        </button>
        <span className="node-editor__hint">Перетаскивай блоки и соединяй их. Сейчас поддерживается одна цепочка.</span>
      </div>

      <div className="node-editor__canvas">
        <ReactFlow
          nodes={nodes}
          edges={edges}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onConnect={onConnect}
          nodeTypes={nodeTypes}
          fitView
          proOptions={{ hideAttribution: false }}
        >
          <Background gap={14} size={1} />
          <MiniMap pannable zoomable />
          <Controls />
        </ReactFlow>
      </div>
    </div>
  )
}

