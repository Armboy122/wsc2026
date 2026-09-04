"""ทดสอบนโยบายเครือข่ายขาออก (network_policy) — CONTRACTS-V2 §7

🔒 security boundary: SSRF blocking — งาน D1.3 / T0.5
เทสบังคับ: บล็อก 169.254.169.254 · บล็อก private range ·
http:// บน production = reject · localhost บน development = ผ่าน
"""

from __future__ import annotations

import pytest

from app.tools.network_policy import (
    DEFAULT_MAX_RESPONSE_BYTES,
    DEFAULT_TIMEOUT_SECONDS,
    FOLLOW_REDIRECTS,
    HARD_MAX_RESPONSE_BYTES,
    HARD_TIMEOUT_SECONDS,
    RETRY_COUNT,
    MODE_DEVELOPMENT,
    MODE_PRODUCTION,
    NetworkPolicyError,
    OutboundLimits,
    check_resolved_ips,
    check_url,
    enforce_outbound_request,
    policy_mode,
)


def _reason(exc_info: pytest.ExceptionInfo[NetworkPolicyError]) -> str:
    return exc_info.value.reason


# ---------------------------------------------------------------------------
# โหมดจาก APP_ENV
# ---------------------------------------------------------------------------


def test_policy_mode_development():
    assert policy_mode("development") == MODE_DEVELOPMENT
    assert policy_mode("DEVELOPMENT") == MODE_DEVELOPMENT


@pytest.mark.parametrize("value", ["production", "prod", "test", "staging", "", None])
def test_policy_mode_fail_closed_to_production(value):
    # ค่าที่ไม่ใช่ development ตรง ๆ = production (fail-closed)
    assert policy_mode(value) == MODE_PRODUCTION


# ---------------------------------------------------------------------------
# development = ไม่จำกัด
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1:8080/api",
        "http://localhost:8000/x",
        "http://169.254.169.254/latest/meta-data",
        "http://192.168.1.10/private",
        "https://api.example.com/v1",
    ],
)
def test_development_allows_localhost_private_and_http(url: str):
    # ไม่ raise = ผ่าน
    enforce_outbound_request(url, app_env="development")


# ---------------------------------------------------------------------------
# production: บล็อก cloud metadata / private range / http
# ---------------------------------------------------------------------------


def test_production_blocks_cloud_metadata_ip():
    with pytest.raises(NetworkPolicyError) as exc_info:
        enforce_outbound_request(
            "https://169.254.169.254/latest/meta-data",
            app_env="production",
        )
    assert _reason(exc_info) == "internal_ip"
    assert "169.254.169.254" in str(exc_info.value)


@pytest.mark.parametrize("ip", ["10.1.2.3", "172.16.0.1", "192.168.1.10", "127.0.0.1"])
def test_production_blocks_private_and_loopback_ranges(ip: str):
    with pytest.raises(NetworkPolicyError) as exc_info:
        enforce_outbound_request(f"https://{ip}/x", app_env="production")
    assert _reason(exc_info) == "internal_ip"


def test_production_blocks_http_even_when_domain_allowlisted():
    with pytest.raises(NetworkPolicyError) as exc_info:
        enforce_outbound_request(
            "http://api.example.com/v1",
            app_env="production",
            allowlist=["api.example.com"],
        )
    assert _reason(exc_info) == "not_https"
    assert "HTTPS" in str(exc_info.value)


def test_production_blocks_domain_not_in_allowlist():
    with pytest.raises(NetworkPolicyError) as exc_info:
        enforce_outbound_request(
            "https://evil.example.net/x",
            app_env="production",
            allowlist=["api.example.com"],
        )
    assert _reason(exc_info) == "domain_not_in_allowlist"


def test_production_allows_allowlisted_domain_when_dns_clean():
    enforce_outbound_request(
        "https://api.example.com/v1",
        app_env="production",
        allowlist=["example.com"],
        resolved_ips=["93.184.216.34"],
    )


def test_production_blocks_domain_resolving_to_private_ip():
    # กัน DNS rebinding: resolve แล้วได้ IP ภายใน = บล็อก
    with pytest.raises(NetworkPolicyError) as exc_info:
        enforce_outbound_request(
            "https://api.example.com/v1",
            app_env="production",
            allowlist=["example.com"],
            resolved_ips=["192.168.0.5"],
        )
    assert _reason(exc_info) == "internal_ip"


