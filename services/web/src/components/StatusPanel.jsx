import React from 'react'
import './StatusPanel.css'

function StatusPanel({ status, interrupting, onInterrupt, compact = false }) {
  const statusText = status?.isProcessing 
    ? (status?.currentCommand || 'Неизвестная команда')
    : 'Готов к работе'

  const isProcessing = status?.isProcessing || false

  return (
    <div className={`status-panel ${compact ? 'compact' : ''} ${isProcessing ? 'processing' : ''}`}>
      {isProcessing && (
        <div className="status-spinner"></div>
      )}
      <span className="status-text">{statusText}</span>
      {isProcessing && onInterrupt && (
        <button
          className="interrupt-btn"
          onClick={onInterrupt}
          disabled={interrupting}
          title="Прервать выполнение"
        >
          {interrupting ? <span style={{ fontSize: '1.2rem', color: 'white' }}>◐</span> : <span style={{ fontSize: '1.2rem', color: 'white', fontWeight: 'bold' }}>◼</span>}
        </button>
      )}
    </div>
  )
}

export default StatusPanel
