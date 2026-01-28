import React, { useState, useEffect } from 'react'
import './RobotControlPage.css'

function RobotControlPage() {
  const [robots, setRobots] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [selectedRobot, setSelectedRobot] = useState(null)
  const [robotStatus, setRobotStatus] = useState(null)
  const [pingResults, setPingResults] = useState({})
  const [groupedRobots, setGroupedRobots] = useState({})
  const [currentRobotIP, setCurrentRobotIP] = useState(null)

  const fetchRobots = async () => {
    try {
      setLoading(true)
      setError(null)
      
      // Получаем текущий IP робота для фильтрации
      if (!currentRobotIP) {
        try {
          const statusResponse = await fetch('/api/status')
          const statusData = await statusResponse.json()
          const myIP = statusData.network?.local_ip || statusData.network?.interface_ip
          if (myIP) {
            setCurrentRobotIP(myIP)
          }
        } catch (e) {
          console.error('Error getting current robot IP:', e)
        }
      }
      
      // Получаем IP адреса из сканера
      const scannedResponse = await fetch('/api/network/scanned_ips')
      const scannedResult = await scannedResponse.json()
      if (!scannedResult.success || !scannedResult.ips || scannedResult.ips.length === 0) {
        setRobots([])
        setGroupedRobots({})
        setLoading(false)
        return
      }
      
      // Фильтруем текущий IP робота
      let ipAddresses = scannedResult.ips
      if (currentRobotIP) {
        ipAddresses = ipAddresses.filter(ip => ip !== currentRobotIP)
      }
      
      if (ipAddresses.length === 0) {
        setRobots([])
        setGroupedRobots({})
        setLoading(false)
        return
      }
      
      // Для каждого IP получаем статус и делаем пинг параллельно
      const robotPromises = ipAddresses.map(async (ip) => {
        let statusData = null
        let pingTime = null
        let pingSuccess = false
        
        try {
          // Получаем статус робота через API
          const statusResponse = await fetch('/api/network/send', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ target_ip: ip, endpoint: '/status', data: {} })
          })
          const statusResult = await statusResponse.json()
          if (statusResult.success && statusResult.response) {
            statusData = statusResult.response
          } else if (statusResult.response) {
            statusData = statusResult.response
          }
        } catch (err) {
          console.error(`Error fetching status for ${ip}:`, err)
        }
        
        // Делаем пинг
        const pingStart = Date.now()
        try {
          const pingResponse = await fetch('/api/network/send', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ target_ip: ip, endpoint: '/health', data: {} })
          })
          const pingResult = await pingResponse.json()
          pingTime = Date.now() - pingStart
          pingSuccess = pingResult.success === true
          setPingResults(prev => ({
            ...prev,
            [ip]: { success: pingSuccess, time: pingTime }
          }))
        } catch (pingErr) {
          pingTime = Date.now() - pingStart
          setPingResults(prev => ({
            ...prev,
            [ip]: { success: false, time: null }
          }))
        }
        
        // Извлекаем данные о роботе из статуса
        if (statusData) {
          const robotData = statusData.robot || {}
          const systemData = statusData.system || {}
          const networkData = statusData.network || {}
          
          return {
            ip: ip,
            robot_id: robotData.robot_id || 'UNKNOWN',
            robot_type: robotData.robot_type || 'UNKNOWN',
            robot_group: robotData.robot_group || 'unknown',
            version_priority: robotData.version_priority || 'UNKNOWN',
            version: statusData.version || {},
            system: systemData,
            network: networkData,
            fullInfo: statusData,
            ping: pingSuccess ? pingTime : null
          }
        } else {
          // Если не удалось получить статус, создаем базовую запись
          return {
            ip: ip,
            robot_id: 'UNKNOWN',
            robot_type: 'UNKNOWN',
            robot_group: 'unknown',
            version_priority: 'UNKNOWN',
            version: {},
            system: {},
            network: {},
            fullInfo: null,
            ping: pingSuccess ? pingTime : null
          }
        }
      })
      
      // Ждем получения всех статусов
      const normalizedRobots = await Promise.all(robotPromises)
      setRobots(normalizedRobots)
      
      // Группируем роботов по RobotGroup
      const grouped = {}
      normalizedRobots.forEach(robot => {
        const group = robot.robot_group || 'unknown'
        if (!grouped[group]) {
          grouped[group] = []
        }
        grouped[group].push(robot)
      })
      setGroupedRobots(grouped)
      
    } catch (err) {
      setError(err.message || 'Ошибка получения данных о роботах')
      console.error('Error fetching robots:', err)
    } finally {
      setLoading(false)
    }
  }

  const fetchRobotStatus = async (robotIp) => {
    try {
      const response = await fetch('/api/network/send', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ target_ip: robotIp, endpoint: '/status', data: {} })
      })
      const result = await response.json()
      if (result.success && result.response) {
        setRobotStatus(result.response)
      } else if (result.response) {
        // Если данные есть, но нет success флага
        setRobotStatus(result.response)
      } else {
        setRobotStatus({ error: 'Не удалось получить статус' })
      }
    } catch (err) {
      setRobotStatus({ error: err.message })
    }
  }

  const pingRobot = async (robotIp) => {
    try {
      const startTime = Date.now()
      const response = await fetch('/api/network/send', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ target_ip: robotIp, endpoint: '/health', data: {} })
      })
      const result = await response.json()
      const pingTime = Date.now() - startTime
      
      if (result.success) {
        setPingResults(prev => ({
          ...prev,
          [robotIp]: { success: true, time: pingTime }
        }))
      } else {
        setPingResults(prev => ({
          ...prev,
          [robotIp]: { success: false, time: null }
        }))
      }
    } catch (err) {
      setPingResults(prev => ({
        ...prev,
        [robotIp]: { success: false, time: null, error: err.message }
      }))
    }
  }

  const handleRobotClick = (robot) => {
    setSelectedRobot(robot)
    setRobotStatus(null)
    if (robot.ip) {
      fetchRobotStatus(robot.ip)
    }
  }

  useEffect(() => {
    // Загружаем данные о роботах
    fetchRobots()
    const interval = setInterval(() => {
      fetchRobots()
    }, 5000) // Обновление каждые 5 секунд
    return () => clearInterval(interval)
  }, [currentRobotIP])

  const getGroupColor = (group) => {
    const colors = {
      'white': '#ffffff',
      'black': '#000000',
      'red': '#ff3366',
      'blue': '#00d4ff',
      'green': '#00ff88',
      'yellow': '#ffd700',
      'unknown': '#888888',
    }
    return colors[group?.toLowerCase()] || colors.unknown
  }

  return (
    <div className="robot-control-page">
      <div className="page-header">
        <h1 className="page-title">Управление роботами</h1>
      </div>

      {error && (
        <div className="error-banner">
          <span>⚠️ {error}</span>
          <button onClick={() => setError(null)}>✕</button>
        </div>
      )}

      {loading && robots.length === 0 ? (
        <div className="loading">
          <div className="spinner"></div>
        </div>
      ) : (
        <div className="robots-layout">
          {/* Robot Groups */}
          <div className="robot-groups">
            <h2 className="section-title">Группы роботов</h2>
            {Object.keys(groupedRobots).length === 0 ? (
              <div className="empty-state">
                <p>Роботы не найдены</p>
              </div>
            ) : (
              Object.entries(groupedRobots).map(([group, groupRobots]) => (
                <div key={group} className="robot-group">
                  <div 
                    className="group-header"
                    style={{ borderLeftColor: getGroupColor(group) }}
                  >
                    <h3 className="group-name">
                      <span 
                        className="group-color-indicator"
                        style={{ backgroundColor: getGroupColor(group) }}
                      ></span>
                      {group.toUpperCase()}
                    </h3>
                    <span className="group-count">{groupRobots.length}</span>
                  </div>
                  <div className="group-robots">
                    {groupRobots.map((robot) => (
                      <RobotCard
                        key={robot.robot_id || robot.ip}
                        robot={robot}
                        isSelected={selectedRobot?.robot_id === robot.robot_id}
                        onClick={() => handleRobotClick(robot)}
                        onPing={() => pingRobot(robot.ip)}
                        pingResult={pingResults[robot.ip]}
                        groupColor={getGroupColor(group)}
                      />
                    ))}
                  </div>
                </div>
              ))
            )}
          </div>

          {/* Robot Details */}
          <div className="robot-details">
            {selectedRobot ? (
              <>
                <div className="card">
                  <div className="card-header">
                    <h2 className="card-title">
                      <span style={{ fontSize: '2.5rem', color: 'white', fontWeight: 'bold' }}>◊</span>
                      {selectedRobot.robot_id || 'Неизвестный робот'}
                    </h2>
                    <button 
                      className="close-btn" 
                      onClick={() => {
                        setSelectedRobot(null)
                        setRobotStatus(null)
                      }}
                    >
                      ✕
                    </button>
                  </div>
                  <div className="card-content">
                    <div className="info-row">
                      <span className="info-label">IP адрес:</span>
                      <span className="info-value" style={{ color: 'var(--accent-primary)' }}>{selectedRobot.ip || 'N/A'}</span>
                    </div>
                    <div className="info-row">
                      <span className="info-label">ID:</span>
                      <span className="info-value">{selectedRobot.robot_id || 'N/A'}</span>
                    </div>
                    <div className="info-row">
                      <span className="info-label">Тип:</span>
                      <span className="info-value">{selectedRobot.robot_type || 'N/A'}</span>
                    </div>
                    <div className="info-row">
                      <span className="info-label">Группа:</span>
                      <span 
                        className="info-value"
                        style={{ color: getGroupColor(selectedRobot.robot_group) }}
                      >
                        {selectedRobot.robot_group || 'N/A'}
                      </span>
                    </div>
                    <div className="info-row">
                      <span className="info-label">Приоритет версии:</span>
                      <span className="info-value">{selectedRobot.version_priority || 'N/A'}</span>
                    </div>
                  </div>
                </div>

                {robotStatus && (
                  <div className="card">
                    <div className="card-header">
                      <h2 className="card-title">
                        <span>📊</span>
                        Статус робота
                      </h2>
                      <button 
                        className="btn btn-secondary" 
                        onClick={() => selectedRobot.ip && fetchRobotStatus(selectedRobot.ip)}
                      >
                        <span style={{ fontSize: '1.5rem', color: 'white', marginRight: '0.5rem', fontWeight: 'bold' }}>⟲</span>Обновить
                      </button>
                    </div>
                    <div className="card-content">
                      {robotStatus.error ? (
                        <div className="error-message">
                          <span>⚠️ {robotStatus.error}</span>
                        </div>
                      ) : (
                        <>
                          {robotStatus.system && (
                            <>
                              <div className="info-section">
                                <h3 className="info-section-title">Система</h3>
                                <div className="info-row">
                                  <span className="info-label">Платформа:</span>
                                  <span className="info-value">{robotStatus.system.platform || 'N/A'}</span>
                                </div>
                                <div className="info-row">
                                  <span className="info-label">Версия ОС:</span>
                                  <span className="info-value">{robotStatus.system.platform_release || 'N/A'}</span>
                                </div>
                                <div className="info-row">
                                  <span className="info-label">Архитектура:</span>
                                  <span className="info-value">{robotStatus.system.architecture || 'N/A'}</span>
                                </div>
                                <div className="info-row">
                                  <span className="info-label">Python:</span>
                                  <span className="info-value">{robotStatus.system.python_version || 'N/A'}</span>
                                </div>
                              </div>
                            </>
                          )}
                          {robotStatus.network && (
                            <>
                              <div className="info-section">
                                <h3 className="info-section-title">Сеть</h3>
                                <div className="info-row">
                                  <span className="info-label">IP:</span>
                                  <span className="info-value" style={{ color: 'var(--accent-primary)' }}>
                                    {robotStatus.network.local_ip || robotStatus.network.interface_ip || 'N/A'}
                                  </span>
                                </div>
                                <div className="info-row">
                                  <span className="info-label">Хостнейм:</span>
                                  <span className="info-value">{robotStatus.network.hostname || 'N/A'}</span>
                                </div>
                              </div>
                            </>
                          )}
                          {robotStatus.version && (
                            <>
                              <div className="info-section">
                                <h3 className="info-section-title">Версия</h3>
                                <div className="info-row">
                                  <span className="info-label">Версия:</span>
                                  <span className="info-value" style={{ color: 'var(--accent-primary)' }}>{robotStatus.version.version || 'N/A'}</span>
                                </div>
                                <div className="info-row">
                                  <span className="info-label">Файлов:</span>
                                  <span className="info-value">{robotStatus.version.files_count || 0}</span>
                                </div>
                              </div>
                            </>
                          )}
                        </>
                      )}
                    </div>
                  </div>
                )}

                <div className="card">
                  <div className="card-header">
                    <h2 className="card-title">
                      <span style={{ fontSize: '1.5rem', color: 'white', fontWeight: 'bold' }}>◉</span>
                      Действия
                    </h2>
                  </div>
                  <div className="card-content">
                    <div className="action-buttons">
                      <button 
                        className="btn btn-secondary" 
                        onClick={() => selectedRobot.ip && pingRobot(selectedRobot.ip)}
                      >
                        📡 Ping
                      </button>
                      {pingResults[selectedRobot.ip] && (
                        <div className="ping-result">
                          {pingResults[selectedRobot.ip].success ? (
                            <span className="ping-success">
                              ✓ {pingResults[selectedRobot.ip].time}ms
                            </span>
                          ) : (
                            <span className="ping-fail">
                              ✗ Недоступен
                            </span>
                          )}
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              </>
            ) : (
              <div className="robot-details-placeholder">
                <div className="placeholder-content">
                  <span className="placeholder-icon" style={{ fontSize: '5rem', color: 'white', fontWeight: 'bold' }}>◊</span>
                  <h2>Выберите робота</h2>
                  <p>Выберите робота из списка для просмотра детальной информации</p>
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

function RobotCard({ robot, isSelected, onClick, onPing, pingResult, groupColor }) {
  return (
    <div 
      className={`robot-card ${isSelected ? 'selected' : ''}`}
      onClick={onClick}
      style={{ borderLeftColor: groupColor }}
    >
      <div className="robot-card-header">
      <div className="robot-card-title">
        <span className="robot-icon" style={{ fontSize: '2rem', color: 'white', fontWeight: 'bold' }}>◊</span>
        <div>
          <div className="robot-name">{robot.robot_id || 'Unknown'}</div>
          <div className="robot-ip">{robot.ip || 'N/A'}</div>
        </div>
      </div>
        <div className="robot-card-status">
          {pingResult ? (
            pingResult.success ? (
              <span className="status-indicator online" title={`Ping: ${pingResult.time}ms`} style={{ fontSize: '1.2rem', color: 'white', fontWeight: 'bold' }}>
                ◉
              </span>
            ) : (
              <span className="status-indicator offline" title="Недоступен" style={{ fontSize: '1.2rem', color: 'white', fontWeight: 'bold' }}>
                ◉
              </span>
            )
          ) : (
            <span className="status-indicator unknown" style={{ fontSize: '1.2rem', color: 'white' }}>○</span>
          )}
        </div>
      </div>
      <div className="robot-card-info">
        <div className="robot-info-item">
          <span className="info-label-small">Тип:</span>
          <span className="info-value-small">{robot.robot_type || 'N/A'}</span>
        </div>
        <div className="robot-info-item">
          <span className="info-label-small">Группа:</span>
          <span 
            className="info-value-small"
            style={{ color: groupColor }}
          >
            {robot.robot_group || 'N/A'}
          </span>
        </div>
        {pingResult && pingResult.success && (
          <div className="robot-info-item">
            <span className="info-label-small">Ping:</span>
            <span className="info-value-small" style={{ color: 'var(--accent-success)' }}>
              {pingResult.time}ms
            </span>
          </div>
        )}
      </div>
      <button 
        className="robot-ping-btn"
        onClick={(e) => {
          e.stopPropagation()
          onPing()
        }}
        title="Ping робота"
        style={{ fontSize: '1.2rem' }}
      >
        📡
      </button>
    </div>
  )
}

export default RobotControlPage
