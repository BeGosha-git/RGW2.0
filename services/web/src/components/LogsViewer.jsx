import React, { useState, useEffect, useRef } from 'react'
import './LogsViewer.css'

function LogsViewer({ maxLines = 100 }) {
  const [logs, setLogs] = useState([])
  const [autoScroll, setAutoScroll] = useState(true)
  const logsEndRef = useRef(null)
  const logsContentRef = useRef(null)

  useEffect(() => {
    // Симуляция логов - в реальности можно получать через WebSocket или API
    const addLog = (level, message) => {
      const timestamp = new Date().toLocaleTimeString('ru-RU')
      setLogs(prev => {
        const newLogs = [...prev, { timestamp, level, message }]
        return newLogs.slice(-maxLines)
      })
    }

    // Имитация системных логов
    const interval = setInterval(() => {
      const logTypes = [
        { level: 'info', messages: ['Система работает нормально', 'Проверка соединения', 'Обновление статуса', 'Сканирование сети'] },
        { level: 'warning', messages: ['Высокая загрузка CPU', 'Медленное соединение'] },
        { level: 'error', messages: ['Таймаут запроса', 'Робот недоступен'] },
      ]
      
      const type = logTypes[Math.floor(Math.random() * logTypes.length)]
      const message = type.messages[Math.floor(Math.random() * type.messages.length)]
      addLog(type.level, message)
    }, 3000)

    // Начальные логи
    addLog('info', 'Система инициализирована')
    addLog('info', 'Веб-сервер запущен на порту 80')
    addLog('info', 'API интегрирован в веб-сервер')

    return () => clearInterval(interval)
  }, [maxLines])

  useEffect(() => {
    if (autoScroll && logsContentRef.current) {
      // Прокручиваем только контейнер логов, а не всю страницу
      logsContentRef.current.scrollTop = logsContentRef.current.scrollHeight
    }
  }, [logs, autoScroll])

  const getLevelClass = (level) => {
    switch (level) {
      case 'error':
        return 'log-error'
      case 'warning':
        return 'log-warning'
      case 'info':
        return 'log-info'
      default:
        return 'log-default'
    }
  }

  const clearLogs = () => {
    setLogs([])
  }

  return (
    <div className="logs-viewer">
      <div className="logs-header">
        <h3 className="logs-title">Системные логи</h3>
        <div className="logs-controls">
          <label className="logs-control">
            <input
              type="checkbox"
              checked={autoScroll}
              onChange={(e) => setAutoScroll(e.target.checked)}
            />
            <span>Автопрокрутка</span>
          </label>
          <button className="btn btn-secondary" onClick={clearLogs}>
            Очистить
          </button>
        </div>
      </div>
      <div className="logs-content" ref={logsContentRef}>
        {logs.length === 0 ? (
          <div className="logs-empty">Логи отсутствуют</div>
        ) : (
          logs.map((log, index) => (
            <div key={index} className={`log-entry ${getLevelClass(log.level)}`}>
              <span className="log-timestamp">[{log.timestamp}]</span>
              <span className="log-level">{log.level.toUpperCase()}</span>
              <span className="log-message">{log.message}</span>
            </div>
          ))
        )}
      </div>
    </div>
  )
}

export default LogsViewer
