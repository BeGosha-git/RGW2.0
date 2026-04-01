from __future__ import annotations

import os
from typing import List, Optional


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, str(default)))
    except Exception:
        return float(default)


def candidate_api_ports() -> List[int]:
    """
    API/Web ports can differ across robots/PCs (port conflicts, different configs).
    Try a small set so updates work out-of-the-box.
    """
    ports: List[int] = []
    try:
        import services_manager

        ports.append(int(services_manager.get_api_port()))
    except Exception:
        pass
    ports += [5000, 5001, 5002, 5003, 5004, 5007, 5008]
    ports += [8080, 8081, 8082, 8083, 8084, 8085]
    out: List[int] = []
    seen = set()
    for p in ports:
        try:
            p = int(p)
        except Exception:
            continue
        if p not in seen:
            seen.add(p)
            out.append(p)
    return out


def timeout_version_check() -> float:
    return max(0.5, min(_env_float("RGW_NET_TIMEOUT_VERSION", 5.0), 30.0))


def timeout_version_refresh() -> float:
    return max(1.0, min(_env_float("RGW_NET_TIMEOUT_REFRESH", 30.0), 120.0))


def timeout_file_head() -> float:
    return max(0.5, min(_env_float("RGW_NET_TIMEOUT_HEAD", 5.0), 60.0))


def timeout_file_info() -> float:
    return max(0.5, min(_env_float("RGW_NET_TIMEOUT_INFO", 5.0), 60.0))


def timeout_file_download() -> float:
    # downloads can be larger; updater code may override anyway
    return max(1.0, min(_env_float("RGW_NET_TIMEOUT_DOWNLOAD", 60.0), 600.0))


def normalize_port(port: Optional[int]) -> Optional[int]:
    try:
        return int(port) if port is not None else None
    except Exception:
        return None

