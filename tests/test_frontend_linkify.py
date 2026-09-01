"""Regression tests สำหรับ safe linkify ในส่วนติดต่อเว็บ (web/linkify.js)

ทดสอบว่า `linkifySafeHtml` แปลงเฉพาะ http/https ที่อยู่ในข้อความที่ escape แล้ว
ให้เป็นลิงก์เปิดแท็บใหม่โดยไม่มี XSS — เรียก Node.js โดยตรงแบบเดียวกับ
``tests/test_live_frontend_audio.py``
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
LINKIFY = ROOT / "web" / "linkify.js"


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is required for the frontend linkify regression")
def test_linkify_only_http_https_with_safe_attributes_and_no_xss() -> None:
    script = r"""
const { linkifySafeHtml } = await import(process.argv[1]);
const assertEqual = (actual, expected, label) => {
  if (actual !== expected) {
    throw new Error(`${label}\n--- expected ---\n${expected}\n--- actual ---\n${actual}`);
  }
};

// 1. http:// และ https:// ถูกแปลงเป็นลิงก์เปิดแท็บใหม่
const httpOut = linkifySafeHtml('ดูที่ https://sabuyservice.pea.co.th/apply และ http://eservice.pea.co.th');
assertEqual(
  httpOut,
  'ดูที่ <a href="https://sabuyservice.pea.co.th/apply" target="_blank" rel="noopener noreferrer">https://sabuyservice.pea.co.th/apply</a> และ <a href="http://eservice.pea.co.th" target="_blank" rel="noopener noreferrer">http://eservice.pea.co.th</a>',
  'http/https ต้องถูก linkify ทุกจุด'
);

// 2. ข้อความที่ไม่มี URL ต้องไม่ถูกแก้ไข
const plain = linkifySafeHtml('ค่าไฟเดือนนี้ปกติ &lt;ข่าว&gt;');
assertEqual(plain, 'ค่าไฟเดือนนี้ปกติ &lt;ข่าว&gt;', 'ข้อความธรรมดาต้องไม่เปลี่ยน');

// 3. scheme อื่น (javascript:, ftp:, mailto:) ต้องไม่ถูกแปลง
const other = linkifySafeHtml('ลิงก์ javascript:alert(1) ftp://files.example.com mailto:a@b.example');
assertEqual(other, 'ลิงก์ javascript:alert(1) ftp://files.example.com mailto:a@b.example', 'ห้าม linkify scheme ที่ไม่ใช่ http/https');

// 4. XSS ที่ถูก escape ไว้แล้วต้องไม่กลายเป็น HTML จริง และ href ต้อง escape ปลอดภัย
const xss = linkifySafeHtml('&lt;script&gt;alert(1)&lt;/script&gt; https://ok.example.com/&quot;onclick=&quot;bad()');
assertEqual(
  xss,
  '&lt;script&gt;alert(1)&lt;/script&gt; <a href="https://ok.example.com/&quot;onclick=&quot;bad()" target="_blank" rel="noopener noreferrer">https://ok.example.com/&quot;onclick=&quot;bad()</a>',
  'HTML ที่ escape แล้วต้องไม่ถูกถอดออก และ URL ใน href ต้องไม่หลุดแอตทริบิวต์'
);
if (/<script>/i.test(xss)) {
  throw new Error('XSS: escaped script tag must never become a real tag');
}

// 5. ทุก anchor ต้องมี target=_blank และ rel=noopener noreferrer
const anchors = linkifySafeHtml('https://a.example https://b.example');
if ((anchors.match(/target="_blank"/g) || []).length !== 2) {
  throw new Error(`expected 2 target=_blank, got ${anchors}`);
}
if ((anchors.match(/rel="noopener noreferrer"/g) || []).length !== 2) {
  throw new Error(`expected 2 rel=noopener noreferrer, got ${anchors}`);
}
"""
    result = subprocess.run(
        [shutil.which("node") or "node", "--input-type=module", "-e", script, str(LINKIFY)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
