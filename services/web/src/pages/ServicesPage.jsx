import React, { useState, useEffect } from 'react'
import SelectBox from '../components/SelectBox'
import Button from '../components/Button'
import Loading from '../components/Loading'
import ErrorBanner from '../components/ErrorBanner'
import './ServicesPage.css'

function ServicesPage() {
  const [services, setServices] = useState({})
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const errorTimeoutRef = React.useRef(null)
  const [expandedService, setExpandedService] = useState(null)
  const [editingParam, setEditingParam] = useState(null)
  const [serviceDetails, setServiceDetails] = useState({}) // { serviceName: { dependencies, depending_services } }
  const [motorShutdownCount, setMotorShutdownCount] = useState(0) // Счетчик запросов на выключение моторов (0-3)

  useEffect(() => {
    fetchServices()
    const interval = setInterval(fetchServices, 10000) // Обновление каждые 10 секунд
    return () => clearInterval(interval)
  }, [])


  const fetchServices = async () => {
    try {
      const response = await fetch('/api/services')
      const result = await response.json()
      if (result.success) {
        setServices(result.services || {})
        setError(null)
        
        // Загружаем детали для всех сервисов параллельно
        const serviceNames = Object.keys(result.services || {})
        const detailResults = await Promise.all(
          serviceNames.map(serviceName =>
            fetch(`/api/services/${serviceName}`)
              .then(r => r.json())
              .catch(err => {
                console.error(`Error fetching details for ${serviceName}:`, err)
                return null
              })
          )
        )
        const details = {}
        serviceNames.forEach((serviceName, i) => {
          const detailResult = detailResults[i]
          if (detailResult && detailResult.success) {
            details[serviceName] = {
              dependencies: detailResult.dependencies || [],
              depending_services: detailResult.depending_services || []
            }
          }
        })
        setServiceDetails(details)
      } else {
        setError(result.message || 'Ошибка загрузки сервисов')
        if (errorTimeoutRef.current) {
          clearTimeout(errorTimeoutRef.current)
        }
        errorTimeoutRef.current = setTimeout(() => {
          setError(null)
        }, 10000)
      }
    } catch (err) {
      setError(`Ошибка: ${err.message}`)
      if (errorTimeoutRef.current) {
        clearTimeout(errorTimeoutRef.current)
      }
      errorTimeoutRef.current = setTimeout(() => {
        setError(null)
      }, 10000)
    } finally {
      setLoading(false)
    }
  }

  const updateServiceEnabled = async (serviceName, enabled) => {
    try {
      const response = await fetch(`/api/services/${serviceName}/enabled`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ enabled })
      })
      const result = await response.json()
      if (result.success) {
        fetchServices()
      } else {
        setError(result.message || 'Ошибка обновления enabled')
          if (errorTimeoutRef.current) {
            clearTimeout(errorTimeoutRef.current)
          }
          errorTimeoutRef.current = setTimeout(() => {
            setError(null)
          }, 10000)
      }
    } catch (err) {
      setError(`Ошибка: ${err.message}`)
      if (errorTimeoutRef.current) {
        clearTimeout(errorTimeoutRef.current)
      }
      errorTimeoutRef.current = setTimeout(() => {
        setError(null)
      }, 10000)
    }
  }

  const handleMotorShutdownRequest = async (serviceName) => {
    try {
      const response = await fetch(`/api/services/${serviceName}/shutdown_request`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' }
      })
      const result = await response.json()
      
      if (result.success) {
        if (result.requires_more_requests) {
          // Требуется больше запросов
          setMotorShutdownCount(prev => {
            const newCount = Math.min(prev + 1, 3)
            return newCount
          })
          // Обновляем список сервисов
          fetchServices()
        } else {
          // Сервис выключен, но счетчик не сбрасываем - кнопка остается видимой
          fetchServices()
        }
    } else {
        setError(result.message || 'Ошибка отправки запроса на выключение')
        if (errorTimeoutRef.current) {
          clearTimeout(errorTimeoutRef.current)
        }
        errorTimeoutRef.current = setTimeout(() => {
          setError(null)
        }, 10000)
      }
    } catch (err) {
      setError(`Ошибка: ${err.message}`)
      if (errorTimeoutRef.current) {
        clearTimeout(errorTimeoutRef.current)
      }
      errorTimeoutRef.current = setTimeout(() => {
        setError(null)
      }, 10000)
    }
  }

  const updateParameter = async (serviceName, parameter, value) => {
    try {
      const response = await fetch(`/api/services/${serviceName}/parameter`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ parameter, value })
      })
      const result = await response.json()
      if (result.success) {
        fetchServices()
        setEditingParam(null)
      } else {
        setError(result.message || 'Ошибка обновления параметра')
        if (errorTimeoutRef.current) {
          clearTimeout(errorTimeoutRef.current)
        }
        errorTimeoutRef.current = setTimeout(() => {
          setError(null)
        }, 10000)
      }
    } catch (err) {
      setError(`Ошибка: ${err.message}`)
      if (errorTimeoutRef.current) {
        clearTimeout(errorTimeoutRef.current)
      }
      errorTimeoutRef.current = setTimeout(() => {
        setError(null)
      }, 10000)
    }
  }

  const resetParameter = async (serviceName, parameter) => {
    try {
      const response = await fetch(`/api/services/${serviceName}/parameter/${parameter}`, {
        method: 'DELETE'
      })
      const result = await response.json()
      if (result.success) {
        fetchServices()
      } else {
        setError(result.message || 'Ошибка сброса параметра')
        if (errorTimeoutRef.current) {
          clearTimeout(errorTimeoutRef.current)
        }
        errorTimeoutRef.current = setTimeout(() => {
          setError(null)
        }, 10000)
      }
    } catch (err) {
      setError(`Ошибка: ${err.message}`)
      if (errorTimeoutRef.current) {
        clearTimeout(errorTimeoutRef.current)
      }
      errorTimeoutRef.current = setTimeout(() => {
        setError(null)
      }, 10000)
    }
  }

  const getStatusColor = (status) => {
    switch (status) {
      case 'ON': return '#4caf50'
      case 'OFF': return '#f44336'
      case 'SLEEP': return '#ff9800'
      default: return '#757575'
    }
  }

  const getStatusLabel = (status) => {
    switch (status) {
      case 'ON': return 'Включен'
      case 'OFF': return 'Выключен'
      case 'SLEEP': return 'Спящий'
      default: return status
    }
  }

  const closeConfirmDialog = () => {
    setConfirmDialog(null)
  }

  if (loading) {
    return (
      <div className="services-page">
        <Loading text="Загрузка сервисов..." />
      </div>
    )
  }

  const servicesList = Object.entries(services)

  return (
    <div className="services-page">
      {error && (
        <ErrorBanner
          error={error}
          onDismiss={() => {
            if (errorTimeoutRef.current) {
              clearTimeout(errorTimeoutRef.current)
            }
            setError(null)
          }}
          variant="error"
        />
      )}

      <div className="services-header">
        <h1>Управление сервисами</h1>
      </div>

      <div className="services-list">
        {servicesList.length === 0 ? (
          <div className="empty-state">
            <p>Сервисы не найдены</p>
          </div>
        ) : (
          servicesList.map(([serviceName, serviceData]) => {
            const status = serviceData.status || 'OFF'
            const parameters = serviceData.parameters || {}
            const defaults = serviceData.defaults || {}
            const isExpanded = expandedService === serviceName

            return (
              <div key={serviceName} className={`service-card ${isExpanded ? 'expanded' : ''}`}>
                <div className="service-header">
                  <div className="service-info">
                    <div className="service-name-with-status">
                      <span 
                        className="status-indicator" 
                        style={{ backgroundColor: getStatusColor(status) }}
                        title={getStatusLabel(status)}
                      ></span>
                      <h3 className="service-name">{serviceName}</h3>
                    </div>
                  </div>
                  <div className="service-actions">
                    <div className="service-status-display">
                      <span className="status-label">Статус:</span>
                      <span 
                        className="status-badge" 
                        style={{ backgroundColor: getStatusColor(status) }}
                        title={getStatusLabel(status)}
                      >
                        {getStatusLabel(status)}
                      </span>
                    </div>
                    <div className="service-enabled-control">
                      <span className="enabled-label">Запуск:</span>
                    <SelectBox
                        value={parameters.enabled !== false ? 'enabled' : 'disabled'}
                        onChange={(value) => updateServiceEnabled(serviceName, value === 'enabled')}
                      options={[
                          { value: 'enabled', label: 'Включен', color: '#4caf50' },
                          { value: 'disabled', label: 'Выключен', color: '#f44336' }
                      ]}
                        className="enabled-select-box"
                      />
                    </div>
                    {serviceName === 'unitree_motor_control' && (
                      <div className="motor-shutdown-control">
                        <button
                          className="motor-shutdown-btn"
                          onClick={() => handleMotorShutdownRequest(serviceName)}
                          disabled={status === 'OFF'}
                          title={`Выключение моторов (требуется 3 запроса). Статус: ${status}`}
                        >
                          Выключить моторы
                        </button>
                      </div>
                    )}
                    <button
                      className="expand-btn"
                      onClick={() => setExpandedService(isExpanded ? null : serviceName)}
                      aria-label={isExpanded ? 'Свернуть' : 'Развернуть'}
                    >
                      <span className={`expand-arrow ${isExpanded ? 'expanded' : ''}`}>
                        {isExpanded ? '▲' : '▼'}
                      </span>
                    </button>
                  </div>
                </div>

                <div className={`service-parameters ${isExpanded ? 'expanded' : ''}`}>
                    {/* Зависимости */}
                    {(() => {
                      const details = serviceDetails[serviceName] || {}
                      const dependencies = details.dependencies || []
                      const dependingServices = details.depending_services || []
                      
                      return (
                        <>
                          {dependencies.length > 0 && (
                            <div className="dependencies-section">
                              <h4>Зависит от:</h4>
                              <div className="dependencies-list">
                                {dependencies.map(dep => (
                                  <span key={dep} className="dependency-badge">
                                    {dep}
                                  </span>
                                ))}
                              </div>
                            </div>
                          )}
                          {dependingServices.length > 0 && (
                            <div className="dependencies-section">
                              <h4>От этого зависят:</h4>
                              <div className="dependencies-list">
                                {dependingServices.map(dep => (
                                  <span key={dep} className="dependency-badge warning">
                                    {dep}
                                  </span>
                                ))}
                              </div>
                            </div>
                          )}
                        </>
                      )
                    })()}
                    
                    <h4>Параметры:</h4>
                    {(() => {
                      // Фильтруем параметры, исключая dependencies и status
                      const filteredParams = Object.entries({ ...defaults, ...parameters }).filter(
                        ([paramName]) => paramName !== 'dependencies' && paramName !== 'status'
                      )
                      
                      if (filteredParams.length === 0) {
                        return <p className="no-parameters">Параметры отсутствуют</p>
                      }
                      
                      return (
                        <div className="parameters-list">
                          {filteredParams.map(([paramName, paramValue]) => {
                            const isDefault = defaults[paramName] === paramValue
                            const isEditing = editingParam === `${serviceName}.${paramName}`

                          return (
                            <div key={paramName} className="parameter-item">
                              <div className="parameter-name">{paramName}:</div>
                              {isEditing ? (
                                <div className="parameter-edit">
                                  <input
                                    type="text"
                                    defaultValue={paramValue}
                                    onKeyDown={(e) => {
                                      if (e.key === 'Enter') {
                                        updateParameter(serviceName, paramName, e.target.value)
                                      } else if (e.key === 'Escape') {
                                        setEditingParam(null)
                                      }
                                    }}
                                    autoFocus
                                  />
                                  <button
                                    className="save-btn"
                                    onClick={(e) => {
                                      const input = e.target.previousSibling
                                      updateParameter(serviceName, paramName, input.value)
                                    }}
                                  >
                                    ✓
                                  </button>
                                  <button
                                    className="cancel-btn"
                                    onClick={() => setEditingParam(null)}
                                  >
                                    ✕
                                  </button>
                                </div>
                              ) : (
                                <div className="parameter-value">
                                  <span className={isDefault ? 'default-value' : 'custom-value'}>
                                    {String(paramValue)}
                                  </span>
                                  {!isDefault && (
                                    <button
                                      className="reset-btn"
                                      onClick={() => resetParameter(serviceName, paramName)}
                                      title="Сбросить к default"
                                    >
                                      ↺
                                    </button>
                                  )}
                                  <button
                                    className="edit-btn"
                                    onClick={() => setEditingParam(`${serviceName}.${paramName}`)}
                                  >
                                    ✎
                                  </button>
                                </div>
                              )}
                            </div>
                          )
                        })}
                        </div>
                      )
                    })()}
                </div>
              </div>
            )
          })
        )}
      </div>

    </div>
  )
}

export default ServicesPage
