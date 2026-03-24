"""
WebRTC handler for camera streams.

Uses aiortc to create RTCPeerConnections that carry a live video track
sourced from the existing CameraStream objects.

Architecture:
  - A single asyncio event loop runs in a background daemon thread (_webrtc_loop).
  - Flask routes call asyncio.run_coroutine_threadsafe() to submit work to the loop.
  - Each browser client creates one RTCPeerConnection via handle_offer().
  - Connections are tracked in _peers dict and cleaned up by close_peer() or GC.
"""
import asyncio
import fractions
import io
import logging
import os
import math
import threading
import time
import uuid
from typing import Dict, Optional, Tuple

logger = logging.getLogger(__name__)

# ── Lazy imports (aiortc / av are optional) ───────────────────────────────────
_aiortc_available = False
try:
    from aiortc import RTCPeerConnection, RTCSessionDescription, VideoStreamTrack
    from aiortc.contrib.media import MediaBlackhole
    import av
    _aiortc_available = True
except ImportError:
    logger.warning('[WebRTC] aiortc or av not installed — WebRTC unavailable. '
                   'Run: pip install aiortc av')

# ── Global asyncio loop ───────────────────────────────────────────────────────
_webrtc_loop: Optional[asyncio.AbstractEventLoop] = None
_webrtc_thread: Optional[threading.Thread] = None
_webrtc_start_lock = threading.Lock()
_webrtc_started_evt = threading.Event()
_peers: dict = {}          # conn_id → RTCPeerConnection
_peers_lock = threading.Lock()

VIDEO_CLOCK_RATE = 90000
VIDEO_TIME_BASE = fractions.Fraction(1, VIDEO_CLOCK_RATE)

# WebRTC tuning for:
#  - weak connection: prefer lowering FPS (down to RGW2_WEBRTC_FPS_MIN, default 20) before JPEG quality
#  - fullscreen: up to RGW2_WEBRTC_FPS_MAX (default 60)
#
# Bitrate constraint from user: "не более 8к" → interpret as ~8 Mbps.
MAX_BITRATE_CAP_BPS = 8_000_000

# Hard FPS bounds (adaptive path stays inside this range).
FPS_MIN = int(os.getenv("RGW2_WEBRTC_FPS_MIN", "20"))
FPS_MAX = int(os.getenv("RGW2_WEBRTC_FPS_MAX", "60"))
FPS_MIN = max(1, FPS_MIN)
FPS_MAX = max(FPS_MIN, FPS_MAX)

def _clamp_fps(v: int) -> int:
    return max(FPS_MIN, min(FPS_MAX, int(v)))


# Fullscreen / normal conditions
TARGET_FPS_HIGH = _clamp_fps(int(os.getenv("RGW2_WEBRTC_FPS_HIGH", os.getenv("RGW2_WEBRTC_FPS", "60"))))
JPEG_QUALITY_HIGH = int(os.getenv("RGW2_WEBRTC_JPEG_QUALITY_HIGH", os.getenv("RGW2_WEBRTC_JPEG_QUALITY", "70")))

# Keep FPS stable; do not exceed bitrate cap.
MAX_BITRATE_BPS_HIGH = int(os.getenv("RGW2_WEBRTC_MAX_BITRATE_BPS_HIGH",
                                    os.getenv("RGW2_WEBRTC_MAX_BITRATE_BPS", str(MAX_BITRATE_CAP_BPS))))
MAX_BITRATE_BPS_HIGH = min(MAX_BITRATE_BPS_HIGH, MAX_BITRATE_CAP_BPS)
MAX_FRAMERATE_HIGH = float(os.getenv("RGW2_WEBRTC_MAX_FRAMERATE_HIGH", str(TARGET_FPS_HIGH)))
MAX_FRAMERATE_HIGH = float(_clamp_fps(int(MAX_FRAMERATE_HIGH)))

# Output resolution (bandwidth control).
WEBRTC_WIDTH_HIGH = int(os.getenv("RGW2_WEBRTC_WIDTH_HIGH", os.getenv("RGW2_WEBRTC_WIDTH", "640")))
WEBRTC_HEIGHT_HIGH = int(os.getenv("RGW2_WEBRTC_HEIGHT_HIGH", os.getenv("RGW2_WEBRTC_HEIGHT", "480")))

