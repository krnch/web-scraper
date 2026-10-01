import socket
import time
from dataclasses import dataclass
from ipaddress import ip_address
from typing import Callable, Protocol
from urllib.error import HTTPError
from urllib.parse import urljoin, urlsplit
from urllib.request import HTTPErrorProcessor, HTTPHandler, HTTPRedirectHandler, HTTPSHandler, Request, build_opener


RETRYABLE_STATUS_CODES = frozenset({408, 429, 500, 502, 503, 504})
DEFAULT_USER_AGENT = "web-scraper/0.1"


class SourceError(ValueError):
    pass


@dataclass(frozen=True)
class SourcePolicy:
    source_id: str
    source_name: str
    start_url: str
    allowed_hosts: tuple[str, ...]
    input_format: str
    max_pages: int = 20
    timeout_seconds: float = 10.0
    max_response_bytes: int = 1_000_000
    max_redirects: int = 3
    max_retries: int = 2
    backoff_seconds: float = 0.25
    max_backoff_seconds: float = 2.0


@dataclass(frozen=True)
class HTTPResult:
    status: int
    headers: dict[str, str]
    body: bytes


class HTTPTransport(Protocol):
    def request(self, url: str, timeout_seconds: float, max_response_bytes: int) -> HTTPResult:
        pass


class _NoRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class UrllibTransport:
    def __init__(self, user_agent: str = DEFAULT_USER_AGENT):
        self._user_agent = user_agent
        self._opener = build_opener(
            HTTPHandler(),
            HTTPSHandler(),
            _NoRedirectHandler(),
            HTTPErrorProcessor(),
        )

    def request(self, url: str, timeout_seconds: float, max_response_bytes: int) -> HTTPResult:
        request = Request(url, method="GET", headers={"User-Agent": self._user_agent})
        try:
            with self._opener.open(request, timeout=timeout_seconds) as response:
                body = response.read(max_response_bytes + 1)
                return HTTPResult(
                    status=response.status,
                    headers={k.lower(): v for k, v in response.headers.items()},
                    body=body,
                )
        except HTTPError as exc:
            body = exc.read(max_response_bytes + 1) if exc.fp else b""
            return HTTPResult(
                status=exc.code,
                headers={k.lower(): v for k, v in exc.headers.items()},
                body=body,
            )


class PermittedSourceAdapter:
    def __init__(
        self,
        transport: HTTPTransport | None = None,
        resolver: Callable[..., list[tuple]] | None = None,
        sleeper: Callable[[float], None] | None = None,
        monotonic: Callable[[], float] | None = None,
    ):
        self._transport = transport or UrllibTransport()
        self._resolver = resolver or socket.getaddrinfo
        self._sleeper = sleeper or time.sleep
        self._monotonic = monotonic or time.monotonic

    def fetch_pages(self, policy: SourcePolicy):
        self._validate_policy(policy)
        deadline = self._monotonic() + policy.timeout_seconds
        url = policy.start_url
        redirects_seen = 0
        pages_fetched = 0

        while url and pages_fetched < policy.max_pages:
            current_url = self._validate_url(url, policy)
            attempt = 0
            while True:
                remaining = max(deadline - self._monotonic(), 0.0)
                if remaining <= 0:
                    raise SourceError("source fetch exceeded timeout")

                timeout = min(policy.timeout_seconds, remaining)
                try:
                    result = self._transport.request(current_url, timeout, policy.max_response_bytes)
                except OSError as exc:
                    if attempt < policy.max_retries:
                        self._sleeper(self._backoff_delay(policy, attempt))
                        attempt += 1
                        continue
                    raise SourceError(f"request failed for {current_url}: {exc}") from exc

                if len(result.body) > policy.max_response_bytes:
                    raise SourceError(
                        f"response exceeds max size ({policy.max_response_bytes} bytes) for {current_url}"
                    )

                status = result.status
                if 300 <= status < 400:
                    location = result.headers.get("location")
                    if not location:
                        raise SourceError(f"redirect response missing location for {current_url}")
                    redirects_seen += 1
                    if redirects_seen > policy.max_redirects:
                        raise SourceError(f"redirect limit exceeded for source {policy.source_id}")
                    current_url = self._validated_redirect_url(current_url, location, policy)
                    continue

                if status in RETRYABLE_STATUS_CODES and attempt < policy.max_retries:
                    self._sleeper(self._backoff_delay(policy, attempt))
                    attempt += 1
                    continue
                if status >= 400:
                    raise SourceError(f"request failed with HTTP {status} for {current_url}")

                pages_fetched += 1
                body = result.body.decode("utf-8")
                next_url = self._parse_next_url(result.headers.get("link"), current_url)
                if next_url:
                    next_url = self._validate_url(next_url, policy)
                yield body, policy.input_format
                url = next_url
                break

    def _backoff_delay(self, policy: SourcePolicy, attempt: int) -> float:
        return min(policy.max_backoff_seconds, policy.backoff_seconds * (2**attempt))

    def _parse_next_url(self, link_header: str | None, base_url: str) -> str | None:
        if not link_header:
            return None
        for raw_part in link_header.split(","):
            part = raw_part.strip()
            if "rel=\"next\"" not in part:
                continue
            if not part.startswith("<") or ">" not in part:
                continue
            target = part[1 : part.index(">")]
            return urljoin(base_url, target)
        return None

    def _validate_policy(self, policy: SourcePolicy) -> None:
        if policy.max_pages < 1 or policy.max_pages > 100:
            raise SourceError("policy max_pages must be between 1 and 100")
        if policy.timeout_seconds <= 0 or policy.max_response_bytes <= 0:
            raise SourceError("policy timeout/size limits must be positive")
        if policy.max_redirects < 0 or policy.max_retries < 0:
            raise SourceError("policy redirect/retry limits must be non-negative")
        if not policy.allowed_hosts:
            raise SourceError("policy must define allowed_hosts")

    def _validated_redirect_url(self, current_url: str, location: str, policy: SourcePolicy) -> str:
        redirected = urljoin(current_url, location)
        return self._validate_url(redirected, policy)

    def _validate_url(self, url: str, policy: SourcePolicy) -> str:
        parts = urlsplit(url)
        if parts.scheme.lower() != "https":
            raise SourceError(f"only https URLs are permitted for source {policy.source_id}")
        if parts.username is not None or parts.password is not None:
            raise SourceError("URLs with embedded credentials are not permitted")
        if not parts.hostname:
            raise SourceError("URL must include a hostname")
        hostname = parts.hostname.encode("idna").decode("ascii").lower()
        allowed_hosts = {item.encode("idna").decode("ascii").lower() for item in policy.allowed_hosts}
        if hostname not in allowed_hosts:
            raise SourceError(f"host is not in allowlist for source {policy.source_id}: {hostname}")

        port = parts.port or 443
        addresses = self._resolver(hostname, port, type=socket.SOCK_STREAM)
        if not addresses:
            raise SourceError(f"hostname did not resolve: {hostname}")
        for entry in addresses:
            ip_text = entry[4][0]
            self._validate_ip(ip_text)

        return url

    def _validate_ip(self, ip_text: str) -> None:
        ip = ip_address(ip_text)
        if (
            ip.is_loopback
            or ip.is_private
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_unspecified
            or ip.is_reserved
        ):
            raise SourceError(f"resolved private/link-local IP is not permitted: {ip_text}")
