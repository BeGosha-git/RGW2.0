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
function WebRTCVideo({ signalingUrl, label, qualityMode = 'low', onDebug }) {
  const videoRef = useRef(null)
  const pcRef = useRef(null)
  const connIdRef = useRef(null)
  const closeUrlRef = useRef(null)
  const retryTimerRef = useRef(null)
  const [state, setState] = useState('connecting') // connecting | connected | error
  const [effectiveQuality, setEffectiveQuality] = useState(qualityMode)
  const [fps, setFps] = useState(null)
  const [captureFps, setCaptureFps] = useState(null)
  const [res, setRes] = useState({ w: null, h: null })
  const [net, setNet] = useState({ fps: null, lossPct: null, jitterMs: null })
  const lastQualityChangeRef = useRef(0)
  const goodStreakRef = useRef(0)

  useEffect(() => {
    setEffectiveQuality(qualityMode)
  }, [qualityMode])

  useEffect(() => {
    try {
      if (typeof onDebug === 'function') {
        const qPct = effectiveQuality === 'low' ? 30 : effectiveQuality === 'high' ? 100 : null
        const w = Number(res?.w || 0) || null
        const h = Number(res?.h || 0) || null
        const base = 1920 * 1080
        const resPct = w && h ? Math.max(1, Math.min(100, Math.round((w * h * 100) / base))) : null
        onDebug({
          state,
          quality: effectiveQuality,
          qualityPct: qPct,
          fps,
        captureFps,
          net,
          res: w && h ? { w, h } : null,
          resPct,
        })
      }
    } catch (_e) {}
  }, [state, effectiveQuality, fps, captureFps, net, res, onDebug])

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
      setCaptureFps(null)
      try {
        const pc = new RTCPeerConnection({ iceServers: [] })
        pcRef.current = pc

        pc.ontrack = (event) => {
          if (!cancelled && videoRef.current && event.streams[0]) {
            videoRef.current.srcObject = event.streams[0]
          // Best-effort: request small playout buffer (~0.5s) for realtime feel.
          try {
            const recvs = pc.getReceivers ? pc.getReceivers() : []
            for (const r of recvs) {
              if (r && r.track && r.track.kind === 'video' && 'playoutDelayHint' in r) {
                r.playoutDelayHint = 0.5
              }
            }
          } catch (_e) {}
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
            quality: effectiveQuality,
          }),
          signal: AbortSignal.timeout ? AbortSignal.timeout(15000) : undefined,
        })

        if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
        const data = await resp.json()
        if (!data.success) throw new Error(data.message || 'Signaling error')

        connIdRef.current = data.conn_id
        if (data.capture_fps != null) setCaptureFps(Number(data.capture_fps))
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
  }, [signalingUrl, effectiveQuality]) // reconnect when adaptive mode changes

  // Adaptive quality:
  // - On bad connection: downgrade to 'low' (server caps bitrate/FPS/res, keeps JPEG >=30%)
  // - When stable again: upgrade back to requested qualityMode
  useEffect(() => {
    if (state !== 'connected') return
    const pc = pcRef.current
    if (!pc || typeof pc.getStats !== 'function') return

    let cancelled = false
    let prev = { recv: 0, lost: 0, ts: 0, frames: 0 }

    const tick = async () => {
      if (cancelled) return
      const pc2 = pcRef.current
      if (!pc2) return
      try {
        const stats = await pc2.getStats()
        let inbound = null
        stats.forEach((r) => {
          if (r && r.type === 'inbound-rtp' && r.kind === 'video') inbound = r
        })
        if (!inbound) return
        const now = Number(inbound.timestamp || Date.now())
        const recv = Number(inbound.packetsReceived || 0)
        const lost = Number(inbound.packetsLost || 0)
        const jitter = Number(inbound.jitter || 0) // seconds
        const frames = Number(inbound.framesDecoded || inbound.framesReceived || 0)

        const dRecv = prev.ts ? Math.max(0, recv - prev.recv) : 0
        const dLost = prev.ts ? Math.max(0, lost - prev.lost) : 0
        const dtMs = prev.ts ? Math.max(1, now - prev.ts) : 0
        const dFrames = prev.ts ? Math.max(0, frames - prev.frames) : 0
        const fpsNet = prev.ts ? (dFrames * 1000) / dtMs : null
        prev = { recv, lost, ts: now, frames }

        const lossRate = dRecv + dLost > 0 ? dLost / (dRecv + dLost) : 0
        const poor = lossRate > 0.08 || jitter > 0.06
        const good = lossRate < 0.02 && jitter < 0.03

        setNet({
          fps: fpsNet != null ? Math.max(0, Math.min(120, fpsNet)) : null,
          lossPct: lossRate ? Math.max(0, Math.min(100, lossRate * 100)) : 0,
          jitterMs: jitter ? Math.max(0, jitter * 1000) : 0,
        })

        const tNow = Date.now()
        const cooldownOk = tNow - lastQualityChangeRef.current > 8000

        if (poor) {
          goodStreakRef.current = 0
          if (effectiveQuality !== 'low' && cooldownOk) {
            lastQualityChangeRef.current = tNow
            setEffectiveQuality('low')
          }
          return
        }

        if (good) {
          goodStreakRef.current += 1
          if (effectiveQuality === 'low' && qualityMode !== 'low' && goodStreakRef.current >= 3 && cooldownOk) {
            lastQualityChangeRef.current = tNow
            setEffectiveQuality(qualityMode)
            goodStreakRef.current = 0
          }
        } else {
          goodStreakRef.current = 0
        }
      } catch (_e) {}
    }

    const t = setInterval(tick, 2000)
    tick()
    return () => {
      cancelled = true
      clearInterval(t)
    }
  }, [state, effectiveQuality, qualityMode])

  // FPS estimate from the rendered video (best-effort).
  useEffect(() => {
    const v = videoRef.current
    if (!v) return
    if (typeof v.requestVideoFrameCallback !== 'function') return

    let cancelled = false
    let last = { t: 0, count: 0 }

    const cb = (_now, meta) => {
      if (cancelled) return
      try {
        if (v.videoWidth && v.videoHeight) setRes({ w: v.videoWidth, h: v.videoHeight })
      } catch (_e) {}
      const t = Number(meta?.expectedDisplayTime || performance.now())
      if (!last.t) {
        last = { t, count: 1 }
      } else {
        last.count += 1
        const dt = t - last.t
        if (dt >= 900) {
          const next = Math.max(0, (last.count * 1000) / dt)
          setFps(next)
          last = { t, count: 0 }
        }
      }
      try {
        v.requestVideoFrameCallback(cb)
      } catch (_e) {}
    }

    try {
      v.requestVideoFrameCallback(cb)
    } catch (_e) {}
    return () => {
      cancelled = true
    }
  }, [state, signalingUrl])

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
