import React, { useState, useRef, useEffect } from 'react'
import Button from '../components/Button'
import { statusApi, filesApi, robotApi } from '../utils/api'
import './TerminalPage.css'

function TerminalPage() {
  const [history, setHistory] = useState([
    { type: 'output', content: 'RGW 2.0 Terminal - Система управления роботами', timestamp: new Date() },
    { type: 'output', content: 'Введите команду для выполнения. Используйте "help" для списка доступных команд.', timestamp: new Date() },
  ])
  const [currentInput, setCurrentInput] = useState('')
  const [isExecuting, setIsExecuting] = useState(false)
  const [currentDirectory, setCurrentDirectory] = useState('.')
  const terminalRef = useRef(null)
  const inputRef = useRef(null)

  useEffect(() => {
    if (terminalRef.current) {
      terminalRef.current.scrollTop = terminalRef.current.scrollHeight
    }
  }, [history])

  // Всегда держим фокус на поле ввода
  useEffect(() => {
    inputRef.current?.focus()
  }, [])

  // Возвращаем фокус после выполнения команды
  useEffect(() => {
    if (!isExecuting) {
      // Небольшая задержка, чтобы убедиться, что DOM обновился
      const timer = setTimeout(() => {
        inputRef.current?.focus()
      }, 10)
      return () => clearTimeout(timer)
    }
  }, [isExecuting, history])

  // Возвращаем фокус при клике на терминал (но не на поле ввода)
  const handleTerminalClick = (e) => {
    // Если клик не на поле ввода или его контейнере, возвращаем фокус
    if (!e.target.closest('.terminal-input-container')) {
      inputRef.current?.focus()
    }
  }

  const addToHistory = (type, content) => {
    setHistory(prev => [...prev, { type, content, timestamp: new Date() }])
  }

  const handleCommand = async (command) => {
    if (!command.trim()) return

    addToHistory('command', command)

    // Обработка встроенных команд
    if (command.trim() === 'clear') {
      setHistory([])
      return
    }

    if (command.trim() === 'help') {
      addToHistory('output', 'Доступные команды:')
      addToHistory('output', '  help          - Показать эту справку')
      addToHistory('output', '  clear         - Очистить терминал')
      addToHistory('output', '  status        - Получить статус системы')
      addToHistory('output', '  ls [path]     - Список файлов в директории')
      addToHistory('output', '  pwd           - Текущая директория')
      addToHistory('output', '  cd [path]     - Изменить директорию')
      addToHistory('output', '  <команда>     - Выполнить команду на сервере')
      return
    }

    if (command.trim() === 'status') {
      setIsExecuting(true)
      try {
        const data = await statusApi.get()
        addToHistory('output', JSON.stringify(data, null, 2))
      } catch (error) {
        addToHistory('error', `Ошибка: ${error.message}`)
      } finally {
        setIsExecuting(false)
      }
      return
    }

    if (command.trim().startsWith('ls')) {
      setIsExecuting(true)
      try {
        const parts = command.trim().split(/\s+/)
        let path = currentDirectory
        if (parts.length > 1) {
          const arg = parts[1]
          if (arg.startsWith('/')) {
            path = arg
          } else if (currentDirectory === '.') {
            path = arg
          } else {
            path = currentDirectory.endsWith('/') 
              ? `${currentDirectory}${arg}` 
              : `${currentDirectory}/${arg}`
          }
        }
        
        const result = await filesApi.list(path)
        if (result.success) {
          const items = result.items || []
          if (items.length === 0) {
            addToHistory('output', 'Директория пуста')
          } else {
            const sortedItems = [...items].sort((a, b) => {
              if (a.is_dir && !b.is_dir) return -1
              if (!a.is_dir && b.is_dir) return 1
              return a.name.localeCompare(b.name)
            })
            sortedItems.forEach(item => {
              const icon = item.is_dir ? '📁' : '📄'
              const size = item.size ? ` (${item.size} байт)` : ''
              addToHistory('output', `${icon} ${item.name}${size}`)
            })
          }
        } else {
          addToHistory('error', result.message || 'Ошибка получения списка файлов')
        }
      } catch (error) {
        addToHistory('error', `Ошибка: ${error.message}`)
      } finally {
        setIsExecuting(false)
      }
      return
    }

    if (command.trim() === 'pwd') {
      addToHistory('output', currentDirectory)
      return
    }

    if (command.trim().startsWith('cd ')) {
      setIsExecuting(true)
      try {
        const pathArg = command.trim().substring(3).trim() || '.'
        
        let checkPath = pathArg
        if (pathArg === '~' || pathArg === '') {
          checkPath = '.'
        } else if (!pathArg.startsWith('/')) {
          if (currentDirectory === '.') {
            checkPath = pathArg
          } else {
            checkPath = currentDirectory.endsWith('/') 
              ? `${currentDirectory}${pathArg}` 
              : `${currentDirectory}/${pathArg}`
          }
        }
        
        const result = await filesApi.list(checkPath)
        
        if (result.success) {
          setCurrentDirectory(checkPath)
          addToHistory('output', `Директория изменена на: ${checkPath}`)
        } else {
          addToHistory('error', result.message || `Директория ${pathArg} не найдена`)
        }
      } catch (error) {
        addToHistory('error', `Ошибка: ${error.message}`)
      } finally {
        setIsExecuting(false)
      }
      return
    }

    // Выполнение команды через API
    setIsExecuting(true)
    try {
      const parts = command.trim().split(/\s+/)
      const cmd = parts[0]
      const args = parts.slice(1)

      const result = await robotApi.execute(cmd, args)
      
      if (result.success) {
        if (result.stdout) {
          addToHistory('output', result.stdout)
        }
        if (result.return_code !== undefined && result.return_code !== 0) {
          addToHistory('output', `Код возврата: ${result.return_code}`)
        } else if (result.return_code === 0 && !result.stdout) {
          addToHistory('output', `Код возврата: ${result.return_code}`)
        }
      } else {
        if (result.stderr) {
          addToHistory('error', result.stderr)
        } else if (result.message) {
          addToHistory('error', result.message)
        } else {
          addToHistory('error', 'Ошибка выполнения команды')
        }
        if (result.return_code !== undefined) {
          addToHistory('error', `Код возврата: ${result.return_code}`)
        }
      }
    } catch (error) {
      addToHistory('error', `Ошибка: ${error.message}`)
    } finally {
      setIsExecuting(false)
    }
  }

  const handleSubmit = (e) => {
    e.preventDefault()
    if (currentInput.trim() && !isExecuting) {
      handleCommand(currentInput)
      setCurrentInput('')
    }
  }

  const handleKeyDown = (e) => {
    if (e.key === 'Enter') {
      handleSubmit(e)
    }
  }

  return (
    <div className="terminal-page">
      <div className="page-header">
        <h1 className="page-title">Терминал системы</h1>
        <div className="header-actions">
          <Button 
            variant="secondary"
            onClick={() => setHistory([])}
          >
            Очистить
          </Button>
        </div>
      </div>

      <div className="terminal-container" onClick={handleTerminalClick}>
        <div className="terminal-content" ref={terminalRef}>
          {history.map((item, index) => (
            <div key={index} className={`terminal-line terminal-line-${item.type}`}>
              {item.type === 'command' && (
                <>
                  <span className="terminal-prompt">
                    <span className="terminal-user">user</span>
                    <span className="terminal-separator">@</span>
                    <span className="terminal-host">rgw</span>
                    <span className="terminal-path">:{currentDirectory === '.' ? '~' : currentDirectory}</span>
                    <span className="terminal-symbol">$</span>
                  </span>
                  <span className="terminal-command">{item.content}</span>
                </>
              )}
              {item.type === 'output' && (
                <span className="terminal-output">{item.content}</span>
              )}
              {item.type === 'error' && (
                <span className="terminal-error">{item.content}</span>
              )}
            </div>
          ))}
          {isExecuting && (
            <div className="terminal-line">
              <span className="terminal-output">Выполнение команды...</span>
            </div>
          )}
        </div>
        <form className="terminal-input-container" onSubmit={handleSubmit}>
          <span className="terminal-prompt">
            <span className="terminal-user">user</span>
            <span className="terminal-separator">@</span>
            <span className="terminal-host">rgw</span>
            <span className="terminal-path">:{currentDirectory === '.' ? '~' : currentDirectory}</span>
            <span className="terminal-symbol">$</span>
          </span>
          <input
            ref={inputRef}
            type="text"
            className="terminal-input"
            value={currentInput}
            onChange={(e) => setCurrentInput(e.target.value)}
            onKeyDown={handleKeyDown}
            disabled={isExecuting}
            placeholder="Введите команду..."
            autoFocus
          />
        </form>
      </div>
    </div>
  )
}

export default TerminalPage
