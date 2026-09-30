"""Bounded access to explicitly permitted HTTPS sources."""

from dataclasses import dataclass, field
from http.client import HTTPResponse
import ipaddress
import socket
import time
from typing import Callable, Mapping, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlsplit
from urllib.request import Request, build_opener


class SourceError(ValueError):
    """Raised when a source request violates policy or cannot be completed."""


@dataclass(frozen=True)
class SourcePolicy:
    allowed_hosts: frozenset[str]
    max_response_bytes: int = 1_000_000
    timeout_seconds: float = 15.0
    max_pages: int = 20
    max_retries: int = 2
    max_backoff_seconds: float = 2.0

    def __post_init__(self):
        hosts = frozenset(host.lower().rstrip(".") for host in self.allowed_hosts)
        if not hosts or any(not host or ":" in host for host in hosts):
            raise SourceError("allowed_hosts must contain DNS hostnames")
        if self.max_response_bytes <= 0 or self.max_pages <= 0:
            raise SourceError("source limits must be positive")
        if self.timeout_seconds <= 0 or self.max_retries < 0:
            raise SourceError("timeout and retry limits are invalid")
        if self.max_backoff_seconds < 0:
            raise SourceError("backoff limit must not be negative")
        object.__setattr__(self, "allowed_hosts", hosts)


@dataclass(frozen=True)
class SourceResponse:
    status: int
    headers: Mapping[str, str]
    body: bytes
    url: str


class SourceTransport(Protocol):
    def __call__(self, request: Request, timeout: float) -> object:
        ...


def _host_is_public(hostname: str) -> bool:
    try:
        addresses = {
            info[4][0]
            for info in socket.getaddrinfo(hostname, None, type=socket.SOCK_STREAM)
        }
    except OSError as exc:
        raise SourceError("source host could not be resolved") from exc
    if not addresses:
        raise SourceError("source host could not be resolved")
    for address in addresses:
        try:
            parsed = ipaddress.ip_address(address.split("%", 1)[0])
        except ValueError as exc:
            raise SourceError("source host resolved to an invalid address") from exc
        if (
            parsed.is_private
            or parsed.is_loopback
            or parsed.is_link_local
            or parsed.is_reserved
            or parsed.is_unspecified
            or parsed.is_multicast
        ):
            return False
    return True


def _validate_url(url: str, policy: SourcePolicy) -> str:
    try:
        parts = urlsplit(url)
        hostname = parts.hostname
        port = parts.port
    except (TypeError, ValueError) as exc:
        raise SourceError("source URL is invalid") from exc
    if (
        parts.scheme.lower() != "https"
        or not hostname
        or parts.username is not None
        or parts.password is not None
        or port not in (None, 443)
    ):
        raise SourceError("source URLs must use HTTPS without credentials or custom ports")
    hostname = hostname.encode("idna").decode("ascii").lower().rstrip(".")
    if hostname not in policy.allowed_hosts:
        raise SourceError("source host is not permitted")
    try:
        public = _host_is_public(hostname)
    except (UnicodeError, ValueError) as exc:
        raise SourceError("source host is invalid") from exc
    if not public:
        raise SourceError("private, loopback, or link-local source address is blocked")
    return parts._replace(scheme="https", netloc=hostname if port is None else f"{hostname}:443").geturl()


def _read_response(response: object, limit: int) -> bytes:
    chunks = []
    total = 0
    while True:
        chunk = response.read(min(64 * 1024, limit - total + 1))
        if not chunk:
            break
        total += len(chunk)
        if total > limit:
            raise SourceError(f"source response exceeds the {limit}-byte limit")
        chunks.append(chunk)
    return b"".join(chunks)


def _response_parts(response: object, url: str, limit: int) -> SourceResponse:
    if isinstance(response, SourceResponse):
        if len(response.body) > limit:
            raise SourceError(f"source response exceeds the {limit}-byte limit")
        headers = {str(key).lower(): str(value) for key, value in response.headers.items()}
        return SourceResponse(response.status, headers, response.body, url)
    status = int(getattr(response, "status", getattr(response, "code", 200)))
    headers = {str(key).lower(): str(value) for key, value in getattr(response, "headers", {}).items()}
    return SourceResponse(status, headers, _read_response(response, limit), url)


@dataclass
class PermittedSource:
    policy: SourcePolicy
    transport: SourceTransport | None = None
    sleep: Callable[[float], None] = time.sleep
    _opener: object = field(default_factory=build_opener, init=False, repr=False)

    def _request(self, url: str) -> SourceResponse:
        current = _validate_url(url, self.policy)
        attempts = 0
        while True:
            request = Request(current, headers={"Accept": "text/html, application/json"})
            try:
                response = (
                    self.transport(request, self.policy.timeout_seconds)
                    if self.transport is not None
                    else self._opener.open(request, timeout=self.policy.timeout_seconds)
                )
                result = _response_parts(response, current, self.policy.max_response_bytes)
            except HTTPError as exc:
                result = _response_parts(exc, current, self.policy.max_response_bytes)
            except (OSError, URLError, TimeoutError) as exc:
                if attempts >= self.policy.max_retries:
                    raise SourceError("source request failed") from exc
                result = None

            if result is not None and result.status not in {429, 500, 502, 503, 504}:
                if 300 <= result.status < 400:
                    location = result.headers.get("location")
                    if not location:
                        raise SourceError("source redirect has no destination")
                    current = _validate_url(urljoin(current, location), self.policy)
                    attempts += 1
                    if attempts > self.policy.max_retries + 1:
                        raise SourceError("source redirect limit exceeded")
                    continue
                if result.status >= 400:
                    raise SourceError(f"source returned HTTP {result.status}")
                return result

            if attempts >= self.policy.max_retries:
                if result is None:
                    raise SourceError("source request failed")
                raise SourceError(f"source returned HTTP {result.status}")
            delay = min(0.25 * (2**attempts), self.policy.max_backoff_seconds)
            if delay:
                self.sleep(delay)
            attempts += 1

    def fetch(self, url: str) -> SourceResponse:
        return self._request(url)

    def fetch_pages(
        self, url: str, next_url: Callable[[SourceResponse], str | None]
    ) -> list[SourceResponse]:
        pages = []
        current = url
        while current is not None and len(pages) < self.policy.max_pages:
            response = self.fetch(current)
            pages.append(response)
            current = next_url(response)
        if current is not None:
            raise SourceError(f"source exceeds the {self.policy.max_pages}-page limit")
        return pages
