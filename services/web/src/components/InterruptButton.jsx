import React from 'react'
import './InterruptButton.css'

function InterruptButton({ isProcessing, interrupting, onInterrupt, compact = false }) {
  if (!isProcessing) return null

  return (
    <button
      className={`interrupt-button ${compact ? 'compact' : ''}`}
      onClick={onInterrupt}
      disabled={interrupting}
      title="Прервать выполнение"
    >
      {interrupting ? (
        <span className="interrupt-spinner"></span>
      ) : (
        <span className="interrupt-icon" style={{ fontSize: '1.5rem', color: 'white', fontWeight: 'bold' }}>◼</span>
      )}
    </button>
  )
}

export default InterruptButton
