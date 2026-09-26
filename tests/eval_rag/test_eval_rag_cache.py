"""Response-cache keying and the model-level cache round trip."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from evaluation.rag.models import (
    ResponseCache,
    StubModel,
    cache_key,
    parse_model_spec,
)


def test_cache_key_is_stable_and_input_sensitive() -> None:
    base = cache_key("stub", "hybrid_qafirst", "prompt")
    assert base == cache_key("stub", "hybrid_qafirst", "prompt")
    assert base != cache_key("other", "hybrid_qafirst", "prompt")
    assert base != cache_key("stub", "longctx_qafirst", "prompt")
    assert base != cache_key("stub", "hybrid_qafirst", "other prompt")


def test_response_cache_round_trip(tmp_path: Path) -> None:
    cache = ResponseCache(tmp_path)
    key = cache_key("stub", "mode", "prompt")
    assert cache.get(key) is None

    cache.put(key, {"text": "hello", "usage": {"input": 1}})
    stored = cache.get(key)
    assert stored is not None
    assert stored["text"] == "hello"
    assert cache.path(key).exists()
    assert cache.path(key).parent == tmp_path


class _CountingStub(StubModel):
    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.calls = 0

    def _call(self, system: str, user: str):
        self.calls += 1
        return super()._call(system, user)


def test_same_prompt_hits_cache_and_mode_misses(tmp_path: Path) -> None:
    cache = ResponseCache(tmp_path)

    first = _CountingStub(cache=cache, mode="hybrid_qafirst")
    answer_one = first.answer(system="s", user="u")
    answer_two = first.answer(system="s", user="u")
    assert answer_one.cached is False
    assert answer_two.cached is True
    assert answer_two.text == answer_one.text
    assert first.calls == 1

    other_mode = _CountingStub(cache=cache, mode="longctx_qafirst")
    assert other_mode.answer(system="s", user="u").cached is False
    assert other_mode.calls == 1


def test_judge_and_answer_prompts_do_not_share_a_cache_entry(tmp_path: Path) -> None:
    cache = ResponseCache(tmp_path)
    model = _CountingStub(cache=cache, mode="hybrid_qafirst")

    model.answer(system="s", user="u")
    model.judge(system="j", user="v")
    assert model.calls == 2


def test_model_specs_parse_without_constructing_a_provider() -> None:
    assert parse_model_spec("stub").kind == "stub"
    pi_spec = parse_model_spec("pi:maxplus/deepseek-v4.1-flash")
    assert pi_spec.kind == "pi"
    assert pi_spec.name == "maxplus/deepseek-v4.1-flash"
    gemini_spec = parse_model_spec("gemini:gemini-3.6-flash")
    assert gemini_spec.kind == "gemini"
    assert gemini_spec.name == "gemini-3.6-flash"
