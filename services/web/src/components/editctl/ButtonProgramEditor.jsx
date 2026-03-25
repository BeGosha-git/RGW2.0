import React, { useMemo, useState } from 'react'
import CustomSelect from '../CustomSelect'
import { derivePrimaryCommandId, validateProgram } from '../../utils/controlProgram'

function stepUid(prefix) {
  return `${prefix}-${Date.now()}-${Math.random().toString(16).slice(2, 6)}`
}

const DELAY_PRESETS = [
  { label: '0.25с', ms: 250 },
  { label: '0.5с', ms: 500 },
  { label: '1с', ms: 1000 },
  { label: '2с', ms: 2000 },
]

function DelayFieldset({ beforeLabel, afterLabel, beforeVal, afterVal, onBefore, onAfter }) {
  return (
    <div className="program-delays">
      <label>
        <span>{beforeLabel}</span>
        <input type="number" min="0" step="50" value={beforeVal ?? 0} onChange={(e) => onBefore(Math.max(0, Number(e.target.value) || 0))} />
      </label>
      <label>
        <span>{afterLabel}</span>
        <input type="number" min="0" step="50" value={afterVal ?? 0} onChange={(e) => onAfter(Math.max(0, Number(e.target.value) || 0))} />
      </label>
      <div className="program-delay-presets">
        <span className="program-delay-presets__ttl">Быстро «после»:</span>
        {DELAY_PRESETS.map((p) => (
          <button key={p.ms} type="button" className="program-preset-chip" onClick={() => onAfter((afterVal ?? 0) + p.ms)}>
            +{p.label}
          </button>
        ))}
        <button type="button" className="program-preset-chip program-preset-chip--muted" onClick={() => onAfter(0)}>
          сброс
        </button>
      </div>
    </div>
  )
}

function TargetOverrideSection({ targetIps, selectedList, onToggleIp, title }) {
  if (!targetIps.length) return null
  const set = new Set(selectedList || [])
  return (
    <div className="program-targets-wrap">
      {title ? <span className="program-sub">{title}</span> : null}
      <div className="program-mini-targets">
        {targetIps.map((ip) => (
          <label key={ip} className="program-target-chip">
            <input type="checkbox" checked={set.has(ip)} onChange={() => onToggleIp(ip)} />
            <span>{ip}</span>
          </label>
        ))}
      </div>
    </div>
  )
}

