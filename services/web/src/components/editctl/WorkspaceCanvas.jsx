import React, { useMemo } from 'react'
import { normalizeProgramFromButton } from '../../utils/controlProgram'
import IconGlyph from '../IconGlyph'

const COLOR_PRESETS = [
  { id: 'blue', hex: '#2196f3' },
  { id: 'green', hex: '#4caf50' },
  { id: 'red', hex: '#f44336' },
  { id: 'white', hex: '#ffffff' },
  { id: 'black', hex: '#000000' },
  { id: 'purple', hex: '#9c27b0' },
]

function hexToRgba(hex, a) {
  const h = String(hex || '').replace('#', '')
  if (h.length !== 6) return `rgba(33,150,243,${a})`
  const r = parseInt(h.slice(0, 2), 16)
  const g = parseInt(h.slice(2, 4), 16)
  const b = parseInt(h.slice(4, 6), 16)
  return `rgba(${r},${g},${b},${a})`
}

function iconToShape(icon) {
  if (icon === '■') return 'square'
  if (icon === '▲') return 'triangle'
  return 'circle'
}

function resolveShape(button) {
  return button.shape || iconToShape(button.icon)
}

function resolveColor(button) {
  return button.color || '#2196f3'
}

function WorkspaceCanvas({
  buttons,
  selectedButtonId,
  draggingId,
  onWorkspaceClick,
  onPointerMove,
  onPointerUp,
  onSelectButton,
  onStartDrag,
  onPatchButton,
  onDeleteButton,
}) {
  const selectedButton = useMemo(
    () => (buttons || []).find((b) => b.id === selectedButtonId) || null,
    [buttons, selectedButtonId],
  )

  return (
    <div
      className="workspace-shell"
      onClick={onWorkspaceClick}
      onPointerMove={onPointerMove}
      onPointerUp={onPointerUp}
      onPointerCancel={onPointerUp}
      onMouseUp={onPointerUp}
      onMouseLeave={onPointerUp}
      onTouchMove={onPointerMove}
      onTouchEnd={onPointerUp}
      onContextMenu={(e) => e.preventDefault()}
    >
      <div className="workspace-frame">
        {selectedButton ? (
          <div
            className="btn-tooltip"
            style={{
              left: `${(selectedButton.x || 0.5) * 100}%`,
              top: `${(selectedButton.y || 0.5) * 100}%`,
              transform: 'translate(-50%, calc(-100% - 10px))',
            }}
            onPointerDown={(e) => e.stopPropagation()}
            onMouseDown={(e) => e.stopPropagation()}
            onClick={(e) => e.stopPropagation()}
          >
            <label className="btn-tooltip__row">
              <span className="btn-tooltip__lbl">Имя</span>
              <input
                className="btn-tooltip__input"
                value={selectedButton.label || ''}
                onPointerDown={(e) => e.stopPropagation()}
                onMouseDown={(e) => e.stopPropagation()}
                onChange={(e) => onPatchButton?.({ label: e.target.value })}
              />
            </label>

            <div className="btn-tooltip__row">
              <span className="btn-tooltip__lbl">Форма</span>
              <div className="shape-bar" onPointerDown={(e) => e.stopPropagation()} onMouseDown={(e) => e.stopPropagation()}>
                {[
                  { shape: 'circle', label: '○' },
                  { shape: 'square', label: '□' },
                  { shape: 'triangle', label: '△' },
                ].map((it) => {
                  const active = resolveShape(selectedButton) === it.shape
                  return (
                    <button
                      key={it.shape}
                      type="button"
                      className={`shape-chip ${active ? 'active' : ''}`}
                      onClick={() =>
                        onPatchButton?.({
                          shape: it.shape,
                        })
                      }
                      title={it.shape}
                    >
                      {it.label}
                    </button>
                  )
                })}
              </div>
            </div>

            <div className="btn-tooltip__row">
              <span className="btn-tooltip__lbl">Цвет</span>
              <div className="color-bar" onPointerDown={(e) => e.stopPropagation()} onMouseDown={(e) => e.stopPropagation()}>
                {COLOR_PRESETS.map((c) => {
                  const active = String(resolveColor(selectedButton)).toLowerCase() === c.hex
                  return (
                    <button
                      key={c.id}
                      type="button"
                      className={`color-chip ${active ? 'active' : ''}`}
                      style={{ backgroundColor: c.hex }}
                      onClick={() => onPatchButton?.({ color: c.hex })}
                      title={c.id}
                    />
                  )
                })}
                <input
                  type="color"
                  className="color-picker"
                  value={resolveColor(selectedButton)}
                  onPointerDown={(e) => e.stopPropagation()}
                  onMouseDown={(e) => e.stopPropagation()}
                  onChange={(e) => onPatchButton?.({ color: e.target.value })}
                  title="Свой цвет"
                />
              </div>
            </div>

            <div className="btn-tooltip__row">
              <span className="btn-tooltip__lbl">Размер</span>
              <input
                type="range"
                min="44"
                max="120"
                value={selectedButton.size || 64}
                onPointerDown={(e) => e.stopPropagation()}
                onMouseDown={(e) => e.stopPropagation()}
                onChange={(e) => onPatchButton?.({ size: Number(e.target.value) })}
              />
            </div>
          </div>
        ) : null}

        {(buttons || []).map((button) => {
          const prog = normalizeProgramFromButton(button)
          const hasScenario = prog.length > 1 || prog.some((b) => b.type === 'parallel')
          const shape = resolveShape(button)
          const color = resolveColor(button)
          const bg = hexToRgba(color, 0.28)
          const border = hexToRgba(color, 0.8)
          const clipPath = shape === 'triangle' ? 'polygon(50% 0%, 0% 100%, 100% 100%)' : undefined
          const borderRadius = shape === 'square' ? '12px' : '50%'
          return (
            <button
              key={button.id}
              className={`workspace-button ${selectedButtonId === button.id ? 'selected' : ''}`}
              style={{
                left: `${(button.x || 0.5) * 100}%`,
                top: `${(button.y || 0.5) * 100}%`,
                width: `${button.size || 64}px`,
                height: `${button.size || 64}px`,
                background: bg,
                borderColor: border,
                borderRadius,
                clipPath,
              }}
              onPointerDown={(event) => {
                event.stopPropagation()
                event.currentTarget.setPointerCapture?.(event.pointerId)
                onStartDrag(button.id)
              }}
              onContextMenu={(event) => {
                event.preventDefault()
                event.stopPropagation()
              }}
              onClick={(event) => {
                event.stopPropagation()
                onSelectButton(button.id)
              }}
              title={draggingId === button.id ? 'Перемещение...' : 'Зажми и двигай'}
            >
              {hasScenario && <span className="workspace-program-badge">{prog.length}</span>}
              <span className="workspace-button__shape" style={{ color: '#fff', display: 'inline-flex', alignItems: 'center', justifyContent: 'center' }}>
                <IconGlyph name={button.icon || (shape === 'square' ? '■' : shape === 'triangle' ? '▲' : '●')} size={18} />
              </span>
              <small>{button.label || button.commandId}</small>
              <small className="target">{(button.targetIps || [button.targetIp || 'LOCAL']).join(', ')}</small>
            </button>
          )
        })}
      </div>
    </div>
  )
}

export default WorkspaceCanvas
