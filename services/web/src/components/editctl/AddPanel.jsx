import React from 'react'

function AddPanel({ commands, selectedCommandId, onSelectCommand, selectedTargetIps, targetIps, onToggleTargetIp }) {
  return (
    <div className="left-panel">
      <h3>Добавление</h3>
      <label>Команда</label>
      <div className="commands-list">
        {commands.map((command) => (
          <button
            key={command.id}
            className={selectedCommandId === command.id ? 'active' : ''}
            onClick={() => onSelectCommand(command.id)}
          >
            {command.name}
          </button>
        ))}
      </div>

      <label>Роботы для новой кнопки</label>
      <div className="targets-checklist">
        {targetIps.map((ip) => (
          <label key={ip} className="target-item">
            <input
              type="checkbox"
              checked={selectedTargetIps.includes(ip)}
              onChange={() => onToggleTargetIp(ip)}
            />
            <span>{ip}</span>
          </label>
        ))}
      </div>
      <p className="panel-hint">Тап по полю добавляет кнопку выбранной команды.</p>
    </div>
  )
}

export default AddPanel
