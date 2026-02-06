import React, { useState, useEffect, useCallback, useRef } from 'react'
import Joystick from '../components/Joystick'
import './MotorControlPage.css'

const unitreeMotorApi = {
  setAngles: async (angles, velocity = 0, interpolation = 0) => {
    const roundedAngles = {}
    for (const [key, value] of Object.entries(angles)) {
      roundedAngles[key] = parseFloat(value.toFixed(4))
    }
    const response = await fetch('/api/unitree_motor/set_angles', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ angles: roundedAngles, velocity, interpolation })
    })
    return response.json()
  },
  getAngles: async () => {
    const response = await fetch('/api/unitree_motor/get_angles')
    return response.json()
  }
}

// Индексы моторов для H1
const MOTOR_INDICES = {
  // Ноги - правая
  RIGHT_HIP_ROLL: 0,
  RIGHT_HIP_PITCH: 1,
  RIGHT_KNEE: 2,
  RIGHT_HIP_YAW: 8,
  RIGHT_ANKLE: 11,
  // Ноги - левая
  LEFT_HIP_ROLL: 3,
  LEFT_HIP_PITCH: 4,
  LEFT_KNEE: 5,
  LEFT_HIP_YAW: 7,
  LEFT_ANKLE: 10,
  // Талия
  WAIST_YAW: 6,
  // Правое плечо
  RIGHT_SHOULDER_PITCH: 12,
  RIGHT_SHOULDER_ROLL: 13,
  RIGHT_SHOULDER_YAW: 14,
  RIGHT_ELBOW: 15,
  // Левое плечо
  LEFT_SHOULDER_PITCH: 16,
  LEFT_SHOULDER_ROLL: 17,
  LEFT_SHOULDER_YAW: 18,
  LEFT_ELBOW: 19,
}

const MOTOR_RANGES = {
  [MOTOR_INDICES.RIGHT_HIP_YAW]: { min: -0.33, max: 0.33 },
  [MOTOR_INDICES.RIGHT_HIP_ROLL]: { min: -0.33, max: 0.33 },
  [MOTOR_INDICES.RIGHT_HIP_PITCH]: { min: -3.04, max: 2.43 },
  [MOTOR_INDICES.RIGHT_KNEE]: { min: -0.16, max: 1.95 },
  [MOTOR_INDICES.RIGHT_ANKLE]: { min: -0.77, max: 0.42 },
  [MOTOR_INDICES.LEFT_HIP_YAW]: { min: -0.33, max: 0.33 },
  [MOTOR_INDICES.LEFT_HIP_ROLL]: { min: -0.33, max: 0.33 },
  [MOTOR_INDICES.LEFT_HIP_PITCH]: { min: -3.04, max: 2.43 },
  [MOTOR_INDICES.LEFT_KNEE]: { min: -0.16, max: 1.95 },
  [MOTOR_INDICES.LEFT_ANKLE]: { min: -0.77, max: 0.42 },
  [MOTOR_INDICES.WAIST_YAW]: { min: -2.25, max: 2.25 },
  [MOTOR_INDICES.RIGHT_SHOULDER_PITCH]: { min: -2.77, max: 2.77 },
  [MOTOR_INDICES.RIGHT_SHOULDER_ROLL]: { min: -3.01, max: 0.24 },
  [MOTOR_INDICES.RIGHT_SHOULDER_YAW]: { min: -4.35, max: 1.2 },
  [MOTOR_INDICES.RIGHT_ELBOW]: { min: -1.15, max: 2.51 },
  [MOTOR_INDICES.LEFT_SHOULDER_PITCH]: { min: -2.77, max: 2.77 },
  [MOTOR_INDICES.LEFT_SHOULDER_ROLL]: { min: -0.24, max: 3.01 },
  [MOTOR_INDICES.LEFT_SHOULDER_YAW]: { min: -1.2, max: 4.35 },
  [MOTOR_INDICES.LEFT_ELBOW]: { min: -1.15, max: 2.51 },
}

