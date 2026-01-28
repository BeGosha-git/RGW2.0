import React, { useState, useRef, useEffect } from 'react'
import { createPortal } from 'react-dom'
import './SelectBox.css'

const SelectBox = ({ 
  value, 
  onChange, 
  options = [], 
  placeholder = 'Выберите...',
  className = '',
  style = {}
}) => {
  const [isOpen, setIsOpen] = useState(false)
  const selectRef = useRef(null)
  const dropdownRef = useRef(null)
  const [dropdownPosition, setDropdownPosition] = useState({ top: 0, left: 0, width: 0 })

  useEffect(() => {
    const handleClickOutside = (event) => {
      if (selectRef.current && !selectRef.current.contains(event.target) &&
          dropdownRef.current && !dropdownRef.current.contains(event.target)) {
        setIsOpen(false)
      }
    }

    if (isOpen) {
      document.addEventListener('mousedown', handleClickOutside)
      // Вычисляем позицию dropdown
      if (selectRef.current) {
        const rect = selectRef.current.getBoundingClientRect()
        setDropdownPosition({
          top: rect.bottom + window.scrollY + 4,
          left: rect.left + window.scrollX,
          width: rect.width
        })
      }
    }

    return () => {
      document.removeEventListener('mousedown', handleClickOutside)
    }
  }, [isOpen])

  const selectedOption = options.find(opt => opt.value === value) || null
  const displayText = selectedOption ? selectedOption.label : placeholder

  const handleSelect = (optionValue) => {
    onChange(optionValue)
    setIsOpen(false)
  }

  const triggerStyle = style.borderColor 
    ? { ...style, borderColor: style.borderColor }
    : style

  const dropdownContent = isOpen && (
    <div 
      ref={dropdownRef}
      className="select-dropdown"
      style={{
        position: 'absolute',
        top: `${dropdownPosition.top}px`,
        left: `${dropdownPosition.left}px`,
        width: `${dropdownPosition.width}px`,
        zIndex: 99999
      }}
    >
      {options.map((option) => (
        <div
          key={option.value}
          className={`select-option ${value === option.value ? 'selected' : ''}`}
          onClick={() => handleSelect(option.value)}
          style={option.color ? { borderLeftColor: option.color } : {}}
        >
          {option.icon && <span className="option-icon">{option.icon}</span>}
          <span className="option-label">{option.label}</span>
        </div>
      ))}
    </div>
  )

  return (
    <>
      <div 
        ref={selectRef}
        className={`custom-select ${isOpen ? 'open' : ''} ${className}`}
      >
        <div 
          className="select-trigger"
          onClick={() => setIsOpen(!isOpen)}
          style={triggerStyle}
        >
          <span className="select-value">{displayText}</span>
          <span className={`select-arrow ${isOpen ? 'open' : ''}`}>▼</span>
        </div>
      </div>
      
      {isOpen && createPortal(dropdownContent, document.body)}
    </>
  )
}

export default SelectBox
