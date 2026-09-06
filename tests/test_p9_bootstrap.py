"""Tests for P9: FastAPI lifespan bootstrap and uvicorn --reload support."""

from __future__ import annotations

import asyncio
import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from app.contracts import ToolName


def _get_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.mark.asyncio
async def test_import_inside_running_event_loop_and_lifespan(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Prove that app.main can be imported and bootstrapped from an active event loop without crashing."""
    import app.main

    # Before bootstrap, the registry holds code tools without crashing
    assert ToolName.KNOWLEDGE in app.main.tool_registry.names

    # Enter lifespan within this running event loop
    async with app.main.lifespan(app.main.app):
        assert ToolName.OMS in app.main.tool_registry.names
        assert ToolName.KNOWLEDGE in app.main.tool_registry.names
        assert app.main._bootstrapped is True


@pytest.mark.asyncio
async def test_lifespan_restores_disabled_code_tools(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Prove that disabled code tools recorded in DB are restored during bootstrap."""
    import app.main
    from app.db import tool_repository

    # Explicitly disable voc_tool in DB
    await tool_repository.set_code_tool_enabled(app.main.db, "voc_tool", False)
    try:
        # Reset bootstrapped flag to exercise bootstrap again
        app.main._bootstrapped = False
        async with app.main.lifespan(app.main.app):
            assert app.main.tool_registry.code_tool_enabled("voc_tool") is False
    finally:
        # Restore state
        await tool_repository.set_code_tool_enabled(app.main.db, "voc_tool", True)
        app.main.tool_registry.set_code_tool_enabled("voc_tool", True)


def test_ensure_bootstrapped_middleware_invokes_bootstrap() -> None:
    """Prove that requests through ASGI middleware invoke bootstrap even if lifespan was not entered."""
    import app.main

    client = TestClient(app.main.app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert app.main._bootstrapped is True
    assert ToolName.OMS in app.main.tool_registry.names


@pytest.mark.parametrize("reload", [False, True], ids=["no_reload", "reload"])
def test_uvicorn_process_startup_and_health(reload: bool) -> None:
    """Prove actual uvicorn process starts successfully with and without --reload and /health responds 200."""
    port = _get_free_port()
    with TemporaryDirectory() as tmpdir:
        db_path = str(Path(tmpdir) / "pea.db")
        state_key = Fernet.generate_key().decode("ascii")
        env = os.environ.copy()
        env["DB_PATH"] = db_path
        env["PEA_STATE_KEY"] = state_key

        cmd = [
            sys.executable,
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ]
        if reload:
            cmd.append("--reload")

        proc = subprocess.Popen(
            cmd,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        try:
            deadline = time.time() + 15
            served = False
            while time.time() < deadline:
                if proc.poll() is not None:
                    stdout, stderr = proc.communicate()
                    pytest.fail(
                        f"uvicorn (reload={reload}) exited prematurely with code {proc.returncode}:\n"
                        f"STDOUT:\n{stdout.decode('utf-8', errors='replace')}\n"
                        f"STDERR:\n{stderr.decode('utf-8', errors='replace')}"
                    )
                try:
                    with urllib.request.urlopen(
                        f"http://127.0.0.1:{port}/health", timeout=1
                    ) as resp:
                        if resp.status == 200:
                            data = resp.read().decode("utf-8")
                            assert '"status":"ok"' in data
                            served = True
                            break
                except Exception:
                    time.sleep(0.3)
            assert served, f"uvicorn (reload={reload}) timed out waiting for /health response"
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
