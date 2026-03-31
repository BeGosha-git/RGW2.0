import React, { useMemo } from 'react'
import IconGlyph from '../IconGlyph'

function ButtonPropertiesPanel({ selectedButton, commands, targetIps, onPatchButton, onDeleteButton }) {
  const selected = selectedButton?.targetIps || (selectedButton?.targetIp ? [selectedButton.targetIp] : ['LOCAL'])
  const ICON_PRESETS = useMemo(() => {
    const bases = [
      { id: 'mv_walk', title: 'Ходьба' },
      { id: 'mv_run', title: 'Бег' },
      { id: 'mv_jump', title: 'Прыжок' },
      { id: 'mv_squat', title: 'Присед' },
      { id: 'mv_sit', title: 'Сесть' },
      { id: 'mv_stand', title: 'Встать' },
      { id: 'mv_wave', title: 'Помахать' },
      { id: 'mv_hug', title: 'Обнимашки' },
      { id: 'mv_dance', title: 'Танец' },
      { id: 'mv_turn_left', title: 'Поворот влево' },
      { id: 'mv_turn_right', title: 'Поворот вправо' },
      { id: 'mv_stop', title: 'Стоп' },
    ]
    const out = []
    for (const b of bases) {
      for (let i = 1; i <= 6; i++) out.push({ id: `${b.id}_${i}`, title: `${b.title} ${i}` })
    }
    return out
  }, [])

  const toggleTargetIp = (ip) => {
    const set = new Set(selected)
    if (set.has(ip)) set.delete(ip)
    else set.add(ip)
    const next = Array.from(set)
    onPatchButton({ targetIps: next.length ? next : ['LOCAL'] })
  }

  return (
    <div className="right-panel">
      <h3>Свойства кнопки</h3>
      {selectedButton ? (
        <>
          <label>Подпись</label>
          <input value={selectedButton.label || ''} onChange={(e) => onPatchButton({ label: e.target.value })} />

          <label>Иконка</label>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 8 }}>
            {ICON_PRESETS.map((ico) => {
              const active = (selectedButton.icon || 'mv_walk_1') === ico.id
              return (
                <button
                  key={ico.id}
                  type="button"
                  className={`shape-chip ${active ? 'active' : ''}`}
                  onClick={() => onPatchButton({ icon: ico.id })}
                  title={ico.title}
                  style={{ color: '#fff' }}
                >
                  <IconGlyph name={ico.id} size={18} title={ico.title} />
                </button>
              )
            })}
          </div>
          <input
            value={selectedButton.icon || ''}
            onChange={(e) => onPatchButton({ icon: Array.from(e.target.value || '').slice(0, 24).join('') })}
            placeholder="например mv_hug_1 или legacy emoji"
          />

          <label>Роботы по умолчанию</label>
          <p className="panel-hint program-hint">
            Используются шагами без «Свои роботы». Параллельный блок может направить разные команды на разные IP.
          </p>
          <div className="targets-checklist">
            {targetIps.map((ip) => (
              <label key={ip} className="target-item">
                <input type="checkbox" checked={selected.includes(ip)} onChange={() => toggleTargetIp(ip)} />
                <span>{ip}</span>
              </label>
            ))}
          </div>

          <label>Размер</label>
          <input
            type="range"
            min="44"
            max="120"
            value={selectedButton.size || 64}
            onChange={(e) => onPatchButton({ size: Number(e.target.value) })}
          />
          <button className="danger-btn danger-btn--filled" onClick={onDeleteButton}>
            Удалить кнопку
          </button>
        </>
      ) : (
        <p className="panel-hint">Выбери кнопку на поле, чтобы изменить свойства.</p>
      )}
    </div>
  )
}

export default ButtonPropertiesPanel
