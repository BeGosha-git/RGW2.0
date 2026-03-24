import React from 'react'

function ButtonPropertiesPanel({ selectedButton, targetIps, onPatchButton, onDeleteButton }) {
  const selected = selectedButton?.targetIps || (selectedButton?.targetIp ? [selectedButton.targetIp] : ['LOCAL'])

  const toggleTargetIp = (ip) => {
    const set = new Set(selected)
    if (set.has(ip)) {
      set.delete(ip)
    } else {
      set.add(ip)
    }
    const next = Array.from(set)
    onPatchButton({ targetIps: next.length ? next : ['LOCAL'] })
  }

  return (
    <div className="right-panel">
      <h3>Свойства кнопки</h3>
      {selectedButton ? (
        <>
          <label>Подпись</label>
          <input
            value={selectedButton.label || ''}
            onChange={(e) => onPatchButton({ label: e.target.value })}
          />

          <label>Иконка</label>
          <input
            value={selectedButton.icon || ''}
            onChange={(e) => onPatchButton({ icon: e.target.value.slice(0, 2) })}
          />

          <label>Роботы (multi)</label>
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
          <button className="danger-btn" onClick={onDeleteButton}>Удалить кнопку</button>
        </>
      ) : (
        <p className="panel-hint">Выбери кнопку на поле, чтобы изменить свойства.</p>
      )}
    </div>
  )
}

export default ButtonPropertiesPanel
