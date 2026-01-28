import React, { useState, useEffect, useRef } from 'react'
import Editor from '@monaco-editor/react'
import Modal from '../components/Modal'
import Button from '../components/Button'
import ErrorBanner from '../components/ErrorBanner'
import Loading from '../components/Loading'
import Toast from '../components/Toast'
import TerminalTabs from '../components/TerminalTabs'
import { useToast } from '../hooks/useToast'
import { useInterval } from '../hooks/useInterval'
import { filesApi, directoryApi } from '../utils/api'
import { ICONS } from '../constants/icons'
import './FileEditorPage.css'

function FileEditorPage() {
  const [currentPath, setCurrentPath] = useState('.')
  const [files, setFiles] = useState([])
  const [selectedFile, setSelectedFile] = useState(null)
  const [openFiles, setOpenFiles] = useState([]) // [{ path: string, content: string, modified: boolean }]
  const [showTerminal, setShowTerminal] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const errorTimeoutRef = useRef(null)

  const setErrorWithAutoHide = (errorMessage) => {
    setError(errorMessage)
    if (errorTimeoutRef.current) {
      clearTimeout(errorTimeoutRef.current)
    }
    errorTimeoutRef.current = setTimeout(() => {
      setError(null)
    }, 10000)
  }
  const [saving, setSaving] = useState({}) // { filepath: boolean }
  const [showNewFileDialog, setShowNewFileDialog] = useState(false)
  const [newFileName, setNewFileName] = useState('')
  const [showNewDirDialog, setShowNewDirDialog] = useState(false)
  const [newDirName, setNewDirName] = useState('')
  const [contextMenu, setContextMenu] = useState(null)
  const [renameItem, setRenameItem] = useState(null)
  const [renameValue, setRenameValue] = useState('')
  const editorRefs = useRef({}) // { filepath: editor }
  const contextMenuRef = useRef(null)
  const { toast, showToast, hideToast } = useToast()

  const loadDirectory = async (path) => {
    try {
      setLoading(true)
      setError(null)
      const result = await filesApi.list(path)
      if (result.success) {
        setFiles(result.items || [])
        setCurrentPath(result.dirpath || path)
      } else {
        setError(result.message || 'Ошибка загрузки директории')
        if (errorTimeoutRef.current) {
          clearTimeout(errorTimeoutRef.current)
        }
        errorTimeoutRef.current = setTimeout(() => {
          setError(null)
        }, 10000)
      }
    } catch (err) {
      setError(err.message || 'Ошибка загрузки директории')
      if (errorTimeoutRef.current) {
        clearTimeout(errorTimeoutRef.current)
      }
      errorTimeoutRef.current = setTimeout(() => {
        setError(null)
      }, 10000)
    } finally {
      setLoading(false)
    }
  }

  const loadFile = async (filepath) => {
    // Проверяем, не открыт ли файл уже
    const existingFile = openFiles.find(f => f.path === filepath)
    if (existingFile) {
      setSelectedFile(filepath)
      return
    }

    try {
      setLoading(true)
      setError(null)
      const result = await filesApi.read(filepath)
      if (result.success) {
        // Добавляем файл в открытые
        setOpenFiles(prev => [...prev, {
          path: filepath,
          content: result.content || '',
          modified: false
        }])
        setSelectedFile(filepath)
      } else {
        setErrorWithAutoHide(result.message || 'Ошибка загрузки файла')
      }
    } catch (err) {
      setErrorWithAutoHide(err.message || 'Ошибка загрузки файла')
    } finally {
      setLoading(false)
    }
  }

  const saveFile = async (filepath = null) => {
    const fileToSave = filepath || selectedFile
    if (!fileToSave) return

    const file = openFiles.find(f => f.path === fileToSave)
    if (!file) return

    try {
      setSaving(prev => ({ ...prev, [fileToSave]: true }))
      setError(null)
      const result = await filesApi.write(fileToSave, file.content)
      if (result.success) {
        // Обновляем файл в открытых, убираем флаг modified
        setOpenFiles(prev => prev.map(f => 
          f.path === fileToSave ? { ...f, modified: false } : f
        ))
        showToast('Файл успешно сохранен', 'success')
      } else {
        setErrorWithAutoHide(result.message || 'Ошибка сохранения файла')
      }
    } catch (err) {
      setErrorWithAutoHide(err.message || 'Ошибка сохранения файла')
    } finally {
      setSaving(prev => ({ ...prev, [fileToSave]: false }))
    }
  }

  const closeFile = (filepath) => {
    const file = openFiles.find(f => f.path === filepath)
    if (file && file.modified) {
      if (!window.confirm(`Файл "${filepath}" изменен. Закрыть без сохранения?`)) {
        return
      }
    }
    
    setOpenFiles(prev => {
      const remaining = prev.filter(f => f.path !== filepath)
      // Если закрываем активный файл, переключаемся на другой
      if (selectedFile === filepath) {
        setSelectedFile(remaining.length > 0 ? remaining[remaining.length - 1].path : null)
      }
      return remaining
    })
    
    // Очищаем ref редактора
    if (editorRefs.current[filepath]) {
      delete editorRefs.current[filepath]
    }
  }

  const updateFileContent = (filepath, content) => {
    setOpenFiles(prev => prev.map(f => 
      f.path === filepath ? { ...f, content, modified: true } : f
    ))
  }

  const handleCreateFile = async () => {
    if (!newFileName.trim()) return

    try {
      const filepath = currentPath === '.' 
        ? newFileName 
        : `${currentPath}/${newFileName}`
      
      const result = await filesApi.create(filepath, '')
      if (result.success) {
        setShowNewFileDialog(false)
        setNewFileName('')
        loadDirectory(currentPath)
        // Открываем новый файл в табе
        setOpenFiles(prev => [...prev, {
          path: filepath,
          content: '',
          modified: false
        }])
        setSelectedFile(filepath)
        showToast('Файл создан', 'success')
      } else {
        setErrorWithAutoHide(result.message || 'Ошибка создания файла')
      }
    } catch (err) {
      setErrorWithAutoHide(err.message || 'Ошибка создания файла')
    }
  }

  const handleCreateDirectory = async () => {
    if (!newDirName.trim()) return

    try {
      const dirpath = currentPath === '.' 
        ? newDirName 
        : `${currentPath}/${newDirName}`
      
      const result = await directoryApi.create(dirpath)
      if (result.success) {
        setShowNewDirDialog(false)
        setNewDirName('')
        loadDirectory(currentPath)
        showToast('Директория создана', 'success')
      } else {
        setErrorWithAutoHide(result.message || 'Ошибка создания директории')
      }
    } catch (err) {
      setErrorWithAutoHide(err.message || 'Ошибка создания директории')
    }
  }

  const handleDelete = async (item) => {
    if (!window.confirm(`Удалить ${item.is_dir ? 'директорию' : 'файл'} "${item.name}"?`)) {
      return
    }

    try {
      const result = item.is_dir 
        ? await directoryApi.delete(item.path)
        : await filesApi.delete(item.path)
      
      if (result.success) {
        // Закрываем файл если он открыт
        if (!item.is_dir) {
          closeFile(item.path)
        }
        loadDirectory(currentPath)
        showToast(`${item.is_dir ? 'Директория' : 'Файл'} удален`, 'success')
      } else {
        setErrorWithAutoHide(result.message || 'Ошибка удаления')
      }
    } catch (err) {
      setErrorWithAutoHide(err.message || 'Ошибка удаления')
    }
  }

  const handleNavigate = (item) => {
    if (item.is_dir) {
      loadDirectory(item.path)
      // НЕ закрываем открытые файлы при смене директории
    } else {
      loadFile(item.path)
    }
  }

  const handleGoUp = () => {
    if (currentPath === '.') return
    const parentPath = currentPath.split('/').slice(0, -1).join('/') || '.'
    loadDirectory(parentPath)
    // НЕ закрываем открытые файлы при переходе на уровень выше
  }

  const handleRename = async (item, newName) => {
    if (!newName || newName.trim() === '' || newName === item.name) {
      setRenameItem(null)
      setRenameValue('')
      return
    }

    try {
      const dir = currentPath === '.' ? '' : currentPath
      const oldPath = item.path
      const newPath = dir ? `${dir}/${newName}` : newName
      
      const result = await filesApi.rename(oldPath, newPath)
      
      if (result.success) {
        // Обновляем путь в открытых файлах
        setOpenFiles(prev => prev.map(f => 
          f.path === oldPath ? { ...f, path: newPath } : f
        ))
        if (selectedFile === oldPath) {
          setSelectedFile(newPath)
        }
        loadDirectory(currentPath)
        showToast('Переименовано', 'success')
      } else {
        setErrorWithAutoHide(result.message || 'Ошибка переименования')
      }
    } catch (err) {
      setErrorWithAutoHide(err.message || 'Ошибка переименования')
    } finally {
      setRenameItem(null)
      setRenameValue('')
    }
  }

  const handleContextMenu = (e, item) => {
    e.preventDefault()
    e.stopPropagation()
    setContextMenu({
      x: e.clientX,
      y: e.clientY,
      item: item
    })
  }

  const handleContextMenuAction = (action, item) => {
    setContextMenu(null)
    if (action === 'rename') {
      setRenameItem(item)
      setRenameValue(item.name)
    } else if (action === 'delete') {
      handleDelete(item)
    }
  }

  useEffect(() => {
    const handleClickOutside = (e) => {
      if (contextMenuRef.current && !contextMenuRef.current.contains(e.target)) {
        setContextMenu(null)
      }
    }

    if (contextMenu) {
      document.addEventListener('click', handleClickOutside)
      return () => document.removeEventListener('click', handleClickOutside)
    }
  }, [contextMenu])

  const getLanguage = (filename) => {
    const ext = filename.split('.').pop()?.toLowerCase() || ''
    const langMap = {
      'js': 'javascript', 'jsx': 'javascript',
      'ts': 'typescript', 'tsx': 'typescript',
      'py': 'python', 'java': 'java',
      'cpp': 'cpp', 'c': 'c', 'cs': 'csharp',
      'php': 'php', 'rb': 'ruby', 'go': 'go', 'rs': 'rust',
      'html': 'html', 'css': 'css', 'scss': 'scss',
      'json': 'json', 'xml': 'xml',
      'yaml': 'yaml', 'yml': 'yaml',
      'md': 'markdown',
      'sh': 'shell', 'bat': 'batch', 'ps1': 'powershell',
      'sql': 'sql',
    }
    return langMap[ext] || 'plaintext'
  }

  // Загружаем открытые файлы из localStorage при монтировании
  useEffect(() => {
    const savedOpenFiles = localStorage.getItem('editor_open_files')
    if (savedOpenFiles) {
      try {
        const parsed = JSON.parse(savedOpenFiles)
        if (parsed && parsed.length > 0) {
          // Загружаем содержимое файлов
          Promise.all(parsed.map(async (file) => {
            try {
              const result = await filesApi.read(file.path)
              if (result.success) {
                return {
                  path: file.path,
                  content: result.content || '',
                  modified: false // Всегда false при загрузке
                }
              }
              return null
            } catch (e) {
              console.error(`Error loading file ${file.path}:`, e)
              return null
            }
          })).then(loadedFiles => {
            const validFiles = loadedFiles.filter(f => f !== null)
            if (validFiles.length > 0) {
              setOpenFiles(validFiles)
              setSelectedFile(validFiles[0].path)
            }
          })
        }
      } catch (e) {
        console.error('Error loading open files:', e)
      }
    }
  }, [])

  // Сохраняем открытые файлы в localStorage при изменении
  useEffect(() => {
    const filesToSave = openFiles.map(f => ({ path: f.path }))
    localStorage.setItem('editor_open_files', JSON.stringify(filesToSave))
  }, [openFiles])

  useEffect(() => {
    loadDirectory(currentPath)
  }, [])

  return (
    <div className="file-editor-page">
      <div className="editor-header">
        <h1 className="page-title">Редактор файлов</h1>
        <div className="editor-actions">
          {selectedFile && (
            <Button 
              onClick={() => saveFile(selectedFile)} 
              disabled={saving[selectedFile]}
              loading={saving[selectedFile]}
              icon="💾"
            >
              Сохранить
            </Button>
          )}
          <Button 
            variant="secondary"
            onClick={() => setShowNewFileDialog(true)}
            icon="➕"
          >
            Новый файл
          </Button>
          <Button 
            variant="secondary"
            onClick={() => setShowNewDirDialog(true)}
            icon="📁"
          >
            Новая папка
          </Button>
          <Button 
            variant={showTerminal ? "primary" : "secondary"}
            onClick={() => setShowTerminal(!showTerminal)}
            icon="💻"
          >
            {showTerminal ? 'Скрыть терминал' : 'Терминал'}
          </Button>
        </div>
      </div>

      {error && (
        <ErrorBanner 
          error={error} 
          onDismiss={() => {
            if (errorTimeoutRef.current) {
              clearTimeout(errorTimeoutRef.current)
            }
            setError(null)
          }}
          variant="error"
        />
      )}

      <div className={`editor-layout ${showTerminal ? 'with-terminal' : ''}`}>
        {/* File Explorer */}
        <div className="file-explorer">
          <div className="explorer-header">
            <div className="path-navigation">
              <span className="current-path" title={currentPath}>
                {currentPath}
              </span>
            </div>
          </div>

          {loading && !files.length ? (
            <Loading text="Загрузка..." />
          ) : (
            <div className="file-list">
              {/* Сортировка: сначала папки, потом файлы */}
              {(() => {
                const sortedFiles = [...files].sort((a, b) => {
                  // Сначала папки, потом файлы
                  if (a.is_dir && !b.is_dir) return -1
                  if (!a.is_dir && b.is_dir) return 1
                  // Внутри каждой группы сортируем по имени
                  return a.name.localeCompare(b.name)
                })

                // Создаем массив для отображения: сначала "..", потом отсортированные элементы
                const displayItems = []
                
                // Добавляем ".." если не в корневой директории
                if (currentPath !== '.') {
                  displayItems.push({
                    name: '..',
                    path: currentPath.split('/').slice(0, -1).join('/') || '.',
                    is_dir: true,
                    isParent: true
                  })
                }
                
                // Добавляем отсортированные элементы
                displayItems.push(...sortedFiles)

                return displayItems.map((item) => (
                  <div
                    key={item.path}
                    className={`file-item ${openFiles.some(f => f.path === item.path) ? 'open' : ''} ${selectedFile === item.path ? 'selected' : ''} ${item.is_dir ? 'directory' : ''}`}
                    onClick={() => {
                      if (!renameItem || renameItem.path !== item.path) {
                        if (item.isParent) {
                          handleGoUp()
                        } else {
                          handleNavigate(item)
                        }
                      }
                    }}
                    onDoubleClick={() => !item.is_dir && !item.isParent && handleNavigate(item)}
                    onContextMenu={(e) => {
                      if (!item.isParent) {
                        handleContextMenu(e, item)
                      }
                    }}
                  >
                    {renameItem && renameItem.path === item.path ? (
                      <input
                        type="text"
                        className="rename-input"
                        value={renameValue}
                        onChange={(e) => setRenameValue(e.target.value)}
                        onBlur={() => handleRename(item, renameValue)}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter') {
                            handleRename(item, renameValue)
                          } else if (e.key === 'Escape') {
                            setRenameItem(null)
                            setRenameValue('')
                          }
                        }}
                        autoFocus
                        onClick={(e) => e.stopPropagation()}
                      />
                    ) : (
                      <>
                        <span className="file-icon">
                          {item.is_dir ? '📁' : '📄'}
                        </span>
                        <span className="file-name">{item.name}</span>
                      </>
                    )}
                  </div>
                ))
              })()}
              {files.length === 0 && currentPath === '.' && (
                <div className="empty-state">
                  <p>Директория пуста</p>
                </div>
              )}
            </div>
          )}
        </div>

        {/* Context Menu */}
        {contextMenu && (
          <div
            ref={contextMenuRef}
            className="context-menu"
            style={{
              position: 'fixed',
              left: `${contextMenu.x}px`,
              top: `${contextMenu.y}px`,
              zIndex: 1000
            }}
          >
            <button
              className="context-menu-item"
              onClick={() => handleContextMenuAction('rename', contextMenu.item)}
            >
              Переименовать
            </button>
            <button
              className="context-menu-item"
              onClick={() => handleContextMenuAction('delete', contextMenu.item)}
            >
              Удалить
            </button>
          </div>
        )}

        {/* Editor */}
        <div className="editor-container">
          {openFiles.length > 0 ? (
            <>
              {/* Tabs */}
              <div className="editor-tabs">
                {openFiles.map(file => {
                  const fileName = file.path.split('/').pop() || file.path
                  const isActive = selectedFile === file.path
                  return (
                    <div
                      key={file.path}
                      className={`editor-tab ${isActive ? 'active' : ''} ${file.modified ? 'modified' : ''}`}
                      onClick={() => setSelectedFile(file.path)}
                      title={file.path}
                    >
                      <span className="tab-name">{fileName}</span>
                      {file.modified && <span className="tab-modified-indicator">●</span>}
                      <button
                        className="tab-close"
                        onClick={(e) => {
                          e.stopPropagation()
                          closeFile(file.path)
                        }}
                        title="Закрыть"
                      >
                        ×
                      </button>
                    </div>
                  )
                })}
              </div>
              
              {/* Editor Content */}
              {selectedFile && (() => {
                const file = openFiles.find(f => f.path === selectedFile)
                if (!file) return null
                
                return (
                  <Editor
                    height="100%"
                    language={getLanguage(selectedFile)}
                    value={file.content}
                    onChange={(value) => updateFileContent(selectedFile, value || '')}
                    theme="vs-dark"
                    options={{
                      minimap: { enabled: true },
                      fontSize: 14,
                      wordWrap: 'on',
                      automaticLayout: true,
                      scrollBeyondLastLine: false,
                      tabSize: 2,
                      insertSpaces: true,
                    }}
                    onMount={(editor) => {
                      editorRefs.current[selectedFile] = editor
                    }}
                  />
                )
              })()}
            </>
          ) : (
            <div className="editor-placeholder">
              <div className="placeholder-content">
                <span className="placeholder-icon">{ICONS.EDITOR}</span>
                <h2>Выберите файл для редактирования</h2>
                <p>Откройте файл из списка слева или создайте новый</p>
              </div>
            </div>
          )}
        </div>

        {/* Terminal Panel */}
        {showTerminal && (
          <div className="terminal-panel">
            <TerminalTabs />
          </div>
        )}
      </div>

      {/* New File Modal */}
      <Modal
        isOpen={showNewFileDialog}
        onClose={() => {
          setShowNewFileDialog(false)
          setNewFileName('')
        }}
        title="Создать новый файл"
        size="small"
        footer={
          <>
            <Button onClick={handleCreateFile} disabled={!newFileName.trim()}>
              Создать
            </Button>
            <Button 
              variant="secondary"
              onClick={() => {
                setShowNewFileDialog(false)
                setNewFileName('')
              }}
            >
              Отмена
            </Button>
          </>
        }
      >
        <input
          type="text"
          className="modal-input"
          placeholder="Имя файла"
          value={newFileName}
          onChange={(e) => setNewFileName(e.target.value)}
          onKeyPress={(e) => e.key === 'Enter' && newFileName.trim() && handleCreateFile()}
          autoFocus
        />
      </Modal>

      {/* New Directory Modal */}
      <Modal
        isOpen={showNewDirDialog}
        onClose={() => {
          setShowNewDirDialog(false)
          setNewDirName('')
        }}
        title="Создать новую папку"
        size="small"
        footer={
          <>
            <Button onClick={handleCreateDirectory} disabled={!newDirName.trim()}>
              Создать
            </Button>
            <Button 
              variant="secondary"
              onClick={() => {
                setShowNewDirDialog(false)
                setNewDirName('')
              }}
            >
              Отмена
            </Button>
          </>
        }
      >
        <input
          type="text"
          className="modal-input"
          placeholder="Имя папки"
          value={newDirName}
          onChange={(e) => setNewDirName(e.target.value)}
          onKeyPress={(e) => e.key === 'Enter' && newDirName.trim() && handleCreateDirectory()}
          autoFocus
        />
      </Modal>

      {/* Toast Notification */}
      {toast && (
        <Toast
          message={toast.message}
          type={toast.type}
          duration={toast.duration}
          onClose={hideToast}
        />
      )}
    </div>
  )
}

export default FileEditorPage
