import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Optional, Callable, Tuple, Set

import api.robot as robot_api
import api.network_api as network_api_module
import status as status_module
import services_manager


_scenario_jobs: Dict[str, Dict[str, Any]] = {}
_scenario_jobs_lock = threading.Lock()
_scenario_inflight_keys: Set[str] = set()
_scenario_inflight_lock = threading.Lock()

_network_api = network_api_module.NetworkAPI()

try:
    _WEB_PORT = services_manager.get_web_port()
except Exception:
    _WEB_PORT = 8080

def _self_id_for_remote(page_host: Optional[str]) -> str:
    try:
        st = status_module.get_robot_status() or {}
        net = st.get("network") or {}
        ip = str(net.get("interface_ip") or net.get("local_ip") or "").strip()
        return ip or (str(page_host).strip() if page_host else "LOCAL")
    except Exception:
        return str(page_host).strip() if page_host else "LOCAL"


def _flatten_program(program: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for b in (program or []):
        if not isinstance(b, dict):
            continue
        t = str(b.get("type") or "").strip()
        if t in ("command", "delay", "stop", "continue", "abort", "and", "or"):
            out.append(b)
        elif t == "parallel" and isinstance(b.get("items"), list):
            # минимальная совместимость: разворачиваем параллель в последовательность
            for it in b.get("items") or []:
                if isinstance(it, dict) and (it.get("commandId") or it.get("command")):
                    out.append({"type": "command", **it})
        else:
            continue
    return out


def _build_distributed_steps(
    program: List[Dict[str, Any]],
    commands_map: Dict[str, Any],
    local_ips_norm: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    steps: List[Dict[str, Any]] = []
    for b in _flatten_program(program):
        t = str(b.get("type") or "").strip()
        if t == "delay":
            steps.append({"type": "delay", "ms": int(b.get("ms") or 0)})
            continue
        if t in ("stop", "continue", "abort", "and", "or"):
            steps.append({"type": t})
            continue
        if t == "command":
            cmd_id = str(b.get("commandId") or "").strip()
            cmd_entry = commands_map.get(cmd_id) if cmd_id else None
            cmd = (cmd_entry.get("command") if isinstance(cmd_entry, dict) else None) or cmd_id or str(b.get("command") or "").strip()
            args = (cmd_entry.get("args") if isinstance(cmd_entry, dict) else None) or b.get("args") or []
            raw_target_ips = b.get("targetIps", None)
            target_ips: Optional[List[str]] = None
            if raw_target_ips is None:
                target_ips = None
            else:
                if isinstance(raw_target_ips, list):
                    items = [str(x).strip() for x in raw_target_ips if str(x).strip()]
                else:
                    items = [str(raw_target_ips).strip()]

                # Если пришёл алиас LOCAL, разворачиваем в реальные IP диспетчера.
                if "LOCAL" in items:
                    replace_with = list(local_ips_norm) if local_ips_norm else []
                    items = [x for x in items if x != "LOCAL"] + replace_with
                # Дедупликация: IP мог уже присутствовать до замены LOCAL
                seen_ips: set = set()
                deduped: List[str] = []
                for ip in items:
                    if ip not in seen_ips:
                        seen_ips.add(ip)
                        deduped.append(ip)
                target_ips = deduped
            steps.append(
                {
                    "type": "command",
                    "commandId": cmd_id,
                    "command": cmd,
                    "args": args if isinstance(args, list) else [args],
                    "delayBeforeMs": int(b.get("delayBeforeMs") or 0),
                    "delayAfterMs": int(b.get("delayAfterMs") or 0),
                    "targetIps": target_ips,
                    "waitContinue": bool(b.get("waitContinue") or False),
                    "useGo": bool(b.get("useGo") or False),
                }
            )
            continue
    return steps


def _run_distributed_dispatch_job(job_id: str, job_key: Optional[str], button: Dict[str, Any], page_host: Optional[str], local_ips: Optional[List[str]]) -> None:
    try:
        program = _normalize_program_from_button(button)
        raw_targets = _normalize_target_list(button)
        local_ips_norm = [str(x).strip() for x in (local_ips or []) if str(x).strip()]

        # LOCAL → заменяем на реальные IP (local_ips_norm или self_id).
        # LOCAL больше не используется как псевдоним для локального агента — только реальные IP.
        should_load_local_agent = False
        self_id = _self_id_for_remote(page_host)
        _local_expand = local_ips_norm if local_ips_norm else ([self_id] if self_id and self_id != "LOCAL" else [])
        if "LOCAL" in raw_targets:
            _raw = [t for t in raw_targets if t != "LOCAL"] + _local_expand
        else:
            _raw = list(raw_targets)
        # Дедупликация targets (сохраняем порядок), убираем оставшиеся LOCAL
        _seen_t: set = set()
        targets: List[str] = []
        for _t in _raw:
            _t = str(_t).strip()
            if not _t or _t == "LOCAL" or _t in _seen_t:
                continue
            _seen_t.add(_t)
            targets.append(_t)

        try:
            print(
                f"[SCENARIO_RUNNER] job={job_id} raw_targets={raw_targets} local_ips={local_ips_norm} targets={targets} load_local={should_load_local_agent}",
                flush=True,
            )
        except Exception:
            pass

        _set_job_patch(job_id, {"status": "running"})
        _set_job_progress(job_id, {"phase": "dispatch", "message": "Рассылка сценария роботам..."})

        # commands map from local api
        try:
            cmds = robot_api.RobotAPI.get_commands() or {}
            commands_map = {c.get("id"): c for c in (cmds.get("commands") or []) if isinstance(c, dict) and c.get("id")}
        except Exception:
            commands_map = {}

        steps = _build_distributed_steps(program, commands_map, local_ips_norm=local_ips_norm)
        scenario_id = str(job_key or button.get("id") or job_id)

        # Собираем всех участников: button.targetIps + все IP из шагов программы.
        # Шаги могут содержать отдельные IP которых нет в button.targetIps.
        _step_ips: set = set()
        for _s in steps:
            for _ip in (_s.get("targetIps") or []):
                _ip = str(_ip).strip()
                if _ip and _ip != "LOCAL":
                    _step_ips.add(_ip)

        _all_candidates_seen: set = set()
        _all_candidates: List[str] = []
        for _t in list(targets) + list(_step_ips):
            _t = str(_t).strip()
            if _t and _t != "LOCAL" and _t not in _all_candidates_seen:
                _all_candidates_seen.add(_t)
                _all_candidates.append(_t)

        remote_candidates: List[str] = _all_candidates
        local_requested = should_load_local_agent

        try:
            if _step_ips - set(targets):
                print(f"[SCENARIO_RUNNER] extra step IPs added to candidates: {_step_ips - set(targets)}", flush=True)
        except Exception:
            pass

        # load (1-й проход): узнаём кто доступен
        reachable: List[str] = []
        load_errors: List[str] = []
        for t in remote_candidates:
            payload = {"scenarioId": scenario_id, "steps": steps, "peers": [], "selfId": t}
            res = _network_api.send_data(t, "/api/robot/scenario/load", payload, timeout=15, port=_WEB_PORT)
            ok = bool(res and res.get("success"))
            remote_ok = bool(isinstance(res, dict) and isinstance(res.get("response"), dict) and res.get("response", {}).get("success"))
            if ok and remote_ok:
                reachable.append(t)
            else:
                load_errors.append(f"{t}: {str((res or {}).get('message') or (res or {}).get('response') or 'load failed')}")
            try:
                print(f"[SCENARIO_RUNNER] load to {t}: ok={ok} remote_ok={remote_ok} res={res}", flush=True)
            except Exception:
                pass

        # load (2-й проход): теперь знаем полный список участников → передаём корректные peers
        loaded_remote: List[str] = []
        for t in reachable:
            peers = [x for x in reachable if x != t]
            payload = {"scenarioId": scenario_id, "steps": steps, "peers": peers, "selfId": t}
            res = _network_api.send_data(t, "/api/robot/scenario/load", payload, timeout=15, port=_WEB_PORT)
            ok = bool(res and res.get("success"))
            remote_ok = bool(isinstance(res, dict) and isinstance(res.get("response"), dict) and res.get("response", {}).get("success"))
            if ok and remote_ok:
                loaded_remote.append(t)
            else:
                load_errors.append(f"{t} (2nd pass): {str((res or {}).get('message') or 'load failed')}")
            try:
                print(f"[SCENARIO_RUNNER] load(2nd pass) to {t}: ok={ok} remote_ok={remote_ok} res={res}", flush=True)
            except Exception:
                pass

        # start
        started_remote: List[str] = []
        start_errors: List[str] = []
        for t in loaded_remote:
            res = _network_api.send_data(
                t, "/api/robot/scenario/start", {"scenarioId": scenario_id}, timeout=8, port=_WEB_PORT
            )
            ok = bool(res and res.get("success"))
            remote_ok = bool(isinstance(res, dict) and isinstance(res.get("response"), dict) and res.get("response", {}).get("success"))
            try:
                print(f"[SCENARIO_RUNNER] start to {t}: ok={ok} remote_ok={remote_ok} res={res}", flush=True)
            except Exception:
                pass
            if ok and remote_ok:
                started_remote.append(t)
            else:
                start_errors.append(f"{t}: {str((res or {}).get('message') or (res or {}).get('response') or 'start failed')}")

        started_count = len(started_remote)
        total_candidates = len(remote_candidates)
        if started_count <= 0:
            unreachable = [e.split(":")[0].strip() for e in load_errors if "No response" in e or "load failed" in e]
            if unreachable and not [e for e in load_errors if "No response" not in e and "load failed" not in e]:
                raise RuntimeError(
                    f"Роботы недоступны: {', '.join(unreachable)}. "
                    f"Проверь IP-адреса в настройках кнопки — возможно они устарели."
                )
            details = "; ".join(load_errors + start_errors)[:1200]
            raise RuntimeError(f"Ни один исполнитель сценария не запущен. {details}")

        skipped = max(0, total_candidates - started_count)
        msg = f"Сценарий запущен на {started_count} исполнителях"
        if skipped:
            msg += f" (пропущено: {skipped})"
        _set_job_progress(job_id, {"phase": "dispatch", "message": msg, "started": started_count, "skipped": skipped})
        _set_job_patch(job_id, {"status": "done", "finished_at": time.time()})
    except Exception as e:
        _set_job_patch(job_id, {"status": "error", "finished_at": time.time(), "error": str(e)})
        _set_job_progress(job_id, {"phase": "dispatch", "message": f"Ошибка рассылки: {str(e)}"})
    finally:
        if job_key:
            with _scenario_inflight_lock:
                _scenario_inflight_keys.discard(job_key)


def _normalize_program_from_button(button: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Нормализация как в frontend:
    - если есть button.program — используем
    - иначе если есть button.commandId — делаем single command block
    """
    prog = button.get("program")
    if isinstance(prog, list) and len(prog) > 0:
        return prog

    command_id = button.get("commandId")
    if command_id:
        return [
            {
                "type": "command",
                "id": "legacy",
                "commandId": command_id,
                "delayBeforeMs": 0,
                "delayAfterMs": 0,
                "targetIps": None,
            }
        ]

    return []


def _normalize_target_list(button: Dict[str, Any]) -> List[str]:
    raw = button.get("targetIps")
    if raw is None:
        raw = button.get("targetIp")
    if raw is None:
        return ["LOCAL"]

    if isinstance(raw, list):
        items = raw
    else:
        items = [raw]

    out = []
    seen = set()
    for t in items:
        s = str(t).strip()
        if not s:
            continue
        if s in seen:
            continue
        seen.add(s)
        out.append(s)
    return out or ["LOCAL"]


def _infer_network_timeout(cmd_id: Optional[str], cmd_entry: Optional[Dict[str, Any]]) -> Optional[int]:
    if not cmd_id or not cmd_entry:
        return None
    if cmd_id in ("update_system", "force_update_system"):
        return 300

    command = str(cmd_entry.get("command") or "").strip()
    args = cmd_entry.get("args") or []
    if command == "python3" and any(("upgrade.py" in str(a)) or ("update.py" in str(a)) for a in args if a is not None):
        return 300
    return None


def _build_is_local_target(local_ips: Optional[List[str]], page_host: Optional[str]) -> Callable[[str], bool]:
    st = {}
    try:
        st = status_module.get_robot_status() or {}
    except Exception:
        st = {}

    net = st.get("network") or {}
    hostname = str(net.get("hostname") or "").strip()
    local_ip = str(net.get("local_ip") or "").strip()
    interface_ip = str(net.get("interface_ip") or "").strip()

    local_set = set()
    for ip in (local_ips or []):
        s = str(ip).strip()
        if s:
            local_set.add(s)
    for ip in (local_ip, interface_ip, hostname):
        if ip:
            local_set.add(ip)

    page_host = (str(page_host).strip() if page_host is not None else "").strip()
    page_host_bracketed = f"[{page_host}]" if page_host else ""

    def is_local_target(target: str) -> bool:
        t = str(target).strip()
        if not t:
            return False
        if t == "LOCAL":
            return True
        if t in local_set:
            return True
        if page_host and (t == page_host or t == page_host_bracketed):
            return True
        return False

    return is_local_target


def _set_job_patch(job_id: str, patch: Dict[str, Any]) -> None:
    with _scenario_jobs_lock:
        job = _scenario_jobs.get(job_id)
        if not job:
            return
        job.update(patch)


def _set_job_progress(job_id: str, progress: Dict[str, Any]) -> None:
    _set_job_patch(job_id, {"progress": progress, "last_update_at": time.time()})


def _normalize_delay_ms(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except Exception:
        return 0


def _run_command_on_targets(
    *,
    cmd_id: str,
    cmd_entry: Dict[str, Any],
    targets: List[str],
    is_local_target: Callable[[str], bool],
) -> None:
    payload = {"command": cmd_entry.get("command"), "args": cmd_entry.get("args") or []}
    if not payload["command"]:
        raise RuntimeError(f"Command entry '{cmd_id}' has no 'command'")

    timeout = _infer_network_timeout(cmd_id, cmd_entry)

    unique_targets = []
    seen = set()
    for t in targets:
        s = str(t).strip()
        if not s or s in seen:
            continue
        seen.add(s)
        unique_targets.append(s)

    local_targets = [t for t in unique_targets if is_local_target(t)]
    remote_targets = [t for t in unique_targets if not is_local_target(t)]

    # Параллельно выполняем на локальных и удалённых (если локальных несколько).
    # Локальные команды всё равно дедуплицируются внутри RobotAPI по fingerprint.
    errors: List[str] = []

    with ThreadPoolExecutor(max_workers=max(1, len(unique_targets))) as ex:
        futs = []

        for t in local_targets:
            futs.append(
                ex.submit(
                    lambda: robot_api.RobotAPI.execute_command(payload["command"], payload["args"]),
                )
            )

        for t in remote_targets:
            futs.append(
                ex.submit(
                    lambda target_ip=t: _network_api.send_data(
                        target_ip,
                        "/api/robot/execute",
                        payload,
                        timeout=timeout,
                    )
                )
            )

        for fut in as_completed(futs):
            res = None
            try:
                res = fut.result()
            except Exception as e:
                errors.append(str(e))
                continue

            # Local result: RobotAPI.execute_command -> dict with success/return_code...
            if isinstance(res, dict) and "success" in res and "response" not in res:
                if not res.get("success", False):
                    errors.append(res.get("message") or "local command failed")
                continue

            # Remote result: NetworkAPI.send_data -> { success: bool, response: dict }
            if not isinstance(res, dict):
                errors.append("invalid remote response")
                continue
            if not res.get("success", False):
                errors.append(res.get("message") or "remote request failed")
                continue
            remote_resp = res.get("response")
            if isinstance(remote_resp, dict) and remote_resp.get("success") is False:
                errors.append(remote_resp.get("message") or remote_resp.get("stderr") or "remote command rejected")
                continue

            # success or non-standard response treated as ok

    if errors:
        raise RuntimeError(" · ".join([e for e in errors if e]))


def _run_scenario_job(job_id: str, job_key: Optional[str], button: Dict[str, Any], page_host: Optional[str], local_ips: Optional[List[str]]) -> None:
    try:
        st_commands = robot_api.RobotAPI.get_commands()
        if not st_commands or not st_commands.get("success"):
            raise RuntimeError(st_commands.get("message") if isinstance(st_commands, dict) else "Failed to load commands")
        commands_list = st_commands.get("commands") or []
        commands_map = {c.get("id"): c for c in commands_list if c and c.get("id")}

        program = _normalize_program_from_button(button)
        if not program:
            raise RuntimeError("Пустой сценарий")

        default_targets = _normalize_target_list(button)
        is_local_target = _build_is_local_target(local_ips, page_host)

        total = len(program)
        _set_job_patch(job_id, {"status": "running", "started_at": time.time(), "progress": {"phase": "start", "message": "Запуск…"}})

        def resolve_targets(step_targets: Any) -> List[str]:
            if step_targets is not None and isinstance(step_targets, list) and len(step_targets) > 0:
                return step_targets
            return default_targets

        for i, block in enumerate(program):
            btype = block.get("type")
            if btype == "command":
                delay_before = _normalize_delay_ms(block.get("delayBeforeMs"))
                delay_after = _normalize_delay_ms(block.get("delayAfterMs"))
                command_id = block.get("commandId")
                if not command_id:
                    raise RuntimeError(f"Шаг {i + 1}: не выбрана команда")
                cmd_entry = commands_map.get(command_id)
                if not cmd_entry:
                    raise RuntimeError(f"Шаг {i + 1}: команда '{command_id}' недоступна")

                _set_job_progress(
                    job_id,
                    {
                        "phase": "delay",
                        "message": f"Пауза перед шагом {i + 1}/{total}…",
                        "blockIndex": i,
                        "blockCount": total,
                        "ms": delay_before,
                    },
                )
                if delay_before:
                    time.sleep(delay_before / 1000.0)

                label = cmd_entry.get("name") or command_id
                _set_job_progress(
                    job_id,
                    {
                        "phase": "run",
                        "message": f"Шаг {i + 1}/{total}: {label}",
                        "blockIndex": i,
                        "blockCount": total,
                    },
                )

                targets = resolve_targets(block.get("targetIps"))
                _run_command_on_targets(
                    cmd_id=str(command_id),
                    cmd_entry=cmd_entry,
                    targets=targets,
                    is_local_target=is_local_target,
                )

                _set_job_progress(
                    job_id,
                    {
                        "phase": "delay",
                        "message": f"Пауза после «{label}»…",
                        "blockIndex": i,
                        "blockCount": total,
                        "ms": delay_after,
                    },
                )
                if delay_after:
                    time.sleep(delay_after / 1000.0)

            elif btype == "delay":
                ms = _normalize_delay_ms(block.get("ms"))
                _set_job_progress(
                    job_id,
                    {
                        "phase": "delay",
                        "message": f"Задержка {ms} мс ({i + 1}/{total})…",
                        "blockIndex": i,
                        "blockCount": total,
                        "ms": ms,
                    },
                )
                if ms:
                    time.sleep(ms / 1000.0)

            elif btype == "parallel":
                delay_before = _normalize_delay_ms(block.get("delayBeforeMs"))
                delay_after = _normalize_delay_ms(block.get("delayAfterMs"))
                items = block.get("items") or []
                if not isinstance(items, list) or not items:
                    raise RuntimeError(f"Блок {i + 1} (параллель): нет веток")

                _set_job_progress(
                    job_id,
                    {
                        "phase": "delay",
                        "message": f"Пауза перед параллельным блоком ({i + 1}/{total})…",
                        "blockIndex": i,
                        "blockCount": total,
                        "ms": delay_before,
                    },
                )
                if delay_before:
                    time.sleep(delay_before / 1000.0)

                _set_job_progress(
                    job_id,
                    {
                        "phase": "parallel",
                        "message": f"Параллельно: {len(items)} ветк. (блок {i + 1}/{total})",
                        "blockIndex": i,
                        "blockCount": total,
                    },
                )

                # Каждая ветка: sleep(item.delayBeforeMs) -> run -> sleep(item.delayAfterMs)
                def branch_worker(j: int, item: Dict[str, Any]) -> None:
                    item_delay_before = _normalize_delay_ms(item.get("delayBeforeMs"))
                    item_delay_after = _normalize_delay_ms(item.get("delayAfterMs"))
                    command_id = item.get("commandId")
                    if not command_id:
                        raise RuntimeError(f"Параллель {i + 1}: ветка {j + 1} без команды")
                    cmd_entry = commands_map.get(command_id)
                    if not cmd_entry:
                        raise RuntimeError(f"Параллель {i + 1}: команда '{command_id}' недоступна")

                    if item_delay_before:
                        time.sleep(item_delay_before / 1000.0)

                    br_label = cmd_entry.get("name") or command_id
                    _set_job_progress(
                        job_id,
                        {
                            "phase": "branch",
                            "message": f"Ветка {j + 1}/{len(items)}: {br_label}",
                            "blockIndex": i,
                            "blockCount": total,
                        },
                    )

                    targets = resolve_targets(item.get("targetIps"))
                    _run_command_on_targets(
                        cmd_id=str(command_id),
                        cmd_entry=cmd_entry,
                        targets=targets,
                        is_local_target=is_local_target,
                    )

                    if item_delay_after:
                        time.sleep(item_delay_after / 1000.0)

                with ThreadPoolExecutor(max_workers=max(1, len(items))) as ex:
                    futs = [ex.submit(branch_worker, j, it) for j, it in enumerate(items)]
                    for fut in as_completed(futs):
                        # Берём первое исключение, чтобы прервать сценарий
                        fut.result()

                _set_job_progress(
                    job_id,
                    {
                        "phase": "delay",
                        "message": "Пауза после параллельного блока…",
                        "blockIndex": i,
                        "blockCount": total,
                        "ms": delay_after,
                    },
                )
                if delay_after:
                    time.sleep(delay_after / 1000.0)

            else:
                raise RuntimeError(f"Неподдерживаемый тип блока: {btype}")

        _set_job_progress(
            job_id,
            {
                "phase": "done",
                "message": f"Готово ({total} блок.)",
                "blockIndex": total - 1,
                "blockCount": total,
            },
        )
        _set_job_patch(job_id, {"status": "done", "finished_at": time.time()})

    except Exception as e:
        _set_job_patch(job_id, {"status": "error", "finished_at": time.time(), "error": str(e)})
    finally:
        if job_key:
            with _scenario_inflight_lock:
                _scenario_inflight_keys.discard(job_key)


def start_scenario_job(
    *,
    button: Dict[str, Any],
    page_host: Optional[str] = None,
    local_ips: Optional[List[str]] = None,
    scenario_key: Optional[str] = None,
) -> Dict[str, Any]:
    if not isinstance(button, dict):
        return {"success": False, "message": "button payload required"}

    job_key = str(scenario_key or button.get("id") or "").strip() or None
    if job_key:
        with _scenario_inflight_lock:
            if job_key in _scenario_inflight_keys:
                return {"success": False, "message": "Сценарий уже выполняется (дублирующий запрос)", "duplicate": True}
            _scenario_inflight_keys.add(job_key)

    job_id = uuid.uuid4().hex
    with _scenario_jobs_lock:
        _scenario_jobs[job_id] = {
            "jobId": job_id,
            "status": "queued",
            "created_at": time.time(),
            "progress": {"phase": "queue", "message": "Поставлено в очередь…"},
            "scenarioKey": job_key,
        }

    t = threading.Thread(
        target=_run_distributed_dispatch_job,
        args=(job_id, job_key, button, page_host, local_ips),
        daemon=True,
    )
    t.start()

    return {"success": True, "jobId": job_id}


def get_scenario_job(job_id: str) -> Dict[str, Any]:
    if not job_id:
        return {"success": False, "message": "jobId required"}
    with _scenario_jobs_lock:
        job = _scenario_jobs.get(job_id)
        if not job:
            return {"success": False, "message": "job not found"}
        # Копируем, чтобы избежать изменений во время сериализации
        return {"success": True, "job": dict(job)}

