"""Tests for operation policy vocabulary (D1.4)."""

import pytest

from app.agent.operation_policy import (
    ClientContextKey,
    DEFAULT_POLICY,
    KNOWN_CLIENT_CONTEXT,
    OperationLimits,
    OperationPolicy,
    OperationSpec,
    dedupe_default,
)


class TestOperationPolicy:
    def test_enum_has_four_values(self) -> None:
        assert set(OperationPolicy.__members__.keys()) == {
            "GROUNDED_ANSWER",
            "WRITE_CONFIRM",
            "GUIDED_FLOW",
            "PLAIN_READ",
        }

    def test_values_are_lowercase_strings(self) -> None:
        assert OperationPolicy.GROUNDED_ANSWER.value == "grounded_answer"
        assert OperationPolicy.WRITE_CONFIRM.value == "write_confirm"
        assert OperationPolicy.GUIDED_FLOW.value == "guided_flow"
        assert OperationPolicy.PLAIN_READ.value == "plain_read"


class TestClientContext:
    def test_enum_has_lat_and_lon(self) -> None:
        assert set(ClientContextKey.__members__.keys()) == {"LAT", "LON"}
        assert ClientContextKey.LAT.value == "lat"
        assert ClientContextKey.LON.value == "lon"

    def test_known_context_set(self) -> None:
        assert KNOWN_CLIENT_CONTEXT == {"lat", "lon"}


class TestDedupeDefault:
    def test_plain_read_and_grounded_answer_are_true(self) -> None:
        assert dedupe_default(OperationPolicy.PLAIN_READ) is True
        assert dedupe_default(OperationPolicy.GROUNDED_ANSWER) is True

    def test_write_confirm_is_false(self) -> None:
        assert dedupe_default(OperationPolicy.WRITE_CONFIRM) is False

    def test_guided_flow_is_false(self) -> None:
        # guided_flow is not mentioned in §3.3; default to False (non-read)
        assert dedupe_default(OperationPolicy.GUIDED_FLOW) is False


class TestOperationLimits:
    def test_max_calls_per_turn_must_be_positive(self) -> None:
        OperationLimits(max_calls_per_turn=1)   # ok
        OperationLimits(max_calls_per_turn=None)  # ok
        with pytest.raises(ValueError, match="positive"):
            OperationLimits(max_calls_per_turn=0)
        with pytest.raises(ValueError, match="positive"):
            OperationLimits(max_calls_per_turn=-1)

    def test_dedupe_identical_input_must_be_boolean(self) -> None:
        OperationLimits(dedupe_identical_input=True)   # ok
        OperationLimits(dedupe_identical_input=False)  # ok
        OperationLimits(dedupe_identical_input=None)   # ok
        with pytest.raises(ValueError, match="boolean"):
            OperationLimits(dedupe_identical_input="true")  # type: ignore

    def test_effective_dedupe_uses_declared_if_set(self) -> None:
        limits = OperationLimits(dedupe_identical_input=True)
        assert limits.effective_dedupe(OperationPolicy.PLAIN_READ) is True
        assert limits.effective_dedupe(OperationPolicy.WRITE_CONFIRM) is True

        limits = OperationLimits(dedupe_identical_input=False)
        assert limits.effective_dedupe(OperationPolicy.PLAIN_READ) is False
        assert limits.effective_dedupe(OperationPolicy.GROUNDED_ANSWER) is False

    def test_effective_dedupe_falls_back_to_policy_default(self) -> None:
        limits = OperationLimits()
        assert limits.effective_dedupe(OperationPolicy.PLAIN_READ) is True
        assert limits.effective_dedupe(OperationPolicy.GROUNDED_ANSWER) is True
        assert limits.effective_dedupe(OperationPolicy.WRITE_CONFIRM) is False
        assert limits.effective_dedupe(OperationPolicy.GUIDED_FLOW) is False


class TestOperationSpec:
    def test_default_policy_is_plain_read(self) -> None:
        spec = OperationSpec()
        assert spec.policy == DEFAULT_POLICY
        assert spec.policy == OperationPolicy.PLAIN_READ

    def test_limits_optional(self) -> None:
        spec = OperationSpec()
        assert spec.limits is None

        limits = OperationLimits(max_calls_per_turn=2)
        spec = OperationSpec(limits=limits)
        assert spec.limits == limits

    def test_client_context_keys_must_be_known(self) -> None:
        # valid
        spec = OperationSpec(client_context={"lat": "latitude", "lon": "longitude"})
        assert spec.client_context == {"lat": "latitude", "lon": "longitude"}

        # reject unknown key
        with pytest.raises(ValueError, match="not in known closed set"):
            OperationSpec(client_context={"foo": "bar"})

        # field name must be non-empty
        with pytest.raises(ValueError, match="non-empty string"):
            OperationSpec(client_context={"lat": ""})

    def test_client_context_uses_mapping_type(self) -> None:
        # dict is fine; Mapping is accepted
        spec = OperationSpec(client_context={"lat": "lat"})
        assert spec.client_context["lat"] == "lat"

    def test_max_calls_per_turn_reads_through_limits(self) -> None:
        assert OperationSpec().max_calls_per_turn is None
        spec = OperationSpec(limits=OperationLimits(max_calls_per_turn=2))
        assert spec.max_calls_per_turn == 2

    def test_effective_dedupe_reads_through_limits_or_policy_default(self) -> None:
        assert OperationSpec(policy=OperationPolicy.PLAIN_READ).effective_dedupe() is True
        assert OperationSpec(policy=OperationPolicy.WRITE_CONFIRM).effective_dedupe() is False
        spec = OperationSpec(
            policy=OperationPolicy.PLAIN_READ,
            limits=OperationLimits(dedupe_identical_input=False),
        )
        assert spec.effective_dedupe() is False