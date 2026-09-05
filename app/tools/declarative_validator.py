"""Shared validation boundary for declarative tools (CONTRACTS-V2 §1.3, §2, §3, §7)

ใช้ทั้งใน loader (app/agent/declarative_tools.py) และ future save path (D3.4 admin form)
เพื่อให้การ validate อยู่ที่จุดเดียว ไม่เกิด logic drift ระหว่างการโหลดและการบันทึก
"""

from __future__ import annotations

import re
from typing import Any, Iterable

from app.agent.operation_policy import KNOWN_CLIENT_CONTEXT, OperationPolicy
from app.agent.tool_shape import ToolOperationShape, ToolShape
from app.tools.network_policy import NetworkPolicyError, check_url
from app.tools.schema_subset import SchemaSubsetError, validate_schema_subset

_SLUG_PATTERN = re.compile(r"^[a-z0-9_-]{1,64}$")
_ALLOWED_POLICIES = frozenset(p.value for p in OperationPolicy)
_ALLOWED_MODES = frozenset({"read", "prepare", "submit"})
_ALLOWED_EXPOSURES = frozenset({"llm", "internal"})
_ALLOWED_HTTP_METHODS = frozenset({"GET", "POST", "PUT", "PATCH", "DELETE"})


class DeclarativeValidationError(ValueError):
    """Raised when a declarative tool definition fails validation."""


def validate_declarative_tool_shape(
    shape: ToolShape,
    *,
    app_env: str | None = None,
    allowlist: Iterable[str] = (),
) -> None:
    """Validate a ToolShape against all declarative tool requirements.

    Raises DeclarativeValidationError if any constraint is violated.
    """
    if not isinstance(shape.slug, str) or not _SLUG_PATTERN.match(shape.slug):
        raise DeclarativeValidationError(
            f"slug '{shape.slug}' ไม่ถูกต้อง: ต้องเป็นตัวพิมพ์เล็ก ตัวเลข _ หรือ - ความยาว 1-64 ตัวอักษร"
        )
    if not shape.display_name or len(shape.display_name) > 200:
        raise DeclarativeValidationError("displayName ต้องมีความยาว 1-200 ตัวอักษร")
    if shape.description is not None and len(shape.description) > 1000:
        raise DeclarativeValidationError("description ต้องมีความยาวไม่เกิน 1000 ตัวอักษร")
    if not shape.operations:
        raise DeclarativeValidationError("tool ต้องมีอย่างน้อยหนึ่ง operation")

    actions = [op.action for op in shape.operations]
    if len(actions) != len(set(actions)):
        raise DeclarativeValidationError(f"มี action ซ้ำใน tool เดียวกัน: {shape.slug}")

    action_set = set(actions)
    operations_by_action = {op.action: op for op in shape.operations}

    for op in shape.operations:
        _validate_operation(
            op,
            action_set=action_set,
            operations_by_action=operations_by_action,
            source=shape.source,
            app_env=app_env,
            allowlist=allowlist,
        )


