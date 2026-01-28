import React, { useState } from 'react'
import { useInterval } from '../hooks/useInterval'
import { statusApi } from '../utils/api'
import Loading from '../components/Loading'
import ErrorBanner from '../components/ErrorBanner'
import Card from '../components/Card'
import LogsViewer from '../components/LogsViewer'
import { ICONS } from '../constants/icons'
import './HomePage.css'

function HomePage() {
  const [status, setStatus] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const fetchStatus = async () => {
    try {
      setLoading(true)
      setError(null)
      const data = await statusApi.get()
      setStatus(data)
    } catch (err) {
      setError(err.message || 'Ошибка загрузки статуса')
      console.error('Error fetching status:', err)
    } finally {
      setLoading(false)
    }
  }

  // Первоначальная загрузка
  React.useEffect(() => {
    fetchStatus()
  }, [])

  // Автообновление каждые 5 секунд
  useInterval(fetchStatus, 5000)

  if (loading && !status) {
    return (
      <div className="page-container">
        <Loading text="Загрузка статуса..." />
      </div>
    )
  }

  if (error && !status) {
    return (
      <div className="page-container">
        <ErrorBanner 
          error={error} 
          onRetry={fetchStatus}
          variant="error"
        />
      </div>
    )
  }

  const { robot = {}, system = {}, version = {}, network = {} } = status || {}

  return (
    <div className="page-container">

      {error && status && (
        <ErrorBanner 
          error={error} 
          onDismiss={() => setError(null)}
          onRetry={fetchStatus}
          variant="warning"
        />
      )}

      <div className="status-grid">
        {/* Robot Info */}
        <Card 
          title="Информация о роботе"
          icon={ICONS.ROBOTS}
          variant="primary"
        >
          <div className="card-badge-container">
            <span className="status-badge online">Онлайн</span>
          </div>
          <div className="info-row">
            <span className="info-label">ID робота:</span>
            <span className="info-value">{robot.robot_id || 'N/A'}</span>
          </div>
          <div className="info-row">
            <span className="info-label">Тип:</span>
            <span className="info-value">{robot.robot_type || 'N/A'}</span>
          </div>
          <div className="info-row">
            <span className="info-label">Группа:</span>
            <span className="info-value highlight">{robot.robot_group || 'N/A'}</span>
          </div>
          <div className="info-row">
            <span className="info-label">Приоритет версии:</span>
            <span className="info-value">{robot.version_priority || 'N/A'}</span>
          </div>
        </Card>

        {/* System Info */}
        <Card 
          title="Системная информация"
          icon={ICONS.TERMINAL}
        >
          <div className="info-row">
            <span className="info-label">Платформа:</span>
            <span className="info-value">{system.platform || 'N/A'}</span>
          </div>
          <div className="info-row">
            <span className="info-label">Версия ОС:</span>
            <span className="info-value">{system.platform_release || 'N/A'}</span>
          </div>
          <div className="info-row">
            <span className="info-label">Архитектура:</span>
            <span className="info-value">{system.architecture || 'N/A'}</span>
          </div>
          <div className="info-row">
            <span className="info-label">Процессор:</span>
            <span className="info-value">{system.processor || 'N/A'}</span>
          </div>
          <div className="info-row">
            <span className="info-label">Python:</span>
            <span className="info-value">{system.python_version || 'N/A'}</span>
          </div>
          <div className="info-row">
            <span className="info-label">Хостнейм:</span>
            <span className="info-value">{system.hostname || 'N/A'}</span>
          </div>
        </Card>

        {/* Network Info */}
        <Card 
          title="Сетевая информация"
          icon={ICONS.STATUS}
          variant="info"
        >
          <div className="info-row">
            <span className="info-label">IP адрес:</span>
            <span className="info-value highlight">{network.local_ip || network.interface_ip || 'N/A'}</span>
          </div>
          <div className="info-row">
            <span className="info-label">Хостнейм:</span>
            <span className="info-value">{network.hostname || 'N/A'}</span>
          </div>
        </Card>

        {/* Version Info */}
        <Card 
          title="Версия системы"
          icon={ICONS.EDITOR}
          variant="success"
        >
          <div className="info-row">
            <span className="info-label">Версия:</span>
            <span className="info-value highlight">{version.version || 'N/A'}</span>
          </div>
          <div className="info-row">
            <span className="info-label">Файлов:</span>
            <span className="info-value">{version.files_count || 0}</span>
          </div>
        </Card>

        {/* Logs Viewer */}
        <Card 
          className="status-card full-width"
          padding={false}
        >
          <LogsViewer maxLines={100} />
        </Card>
      </div>
    </div>
  )
}

export default HomePage
