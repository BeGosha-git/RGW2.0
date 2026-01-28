import React from 'react'
import './Card.css'

const Card = ({
  children,
  title,
  icon,
  className = '',
  variant = 'default',
  padding = true,
  ...props
}) => {
  return (
    <div className={`card card-${variant} ${className}`} {...props}>
      {title && (
        <div className="card-header">
          {icon && <span className="card-icon">{icon}</span>}
          <h3 className="card-title">{title}</h3>
        </div>
      )}
      <div className={`card-content ${padding ? 'card-padding' : ''}`}>
        {children}
      </div>
    </div>
  )
}

export default Card