VIDEO_RESYNC_SLEEP = float(os.getenv("RGW2_WEBRTC_RESYNC_SLEEP_SEC", "0.0"))  # optional debug knob

# Matrix / weak connection — start lower; under load we drop FPS toward FPS_MIN before JPEG quality.
TARGET_FPS_LOW = _clamp_fps(int(os.getenv("RGW2_WEBRTC_FPS_LOW", "30")))

# Require JPEG quality not below 30.
QUALITY_SCALE = 1.5
default_low_q = int(JPEG_QUALITY_HIGH / QUALITY_SCALE)
default_low_q = max(30, default_low_q)
JPEG_QUALITY_LOW = int(os.getenv("RGW2_WEBRTC_JPEG_QUALITY_LOW", str(default_low_q)))

MAX_BITRATE_BPS_LOW = int(os.getenv("RGW2_WEBRTC_MAX_BITRATE_BPS_LOW", str(MAX_BITRATE_BPS_HIGH)))
MAX_BITRATE_BPS_LOW = min(MAX_BITRATE_BPS_LOW, MAX_BITRATE_CAP_BPS)
MAX_FRAMERATE_LOW = float(os.getenv("RGW2_WEBRTC_MAX_FRAMERATE_LOW", str(TARGET_FPS_LOW)))
MAX_FRAMERATE_LOW = float(_clamp_fps(int(MAX_FRAMERATE_LOW)))

# Resolution scale so that bandwidth also drops with low quality.
# width/height scale = 1/sqrt(1.5) ~= 0.816
_wh_scale = 1.0 / math.sqrt(QUALITY_SCALE)
WEBRTC_WIDTH_LOW = int(
    os.getenv(
        "RGW2_WEBRTC_WIDTH_LOW",
        str(max(320, int(WEBRTC_WIDTH_HIGH * _wh_scale))),
    )
)
WEBRTC_HEIGHT_LOW = int(
    os.getenv(
        "RGW2_WEBRTC_HEIGHT_LOW",
        str(max(180, int(WEBRTC_HEIGHT_HIGH * _wh_scale))),
    )
)


# ── Video track ───────────────────────────────────────────────────────────────

def _build_fallback_jpeg(width: int, height: int) -> Optional[bytes]:
    """
    Create a dark-gray 640×480 'No Signal' JPEG used when the camera has no frame.
    Tries Pillow first (always available), falls back to OpenCV/numpy.
    Returns None only if both fail — in which case garbage fallback is avoided via
    a separately zeroed av.VideoFrame.
    """
    try:
        from PIL import Image, ImageDraw, ImageFont
        img = Image.new('RGB', (width, height), (18, 18, 18))
        draw = ImageDraw.Draw(img)
        text = 'Нет сигнала'
        try:
            w, h = draw.textlength(text), 20
        except Exception:
            w, h = len(text) * 10, 20
        draw.text(((width - w) / 2, (height - h) / 2), text, fill=(60, 60, 60))
        buf = io.BytesIO()
        img.save(buf, format='JPEG', quality=30)
        return buf.getvalue()
    except Exception:
        pass
    try:
        import numpy as np
        import cv2 as _cv2
        frame = np.full((height, width, 3), 18, dtype=np.uint8)
        _, buf = _cv2.imencode('.jpg', frame, [_cv2.IMWRITE_JPEG_QUALITY, 30])
        return bytes(buf)
    except Exception:
        return None


# Cached fallback JPEGs per output resolution.
_FALLBACK_JPEG_CACHE: Dict[Tuple[int, int], Optional[bytes]] = {}


def _get_fallback_jpeg(width: int, height: int) -> Optional[bytes]:
    key = (int(width), int(height))
    if key not in _FALLBACK_JPEG_CACHE:
        _FALLBACK_JPEG_CACHE[key] = _build_fallback_jpeg(width=key[0], height=key[1])
    return _FALLBACK_JPEG_CACHE[key]


