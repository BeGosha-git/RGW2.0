import { useState, useEffect, useCallback } from 'react'

/**
 * Хук для работы с API запросами
 * @param {Function} apiFunction - Функция для выполнения API запроса
 * @param {Array} dependencies - Зависимости для повторного выполнения
 * @param {Object} options - Опции (autoFetch, interval)
 */
export const useApi = (apiFunction, dependencies = [], options = {}) => {
  const { autoFetch = true, interval = null } = options
  
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(autoFetch)
  const [error, setError] = useState(null)

  const fetchData = useCallback(async () => {
    try {
      setLoading(true)
      setError(null)
      const result = await apiFunction()
      setData(result)
      return result
    } catch (err) {
      const errorMessage = err.message || 'Ошибка выполнения запроса'
      setError(errorMessage)
      throw err
    } finally {
      setLoading(false)
    }
  }, [apiFunction])

  useEffect(() => {
    if (autoFetch) {
      fetchData()
    }
  }, [autoFetch, fetchData, ...dependencies])

  useEffect(() => {
    if (interval && autoFetch) {
      const intervalId = setInterval(() => {
        fetchData()
      }, interval)
      return () => clearInterval(intervalId)
    }
  }, [interval, autoFetch, fetchData])

  return { data, loading, error, refetch: fetchData }
}