// Начальные углы (нейтральная позиция)
const INITIAL_ANGLES = {
  // Ноги - правая
  [MOTOR_INDICES.RIGHT_HIP_ROLL]: 0,
  [MOTOR_INDICES.RIGHT_HIP_PITCH]: 0,
  [MOTOR_INDICES.RIGHT_KNEE]: 0,
  [MOTOR_INDICES.RIGHT_HIP_YAW]: 0,
  [MOTOR_INDICES.RIGHT_ANKLE]: 0,
  // Ноги - левая
  [MOTOR_INDICES.LEFT_HIP_ROLL]: 0,
  [MOTOR_INDICES.LEFT_HIP_PITCH]: 0,
  [MOTOR_INDICES.LEFT_KNEE]: 0,
  [MOTOR_INDICES.LEFT_HIP_YAW]: 0,
  [MOTOR_INDICES.LEFT_ANKLE]: 0,
  // Талия
  [MOTOR_INDICES.WAIST_YAW]: 0,
  [MOTOR_INDICES.RIGHT_SHOULDER_PITCH]: 0,
  [MOTOR_INDICES.RIGHT_SHOULDER_ROLL]: 0,
  [MOTOR_INDICES.RIGHT_SHOULDER_YAW]: 0,
  [MOTOR_INDICES.RIGHT_ELBOW]: 0,
  [MOTOR_INDICES.LEFT_SHOULDER_PITCH]: 0,
  [MOTOR_INDICES.LEFT_SHOULDER_ROLL]: 0,
  [MOTOR_INDICES.LEFT_SHOULDER_YAW]: 0,
  [MOTOR_INDICES.LEFT_ELBOW]: 0,
}