def _jpeg_to_av_frame(jpeg_bytes: bytes) -> Optional[object]:
    """
    Decode JPEG bytes to an av.VideoFrame in yuv420p.

    Strategy (most reliable → least):
      1. numpy + cv2 (same stack that encoded the JPEG) → av.VideoFrame.from_ndarray
      2. av.open demux (original approach, fallback)
    Returns None on any failure.
    """
    # Strategy 1: numpy/cv2 (preferred — same codec that made the JPEG)
    try:
        import numpy as np
        import cv2 as _cv2
        buf = np.frombuffer(jpeg_bytes, dtype=np.uint8)
        bgr = _cv2.imdecode(buf, _cv2.IMREAD_COLOR)
        if bgr is not None:
            rgb = _cv2.cvtColor(bgr, _cv2.COLOR_BGR2RGB)
            frame = av.VideoFrame.from_ndarray(rgb, format='rgb24')
            return frame.reformat(format='yuv420p')
    except Exception as e:
        logger.debug('[WebRTC] cv2 decode error: %s', e)

    # Strategy 2: av demux (fallback for non-cv2 environments)
    try:
        container = av.open(io.BytesIO(jpeg_bytes))
        for packet in container.demux(video=0):
            for raw_frame in packet.decode():
                return raw_frame.reformat(format='yuv420p')
    except Exception as e:
        logger.debug('[WebRTC] av demux decode error: %s', e)

    return None


