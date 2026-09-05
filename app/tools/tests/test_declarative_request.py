"""ทดสอบกลไก "LLM เติมค่า" ที่เลือกใช้ — D2.6, ARCHITECTURE-V2.md §3.7

placeholder {field} ใน urlTemplate ดึงจาก input · ฟิลด์ที่เหลือไป query (GET/DELETE)
หรือ JSON body (POST/PUT/PATCH)
"""

from __future__ import annotations

import pytest

from app.tools.declarative_executor import DeclarativeToolAuth
from app.tools.declarative_request import UrlTemplateError, build_declarative_http_request


def test_get_substitutes_path_placeholder_and_puts_rest_in_query():
    request = build_declarative_http_request(
        http_method="get",
        url_template="https://api.example.com/facts/{factId}",
        input={"factId": "42", "maxLength": 100},
    )
    assert request.method == "GET"
    assert request.url == "https://api.example.com/facts/42"
    assert request.query == {"maxLength": "100"}
    assert request.json_body is None


def test_get_with_no_placeholders_puts_everything_in_query():
    request = build_declarative_http_request(
        http_method="GET",
        url_template="https://catfact.ninja/fact",
        input={"max_length": 50},
    )
    assert request.url == "https://catfact.ninja/fact"
    assert request.query == {"max_length": "50"}


def test_post_puts_remaining_fields_in_json_body_not_query():
    request = build_declarative_http_request(
        http_method="post",
        url_template="https://api.example.com/orders/{orderId}/notes",
        input={"orderId": "abc", "text": "hello"},
    )
    assert request.method == "POST"
    assert request.url == "https://api.example.com/orders/abc/notes"
    assert request.query == {}
    assert request.json_body == {"text": "hello"}


def test_post_with_empty_remaining_fields_has_no_body():
    request = build_declarative_http_request(
        http_method="POST",
        url_template="https://api.example.com/orders/{orderId}/cancel",
        input={"orderId": "abc"},
    )
    assert request.json_body is None


def test_placeholder_value_is_url_encoded():
    request = build_declarative_http_request(
        http_method="GET",
        url_template="https://api.example.com/search/{term}",
        input={"term": "a/b c"},
    )
    assert request.url == "https://api.example.com/search/a%2Fb%20c"


def test_missing_field_referenced_by_template_raises():
    with pytest.raises(UrlTemplateError):
        build_declarative_http_request(
            http_method="GET",
            url_template="https://api.example.com/facts/{factId}",
            input={},
        )


def test_auth_is_passed_through_unchanged():
    auth = DeclarativeToolAuth(env_var="DEMO_TOOL_API_KEY")
    request = build_declarative_http_request(
        http_method="GET",
        url_template="https://api.example.com/x",
        input={},
        auth=auth,
    )
    assert request.auth is auth
