import React, { useState, useRef, useEffect } from 'react'
import { robotApi, filesApi, statusApi } from '../utils/api'
import './TerminalTabs.css'

// Список команд для автодополнения
const COMMANDS = ['help', 'clear', 'status', 'ls', 'pwd', 'cd', 'cat', 'nano']

function TerminalTabs({ onOpenFile }) {
  const [terminals, setTerminals] = useState([{ 
    id: 1, 
    name: 'Terminal 1', 
    history: [], 
    currentInput: '', 
    isExecuting: false, 
    currentDirectory: '.' 
  }])
  const [activeTerminalId, setActiveTerminalId] = useState(1)
  const terminalRefs = useRef({})
  const inputRefs = useRef({})
  const commandHistory = useRef([]) // История команд для автодополнения
  const [suggestions, setSuggestions] = useState([])
  const [suggestionIndex, setSuggestionIndex] = useState(-1)

  // Загружаем историю из localStorage при монтировании
  useEffect(() => {
    const savedHistory = localStorage.getItem('editor_terminal_history')
    if (savedHistory) {
      try {
        const parsed = JSON.parse(savedHistory)
        if (parsed && parsed.length > 0) {
          // Восстанавливаем все сохраненные терминалы
          const restoredTerminals = parsed.map((savedTerm, idx) => ({
            id: idx + 1,
            name: `Terminal ${idx + 1}`,
            history: savedTerm.history || [],
            currentInput: savedTerm.currentInput || '',
            isExecuting: false,
            currentDirectory: normalizePath(savedTerm.currentDirectory || '.')
          }))
          setTerminals(restoredTerminals)
          // Активируем последний терминал
          if (restoredTerminals.length > 0) {
            setActiveTerminalId(restoredTerminals[restoredTerminals.length - 1].id)
          }
        }
      } catch (e) {
        console.error('Error loading terminal history:', e)
      }
    }
  }, [])

  // Сохраняем историю в localStorage при изменении
  useEffect(() => {
    const historyToSave = terminals.map(term => ({
      history: term.history.slice(-10), // Только последние 10 команд и ответов
      currentInput: term.currentInput,
      currentDirectory: term.currentDirectory
    }))
    localStorage.setItem('editor_terminal_history', JSON.stringify(historyToSave))
  }, [terminals])

  useEffect(() => {
    const activeTerminal = terminals.find(t => t.id === activeTerminalId)
    if (activeTerminal && terminalRefs.current[activeTerminalId]) {
      terminalRefs.current[activeTerminalId].scrollTop = terminalRefs.current[activeTerminalId].scrollHeight
    }
  }, [terminals, activeTerminalId])

  useEffect(() => {
    const activeInput = inputRefs.current[activeTerminalId]
    if (activeInput) {
      activeInput.focus()
    }
    // Очищаем предложения при смене терминала
    setSuggestions([])
    setSuggestionIndex(-1)
  }, [activeTerminalId])

  const addTerminal = () => {
    const newId = Math.max(...terminals.map(t => t.id), 0) + 1
    setTerminals(prev => [...prev, {
      id: newId,
      name: `Terminal ${newId}`,
      history: [],
      currentInput: '',
      isExecuting: false,
      currentDirectory: '.'
    }])
    setActiveTerminalId(newId)
  }

  const closeTerminal = (id) => {
    if (terminals.length === 1) return // Не закрываем последний терминал
    setTerminals(prev => prev.filter(t => t.id !== id))
    if (activeTerminalId === id) {
      const remaining = terminals.filter(t => t.id !== id)
      setActiveTerminalId(remaining[remaining.length - 1].id)
    }
  }

  const addToHistory = (terminalId, type, content) => {
    setTerminals(prev => prev.map(term =>
      term.id === terminalId
        ? { ...term, history: [...term.history, { type, content, timestamp: new Date() }] }
        : term
    ))
  }

  const updateTerminalInput = (terminalId, value) => {
    setTerminals(prev => {
      const updated = prev.map(term =>
        term.id === terminalId ? { ...term, currentInput: value } : term
      )
      
      // Обновляем предложения при изменении ввода (только для активного терминала)
      if (terminalId === activeTerminalId) {
        const trimmed = value.trim()
        if (!trimmed) {
          setSuggestions([])
          setSuggestionIndex(-1)
        } else {
          const parts = trimmed.split(/\s+/)
          const currentWord = parts[parts.length - 1]

          // Если это команда (первое слово)
          if (parts.length === 1) {
            const matching = COMMANDS.filter(cmd => cmd.startsWith(currentWord.toLowerCase()))
            if (matching.length > 0) {
              setSuggestions(matching)
              setSuggestionIndex(-1)
            } else {
              setSuggestions([])
              setSuggestionIndex(-1)
            }
          } else {
            // Если это аргумент команды (например, путь для cd или ls)
            const command = parts[0].toLowerCase()
            if (command === 'cd' || command === 'ls') {
              const terminal = updated.find(t => t.id === terminalId)
              if (terminal) {
                filesApi.list(terminal.currentDirectory)
                  .then(result => {
                    if (result.success && terminalId === activeTerminalId) {
                      const items = result.items || []
                      const matching = items
                        .filter(item => item.name.startsWith(currentWord))
                        .map(item => item.name)
                      if (matching.length > 0) {
                        setSuggestions(matching)
                        setSuggestionIndex(-1)
                      } else {
                        setSuggestions([])
                        setSuggestionIndex(-1)
                      }
                    }
                  })
                  .catch(() => {
                    if (terminalId === activeTerminalId) {
                      setSuggestions([])
                      setSuggestionIndex(-1)
                    }
                  })
              }
            } else {
              setSuggestions([])
              setSuggestionIndex(-1)
            }
          }
        }
      }
      
      return updated
    })
  }

  const normalizePath = (path) => {
    if (!path || path === '.') return '.'
    
    // Разбиваем путь на части
    const parts = path.split('/').filter(p => p !== '' && p !== '.')
    const normalized = []
    
    for (const part of parts) {
      if (part === '..') {
        // Удаляем последний элемент если есть, иначе игнорируем
        if (normalized.length > 0) {
          normalized.pop()
        }
      } else {
        normalized.push(part)
      }
    }
    
    // Если массив пуст, возвращаем '.'
    if (normalized.length === 0) return '.'
    
    // Объединяем обратно
    return normalized.join('/')
  }

  const updateTerminalDirectory = (terminalId, directory) => {
    const normalizedDir = normalizePath(directory)
    setTerminals(prev => prev.map(term =>
      term.id === terminalId ? { ...term, currentDirectory: normalizedDir } : term
    ))
  }

  const setTerminalExecuting = (terminalId, executing) => {
    setTerminals(prev => prev.map(term =>
      term.id === terminalId ? { ...term, isExecuting: executing } : term
    ))
  }

  const applySuggestion = (terminalId, suggestion) => {
    const terminal = terminals.find(t => t.id === terminalId)
    if (!terminal) return

    const trimmed = terminal.currentInput.trim()
    const parts = trimmed.split(/\s+/)
    
    if (parts.length === 1) {
      // Заменяем команду
      updateTerminalInput(terminalId, suggestion + ' ')
    } else {
      // Заменяем последний аргумент
      const newParts = [...parts.slice(0, -1), suggestion]
      updateTerminalInput(terminalId, newParts.join(' ') + ' ')
    }
    setSuggestions([])
    setSuggestionIndex(-1)
  }

  const handleCommand = async (terminalId, command) => {
    if (!command.trim()) return

    const terminal = terminals.find(t => t.id === terminalId)
    if (!terminal) return

    // Добавляем команду в историю для автодополнения
    if (!commandHistory.current.includes(command.trim())) {
      commandHistory.current.push(command.trim())
      if (commandHistory.current.length > 50) {
        commandHistory.current.shift()
      }
    }

    addToHistory(terminalId, 'command', command)
    updateTerminalInput(terminalId, '')
    setSuggestions([])
    setSuggestionIndex(-1)

    if (command.trim() === 'clear') {
      setTerminals(prev => prev.map(term =>
        term.id === terminalId ? { ...term, history: [] } : term
      ))
      return
    }

    if (command.trim() === 'help') {
      addToHistory(terminalId, 'output', 'Доступные команды:')
      addToHistory(terminalId, 'output', '  help          - Показать эту справку')
      addToHistory(terminalId, 'output', '  clear         - Очистить терминал')
      addToHistory(terminalId, 'output', '  status        - Получить статус системы')
      addToHistory(terminalId, 'output', '  ls [path]     - Список файлов в директории')
      addToHistory(terminalId, 'output', '  pwd           - Текущая директория')
      addToHistory(terminalId, 'output', '  cd [path]     - Изменить директорию')
      addToHistory(terminalId, 'output', '  cat [file]    - Показать содержимое файла')
      addToHistory(terminalId, 'output', '  nano [file]   - Открыть файл в редакторе')
      addToHistory(terminalId, 'output', '  <команда>     - Выполнить команду на сервере')
      return
    }

    if (command.trim() === 'status') {
      setTerminalExecuting(terminalId, true)
      try {
        const data = await statusApi.get()
        addToHistory(terminalId, 'output', JSON.stringify(data, null, 2))
      } catch (error) {
        addToHistory(terminalId, 'error', `Ошибка: ${error.message}`)
      } finally {
        setTerminalExecuting(terminalId, false)
      }
      return
    }

    if (command.trim().startsWith('ls')) {
      setTerminalExecuting(terminalId, true)
      try {
        const parts = command.trim().split(/\s+/)
        let path = terminal.currentDirectory
        if (parts.length > 1) {
          const arg = parts[1]
          if (arg.startsWith('/')) {
            path = arg
          } else if (terminal.currentDirectory === '.') {
            path = arg
          } else {
            path = terminal.currentDirectory.endsWith('/')
              ? `${terminal.currentDirectory}${arg}`
              : `${terminal.currentDirectory}/${arg}`
          }
        }
        // Нормализуем путь перед использованием
        path = normalizePath(path)
        const result = await filesApi.list(path)
        if (result.success) {
          const items = result.items || []
          if (items.length === 0) {
            addToHistory(terminalId, 'output', 'Директория пуста')
          } else {
            const sortedItems = [...items].sort((a, b) => {
              if (a.is_dir && !b.is_dir) return -1
              if (!a.is_dir && b.is_dir) return 1
              return a.name.localeCompare(b.name)
            })
            sortedItems.forEach(item => {
              const icon = item.is_dir ? '📁' : '📄'
              const size = item.size ? ` (${item.size} байт)` : ''
              addToHistory(terminalId, 'output', `${icon} ${item.name}${size}`)
            })
          }
        } else {
          addToHistory(terminalId, 'error', result.message || 'Ошибка получения списка файлов')
        }
      } catch (error) {
        addToHistory(terminalId, 'error', `Ошибка: ${error.message}`)
      } finally {
        setTerminalExecuting(terminalId, false)
      }
      return
    }

    if (command.trim() === 'pwd') {
      const normalizedPath = normalizePath(terminal.currentDirectory)
      addToHistory(terminalId, 'output', normalizedPath)
      return
    }

    if (command.trim().startsWith('cd ')) {
      setTerminalExecuting(terminalId, true)
      try {
        const pathArg = command.trim().substring(3).trim() || '.'
        let checkPath = pathArg
        if (pathArg === '~' || pathArg === '') {
          checkPath = '.'
        } else if (!pathArg.startsWith('/')) {
          // Относительный путь - объединяем с текущей директорией
          if (terminal.currentDirectory === '.') {
            checkPath = pathArg
          } else {
            checkPath = terminal.currentDirectory.endsWith('/')
              ? `${terminal.currentDirectory}${pathArg}`
              : `${terminal.currentDirectory}/${pathArg}`
          }
        }
        // Нормализуем путь перед проверкой
        checkPath = normalizePath(checkPath)
        
        const result = await filesApi.list(checkPath)
        if (result.success) {
          updateTerminalDirectory(terminalId, checkPath)
          addToHistory(terminalId, 'output', `Директория изменена на: ${checkPath}`)
        } else {
          addToHistory(terminalId, 'error', result.message || `Директория ${pathArg} не найдена`)
        }
      } catch (error) {
        addToHistory(terminalId, 'error', `Ошибка: ${error.message}`)
      } finally {
        setTerminalExecuting(terminalId, false)
      }
      return
    }

    if (command.trim().startsWith('cat ')) {
      setTerminalExecuting(terminalId, true)
      try {
        const parts = command.trim().split(/\s+/)
        if (parts.length < 2) {
          addToHistory(terminalId, 'error', 'Использование: cat <файл>')
          return
        }
        
        const fileArg = parts[1]
        let filePath = fileArg
        
        // Обрабатываем относительные пути
        if (!fileArg.startsWith('/')) {
          if (terminal.currentDirectory === '.') {
            filePath = fileArg
          } else {
            filePath = terminal.currentDirectory.endsWith('/')
              ? `${terminal.currentDirectory}${fileArg}`
              : `${terminal.currentDirectory}/${fileArg}`
          }
        }
        
        // Нормализуем путь перед использованием
        filePath = normalizePath(filePath)
        
        const result = await filesApi.read(filePath)
        if (result.success) {
          const content = result.content || ''
          if (content) {
            // Разбиваем содержимое на строки для лучшего отображения
            const lines = content.split('\n')
            lines.forEach(line => {
              addToHistory(terminalId, 'output', line)
            })
          } else {
            addToHistory(terminalId, 'output', '(файл пуст)')
          }
        } else {
          addToHistory(terminalId, 'error', result.message || `Файл ${fileArg} не найден`)
        }
      } catch (error) {
        addToHistory(terminalId, 'error', `Ошибка: ${error.message}`)
      } finally {
        setTerminalExecuting(terminalId, false)
      }
      return
    }

    if (command.trim().startsWith('nano ')) {
      if (!onOpenFile) {
        addToHistory(terminalId, 'error', 'Редактор недоступен (команда nano работает только на странице редактора)')
        return
      }
      
      setTerminalExecuting(terminalId, true)
      try {
        const parts = command.trim().split(/\s+/)
        if (parts.length < 2) {
          addToHistory(terminalId, 'error', 'Использование: nano <файл>')
          return
        }
        
        const fileArg = parts[1]
        let filePath = fileArg
        
        // Обрабатываем относительные пути
        if (!fileArg.startsWith('/')) {
          if (terminal.currentDirectory === '.') {
            filePath = fileArg
          } else {
            filePath = terminal.currentDirectory.endsWith('/')
              ? `${terminal.currentDirectory}${fileArg}`
              : `${terminal.currentDirectory}/${fileArg}`
          }
        }
        
        // Нормализуем путь перед использованием
        filePath = normalizePath(filePath)
        
        // Проверяем, что это файл, а не директория
        const listResult = await filesApi.list(filePath)
        if (listResult.success && listResult.items && listResult.items.length > 0) {
          const item = listResult.items[0]
          if (item.is_dir) {
            addToHistory(terminalId, 'error', `${fileArg} является директорией, а не файлом`)
            return
          }
        }
        
        // Открываем файл в редакторе
        await onOpenFile(filePath)
        addToHistory(terminalId, 'output', `Файл ${filePath} открыт в редакторе`)
      } catch (error) {
        addToHistory(terminalId, 'error', `Ошибка: ${error.message}`)
      } finally {
        setTerminalExecuting(terminalId, false)
      }
      return
    }

    // Выполнение команды через API
    setTerminalExecuting(terminalId, true)
    try {
      const parts = command.trim().split(/\s+/)
      const cmd = parts[0]
      const args = parts.slice(1)

      const result = await robotApi.execute(cmd, args)
      if (result.success) {
        if (result.stdout) {
          addToHistory(terminalId, 'output', result.stdout)
        }
        if (result.stderr) {
          addToHistory(terminalId, 'error', result.stderr)
        }
        if (!result.stdout && !result.stderr) {
          addToHistory(terminalId, 'output', `Команда выполнена успешно (код возврата: ${result.return_code || 0})`)
        }
      } else {
        addToHistory(terminalId, 'error', result.message || 'Ошибка выполнения команды')
      }
    } catch (error) {
      addToHistory(terminalId, 'error', `Ошибка: ${error.message}`)
    } finally {
      setTerminalExecuting(terminalId, false)
    }
  }

  const handleKeyDown = (e, terminalId) => {
    const terminal = terminals.find(t => t.id === terminalId)
    if (!terminal) return

    if (e.key === 'Tab' && suggestions.length > 0) {
      e.preventDefault()
      const index = suggestionIndex >= 0 ? suggestionIndex : 0
      applySuggestion(terminalId, suggestions[index])
      return
    }

    if (e.key === 'ArrowDown' && suggestions.length > 0) {
      e.preventDefault()
      setSuggestionIndex(prev => 
        prev < suggestions.length - 1 ? prev + 1 : prev
      )
      return
    }

    if (e.key === 'ArrowUp' && suggestions.length > 0) {
      e.preventDefault()
      setSuggestionIndex(prev => prev > 0 ? prev - 1 : -1)
      return
    }

    if (e.key === 'Enter' && !terminal.isExecuting) {
      handleCommand(terminalId, terminal.currentInput)
    }
  }

  const activeTerminal = terminals.find(t => t.id === activeTerminalId)

  return (
    <div className="terminal-tabs-container">
      <div className="terminal-tabs-header">
        {terminals.map(term => (
          <div
            key={term.id}
            className={`terminal-tab ${activeTerminalId === term.id ? 'active' : ''}`}
            onClick={() => {
              setActiveTerminalId(term.id)
              setSuggestions([])
              setSuggestionIndex(-1)
            }}
          >
            <span>{term.name}</span>
            {terminals.length > 1 && (
              <button
                className="terminal-tab-close"
                onClick={(e) => {
                  e.stopPropagation()
                  closeTerminal(term.id)
                }}
              >
                ×
              </button>
            )}
          </div>
        ))}
        <button className="terminal-tab-add" onClick={addTerminal} title="Новый терминал">
          +
        </button>
      </div>
      {activeTerminal && (
        <div className="terminal-content">
          <div
            ref={el => terminalRefs.current[activeTerminalId] = el}
            className="terminal-output"
          >
            {activeTerminal.history.length === 0 && (
              <div className="terminal-welcome">
                <div>RGW 2.0 Terminal</div>
                <div>Текущая директория: {activeTerminal.currentDirectory}</div>
                <div>Введите команду для выполнения. Используйте "help" для списка доступных команд.</div>
                <div>Используйте Tab для автодополнения команд.</div>
              </div>
            )}
            {activeTerminal.history.map((item, idx) => (
              <div key={idx} className={`terminal-line terminal-line-${item.type}`}>
                {item.type === 'command' && <span className="terminal-prompt">$ </span>}
                <span>{item.content}</span>
              </div>
            ))}
            {activeTerminal.isExecuting && (
              <div className="terminal-line terminal-line-output">
                <span className="terminal-prompt">$ </span>
                <span className="terminal-executing">Выполняется...</span>
              </div>
            )}
          </div>
          <div className="terminal-input-container">
            <span className="terminal-prompt">$ </span>
            <div className="terminal-input-wrapper">
              <input
                ref={el => inputRefs.current[activeTerminalId] = el}
                type="text"
                className="terminal-input"
                value={activeTerminal.currentInput}
                onChange={(e) => updateTerminalInput(activeTerminalId, e.target.value)}
                onKeyDown={(e) => handleKeyDown(e, activeTerminalId)}
                disabled={activeTerminal.isExecuting}
                placeholder="Введите команду..."
              />
              {suggestions.length > 0 && (
                <div className="terminal-suggestions">
                  {suggestions.map((suggestion, idx) => (
                    <div
                      key={idx}
                      className={`terminal-suggestion ${idx === suggestionIndex ? 'selected' : ''}`}
                      onClick={() => applySuggestion(activeTerminalId, suggestion)}
                    >
                      {suggestion}
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default TerminalTabs
