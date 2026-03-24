import React from 'react'

function LayoutToolbar({
  layoutName,
  onLayoutNameChange,
  onPrevLayout,
  onNextLayout,
  onAddLayout,
  onDeleteLayout,
  onSave,
}) {
  return (
    <div className="editctl-toolbar">
      <button onClick={onPrevLayout}>Предыдущая</button>
      <input value={layoutName} onChange={(e) => onLayoutNameChange(e.target.value)} />
      <button onClick={onNextLayout}>Следующая</button>
      <button onClick={onAddLayout}>+ Раскладка</button>
      <button onClick={onDeleteLayout}>Удалить</button>
      <button className="save-btn" onClick={onSave}>Сохранить</button>
    </div>
  )
}

export default LayoutToolbar
