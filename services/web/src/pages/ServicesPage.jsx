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
  const [confirmDialog, setConfirmDialog] = useState(null) // { serviceName, dependingServices, newStatus }

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
        
        // Загружаем детали для каждого сервиса
        const details = {}
        for (const serviceName of Object.keys(result.services || {})) {
          try {
            const detailResponse = await fetch(`/api/services/${serviceName}`)
            const detailResult = await detailResponse.json()
            if (detailResult.success) {
              details[serviceName] = {
                dependencies: detailResult.dependencies || [],
                depending_services: detailResult.depending_services || []
              }
            }
          } catch (err) {
            console.error(`Error fetching details for ${serviceName}:`, err)
          }
        }
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

  const updateServiceStatus = async (serviceName, newStatus, disableDependents = false) => {
    try {
      const response = await fetch(`/api/services/${serviceName}/status`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status: newStatus, disable_dependents: disableDependents })
      })
      const result = await response.json()
      if (result.success) {
        fetchServices()
        setConfirmDialog(null)
      } else {
        // Если требуется подтверждение из-за зависимостей
        if (result.requires_confirmation && result.depending_services) {
          setConfirmDialog({
            serviceName,
            dependingServices: result.depending_services,
            newStatus
          })
        } else {
          setError(result.message || 'Ошибка обновления статуса')
          if (errorTimeoutRef.current) {
            clearTimeout(errorTimeoutRef.current)
          }
          errorTimeoutRef.current = setTimeout(() => {
            setError(null)
          }, 10000)
        }
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

  const handleStatusChange = (serviceName, newStatus) => {
    const details = serviceDetails[serviceName]
    const dependingServices = details?.depending_services || []
    
    // Если выключаем и есть зависимости - показываем диалог
    if (newStatus === 'OFF' && dependingServices.length > 0) {
      setConfirmDialog({
        serviceName,
        dependingServices,
        newStatus
      })
    } else {
      // Иначе сразу обновляем
      updateServiceStatus(serviceName, newStatus)
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

  const confirmDisableWithDependents = () => {
    if (confirmDialog) {
      updateServiceStatus(confirmDialog.serviceName, confirmDialog.newStatus, true)
    }
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
                    <SelectBox
                      value={status === 'SLEEP' ? 'OFF' : status}
                      onChange={(value) => handleStatusChange(serviceName, value)}
                      options={[
                        { value: 'ON', label: 'Включен', color: '#4caf50' },
                        { value: 'OFF', label: 'Выключен', color: '#f44336' }
                      ]}
                      className="status-select-box"
                    />
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

      {/* Диалог подтверждения выключения с зависимостями */}
      {confirmDialog && (
        <div className="modal-overlay" onClick={closeConfirmDialog}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <h3>Предупреждение о зависимостях</h3>
            <p>
              Сервис <strong>{confirmDialog.serviceName}</strong> используется следующими сервисами:
            </p>
            <ul className="depending-services-list">
              {confirmDialog.dependingServices.map(service => (
                <li key={service}>{service}</li>
              ))}
            </ul>
            <p>Выключить эти сервисы тоже?</p>
            <div className="modal-actions">
              <Button
                variant="secondary"
                onClick={closeConfirmDialog}
              >
                Отмена
              </Button>
              <Button
                variant="danger"
                onClick={confirmDisableWithDependents}
              >
                Выключить все
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default ServicesPage
