"""นโยบายเครือข่ายขาออกและกัน SSRF (CONTRACTS-V2 §7)

โมดูลนี้เป็น gate เดียวที่ executor ของ declarative tool (D2.4) ต้องผ่านก่อนยิง
HTTP ทุกครั้ง — ไม่มีทางลัด:

- **โหมด** มาจาก ``APP_ENV`` เท่านั้น (CONTRACTS-V2 §7.1):
  ``development`` ยิงได้ทุกที่ (localhost/private/http ได้หมด) ส่วนค่า
  อื่นที่ไม่ใช่ ``development`` (production/test/ไม่ตั้ง) = ถือเป็น
  ``production`` แบบ fail-closed
- **production**: ต้องเป็น ``https://`` + โดเมนอยู่ใน ``domain_allowlist``
  + IP ที่ resolve แล้ว (หรือ literal IP) ต้องไม่อยู่ใน blocklist §7.2
  (กัน DNS rebinding ด้วยการ resolve แล้วเทียบ IP ก่อนยิงเสมอ)
- **ใช้ ``ipaddress`` ใน stdlib** สำหรับทุกการตัดสินใจเรื่อง IP —
  ห้ามเขียน parser IP เอง เพราะโดนเทคนิคหลอก (octal/hex/IPv4-mapped IPv6)
- **เพดานทรัพยากร** (§7.4): timeout default 5s เพดานแข็ง 30s ·
  response 1 MB เพดานแข็ง 10 MB · retry 0 เสมอ · ไม่ตาม redirect
  (``follow_redirects=False``) — 3xx ถือว่า URL ผิด ต้องแก้ config

ทุก error ภาษาไทย ระบุเหตุผลที่ admin แก้ได้: ``โดเมนไม่อยู่ใน allowlist`` ·
``ปลายทางเป็น IP ภายใน`` · ``ไม่ใช่ HTTPS`` ฯลฯ (CONTRACTS-V2 §7.5)
"""

from __future__ import annotations

import ipaddress
import socket
from dataclasses import dataclass
from typing import Callable, Iterable
from urllib.parse import urlparse

MODE_DEVELOPMENT = "development"
MODE_PRODUCTION = "production"

# CONTRACTS-V2 §7.2 — blocklist ของ production
_BLOCKED_NETWORKS: tuple[ipaddress.IPv4Network | ipaddress.IPv6Network, ...] = (
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),  # cloud metadata (169.254.169.254)
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
)

# เพดานทรัพยากร (CONTRACTS-V2 §7.4)
DEFAULT_TIMEOUT_SECONDS = 5.0
HARD_TIMEOUT_SECONDS = 30.0
DEFAULT_MAX_RESPONSE_BYTES = 1_000_000  # 1 MB
HARD_MAX_RESPONSE_BYTES = 10_000_000  # 10 MB
RETRY_COUNT = 0
FOLLOW_REDIRECTS = False

_ALLOWED_SCHEMES = frozenset({"http", "https"})


class NetworkPolicyError(ValueError):
    """ปลายทาง/URL ไม่ผ่านนโยบายเครือข่ายขาออก

    ``reason`` เป็นรหัสที่เครื่องอ่านได้ (ใช้บันทึก POLICY_REJECTED ได้)
    ข้อความภาษาไทยบอกเหตุผลที่ admin แก้ได้
    """

    def __init__(self, reason: str, message: str) -> None:
        super().__init__(message)
        self.reason = reason
        self.message = message


@dataclass(frozen=True, slots=True)
class OutboundLimits:
    """เพดานทรัพยากรของคำขอขาออก 1 ครั้ง (executor ต้องใช้ค่านี้)

    ค่าที่ admin ตั้งได้ถูก clamp ไว้ด้วยเพดานแข็งเสมอ (CONTRACTS-V2 §7.4)
    """

    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS
    max_response_bytes: int = DEFAULT_MAX_RESPONSE_BYTES
    retries: int = RETRY_COUNT
    follow_redirects: bool = FOLLOW_REDIRECTS

    def __post_init__(self) -> None:
        # clamp ให้อยู่ในเพดานแข็ง และกันค่าที่ใช้ไม่ได้
        timeout = min(max(self.timeout_seconds, 0.1), HARD_TIMEOUT_SECONDS)
        max_bytes = min(max(self.max_response_bytes, 1), HARD_MAX_RESPONSE_BYTES)
        object.__setattr__(self, "timeout_seconds", timeout)
        object.__setattr__(self, "max_response_bytes", max_bytes)


Resolver = Callable[[str], list[str]]


def policy_mode(app_env: str | None) -> str:
    """โหมดจาก ``APP_ENV`` — เฉพาะ ``development`` เท่านั้นที่ไม่จำกัด

    ค่าอื่น (production/test/ไม่ตั้ง/ค่าผิด) = ``production`` แบบ fail-closed
    """
    if app_env is not None and app_env.strip().lower() == MODE_DEVELOPMENT:
        return MODE_DEVELOPMENT
    return MODE_PRODUCTION


def normalize_allowlist(allowlist: Iterable[str]) -> frozenset[str]:
    """ทำรายการโดเมนใน allowlist ให้สะอาดก่อนเปรียบเทียบ

    รับเฉพาะชื่อโดเมนเปล่า ๆ (เช่น ``example.com``) — ลดตัวพิมพ์เล็ก
    และตัด trailing dot ทิ้ง
    """
    cleaned: set[str] = set()
    for entry in allowlist:
        value = entry.strip().lower().rstrip(".")
        if value:
            cleaned.add(value)
    return frozenset(cleaned)


