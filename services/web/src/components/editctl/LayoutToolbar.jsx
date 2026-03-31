import React from 'react'

function LayoutToolbar({
  layouts,
  activeIndex,
  onSelectIndex,
  activeLayoutName,
  onActiveLayoutNameChange,
  onAddLayout,
  onSave,
  placingButton,
  hasSelectedButton,
  onTogglePlaceButton,
  onDeleteSelectedButton,
}) {
  return (
    <div className="editctl-toolbar">
      <div className="layout-tabs" role="tablist" aria-label="Раскладки">
        {(layouts || []).map((l, idx) => (
          <button
            key={l.id || idx}
            type="button"
            role="tab"
            aria-selected={idx === activeIndex}
            className={`layout-tab ${idx === activeIndex ? 'active' : ''}`}
            onClick={() => onSelectIndex(idx)}
            title={l.name || `Раскладка ${idx + 1}`}
          >
            {(l.name || `Раскладка ${idx + 1}`).slice(0, 24)}
          </button>
        ))}
      </div>

      <button type="button" className="layout-plus" onClick={onAddLayout} title="Добавить раскладку">
        +
      </button>

      <input
        className="layout-name-input"
        value={activeLayoutName || ''}
        onChange={(e) => onActiveLayoutNameChange(e.target.value)}
        title="Имя текущей раскладки"
      />

      <button className="save-btn" type="button" onClick={onSave}>
        Сохранить
      </button>

      <button
        type="button"
        className={`node-editor__btn ${placingButton ? 'node-editor__btn--accent' : ''}`}
        onClick={onTogglePlaceButton}
        title={placingButton ? 'Отмена добавления кнопки' : 'Создать кнопку: потом клик по экрану телефона'}
      >
        {placingButton ? 'Отмена' : 'Создать кнопку'}
      </button>

      <button
        type="button"
        className="node-editor__btn node-editor__btn--danger"
        onClick={onDeleteSelectedButton}
        disabled={!hasSelectedButton}
        title="Удалить выбранную кнопку"
      >
        Удалить кнопку
      </button>
    </div>
  )
}

export default LayoutToolbar