export default function ButtonProgramEditor({ program, commands, targetIps, onChangeProgram }) {
  const commandsMap = useMemo(() => {
    const m = {}
    for (const c of commands) m[c.id] = c
    return m
  }, [commands])

  const commandOptions = useMemo(() => commands.map((c) => ({ value: c.id, label: c.name || c.id })), [commands])
  const firstCmd = commands[0]?.id || ''
  const validation = useMemo(() => validateProgram(program, commandsMap), [program, commandsMap])

  const [collapsed, setCollapsed] = useState(() => new Set())

  const emit = (next) => {
    onChangeProgram(next, derivePrimaryCommandId(next))
  }

  const toggleCollapse = (id) => {
    setCollapsed((prev) => {
      const n = new Set(prev)
      if (n.has(id)) n.delete(id)
      else n.add(id)
      return n
    })
  }

  const moveBlock = (idx, dir) => {
    const j = idx + dir
    if (j < 0 || j >= program.length) return
    const next = [...program]
    const t = next[idx]
    next[idx] = next[j]
    next[j] = t
    emit(next)
  }

  const removeBlock = (idx) => {
    emit(program.filter((_, i) => i !== idx))
  }

  const duplicateBlock = (idx) => {
    const copy = JSON.parse(JSON.stringify(program[idx]))
    const assignIds = (block) => {
      block.id = stepUid(block.type === 'parallel' ? 'par' : 'step')
      if (block.type === 'parallel' && Array.isArray(block.items)) {
        block.items = block.items.map((it) => ({ ...it, id: stepUid('pi') }))
      }
    }
    assignIds(copy)
    const next = [...program.slice(0, idx + 1), copy, ...program.slice(idx + 1)]
    emit(next)
  }

  const addCommandStep = () => {
    emit([
      ...program,
      {
        type: 'command',
        id: stepUid('step'),
        commandId: firstCmd,
        delayBeforeMs: 0,
        delayAfterMs: 0,
        targetIps: null,
      },
    ])
  }

  const addParallelBlock = () => {
    emit([
      ...program,
      {
        type: 'parallel',
        id: stepUid('par'),
        delayBeforeMs: 0,
        delayAfterMs: 0,
        items: [
          {
            id: stepUid('pi'),
            commandId: firstCmd,
            delayBeforeMs: 0,
            delayAfterMs: 0,
            targetIps: null,
          },
        ],
      },
    ])
  }

  const patchBlock = (idx, patch) => {
    emit(program.map((b, i) => (i === idx ? { ...b, ...patch } : b)))
  }

  const patchParallelItem = (blockIdx, itemId, patch) => {
    const block = program[blockIdx]
    if (block.type !== 'parallel') return
    const items = (block.items || []).map((it) => (it.id === itemId ? { ...it, ...patch } : it))
    patchBlock(blockIdx, { items })
  }

  const addParallelItem = (blockIdx) => {
    const block = program[blockIdx]
    if (block.type !== 'parallel') return
    const items = [
      ...(block.items || []),
      { id: stepUid('pi'), commandId: firstCmd, delayBeforeMs: 0, delayAfterMs: 0, targetIps: null },
    ]
    patchBlock(blockIdx, { items })
  }

  const removeParallelItem = (blockIdx, itemId) => {
    const block = program[blockIdx]
    if (block.type !== 'parallel') return
    const items = (block.items || []).filter((it) => it.id !== itemId)
    if (!items.length) return
    patchBlock(blockIdx, { items })
  }

  const toggleStepIp = (blockIdx, ip, isParallel, itemId) => {
    const toggle = (cur) => {
      const set = new Set(cur || [])
      if (set.has(ip)) set.delete(ip)
      else set.add(ip)
      const arr = Array.from(set)
      return arr.length ? arr : null
    }
    if (isParallel) {
      const block = program[blockIdx]
      if (block.type !== 'parallel') return
      const it = block.items?.find((x) => x.id === itemId)
      if (!it) return
      patchParallelItem(blockIdx, itemId, { targetIps: toggle(it.targetIps) })
    } else {
      const b = program[blockIdx]
      if (b.type !== 'command') return
      patchBlock(blockIdx, { targetIps: toggle(b.targetIps) })
    }
  }

  const useDefaultToggle = (blockIdx, useDefault, isParallel, itemId) => {
    if (isParallel) {
      patchParallelItem(blockIdx, itemId, { targetIps: useDefault ? null : [] })
    } else {
      patchBlock(blockIdx, { targetIps: useDefault ? null : [] })
    }
  }

  if (!commands.length) {
    return <p className="panel-hint">Команды не загружены</p>
  }

  return (
    <div className="program-editor">
      <div className="program-editor__intro">
        <p className="program-editor__lead">
          Шаги выполняются <strong>сверху вниз</strong>. Блок <strong>«Параллель»</strong> запускает ветки одновременно на разных роботах.
        </p>
        {!validation.ok && (
          <ul className="program-validation-errors">
            {validation.errors.map((err, i) => (
              <li key={i}>{err}</li>
            ))}
          </ul>
        )}
      </div>

      <div className="program-editor__header">
        <span className="program-editor__title">Сценарий</span>
        <div className="program-editor__add-btns">
          <button type="button" className="program-small-btn" onClick={addCommandStep}>
            + Шаг
          </button>
          <button type="button" className="program-small-btn program-small-btn--accent" onClick={addParallelBlock}>
            ‖ Параллель
          </button>
        </div>
      </div>

      {program.length === 0 ? (
        <p className="panel-hint">Добавь шаг или параллельный блок.</p>
      ) : (
        <ol className="program-timeline">
          {program.map((block, idx) => {
            const bid = block.id || `idx-${idx}`
            const isCollapsed = collapsed.has(bid)
            return (
              <li key={bid} className={`program-timeline__item program-block program-block--${block.type}`}>
                <div className="program-timeline__rail" aria-hidden />
                <div className="program-block__shell">
                  <div className="program-block__toolbar">
                    <button
                      type="button"
                      className="program-block__collapse-hit"
                      onClick={() => toggleCollapse(bid)}
                      aria-expanded={!isCollapsed}
                    >
                      <span className="program-block__chev">{isCollapsed ? '▸' : '▾'}</span>
                      <span className="program-block__badge">
                        {block.type === 'parallel'
                          ? `‖ Параллель · ${(block.items || []).length} ветк.`
                          : `${idx + 1}. Команда`}
                      </span>
                      {!isCollapsed && block.type === 'command' && (
                        <span className="program-block__hint">{commandsMap[block.commandId]?.name || block.commandId}</span>
                      )}
                    </button>
                    <div className="program-block__mover">
                      <button type="button" aria-label="Дублировать блок" title="Дублировать" onClick={() => duplicateBlock(idx)}>
                        ⧉
                      </button>
                      <button type="button" aria-label="Вверх" onClick={() => moveBlock(idx, -1)} disabled={idx === 0}>
                        ↑
                      </button>
                      <button type="button" aria-label="Вниз" onClick={() => moveBlock(idx, 1)} disabled={idx === program.length - 1}>
                        ↓
                      </button>
                      <button type="button" className="program-block__del" aria-label="Удалить" onClick={() => removeBlock(idx)}>
                        ×
                      </button>
                    </div>
                  </div>

                  {!isCollapsed && block.type === 'command' && (
                    <div className="program-block__body">
                      <label className="program-label">Команда</label>
                      <CustomSelect
                        value={block.commandId || firstCmd}
                        options={commandOptions}
                        onChange={(v) => patchBlock(idx, { commandId: v })}
                      />

                      <DelayFieldset
                        beforeLabel="Пауза до (мс)"
                        afterLabel="Пауза после (мс)"
                        beforeVal={block.delayBeforeMs}
                        afterVal={block.delayAfterMs}
                        onBefore={(v) => patchBlock(idx, { delayBeforeMs: v })}
                        onAfter={(v) => patchBlock(idx, { delayAfterMs: v })}
                      />

                      <label className="program-custom-targets">
                        <input
                          type="checkbox"
                          checked={block.targetIps != null}
                          onChange={(e) => useDefaultToggle(idx, !e.target.checked, false)}
                        />
                        <span>Свои роботы (иначе — «по умолчанию» слева)</span>
                      </label>
                      {block.targetIps != null && (
                        <TargetOverrideSection
                          targetIps={targetIps}
                          selectedList={block.targetIps}
                          title="Роботы шага"
                          onToggleIp={(ip) => toggleStepIp(idx, ip, false)}
                        />
                      )}
                    </div>
                  )}

                  {!isCollapsed && block.type === 'parallel' && (
                    <div className="program-block__body">
                      <DelayFieldset
                        beforeLabel="Пауза до блока (мс)"
                        afterLabel="Пауза после блока (мс)"
                        beforeVal={block.delayBeforeMs}
                        afterVal={block.delayAfterMs}
                        onBefore={(v) => patchBlock(idx, { delayBeforeMs: v })}
                        onAfter={(v) => patchBlock(idx, { delayAfterMs: v })}
                      />

                      <ul className="program-parallel-items">
                        {(block.items || []).map((it, j) => (
                          <li key={it.id} className="program-parallel-item">
                            <div className="program-parallel-item__head">Ветка {j + 1}</div>
                            <CustomSelect
                              value={it.commandId || firstCmd}
                              options={commandOptions}
                              onChange={(v) => patchParallelItem(idx, it.id, { commandId: v })}
                            />
                            <div className="program-delays program-delays--compact">
                              <label>
                                <span>до (мс)</span>
                                <input
                                  type="number"
                                  min="0"
                                  step="50"
                                  value={it.delayBeforeMs ?? 0}
                                  onChange={(e) =>
                                    patchParallelItem(idx, it.id, {
                                      delayBeforeMs: Math.max(0, Number(e.target.value) || 0),
                                    })
                                  }
                                />
                              </label>
                              <label>
                                <span>после (мс)</span>
                                <input
                                  type="number"
                                  min="0"
                                  step="50"
                                  value={it.delayAfterMs ?? 0}
                                  onChange={(e) =>
                                    patchParallelItem(idx, it.id, {
                                      delayAfterMs: Math.max(0, Number(e.target.value) || 0),
                                    })
                                  }
                                />
                              </label>
                            </div>
                            <div className="program-delay-presets program-delay-presets--inline">
                              {DELAY_PRESETS.map((p) => (
                                <button
                                  key={p.ms}
                                  type="button"
                                  className="program-preset-chip"
                                  onClick={() =>
                                    patchParallelItem(idx, it.id, {
                                      delayAfterMs: (it.delayAfterMs ?? 0) + p.ms,
                                    })
                                  }
                                >
                                  +{p.label}
                                </button>
                              ))}
                            </div>
                            <label className="program-custom-targets program-custom-targets--inline">
                              <input
                                type="checkbox"
                                checked={it.targetIps != null}
                                onChange={(e) => useDefaultToggle(idx, !e.target.checked, true, it.id)}
                              />
                              <span>Свои роботы</span>
                            </label>
                            {it.targetIps != null && (
                              <TargetOverrideSection
                                targetIps={targetIps}
                                selectedList={it.targetIps}
                                title=""
                                onToggleIp={(ip) => toggleStepIp(idx, ip, true, it.id)}
                              />
                            )}
                            {(block.items || []).length > 1 && (
                              <button type="button" className="program-remove-item" onClick={() => removeParallelItem(idx, it.id)}>
                                Удалить ветку
                              </button>
                            )}
                          </li>
                        ))}
                      </ul>
                      <button type="button" className="program-add-branch" onClick={() => addParallelItem(idx)}>
                        + Добавить ветку
                      </button>
                    </div>
                  )}
                </div>
              </li>
            )
          })}
        </ol>
      )}
    </div>
  )
}