if _aiortc_available:
    class CameraVideoTrack(VideoStreamTrack):
        """
        A VideoStreamTrack that pulls JPEG frames from a CameraStream object
        and converts them to YUV420p av.VideoFrame for aiortc.
        """
        kind = 'video'

        def __init__(self, camera_stream, quality_mode: str = 'high'):
            super().__init__()
            self._cam = camera_stream
            self._pts = 0
            self._fps_floor = FPS_MIN
            if str(quality_mode).lower() == 'low':
                self._quality_mode = 'low'
                self._jpeg_quality = JPEG_QUALITY_LOW
                self._jpeg_quality_min = 30  # keep image quality >= 30%
                self._out_w = WEBRTC_WIDTH_LOW
                self._out_h = WEBRTC_HEIGHT_LOW
                self._target_fps = TARGET_FPS_LOW
                self._max_bitrate_bps = MAX_BITRATE_BPS_LOW
                # Matrix view: never auto-ramp above this FPS (saves bandwidth).
                self._fps_ceiling = TARGET_FPS_LOW
            else:
                self._quality_mode = 'high'
                self._jpeg_quality = JPEG_QUALITY_HIGH
                self._jpeg_quality_min = 30
                self._out_w = WEBRTC_WIDTH_HIGH
                self._out_h = WEBRTC_HEIGHT_HIGH
                self._target_fps = TARGET_FPS_HIGH
                self._max_bitrate_bps = MAX_BITRATE_BPS_HIGH
                self._fps_ceiling = TARGET_FPS_HIGH

            self._target_fps = _clamp_fps(int(self._target_fps))
            self._fps_ceiling = _clamp_fps(int(self._fps_ceiling))
            if self._fps_ceiling < self._target_fps:
                self._fps_ceiling = self._target_fps
            self._frame_interval = VIDEO_CLOCK_RATE // self._target_fps
            self._no_frame_count = 0  # consecutive misses — for logging
            self._last_emit_time = None  # monotonic timestamp for pacing

            # Simple bitrate guard:
            # adjust JPEG quality to keep avg bitrate <= cap (best-effort).
            self._bytes_acc = 0
            self._bitrate_last_ts = time.monotonic()
            self._bitrate_eval_period_s = 0.5
            self._jpeg_quality_cap = int(self._jpeg_quality)

        def _apply_target_fps(self, fps: int) -> None:
            """Update pacing + RTP clock step when adaptive FPS changes."""
            fps = max(self._fps_floor, min(self._fps_ceiling, int(fps)))
            if fps == self._target_fps:
                return
            self._target_fps = fps
            self._frame_interval = VIDEO_CLOCK_RATE // self._target_fps

        async def recv(self):
            loop = asyncio.get_event_loop()

            # Pull latest JPEG frame without waiting.
            # Waiting here adds latency when camera momentarily stalls.
            # Note: we may adjust self._jpeg_quality based on bitrate cap.
            jpeg_bytes = await loop.run_in_executor(
                None,
                lambda: self._cam.get_latest_frame(
                    quality=self._jpeg_quality,
                    wait=False,
                    width=self._out_w,
                    height=self._out_h,
                ),
            )

            av_frame: Optional[object] = None

            if jpeg_bytes:
                av_frame = _jpeg_to_av_frame(jpeg_bytes)
                # Bitrate estimation & quality adaptation (for weak connections).
                try:
                    self._bytes_acc += len(jpeg_bytes)
                    now = time.monotonic()
                    dt = now - self._bitrate_last_ts
                    if dt >= self._bitrate_eval_period_s:
                        bitrate_bps = (self._bytes_acc * 8) / dt
                        self._bytes_acc = 0
                        self._bitrate_last_ts = now

                        # Hysteresis: when over cap, lower FPS first (down to FPS_MIN), then JPEG quality.
                        # When under cap, raise FPS first (up to mode ceiling), then quality.
                        if bitrate_bps > self._max_bitrate_bps * 1.05:
                            if self._target_fps > self._fps_floor:
                                self._apply_target_fps(self._target_fps - 3)
                            else:
                                self._jpeg_quality = max(
                                    self._jpeg_quality_min, self._jpeg_quality - 5
                                )
                        elif bitrate_bps < self._max_bitrate_bps * 0.70:
                            if self._target_fps < self._fps_ceiling:
                                self._apply_target_fps(self._target_fps + 2)
                            else:
                                self._jpeg_quality = min(
                                    self._jpeg_quality_cap, self._jpeg_quality + 2
                                )
                except Exception:
                    pass
                if av_frame is None:
                    logger.debug('[WebRTC] All JPEG decode strategies failed (%d bytes)', len(jpeg_bytes))
                else:
                    if self._no_frame_count > 0:
                        logger.debug('[WebRTC] Camera resumed after %d missed frames', self._no_frame_count)
                    self._no_frame_count = 0

            if av_frame is None:
                self._no_frame_count += 1
                if self._no_frame_count == 1 or self._no_frame_count % 30 == 0:
                    logger.info('[WebRTC] No frame from camera (miss #%d) — sending fallback', self._no_frame_count)

                # Decode the pre-built dark-gray fallback JPEG
                fallback_jpeg = _get_fallback_jpeg(width=self._out_w, height=self._out_h)
                if fallback_jpeg:
                    av_frame = _jpeg_to_av_frame(fallback_jpeg)

                if av_frame is None:
                    # Absolute last resort: properly zeroed 640×480 frame
                    # (do NOT use av.VideoFrame(w, h, fmt) — its planes are uninitialized!)
                    try:
                        import numpy as np
                        black = np.zeros((self._out_h, self._out_w, 3), dtype=np.uint8)
                        av_frame = av.VideoFrame.from_ndarray(black, format='rgb24').reformat(format='yuv420p')
                    except Exception:
                        # Can't build a proper frame — skip this tick
                        av_frame = av.VideoFrame(width=self._out_w, height=self._out_h, format='yuv420p')

            av_frame.pts = self._pts
            av_frame.time_base = VIDEO_TIME_BASE
            self._pts += self._frame_interval

            # Pacing: one frame per target interval. If we are behind schedule, resync to "now"
            # instead of bursting frames (bursting grows queues and ICE/packet loss).
            if self._last_emit_time is None:
                self._last_emit_time = time.monotonic()
            else:
                interval = 1.0 / max(1, self._target_fps)
                next_time = self._last_emit_time + interval
                now = time.monotonic()
                sleep_for = next_time - now
                if sleep_for > 0:
                    await asyncio.sleep(sleep_for)
                    self._last_emit_time = next_time
                else:
                    self._last_emit_time = now
            return av_frame


# ── Asyncio event loop (background thread) ────────────────────────────────────

def _start_event_loop():
    global _webrtc_loop
    try:
        loop = asyncio.new_event_loop()
        _webrtc_loop = loop
        asyncio.set_event_loop(loop)
        logger.info('[WebRTC] asyncio event loop started')
        _webrtc_started_evt.set()
        loop.run_forever()
    except Exception as e:
        logger.exception('[WebRTC] event loop thread crashed: %s', e)
        _webrtc_started_evt.set()