def _validate_operation(
    op: ToolOperationShape,
    *,
    action_set: set[str],
    operations_by_action: dict[str, ToolOperationShape],
    source: str,
    app_env: str | None,
    allowlist: Iterable[str],
) -> None:
    if not op.action or len(op.action) > 64:
        raise DeclarativeValidationError("action ต้องมีความยาว 1-64 ตัวอักษร")

    if op.policy not in _ALLOWED_POLICIES:
        raise DeclarativeValidationError(
            f"policy '{op.policy}' ของ action '{op.action}' ไม่ถูกต้อง (ต้องเป็นหนึ่งใน {sorted(_ALLOWED_POLICIES)})"
        )

    if op.mode not in _ALLOWED_MODES:
        raise DeclarativeValidationError(
            f"mode '{op.mode}' ของ action '{op.action}' ไม่ถูกต้อง (ต้องเป็นหนึ่งใน {sorted(_ALLOWED_MODES)})"
        )

    if op.exposure not in _ALLOWED_EXPOSURES:
        raise DeclarativeValidationError(
            f"exposure '{op.exposure}' ของ action '{op.action}' ไม่ถูกต้อง (ต้องเป็นหนึ่งใน {sorted(_ALLOWED_EXPOSURES)})"
        )

    # Cross-validation: mode=submit MUST have exposure=internal
    if op.mode == "submit" and op.exposure != "internal":
        raise DeclarativeValidationError(
            f"action '{op.action}' เป็น mode: submit ต้องเป็น exposure: internal เท่านั้น"
        )

    # Cross-validation: submitAction and mode
    if op.mode == "prepare":
        if not op.submit_action:
            raise DeclarativeValidationError(
                f"action '{op.action}' เป็น mode: prepare ต้องระบุ submitAction"
            )
        if op.submit_action not in action_set:
            raise DeclarativeValidationError(
                f"submitAction '{op.submit_action}' ของ action '{op.action}' ไม่มีอยู่ใน tool นี้"
            )
        if op.policy != "write_confirm":
            raise DeclarativeValidationError(
                f"action '{op.action}' มี submitAction แต่ policy ต้องเป็น write_confirm"
            )
        target_submit = operations_by_action[op.submit_action]
        if target_submit.mode != "submit":
            raise DeclarativeValidationError(
                f"submitAction '{op.submit_action}' ต้องเป็น mode: submit (ปัจจุบันเป็น {target_submit.mode})"
            )
        if target_submit.policy != "write_confirm":
            raise DeclarativeValidationError(
                f"submitAction '{op.submit_action}' ต้องมี policy: write_confirm"
            )
    else:
        if op.submit_action is not None:
            raise DeclarativeValidationError(
                f"action '{op.action}' ไม่ใช่ mode: prepare ต้องไม่ระบุ submitAction"
            )

    # Cross-validation: write_confirm pairing for submit mode
    if op.policy == "write_confirm":
        if op.mode not in ("prepare", "submit"):
            raise DeclarativeValidationError(
                f"action '{op.action}' ประกาศ write_confirm แต่ mode ต้องเป็น prepare หรือ submit"
            )
        if op.mode == "submit":
            matching_prepares = [
                prep for prep in operations_by_action.values()
                if prep.mode == "prepare" and prep.submit_action == op.action and prep.policy == "write_confirm"
            ]
            if not matching_prepares:
                raise DeclarativeValidationError(
                    f"action '{op.action}' เป็น submit ของ write_confirm แต่ไม่มี prepare operation ที่ชี้มาหา"
                )

    # Cross-validation: clientContext
    if op.client_context is not None:
        if not isinstance(op.client_context, dict):
            raise DeclarativeValidationError(f"clientContext ของ action '{op.action}' ต้องเป็น object")
        for key, field_name in op.client_context.items():
            if key not in KNOWN_CLIENT_CONTEXT:
                raise DeclarativeValidationError(
                    f"clientContext ของ action '{op.action}' อ้าง context นอก enum ปิด: '{key}'"
                )
            if not field_name or not isinstance(field_name, str):
                raise DeclarativeValidationError(
                    f"clientContext ของ action '{op.action}' ต้องมีชื่อ field ที่เป็น string ไม่ว่าง"
                )

    # Schema validation: input_schema
    if not isinstance(op.input_schema, dict):
        raise DeclarativeValidationError(f"inputSchema ของ action '{op.action}' ต้องเป็น JSON object")
    try:
        validate_schema_subset(op.input_schema)
    except SchemaSubsetError as error:
        raise DeclarativeValidationError(
            f"inputSchema ของ action '{op.action}' ไม่ผ่าน schema subset validation: {error}"
        ) from error

    # Schema validation: output_schema
    if op.output_schema is not None and op.output_schema != {}:
        if not isinstance(op.output_schema, dict):
            raise DeclarativeValidationError(f"outputSchema ของ action '{op.action}' ต้องเป็น JSON object")
        try:
            validate_schema_subset(op.output_schema)
        except SchemaSubsetError as error:
            raise DeclarativeValidationError(
                f"outputSchema ของ action '{op.action}' ไม่ผ่าน schema subset validation: {error}"
            ) from error

    # HTTP config for source=db
    if source == "db":
        if op.mode == "prepare":
            if op.http_method is not None or op.url_template is not None:
                raise DeclarativeValidationError(
                    f"action '{op.action}' เป็น mode: prepare (source: db) ต้องมี httpMethod และ urlTemplate เป็น null"
                )
        else:
            if op.http_method is None or op.url_template is None:
                raise DeclarativeValidationError(
                    f"action '{op.action}' (source: db, mode: {op.mode}) ต้องมี httpMethod และ urlTemplate"
                )
            if op.http_method not in _ALLOWED_HTTP_METHODS:
                raise DeclarativeValidationError(
                    f"httpMethod '{op.http_method}' ของ action '{op.action}' ไม่ถูกต้อง (ต้องเป็นหนึ่งใน {sorted(_ALLOWED_HTTP_METHODS)})"
                )
            try:
                check_url(op.url_template, app_env=app_env, allowlist=allowlist)
            except NetworkPolicyError as error:
                raise DeclarativeValidationError(
                    f"urlTemplate ของ action '{op.action}' ไม่ผ่าน network policy: {error.message}"
                ) from error


def sanitize_validation_error_message(message: str) -> str:
    """Sanitize validation error messages for logging without leaking secrets/URLs/tokens."""
    clean = str(message)
    # Redact JWTs and bearer/token values
    clean = re.sub(r"eyJ[a-zA-Z0-9_\-\.]+", "[redacted_jwt]", clean)
    clean = re.sub(r"(?i)(bearer\s+|token=)[a-zA-Z0-9_\-\.]+", r"\1[redacted]", clean)
    # Redact query strings from URLs if any
    clean = re.sub(r"(\?[^ \n\r\t]+)", "?[redacted]", clean)
    # Redact basic auth in URLs if any
    clean = re.sub(r"://[^@\s]+@", "://[redacted]@", clean)
    # Redact full URLs to prevent leaking internal endpoints
    clean = re.sub(r"https?://[^\s)]+", "[url_redacted]", clean)
    return clean[:500]
