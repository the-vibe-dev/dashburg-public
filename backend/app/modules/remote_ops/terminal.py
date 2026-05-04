from __future__ import annotations

import asyncio
import fcntl
import os
import pty
import re
import shlex
import signal
import struct
import subprocess
import termios
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect

_TERMINAL_DA_RESPONSE_PATTERNS = (
    re.compile(r"^\x1b\[\?[0-9;]*c$"),
    re.compile(r"^\x1b\[>[0-9;]*c$"),
    re.compile(r"^[0-9]+(?:;[0-9]+)*c$"),
)


def _is_terminal_da_response(data: str) -> bool:
    normalized = data.replace("\r", "").replace("\n", "")
    if not normalized:
        return False
    return any(pattern.fullmatch(normalized) for pattern in _TERMINAL_DA_RESPONSE_PATTERNS)


@dataclass
class RuntimeSession:
    session_id: str
    node_id: str
    process: subprocess.Popen[Any]
    master_fd: int
    started_at: float
    last_activity: float
    last_input_at: float
    closed: bool = False
    exit_code: int | None = None
    subscribers: set[asyncio.Queue[dict[str, Any]]] = field(default_factory=set)
    output_buffer: str = ""


class TerminalManager:
    def __init__(self) -> None:
        self._sessions: dict[str, RuntimeSession] = {}
        self._lock = asyncio.Lock()
        self._cleanup_task: asyncio.Task[None] | None = None
        self._idle_timeout_seconds = int(os.getenv("REMOTEOPS_TERMINAL_IDLE_TIMEOUT_SECONDS", "1800"))
        self._output_buffer_max_chars = int(os.getenv("REMOTEOPS_TERMINAL_OUTPUT_BUFFER_CHARS", "262144"))
        self._persist_sessions = os.getenv("REMOTEOPS_TERMINAL_PERSIST_SESSIONS", "1").strip().lower() not in {"0", "false", "no"}
        self._tmux_prefix = os.getenv("REMOTEOPS_TERMINAL_TMUX_PREFIX", "dashburg-remote-").strip() or "dashburg-remote-"

    def configure(self, *, idle_timeout_seconds: int | None = None) -> None:
        if idle_timeout_seconds is not None:
            self._idle_timeout_seconds = max(0, int(idle_timeout_seconds))

    def _tmux_name(self, session_id: str) -> str:
        safe_id = "".join(ch for ch in str(session_id) if ch.isalnum() or ch in {"-", "_"})
        return f"{self._tmux_prefix}{safe_id}"

    def _remote_startup_command(
        self,
        session_id: str,
        node_id: str,
        cwd: str | None,
        command: str | None,
        restore_only: bool,
        ssh_target: str | None = None,
    ) -> str:
        def _norm(value: str | None) -> str:
            return str(value or "").strip().lower()

        windows_nodes = {
            _norm(n)
            for n in os.getenv("REMOTEOPS_TERMINAL_WINDOWS_NODE_IDS", "").split(",")
            if _norm(n)
        }
        node_norm = _norm(node_id)
        target_norm = _norm(ssh_target)
        target_user = target_norm.split("@", 1)[0] if "@" in target_norm else ""

        is_windows_node = node_norm in windows_nodes
        if not is_windows_node and node_norm:
            # Defensive fallback when UI aliases differ from backend node ids.
            is_windows_node = node_norm.startswith("win") or "windows" in node_norm
        if not is_windows_node and target_user:
            # Windows hosts in this environment use win-prefixed ssh usernames.
            is_windows_node = target_user.startswith("win") or "windows" in target_user

        if is_windows_node:
            cmd_val = str(command or "").strip()
            if cmd_val:
                return cmd_val
            if restore_only:
                return "cmd.exe"
            return os.getenv("REMOTEOPS_TERMINAL_WINDOWS_ENTRY", "powershell.exe -NoLogo")

        entry_command = os.getenv("REMOTEOPS_TERMINAL_ENTRY", "").strip() or "/usr/local/bin/dashterm-entry"
        tmux_name = self._tmux_name(session_id)
        cwd_val = str(cwd or "").strip()
        cmd_val = str(command or "").strip()
        create_flag = "0" if restore_only else "1"
        script_lines = [
            f'TMUX_NAME={shlex.quote(tmux_name)}',
            f'CREATE_IF_MISSING={shlex.quote(create_flag)}',
            f'INIT_CWD={shlex.quote(cwd_val)}',
            f'INIT_CMD={shlex.quote(cmd_val)}',
            "if command -v tmux >/dev/null 2>&1; then",
            '  if ! tmux has-session -t "$TMUX_NAME" 2>/dev/null; then',
            '    if [ "$CREATE_IF_MISSING" != "1" ]; then',
            "      exit 87",
            "    fi",
            '    if [ -n "$INIT_CWD" ]; then',
            '      if command -v systemd-run >/dev/null 2>&1; then',
            '        systemd-run --user --scope --quiet --unit "dashburg-tmux-$TMUX_NAME" tmux new-session -d -s "$TMUX_NAME" -c "$INIT_CWD" >/dev/null 2>&1 || tmux new-session -d -s "$TMUX_NAME" -c "$INIT_CWD"',
            "      else",
            '        tmux new-session -d -s "$TMUX_NAME" -c "$INIT_CWD"',
            "      fi",
            "    else",
            '      if command -v systemd-run >/dev/null 2>&1; then',
            '        systemd-run --user --scope --quiet --unit "dashburg-tmux-$TMUX_NAME" tmux new-session -d -s "$TMUX_NAME" >/dev/null 2>&1 || tmux new-session -d -s "$TMUX_NAME"',
            "      else",
            '        tmux new-session -d -s "$TMUX_NAME"',
            "      fi",
            "    fi",
            '    if [ -n "$INIT_CMD" ] && [ "$INIT_CMD" != "bash -l" ] && [ "$INIT_CMD" != "bash" ]; then',
            '      tmux send-keys -t "$TMUX_NAME" "$INIT_CMD" C-m',
            "    fi",
            "  fi",
            '  exec tmux attach-session -t "$TMUX_NAME"',
            "fi",
        ]
        if restore_only:
            script_lines.append("exit 87")
        else:
            script_lines.extend(
                [
                    f'if [ -x "{entry_command}" ]; then exec "{entry_command}"; else echo "Welcome to RemoteOps Terminal"; exec bash -l; fi',
                ]
            )
        # Keep shell control blocks on separate lines to avoid invalid constructs like `then;`.
        return "\n".join(script_lines)

    def _spawn_session(
        self, session_id: str, node_id: str, ssh_target: str, cwd: str | None, command: str | None, restore_only: bool
    ) -> RuntimeSession:
        master_fd, slave_fd = pty.openpty()
        root_dir = Path(__file__).resolve().parents[4]
        known_hosts_dir = root_dir / "data" / "remoteops"
        known_hosts_dir.mkdir(parents=True, exist_ok=True)
        known_hosts_file = known_hosts_dir / "known_hosts"
        known_hosts_file.touch(exist_ok=True)

        strict_mode = os.getenv("REMOTEOPS_SSH_STRICT_HOST_KEY_CHECKING", "accept-new").strip() or "accept-new"
        ssh_key_path = os.getenv("REMOTEOPS_SSH_KEY_PATH", "").strip()
        if not ssh_key_path:
            default_key = Path.home() / ".ssh" / "dashburg_remoteops"
            if default_key.exists():
                ssh_key_path = str(default_key)
        ssh_cmd = [
            "ssh",
            "-tt",
            "-o",
            "BatchMode=yes",
            "-o",
            "IdentitiesOnly=yes",
            "-o",
            "ConnectTimeout=8",
            "-o",
            "ServerAliveInterval=10",
            "-o",
            "ServerAliveCountMax=6",
            "-o",
            "TCPKeepAlive=yes",
            "-o",
            f"StrictHostKeyChecking={strict_mode}",
            "-o",
            f"UserKnownHostsFile={known_hosts_file}",
        ]
        if ssh_key_path:
            ssh_cmd.extend(["-i", ssh_key_path])
        remote_command = self._remote_startup_command(session_id, node_id, cwd, command, restore_only=restore_only, ssh_target=ssh_target)
        ssh_cmd.extend(
            [
                ssh_target,
                remote_command,
            ]
        )
        env = dict(os.environ)
        # Ensure remote PTY sessions advertise a full terminal type so startup scripts
        # that call `clear`/terminfo-dependent tools do not fail immediately.
        env["TERM"] = str(env.get("TERM") or "xterm-256color")

        process = subprocess.Popen(
            ssh_cmd,
            stdin=slave_fd,
            stdout=slave_fd,
            stderr=slave_fd,
            env=env,
            close_fds=True,
            start_new_session=True,
        )
        os.close(slave_fd)

        now = time.time()
        runtime = RuntimeSession(
            session_id=session_id,
            node_id=node_id,
            process=process,
            master_fd=master_fd,
            started_at=now,
            last_activity=now,
            last_input_at=now,
        )
        return runtime

    async def create(self, session_id: str, node_id: str, ssh_target: str, cwd: str | None = None, command: str | None = None) -> None:
        loop = asyncio.get_running_loop()
        runtime = await loop.run_in_executor(None, self._spawn_session, session_id, node_id, ssh_target, cwd, command, False)
        async with self._lock:
            self._sessions[session_id] = runtime
            if self._cleanup_task is None or self._cleanup_task.done():
                self._cleanup_task = asyncio.create_task(self._cleanup_loop())

        self._start_reader_thread(loop, runtime)

    async def restore(self, session_id: str, node_id: str, ssh_target: str) -> bool:
        if not self._persist_sessions:
            return False
        if self.is_open(session_id):
            return True
        loop = asyncio.get_running_loop()
        try:
            runtime = await loop.run_in_executor(None, self._spawn_session, session_id, node_id, ssh_target, None, None, True)
        except Exception:
            return False
        async with self._lock:
            self._sessions[session_id] = runtime
            if self._cleanup_task is None or self._cleanup_task.done():
                self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        self._start_reader_thread(loop, runtime)
        await asyncio.sleep(0.25)
        return self.is_open(session_id)

    def _start_reader_thread(self, loop: asyncio.AbstractEventLoop, runtime: RuntimeSession) -> None:
        def _reader() -> None:
            while True:
                if runtime.closed:
                    break
                try:
                    data = os.read(runtime.master_fd, 4096)
                except OSError:
                    break

                if not data:
                    break

                runtime.last_activity = time.time()
                chunk = data.decode("utf-8", errors="replace")
                runtime.output_buffer = (runtime.output_buffer + chunk)[-self._output_buffer_max_chars :]
                payload = {"type": "output", "data": chunk}
                loop.call_soon_threadsafe(self._broadcast_threadsafe, runtime.session_id, payload)

            exit_code = runtime.process.poll()
            if exit_code is None:
                try:
                    exit_code = runtime.process.wait(timeout=2.0)
                except Exception:
                    exit_code = -1
            runtime.exit_code = exit_code
            loop.call_soon_threadsafe(self._on_exit_threadsafe, runtime.session_id, exit_code)

        t = threading.Thread(target=_reader, daemon=True)
        t.start()

    def _broadcast_threadsafe(self, session_id: str, payload: dict[str, Any]) -> None:
        runtime = self._sessions.get(session_id)
        if not runtime:
            return
        for q in list(runtime.subscribers):
            try:
                q.put_nowait(payload)
            except asyncio.QueueFull:
                pass

    def _on_exit_threadsafe(self, session_id: str, exit_code: int | None) -> None:
        runtime = self._sessions.get(session_id)
        if not runtime:
            return
        runtime.closed = True
        payload = {"type": "exit", "code": exit_code if exit_code is not None else 0}
        for q in list(runtime.subscribers):
            try:
                q.put_nowait(payload)
            except asyncio.QueueFull:
                pass

    async def attach(self, session_id: str, websocket: WebSocket) -> None:
        runtime = self._sessions.get(session_id)
        if not runtime:
            await websocket.send_json({"type": "exit", "code": 404})
            await websocket.close(code=1008)
            return

        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=500)
        runtime.subscribers.add(queue)
        runtime.last_activity = time.time()
        runtime.last_input_at = runtime.last_activity
        if runtime.output_buffer:
            try:
                queue.put_nowait({"type": "output", "data": runtime.output_buffer})
            except asyncio.QueueFull:
                pass

        async def sender() -> None:
            while True:
                msg = await queue.get()
                try:
                    await websocket.send_json(msg)
                except WebSocketDisconnect:
                    break
                if msg.get("type") == "exit":
                    break

        async def receiver() -> None:
            while True:
                try:
                    payload = await websocket.receive_json()
                except WebSocketDisconnect:
                    break
                except Exception:
                    # Ignore malformed or non-JSON frames instead of tearing down
                    # the full terminal session transport.
                    continue
                ptype = str(payload.get("type", ""))
                if ptype == "input":
                    data = str(payload.get("data", ""))
                    if data:
                        if _is_terminal_da_response(data):
                            continue
                        os.write(runtime.master_fd, data.encode("utf-8", errors="ignore"))
                        runtime.last_activity = time.time()
                        runtime.last_input_at = runtime.last_activity
                elif ptype == "resize":
                    cols = int(payload.get("cols", 120))
                    rows = int(payload.get("rows", 40))
                    self._resize(runtime.master_fd, rows, cols)
                    runtime.last_activity = time.time()
                elif ptype == "signal":
                    name = str(payload.get("name", "")).upper()
                    self._signal(runtime, name)
                    runtime.last_activity = time.time()

        sender_task = asyncio.create_task(sender())
        recv_task = asyncio.create_task(receiver())
        done, pending = await asyncio.wait({sender_task, recv_task}, return_when=asyncio.FIRST_COMPLETED)
        for task in pending:
            task.cancel()
        for task in done:
            try:
                task.result()
            except WebSocketDisconnect:
                pass
            except asyncio.CancelledError:
                pass
            except Exception:
                pass

        runtime.subscribers.discard(queue)

    def _resize(self, master_fd: int, rows: int, cols: int) -> None:
        winsize = struct.pack("HHHH", rows, cols, 0, 0)
        fcntl.ioctl(master_fd, termios.TIOCSWINSZ, winsize)

    def _signal(self, runtime: RuntimeSession, name: str) -> None:
        sig = {"SIGINT": signal.SIGINT, "SIGTERM": signal.SIGTERM, "SIGKILL": signal.SIGKILL}.get(name)
        if sig is None:
            return
        try:
            runtime.process.send_signal(sig)
        except Exception:
            pass

    async def kill(self, session_id: str) -> bool:
        async with self._lock:
            runtime = self._sessions.get(session_id)
        if not runtime:
            return False

        if runtime.process.poll() is None:
            try:
                runtime.process.terminate()
                runtime.process.wait(timeout=3)
            except Exception:
                try:
                    runtime.process.kill()
                except Exception:
                    pass
        runtime.closed = True
        try:
            os.close(runtime.master_fd)
        except OSError:
            pass
        return True

    def is_open(self, session_id: str) -> bool:
        runtime = self._sessions.get(session_id)
        if not runtime:
            return False
        if runtime.closed:
            return False
        return runtime.process.poll() is None

    def active_count(self) -> int:
        return sum(1 for r in self._sessions.values() if not r.closed and r.process.poll() is None)

    def find_active_session(self, node_id: str | None = None) -> str | None:
        candidates: list[RuntimeSession] = []
        for runtime in self._sessions.values():
            if runtime.closed or runtime.process.poll() is not None:
                continue
            if node_id and runtime.node_id != node_id:
                continue
            candidates.append(runtime)
        if not candidates:
            return None
        candidates.sort(key=lambda r: (r.last_activity, r.started_at), reverse=True)
        return candidates[0].session_id

    def list_active(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for runtime in self._sessions.values():
            if runtime.closed or runtime.process.poll() is not None:
                continue
            rows.append(
                {
                    "session_id": runtime.session_id,
                    "node_id": runtime.node_id,
                    "last_activity": runtime.last_activity,
                    "last_input_at": runtime.last_input_at,
                    "subscribers": len(runtime.subscribers),
                }
            )
        rows.sort(key=lambda r: float(r["last_activity"]))
        return rows

    async def reclaim_oldest(self) -> bool:
        active = self.list_active()
        if not active:
            return False
        oldest = active[0]
        return await self.kill(str(oldest["session_id"]))

    async def _cleanup_loop(self) -> None:
        while True:
            await asyncio.sleep(15)
            to_kill: list[str] = []
            async with self._lock:
                for sid, runtime in list(self._sessions.items()):
                    if runtime.closed or runtime.process.poll() is not None:
                        to_kill.append(sid)
                    elif self._idle_timeout_seconds > 0 and len(runtime.subscribers) == 0 and runtime.last_activity < (time.time() - self._idle_timeout_seconds):
                        to_kill.append(sid)
            for sid in to_kill:
                await self.kill(sid)


_manager: TerminalManager | None = None


def get_terminal_manager() -> TerminalManager:
    global _manager
    if _manager is None:
        _manager = TerminalManager()
    return _manager
