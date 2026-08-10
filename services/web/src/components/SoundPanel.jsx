import React, { useState, useEffect, useCallback } from 'react'
import Card from './Card'
import './SoundPanel.css'

/**
 * Панель воспроизведения звука на Unitree G1.
 *
 * Позволяет:
 *  - воспроизвести предустановленный тон-подсказку;
 *  - проиграть сохранённый WAV-файл из data/sounds;
 *  - синтезировать и проиграть речь (TTS, требуется espeak на роботе);
 *  - загрузить свой WAV-файл в data/sounds;
 *  - остановить текущее воспроизведение.
 */
function SoundPanel() {
  const [info, setInfo] = useState(null)
  const [tones, setTones] = useState([])
  const [files, setFiles] = useState([])
  const [status, setStatus] = useState(null)
  const [loading, setLoading] = useState(false)
  const [playing, setPlaying] = useState(false)
  const [message, setMessage] = useState(null)
  const [messageType, setMessageType] = useState('info')
  const [speechText, setSpeechText] = useState('Привет! Я робот G1.')
  const [uploadFile, setUploadFile] = useState(null)

  const notify = useCallback((text, type = 'info') => {
    setMessage(text)
    setMessageType(type)
    if (typeof window !== 'undefined') {
      clearTimeout(window.__soundPanelMsgTimer)
      window.__soundPanelMsgTimer = setTimeout(() => setMessage(null), 4000)
    }
  }, [])

  const fetchInfo = useCallback(async () => {
    try {
      const resp = await fetch('/api/robot/g1/sound/info')
      const data = await resp.json()
      if (data.success) {
        setTones(data.tones || [])
        setFiles(data.files || [])
        setStatus(data.status || null)
      }
    } catch (e) {
      // тихо — робот может быть недоступен
    }
  }, [])

  useEffect(() => {
    fetchInfo()
    const timer = setInterval(fetchInfo, 8000)
    return () => clearInterval(timer)
  }, [fetchInfo])

  const runAction = async (path, body, okMsg) => {
    setLoading(true)
    try {
      const resp = await fetch(path, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body || {}),
      })
      const data = await resp.json()
      if (data.success) {
        setPlaying(true)
        notify(okMsg || data.message || 'ОК', 'success')
        setTimeout(() => fetchInfo(), 800)
      } else {
        notify(data.message || 'Ошибка', 'error')
      }
    } catch (e) {
      notify(`Ошибка запроса: ${e.message}`, 'error')
    } finally {
      setLoading(false)
    }
  }

  const playTone = (name) => runAction('/api/robot/g1/sound/play/tone', { name }, `Тон «${name}» отправлен`)
  const playFile = (filename) => runAction('/api/robot/g1/sound/play/file', { filename }, `Файл «${filename}» отправлен`)
  const stopSound = () => {
    setPlaying(false)
    runAction('/api/robot/g1/sound/stop', {}, 'Воспроизведение остановлено')
  }

  const speak = () => {
    const text = speechText.trim()
    if (!text) {
      notify('Введите текст для синтеза', 'error')
      return
    }
    runAction('/api/robot/g1/sound/play/speak', { text }, 'Речь отправлена')
  }

  const handleUpload = async () => {
    if (!uploadFile) {
      notify('Выберите WAV-файл', 'error')
      return
    }
    setLoading(true)
    try {
      const fd = new FormData()
      fd.append('file', uploadFile)
      fd.append('filename', uploadFile.name || 'sound.wav')
      const resp = await fetch('/api/robot/g1/sound/upload', { method: 'POST', body: fd })
      const data = await resp.json()
      if (data.success) {
        notify(`Файл загружен: ${data.filename}`, 'success')
        setUploadFile(null)
        fetchInfo()
      } else {
        notify(data.message || 'Ошибка загрузки', 'error')
      }
    } catch (e) {
      notify(`Ошибка загрузки: ${e.message}`, 'error')
    } finally {
      setLoading(false)
    }
  }

  return (
    <Card className="sound-panel status-card full-width" title="Звук на роботе (G1)" icon="🔊">
      <div className="sound-panel__body">
        {message && (
          <div className={`sound-msg sound-msg--${messageType}`}>{message}</div>
        )}

        {status?.initialized === false && (
          <div className="sound-msg sound-msg--warn">
            Звуковой модуль пока не инициализирован (DDS). Воспроизведение выполняется по запросу.
          </div>
        )}

        {/* Тоны */}
        <div className="sound-section">
          <div className="sound-section__title">Быстрые тоны</div>
          <div className="sound-tones">
            {(tones.length ? tones : [
              { name: 'beep' }, { name: 'success' }, { name: 'error' },
              { name: 'ding' }, { name: 'attention' }, { name: 'alert' },
            ]).map((t) => (
              <button
                key={t.name}
                className="sound-tone-btn"
                disabled={loading}
                onClick={() => playTone(t.name)}
                title={`Воспроизвести тон «${t.name}»`}
              >
                🔊 {t.name}
              </button>
            ))}
          </div>
        </div>

        {/* Файлы */}
        {files.length > 0 && (
          <div className="sound-section">
            <div className="sound-section__title">WAV-файлы (data/sounds)</div>
            <div className="sound-files">
              {files.map((f) => (
                <button
                  key={f.name}
                  className="sound-file-btn"
                  disabled={loading}
                  onClick={() => playFile(f.name)}
                  title={`Воспроизвести ${f.name} (${f.size} байт)`}
                >
                  ▶ {f.name}
                </button>
              ))}
            </div>
          </div>
        )}

        {/* TTS */}
        <div className="sound-section">
          <div className="sound-section__title">Синтез речи (TTS)</div>
          <div className="sound-speak">
            <input
              className="sound-speak__input"
              value={speechText}
              onChange={(e) => setSpeechText(e.target.value)}
              placeholder="Текст для произнесения на роботе"
              disabled={loading}
            />
            <button className="sound-speak__btn" onClick={speak} disabled={loading || !speechText.trim()}>
              ▶ Говорить
            </button>
          </div>
        </div>

        {/* Upload */}
        <div className="sound-section">
          <div className="sound-section__title">Загрузить WAV-файл</div>
          <div className="sound-upload">
            <input
              className="sound-upload__file"
              type="file"
              accept=".wav,audio/wav,audio/x-wav"
              onChange={(e) => setUploadFile(e.target.files?.[0] || null)}
            />
            <button className="sound-upload__btn" onClick={handleUpload} disabled={loading || !uploadFile}>
              ⬆ Загрузить
            </button>
          </div>
        </div>

        {/* Управление */}
        <div className="sound-controls">
          <button className="sound-controls__stop" onClick={stopSound} disabled={loading}>
            ⏹ Остановить
          </button>
          <span className={`sound-controls__state ${playing ? 'sound-controls__state--playing' : ''}`}>
            {playing ? '● воспроизведение' : '○ тишина'}
          </span>
        </div>
      </div>
    </Card>
  )
}

export default SoundPanel
