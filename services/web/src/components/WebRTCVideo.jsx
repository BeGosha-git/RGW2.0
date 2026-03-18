import React, { useState, useEffect, useRef } from 'react'
import './WebRTCVideo.css'

/**
 * Connects to a robot camera via WebRTC.
 *
 * signalingUrl — single relative/absolute URL for POST .../webrtc/offer.
 * Using a string (not array) ensures React compares by value and does NOT
 * re-trigger the effect on every parent render (arrays are compared by reference).
 *
 * qualityMode — 'low' (matrix/thumbnail view) | 'high' (fullscreen)
 */
function WebRTCVideo({ signalingUrl, label, qualityMode = 'low' }) {
  const videoRef = useRef(null)
  const pcRef = useRef(null)
  const connIdRef = useRef(null)
  const closeUrlRef = useRef(null)
  const retryTimerRef = useRef(null)
  const [state, setState] = useState('connecting') // connecting | connected | error

  useEffect(() => {
    if (!signalingUrl) {
      setState('error')
      return
    }

    let cancelled = false
    let retryDelay = 3000

    const cleanup = () => {
      if (retryTimerRef.current) { clearTimeout(retryTimerRef.current); retryTimerRef.current = null }
      if (pcRef.current) { pcRef.current.close(); pcRef.current = null }
      if (closeUrlRef.current) {
        fetch(closeUrlRef.current, { method: 'DELETE' }).catch(() => {})
        closeUrlRef.current = null
      }
    }

    const connect = async () => {
      if (cancelled) return
      setState('connecting')
      try {
        const pc = new RTCPeerConnection({ iceServers: [] })
        pcRef.current = pc

        pc.ontrack = (event) => {
          if (!cancelled && videoRef.current && event.streams[0]) {
            videoRef.current.srcObject = event.streams[0]
            setState('connected')
            retryDelay = 3000 // reset backoff on success
          }
        }

        pc.oniceconnectionstatechange = () => {
          if (cancelled) return
          const s = pc.iceConnectionState
          if (s === 'failed' || s === 'disconnected' || s === 'closed') {
            setState('error')
            if (!cancelled) {
              retryTimerRef.current = setTimeout(() => { if (!cancelled) connect() }, retryDelay)
              retryDelay = Math.min(retryDelay * 2, 30000)
            }
          }
        }

        // We only receive video
        pc.addTransceiver('video', { direction: 'recvonly' })

        const offer = await pc.createOffer()
        await pc.setLocalDescription(offer)

        // Wait briefly for ICE gathering.
        // For low-latency we DO NOT wait the full 4s; we cap it so
        // offer/answer exchange starts within ~1s on LAN/weak networks.
        await new Promise((resolve) => {
          if (pc.iceGatheringState === 'complete') { resolve(); return }
          const onStateChange = () => {
            if (pc.iceGatheringState === 'complete') {
              pc.removeEventListener('icegatheringstatechange', onStateChange)
              resolve()
            }
          }
          pc.addEventListener('icegatheringstatechange', onStateChange)
          setTimeout(resolve, 800) // 0.8s max wait on weak networks
        })

        if (cancelled) { pc.close(); pcRef.current = null; return }

        const resp = await fetch(signalingUrl, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            sdp: pc.localDescription.sdp,
            type: pc.localDescription.type,
            quality: qualityMode,
          }),
          signal: AbortSignal.timeout ? AbortSignal.timeout(15000) : undefined,
        })

        if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
        const data = await resp.json()
        if (!data.success) throw new Error(data.message || 'Signaling error')

        connIdRef.current = data.conn_id
        closeUrlRef.current = signalingUrl.replace(/\/offer$/, `/${data.conn_id}`)
        await pc.setRemoteDescription({ sdp: data.sdp, type: data.type })
      } catch (err) {
        if (!cancelled) {
          console.warn('[WebRTC]', label, err.message || err)
          setState('error')
          retryTimerRef.current = setTimeout(() => { if (!cancelled) connect() }, retryDelay)
          retryDelay = Math.min(retryDelay * 2, 30000)
        }
      }
    }

    connect()

    return () => {
      cancelled = true
      cleanup()
    }
  }, [signalingUrl, qualityMode]) // qualityMode — must reconnect when switching low/high

  return (
    <div className="camera-stream webrtc-stream">
      <video
        ref={videoRef}
        autoPlay
        playsInline
        muted
        style={{ width: '100%', display: state === 'connected' ? 'block' : 'none' }}
      />
      {state === 'connecting' && (
        <div className="camera-connecting">
          <span>WebRTC подключение…</span>
        </div>
      )}
      {state === 'error' && (
        <div className="camera-error">
          <span>Камера недоступна</span>
        </div>
      )}
    </div>
  )
}

export default WebRTCVideo
