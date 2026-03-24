import React from 'react'

function WorkspaceCanvas({
  buttons,
  selectedButtonId,
  draggingId,
  onWorkspaceClick,
  onPointerMove,
  onPointerUp,
  onSelectButton,
  onStartDrag,
}) {
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
    >
      <div className="workspace-frame">
        {(buttons || []).map((button) => (
          <button
            key={button.id}
            className={`workspace-button ${selectedButtonId === button.id ? 'selected' : ''}`}
            style={{
              left: `${(button.x || 0.5) * 100}%`,
              top: `${(button.y || 0.5) * 100}%`,
              width: `${button.size || 64}px`,
              height: `${button.size || 64}px`,
            }}
            onPointerDown={(event) => {
              event.stopPropagation()
              event.currentTarget.setPointerCapture?.(event.pointerId)
              onStartDrag(button.id)
            }}
            onClick={(event) => {
              event.stopPropagation()
              onSelectButton(button.id)
            }}
            title={draggingId === button.id ? 'Перемещение...' : 'Зажми и двигай'}
          >
            <span>{button.icon || '●'}</span>
            <small>{button.label || button.commandId}</small>
            <small className="target">{(button.targetIps || [button.targetIp || 'LOCAL']).join(', ')}</small>
          </button>
        ))}
      </div>
    </div>
  )
}

export default WorkspaceCanvas
