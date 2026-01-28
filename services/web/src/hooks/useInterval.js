import { useEffect, useRef } from 'react'

/**
 * Хук для выполнения функции с интервалом
 * @param {Function} callback - Функция для выполнения
 * @param {number|null} delay - Интервал в миллисекундах (null для остановки)
 */
export const useInterval = (callback, delay) => {
  const savedCallback = useRef()

  useEffect(() => {
    savedCallback.current = callback
  }, [callback])

  useEffect(() => {
    function tick() {
      savedCallback.current()
    }
    
    if (delay !== null) {
      const id = setInterval(tick, delay)
      return () => clearInterval(id)
    }
  }, [delay])
}
