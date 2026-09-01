"""การตรวจสอบเมื่อเริ่มต้นและการเชื่อมต่อ bootstrap สำหรับแพลตฟอร์ม FastAPI"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI

from app.contracts import ToolName
from app.core.config import Settings, load_settings
from app.core.errors import register_exception_handlers
from app.core.logging import configure_logging, get_logger
from app.core.middleware import RequestIdMiddleware, add_cors_middleware

logger = get_logger(__name__)

# Knowledge เป็น built-in ที่ต้องมีเสมอ ส่วนเครื่องมือปฏิบัติการมาจากปลั๊กอินที่เปิดใช้งาน
REQUIRED_TOOLS: frozenset[ToolName] = frozenset({ToolName.KNOWLEDGE})


def _resolve_tool_names(tool_registry: Any) -> set[ToolName]:
    """อ่านชื่อเครื่องมือไม่ว่า registry จะเปิดเผยผ่าน callable seam หรือ property"""
    names_attr = getattr(tool_registry, "names", None)
    if names_attr is None:
        return set()
    names = names_attr() if callable(names_attr) else names_attr
    if not isinstance(names, set | frozenset):
        names = set(names)
    return set(names)


def validate_tool_registry(tool_registry: Any) -> None:
    """ตรวจสอบว่าเครื่องมือ built-in ที่จำเป็นถูกลงทะเบียนครบก่อนเปิดให้บริการ"""
    names = _resolve_tool_names(tool_registry)
    missing = set(REQUIRED_TOOLS) - names
    if missing:
        raise RuntimeError(
            f"registry เครื่องมือขาดรายการที่จำเป็น {sorted(n.value for n in missing)}, "
            f"แต่ได้รับ {sorted(getattr(n, 'value', str(n)) for n in names)}"
        )


def create_platform_app(settings: Settings | None = None) -> FastAPI:
    """สร้างแอป FastAPI พื้นฐานพร้อม middleware และตัวจัดการข้อยกเว้นของแพลตฟอร์ม"""
    settings = settings or load_settings()
    configure_logging(settings.log_level)

    app = FastAPI(
        title="PEA One Agent",
        version="0.1.0",
        docs_url="/docs" if settings.app_env == "development" else None,
        redoc_url="/redoc" if settings.app_env == "development" else None,
    )

    app.add_middleware(RequestIdMiddleware)
    add_cors_middleware(app, settings.cors_origins)
    register_exception_handlers(app)

    app.state.settings = settings
    return app


def startup_event(app: FastAPI, tool_registry: Any | None = None) -> None:
    """เรียกการตรวจสอบเมื่อเริ่มต้น และเชื่อมต่ออะแดปเตอร์หากผู้ดูแลส่งมาให้"""
    if tool_registry is not None:
        validate_tool_registry(tool_registry)
    logger.info("platform_startup_complete", extra={"simulation_mode": True})