def test_production_blocks_ipv4_mapped_ipv6_metadata():
    # encoding trick: ::ffff:169.254.169.254 ต้องโดนบล็อกเหมือน IPv4 ตรง ๆ
    with pytest.raises(NetworkPolicyError) as exc_info:
        enforce_outbound_request(
            "https://api.example.com/v1",
            app_env="production",
            allowlist=["example.com"],
            resolved_ips=["::ffff:169.254.169.254"],
        )
    assert _reason(exc_info) == "internal_ip"


def test_production_blocklist_overrides_allowlist():
    # ใส่ IP ภายในใน allowlist เองก็ยังโดนบล็อก
    with pytest.raises(NetworkPolicyError) as exc_info:
        enforce_outbound_request(
            "https://169.254.169.254/x",
            app_env="production",
            allowlist=["169.254.169.254"],
        )
    assert _reason(exc_info) == "internal_ip"


def test_check_url_returns_normalized_host():
    host = check_url(
        "https://API.Example.com/v1",
        app_env="production",
        allowlist=["example.com"],
    )
    assert host == "api.example.com"


# ---------------------------------------------------------------------------
# URL รูปแบบ / credential (ทั้งสองโหมด)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "url",
    [
        "not-a-url",
        "ftp://example.com/file",
        "//example.com/no-scheme",
        "https://",
        "https://user:pass@example.com/x",
    ],
)
def test_invalid_url_or_credentials_rejected_in_both_modes(url: str):
    for env in ("development", "production"):
        with pytest.raises(NetworkPolicyError):
            enforce_outbound_request(url, app_env=env)


def test_credentials_reason():
    with pytest.raises(NetworkPolicyError) as exc_info:
        check_url("https://admin:s3cret@example.com/x", app_env="production", allowlist=["example.com"])
    assert _reason(exc_info) == "credentials_in_url"


# ---------------------------------------------------------------------------
# เพดานทรัพยากร (CONTRACTS-V2 §7.4)
# ---------------------------------------------------------------------------


def test_outbound_limits_defaults():
    limits = OutboundLimits()
    assert limits.timeout_seconds == DEFAULT_TIMEOUT_SECONDS == 5.0
    assert limits.max_response_bytes == DEFAULT_MAX_RESPONSE_BYTES == 1_000_000
    assert limits.retries == RETRY_COUNT == 0
    assert limits.follow_redirects is FOLLOW_REDIRECTS is False


def test_outbound_limits_clamped_to_hard_caps():
    limits = OutboundLimits(timeout_seconds=300.0, max_response_bytes=100_000_000)
    assert limits.timeout_seconds == HARD_TIMEOUT_SECONDS == 30.0
    assert limits.max_response_bytes == HARD_MAX_RESPONSE_BYTES == 10_000_000


def test_outbound_limits_reject_zero_or_negative():
    limits = OutboundLimits(timeout_seconds=0.0, max_response_bytes=-5)
    assert limits.timeout_seconds == 0.1  # floor กันค่าที่ใช้ไม่ได้
    assert limits.max_response_bytes == 1


def test_hard_cap_values_match_contract():
    assert DEFAULT_TIMEOUT_SECONDS == 5
    assert HARD_TIMEOUT_SECONDS == 30
    assert DEFAULT_MAX_RESPONSE_BYTES == 1_000_000  # 1 MB
    assert HARD_MAX_RESPONSE_BYTES == 10_000_000  # 10 MB
    assert RETRY_COUNT == 0
    assert FOLLOW_REDIRECTS is False


def test_check_resolved_ips_allows_public_ip_on_production():
    # ผ่านเพราะไม่ใช่ IP ใน blocklist
    check_resolved_ips(["93.184.216.34"], app_env="production")


def test_check_resolved_ips_noop_in_development():
    check_resolved_ips(["169.254.169.254", "10.0.0.1"], app_env="development")


def test_error_message_is_thai():
    with pytest.raises(NetworkPolicyError) as exc_info:
        enforce_outbound_request("http://api.example.com", app_env="production")
    message = str(exc_info.value)
    assert any("\u0e01" <= ch <= "\u0e5b" for ch in message)