function MotorControlPage() {
  const [angles, setAngles] = useState(INITIAL_ANGLES)
  const [velocity, setVelocity] = useState(1.0)
  const velocityRef = useRef(1.0)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [success, setSuccess] = useState(null)
  const [currentAngles, setCurrentAngles] = useState(null)
  const sendTimeoutRef = useRef(null)
  const [motorShutdownCount, setMotorShutdownCount] = useState(0)
  const [motorServiceStatus, setMotorServiceStatus] = useState(null)

  useEffect(() => {
    velocityRef.current = velocity
  }, [velocity])

  useEffect(() => {
    loadCurrentAngles()
    loadMotorServiceStatus()
    const interval = setInterval(loadCurrentAngles, 2000)
    const statusInterval = setInterval(loadMotorServiceStatus, 2000)
    return () => {
      clearInterval(interval)
      clearInterval(statusInterval)
    }
  }, [])


  const loadCurrentAngles = async () => {
    try {
      const result = await unitreeMotorApi.getAngles()
      if (result.success && result.current_angles) {
        setCurrentAngles(result.current_angles)
      }
    } catch (err) {
      console.error('Error loading current angles:', err)
    }
  }

  const loadMotorServiceStatus = async () => {
    try {
      const response = await fetch('/api/services/unitree_motor_control')
      const result = await response.json()
      if (result.success && result.service) {
        setMotorServiceStatus(result.service.status || null)
      }
    } catch (err) {
      console.error('Error loading motor service status:', err)
    }
  }

  const handleMotorShutdownRequest = async () => {
    try {
      const response = await fetch('/api/services/unitree_motor_control/shutdown_request', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' }
      })
      const result = await response.json()
      
      if (result.success) {
        if (result.requires_more_requests) {
          setMotorShutdownCount(prev => Math.min(prev + 1, 3))
        }
        // Счетчик не сбрасываем даже после выключения - кнопка остается видимой
        setTimeout(() => loadMotorServiceStatus(), 500)
      } else {
        setError(result.message || 'Ошибка отправки запроса на выключение')
        setTimeout(() => setError(null), 10000)
      }
    } catch (err) {
      setError(`Ошибка: ${err.message}`)
      setTimeout(() => setError(null), 10000)
    }
  }

  const joystickToAngle = (joystickValue, motorIndex) => {
    const range = MOTOR_RANGES[motorIndex]
    if (!range) return 0
    
    const normalized = (joystickValue + 1) / 2
    const angle = range.min + normalized * (range.max - range.min)
    return Math.max(range.min, Math.min(range.max, angle))
  }

  const sendAngles = async (anglesToSend) => {
    try {
      setLoading(true)
      setError(null)
      
      const roundedAngles = {}
      for (const [key, value] of Object.entries(anglesToSend)) {
        roundedAngles[key] = parseFloat(value.toFixed(4))
      }
      
      const result = await unitreeMotorApi.setAngles(roundedAngles, velocityRef.current, velocityRef.current)
      
      if (result.success) {
        setSuccess('Углы успешно установлены')
        setTimeout(() => setSuccess(null), 2000)
      } else {
        setError(result.message || 'Ошибка установки углов')
      }
    } catch (err) {
      setError(err.message || 'Ошибка отправки команд')
      console.error('Error sending angles:', err)
    } finally {
      setLoading(false)
    }
  }

  // Функция для отправки углов с debounce
  const sendAnglesDebounced = useCallback((newAngles) => {
    if (sendTimeoutRef.current) {
      clearTimeout(sendTimeoutRef.current)
    }
    sendTimeoutRef.current = setTimeout(() => {
      sendAngles(newAngles)
    }, 100) // Задержка 100мс для уменьшения количества запросов
  }, [])

  // Обработчик изменения джойстика правого плеча
  const handleRightShoulderChange = useCallback((x, y) => {
    setAngles(prevAngles => {
      const newAngles = {
        ...prevAngles,
        [MOTOR_INDICES.RIGHT_SHOULDER_PITCH]: joystickToAngle(y, MOTOR_INDICES.RIGHT_SHOULDER_PITCH),
        [MOTOR_INDICES.RIGHT_SHOULDER_ROLL]: joystickToAngle(x, MOTOR_INDICES.RIGHT_SHOULDER_ROLL),
      }
      sendAnglesDebounced(newAngles)
      return newAngles
    })
  }, [sendAnglesDebounced])

  // Обработчик изменения джойстика левого плеча
  const handleLeftShoulderChange = useCallback((x, y) => {
    setAngles(prevAngles => {
      const newAngles = {
        ...prevAngles,
        [MOTOR_INDICES.LEFT_SHOULDER_PITCH]: joystickToAngle(y, MOTOR_INDICES.LEFT_SHOULDER_PITCH),
        [MOTOR_INDICES.LEFT_SHOULDER_ROLL]: joystickToAngle(x, MOTOR_INDICES.LEFT_SHOULDER_ROLL),
      }
      sendAnglesDebounced(newAngles)
      return newAngles
    })
  }, [sendAnglesDebounced])

  // Обработчик изменения Yaw для правого плеча
  const handleRightYawChange = useCallback((x, y) => {
    setAngles(prevAngles => {
      const newAngles = {
        ...prevAngles,
        [MOTOR_INDICES.RIGHT_SHOULDER_YAW]: joystickToAngle(x, MOTOR_INDICES.RIGHT_SHOULDER_YAW),
      }
      sendAnglesDebounced(newAngles)
      return newAngles
    })
  }, [sendAnglesDebounced])

  // Обработчик изменения Yaw для левого плеча
  const handleLeftYawChange = useCallback((x, y) => {
    setAngles(prevAngles => {
      const newAngles = {
        ...prevAngles,
        [MOTOR_INDICES.LEFT_SHOULDER_YAW]: joystickToAngle(x, MOTOR_INDICES.LEFT_SHOULDER_YAW),
      }
      sendAnglesDebounced(newAngles)
      return newAngles
    })
  }, [sendAnglesDebounced])

  // Обработчик изменения локтя
  const handleElbowChange = useCallback((motorIndex, x, y) => {
    setAngles(prevAngles => {
      const newAngles = {
        ...prevAngles,
        [motorIndex]: joystickToAngle(y, motorIndex),
      }
      sendAnglesDebounced(newAngles)
      return newAngles
    })
  }, [sendAnglesDebounced])

  // Обработчик изменения правой ноги (Hip Pitch/Roll)
  const handleRightLegChange = useCallback((x, y) => {
    setAngles(prevAngles => {
      const newAngles = {
        ...prevAngles,
        [MOTOR_INDICES.RIGHT_HIP_PITCH]: joystickToAngle(y, MOTOR_INDICES.RIGHT_HIP_PITCH),
        [MOTOR_INDICES.RIGHT_HIP_ROLL]: joystickToAngle(x, MOTOR_INDICES.RIGHT_HIP_ROLL),
      }
      sendAnglesDebounced(newAngles)
      return newAngles
    })
  }, [sendAnglesDebounced])

  // Обработчик изменения левой ноги (Hip Pitch/Roll)
  const handleLeftLegChange = useCallback((x, y) => {
    setAngles(prevAngles => {
      const newAngles = {
        ...prevAngles,
        [MOTOR_INDICES.LEFT_HIP_PITCH]: joystickToAngle(y, MOTOR_INDICES.LEFT_HIP_PITCH),
        [MOTOR_INDICES.LEFT_HIP_ROLL]: joystickToAngle(x, MOTOR_INDICES.LEFT_HIP_ROLL),
      }
      sendAnglesDebounced(newAngles)
      return newAngles
    })
  }, [sendAnglesDebounced])

  // Обработчик изменения колена
  const handleKneeChange = useCallback((motorIndex, x, y) => {
    setAngles(prevAngles => {
      const newAngles = {
        ...prevAngles,
        [motorIndex]: joystickToAngle(y, motorIndex),
      }
      sendAnglesDebounced(newAngles)
      return newAngles
    })
  }, [sendAnglesDebounced])

  // Обработчик изменения талии
  const handleWaistChange = useCallback((x, y) => {
    setAngles(prevAngles => {
      const newAngles = {
        ...prevAngles,
        [MOTOR_INDICES.WAIST_YAW]: joystickToAngle(x, MOTOR_INDICES.WAIST_YAW),
      }
      sendAnglesDebounced(newAngles)
      return newAngles
    })
  }, [sendAnglesDebounced])


  // Очистка таймера при размонтировании
  useEffect(() => {
    return () => {
      if (sendTimeoutRef.current) {
        clearTimeout(sendTimeoutRef.current)
      }
    }
  }, [])

  const handleReset = () => {
    setAngles(INITIAL_ANGLES)
    if (sendTimeoutRef.current) {
      clearTimeout(sendTimeoutRef.current)
    }
    sendAngles(INITIAL_ANGLES)
  }

  const formatAngle = (angle) => {
    if (angle === null || angle === undefined) return 'N/A'
    const degrees = (angle * 180 / Math.PI).toFixed(1)
    return `${degrees}°`
  }

  return (
    <div className="motor-control-page">
      <div className="page-header">
        <h1 className="page-title">Управление моторами</h1>
        <div className="page-controls">
          <label className="velocity-control">
            <span>Скорость:</span>
            <input
              type="number"
              min="1"
              max="1000.0"
              step="1"
              value={velocity}
              onChange={(e) => {
                const val = parseFloat(e.target.value) || 0.1
                const clamped = Math.max(0.1, Math.min(100.0, val))
                setVelocity(clamped)
              }}
            />
            <span>рад/с</span>
          </label>
          <button className="reset-button" onClick={handleReset}>
            Сброс
          </button>
          <button 
            className="motor-shutdown-button" 
            onClick={handleMotorShutdownRequest}
            disabled={motorServiceStatus === 'OFF'}
            title={`Выключение процесса сервиса (требуется 3 запроса). Статус: ${motorServiceStatus || 'неизвестен'}`}
          >
            Выключить процесс
          </button>
        </div>
      </div>

      <div className="pd-info-banner">
        <div className="pd-info-item">
          <span className="pd-label">Слабые моторы (руки, лодыжки):</span>
          <span className="pd-value">Kp: 60.0, Kd: 1.5</span>
        </div>
        <div className="pd-info-item">
          <span className="pd-label">Сильные моторы (ноги, талия):</span>
          <span className="pd-value">Kp: 200.0, Kd: 5.0</span>
        </div>
      </div>

      {error && (
        <div className="notification-banner error-banner">
          <span>⚠️ {error}</span>
          <button onClick={() => setError(null)}>✕</button>
        </div>
      )}

      {success && (
        <div className="notification-banner success-banner">
          <span>✓ {success}</span>
        </div>
      )}

      <div className="motor-control-layout">
        {/* Правая нога */}
        <div className="arm-control-section">
          <h2 className="section-title">Правая нога</h2>
          
          <div className="joysticks-grid">
            <div className="joystick-group">
              <Joystick
                size={200}
                label="Hip Pitch / Roll"
                onChange={handleRightLegChange}
              />
              <div className="motor-info">
                <div className="motor-info-item">
                  <span>Hip Pitch:</span>
                  <span>{formatAngle(angles[MOTOR_INDICES.RIGHT_HIP_PITCH])}</span>
                </div>
                <div className="motor-info-item">
                  <span>Hip Roll:</span>
                  <span>{formatAngle(angles[MOTOR_INDICES.RIGHT_HIP_ROLL])}</span>
                </div>
              </div>
            </div>

            <div className="joystick-group">
              <Joystick
                size={150}
                label="Knee"
                onChange={(x, y) => handleKneeChange(MOTOR_INDICES.RIGHT_KNEE, x, y)}
              />
              <div className="motor-info">
                <div className="motor-info-item">
                  <span>Knee:</span>
                  <span>{formatAngle(angles[MOTOR_INDICES.RIGHT_KNEE])}</span>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Левая нога */}
        <div className="arm-control-section">
          <h2 className="section-title">Левая нога</h2>
          
          <div className="joysticks-grid">
            <div className="joystick-group">
              <Joystick
                size={200}
                label="Hip Pitch / Roll"
                onChange={handleLeftLegChange}
              />
              <div className="motor-info">
                <div className="motor-info-item">
                  <span>Hip Pitch:</span>
                  <span>{formatAngle(angles[MOTOR_INDICES.LEFT_HIP_PITCH])}</span>
                </div>
                <div className="motor-info-item">
                  <span>Hip Roll:</span>
                  <span>{formatAngle(angles[MOTOR_INDICES.LEFT_HIP_ROLL])}</span>
                </div>
              </div>
            </div>

            <div className="joystick-group">
              <Joystick
                size={150}
                label="Knee"
                onChange={(x, y) => handleKneeChange(MOTOR_INDICES.LEFT_KNEE, x, y)}
              />
              <div className="motor-info">
                <div className="motor-info-item">
                  <span>Knee:</span>
                  <span>{formatAngle(angles[MOTOR_INDICES.LEFT_KNEE])}</span>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Правое плечо */}
        <div className="arm-control-section">
          <h2 className="section-title">Правое плечо</h2>
          
          <div className="joysticks-grid">
            <div className="joystick-group">
              <Joystick
                size={200}
                label="Pitch / Roll"
                onChange={handleRightShoulderChange}
              />
              <div className="motor-info">
                <div className="motor-info-item">
                  <span>Pitch:</span>
                  <span>{formatAngle(angles[MOTOR_INDICES.RIGHT_SHOULDER_PITCH])}</span>
                </div>
                <div className="motor-info-item">
                  <span>Roll:</span>
                  <span>{formatAngle(angles[MOTOR_INDICES.RIGHT_SHOULDER_ROLL])}</span>
                </div>
              </div>
            </div>

            <div className="joystick-group">
              <Joystick
                size={150}
                label="Yaw"
                onChange={handleRightYawChange}
              />
              <div className="motor-info">
                <div className="motor-info-item">
                  <span>Yaw:</span>
                  <span>{formatAngle(angles[MOTOR_INDICES.RIGHT_SHOULDER_YAW])}</span>
                </div>
              </div>
            </div>

            <div className="joystick-group">
              <Joystick
                size={150}
                label="Elbow"
                onChange={(x, y) => handleElbowChange(MOTOR_INDICES.RIGHT_ELBOW, x, y)}
              />
              <div className="motor-info">
                <div className="motor-info-item">
                  <span>Elbow:</span>
                  <span>{formatAngle(angles[MOTOR_INDICES.RIGHT_ELBOW])}</span>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Левое плечо */}
        <div className="arm-control-section">
          <h2 className="section-title">Левое плечо</h2>
          
          <div className="joysticks-grid">
            <div className="joystick-group">
              <Joystick
                size={200}
                label="Pitch / Roll"
                onChange={handleLeftShoulderChange}
              />
              <div className="motor-info">
                <div className="motor-info-item">
                  <span>Pitch:</span>
                  <span>{formatAngle(angles[MOTOR_INDICES.LEFT_SHOULDER_PITCH])}</span>
                </div>
                <div className="motor-info-item">
                  <span>Roll:</span>
                  <span>{formatAngle(angles[MOTOR_INDICES.LEFT_SHOULDER_ROLL])}</span>
                </div>
              </div>
            </div>

            <div className="joystick-group">
              <Joystick
                size={150}
                label="Yaw"
                onChange={handleLeftYawChange}
              />
              <div className="motor-info">
                <div className="motor-info-item">
                  <span>Yaw:</span>
                  <span>{formatAngle(angles[MOTOR_INDICES.LEFT_SHOULDER_YAW])}</span>
                </div>
              </div>
            </div>

            <div className="joystick-group">
              <Joystick
                size={150}
                label="Elbow"
                onChange={(x, y) => handleElbowChange(MOTOR_INDICES.LEFT_ELBOW, x, y)}
              />
              <div className="motor-info">
                <div className="motor-info-item">
                  <span>Elbow:</span>
                  <span>{formatAngle(angles[MOTOR_INDICES.LEFT_ELBOW])}</span>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Талия */}
        <div className="arm-control-section">
          <h2 className="section-title">Талия</h2>
          
          <div className="joysticks-grid">
            <div className="joystick-group">
              <Joystick
                size={150}
                label="Yaw"
                onChange={handleWaistChange}
              />
              <div className="motor-info">
                <div className="motor-info-item">
                  <span>Waist Yaw:</span>
                  <span>{formatAngle(angles[MOTOR_INDICES.WAIST_YAW])}</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      {currentAngles && (
        <div className="current-angles-panel">
          <h3 className="panel-title">Текущие углы</h3>
          <div className="angles-grid">
            {Object.entries(MOTOR_INDICES).map(([name, index]) => (
              <div key={name} className="angle-item">
                <span className="angle-label">{name.replace(/_/g, ' ')}:</span>
                <span className="angle-value">{formatAngle(currentAngles[index])}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

export default MotorControlPage
