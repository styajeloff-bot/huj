"""Internal API trailing-slash normalization.

Starlette normally fixes slash mismatches with an HTTP 307 redirect. Behind an
HTTPS ingress that redirect can leak the backend's HTTP scheme into Location,
so API clients should reach the matching route inside the ASGI app instead.
"""

from __future__ import annotations

from collections import deque
from urllib.parse import quote

from starlette.datastructures import URL
from starlette.routing import Router
from starlette.types import ASGIApp, Message, Receive, Scope, Send

_REDIRECT_URL_SAFE = ":/%#?=@[]!$&'()*+,;"


class ApiTrailingSlashMiddleware:
    """Rewrite `/api/` slash mismatches internally when the alternate route exists."""

    def __init__(self, app: ASGIApp, *, router: Router) -> None:
        self.app = app
        self.router = router

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        if not path.startswith("/api/"):
            await self.app(scope, receive, send)
            return

        alternate_path = self._alternate_path(path)
        consumed_before_routing: list[Message] = []
        retry_with_alternate = False

        async def recording_receive() -> Message:
            message = await receive()
            if "route" not in scope and "endpoint" not in scope:
                consumed_before_routing.append(dict(message))
            return message

        async def intercept_redirect(message: Message) -> None:
            nonlocal retry_with_alternate

            if message["type"] == "http.response.start":
                retry_with_alternate = self._is_slash_redirect(
                    scope,
                    message,
                    alternate_path=alternate_path,
                )

            if not retry_with_alternate:
                await send(message)

        await self.app(scope, recording_receive, intercept_redirect)
        if not retry_with_alternate:
            return

        replay = deque(consumed_before_routing)

        async def replay_receive() -> Message:
            if replay:
                return replay.popleft()
            return await receive()

        await self.app(
            self._scope_with_path(scope, alternate_path),
            replay_receive,
            send,
        )

    def _is_slash_redirect(
        self,
        scope: Scope,
        message: Message,
        *,
        alternate_path: str,
    ) -> bool:
        if (
            message.get("status") != 307
            or scope.get("router") is not self.router
            or "route" in scope
            or "endpoint" in scope
        ):
            return False

        expected_location = quote(
            str(URL(scope=self._scope_with_path(scope, alternate_path))),
            safe=_REDIRECT_URL_SAFE,
        ).encode("latin-1")
        return any(
            name.lower() == b"location" and value == expected_location
            for name, value in message.get("headers", [])
        )

    @staticmethod
    def _scope_with_path(scope: Scope, path: str) -> Scope:
        candidate_scope = dict(scope)
        current_path = scope.get("path", "")
        candidate_scope["path"] = path

        raw_path = scope.get("raw_path")
        if isinstance(raw_path, bytes):
            candidate_scope["raw_path"] = (
                raw_path.rstrip(b"/") if current_path.endswith("/") else raw_path + b"/"
            )

        return candidate_scope

    @staticmethod
    def _alternate_path(path: str) -> str:
        if path.endswith("/"):
            return path.rstrip("/")
        return f"{path}/"
