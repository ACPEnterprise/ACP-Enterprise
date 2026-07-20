from ipaddress import ip_address, ip_network
from starlette.datastructures import MutableHeaders
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.config import Settings, settings


class TrustedProxyMiddleware:
    def __init__(self, app: ASGIApp, configuration: Settings = settings) -> None:
        self.app = app
        self.configuration = configuration
        self.networks = tuple(
            ip_network(cidr, strict=False) for cidr in configuration.trusted_proxy_cidrs
        )

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = MutableHeaders(scope=scope)
        forwarded_for = headers.get("x-forwarded-for")
        forwarded_proto = headers.get("x-forwarded-proto")
        if not forwarded_for and not forwarded_proto:
            await self.app(scope, receive, send)
            return
        peer = scope.get("client")
        trusted = False
        if peer is not None:
            try:
                trusted = any(
                    ip_address(peer[0]) in network for network in self.networks
                )
            except ValueError:
                trusted = False
        if not self.configuration.trust_forwarded_headers or not trusted:
            response = JSONResponse(
                {"detail": "Untrusted forwarding headers."}, status_code=400
            )
            await response(scope, receive, send)
            return
        if forwarded_for:
            try:
                chain = [
                    ip_address(value.strip()) for value in forwarded_for.split(",")
                ]
            except ValueError:
                response = JSONResponse(
                    {"detail": "Invalid forwarding headers."}, status_code=400
                )
                await response(scope, receive, send)
                return
            client = next(
                (
                    address
                    for address in reversed(chain)
                    if not any(address in network for network in self.networks)
                ),
                chain[0],
            )
            scope["client"] = (str(client), peer[1] if peer else 0)
        if forwarded_proto:
            protocol = forwarded_proto.split(",", 1)[0].strip().lower()
            if protocol not in {"http", "https"}:
                response = JSONResponse(
                    {"detail": "Invalid forwarding headers."}, status_code=400
                )
                await response(scope, receive, send)
                return
            scope["scheme"] = protocol
        await self.app(scope, receive, send)


class SecurityHeadersMiddleware:
    def __init__(self, app: ASGIApp, configuration: Settings = settings) -> None:
        self.app = app
        self.configuration = configuration

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        async def send_with_headers(message: Message) -> None:
            if (
                message["type"] == "http.response.start"
                and self.configuration.security_headers_enabled
            ):
                headers = MutableHeaders(scope=message)
                headers["X-Content-Type-Options"] = "nosniff"
                headers["X-Frame-Options"] = "DENY"
                headers["Referrer-Policy"] = self.configuration.referrer_policy
                headers["Content-Security-Policy"] = (
                    self.configuration.content_security_policy
                )
                headers["Permissions-Policy"] = self.configuration.permissions_policy
                if self.configuration.hsts_enabled and scope.get("scheme") == "https":
                    value = f"max-age={self.configuration.hsts_max_age_seconds}"
                    if self.configuration.hsts_include_subdomains:
                        value += "; includeSubDomains"
                    if self.configuration.hsts_preload:
                        value += "; preload"
                    headers["Strict-Transport-Security"] = value
            await send(message)

        await self.app(scope, receive, send_with_headers)
