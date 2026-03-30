import threading
import time
import uuid
from typing import Any, Dict, List, Optional, Set

import api.robot as robot_api
import api.network_api as network_api_module
import services_manager


_network_api = network_api_module.NetworkAPI()
try:
    _WEB_PORT = services_manager.get_web_port()
except Exception:
    _WEB_PORT = 8080


class ScenarioAgent:
    """
    Локальный исполнитель сценария на роботе.

    Идея:
    - координатор (веб-сервер/браузер) рассылает всем участникам один и тот же список шагов
      (command/delay/stop/continue/abort), но командные шаги могут быть "не для этого робота"
      (targets не содержит наш ip/LOCAL) — тогда робот только участвует в синхронизации.
    - READY сигнал: робот рассылает всем peers что дошёл до barrier шагов (по step_index).
    - WAIT CONTINUE: для command шага можно включить ожидание:
        - не выполнять шаг без внешней команды CONTINUE
        - и не выполнять пока не получены READY от всех участников
    - STOP: ставит паузу (все ждут CONTINUE)
    - ABORT: прерывает и очищает сценарий
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self._scenario_id: Optional[str] = None
        self._steps: List[Dict[str, Any]] = []
        self._peers: List[str] = []
        self._self_id: str = "LOCAL"
        # Версия: при каждом новом load увеличивается; _run() проверяет её и выходит если устарела
        self._run_version: int = 0

        self._paused = threading.Event()
        self._paused.clear()
        self._abort = threading.Event()
        self._abort.clear()
        self._continue_token = threading.Event()
        self._continue_token.clear()

        # ready_by_step[i] = set(ips) that have reported ready for step i
        self._ready_by_step: Dict[int, Set[str]] = {}

    def load(self, scenario_id: str, steps: List[Dict[str, Any]], peers: List[str], self_id: str) -> Dict[str, Any]:
        sid = str(scenario_id or "")
        new_peers = [str(x).strip() for x in (peers or []) if str(x).strip()]
        new_self_id = str(self_id or "LOCAL").strip() or "LOCAL"
        with self._lock:
            same_scenario = (self._scenario_id == sid and sid)
            thread_alive = bool(self._thread and self._thread.is_alive())
            if same_scenario and thread_alive:
                # Сценарий уже запущен — только обновляем peers, не сбрасываем ready_by_step
                self._peers = new_peers
                try:
                    print(f"[SCENARIO_AGENT] load: update peers only for running scenario {sid} peers={new_peers}", flush=True)
                except Exception:
                    pass
                return {"success": True, "scenarioId": sid, "steps": len(self._steps), "updated_peers": True}
            if same_scenario and not thread_alive:
                # Тот же scenarioId, но поток не запущен — обновляем peers и шаги, ready_by_step НЕ сбрасываем
                # (могли прийти READY от других агентов до старта)
                self._steps = list(steps or [])
                self._peers = new_peers
                self._self_id = new_self_id
                try:
                    print(f"[SCENARIO_AGENT] load: re-load same scenario {sid} peers={new_peers} (keep ready_by_step)", flush=True)
                except Exception:
                    pass
                return {"success": True, "scenarioId": sid, "steps": len(self._steps)}
            # Новый сценарий — прерываем предыдущий и полный сброс
            self._run_version += 1  # invalidate any running _run() thread
            self._abort.set()       # signal existing _run() to exit fast
            self._continue_token.set()  # unblock any waits in _run()
            self._scenario_id = sid
            self._steps = list(steps or [])
            self._peers = new_peers
            self._self_id = new_self_id
            self._ready_by_step = {}
            self._abort.clear()
            self._paused.clear()
            self._continue_token.clear()

        try:
            print(f"[SCENARIO_AGENT] load: new scenario {sid} selfId={new_self_id} peers={new_peers} steps={len(steps or [])}", flush=True)
        except Exception:
            pass
        return {"success": True, "scenarioId": self._scenario_id, "steps": len(self._steps)}

    def start(self) -> Dict[str, Any]:
        with self._lock:
            if not self._scenario_id or not self._steps:
                return {"success": False, "message": "no scenario loaded"}
            # Если поток жив, но abort уже установлен — он скоро завершится, не блокируем.
            # Если поток жив и abort НЕ установлен — реально работает, отклоняем.
            if self._thread and self._thread.is_alive() and not self._abort.is_set():
                return {"success": False, "message": "scenario already running"}
            self._abort.clear()
            self._paused.clear()
            self._continue_token.clear()
            my_version = self._run_version
            t = threading.Thread(target=self._run, args=(my_version,), name=f"scenario-agent-{self._scenario_id}", daemon=True)
            self._thread = t
            t.start()
        try:
            print(f"[SCENARIO_AGENT] started scenario={self._scenario_id} selfId={self._self_id} peers={self._peers} version={my_version}", flush=True)
        except Exception:
            pass
        return {"success": True}

    def stop(self) -> Dict[str, Any]:
        # STOP: pause progression; current command is not forcibly killed (best-effort).
        self._paused.set()
        return {"success": True, "paused": True}

    def cont(self) -> Dict[str, Any]:
        self._paused.clear()
        self._continue_token.set()
        return {"success": True, "paused": False}

    def abort(self) -> Dict[str, Any]:
        self._abort.set()
        self._paused.clear()
        self._continue_token.set()
        with self._lock:
            self._run_version += 1  # делаем текущий поток stale → он выйдет
            self._scenario_id = None
            self._steps = []
            self._peers = []
            self._ready_by_step = {}
        return {"success": True}

    def mark_ready(self, scenario_id: str, step_index: int, from_ip: str) -> Dict[str, Any]:
        sid = str(scenario_id or "")
        if not sid:
            return {"success": False, "message": "scenarioId required"}
        with self._lock:
            if self._scenario_id != sid:
                return {"success": False, "message": "scenarioId mismatch"}
            idx = int(step_index)
            if idx < 0:
                return {"success": False, "message": "invalid stepIndex"}
            st = self._ready_by_step.setdefault(idx, set())
            st.add(str(from_ip or "").strip() or "UNKNOWN")
        return {"success": True}

    def state(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "success": True,
                "scenarioId": self._scenario_id,
                "steps": len(self._steps),
                "peers": self._peers,
                "selfId": self._self_id,
                "paused": self._paused.is_set(),
                "aborted": self._abort.is_set(),
                "continueSet": self._continue_token.is_set(),
                "readyByStep": {int(k): sorted(list(v)) for k, v in self._ready_by_step.items()},
            }

    def _broadcast_ready(self, step_index: int) -> None:
        with self._lock:
            scenario_id = self._scenario_id
            peers = list(self._peers)
            self_id = self._self_id
        if not scenario_id:
            return
        payload = {"scenarioId": scenario_id, "stepIndex": int(step_index), "fromIp": self_id}
        for ip in peers:
            try:
                _network_api.send_data(
                    ip, "/api/robot/scenario/ready", payload, timeout=8, port=_WEB_PORT
                )
            except Exception:
                continue

    def _participants(self) -> Set[str]:
        with self._lock:
            return set(self._peers) | {self._self_id}

    def _wait_for_barrier(self, step_index: int, timeout_sec: float = 30.0, extra_participants: Optional[Set[str]] = None) -> bool:
        # Wait until READY from all participants has been received for this step_index.
        # extra_participants overrides default participants (peers | self_id) if provided.
        if extra_participants is not None:
            participants = set(extra_participants)
        else:
            participants = self._participants()
        # If no one to wait for — pass immediately
        if not participants or participants == {self._self_id}:
            with self._lock:
                st = self._ready_by_step.setdefault(step_index, set())
                st.add(self._self_id)
            return True
        # include self ready immediately
        with self._lock:
            st = self._ready_by_step.setdefault(step_index, set())
            st.add(self._self_id)

        t0 = time.time()
        last_log = 0.0
        while True:
            if self._abort.is_set():
                return False
            if timeout_sec is not None and (time.time() - t0) > float(timeout_sec):
                try:
                    with self._lock:
                        got = set(self._ready_by_step.get(step_index, set()))
                    missing = participants - got
                    print(f"[SCENARIO_AGENT] barrier step={step_index} TIMEOUT after {timeout_sec}s, missing={missing}", flush=True)
                except Exception:
                    pass
                return False
            # global pause
            if self._paused.is_set():
                time.sleep(0.05)
                continue
            with self._lock:
                got = set(self._ready_by_step.get(step_index, set()))
            if participants.issubset(got):
                return True
            # periodic log while waiting
            now = time.time()
            if now - last_log > 3.0:
                try:
                    missing = participants - got
                    print(f"[SCENARIO_AGENT] barrier step={step_index} waiting for {missing} (have {got})", flush=True)
                except Exception:
                    pass
                last_log = now
            time.sleep(0.05)

    def _should_execute_for_me(self, step: Dict[str, Any]) -> bool:
        # If command has targets list, run only if self_id matches.
        targets = step.get("targets")
        if targets is None:
            targets = step.get("targetIps")
        if targets is None:
            return True
        if not isinstance(targets, list):
            targets = [targets]
        tset = {str(x).strip() for x in targets if str(x).strip()}
        if not tset:
            return True
        # Прямое совпадение
        if self._self_id in tset:
            return True
        return False

    def _run(self, my_version: int = 0) -> None:
        # unique local run id (for debugging only)
        _run_id = uuid.uuid4().hex[:8]

        def _stale() -> bool:
            """Returns True if a newer load() has replaced this run."""
            with self._lock:
                return self._run_version != my_version

        try:
            print(f"[SCENARIO_AGENT] _run START id={_run_id} version={my_version} steps={len(self._steps)} abort={self._abort.is_set()} stale={_stale()}", flush=True)
        except Exception:
            pass

        for idx, step in enumerate(list(self._steps)):
            if self._abort.is_set() or _stale():
                return

            # pause gate
            while self._paused.is_set() and not self._abort.is_set() and not _stale():
                time.sleep(0.05)
            if self._abort.is_set() or _stale():
                return

            stype = str(step.get("type") or "").strip()
            if stype == "stop":
                # entering stop => pause until external CONTINUE
                self._paused.set()
                self._broadcast_ready(idx)
                continue
            if stype == "abort":
                self.abort()
                return
            if stype == "continue":
                # continue node = locally allows progression
                self.cont()
                self._broadcast_ready(idx)
                continue
            if stype == "delay":
                ms = int(step.get("ms") or 0)
                self._broadcast_ready(idx)
                # delay is a "command": it should respect pause/abort
                remaining = max(0, ms) / 1000.0
                while remaining > 0:
                    if self._abort.is_set():
                        return
                    if self._paused.is_set():
                        time.sleep(0.05)
                        continue
                    t0 = time.time()
                    time.sleep(min(0.05, remaining))
                    remaining -= (time.time() - t0)
                continue

            if stype == "command":
                wait_all = bool(step.get("waitContinue"))
                use_go = bool(step.get("useGo"))
                # READY barrier is per-step index
                targets_dbg = step.get("targetIps") or step.get("targets")
                try:
                    print(
                        f"[SCENARIO_AGENT] cmd idx={idx} self={self._self_id} wait_all={wait_all} use_go={use_go} targets={targets_dbg}",
                        flush=True,
                    )
                except Exception:
                    pass
                self._broadcast_ready(idx)

                if wait_all:
                    # Ждём только тех кто в targetIps (они реально выполняют команду).
                    # Если targetIps пусты/None — ждём всех peers.
                    step_targets = step.get("targetIps") or step.get("targets")
                    if step_targets:
                        step_tset = {str(x).strip() for x in step_targets if str(x).strip() and str(x).strip() != "LOCAL"}
                        # Участники барьера = пересечение peers с targetIps + self если в targetIps
                        with self._lock:
                            all_peers = set(self._peers)
                        barrier_participants = (all_peers & step_tset)
                        if self._self_id in step_tset:
                            barrier_participants.add(self._self_id)
                        # Если никого в пересечении нет — барьер не нужен
                        barrier_ok = self._wait_for_barrier(idx, timeout_sec=30.0, extra_participants=barrier_participants or None)
                    else:
                        barrier_ok = self._wait_for_barrier(idx, timeout_sec=30.0)
                    if self._abort.is_set():
                        return
                    if not barrier_ok:
                        try:
                            print(f"[SCENARIO_AGENT] cmd idx={idx} self={self._self_id}: barrier timeout, executing anyway", flush=True)
                        except Exception:
                            pass

                if use_go:
                    # Если GO подключён — ждем внешнее "ПРОДОЛЖИТЬ"
                    while not self._continue_token.is_set() and not self._abort.is_set():
                        if self._paused.is_set():
                            time.sleep(0.05)
                            continue
                        time.sleep(0.05)
                    if self._abort.is_set():
                        return

                if not self._should_execute_for_me(step):
                    try:
                        print(
                            f"[SCENARIO_AGENT] cmd idx={idx} self={self._self_id}: SKIP (targets mismatch)",
                            flush=True,
                        )
                    except Exception:
                        pass
                    continue

                cmd = str(step.get("command") or step.get("commandId") or "").strip()
                args = step.get("args") or []
                if cmd:
                    try:
                        # Best-effort: do not kill on STOP, only block next steps
                        try:
                            print(f"[SCENARIO_AGENT] cmd idx={idx} self={self._self_id}: EXEC cmd={cmd}", flush=True)
                        except Exception:
                            pass
                        # apply delayBeforeMs/delayAfterMs semantics
                        delay_before_ms = int(step.get("delayBeforeMs") or 0)
                        delay_after_ms = int(step.get("delayAfterMs") or 0)
                        while delay_before_ms > 0:
                            if self._abort.is_set():
                                return
                            if self._paused.is_set():
                                time.sleep(0.05)
                                continue
                            sl = min(50, delay_before_ms)
                            time.sleep(sl / 1000.0)
                            delay_before_ms -= sl

                        exec_args = args if isinstance(args, list) else [args]
                        try:
                            robot_type_now = None
                            if hasattr(robot_api.RobotAPI, "_get_robot_type"):
                                robot_type_now = robot_api.RobotAPI._get_robot_type()
                            print(f"[SCENARIO_AGENT] cmd idx={idx} self={self._self_id}: robot_type={robot_type_now}", flush=True)
                        except Exception:
                            pass
                        result = robot_api.RobotAPI.execute_command(cmd, exec_args)

                        try:
                            print(
                                f"[SCENARIO_AGENT] cmd idx={idx} self={self._self_id}: result.success={result.get('success')} message={result.get('message')} duration_ms={result.get('duration_ms')}",
                                flush=True,
                            )
                        except Exception:
                            pass

                        # Если команда fire-and-forget (RPC) — ждём физического завершения.
                        # duration_ms в результате означает что команда уже отправлена роботу,
                        # но физически ещё выполняется. Ждём это время прежде чем идти дальше.
                        cmd_duration_ms = int(result.get("duration_ms") or 0)
                        if cmd_duration_ms > 0 and delay_after_ms < cmd_duration_ms:
                            # Используем максимум из duration_ms и delay_after_ms
                            delay_after_ms = cmd_duration_ms

                        while delay_after_ms > 0:
                            if self._abort.is_set():
                                return
                            if self._paused.is_set():
                                time.sleep(0.05)
                                continue
                            sl = min(50, delay_after_ms)
                            time.sleep(sl / 1000.0)
                            delay_after_ms -= sl
                    except Exception:
                        # ignore errors in this minimal implementation
                        try:
                            print(f"[SCENARIO_AGENT] cmd idx={idx} self={self._self_id}: EXEC failed", flush=True)
                        except Exception:
                            pass
                        pass
                continue

            # unknown step => ignore
            self._broadcast_ready(idx)


_agent = ScenarioAgent()


def get_agent() -> ScenarioAgent:
    return _agent

