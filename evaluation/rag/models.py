"""Swappable answer/judge models plus the on-disk response cache.

Model specs are plain strings so switching provider never needs a code change:

- ``stub`` — deterministic, offline, used by tests and for pipeline smoke runs.
- ``pi:<provider/model>`` — a subprocess ``pi -p --model <provider/model>`` run.
- ``gemini:<name>`` — the google-genai SDK, key read from the environment only.

Real adapters construct nothing heavy (and touch no network) until the first call. Model
specs are never logged with credentials; the Gemini adapter reads ``GEMINI_API_KEY`` from the
process environment via the normal application settings, never from a file, and never prints
or stores it.

The answer and judge prompts share one ``ResponseCache`` under
``evaluation/rag/out/cache/``; entries are keyed by ``sha256(model spec, mode, prompt)`` so the
same question asked with a different model or mode is a cache miss.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from app.core.config import Settings

STUB = "stub"
PI = "pi"
GEMINI = "gemini"
MODEL_KINDS = (STUB, PI, GEMINI)

DEFAULT_PI_TIMEOUT_S = 600.0
DEFAULT_PI_ATTEMPTS = 3
STUB_ANSWER_TEXT = "ไม่พบข้อมูลในเอกสารที่ได้รับ กรุณาติดต่อ 1129"
STUB_JUDGE_VERDICT = "CORRECT"
STUB_JUDGE_REASON = "stub"


@dataclass(frozen=True)
class ModelSpec:
    """A parsed ``<kind>[:<name>]`` model spec."""

    kind: str
    name: str
    raw: str


@dataclass(frozen=True)
class ModelResponse:
    """One model reply with its measured latency and, when available, provider usage."""

    text: str
    latency_s: float
    usage: Mapping[str, int] | None = None
    cached: bool = False


def parse_model_spec(spec: str) -> ModelSpec:
    """Parse ``stub``, ``pi:<provider/model>`` or ``gemini:<name>``."""
    text = (spec or "").strip()
    if not text:
        raise ValueError("model spec must not be empty")
    kind, separator, name = text.partition(":")
    kind = kind.strip().lower()
    if not separator:
        if kind == STUB:
            return ModelSpec(STUB, STUB, text)
        raise ValueError(
            f"unsupported model spec {spec!r}: expected 'stub', 'pi:<provider/model>' "
            "or 'gemini:<name>'"
        )
    name = name.strip()
    if not name:
        raise ValueError(f"model spec {spec!r} is missing a model name")
    if kind not in (PI, GEMINI):
        raise ValueError(
            f"unsupported model spec {spec!r}: expected 'stub', 'pi:<provider/model>' "
            "or 'gemini:<name>'"
        )
    return ModelSpec(kind, name, text)


def cache_key(model: str, mode: str, prompt: str) -> str:
    """Stable cache key for one (model spec, mode, prompt) triple."""
    payload = json.dumps(
        {"model": model, "mode": mode, "prompt": prompt},
        ensure_ascii=False,
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class ResponseCache:
    """Tiny JSON response cache keyed by :func:`cache_key`, one file per entry."""

    def __init__(self, root: Path | str) -> None:
        self._root = Path(root)

    @property
    def root(self) -> Path:
        return self._root

    def path(self, key: str) -> Path:
        return self._root / f"{key}.json"

    def get(self, key: str) -> dict[str, object] | None:
        try:
            data = json.loads(self.path(key).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        return data if isinstance(data, dict) else None

    def put(self, key: str, value: Mapping[str, object]) -> None:
        self._root.mkdir(parents=True, exist_ok=True)
        path = self.path(key)
        temporary = path.with_suffix(".json.tmp")
        temporary.write_text(
            json.dumps(dict(value), ensure_ascii=False), encoding="utf-8"
        )
        os.replace(temporary, path)


@runtime_checkable
class AnswerModel(Protocol):
    """Turns a system + user prompt into an answer."""

    spec: str

    def answer(self, *, system: str, user: str) -> ModelResponse: ...


@runtime_checkable
class JudgeModel(Protocol):
    """Turns a system + user prompt into a raw (JSON) verdict."""

    spec: str

    def judge(self, *, system: str, user: str) -> ModelResponse: ...


class _BaseModel:
    """Shared prompt composition, disk caching and latency measurement."""

    def __init__(
        self,
        spec: str,
        *,
        cache: ResponseCache | None = None,
        mode: str = "default",
    ) -> None:
        self.spec = spec
        self._cache = cache
        self._mode = mode

    def answer(self, *, system: str, user: str) -> ModelResponse:
        return self._generate(system, user)

    def judge(self, *, system: str, user: str) -> ModelResponse:
        return self._generate(system, user)

    def _generate(self, system: str, user: str) -> ModelResponse:
        prompt = f"{system}\n\n{user}"
        key = cache_key(self.spec, self._mode, prompt)
        if self._cache is not None:
            cached = self._cache.get(key)
            if cached is not None:
                usage = cached.get("usage")
                return ModelResponse(
                    text=str(cached.get("text", "")),
                    latency_s=0.0,
                    usage=usage if isinstance(usage, dict) else None,
                    cached=True,
                )
        started = time.perf_counter()
        text, usage = self._call(system, user)
        response = ModelResponse(
            text=text,
            latency_s=round(time.perf_counter() - started, 3),
            usage=usage,
        )
        if self._cache is not None:
            self._cache.put(
                key,
                {"text": text, "usage": dict(usage) if usage else None,
                 "model": self.spec, "mode": self._mode},
            )
        return response

    def _call(self, system: str, user: str) -> tuple[str, Mapping[str, int] | None]:
        raise NotImplementedError


class StubModel(_BaseModel):
    """Deterministic offline model for tests and cold-pipeline smoke runs."""

    def __init__(
        self,
        *,
        spec: str = STUB,
        answer_text: str = STUB_ANSWER_TEXT,
        verdict: str = STUB_JUDGE_VERDICT,
        reason: str = STUB_JUDGE_REASON,
        cache: ResponseCache | None = None,
        mode: str = "default",
    ) -> None:
        super().__init__(spec, cache=cache, mode=mode)
        self._answer_text = answer_text
        self._verdict = verdict
        self._reason = reason

    def _call(self, system: str, user: str) -> tuple[str, Mapping[str, int] | None]:
        if "verdict" in system or "verdict" in user:
            return (
                json.dumps(
                    {"verdict": self._verdict, "reason": self._reason},
                    ensure_ascii=False,
                ),
                None,
            )
        return self._answer_text, None


class PiCliModel(_BaseModel):
    """Answer/judge through ``pi -p --model <provider/model>`` on the command line.

    The user prompt is written to a temporary file and attached with ``@file`` so very long
    long-context prompts never hit the argument-length limit. ``stdin`` is ``/dev/null`` so a
    detached subprocess can never wait on a terminal, and every attempt has a hard timeout.
    No credentials are handled here: ``pi`` uses its own configured provider auth.
    """

    def __init__(
        self,
        name: str,
        *,
        spec: str | None = None,
        cache: ResponseCache | None = None,
        mode: str = "default",
        command: str = "pi",
        thinking: str = "off",
        timeout_s: float = DEFAULT_PI_TIMEOUT_S,
        attempts: int = DEFAULT_PI_ATTEMPTS,
        extra_args: Sequence[str] = (),
        cwd: Path | str | None = None,
    ) -> None:
        super().__init__(spec or f"{PI}:{name}", cache=cache, mode=mode)
        if attempts < 1:
            raise ValueError("attempts must be at least 1")
        self.name = name
        self.command = command
        self.thinking = thinking
        self.timeout_s = timeout_s
        self.attempts = attempts
        self.extra_args = tuple(extra_args)
        self.cwd = cwd

    def _call(self, system: str, user: str) -> tuple[str, Mapping[str, int] | None]:
        with tempfile.TemporaryDirectory(prefix="pea-rag-eval-") as directory:
            prompt_path = Path(directory) / "prompt.md"
            prompt_path.write_text(user, encoding="utf-8")
            command = [
                self.command,
                "-p",
                "--no-session",
                "--no-tools",
                "--no-extensions",
                "--no-skills",
                "--no-prompt-templates",
                "--no-context-files",
                "--model",
                self.name,
                "--thinking",
                self.thinking,
                "--system-prompt",
                system,
                *self.extra_args,
                f"@{prompt_path}",
                "ตอบตามคำสั่งข้างต้น",
            ]
            last_error = ""
            for attempt in range(1, self.attempts + 1):
                try:
                    completed = subprocess.run(
                        command,
                        stdin=subprocess.DEVNULL,
                        capture_output=True,
                        text=True,
                        timeout=self.timeout_s,
                        cwd=str(self.cwd) if self.cwd is not None else directory,
                        check=False,
                    )
                except subprocess.TimeoutExpired:
                    last_error = f"timeout after {self.timeout_s:.0f}s"
                except OSError as exc:
                    last_error = f"could not run {self.command!r}: {type(exc).__name__}"
                else:
                    if completed.returncode == 0 and completed.stdout.strip():
                        return completed.stdout.strip(), None
                    last_error = completed.stderr.strip()[-300:] or (
                        f"exit code {completed.returncode}"
                    )
                if attempt < self.attempts:
                    time.sleep(1.0)
        raise RuntimeError(f"pi model {self.name!r} failed: {last_error}")


class GeminiModel(_BaseModel):
    """Answer/judge through the google-genai SDK (``gemini:<name>``).

    The API key is read from ``GEMINI_API_KEY`` through the normal application settings on the
    first call only; it is never logged, returned, or written to any evaluation output. The
    SDK client is created lazily so importing this module and constructing the adapter stay
    offline.
    """

    def __init__(
        self,
        name: str,
        *,
        spec: str | None = None,
        cache: ResponseCache | None = None,
        mode: str = "default",
        api_key: str | None = None,
        client: Any | None = None,
    ) -> None:
        super().__init__(spec or f"{GEMINI}:{name}", cache=cache, mode=mode)
        self.name = name
        self._api_key = api_key
        self._client = client

    def _call(self, system: str, user: str) -> tuple[str, Mapping[str, int] | None]:
        client = self._ensure_client()
        from google.genai import types

        response = client.models.generate_content(
            model=self.name,
            contents=user,
            config=types.GenerateContentConfig(system_instruction=system),
        )
        text = getattr(response, "text", None) or ""
        return text, _gemini_usage(response)

    def _ensure_client(self) -> Any:
        if self._client is None:
            from google.genai import Client

            api_key = self._api_key or Settings.from_env().gemini_api_key
            if not api_key:
                raise RuntimeError(
                    "GEMINI_API_KEY is not set; real Gemini runs are an owner action"
                )
            self._client = Client(api_key=api_key)
        return self._client


def _gemini_usage(response: object) -> Mapping[str, int] | None:
    metadata = getattr(response, "usage_metadata", None)
    if metadata is None:
        return None
    usage: dict[str, int] = {}
    for name in ("prompt_token_count", "candidates_token_count", "total_token_count"):
        value = getattr(metadata, name, None)
        if isinstance(value, int):
            usage[name] = value
    return usage or None


def build_model(
    spec: str,
    *,
    cache: ResponseCache | None = None,
    mode: str = "default",
    **kwargs: Any,
) -> StubModel | PiCliModel | GeminiModel:
    """Construct the adapter for a model spec without calling it."""
    parsed = parse_model_spec(spec)
    if parsed.kind == STUB:
        return StubModel(spec=parsed.raw, cache=cache, mode=mode, **kwargs)
    if parsed.kind == PI:
        return PiCliModel(parsed.name, spec=parsed.raw, cache=cache, mode=mode, **kwargs)
    return GeminiModel(parsed.name, spec=parsed.raw, cache=cache, mode=mode, **kwargs)
