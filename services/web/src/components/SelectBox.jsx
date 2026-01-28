import React, { useState, useRef, useEffect } from 'react'
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

  useEffect(() => {
    const handleClickOutside = (event) => {
      if (selectRef.current && !selectRef.current.contains(event.target)) {
        setIsOpen(false)
      }
    }

    if (isOpen) {
      document.addEventListener('mousedown', handleClickOutside)
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

  return (
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
      
      {isOpen && (
        <div className="select-dropdown">
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
      )}
    </div>
  )
}

export default SelectBox
