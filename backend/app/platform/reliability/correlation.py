from __future__ import annotations

from contextvars import ContextVar, Token
from uuid import UUID, uuid4

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

request_correlation_id: ContextVar[UUID | None] = ContextVar(
    "request_correlation_id", default=None
)


def current_correlation_id() -> UUID | None:
    return request_correlation_id.get()


def _accepted_correlation(headers: MutableHeaders) -> UUID:
    supplied = headers.get("X-Request-ID")
    if supplied:
        try:
            return UUID(supplied)
        except ValueError:
            pass
    return uuid4()


class CorrelationMiddleware:
    """Bind one safe UUID across an HTTP operation and its response."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        correlation_id = _accepted_correlation(MutableHeaders(scope=scope))
        token: Token[UUID | None] = request_correlation_id.set(correlation_id)

        async def send_with_correlation(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers["X-Request-ID"] = str(correlation_id)
            await send(message)

        try:
            await self.app(scope, receive, send_with_correlation)
        finally:
            request_correlation_id.reset(token)
