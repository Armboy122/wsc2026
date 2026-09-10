from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Annotated
from uuid import UUID

from fastapi import Depends, FastAPI, Header
from fastapi.responses import JSONResponse
from pydantic import Field

from .bootstrap import Settings, authenticate, build
from .contracts import Answer, DomainError, Model, Principal


class AskRequest(Model):
    question: str = Field(min_length=1, max_length=2000)
    session_id: UUID | None = None


def create_app(settings: Settings | None = None, service=None):
    settings = settings or Settings.from_env()
    service = service or build(settings)

    @asynccontextmanager
    async def lifespan(app):
        await service.sessions.initialize()
        yield
        await service.provider.close()

    app = FastAPI(title="Knowledge Lab", lifespan=lifespan)

    async def principal(authorization: Annotated[str | None, Header()] = None):
        token = authorization[7:] if authorization and authorization.startswith("Bearer ") else None
        return authenticate(settings, token)

    @app.exception_handler(DomainError)
    async def domain_error(request, error):
        return JSONResponse(status_code=error.status, content={"code": error.code, "message": error.message})

    @app.get("/health")
    async def health():
        return {"status": "ok", "scope": "knowledge-only", "provider": settings.provider,
                "live_provider_verified": False}

    @app.get("/plugins")
    async def plugins(user: Principal = Depends(principal)):
        return service.registry.catalogue(user)

    @app.post("/ask", response_model=Answer)
    async def ask(body: AskRequest, user: Principal = Depends(principal)):
        return await service.ask(user, body.question, str(body.session_id) if body.session_id else None)

    @app.delete("/sessions/{session_id}", status_code=204)
    async def delete_session(session_id: UUID, user: Principal = Depends(principal)):
        await service.sessions.delete(user.id, str(session_id))

    return app
