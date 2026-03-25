import React, { useEffect, useRef, useState } from 'react'
import './CustomSelect.css'

/* Кастомный выпадающий список вместо нативного select для единого стиля. */
function CustomSelect({
  value,
  onChange,
  options,
  placeholder = 'Выбрать…',
  disabled = false,
  className = '',
  id,
}) {
  const [open, setOpen] = useState(false)
  const rootRef = useRef(null)

  useEffect(() => {
    if (!open) return
    const onDoc = (e) => {
      if (rootRef.current && !rootRef.current.contains(e.target)) setOpen(false)
    }
    document.addEventListener('mousedown', onDoc, true)
    document.addEventListener('touchstart', onDoc, true)
    return () => {
      document.removeEventListener('mousedown', onDoc, true)
      document.removeEventListener('touchstart', onDoc, true)
    }
  }, [open])

  const selected = options.find((o) => o.value === value)
  const label = selected?.label ?? placeholder

  return (
    <div ref={rootRef} className={`custom-select ${open ? 'custom-select--open' : ''} ${className}`} id={id}>
      <button
        type="button"
        className="custom-select__trigger"
        disabled={disabled}
        aria-haspopup="listbox"
        aria-expanded={open}
        onClick={() => !disabled && setOpen((v) => !v)}
      >
        <span className="custom-select__value">{label}</span>
        <span className="custom-select__chev" aria-hidden />
      </button>
      {open && (
        <ul className="custom-select__menu" role="listbox">
          {options.map((opt) => (
            <li key={String(opt.value)}>
              <button
                type="button"
                role="option"
                aria-selected={opt.value === value}
                className={`custom-select__option${opt.value === value ? ' is-active' : ''}`}
                onClick={() => {
                  onChange(opt.value)
                  setOpen(false)
                }}
              >
                {opt.label}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

export default CustomSelect
