/**
 * Утилиты для работы с API
 */

const API_BASE = ''

/**
 * Выполняет API запрос
 */
export const apiRequest = async (endpoint, options = {}) => {
  const {
    method = 'GET',
    body = null,
    headers = {},
    ...restOptions
  } = options

  const config = {
    method,
    headers: {
      'Content-Type': 'application/json',
      ...headers
    },
    ...restOptions
  }

  if (body && method !== 'GET') {
    config.body = typeof body === 'string' ? body : JSON.stringify(body)
  }

  try {
    const response = await fetch(`${API_BASE}${endpoint}`, config)
    const data = await response.json()
    
    if (!response.ok) {
      throw new Error(data.message || `HTTP error! status: ${response.status}`)
    }
    
    return data
  } catch (error) {
    console.error(`API request failed: ${endpoint}`, error)
    throw error
  }
}

/**
 * GET запрос
 */
export const apiGet = (endpoint, options = {}) => {
  return apiRequest(endpoint, { ...options, method: 'GET' })
}

/**
 * POST запрос
 */
export const apiPost = (endpoint, body, options = {}) => {
  return apiRequest(endpoint, { ...options, method: 'POST', body })
}

/**
 * PUT запрос
 */
export const apiPut = (endpoint, body, options = {}) => {
  return apiRequest(endpoint, { ...options, method: 'PUT', body })
}

/**
 * DELETE запрос
 */
export const apiDelete = (endpoint, options = {}) => {
  return apiRequest(endpoint, { ...options, method: 'DELETE' })
}

/**
 * API функции для статуса
 */
export const statusApi = {
  get: () => apiGet('/api/status')
}

/**
 * API функции для файлов
 */
export const filesApi = {
  list: (dirpath = '.') => apiGet(`/api/files/list?dirpath=${encodeURIComponent(dirpath)}`),
  read: (filepath) => apiGet(`/api/files/read?filepath=${encodeURIComponent(filepath)}`),
  write: (filepath, content) => apiPost('/api/files/write', { filepath, content }),
  create: (filepath, content = '') => apiPost('/api/files/create', { filepath, content }),
  delete: (filepath) => apiPost('/api/files/delete', { filepath }),
  rename: (old_path, new_path) => apiPost('/api/files/rename', { old_path, new_path }),
  info: (filepath) => apiGet(`/api/files/info?filepath=${encodeURIComponent(filepath)}`)
}

/**
 * API функции для директорий
 */
export const directoryApi = {
  create: (dirpath) => apiPost('/api/directory/create', { dirpath }),
  delete: (dirpath) => apiPost('/api/directory/delete', { dirpath })
}

/**
 * API функции для сети
 */
export const networkApi = {
  findRobots: () => apiGet('/api/network/find_robots'),
  scannedIps: () => apiGet('/api/network/scanned_ips'),
  send: (target_ip, endpoint, data = {}) => apiPost('/api/network/send', { target_ip, endpoint, data })
}

/**
 * API функции для робота
 */
export const robotApi = {
  execute: (command, args = []) => apiPost('/api/robot/execute', { command, args }),
  getCommands: () => apiGet('/api/robot/commands'),
  updateCommands: (data) => apiPut('/api/robot/commands', data),
  updateRobotGroup: (target_ip, robot_group) => apiPost('/api/robot/update_group', { target_ip, robot_group })
}

/**
 * API функции для настроек
 */
export const settingsApi = {
  get: () => apiGet('/api/settings'),
  update: (settings) => apiPost('/api/settings', settings)
}

/**
 * API функции для управления моторами Unitree
 */
export const unitreeMotorApi = {
  setAngle: (motorIndex, angle, velocity = 0, interpolation = 0) => 
    apiPost('/api/unitree_motor/set_angle', { motor_index: motorIndex, angle, velocity, interpolation }),
  setAngles: (angles, velocity = 0, interpolation = 0) => {
    const roundedAngles = {}
    for (const [key, value] of Object.entries(angles)) {
      roundedAngles[key] = parseFloat(value.toFixed(4))
    }
    return apiPost('/api/unitree_motor/set_angles', { angles: roundedAngles, velocity, interpolation })
  },
  getAngles: () => apiGet('/api/unitree_motor/get_angles'),
  setFromNeuralNetwork: (data) => 
    apiPost('/api/unitree_motor/neural_network', data)
}
