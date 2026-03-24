"""
Universal WebRTC service.
Chooses a valid camera stream source based on robot type profile.
"""
import json
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import services_manager
import status
from services.camera_stream.camera_stream import (
    detect_cameras,
    get_all_streams,
    get_camera_stream,
    start_camera_stream,
)

SERVICE_NAME = "webrtc"

ROBOT_CAMERA_PRIORITY = {
    "G": ["realsense_0", "usb_2", "usb_0", "usb_1", "usb_3"],
    "G1": ["realsense_0", "usb_2", "usb_0", "usb_1", "usb_3"],
    "H": ["realsense_0", "usb_0", "usb_1", "usb_2", "usb_3"],
    "H1": ["realsense_0", "usb_0", "usb_1", "usb_2", "usb_3"],
}


def _load_robot_type() -> str:
    settings_path = Path(__file__).resolve().parents[2] / "data" / "settings.json"
    try:
        data = json.loads(settings_path.read_text(encoding="utf-8"))
        return str(data.get("RobotType", "G")).upper()
    except Exception:
        return "G"


def _priority(robot_type: str) -> List[str]:
    return ROBOT_CAMERA_PRIORITY.get(robot_type.upper(), ROBOT_CAMERA_PRIORITY["G"])


def _default_udp_port(camera_id: str) -> int:
    if camera_id.startswith("realsense_"):
        return 5006
    if camera_id.startswith("usb_"):
        try:
            idx = int(camera_id.split("_", 1)[1])
            return 5005 + max(0, min(idx, 3))
        except Exception:
            return 5005
    return 5005


def resolve_primary_camera(robot_type: Optional[str] = None) -> Tuple[Optional[str], List[Dict]]:
    rt = (robot_type or _load_robot_type()).upper()
    cameras = detect_cameras()
    available = {c.get("id") for c in cameras}
    for cid in _priority(rt):
        if cid in available:
            return cid, cameras
    if cameras:
        return cameras[0].get("id"), cameras
    return None, cameras


def ensure_robot_stream(robot_type: Optional[str] = None) -> Dict:
    rt = (robot_type or _load_robot_type()).upper()
    cameras = detect_cameras()
    if not cameras:
        return {"ok": False, "camera_id": None, "message": "No cameras detected", "cameras": cameras}
    camera_ids_available = {c.get("id") for c in cameras}
    candidates = [cid for cid in _priority(rt) if cid in camera_ids_available]
    if not candidates:
        candidates = [c.get("id") for c in cameras if c.get("id")]

    stream = None
    camera_id = None
    for candidate_id in candidates:
        camera_id = candidate_id
        stream = get_camera_stream(candidate_id)
        if stream:
            break
        if start_camera_stream(candidate_id, udp_port=_default_udp_port(candidate_id)):
            stream = get_camera_stream(candidate_id)
            if stream:
                break
    if not stream or not camera_id:
        return {"ok": False, "camera_id": None, "message": "Failed to start any camera stream", "cameras": cameras}

    frame_ok = False
    try:
        frame = stream.get_latest_frame(quality=70, wait=True) if stream else None
        frame_ok = bool(frame)
    except Exception:
        frame_ok = False

    return {
        "ok": True,
        "camera_id": camera_id,
        "robot_type": rt,
        "frame_ok": frame_ok,
        "streams": get_all_streams(),
        "cameras": cameras,
    }


def run():
    manager = services_manager.get_services_manager()
    started_at = time.time()
    while True:
        try:
            service = manager.get_service(SERVICE_NAME)
            service_status = service.get("status", "ON")
            if service_status == "OFF":
                status.unregister_service_data(SERVICE_NAME)
                break
            if service_status == "SLEEP":
                time.sleep(1)
                continue
            params = manager.get_service_parameters(SERVICE_NAME)
            robot_type = str(params.get("robot_type") or _load_robot_type()).upper()
            probe_interval = int(params.get("probe_interval", 5))
            data = ensure_robot_stream(robot_type=robot_type)
            status.register_service_data(SERVICE_NAME, {"status": "running", "started_at": started_at, **data})
            time.sleep(max(1, probe_interval))
        except KeyboardInterrupt:
            status.unregister_service_data(SERVICE_NAME)
            break
        except Exception as exc:
            status.register_service_data(SERVICE_NAME, {"status": "error", "error": str(exc), "timestamp": time.time()})
            time.sleep(1)


if __name__ == "__main__":
    run()
