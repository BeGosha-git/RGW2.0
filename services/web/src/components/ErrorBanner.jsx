import React from 'react'
import Button from './Button'
import './ErrorBanner.css'

const ErrorBanner = ({ 
  error, 
  onDismiss, 
  onRetry, 
  variant = 'error',
  className = '' 
}) => {
  if (!error) return null

  return (
    <div className={`error-banner error-banner-${variant} ${className}`}>
      <div className="error-banner-content">
        <span className="error-banner-icon">
          {variant === 'error' ? '⚠' : variant === 'warning' ? '⚠' : 'ℹ'}
        </span>
        <div className="error-banner-message">
          {typeof error === 'string' ? error : error.message || 'Произошла ошибка'}
        </div>
      </div>
      <div className="error-banner-actions">
        {onRetry && (
          <Button 
            variant="secondary" 
            size="small" 
            onClick={onRetry}
          >
            Повторить
          </Button>
        )}
        {onDismiss && (
          <button 
            className="error-banner-close"
            onClick={onDismiss}
            aria-label="Закрыть"
          >
            ✕
          </button>
        )}
      </div>
    </div>
  )
}

export default ErrorBanner
