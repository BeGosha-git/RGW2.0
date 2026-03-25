import React, { useMemo } from 'react'
import CustomSelect from '../CustomSelect'

function AddPanel({ commands, selectedCommandId, onSelectCommand, selectedTargetIps, targetIps, onToggleTargetIp }) {
  const options = useMemo(
    () => commands.map((c) => ({ value: c.id, label: c.name || c.id })),
    [commands],
  )

  return (
    <div className="left-panel">
      <h3>Добавление</h3>
      <label>Команда (первая в сценарии)</label>
      {commands.length > 0 ? (
        <CustomSelect
          value={selectedCommandId || commands[0]?.id}
          options={options}
          onChange={onSelectCommand}
          placeholder="Выбери команду"
        />
      ) : (
        <p className="panel-hint">Нет команд</p>
      )}

      <label>Роботы для новой кнопки</label>
      <div className="targets-checklist">
        {targetIps.map((ip) => (
          <label key={ip} className="target-item">
            <input type="checkbox" checked={selectedTargetIps.includes(ip)} onChange={() => onToggleTargetIp(ip)} />
            <span>{ip}</span>
          </label>
        ))}
      </div>
      <p className="panel-hint">Тап по полю добавляет кнопку с одним шагом. Сценарий правь справа.</p>
    </div>
  )
}

export default AddPanel
