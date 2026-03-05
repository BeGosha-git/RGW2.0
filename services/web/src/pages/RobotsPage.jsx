import React, { useState, useEffect, useRef, useCallback, useMemo } from 'react'
import StatusPanel from '../components/StatusPanel'
import SelectBox from '../components/SelectBox'
import './RobotsPage.css'

const COMMAND_COLORS = {
  red: '#f44336',
  blue: '#2196f3',
  green: '#4caf50',
  white: '#ffffff',
  black: '#000000'
}

const ROBOTS_PER_PAGE = 12 // Количество роботов на странице

function RobotsPage() {
  const [robots, setRobots] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const errorTimeoutRef = useRef(null)
  const [currentRobotIP, setCurrentRobotIP] = useState(null)
  const [robotCommands, setRobotCommands] = useState({}) // { robotId: group }
  const [groupLeaders, setGroupLeaders] = useState({}) // { group: leaderRobotId }
  const [manuallySetCommands, setManuallySetCommands] = useState(new Set()) // ID роботов, для которых команда была установлена вручную
  const [selectedGroup, setSelectedGroup] = useState('all')
  const [viewMode, setViewMode] = useState('groups') // 'groups', 'view', 'commands'
  const [selectedControlRobot, setSelectedControlRobot] = useState(null)
  const [selectedRobots, setSelectedRobots] = useState(new Set()) // Множественный выбор роботов
  const [colorFilter, setColorFilter] = useState(null) // Фильтр по цвету команды
  const [executingCommands, setExecutingCommands] = useState(new Set())
  const [robotStatuses, setRobotStatuses] = useState({}) // { robotId: status }
  const [availableCommands, setAvailableCommands] = useState([]) // Команды из commands.json
  const [containerSize, setContainerSize] = useState({ width: 0, height: 0 })
  const [connectionPaths, setConnectionPaths] = useState([])
  const [connectionUpdate, setConnectionUpdate] = useState(0)
  const [windowSize, setWindowSize] = useState({ width: 0, height: 0 })
  const [currentPage, setCurrentPage] = useState(1) // Пагинация
  const [localCameras, setLocalCameras] = useState([]) // Локальные камеры
  const containerRef = useRef(null)
  const cardRefs = useRef({})
  const abortControllerRef = useRef(null)
  const isFetchingRef = useRef(false)
  const manuallySetCommandsRef = useRef(new Set()) // Ref для актуального состояния ручных команд

  // Базовые размеры
  const BASE_WIDTH = 1080
  const BASE_HEIGHT = 1920
  const BASE_ROBOT_COUNT = 10
  const BASE_CLIENT_WIDTH = 287 * 1.5 // Увеличено на 50%

  // Получаем текущий IP робота
  useEffect(() => {
    const fetchCurrentIP = async () => {
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
    fetchCurrentIP()
  }, [])

  // Отслеживаем размер окна
  useEffect(() => {
    const handleResize = () => {
      setWindowSize({
        width: window.innerWidth,
        height: window.innerHeight
      })
    }
    window.addEventListener('resize', handleResize)
    handleResize()
    return () => window.removeEventListener('resize', handleResize)
  }, [])

  // Функция для расчета позиций по овалу
  const calculateOvalPosition = useCallback((index, totalClients) => {
    if (containerSize.width === 0 || containerSize.height === 0) {
      return { x: '50%', y: '50%' }
    }
    
    // Параметры овала
    const widthMultiplier = selectedGroup === 'all' ? 0.3375 : 0.21375
    const a = Math.min(containerSize.width * widthMultiplier, selectedGroup === 'all' ? 663.75 : 401.375)
    const b = Math.min(containerSize.height * 0.475, 380)
    
    // Угол для каждого робота равномерно распределен по овалу
    let angle = (index * 2 * Math.PI) / totalClients
    
    // Смещение фазы для блоков на вершинах ширины
    const cosAngle = Math.cos(angle)
    const absCosAngle = Math.abs(cosAngle)
    
    if (absCosAngle > 0.7) {
      const phaseShift = cosAngle > 0 ? -0.15 : 0.15
      angle += phaseShift
    }
    
    // Координаты на овале
    const sinAngle = Math.sin(angle)
    const absSinAngle = Math.abs(sinAngle)
    
    let x = a * Math.cos(angle)
    let y = b * sinAngle
    
    // Уменьшаем расстояние для блоков около вершин
    if (absSinAngle > 0.7) {
      const verticalScale = 0.7
      y = y * verticalScale
    }
    
    // Центр контейнера
    const centerX = containerSize.width / 2
    const centerY = containerSize.height / 2
    
    // Абсолютные координаты
    const absoluteX = centerX + x
    const absoluteY = centerY + y
    
    // Используем абсолютные пиксели вместо процентов для более точного позиционирования
    return { 
      x: `${absoluteX}px`, 
      y: `${absoluteY}px` 
    }
  }, [containerSize, selectedGroup])

  // Функция для получения позиции карточки робота
  const getCardPosition = useCallback((robotId) => {
    const cardElement = cardRefs.current[robotId]
    if (!cardElement) return null
    
    const container = containerRef.current?.querySelector('.robots-container-oval')
    if (!container) return null
    
    const containerRect = container.getBoundingClientRect()
    const cardRect = cardElement.getBoundingClientRect()
    
    const x = cardRect.left - containerRect.left + cardRect.width / 2
    const y = cardRect.top - containerRect.top + cardRect.height / 2
    
    if (isNaN(x) || isNaN(y) || x < 0 || y < 0) return null
    
    return { x, y }
  }, [])

  // Функция для рисования кривой линии между двумя точками
  const getCurvePath = useCallback((x1, y1, x2, y2) => {
    const dx = x2 - x1
    const dy = y2 - y1
    const distance = Math.sqrt(dx * dx + dy * dy)
    const controlX = x1 + dx * 0.5
    const curvature = Math.min(distance * 0.2, 100)
    const controlY = y1 - curvature
    
    return `M ${x1} ${y1} Q ${controlX} ${controlY} ${x2} ${y2}`
  }, [])

  // Функция для расчета размеров блоков
  const calculateCardSize = useCallback((robotCount) => {
    if (robotCount === 0) {
      return BASE_CLIENT_WIDTH * 0.8 // Уменьшаем на 20%
    }

    const screenWidth = windowSize.width || BASE_WIDTH
    const baseSize = BASE_CLIENT_WIDTH
    const countScale = BASE_ROBOT_COUNT / Math.max(robotCount, 1)
    const widthScale = screenWidth / BASE_WIDTH
    const finalSize = baseSize * countScale * widthScale * 0.7 * 0.8 // Уменьшаем на 20%

    const minSize = 168 // 112 * 1.5 (увеличено на 50%)
    const maxSize = 336 // 224 * 1.5 (увеличено на 50%)
    
    return Math.max(minSize, Math.min(maxSize, finalSize))
  }, [windowSize])

  // Функция для расчета масштаба блоков
  const calculateScale = useCallback((robotCount) => {
    if (robotCount === 0) return 0.8 // Уменьшаем на 20%
    
    const baseScale = selectedGroup === 'all' ? 0.7 : 0.5
    const scaleMultiplier = 0.8 // Уменьшаем на 20%
    
    if (robotCount <= 4) {
      return baseScale * scaleMultiplier
    } else if (robotCount <= 8) {
      return baseScale * 0.85 * scaleMultiplier
    } else if (robotCount <= 12) {
      return baseScale * 0.7 * scaleMultiplier
    } else {
      return baseScale * 0.6 * scaleMultiplier
    }
  }, [selectedGroup])

  // Получаем список всех групп
  const availableGroups = useMemo(() => {
    const groups = new Set()
    Object.values(robotCommands).forEach(group => {
      if (group) groups.add(group)
    })
    return Array.from(groups).sort()
  }, [robotCommands])

  // Фильтруем роботов по выбранной группе
  const filteredRobots = useMemo(() => {
    if (selectedGroup === 'all') {
      return robots
    }
    return robots.filter(robot => robotCommands[robot.id] === selectedGroup)
  }, [robots, selectedGroup, robotCommands])

  // Пагинация: получаем роботов для текущей страницы
  const paginatedRobots = useMemo(() => {
    const startIndex = (currentPage - 1) * ROBOTS_PER_PAGE
    const endIndex = startIndex + ROBOTS_PER_PAGE
    return filteredRobots.slice(startIndex, endIndex)
  }, [filteredRobots, currentPage])

  // Пересчитываем позиции при изменении контейнера или роботов
  const robotPositions = useMemo(() => {
    if (!paginatedRobots.length || containerSize.width === 0 || containerSize.height === 0) {
      return {}
    }
    const positions = {}
    paginatedRobots.forEach((robot, index) => {
      positions[robot.id] = calculateOvalPosition(index, paginatedRobots.length)
    })
    return positions
  }, [paginatedRobots, containerSize, calculateOvalPosition])

  const totalPages = useMemo(() => {
    return Math.ceil(filteredRobots.length / ROBOTS_PER_PAGE)
  }, [filteredRobots])

  // Отслеживаем размер контейнера
  useEffect(() => {
    const updateContainerSize = () => {
      const container = containerRef.current?.querySelector('.robots-container-oval')
      if (container) {
        const rect = container.getBoundingClientRect()
        setContainerSize({ width: rect.width, height: rect.height })
      }
    }
    
    // Обновляем размер сразу и после небольшой задержки для корректного расчета
    updateContainerSize()
    const timeoutId1 = setTimeout(updateContainerSize, 50)
    const timeoutId2 = setTimeout(updateContainerSize, 200)
    
    window.addEventListener('resize', updateContainerSize)
    
    // Также обновляем при изменении количества роботов
    const observer = new MutationObserver(() => {
      setTimeout(updateContainerSize, 50)
    })
    
    const container = containerRef.current?.querySelector('.robots-container-oval')
    if (container) {
      observer.observe(container, { childList: true, subtree: true, attributes: true })
    }
    
    return () => {
      window.removeEventListener('resize', updateContainerSize)
      clearTimeout(timeoutId1)
      clearTimeout(timeoutId2)
      observer.disconnect()
    }
  }, [filteredRobots.length, selectedGroup, paginatedRobots.length])

  const fetchRobots = async () => {
    // Если уже выполняется запрос, пропускаем
    if (isFetchingRef.current) {
      return
    }

    // Отменяем предыдущий запрос, если он еще выполняется
    if (abortControllerRef.current) {
      abortControllerRef.current.abort()
    }

    // Создаем новый AbortController для этого запроса
    const controller = new AbortController()
    abortControllerRef.current = controller
    isFetchingRef.current = true

    try {
      setLoading(true)
      setError(null)

      // Получаем IP адреса из сканера
      const scannedResponse = await fetch('/api/network/scanned_ips', {
        signal: controller.signal
      })
      
      // Проверяем, не был ли запрос отменен
      if (controller.signal.aborted) {
        return
      }

      const scannedResult = await scannedResponse.json()
      
      // Получаем список IP адресов (включая текущий робот)
      let ipAddresses = scannedResult.success && scannedResult.ips ? scannedResult.ips : []
      
      // Добавляем текущий IP робота, если его еще нет в списке
      if (currentRobotIP && !ipAddresses.includes(currentRobotIP)) {
        ipAddresses.push(currentRobotIP)
      }

      if (ipAddresses.length === 0) {
        setRobots([])
        setLoading(false)
        isFetchingRef.current = false
        return
      }

      // Функция для выполнения запроса с таймаутом
      const fetchWithTimeout = async (url, options, timeout = 3000) => {
        // Проверяем, не был ли основной запрос отменен
        if (controller.signal.aborted) {
          throw new Error('Request aborted')
        }

        const requestController = new AbortController()
        const timeoutId = setTimeout(() => requestController.abort(), timeout)
        
        // Объединяем сигналы: отменяем если отменен основной запрос или истек таймаут
        const combinedSignal = controller.signal.aborted 
          ? controller.signal 
          : requestController.signal
        
        try {
          const response = await fetch(url, {
            ...options,
            signal: combinedSignal
          })
          clearTimeout(timeoutId)
          return response
        } catch (error) {
          clearTimeout(timeoutId)
          if (error.name === 'AbortError' || controller.signal.aborted) {
            throw new Error('Request aborted')
          }
          throw error
        }
      }

      // Для каждого IP получаем статус (одновременно измеряем время отклика как ping)
      const robotPromises = ipAddresses.map(async (ip) => {
        // Для текущего робота используем прямой запрос к /api/status, для остальных - через /api/network/send
        const isCurrentRobot = currentRobotIP && ip === currentRobotIP
        
        // Запрос статуса с измерением времени отклика
        const pingStart = Date.now()
        let statusData = null
        let pingSuccess = false
        
        try {
          if (isCurrentRobot) {
            // Для текущего робота используем прямой запрос
            const response = await fetchWithTimeout('/api/status', {
              method: 'GET'
            }, 3000)
            const data = await response.json()
            statusData = data || null
            pingSuccess = response.ok
          } else {
            // Для удаленных роботов используем /api/network/send
            const response = await fetchWithTimeout('/api/network/send', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ target_ip: ip, endpoint: '/status', data: {} })
            }, 3000)
            const data = await response.json()
            statusData = data.success && data.response ? data.response : null
            pingSuccess = data.success === true
          }
        } catch {
          // Ошибка запроса - робот недоступен
          statusData = null
          pingSuccess = false
        }
        
        const pingTime = Date.now() - pingStart

        // Извлекаем данные о роботе из статуса
        // Для текущего робота структура ответа может отличаться
        if (statusData) {
          let robotData = {}
          if (isCurrentRobot) {
            // Для текущего робота данные находятся в statusData.robot
            robotData = statusData.robot || {}
          } else {
            // Для удаленных роботов данные уже в statusData.robot
            robotData = statusData.robot || {}
          }
          
          return {
            id: ip,
            ip: ip,
            name: robotData.robot_id || `Робот ${ip}`,
            robot_id: robotData.robot_id || 'UNKNOWN',
            robot_type: robotData.robot_type || 'UNKNOWN',
            robot_group: robotData.robot_group || 'unknown',
            status: pingSuccess ? 'online' : 'offline',
            responseTime: pingTime,
            ping: pingSuccess ? pingTime : null,
            fullInfo: statusData,
            isCurrent: isCurrentRobot
          }
        } else {
          return {
            id: ip,
            ip: ip,
            name: isCurrentRobot ? `Текущий робот ${ip}` : `Робот ${ip}`,
            robot_id: 'UNKNOWN',
            robot_type: 'UNKNOWN',
            robot_group: 'unknown',
            status: pingSuccess ? 'online' : 'offline',
            responseTime: pingTime,
            ping: pingSuccess ? pingTime : null,
            fullInfo: null,
            isCurrent: isCurrentRobot
          }
        }
      })

      // Используем Promise.allSettled чтобы не останавливаться на ошибках отдельных роботов
      const results = await Promise.allSettled(robotPromises)
      const formattedRobots = results
        .filter(result => result.status === 'fulfilled')
        .map(result => result.value)
        .filter(robot => robot !== null && robot !== undefined)
      setRobots(formattedRobots)

      // Восстанавливаем команды из данных роботов
      // Если команда в статусе совпадает с командой в состоянии, убираем метку "ручная команда"
      setRobotCommands(prev => {
        const merged = { ...prev }
        const currentManuallySet = manuallySetCommandsRef.current
        const toRemoveFromManual = new Set()
        
        formattedRobots.forEach(robot => {
          if (robot.robot_group && robot.robot_group !== 'unknown') {
            const robotId = robot.id
            const robotGroup = robot.robot_group.toLowerCase()
            
            // Если команда уже есть в состоянии
            if (robotId in prev) {
              // И она совпадает с командой из статуса - убираем метку "ручная команда"
              if (prev[robotId] === robotGroup && currentManuallySet.has(robotId)) {
                toRemoveFromManual.add(robotId)
              }
              // Если команда отличается от статуса, НЕ перезаписываем (она была установлена вручную)
            } else {
              // Если команды нет в состоянии, восстанавливаем из статуса
              if (!currentManuallySet.has(robotId)) {
                merged[robotId] = robotGroup
              }
            }
          }
        })
        
        // Убираем метки "ручная команда" для роботов, чья команда теперь в статусе
        if (toRemoveFromManual.size > 0) {
          setManuallySetCommands(prev => {
            const newSet = new Set(prev)
            toRemoveFromManual.forEach(robotId => {
              newSet.delete(robotId)
            })
            manuallySetCommandsRef.current = newSet
            return newSet
          })
        }
        
        return merged
      })

      // Обновляем лидеров групп
      setGroupLeaders(prevLeaders => {
        const updated = { ...prevLeaders }
        formattedRobots.forEach(robot => {
          const group = robot.robot_group?.toLowerCase()
          if (group && group !== 'unknown' && !updated[group]) {
            updated[group] = robot.id
          }
        })
        return updated
      })

    } catch (err) {
      // Игнорируем ошибки отмены запросов
      if (err.message === 'Request aborted' || err.name === 'AbortError') {
        return
      }
      setError(err.message || 'Ошибка загрузки роботов')
      console.error('Error fetching robots:', err)
    } finally {
      setLoading(false)
      isFetchingRef.current = false
      // Очищаем ссылку на контроллер только если это был текущий запрос
      if (abortControllerRef.current === controller) {
        abortControllerRef.current = null
      }
    }
  }

  // Загружаем команды из commands.json
  const fetchCommands = async () => {
    try {
      const response = await fetch('/api/robot/commands')
      const result = await response.json()
      if (result.success) {
        // Фильтруем только команды с showButton: true
        const visibleCommands = result.commands.filter(cmd => cmd.showButton === true)
        // Сортируем по position если есть
        visibleCommands.sort((a, b) => {
          const posA = a.buttonConfig?.position || 999
          const posB = b.buttonConfig?.position || 999
          return posA - posB
        })
        setAvailableCommands(visibleCommands)
      }
    } catch (err) {
      console.error('Error fetching commands:', err)
    }
  }

  useEffect(() => {
    // Первый запрос сразу
    fetchRobots()
    fetchCommands() // Загружаем команды при монтировании
    
    // Последующие запросы каждые 20 секунд, но не блокируем UI
    const interval = setInterval(() => {
      // Выполняем асинхронно, не ждем завершения
      fetchRobots().catch(err => {
        // Игнорируем ошибки отмены
        if (err.message !== 'Request aborted' && err.name !== 'AbortError') {
          console.error('Background fetch robots error:', err)
        }
      })
    }, 20000)
    
    return () => {
      clearInterval(interval)
      // Отменяем запросы при размонтировании компонента
      if (abortControllerRef.current) {
        abortControllerRef.current.abort()
        abortControllerRef.current = null
      }
      isFetchingRef.current = false
    }
  }, [currentRobotIP])

  // Сброс на первую страницу при изменении группы
  useEffect(() => {
    setCurrentPage(1)
  }, [selectedGroup])

  // Генерируем пути для связей
  useEffect(() => {
    if (loading || !paginatedRobots || paginatedRobots.length === 0) {
      setConnectionPaths([])
      return
    }
    
    const timeoutId = setTimeout(() => {
      const paths = []
      
      paginatedRobots.forEach(robot => {
        const robotId = robot.id
        const group = robotCommands[robotId]
        if (group && groupLeaders[group] && groupLeaders[group] !== robotId) {
          const leaderId = groupLeaders[group]
          if (paginatedRobots.find(r => r.id === leaderId)) {
            const leaderPos = getCardPosition(leaderId)
            const followerPos = getCardPosition(robotId)
            
            if (leaderPos && followerPos && 
                typeof leaderPos.x === 'number' && typeof leaderPos.y === 'number' &&
                typeof followerPos.x === 'number' && typeof followerPos.y === 'number' &&
                leaderPos.x > 0 && leaderPos.y > 0 && followerPos.x > 0 && followerPos.y > 0) {
              paths.push({
                path: getCurvePath(leaderPos.x, leaderPos.y, followerPos.x, followerPos.y),
                color: COMMAND_COLORS[group],
                group,
                leaderId,
                followerId: robotId
              })
            }
          }
        }
      })
      
      setConnectionPaths(paths)
    }, 300)
    
    return () => clearTimeout(timeoutId)
  }, [robotCommands, groupLeaders, connectionUpdate, loading, paginatedRobots, getCardPosition, getCurvePath])

  // Обновляем позиции связей при изменении размера окна
  useEffect(() => {
    const handleResize = () => {
      setTimeout(() => {
        setConnectionUpdate(prev => prev + 1)
      }, 150)
    }
    
    const handleScroll = () => {
      setConnectionUpdate(prev => prev + 1)
    }
    
    window.addEventListener('resize', handleResize)
    window.addEventListener('scroll', handleScroll)
    
    const timeoutId = setTimeout(() => {
      setConnectionUpdate(prev => prev + 1)
    }, 300)
    
    return () => {
      window.removeEventListener('resize', handleResize)
      window.removeEventListener('scroll', handleScroll)
      clearTimeout(timeoutId)
    }
  }, [robots.length, selectedGroup, filteredRobots.length])

  // Загружаем список локальных камер
  useEffect(() => {
    const fetchLocalCameras = async () => {
      try {
        const response = await fetch('/api/cameras/list')
        const data = await response.json()
        if (data.success && data.cameras) {
          setLocalCameras(data.cameras)
          // Автоматически запускаем потоки для всех камер
          for (const camera of data.cameras) {
            try {
              await fetch(`/api/cameras/${camera.id}/start`, { method: 'POST' })
            } catch (e) {
              console.error(`Failed to start camera ${camera.id}:`, e)
            }
          }
        }
      } catch (e) {
        console.error('Error fetching local cameras:', e)
      }
    }
    
    if (viewMode === 'view') {
      fetchLocalCameras()
      // Обновляем список каждые 10 секунд
      const interval = setInterval(fetchLocalCameras, 10000)
      return () => clearInterval(interval)
    }
  }, [viewMode])

  const handleCommandChange = useCallback(async (robotId, command) => {
    const robot = robots.find(r => r.id === robotId)
    if (!robot) {
      console.error(`Robot with id ${robotId} not found`)
      return
    }

    console.log(`[handleCommandChange] Changing group for robot ${robotId} (${robot.ip}) to: ${command}`)

    // Сначала обновляем локальное состояние команды для ЭТОГО конкретного робота
    setRobotCommands(prev => {
      const newCommands = { ...prev }
      const currentCommand = prev[robotId]

      if (!command || command === '') {
        // Удаляем команду для этого робота
        delete newCommands[robotId]
      } else {
        // Устанавливаем команду ТОЛЬКО для этого робота
        newCommands[robotId] = command
      }

      // Обновляем лидеров групп
      setGroupLeaders(prevLeaders => {
        const updated = { ...prevLeaders }
        
        // Если у робота была предыдущая команда, убираем его из лидеров этой группы
        if (currentCommand && currentCommand !== command) {
          if (updated[currentCommand] === robotId) {
            // Ищем другого робота с этой же командой
            const otherRobot = Object.keys(newCommands).find(
              id => id !== robotId && newCommands[id] === currentCommand
            )
            if (otherRobot) {
              updated[currentCommand] = otherRobot
            } else {
              delete updated[currentCommand]
            }
          }
        }
        
        // Если устанавливаем новую команду, делаем этого робота лидером группы
        if (command && command !== '') {
          updated[command] = robotId
        } else if (currentCommand) {
          // Если удаляем команду, убираем из лидеров
          if (updated[currentCommand] === robotId) {
            const otherRobot = Object.keys(newCommands).find(
              id => id !== robotId && newCommands[id] === currentCommand
            )
            if (otherRobot) {
              updated[currentCommand] = otherRobot
            } else {
              delete updated[currentCommand]
            }
          }
        }
        
        return updated
      })

      console.log(`[handleCommandChange] Updated commands:`, newCommands)
      return newCommands
    })

    // Помечаем, что команда установлена вручную для этого робота
    setManuallySetCommands(prev => {
      const newSet = new Set(prev)
      if (command && command !== '') {
        newSet.add(robotId)
      } else {
        newSet.delete(robotId)
      }
      // Обновляем ref для актуального состояния
      manuallySetCommandsRef.current = newSet
      console.log(`[handleCommandChange] Manually set commands:`, Array.from(newSet))
      return newSet
    })

    // Отправляем команду ТОЛЬКО на конкретного робота через API
    try {
      console.log(`[handleCommandChange] Sending update to robot ${robot.ip} with group: "${command || ''}"`)
      const response = await fetch('/api/robot/update_group', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          target_ip: robot.ip, // Только IP конкретного робота
          robot_group: command || ''
        })
      })
      const result = await response.json()
      console.log(`[handleCommandChange] Response from API:`, result)
      
      if (!result.success) {
        console.error(`[handleCommandChange] Error updating robot group for ${robot.ip}:`, result.message)
        setError(`Ошибка обновления группы для ${robot.name}: ${result.message}`)
      } else {
        console.log(`[handleCommandChange] Successfully updated group for robot ${robot.ip} to "${command}"`)
        console.log(`[handleCommandChange] Updated settings:`, result.settings)
        // Показываем успешное сообщение
        if (result.settings && result.settings.RobotGroup) {
          console.log(`[handleCommandChange] Confirmed: RobotGroup in settings is now "${result.settings.RobotGroup}"`)
        }
      }
    } catch (error) {
      console.error(`[handleCommandChange] Error updating robot group for ${robot.ip}:`, error)
      setError(`Ошибка обновления группы для ${robot.name}: ${error.message}`)
    }
  }, [robots])

  const handleExecuteCommand = async (button, robotId) => {
    if (!robotId) {
      console.warn('handleExecuteCommand: No robot ID provided')
      setError('Робот не выбран')
      return
    }

    const buttonKey = button.id || `button-${robotId}-${Date.now()}`
    
    if (executingCommands.has(buttonKey)) return

    setExecutingCommands(prev => new Set(prev).add(buttonKey))

    try {
      const robot = robots.find(r => r.id === robotId)
      if (!robot) {
        console.warn(`Robot not found: ${robotId}`, { robots: robots.map(r => r.id) })
        throw new Error(`Робот с ID ${robotId} не найден`)
      }

      console.log(`Executing command "${button.command}" for robot ${robotId} (${robot.ip})`)

      // Определяем таймаут в зависимости от типа команды
      // Для команд обновления используем увеличенный таймаут (5 минут)
      const isUpdateCommand = button.id === 'update_system' || button.command === 'python3' && button.args && button.args.includes('update.py')
      const timeout = isUpdateCommand ? 60 : undefined // 5 минут для обновления
      
      const response = await fetch('/api/network/send', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          target_ip: robot.ip,
          endpoint: '/api/robot/execute',
          data: { 
            command: button.command,
            args: button.args || []
          },
          timeout: timeout
        })
      })

      if (!response.ok) {
        const errorText = await response.text()
        console.error(`HTTP error for robot ${robotId}:`, response.status, errorText)
        throw new Error(`HTTP ${response.status}: ${errorText}`)
      }

      const result = await response.json()
      console.log(`Command result for robot ${robotId}:`, result)

      // Проверяем структуру ответа
      if (result.success === true) {
        // Если ответ содержит вложенный response с результатом выполнения команды
        const commandResult = result.response || result
        const isCommandSuccessful = commandResult.success !== false && commandResult.return_code === 0
        
        setRobotStatuses(prev => ({
          ...prev,
          [robotId]: { 
            isProcessing: false, 
            currentCommand: button.name,
            lastResult: isCommandSuccessful ? 'success' : 'error'
          }
        }))
        
        if (isCommandSuccessful) {
          setError(null) // Очищаем ошибки при успехе
        } else {
          const errorMsg = commandResult.message || commandResult.stderr || 'Команда завершилась с ошибкой'
          throw new Error(errorMsg)
        }
      } else {
        throw new Error(result.message || 'Ошибка выполнения команды')
      }
    } catch (error) {
      console.error('Error executing command:', error)
      setError(error.message || 'Ошибка выполнения команды')
      // Автоматически скрываем ошибку через 10 секунд
      if (errorTimeoutRef.current) {
        clearTimeout(errorTimeoutRef.current)
      }
      errorTimeoutRef.current = setTimeout(() => {
        setError(null)
      }, 10000)
    } finally {
      setExecutingCommands(prev => {
        const newSet = new Set(prev)
        newSet.delete(buttonKey)
        return newSet
      })
    }
  }

  // Выполнение команды для нескольких роботов
  const handleExecuteCommandMultiple = async (button, robotIds) => {
    if (!robotIds || robotIds.length === 0) {
      console.warn('handleExecuteCommandMultiple: No robot IDs provided')
      return
    }

    const buttonKey = `multi-${button.id}-${Date.now()}`
    if (executingCommands.has(buttonKey)) return

    setExecutingCommands(prev => new Set(prev).add(buttonKey))

    try {
      const promises = robotIds.map(async (robotId) => {
        const robot = robots.find(r => r.id === robotId)
        if (!robot) {
          console.warn(`Robot not found: ${robotId}`, { robots: robots.map(r => r.id) })
          return { robotId, success: false, error: 'Робот не найден' }
        }

        try {
          // Определяем таймаут в зависимости от типа команды
          const isUpdateCommand = button.id === 'update_system' || button.command === 'python3' && button.args && button.args.includes('update.py')
          const timeout = isUpdateCommand ? 300 : undefined // 5 минут для обновления
          
          const response = await fetch('/api/network/send', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              target_ip: robot.ip,
              endpoint: '/api/robot/execute',
              data: { 
                command: button.command,
                args: button.args || []
              },
              timeout: timeout
            })
          })

          if (!response.ok) {
            const errorText = await response.text()
            console.error(`HTTP error for robot ${robotId} (${robot.ip}):`, response.status, errorText)
            return {
              robotId,
              success: false,
              error: `HTTP ${response.status}: ${errorText}`
            }
          }

          const result = await response.json()
          console.log(`Command result for robot ${robotId} (${robot.ip}):`, result)
          
          // Проверяем структуру ответа более надежно
          if (result.success === true) {
            // Если ответ содержит вложенный response с результатом выполнения команды
            const commandResult = result.response || result
            const isCommandSuccessful = commandResult.success !== false && commandResult.return_code === 0
            
            return {
              robotId,
              success: isCommandSuccessful,
              error: isCommandSuccessful ? null : (commandResult.message || commandResult.stderr || 'Команда завершилась с ошибкой')
            }
          } else {
            return {
              robotId,
              success: false,
              error: result.message || 'Ошибка выполнения команды'
            }
          }
        } catch (error) {
          console.error(`Error executing command for robot ${robotId} (${robot.ip}):`, error)
          return { robotId, success: false, error: error.message || 'Ошибка сети' }
        }
      })

      const results = await Promise.allSettled(promises)
      
      // Обрабатываем результаты
      const processedResults = results.map((result, index) => {
        if (result.status === 'fulfilled') {
          return result.value
        } else {
          // Если промис был отклонен (не должно происходить, но на всякий случай)
          console.error(`Promise rejected for robot ${robotIds[index]}:`, result.reason)
          return {
            robotId: robotIds[index],
            success: false,
            error: result.reason?.message || 'Неизвестная ошибка'
          }
        }
      })

      const successful = processedResults.filter(r => r.success === true).length
      const failed = processedResults.length - successful

      console.log(`Command execution summary: ${successful} successful, ${failed} failed`, processedResults)

      // Обновляем статусы для успешных роботов
      processedResults.forEach((result) => {
        if (result.success) {
          setRobotStatuses(prev => ({
            ...prev,
            [result.robotId]: { isProcessing: false, currentCommand: button.name }
          }))
        }
      })

      if (successful > 0 && failed === 0) {
        // Все успешно - показываем успешное сообщение
        setError(null)
      } else if (failed > 0) {
        // Есть ошибки
        const errorDetails = processedResults
          .filter(r => !r.success)
          .map(r => `Робот ${r.robotId}: ${r.error}`)
          .join('; ')
        setError(`Команда выполнена для ${successful} роботов, ошибок: ${failed}. ${errorDetails}`)
        // Автоматически скрываем ошибку через 10 секунд
        if (errorTimeoutRef.current) {
          clearTimeout(errorTimeoutRef.current)
        }
        errorTimeoutRef.current = setTimeout(() => {
          setError(null)
        }, 10000)
      }
    } catch (error) {
      console.error('Error executing command for multiple robots:', error)
      setError(`Критическая ошибка: ${error.message}`)
      // Автоматически скрываем ошибку через 10 секунд
      if (errorTimeoutRef.current) {
        clearTimeout(errorTimeoutRef.current)
      }
      errorTimeoutRef.current = setTimeout(() => {
        setError(null)
      }, 10000)
    } finally {
      setExecutingCommands(prev => {
        const newSet = new Set(prev)
        newSet.delete(buttonKey)
        return newSet
      })
    }
  }

  // Обработчики выбора роботов
  const handleRobotToggle = useCallback((robotId) => {
    setSelectedRobots(prev => {
      const newSet = new Set(prev)
      if (newSet.has(robotId)) {
        newSet.delete(robotId)
      } else {
        newSet.add(robotId)
      }
      return newSet
    })
    // Сбрасываем одиночный выбор при множественном
    if (selectedControlRobot === robotId) {
      setSelectedControlRobot(null)
    }
  }, [selectedControlRobot])

  const handleRobotSingleSelect = useCallback((robotId) => {
    setSelectedControlRobot(robotId)
    setSelectedRobots(new Set([robotId]))
  }, [])

  const handleSelectByColor = useCallback((color) => {
    if (color === null) {
      setColorFilter(null)
      setSelectedRobots(new Set())
      setSelectedControlRobot(null)
      return
    }
    setColorFilter(color)
    const robotsWithColor = robots.filter(robot => {
      const command = robotCommands[robot.id]
      return command === color
    })
    setSelectedRobots(new Set(robotsWithColor.map(r => r.id)))
    // Если выбран только один робот, делаем его одиночным выбором
    if (robotsWithColor.length === 1) {
      setSelectedControlRobot(robotsWithColor[0].id)
    } else {
      setSelectedControlRobot(null)
    }
  }, [robots, robotCommands])

  const handleSelectAll = useCallback(() => {
    setSelectedRobots(new Set(robots.map(r => r.id)))
  }, [robots])

  const handleDeselectAll = useCallback(() => {
    setSelectedRobots(new Set())
    setSelectedControlRobot(null)
  }, [])

  // Фильтрация роботов по цвету
  const filteredRobotsForCommands = useMemo(() => {
    if (colorFilter === null) {
      return robots
    }
    return robots.filter(robot => robotCommands[robot.id] === colorFilter)
  }, [robots, robotCommands, colorFilter])

  // Получение команд для отображения (общие при множественном выборе)
  const displayCommands = useMemo(() => {
    const selectedCount = selectedRobots.size
    if (selectedCount === 0) {
      return []
    }
    
    // При множественном выборе показываем только общие команды
    if (selectedCount > 1) {
      return availableCommands.filter(cmd => cmd.buttonConfig?.isCommon !== false)
    }
    
    // При одиночном выборе показываем все команды
    return availableCommands
  }, [selectedRobots.size, availableCommands])

  const handleInterrupt = async (robotId) => {
    try {
      const robot = robots.find(r => r.id === robotId)
      if (!robot) return

      const response = await fetch('/api/network/send', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          target_ip: robot.ip,
          endpoint: '/interrupt',
          data: {}
        })
      })

      const result = await response.json()
      if (result.success) {
        setRobotStatuses(prev => ({
          ...prev,
          [robotId]: { isProcessing: false }
        }))
      }
    } catch (error) {
      console.error('Error interrupting command:', error)
    }
  }

  if (loading && robots.length === 0) {
    return (
      <div className="robots-page">
        <div className="loading">
          <div className="spinner"></div>
        </div>
      </div>
    )
  }

  return (
    <div className="robots-page" ref={containerRef}>
      {error && (
        <div className="error-banner">
          <span><span style={{ fontSize: '1.5rem', color: 'white', marginRight: '0.5rem', fontWeight: 'bold' }}>⚠</span>{error}</span>
          <button onClick={() => {
            if (errorTimeoutRef.current) {
              clearTimeout(errorTimeoutRef.current)
            }
            setError(null)
          }}>✕</button>
        </div>
      )}

      {/* Меню выбора групп */}
      {viewMode === 'groups' && (
        <div className="groups-menu">
          <h3>Группы:</h3>
          <div className="groups-list">
            <button
              className={`group-button ${selectedGroup === 'all' ? 'active' : ''}`}
              onClick={() => setSelectedGroup('all')}
            >
              ВСЕ
              <span className="group-count">{robots.length}</span>
            </button>
            {availableGroups.map(group => {
              const groupRobots = robots.filter(r => robotCommands[r.id] === group)
              return (
                <button
                  key={group}
                  className={`group-button ${selectedGroup === group ? 'active' : ''}`}
                  onClick={() => setSelectedGroup(group)}
                  style={{
                    borderColor: selectedGroup === group ? COMMAND_COLORS[group] : 'transparent',
                    backgroundColor: selectedGroup === group ? COMMAND_COLORS[group] : 'var(--bg-tertiary)'
                  }}
                >
                  <span className="group-dot" style={{ backgroundColor: COMMAND_COLORS[group] }}></span>
                  {group.toUpperCase()}
                  <span className="group-count">{groupRobots.length}</span>
                </button>
              )
            })}
          </div>
        </div>
      )}

      {/* Меню режимов */}
      <div className="view-modes-menu">
        <h3>Режимы</h3>
        {[
          { id: 'groups', label: 'Группы' },
          { id: 'view', label: 'Просмотр' },
          { id: 'commands', label: 'Команды' }
        ].map((mode) => (
          <button
            key={mode.id}
            className={`view-mode-button ${viewMode === mode.id ? 'active' : ''}`}
            onClick={() => {
              setViewMode(mode.id)
              // Сбрасываем выбор при переключении режима
              if (mode.id !== 'commands') {
                setSelectedRobots(new Set())
                setSelectedControlRobot(null)
                setColorFilter(null)
              }
            }}
          >
            {mode.label}
          </button>
        ))}
      </div>

      {/* Режим "Группы" */}
      {viewMode === 'groups' && (
        <div className="robots-container">
          
          {/* Пагинация */}
          {totalPages > 1 && (
            <div className="pagination-controls">
              <button
                className="pagination-btn"
                onClick={() => setCurrentPage(prev => Math.max(1, prev - 1))}
                disabled={currentPage === 1}
              >
                ‹ Предыдущая
              </button>
              <span className="pagination-info">
                Страница {currentPage} из {totalPages} ({filteredRobots.length} роботов)
              </span>
              <button
                className="pagination-btn"
                onClick={() => setCurrentPage(prev => Math.min(totalPages, prev + 1))}
                disabled={currentPage === totalPages}
              >
                Следующая ›
              </button>
            </div>
          )}

          <div className="robots-container-oval">
            {paginatedRobots.map((robot, index) => {
              const isLeader = groupLeaders[robotCommands[robot.id]] === robot.id
              const selectedCommand = robotCommands[robot.id]
              const status = robotStatuses[robot.id] || { isProcessing: false }
              const position = robotPositions[robot.id] || calculateOvalPosition(index, paginatedRobots.length)
              const scale = calculateScale(paginatedRobots.length)
              const cardWidth = calculateCardSize(paginatedRobots.length)
              const isCurrentRobot = robot.isCurrent || (currentRobotIP && robot.ip === currentRobotIP)

              return (
                <div
                  key={robot.id}
                  ref={el => {
                    if (el) cardRefs.current[robot.id] = el
                  }}
                  className={`robot-card robot-card-animated ${isLeader && selectedCommand ? 'leader' : ''} ${isCurrentRobot ? 'current-robot' : ''}`}
                  style={{
                    position: 'absolute',
                    left: position.x,
                    top: position.y,
                    transform: `translate(-50%, -50%) scale(${scale})`,
                    transition: 'transform 0.5s ease',
                    transformOrigin: 'center center',
                    willChange: 'transform',
                    zIndex: isCurrentRobot ? 4 : (isLeader ? 3 : 2),
                    width: `${cardWidth}px`,
                    maxWidth: `${cardWidth}px`,
                    minWidth: `${cardWidth}px`,
                    '--card-scale': scale,
                    borderColor: isCurrentRobot 
                      ? 'var(--accent-primary)'
                      : (selectedCommand && COMMAND_COLORS[selectedCommand]
                        ? COMMAND_COLORS[selectedCommand] 
                        : 'var(--border-color)'),
                    boxShadow: isCurrentRobot
                      ? `0 0 25px var(--accent-primary)60, 0 0 10px var(--accent-primary)40, var(--shadow-lg)`
                      : (selectedCommand && COMMAND_COLORS[selectedCommand]
                        ? `0 0 20px ${COMMAND_COLORS[selectedCommand]}40, var(--shadow-lg)`
                        : 'var(--shadow-md)')
                  }}
                >
                  <div className="robot-card-header">
                    <h3 className="robot-card-name">
                      {isCurrentRobot && <span style={{ color: 'var(--accent-primary)', marginRight: '0.5rem' }}>●</span>}
                      {robot.name}
                      {isCurrentRobot && <span style={{ color: 'var(--text-secondary)', fontSize: '0.8rem', marginLeft: '0.5rem', fontWeight: 'normal' }}>(Текущий)</span>}
                    </h3>
                    <div className="robot-card-actions">
                      <button
                        className="robot-refresh-btn"
                        onClick={() => fetchRobots()}
                        title="Обновить"
                        style={{ fontSize: '1.5rem', color: 'white', fontWeight: 'bold' }}
                      >
                        ⟲
                      </button>
                    </div>
                  </div>

                  <div className="robot-card-status">
                    <span className={`status-badge ${robot.status}`}>
                      <span style={{ fontSize: '1.2rem', color: 'white', fontWeight: 'bold' }}>
                        {robot.status === 'online' ? '◉' : '○'}
                      </span> {robot.status}
                    </span>
                    {robot.responseTime > 0 && (
                      <span className="robot-ping">{robot.responseTime}мс</span>
                    )}
                  </div>

                  <div className="robot-card-info">
                    <div className="robot-info-item">
                      <span className="info-label-small">IP:</span>
                      <span className="info-value-small">{robot.ip}</span>
                    </div>
                    <div className="robot-info-item">
                      <span className="info-label-small">ID:</span>
                      <span className="info-value-small">{robot.robot_id}</span>
                    </div>
                  </div>

                  <div className="robot-card-group">
                    <label className="group-select-label">Группа:</label>
                    <SelectBox
                      value={selectedCommand || ''}
                      onChange={(value) => handleCommandChange(robot.id, value)}
                      options={[
                        { value: '', label: 'Нет группы' },
                        { value: 'red', label: 'Red', color: COMMAND_COLORS.red, icon: '●' },
                        { value: 'blue', label: 'Blue', color: COMMAND_COLORS.blue, icon: '●' },
                        { value: 'green', label: 'Green', color: COMMAND_COLORS.green, icon: '●' },
                        { value: 'white', label: 'White', color: COMMAND_COLORS.white, icon: '●' },
                        { value: 'black', label: 'Black', color: COMMAND_COLORS.black, icon: '●' }
                      ]}
                      placeholder="Выберите группу"
                      style={{
                        borderColor: selectedCommand ? COMMAND_COLORS[selectedCommand] : undefined
                      }}
                    />
                    {isLeader && selectedCommand && (
                      <span className="leader-badge" style={{ backgroundColor: COMMAND_COLORS[selectedCommand] }}>
                        Главный
                      </span>
                    )}
                  </div>

                  <StatusPanel
                    status={status}
                    onInterrupt={() => handleInterrupt(robot.id)}
                    compact={true}
                  />
                </div>
              )
            })}

            {/* SVG для рисования связей */}
            {connectionPaths.length > 0 && (
              <div className="connections-overlay">
                <svg
                  width="100%"
                  height="100%"
                  style={{ 
                    position: 'absolute', 
                    top: 0, 
                    left: 0,
                    overflow: 'visible',
                    pointerEvents: 'none'
                  }}
                  preserveAspectRatio="none"
                >
                  <defs>
                    {connectionPaths.map((conn, index) => (
                      <marker
                        key={`arrowhead-${conn.leaderId}-${conn.followerId}-${index}`}
                        id={`arrowhead-${conn.leaderId}-${conn.followerId}-${index}`}
                        markerWidth="10"
                        markerHeight="10"
                        refX="9"
                        refY="3"
                        orient="auto"
                        markerUnits="strokeWidth"
                      >
                        <polygon
                          points="0 0, 10 3, 0 6"
                          fill={conn.color}
                        />
                      </marker>
                    ))}
                    <style>
                      {`
                        @keyframes dash {
                          to {
                            stroke-dashoffset: -20;
                          }
                        }
                        .animated-arrow {
                          animation: dash 1s linear infinite;
                        }
                      `}
                    </style>
                  </defs>
                  {connectionPaths.map((conn, index) => (
                    <g key={`${conn.leaderId}-${conn.followerId}-${index}`}>
                      <path
                        d={conn.path}
                        stroke={conn.color}
                        strokeWidth="2"
                        fill="none"
                        strokeDasharray="5,5"
                        strokeDashoffset="0"
                        opacity={0.7}
                        markerEnd={`url(#arrowhead-${conn.leaderId}-${conn.followerId}-${index})`}
                        className="animated-arrow"
                        style={{
                          filter: 'drop-shadow(0 0 2px rgba(0,0,0,0.1))'
                        }}
                      />
                    </g>
                  ))}
                </svg>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Режим "Просмотр" - камеры */}
      {viewMode === 'view' && (
        <div className="robots-view-mode">
          <h2 className="robots-title">Просмотр камер</h2>
          
          {/* Локальные камеры - только usb_2 и usb_3 */}
          {localCameras.filter(c => c.id === 'usb_2' || c.id === 'usb_3').length > 0 && (
            <div className="cameras-section">
              <h3 className="cameras-section-title">Локальные камеры</h3>
              <div className="cameras-grid">
                {localCameras
                  .filter(camera => camera.id === 'usb_2' || camera.id === 'usb_3')
                  .map((camera) => {
                    const cameraStreamUrl = `/api/cameras/${camera.id}/mjpeg`
                    return (
                      <div key={camera.id} className="camera-card">
                        <h3>{camera.name}</h3>
                        <div className="camera-stream">
                          <img
                            src={cameraStreamUrl}
                            alt={`Камера ${camera.name}`}
                            onError={(e) => {
                              e.target.style.display = 'none'
                              const errorBox = e.target.nextSibling
                              if (errorBox) errorBox.style.display = 'flex'
                            }}
                          />
                          <div className="camera-error" style={{ display: 'none' }}>
                            <span>Камера недоступна</span>
                          </div>
                        </div>
                        <div className="camera-info">
                          USB • {camera.id}
                        </div>
                      </div>
                    )
                  })}
              </div>
            </div>
          )}
          
          {/* Камеры роботов - только usb_2 и usb_3 */}
          <div className="cameras-section">
            <h3 className="cameras-section-title">Камеры роботов</h3>
            <div className="cameras-grid">
              {paginatedRobots.map((robot) => {
                const robotIP = robot.ip
                // Используем актуальные стримы usb_2 и usb_3
                const cameraStreams = [
                  {
                    id: 'usb_2',
                    name: 'USB Camera 2',
                    url: robotIP && /^\d+\.\d+\.\d+\.\d+$/.test(robotIP)
                      ? `http://${robotIP}:5000/api/cameras/usb_2/mjpeg`
                      : null
                  },
                  {
                    id: 'usb_3',
                    name: 'USB Camera 3',
                    url: robotIP && /^\d+\.\d+\.\d+\.\d+$/.test(robotIP)
                      ? `http://${robotIP}:5000/api/cameras/usb_3/mjpeg`
                      : null
                  }
                ]

                return (
                  <div key={robot.id} className="camera-card">
                    <h3>{robot.name}</h3>
                    {cameraStreams.map((camera) => (
                      <div key={camera.id} style={{ marginBottom: '10px' }}>
                        <div className="camera-info" style={{ marginBottom: '5px', fontSize: '12px' }}>
                          {camera.name}
                        </div>
                        {camera.url ? (
                          <div className="camera-stream">
                            <img
                              src={camera.url}
                              alt={`${camera.name} - ${robot.name}`}
                              onError={(e) => {
                                e.target.style.display = 'none'
                                const errorBox = e.target.nextSibling
                                if (errorBox) errorBox.style.display = 'flex'
                              }}
                            />
                            <div className="camera-error" style={{ display: 'none' }}>
                              <span>Камера недоступна</span>
                            </div>
                          </div>
                        ) : (
                          <div className="camera-error">
                            <span>IP не определен</span>
                          </div>
                        )}
                      </div>
                    ))}
                    {robotIP && (
                      <div className="camera-info">{robotIP}:5000</div>
                    )}
                  </div>
                )
              })}
            </div>
          </div>
          {/* Пагинация для камер */}
          {totalPages > 1 && (
            <div className="pagination-controls">
              <button
                className="pagination-btn"
                onClick={() => setCurrentPage(prev => Math.max(1, prev - 1))}
                disabled={currentPage === 1}
              >
                ‹ Предыдущая
              </button>
              <span className="pagination-info">
                Страница {currentPage} из {totalPages}
              </span>
              <button
                className="pagination-btn"
                onClick={() => setCurrentPage(prev => Math.min(totalPages, prev + 1))}
                disabled={currentPage === totalPages}
              >
                Следующая ›
              </button>
            </div>
          )}
        </div>
      )}

      {/* Режим "Команды" */}
      {viewMode === 'commands' && (
        <div className="robots-commands-mode">
          <div className="commands-layout">
            {/* Левая панель: список роботов */}
            <div className="commands-robots-panel">
              <div className="commands-panel-header">
                <h3>Роботы</h3>
                <div className="commands-panel-actions">
                  <button
                    className="commands-action-btn"
                    onClick={handleSelectAll}
                    title="Выбрать всех"
                  >
                    Все
                  </button>
                  <button
                    className="commands-action-btn"
                    onClick={handleDeselectAll}
                    title="Снять выбор"
                  >
                    Сброс
                  </button>
                </div>
              </div>

              {/* Фильтры по цветам */}
              <div className="commands-color-filters">
                <div className="color-filters-title">Быстрый выбор по цветам:</div>
                <div className="color-filters-grid">
                  <button
                    className={`color-filter-btn ${colorFilter === null ? 'active' : ''}`}
                    onClick={() => handleSelectByColor(null)}
                    title="Все роботы"
                  >
                    Все
                  </button>
                  {Object.entries(COMMAND_COLORS).map(([color, colorValue]) => (
                    <button
                      key={color}
                      className={`color-filter-btn ${colorFilter === color ? 'active' : ''}`}
                      onClick={() => handleSelectByColor(color)}
                      style={{
                        borderColor: colorValue,
                        backgroundColor: colorFilter === color ? `${colorValue}20` : 'transparent'
                      }}
                      title={`Выбрать ${color} роботов`}
                    >
                      <span className="color-dot" style={{ backgroundColor: colorValue }}></span>
                      {color}
                    </button>
                  ))}
                </div>
              </div>

              {/* Список роботов */}
              <div className="commands-robots-list">
                {filteredRobotsForCommands.length === 0 ? (
                  <div className="empty-state-small">
                    <p>Роботы не найдены</p>
                  </div>
                ) : (
                  filteredRobotsForCommands.map(robot => {
                    const isSelected = selectedRobots.has(robot.id)
                    const isSingleSelected = selectedControlRobot === robot.id
                    const robotCommand = robotCommands[robot.id]
                    const commandColor = robotCommand ? COMMAND_COLORS[robotCommand] : null
                    const status = robotStatuses[robot.id] || { isProcessing: false }

                    return (
                      <div
                        key={robot.id}
                        className={`commands-robot-item ${isSelected ? 'selected' : ''} ${isSingleSelected ? 'single-selected' : ''}`}
                        onClick={() => handleRobotSingleSelect(robot.id)}
                      >
                        <div className="commands-robot-checkbox">
                          <input
                            type="checkbox"
                            checked={isSelected}
                            onChange={(e) => {
                              e.stopPropagation()
                              handleRobotToggle(robot.id)
                            }}
                            onClick={(e) => e.stopPropagation()}
                          />
                        </div>
                        <div className="commands-robot-info">
                          <div className="commands-robot-header">
                            <span className="commands-robot-name">{robot.name}</span>
                            {commandColor && (
                              <span
                                className="commands-robot-color"
                                style={{ backgroundColor: commandColor }}
                                title={`Группа: ${robotCommand}`}
                              ></span>
                            )}
                          </div>
                          <div className="commands-robot-details">
                            <span className="commands-robot-ip">{robot.ip}</span>
                            <span className={`commands-robot-status ${robot.status}`}>
                              {robot.status === 'online' ? '◉' : '○'} {robot.status}
                            </span>
                            {robot.ping && (
                              <span className="commands-robot-ping">{robot.ping}мс</span>
                            )}
                          </div>
                          {status.isProcessing && (
                            <div className="commands-robot-processing">
                              <span>◐</span> Выполняется: {status.currentCommand || 'команда'}
                            </div>
                          )}
                        </div>
                      </div>
                    )
                  })
                )}
              </div>

              {/* Информация о выбранных */}
              {selectedRobots.size > 0 && (
                <div className="commands-selection-info">
                  Выбрано: {selectedRobots.size} {selectedRobots.size === 1 ? 'робот' : 'роботов'}
                </div>
              )}
            </div>

            {/* Правая панель: команды */}
            <div className="commands-actions-panel">
              <div className="commands-panel-header">
                <h3>
                  {selectedRobots.size === 0
                    ? 'Выберите роботов'
                    : selectedRobots.size === 1
                    ? 'Команды для робота'
                    : `Общие команды (${selectedRobots.size} роботов)`}
                </h3>
              </div>

              {selectedRobots.size === 0 ? (
                <div className="empty-state">
                  <p>Выберите одного или нескольких роботов для выполнения команд</p>
                </div>
              ) : displayCommands.length === 0 ? (
                <div className="empty-state">
                  <p>
                    {selectedRobots.size > 1
                      ? 'Нет общих команд для множественного выбора. Выберите одного робота для доступа ко всем командам.'
                      : 'Команды не настроены. Добавьте команды в commands.json с showButton: true'}
                  </p>
                </div>
              ) : (
                <div className="commands-list">
                  {displayCommands.map((button) => {
                    const isMultiple = selectedRobots.size > 1
                    const buttonKey = isMultiple
                      ? `multi-${button.id}`
                      : `button-${Array.from(selectedRobots)[0]}-${button.name}`
                    const isExecuting = executingCommands.has(buttonKey)
                    const buttonColor = button.buttonConfig?.color || 'primary'
                    
                    return (
                      <button
                        key={button.id}
                        className={`command-execute-btn command-btn-${buttonColor}`}
                        onClick={() => {
                          const selectedArray = Array.from(selectedRobots)
                          if (selectedArray.length === 0) {
                            console.warn('No robots selected')
                            setError('Выберите хотя бы одного робота')
                            return
                          }
                          
                          if (isMultiple) {
                            console.log(`Executing command "${button.name}" for ${selectedArray.length} robots:`, selectedArray)
                            handleExecuteCommandMultiple(button, selectedArray)
                          } else {
                            const robotId = selectedArray[0]
                            console.log(`Executing command "${button.name}" for robot:`, robotId)
                            handleExecuteCommand(button, robotId)
                          }
                        }}
                        disabled={isExecuting}
                        title={button.description || button.name}
                      >
                        {isExecuting ? (
                          <>
                            <span style={{ fontSize: '1.2rem', color: 'white', marginRight: '0.5rem' }}>◐</span>
                            Выполняется...
                          </>
                        ) : (
                          <>
                            {button.buttonConfig?.icon && (
                              <span className="command-icon" style={{ marginRight: '0.5rem' }}>
                                {button.buttonConfig.icon === 'restart' && '⟲'}
                                {button.buttonConfig.icon === 'update' && '◈'}
                                {button.buttonConfig.icon === 'info' && '◉'}
                                {!['restart', 'update', 'info'].includes(button.buttonConfig.icon) && '▶'}
                              </span>
                            )}
                            {button.name}
                            {isMultiple && (
                              <span className="command-multiple-badge">
                                ({selectedRobots.size})
                              </span>
                            )}
                          </>
                        )}
                      </button>
                    )
                  })}
                </div>
              )}

              {/* Статус выбранных роботов (только для одиночного выбора) */}
              {selectedRobots.size === 1 && selectedControlRobot && (
                <div className="commands-robot-status-panel">
                  <StatusPanel
                    status={robotStatuses[selectedControlRobot] || { isProcessing: false }}
                    onInterrupt={() => handleInterrupt(selectedControlRobot)}
                  />
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default RobotsPage
