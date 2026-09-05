-- D2.1: 5 ตารางที่บางที่สุดสำหรับ tool เป็นข้อมูล (ARCHITECTURE-V2.md §8, TASKS-3DAYS.md D2.1)
--
-- ตัดออกโดยตั้งใจ (อยู่ใน docs/v2/TASKS.md แผนเต็ม ไม่ใช่ 3 วันนี้):
--   tool_version · channel_profile · api_key · pending_action · trace_event
-- ทั้งหมดอยู่ใน RAM ต่อไปตามที่แผนที่ตัดไว้
--
-- ผลของการตัด tool_version: ยังไม่มี config_version ให้ trace อ้างอิงย้อนหลัง
-- (ยอมรับได้เพราะ trace ยังอยู่ RAM และเดโมไม่ได้สอบสวนย้อนหลัง)
-- แต่ยังทำ soft delete (tool.enabled = 0) เพื่อไม่ให้ต้อง migrate schema ซ้ำตอนเติม tool_version ทีหลัง

CREATE TABLE tool (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    slug TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    enabled INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1)),
    source TEXT NOT NULL CHECK (source IN ('db', 'code')),
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- D2.6: http_method + url_template — จุดที่ตอน D2.1 คิดไว้ยังไม่มี (ARCHITECTURE-V2.md §3.4
-- ประกาศ operations[] แค่ policy/mode/schema ไม่มีที่เก็บ "จะยิงไปไหนด้วย method อะไร") เติมตอนสร้าง
-- declarative tool ตัวแรกที่ยิง REST จริง เพราะไม่มีฟิลด์นี้ก็ประกอบ HTTP request ไม่ได้เลย
-- กลไก "LLM เติมค่า" ที่เลือก (ตาม §3.7 ต้องเลือกอันเดียว): placeholder `{fieldName}` ใน
-- url_template ดึงจาก field ระดับบนสุดของ input เสมอ ฟิลด์ที่เหลือไปเป็น query string
-- (GET/DELETE) หรือ JSON body (POST/PUT/PATCH) — ดู app/tools/declarative_request.py
--
-- schema เก็บเป็น JSON string ที่ผ่าน validate_schema_subset()/check_schema() แล้วตอน save เท่านั้น
-- (ดู app/tools/schema_subset.py — D1.2) ตารางนี้ไม่ตรวจซ้ำ เชื่อชั้น application
CREATE TABLE tool_operation (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tool_id INTEGER NOT NULL REFERENCES tool (id) ON DELETE CASCADE,
    action TEXT NOT NULL,
    policy TEXT NOT NULL CHECK (
        policy IN ('grounded_answer', 'write_confirm', 'guided_flow', 'plain_read')
    ),
    input_schema TEXT NOT NULL,
    output_schema TEXT NOT NULL,
    exposure TEXT NOT NULL CHECK (exposure IN ('llm', 'internal')),
    mode TEXT NOT NULL CHECK (mode IN ('read', 'prepare', 'submit')),
    submit_action TEXT,
    -- NULL เฉพาะ operation ที่มาจาก Python plugin (source='code') ซึ่งประกอบ request เองในโค้ด —
    -- operation ของ declarative tool (source='db') ต้องมีทั้งคู่เสมอ (ตรวจตอน save โดยชั้น admin)
    http_method TEXT CHECK (http_method IN ('GET', 'POST', 'PUT', 'PATCH', 'DELETE')),
    url_template TEXT,
    limits TEXT,
    client_context TEXT,
    UNIQUE (tool_id, action)
);

-- V2 ทำแค่ api_key (เก็บชื่อ env var ไม่เก็บค่าจริง) แต่แยกตารางไว้แล้วเผื่อ oauth2 ทีหลัง (ARCHITECTURE-V2.md §8.3)
CREATE TABLE tool_auth (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tool_id INTEGER NOT NULL REFERENCES tool (id) ON DELETE CASCADE,
    type TEXT NOT NULL CHECK (type IN ('api_key', 'oauth2')),
    secret_ref TEXT NOT NULL
);

-- SYSTEM_PROMPT ที่เดิม hardcode ใน app/llm/prompting.py (D3.2 จะย้ายมาที่นี่)
CREATE TABLE prompt (
    key TEXT PRIMARY KEY,
    content TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- โดเมนที่อนุญาตยิงออกบน production (ARCHITECTURE-V2.md §7.4, admin เพิ่ม/ลบได้แต่ปิดโหมด production ไม่ได้)
CREATE TABLE domain_allowlist (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    domain TEXT NOT NULL UNIQUE,
    enabled INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1))
);
