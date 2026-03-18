import React, { useEffect, useRef, useState, useCallback } from 'react'
import { Terminal } from '@xterm/xterm'
import { FitAddon } from '@xterm/addon-fit'
import { WebLinksAddon } from '@xterm/addon-web-links'
import '@xterm/xterm/css/xterm.css'
import './TerminalPage.css'

// Fallback port — used only when the API is unreachable
const DEFAULT_WS_PORT = 8765

function TerminalPage() {
  const containerRef = useRef(null)
  const tabsRef = useRef([]) // [{ term, fitAddon, ws }]
  const [status, setStatus] = useState('connecting') // connecting | open | closed | error
  const [wsPort, setWsPort] = useState(null) // null = not yet fetched

  // ── Resolve the actual WebSocket port from the backend ────────────────────
  useEffect(() => {
    let cancelled = false
    const fetchPort = async () => {
      try {
        const resp = await fetch('/api/status/service/terminal')
        if (!resp.ok) throw new Error('status not ok')
        const data = await resp.json()
        const port = data?.port ?? DEFAULT_WS_PORT
        if (!cancelled) setWsPort(Number(port))
      } catch {
        if (!cancelled) setWsPort(DEFAULT_WS_PORT)
      }
    }
    fetchPort()
    return () => { cancelled = true }
  }, [])

  // ── Build WebSocket URL ────────────────────────────────────────────────────
  const getWsUrl = useCallback(() => {
    const port = wsPort ?? DEFAULT_WS_PORT
    const proto = window.location.protocol === 'https:' ? 'wss' : 'ws'
    return `${proto}://${window.location.hostname}:${port}`
  }, [wsPort])

  // ── Create terminal + WebSocket ───────────────────────────────────────────
  const createTab = useCallback((containerEl) => {
    const term = new Terminal({
      cursorBlink: true,
      fontSize: 14,
      fontFamily: "'JetBrains Mono', 'Fira Code', 'Cascadia Code', 'Consolas', 'Monaco', monospace",
      theme: {
        background: '#0d1117',
        foreground: '#e6edf3',
        cursor: '#58a6ff',
        cursorAccent: '#0d1117',
        selectionBackground: '#264f7840',
        black: '#484f58',
        red: '#ff7b72',
        green: '#3fb950',
        yellow: '#d29922',
        blue: '#58a6ff',
        magenta: '#bc8cff',
        cyan: '#39c5cf',
        white: '#b1bac4',
        brightBlack: '#6e7681',
        brightRed: '#ffa198',
        brightGreen: '#56d364',
        brightYellow: '#e3b341',
        brightBlue: '#79c0ff',
        brightMagenta: '#d2a8ff',
        brightCyan: '#56d4dd',
        brightWhite: '#f0f6fc',
      },
      allowProposedApi: true,
      scrollback: 5000,
    })

    const fitAddon = new FitAddon()
    term.loadAddon(fitAddon)
    term.loadAddon(new WebLinksAddon())
    term.open(containerEl)
    fitAddon.fit()

    const ws = new WebSocket(getWsUrl())
    ws.binaryType = 'arraybuffer'

    ws.onopen = () => {
      setStatus('open')
      ws.send(JSON.stringify({ type: 'resize', cols: term.cols, rows: term.rows }))
    }
    ws.onmessage = (e) => {
      term.write(e.data instanceof ArrayBuffer ? new Uint8Array(e.data) : e.data)
    }
    ws.onerror = () => setStatus('error')
    ws.onclose = () => {
      setStatus('closed')
      term.write('\r\n\x1b[31m[Соединение закрыто]\x1b[0m\r\n')
    }

    term.onData((data) => {
      if (ws.readyState === WebSocket.OPEN) ws.send(data)
    })
    term.onResize(({ cols, rows }) => {
      if (ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: 'resize', cols, rows }))
      }
    })

    return { term, fitAddon, ws }
  }, [getWsUrl])

  // ── Mount terminal once the port is known ─────────────────────────────────
  useEffect(() => {
    if (wsPort === null || !containerRef.current) return

    const tab = createTab(containerRef.current)
    tabsRef.current = [tab]
    setStatus('connecting')

    const ro = new ResizeObserver(() => {
      try { tab.fitAddon.fit() } catch (_) {}
    })
    ro.observe(containerRef.current)

    return () => {
      ro.disconnect()
      tabsRef.current.forEach(({ term, ws }) => { ws?.close(); term?.dispose() })
      tabsRef.current = []
    }
  }, [wsPort, createTab])

  // ── Reconnect ─────────────────────────────────────────────────────────────
  const reconnect = useCallback(() => {
    const tab = tabsRef.current[0]
    if (!tab) return
    tab.ws?.close()
    tab.term.write('\r\n\x1b[33m[Переподключение...]\x1b[0m\r\n')

    const ws = new WebSocket(getWsUrl())
    ws.binaryType = 'arraybuffer'
    ws.onopen = () => {
      setStatus('open')
      ws.send(JSON.stringify({ type: 'resize', cols: tab.term.cols, rows: tab.term.rows }))
    }
    ws.onmessage = (e) => {
      tab.term.write(e.data instanceof ArrayBuffer ? new Uint8Array(e.data) : e.data)
    }
    ws.onerror = () => setStatus('error')
    ws.onclose = () => {
      setStatus('closed')
      tab.term.write('\r\n\x1b[31m[Соединение закрыто]\x1b[0m\r\n')
    }
    tab.term.onData((data) => {
      if (ws.readyState === WebSocket.OPEN) ws.send(data)
    })
    tab.ws = ws
    setStatus('connecting')
  }, [getWsUrl])

  // ── Status badge ──────────────────────────────────────────────────────────
  const statusLabel = {
    connecting: { text: 'Подключение…', cls: 'status-connecting' },
    open: { text: 'Подключён', cls: 'status-open' },
    closed: { text: 'Отключён', cls: 'status-closed' },
    error: { text: 'Ошибка', cls: 'status-error' },
  }[status] ?? { text: status, cls: '' }

  return (
    <div className="terminal-page">
      <div className="page-header">
        <h1 className="page-title">Терминал</h1>
        <div className="terminal-header-right">
          <span className={`terminal-status-badge ${statusLabel.cls}`}>
            {statusLabel.text}
          </span>
          {(status === 'closed' || status === 'error') && (
            <button className="terminal-reconnect-btn" onClick={reconnect}>
              Переподключить
            </button>
          )}
        </div>
      </div>

      <div className="terminal-wrapper">
        <div ref={containerRef} className="terminal-xterm-container" />
      </div>
    </div>
  )
}

export default TerminalPage
