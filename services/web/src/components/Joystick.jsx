import React, { useRef, useEffect, useState, useCallback } from 'react'
import './Joystick.css'

let activeJoystickId = null
let joystickCounter = 0

function Joystick({ size = 200, onChange, label = '' }) {
  const containerRef = useRef(null)
  const [position, setPosition] = useState({ x: 0, y: 0 })
  const [isDragging, setIsDragging] = useState(false)
  const joystickIdRef = useRef(joystickCounter++)
  const baseRectRef = useRef(null)

  const radius = size / 2
  const stickRadius = size * 0.15
  const maxDistance = radius - stickRadius

  useEffect(() => {
    if (containerRef.current) {
      const rect = containerRef.current.getBoundingClientRect()
      baseRectRef.current = {
        left: rect.left,
        top: rect.top,
        width: rect.width,
        height: rect.height,
        centerX: rect.left + rect.width / 2,
        centerY: rect.top + rect.height / 2
      }
    }
  }, [])

  const updatePosition = useCallback((x, y) => {
    const clampedX = Math.max(-1, Math.min(1, x))
    const clampedY = Math.max(-1, Math.min(1, y))
    setPosition({ x: clampedX, y: clampedY })
    if (onChange) {
      onChange(clampedX, clampedY)
    }
  }, [onChange])

  const getPositionFromEvent = useCallback((clientX, clientY) => {
    if (!baseRectRef.current) return { x: 0, y: 0 }

    const centerX = baseRectRef.current.centerX
    const centerY = baseRectRef.current.centerY

    const deltaX = clientX - centerX
    const deltaY = clientY - centerY
    const distance = Math.sqrt(deltaX * deltaX + deltaY * deltaY)

    if (distance === 0) return { x: 0, y: 0 }

    let x = deltaX / maxDistance
    let y = deltaY / maxDistance

    if (distance > maxDistance) {
      const angle = Math.atan2(deltaY, deltaX)
      x = Math.cos(angle)
      y = Math.sin(angle)
    }

    return { x, y }
  }, [maxDistance])

  const handleStart = useCallback((e) => {
    e.preventDefault()
    e.stopPropagation()

    if (activeJoystickId !== null && activeJoystickId !== joystickIdRef.current) {
      return
    }

    if (!containerRef.current || !baseRectRef.current) {
      const rect = containerRef.current.getBoundingClientRect()
      baseRectRef.current = {
        left: rect.left,
        top: rect.top,
        width: rect.width,
        height: rect.height,
        centerX: rect.left + rect.width / 2,
        centerY: rect.top + rect.height / 2
      }
    }

    activeJoystickId = joystickIdRef.current
    setIsDragging(true)

    const clientX = e.touches ? e.touches[0].clientX : e.clientX
    const clientY = e.touches ? e.touches[0].clientY : e.clientY
    const pos = getPositionFromEvent(clientX, clientY)
    updatePosition(pos.x, pos.y)
  }, [getPositionFromEvent, updatePosition])

  const handleMove = useCallback((e) => {
    if (activeJoystickId !== joystickIdRef.current) return

    e.preventDefault()
    e.stopPropagation()

    if (!baseRectRef.current) return

    const clientX = e.touches ? e.touches[0].clientX : e.clientX
    const clientY = e.touches ? e.touches[0].clientY : e.clientY
    const pos = getPositionFromEvent(clientX, clientY)
    updatePosition(pos.x, pos.y)
  }, [getPositionFromEvent, updatePosition])

  const handleEnd = useCallback(() => {
    if (activeJoystickId !== joystickIdRef.current) return

    activeJoystickId = null
    setIsDragging(false)
  }, [])

  useEffect(() => {
    if (!isDragging) return

    const moveHandler = (e) => {
      if (activeJoystickId === joystickIdRef.current) {
        handleMove(e)
      }
    }

    const endHandler = () => {
      if (activeJoystickId === joystickIdRef.current) {
        handleEnd()
      }
    }

    window.addEventListener('mousemove', moveHandler, { passive: false })
    window.addEventListener('mouseup', endHandler, { passive: false })
    window.addEventListener('touchmove', moveHandler, { passive: false })
    window.addEventListener('touchend', endHandler, { passive: false })

    return () => {
      window.removeEventListener('mousemove', moveHandler)
      window.removeEventListener('mouseup', endHandler)
      window.removeEventListener('touchmove', moveHandler)
      window.removeEventListener('touchend', endHandler)
    }
  }, [isDragging, handleMove, handleEnd])

  const stickX = position.x * maxDistance
  const stickY = position.y * maxDistance

  return (
    <div className="joystick-container">
      {label && <div className="joystick-label">{label}</div>}
      <div
        ref={containerRef}
        className="joystick-base"
        style={{ 
          width: size, 
          height: size,
          position: 'relative',
          pointerEvents: activeJoystickId !== null && activeJoystickId !== joystickIdRef.current ? 'none' : 'auto',
          opacity: activeJoystickId !== null && activeJoystickId !== joystickIdRef.current ? 0.5 : 1
        }}
        onMouseDown={handleStart}
        onTouchStart={handleStart}
      >
        <div
          className="joystick-stick"
          style={{
            width: stickRadius * 2,
            height: stickRadius * 2,
            position: 'absolute',
            left: '50%',
            top: '50%',
            transform: `translate(calc(-50% + ${stickX}px), calc(-50% + ${stickY}px))`,
            transition: isDragging ? 'none' : 'transform 0.1s ease-out'
          }}
        />
        <div className="joystick-center-dot" />
      </div>
      <div className="joystick-values">
        <span>X: {position.x.toFixed(2)}</span>
        <span>Y: {position.y.toFixed(2)}</span>
      </div>
    </div>
  )
}

export default Joystick