def ensure_loop() -> Optional[asyncio.AbstractEventLoop]:
    """Start the WebRTC asyncio event loop thread if not running yet."""
    global _webrtc_thread, _webrtc_loop
    if _webrtc_loop is not None and _webrtc_loop.is_running():
        return _webrtc_loop

    with _webrtc_start_lock:
        # Another thread might have started it while we waited.
        if _webrtc_loop is not None and _webrtc_loop.is_running():
            return _webrtc_loop

        # If thread exists and is alive, just wait for the loop to become running.
        if _webrtc_thread is not None and _webrtc_thread.is_alive():
            pass
        else:
            _webrtc_started_evt.clear()
            _webrtc_thread = threading.Thread(target=_start_event_loop, daemon=True, name='webrtc-loop')
            _webrtc_thread.start()

    # Wait up to 3s for the loop to start & become running
    deadline = time.monotonic() + 3.0
    while time.monotonic() < deadline:
        if _webrtc_loop is not None and _webrtc_loop.is_running():
            return _webrtc_loop
        if _webrtc_started_evt.is_set() and (_webrtc_loop is None):
            break
        time.sleep(0.05)
    logger.error('[WebRTC] Failed to start event loop')
    return _webrtc_loop if _webrtc_loop and _webrtc_loop.is_running() else None


# ── Core coroutine ────────────────────────────────────────────────────────────

async def _handle_offer_async(camera_id: str, offer_sdp: str, offer_type: str, quality_mode: str) -> dict:
    """
    Create an RTCPeerConnection, attach a video track from the given camera,
    perform the offer/answer exchange, and return the SDP answer.
    """
    if not _aiortc_available:
        return {'success': False, 'message': 'aiortc not installed'}

    # Import here to avoid NameError when aiortc is unavailable
    from . import camera_stream as cs_module  # noqa

    # Get or start the camera stream.
    # If requested camera can't start, try other available cameras as fallback.
    # start_camera_stream() calls detect_cameras() which scans /dev/video0-9 — that
    # can take 0.5–1.5 s. Running it in an executor prevents event-loop stalls.
    loop = asyncio.get_event_loop()
    requested_camera_id = camera_id
    stream_obj = cs_module.get_camera_stream(camera_id)
    if stream_obj is None:
        started = await loop.run_in_executor(None, lambda: cs_module.start_camera_stream(camera_id))
        if started:
            stream_obj = cs_module.get_camera_stream(camera_id)

    if stream_obj is None:
        cameras = cs_module.detect_cameras()
        fallback_ids = []
        for cam in cameras:
            cid = cam.get("id")
            if not cid or cid == requested_camera_id:
                continue
            if not cam.get("available", True):
                continue
            fallback_ids.append(cid)

        for candidate_id in fallback_ids:
            started = await loop.run_in_executor(None, lambda cid=candidate_id: cs_module.start_camera_stream(cid))
            if not started:
                continue
            stream_obj = cs_module.get_camera_stream(candidate_id)
            if stream_obj is not None:
                camera_id = candidate_id
                logger.info("[WebRTC] fallback camera selected: requested=%s selected=%s", requested_camera_id, camera_id)
                break

    if stream_obj is None:
        return {'success': False, 'message': f"Camera '{requested_camera_id}' not found or failed to start"}

    conn_id = str(uuid.uuid4())
    pc = RTCPeerConnection()

    quality_mode_l = str(quality_mode).lower()
    if quality_mode_l == 'low':
        dbg_target_fps = TARGET_FPS_LOW
        dbg_jpeg_q = JPEG_QUALITY_LOW
        dbg_w = WEBRTC_WIDTH_LOW
        dbg_h = WEBRTC_HEIGHT_LOW
        dbg_bitrate_cap = MAX_BITRATE_BPS_LOW
    else:
        dbg_target_fps = TARGET_FPS_HIGH
        dbg_jpeg_q = JPEG_QUALITY_HIGH
        dbg_w = WEBRTC_WIDTH_HIGH
        dbg_h = WEBRTC_HEIGHT_HIGH
        dbg_bitrate_cap = MAX_BITRATE_BPS_HIGH

    logger.info(
        '[WebRTC] offer camera=%s mode=%s target_fps=%s jpeg_quality=%s out=%sx%s bitrate_cap_bps=%s conn=%s',
        camera_id, quality_mode_l, dbg_target_fps, dbg_jpeg_q, dbg_w, dbg_h, dbg_bitrate_cap, conn_id[:8]
    )

    track = CameraVideoTrack(stream_obj, quality_mode=quality_mode)
    sender = pc.addTrack(track)

    # Tune sender for low-latency / weak connections.
    # aiortc codec/parameter support depends on version; all tuning is best-effort.
    try:
        params = sender.getParameters()
        if params and getattr(params, "encodings", None):
            quality_mode_l = str(quality_mode).lower()
            max_bitrate = MAX_BITRATE_BPS_LOW if quality_mode_l == 'low' else MAX_BITRATE_BPS_HIGH
            max_framerate = MAX_FRAMERATE_LOW if quality_mode_l == 'low' else MAX_FRAMERATE_HIGH
            for enc in params.encodings:
                enc.maxBitrate = max_bitrate
                enc.maxFramerate = max_framerate
            # setParameters can be async depending on aiortc version
            maybe_coro = sender.setParameters(params)
            if asyncio.iscoroutine(maybe_coro):
                await maybe_coro
    except Exception as e:
        logger.debug('[WebRTC] sender parameter tuning skipped: %s', e)

    @pc.on('connectionstatechange')
    async def on_state_change():
        state = pc.connectionState
        logger.info('[WebRTC] %s connection state: %s', conn_id[:8], state)
        if state in ('failed', 'closed', 'disconnected'):
            await _close_peer_async(conn_id)

    with _peers_lock:
        _peers[conn_id] = pc

    try:
        offer = RTCSessionDescription(sdp=offer_sdp, type=offer_type)
        await pc.setRemoteDescription(offer)
        answer = await pc.createAnswer()
        await pc.setLocalDescription(answer)

        return {
            'success': True,
            'conn_id': conn_id,
            'camera_id': camera_id,
            'requested_camera_id': requested_camera_id,
            'sdp': pc.localDescription.sdp,
            'type': pc.localDescription.type,
        }
    except Exception as e:
        logger.exception('[WebRTC] handle_offer error for %s', camera_id)
        await _close_peer_async(conn_id)
        return {'success': False, 'message': str(e)}


