from __future__ import annotations

import asyncio
import fcntl
import os
import pty
import re
import shlex
import shutil
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
    process: subprocess.Popen[Any]
    master_fd: int
    cwd: str
    command: str
    started_at: float
    last_activity: float
    last_input_at: float
    closed: bool = False
    exit_code: int | None = None
    subscribers: set[asyncio.Queue[dict[str, Any]]] = field(default_factory=set)
    output_buffer: str = ""


class LocalTerminalManager:
    def __init__(self) -> None:
        self._sessions: dict[str, RuntimeSession] = {}
        self._lock = asyncio.Lock()
        self._cleanup_task: asyncio.Task[None] | None = None
        self._idle_timeout_seconds = int(os.getenv("LOCALOPS_TERMINAL_IDLE_TIMEOUT_SECONDS", "1800"))
        self._output_buffer_max_chars = int(os.getenv("LOCALOPS_TERMINAL_OUTPUT_BUFFER_CHARS", "262144"))
        self._persist_sessions = os.getenv("LOCALOPS_TERMINAL_PERSIST_SESSIONS", "1").strip().lower() not in {"0", "false", "no"}
        self._tmux_prefix = os.getenv("LOCALOPS_TERMINAL_TMUX_PREFIX", "dashburg-local-").strip() or "dashburg-local-"

    def configure(self, *, idle_timeout_seconds: int | None = None) -> None:
        if idle_timeout_seconds is not None:
            self._idle_timeout_seconds = max(0, int(idle_timeout_seconds))

    def _tmux_available(self) -> bool:
        return shutil.which("tmux") is not None

    def _tmux_name(self, session_id: str) -> str:
        safe_id = "".join(ch for ch in str(session_id) if ch.isalnum() or ch in {"-", "_"})
        return f"{self._tmux_prefix}{safe_id}"

    def _spawn_tmux_attach(
        self, session_id: str, cwd: Path, command: str | None, create_if_missing: bool
    ) -> tuple[subprocess.Popen[Any], int]:
        tmux_name = self._tmux_name(session_id)
        init_cmd = str(command or "").strip()
        create_flag = "1" if create_if_missing else "0"
        script = "\n".join(
            [
                f'TMUX_NAME={shlex.quote(tmux_name)}',
                f'CREATE_IF_MISSING={shlex.quote(create_flag)}',
                f'TARGET_CWD={shlex.quote(str(cwd))}',
                f'INIT_CMD={shlex.quote(init_cmd)}',
                'if ! command -v tmux >/dev/null 2>&1; then echo "tmux not installed"; exit 86; fi',
                'if ! tmux has-session -t "$TMUX_NAME" 2>/dev/null; then',
                '  if [ "$CREATE_IF_MISSING" != "1" ]; then',
                '    echo "tmux session not found: $TMUX_NAME"',
                "    exit 87",
                "  fi",
                '  if command -v systemd-run >/dev/null 2>&1; then',
                '    systemd-run --user --scope --quiet --unit "dashburg-tmux-$TMUX_NAME" tmux new-session -d -s "$TMUX_NAME" -c "$TARGET_CWD" >/dev/null 2>&1 || tmux new-session -d -s "$TMUX_NAME" -c "$TARGET_CWD"',
                "  else",
                '    tmux new-session -d -s "$TMUX_NAME" -c "$TARGET_CWD"',
                "  fi",
                '  if [ -n "$INIT_CMD" ] && [ "$INIT_CMD" != "bash -l" ] && [ "$INIT_CMD" != "bash" ]; then',
                '    tmux send-keys -t "$TMUX_NAME" "$INIT_CMD" C-m',
                "  fi",
                "fi",
                'exec tmux attach-session -t "$TMUX_NAME"',
            ]
        )
        master_fd, slave_fd = pty.openpty()
        env = dict(os.environ)
        env["TERM"] = str(env.get("TERM") or "xterm-256color")
        process = subprocess.Popen(
            ["bash", "-lc", script],
            stdin=slave_fd,
            stdout=slave_fd,
            stderr=slave_fd,
            env=env,
            close_fds=True,
            start_new_session=True,
        )
        os.close(slave_fd)
        return process, master_fd

    def _spawn_session(self, session_id: str, cwd: str | None, command: str | None) -> RuntimeSession:
        base_dir = Path(os.getenv("LOCALOPS_TERMINAL_CWD", str(Path.home()))).expanduser().resolve()
        target_cwd = Path(cwd).expanduser().resolve() if cwd else base_dir
        if not target_cwd.exists() or not target_cwd.is_dir():
            target_cwd = base_dir

        entry = (command or os.getenv("LOCALOPS_TERMINAL_ENTRY", "bash -l")).strip() or "bash -l"
        if self._persist_sessions and self._tmux_available():
            process, master_fd = self._spawn_tmux_attach(session_id, target_cwd, entry, create_if_missing=True)
        else:
            master_fd, slave_fd = pty.openpty()
            shell_cmd = f"cd {shlex.quote(str(target_cwd))} && exec {entry}"
            env = dict(os.environ)
            env["TERM"] = str(env.get("TERM") or "xterm-256color")
            process = subprocess.Popen(
                ["bash", "-lc", shell_cmd],
                stdin=slave_fd,
                stdout=slave_fd,
                stderr=slave_fd,
                env=env,
                close_fds=True,
                start_new_session=True,
            )
            os.close(slave_fd)

        now = time.time()
        return RuntimeSession(
            session_id=session_id,
            process=process,
            master_fd=master_fd,
            cwd=str(target_cwd),
            command=entry,
            started_at=now,
            last_activity=now,
            last_input_at=now,
        )

    def _spawn_restore_session(self, session_id: str) -> RuntimeSession | None:
        if not (self._persist_sessions and self._tmux_available()):
            return None
        base_dir = Path(os.getenv("LOCALOPS_TERMINAL_CWD", str(Path.home()))).expanduser().resolve()
        process, master_fd = self._spawn_tmux_attach(session_id, base_dir, None, create_if_missing=False)
        now = time.time()
        return RuntimeSession(
            session_id=session_id,
            process=process,
            master_fd=master_fd,
            cwd=str(base_dir),
            command="tmux-attach",
            started_at=now,
            last_activity=now,
            last_input_at=now,
        )

    async def create(self, session_id: str, cwd: str | None = None, command: str | None = None) -> None:
        loop = asyncio.get_running_loop()
        runtime = await loop.run_in_executor(None, self._spawn_session, session_id, cwd, command)
        async with self._lock:
            self._sessions[session_id] = runtime
            if self._cleanup_task is None or self._cleanup_task.done():
                self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        self._start_reader_thread(loop, runtime)

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

        threading.Thread(target=_reader, daemon=True).start()

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
            loop = asyncio.get_running_loop()
            restored = await loop.run_in_executor(None, self._spawn_restore_session, session_id)
            if restored:
                async with self._lock:
                    self._sessions[session_id] = restored
                    if self._cleanup_task is None or self._cleanup_task.done():
                        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
                self._start_reader_thread(loop, restored)
                runtime = restored
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
                    # Ignore malformed/non-JSON frames; keep terminal transport alive.
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
                    self._signal(runtime, str(payload.get("name", "")).upper())
                    runtime.last_activity = time.time()

        sender_task = asyncio.create_task(sender())
        recv_task = asyncio.create_task(receiver())
        done, pending = await asyncio.wait({sender_task, recv_task}, return_when=asyncio.FIRST_COMPLETED)
        for task in pending:
            task.cancel()
        for task in done:
            try:
                task.result()
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
        async with self._lock:
            self._sessions.pop(session_id, None)
        return True

    def is_open(self, session_id: str) -> bool:
        runtime = self._sessions.get(session_id)
        if not runtime or runtime.closed:
            return False
        return runtime.process.poll() is None

    def find_active_session(self) -> str | None:
        for runtime in self._sessions.values():
            if runtime.closed or runtime.process.poll() is not None:
                continue
            return runtime.session_id
        return None

    def session_payload(self, session_id: str) -> dict[str, Any] | None:
        runtime = self._sessions.get(session_id)
        if not runtime:
            return None
        return {
            "session_id": runtime.session_id,
            "cwd": runtime.cwd,
            "command": runtime.command,
            "open": (not runtime.closed and runtime.process.poll() is None),
            "last_activity": runtime.last_activity,
            "started_at": runtime.started_at,
        }

    async def _cleanup_loop(self) -> None:
        while True:
            await asyncio.sleep(15)
            to_kill: list[str] = []
            async with self._lock:
                cutoff = time.time() - self._idle_timeout_seconds if self._idle_timeout_seconds > 0 else None
                for sid, runtime in list(self._sessions.items()):
                    if runtime.closed or runtime.process.poll() is not None:
                        to_kill.append(sid)
                    elif cutoff is not None and len(runtime.subscribers) == 0 and runtime.last_activity < cutoff:
                        to_kill.append(sid)
            for sid in to_kill:
                await self.kill(sid)


_manager: LocalTerminalManager | None = None


def get_local_terminal_manager() -> LocalTerminalManager:
    global _manager
    if _manager is None:
        _manager = LocalTerminalManager()
    return _manager
