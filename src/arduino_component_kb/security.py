"""Same-origin enforcement and browser security headers."""

from __future__ import annotations

from urllib.parse import urlsplit

from starlette.datastructures import Headers, MutableHeaders
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

CONTENT_SECURITY_POLICY = (
    "default-src 'self'; "
    "base-uri 'none'; "
    "object-src 'none'; "
    "frame-ancestors 'none'; "
    "form-action 'self'; "
    "script-src 'self'; "
    "style-src 'self'; "
    "img-src 'self' data: blob:; "
    "font-src 'self'; "
    "connect-src 'self'; "
    "media-src 'self' blob:"
)

SECURITY_HEADERS = {
    "Content-Security-Policy": CONTENT_SECURITY_POLICY,
    "Cross-Origin-Opener-Policy": "same-origin",
    "Permissions-Policy": "camera=(), geolocation=(), microphone=()",
    "Referrer-Policy": "no-referrer",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
}


def is_same_origin(origin: str, scheme: str, host: str) -> bool:
    """Compare a browser Origin with the externally visible request origin."""
    if not origin or origin == "null" or len(origin) > 512 or not host or len(host) > 512:
        return False
    try:
        parsed = urlsplit(origin)
        port = parsed.port
    except ValueError:
        return False
    if (
        parsed.scheme not in {"http", "https"}
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        return False
    normalized_port = port or (443 if parsed.scheme == "https" else 80)
    try:
        request = urlsplit(f"//{host}")
        request_port = request.port or (443 if scheme == "https" else 80)
    except ValueError:
        return False
    if request.username is not None or request.password is not None or request.path:
        return False
    return (
        parsed.scheme == scheme
        and parsed.hostname is not None
        and request.hostname is not None
        and parsed.hostname.casefold() == request.hostname.casefold()
        and normalized_port == request_port
    )


class BrowserSecurityMiddleware:
    """Deny cross-origin browser requests and attach defense-in-depth headers."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        request_headers = Headers(scope=scope)
        origin = request_headers.get("origin")
        scheme = request_headers.get("x-forwarded-proto", scope.get("scheme", "http"))
        host = request_headers.get("host", "")
        if origin is not None and not is_same_origin(origin, scheme, host):
            response = JSONResponse(
                {"detail": {"code": "cross_origin_forbidden"}},
                status_code=403,
                headers=SECURITY_HEADERS,
            )
            await response(scope, receive, send)
            return

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                response_headers = MutableHeaders(scope=message)
                for name, value in SECURITY_HEADERS.items():
                    response_headers[name] = value
            await send(message)

        await self.app(scope, receive, send_with_headers)
