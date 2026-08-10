"""
Растровый JPEG с вида окна Viser (ClientHandle.get_render), не проекция NumPy/OpenCV.

Нужен подключённый клиент браузера к тому же ViserServer — рендер выполняется на стороне клиента.
"""

from __future__ import annotations

import io
import threading
import time
from typing import Any, List, Optional

import numpy as np
from PIL import Image


class ViserRenderStream:
    """
    Совместим с webrtc CameraVideoTrack: get_latest_frame(width=, height=, quality=, wait=) -> jpeg bytes.
    """

    def __init__(self, base_width: int = 640, base_height: int = 480):
        self.base_width = int(base_width)
        self.base_height = int(base_height)
        self._servers: List[Any] = []
        self._client: Any = None
        self._lock = threading.Lock()
        self._warned_no_client = False
        self._frame_id = 0

    def attach_server(self, server: Any) -> None:
        with self._lock:
            if server not in self._servers:
                self._servers.append(server)

        @server.on_client_connect
        def _on_connect(client: Any) -> None:
            with self._lock:
                self._client = client
            print("[ViserRenderStream] клиент Viser подключён — WebRTC: растр с вида 3D-окна", flush=True)

        @server.on_client_disconnect
        def _on_disconnect(client: Any) -> None:
            with self._lock:
                if self._client is client:
                    self._client = None

    def _active_client(self) -> Any:
        with self._lock:
            c = self._client
        if c is not None:
            return c
        with self._lock:
            srvs = list(self._servers)
        for srv in srvs:
            if srv is None:
                continue
            try:
                clients = srv.get_clients()
                if not clients:
                    continue
                return next(iter(clients.values()))
            except Exception:
                continue
        return None

    def get_latest_frame(
        self,
        width: int = None,
        height: int = None,
        quality: int = 80,
        wait: bool = True,
    ) -> Optional[bytes]:
        client = self._active_client()
        if client is None:
            if wait:
                time.sleep(0.08)
                client = self._active_client()
            if client is None:
                if not self._warned_no_client:
                    self._warned_no_client = True
                    print(
                        "[ViserRenderStream] нет клиента Viser — откройте страницу Viser в браузере "
                        "или будет запасной рендер (2D-проекция).",
                        flush=True,
                    )
                return None

        w = int(width) if width is not None else self.base_width
        h = int(height) if height is not None else self.base_height
        w = max(160, min(4096, w))
        h = max(120, min(4096, h))
        qv = max(30, min(95, int(quality)))

        try:
            # JPEG по транспорту: меньше трафик клиент→сервер; на выходе всё равно RGB uint8 (см. доку viser).
            try:
                arr = client.get_render(height=h, width=w, transport_format="jpeg")
            except TypeError:
                arr = client.get_render(height=h, width=w)
        except Exception as e:
            if not self._warned_no_client:
                print(f"[ViserRenderStream] get_render: {e}", flush=True)
            return None

        if arr is None:
            return None
        img = np.asarray(arr)
        if img.ndim != 3 or img.shape[2] < 3:
            return None
        rgb = img[:, :, :3].astype(np.uint8, copy=False)
        try:
            pil_im = Image.fromarray(rgb, mode="RGB")
            if pil_im.size != (w, h):
                pil_im = pil_im.resize((w, h), Image.Resampling.BILINEAR)
            buf = io.BytesIO()
            pil_im.save(buf, format="JPEG", quality=qv)
            self._frame_id = (self._frame_id + 1) & 0x7FFFFFFF
            return buf.getvalue()
        except Exception:
            return None

    def get_capture_fps(self) -> float:
        return 0.0


class ChainedPreviewStream:
    """Сначала primary (Viser), при отсутствии кадра — fallback (например WorldPreviewStream)."""

    def __init__(self, primary: Any, fallback: Any) -> None:
        self._primary = primary
        self._fallback = fallback

    def get_latest_frame(
        self,
        width: int = None,
        height: int = None,
        quality: int = 80,
        wait: bool = True,
    ) -> Optional[bytes]:
        j = self._primary.get_latest_frame(
            width=width, height=height, quality=quality, wait=wait
        )
        if j:
            return j
        return self._fallback.get_latest_frame(
            width=width, height=height, quality=quality, wait=wait
        )

    def get_capture_fps(self) -> Optional[float]:
        for obj in (self._primary, self._fallback):
            fn = getattr(obj, "get_capture_fps", None)
            if callable(fn):
                try:
                    v = float(fn())
                    if v > 0.0:
                        return v
                except Exception:
                    pass
        return None

    def stop(self) -> None:
        fn = getattr(self._fallback, "stop", None)
        if callable(fn):
            fn()
