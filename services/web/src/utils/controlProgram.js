/** Нормализация сценария кнопки (legacy: только commandId). */
export function normalizeProgramFromButton(button) {
  if (Array.isArray(button.program) && button.program.length > 0) {
    return button.program
  }
  if (button.commandId) {
    return [
      {
        type: 'command',
        id: 'legacy',
        commandId: button.commandId,
        delayBeforeMs: 0,
        delayAfterMs: 0,
        targetIps: null,
      },
    ]
  }
  return []
}

export function derivePrimaryCommandId(program) {
  for (const b of program) {
    if (b.type === 'delay') continue
    if (b.type === 'command' && b.commandId) return b.commandId
    if (b.type === 'parallel' && Array.isArray(b.items)) {
      const first = b.items.find((x) => x.commandId)
      if (first) return first.commandId
    }
  }
  return ''
}

/** Все IP из шагов + базовые target кнопки (для подсказок недоступных). */
export function collectAllTargetsFromButton(button) {
  const base = []
  const raw = button.targetIps ?? (button.targetIp ? [button.targetIp] : ['LOCAL'])
  const list = Array.isArray(raw) ? raw : [raw]
  for (const t of list) {
    const s = String(t).trim()
    if (s) base.push(s)
  }
  const set = new Set(base)
  for (const block of button.program || []) {
    if (block.type === 'command' && Array.isArray(block.targetIps) && block.targetIps.length) {
      block.targetIps.forEach((t) => set.add(String(t).trim()))
    }
    if (block.type === 'parallel' && Array.isArray(block.items)) {
      block.items.forEach((it) => {
        if (Array.isArray(it.targetIps) && it.targetIps.length) {
          it.targetIps.forEach((t) => set.add(String(t).trim()))
        }
      })
    }
  }
  return Array.from(set).filter(Boolean)
}

export function normalizeTargetList(button) {
  const raw = button.targetIps ?? (button.targetIp ? [button.targetIp] : ['LOCAL'])
  const list = Array.isArray(raw) ? raw : [raw]
  return [...new Set(list.map((t) => String(t).trim()).filter(Boolean))]
}

/**
 * Проверка сценария перед сохранением / на /control.
 * @param {Array} program
 * @param {Record<string, object>} commandsMap id → команда из API
 */
export function validateProgram(program, commandsMap) {
  const errors = []
  if (!program.length) errors.push('Добавьте хотя бы один шаг')

  program.forEach((block, i) => {
    const n = i + 1
    if (block.type === 'command') {
      if (!block.commandId) errors.push(`Шаг ${n}: не выбрана команда`)
      else if (!commandsMap[block.commandId]) errors.push(`Шаг ${n}: команда «${block.commandId}» недоступна на роботе`)
    } else if (block.type === 'delay') {
      const ms = Number(block.ms)
      if (!Number.isFinite(ms) || ms < 0) errors.push(`Шаг ${n}: задержка должна быть >= 0 мс`)
    } else if (
      block.type === 'stop' ||
      block.type === 'continue' ||
      block.type === 'abort' ||
      block.type === 'and' ||
      block.type === 'or'
    ) {
      // ok
    } else if (block.type === 'parallel') {
      const items = block.items || []
      if (!items.length) errors.push(`Блок ${n} (параллель): добавьте хотя бы одну ветку`)
      items.forEach((it, j) => {
        if (!it.commandId) errors.push(`Параллель ${n}, ветка ${j + 1}: нет команды`)
        else if (!commandsMap[it.commandId]) {
          errors.push(`Параллель ${n}, ветка ${j + 1}: «${it.commandId}» недоступна`)
        }
      })
    } else {
      errors.push(`Шаг ${n}: неподдерживаемый тип «${block.type}»`)
    }
  })

  return { ok: errors.length === 0, errors }
}
