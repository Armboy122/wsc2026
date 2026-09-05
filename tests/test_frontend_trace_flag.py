"""P2 regressions for the real frontend markup, CSS, and trace URL flag."""
from __future__ import annotations

import re
import shutil
import subprocess
from html.parser import HTMLParser
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
INDEX_HTML = ROOT / "web" / "index.html"
STYLES_CSS = ROOT / "web" / "styles.css"
TRACE_FLAG_JS = ROOT / "web" / "trace-flag.js"


class _TagCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.tags: list[tuple[str, dict[str, str | None]]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.tags.append((tag, dict(attrs)))


def _parse_index() -> _TagCollector:
    parser = _TagCollector()
    parser.feed(INDEX_HTML.read_text(encoding="utf-8"))
    return parser


def test_header_has_hidden_trace_toggle_and_admin_link() -> None:
    parsed = _parse_index()
    toggles = [
        attrs
        for tag, attrs in parsed.tags
        if tag == "button" and attrs.get("id") == "trace-toggle"
    ]
    assert toggles, "index.html ต้องมีปุ่ม trace-toggle"
    assert "hidden" in toggles[0], "ปุ่ม trace ต้องมี hidden attribute เป็นค่าเริ่มต้น"
    links = [
        attrs
        for tag, attrs in parsed.tags
        if tag == "a" and attrs.get("id") == "admin-link"
    ]
    assert links, "index.html ต้องมีลิงก์ไปหน้าแอดมิน (id=admin-link)"
    assert links[0].get("href") == "admin.html"


def test_css_keeps_hidden_authoritative_for_ghost_btn() -> None:
    css = STYLES_CSS.read_text(encoding="utf-8")
    rule = re.search(r"\.ghost-btn\[hidden\]\s*\{[^}]*\}", css)
    assert rule, "styles.css ต้องมีกติกา .ghost-btn[hidden] กัน class ทับ hidden"
    assert re.search(r"display:\s*none", rule.group(0)), (
        ".ghost-btn[hidden] ต้องบังคับ display: none"
    )
    mobile_start = css.index("@media (max-width: 480px)")
    mobile_end = css.index("@media (prefers-reduced-motion: reduce)", mobile_start)
    mobile = css[mobile_start:mobile_end]
    assert re.search(r"\.header-buttons\s*\{[^}]*flex-wrap:\s*wrap", mobile, re.S)
    assert re.search(
        r"\.header-buttons \.ghost-btn\s*\{[^}]*flex:\s*1 1 calc\(50%",
        mobile,
        re.S,
    )
    assert re.search(
        r"\.sim-badge\s*\{[^}]*width:\s*100%[^}]*white-space:\s*normal",
        mobile,
        re.S,
    )


def test_app_js_wires_trace_flag_to_trace_toggle() -> None:
    source = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
    assert "trace-flag.js" in source, "app.js ต้อง import web/trace-flag.js"
    assert re.search(r"traceToggle\.hidden\s*=\s*false", source), (
        "app.js ต้องปลด hidden ของ trace-toggle เมื่อ flag เปิด"
    )


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is required for the trace flag regression")
def test_trace_flag_url_semantics() -> None:
    script = r"""
const { isTracePanelEnabled } = await import(process.argv[1]);
const assertEqual = (actual, expected, label) => {
  if (actual !== expected) {
    throw new Error(`${label}: expected ${expected}, got ${actual}`);
  }
};

assertEqual(isTracePanelEnabled(''), false, 'ไม่มี query string ต้องปิด');
assertEqual(isTracePanelEnabled('?'), false, 'query string เปล่าต้องปิด');
assertEqual(isTracePanelEnabled('?other=1'), false, 'query อื่นต้องไม่เปิด trace');
assertEqual(isTracePanelEnabled('?trace='), false, 'ค่า flag ว่างต้องปิด');
assertEqual(isTracePanelEnabled('?trace=2'), false, 'ค่า flag อื่นต้องปิด');
assertEqual(isTracePanelEnabled('?trace=false'), false, '?trace=false ต้องปิด');

assertEqual(isTracePanelEnabled('?trace=1'), true, '?trace=1 ต้องเปิด');
assertEqual(isTracePanelEnabled('?trace=1&x=2'), true, 'flag ร่วมกับพารามิเตอร์อื่นต้องเปิด');
assertEqual(isTracePanelEnabled('?x=2&trace=1'), true, 'ลำดับพารามิเตอร์ใดก็ได้');
assertEqual(isTracePanelEnabled('?trace=TRUE'), false, 'ค่าที่ไม่ใช่ 1 ต้องปิด');
"""
    result = subprocess.run(
        [shutil.which("node") or "node", "--input-type=module", "-e", script, str(TRACE_FLAG_JS)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
