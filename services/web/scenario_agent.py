import threading
import time
import uuid
from typing import Any, Dict, List, Optional, Set

import api.robot as robot_api
import api.network_api as network_api_module


_network_api = network_api_module.NetworkAPI()


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

        self._paused = threading.Event()
        self._paused.clear()
        self._abort = threading.Event()
        self._abort.clear()
        self._continue_token = threading.Event()
        self._continue_token.clear()

        # ready_by_step[i] = set(ips) that have reported ready for step i
        self._ready_by_step: Dict[int, Set[str]] = {}

    def load(self, scenario_id: str, steps: List[Dict[str, Any]], peers: List[str], self_id: str) -> Dict[str, Any]:
        with self._lock:
            self._scenario_id = str(scenario_id or "")
            self._steps = list(steps or [])
            self._peers = [str(x).strip() for x in (peers or []) if str(x).strip()]
            self._self_id = str(self_id or "LOCAL").strip() or "LOCAL"
            self._ready_by_step = {}
            self._abort.clear()
            self._paused.clear()
            self._continue_token.clear()

        return {"success": True, "scenarioId": self._scenario_id, "steps": len(self._steps)}

    def start(self) -> Dict[str, Any]:
        with self._lock:
            if not self._scenario_id or not self._steps:
                return {"success": False, "message": "no scenario loaded"}
            if self._thread and self._thread.is_alive():
                return {"success": False, "message": "scenario already running"}
            self._abort.clear()
            self._paused.clear()
            self._continue_token.clear()
            t = threading.Thread(target=self._run, name=f"scenario-agent-{self._scenario_id}", daemon=True)
            self._thread = t
            t.start()
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
                _network_api.send_data(ip, "/api/robot/scenario/ready", payload, timeout=8)
            except Exception:
                continue

    def _participants(self) -> Set[str]:
        with self._lock:
            return set(self._peers) | {self._self_id}

    def _wait_for_barrier(self, step_index: int) -> bool:
        # Wait until READY from all participants has been received for this step_index.
        participants = self._participants()
        # include self ready immediately
        with self._lock:
            st = self._ready_by_step.setdefault(step_index, set())
            st.add(self._self_id)

        while True:
            if self._abort.is_set():
                return False
            # global pause
            if self._paused.is_set():
                time.sleep(0.05)
                continue
            with self._lock:
                got = set(self._ready_by_step.get(step_index, set()))
            if participants.issubset(got):
                return True
            time.sleep(0.05)

    def _should_execute_for_me(self, step: Dict[str, Any]) -> bool:
        # If command has targets list, run only if self_id/LOCAL matches.
        targets = step.get("targets")
        if targets is None:
            targets = step.get("targetIps")
        if targets is None:
            return True
        if not isinstance(targets, list):
            targets = [targets]
        tset = {str(x).strip() for x in targets if str(x).strip()}
        if "LOCAL" in tset and self._self_id == "LOCAL":
            return True
        return self._self_id in tset or ("LOCAL" in tset and self._self_id != "LOCAL")

    def _run(self) -> None:
        # unique local run id (for debugging only)
        _run_id = uuid.uuid4().hex[:8]
        for idx, step in enumerate(list(self._steps)):
            if self._abort.is_set():
                return

            # pause gate
            while self._paused.is_set() and not self._abort.is_set():
                time.sleep(0.05)
            if self._abort.is_set():
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
                wait_continue = bool(step.get("waitContinue"))
                # ready barrier is per-step index
                self._broadcast_ready(idx)
                if wait_continue:
                    # wait for global continue and all peers ready
                    while not self._continue_token.is_set() and not self._abort.is_set():
                        if self._paused.is_set():
                            time.sleep(0.05)
                            continue
                        time.sleep(0.05)
                    if self._abort.is_set():
                        return
                    if not self._wait_for_barrier(idx):
                        return

                if not self._should_execute_for_me(step):
                    continue

                cmd = str(step.get("command") or step.get("commandId") or "").strip()
                args = step.get("args") or []
                if cmd:
                    try:
                        # Best-effort: do not kill on STOP, only block next steps
                        robot_api.RobotAPI.execute_command(cmd, args if isinstance(args, list) else [args])
                    except Exception:
                        # ignore errors in this minimal implementation
                        pass
                continue

            # unknown step => ignore
            self._broadcast_ready(idx)


_agent = ScenarioAgent()


def get_agent() -> ScenarioAgent:
    return _agent