def check_url(
    url: str,
    *,
    app_env: str | None = None,
    allowlist: Iterable[str] = (),
) -> str:
    """ตรวจ URL ตอน save: รูปแบบ + scheme + credential + (production) HTTPS + allowlist

    คืน ``host`` ที่ถูก normalize แล้ว (ใช้ตอน execute ต่อได้)
    """
    mode = policy_mode(app_env)
    parsed = urlparse(url)
    scheme = parsed.scheme.lower()
    host = (parsed.hostname or "").lower()

    if scheme not in _ALLOWED_SCHEMES or not host or not parsed.netloc:
        raise NetworkPolicyError(
            "invalid_url",
            "URL ไม่ถูกต้อง: ต้องเป็น http:// หรือ https:// แบบเต็ม (มีโดเมน)",
        )
    if parsed.username is not None or parsed.password is not None:
        raise NetworkPolicyError(
            "credentials_in_url",
            "URL ต้องไม่มีชื่อผู้ใช้/รหัสผ่านฝังอยู่",
        )
    if mode == MODE_PRODUCTION and scheme != "https":
        raise NetworkPolicyError("not_https", "ไม่ใช่ HTTPS: production ต้องใช้ https:// เท่านั้น")

    if mode == MODE_PRODUCTION:
        allow = normalize_allowlist(allowlist)
        if _is_ip_literal(host):
            # IP ภายในโดน blocklist ก่อนเสมอ ต่อให้ใส่ใน allowlist ก็ตาม
            check_resolved_ips([host], app_env=mode)
            if host not in allow:
                # literal IP ไม่เทียบ suffix แบบโดเมน — ต้องมีใน allowlist ตรง ๆ
                raise NetworkPolicyError(
                    "domain_not_in_allowlist",
                    f"โดเมนไม่อยู่ใน allowlist: {host} (URL ที่เป็น IP ตรง ๆ ต้องมี IP นั้นใน allowlist)",
                )
        elif not _host_in_allowlist(host, allow):
            raise NetworkPolicyError(
                "domain_not_in_allowlist",
                f"โดเมนไม่อยู่ใน allowlist: {host}",
            )
    return host


def check_resolved_ips(
    ips: Iterable[str],
    *,
    app_env: str | None = None,
) -> None:
    """ตรวจ IP (หลัง resolve DNS หรือ literal IP) กับ blocklist ของ production"""
    if policy_mode(app_env) != MODE_PRODUCTION:
        return
    for raw in ips:
        address = _parse_ip(raw)
        if address is None:
            continue  # ไม่ใช่ IP จริง ๆ ให้ข้ามไป — ตัวที่ตรวจคือ host/โดเมน
        if _is_blocked(address):
            raise NetworkPolicyError(
                "internal_ip",
                f"ปลายทางเป็น IP ภายใน/ไม่ปลอดภัย: {address}",
            )


def enforce_outbound_request(
    url: str,
    *,
    app_env: str | None = None,
    allowlist: Iterable[str] = (),
    resolved_ips: Iterable[str] | None = None,
    resolver: Resolver | None = None,
) -> None:
    """ตรวจครบตอน execute ก่อนยิง HTTP (CONTRACTS-V2 §7.3)

    1. ตรวจ URL (scheme/HTTPS/allowlist/credential) เหมือนตอน save
    2. resolve DNS ของ hostname แล้วเทียบ IP กับ blocklist ทุกครั้ง
       (กัน DNS rebinding) — ถ้า ``resolved_ips`` ส่งเข้ามาให้ใช้ค่านั้น
    3. development = ไม่จำกัด (ผ่าน URL ตรวจรูปแบบเท่านั้น)
    """
    mode = policy_mode(app_env)
    host = check_url(url, app_env=mode, allowlist=allowlist)
    if mode == MODE_DEVELOPMENT:
        return

    if _is_ip_literal(host):
        ips = [host]
    elif resolved_ips is not None:
        ips = list(resolved_ips)
    else:
        ips = _resolve_host(host, resolver=resolver)
        if not ips:
            raise NetworkPolicyError(
                "dns_resolution_failed",
                f"ไม่สามารถ resolve โดเมนได้: {host}",
            )
    check_resolved_ips(ips, app_env=mode)


def _parse_ip(raw: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    """parse IP ด้วย ``ipaddress`` เท่านั้น (ห้ามเขียน parser เอง)

    จัดการ IPv4-mapped IPv6 (``::ffff:169.254.169.254``) โดยคลายกลับเป็น IPv4
    เพื่อไม่ให้เลี่ยง blocklist ได้
    """
    value = raw.strip().lower()
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        return None
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped is not None:
        return address.ipv4_mapped
    return address


def _is_blocked(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return any(net.version == address.version and address in net for net in _BLOCKED_NETWORKS)


def _is_ip_literal(host: str) -> bool:
    return _parse_ip(host) is not None


def _host_in_allowlist(host: str, allowlist: frozenset[str]) -> bool:
    """โดเมนตรงเป๊ะ หรือเป็น subdomain ของโดเมนใน allowlist

    ``api.example.com`` เข้าได้ถ้า allowlist มี ``example.com``
    """
    if host in allowlist:
        return True
    return any(host.endswith(f".{entry}") for entry in allowlist)


def _resolve_host(host: str, *, resolver: Resolver | None) -> list[str]:
    """resolve DNS ผ่าน stdlib (socket) — executor ใช้ค่านี้เทียบ blocklist ก่อนยิง"""
    if resolver is not None:
        return list(resolver(host))
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        return []
    seen: list[str] = []
    for info in infos:
        raw = info[4][0]
        if raw not in seen:
            seen.append(raw)
    return seen