async def _close_peer_async(conn_id: str):
    with _peers_lock:
        pc = _peers.pop(conn_id, None)
    if pc is not None:
        try:
            await pc.close()
        except Exception:
            pass


# ── Public synchronous API (called from Flask routes) ─────────────────────────

def handle_offer(
    camera_id: str,
    offer_sdp: str,
    offer_type: str = 'offer',
    quality_mode: str = 'high',
) -> dict:
    """
    Called from a Flask route (sync context).
    Submits the offer to the asyncio loop and waits for the answer.
    """
    if not _aiortc_available:
        return {'success': False, 'message': 'aiortc not installed on this robot'}

    loop = ensure_loop()
    if loop is None:
        return {'success': False, 'message': 'WebRTC event loop unavailable'}

    future = asyncio.run_coroutine_threadsafe(
        _handle_offer_async(camera_id, offer_sdp, offer_type, quality_mode),
        loop,
    )
    try:
        return future.result(timeout=20)
    except Exception as e:
        logger.exception('[WebRTC] handle_offer timeout/error')
        return {'success': False, 'message': str(e)}


def close_peer(conn_id: str) -> dict:
    """Close a specific peer connection."""
    loop = ensure_loop()
    if loop is None:
        return {'success': False, 'message': 'Event loop unavailable'}

    future = asyncio.run_coroutine_threadsafe(
        _close_peer_async(conn_id),
        loop,
    )
    try:
        future.result(timeout=5)
        return {'success': True}
    except Exception as e:
        return {'success': False, 'message': str(e)}


def get_active_connections() -> list:
    """Return list of active connection IDs (for status/debug)."""
    with _peers_lock:
        return list(_peers.keys())
