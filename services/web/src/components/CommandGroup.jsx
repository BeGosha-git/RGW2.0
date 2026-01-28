import React, { useState } from 'react'
import './CommandGroup.css'

const PAGE_SIZE = 9

function CommandGroup({ tag, commands, isProcessing, currentCommand, onExecute }) {
  const [page, setPage] = useState(0)
  const totalPages = Math.ceil(commands.length / PAGE_SIZE)

  const handlePrev = () => setPage((p) => Math.max(0, p - 1))
  const handleNext = () => setPage((p) => Math.min(totalPages - 1, p + 1))

  const pageCommands = commands.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE)

  return (
    <div className="command-group">
      <h3 className="command-group-title">{tag}</h3>
      <div className="command-grid">
        {Array.from({ length: PAGE_SIZE }).map((_, idx) => {
          const cmd = pageCommands[idx]
          return (
            <div key={cmd ? cmd.id : `empty-${idx}`} className="command-grid-item">
              {cmd && (
                <button
                  className={`command-button ${isProcessing && currentCommand === cmd.id ? 'executing' : ''}`}
                  onClick={() => !isProcessing && onExecute(cmd)}
                  disabled={isProcessing}
                >
                  <span className="command-icon" style={{ fontSize: '1.5rem', color: 'white', fontWeight: 'bold' }}>▶</span>
                  <span className="command-name">{cmd.name}</span>
                  {isProcessing && currentCommand === cmd.id && (
                    <span className="command-spinner"></span>
                  )}
                </button>
              )}
            </div>
          )
        })}
      </div>
      {totalPages > 1 && (
        <div className="command-pagination">
          <button onClick={handlePrev} disabled={page === 0}>‹</button>
          <span>{page + 1} / {totalPages}</span>
          <button onClick={handleNext} disabled={page === totalPages - 1}>›</button>
        </div>
      )}
    </div>
  )
}

export default CommandGroup
