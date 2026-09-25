# ARCHITECTURE — PEA Knowledge Voice Agent

## ภาพรวม

```text
Browser (web/index.html, web/phone.html)
  │  PCM16 16 kHz (binary)            ▲ PCM16 24 kHz + JSON events
  ▼                                   │
FastAPI  WS /ws/live  (app/api/live.py)
  ▼
AdkLiveSession  (app/runtime/adk_live.py)
  │  LiveRequestQueue → Runner.run_live() → forward_event()
  ▼
ADK Agent "pea_one_agent"  (app/agent/adk_agent.py)
  │  instruction = app/prompts/adk_voice.md + Knowledge catalog (JSON)
  │  tools = [get_knowledge_documents]
  ▼
Gemini Live  ──calls──►  AdkKnowledgeTool
                            ▼
                         KnowledgeDocumentService  (app/knowledge/service.py)
                            ▼
                         KnowledgeCatalog + aliases (app/knowledge/catalog.py, aliases.py)
                            ▼
                         knowledge/source/**/*.md  (อ่านทั้งไฟล์)
```

Gemini Live ผ่าน ADK เป็นโมเดลสนทนาและผู้ตัดสินใจเพียงตัวเดียว: รับเสียง, เลือก `sourceId`
จาก catalog, เรียกเครื่องมือ, อ่านเอกสารที่ได้ แล้วตอบด้วยเสียงใน session เดิม

## โมดูล

| โมดูล | หน้าที่ | ข้อห้าม |
| --- | --- | --- |
| `app/main.py` | โหลด settings → สร้าง catalog/service → `create_platform_app` → router health/live → mount `web/` | ไม่มี business logic |
| `app/core/` | config (6 ค่า), DI ของ Knowledge service, logging, request-id middleware, validation handler, `create_platform_app` (ปิด docs/openapi) | ไม่มี CORS, ไม่มี provider อื่น |
| `app/api/routes.py` | `GET /health` | |
| `app/api/live.py` | entry point WebSocket; ตรวจ `GEMINI_API_KEY` แล้วส่งต่อให้ `AdkLiveSession` | ไม่มี runtime selector |
| `app/runtime/adk_live.py` | สะพานระหว่าง wire protocol ของเว็บกับ ADK bidi streaming; ตรวจ PCM frame; แปลง ADK event เป็น event ที่ปลอดภัย | ไม่ส่ง raw event/thought/tool payload/provider error ให้ browser; JSON จาก browser ถูกเพิกเฉย |
| `app/agent/adk_agent.py` | สร้าง ADK `Agent` และ `AdkKnowledgeTool` (`get_knowledge_documents`) | มีเครื่องมือเดียว; ไม่เรียก `generate_content` |
| `app/knowledge/` | catalog แบบ deterministic, alias metadata, การเลือกเอกสารตาม allowlist และขีดจำกัด | ไม่เรียก LLM/embedding/network; ไม่ค้นจากคำถาม; ไม่ตัดทอน |
| `app/contracts.py` | `FrozenModel`, `ToolErrorCode`, `HealthResponse` | |
| `web/` | UI เสียง (ปุ่มไมโครโฟน, transcript) และหน้าจำลองโทรศัพท์ | ไม่มีแชตพิมพ์/REST API/geolocation |

## Knowledge (deterministic)

1. เมื่อเริ่มระบบ `KnowledgeCatalog` สแกน `.md` ที่อนุมัติใต้ `KNOWLEDGE_SOURCE_ROOT`
   (ข้าม README และไฟล์ซ่อน) สร้าง entry `sourceId`/`title`/`headings` และผูก alias จาก
   `knowledge/aliases/` (alias ที่อ้างไฟล์ที่ไม่มีอยู่ทำให้เริ่มระบบไม่สำเร็จ)
2. catalog แบบย่อถูกฝังใน instruction ของ agent — ไม่มีเนื้อหาเอกสาร
3. Gemini Live เรียก `get_knowledge_documents(source_ids)`; service ตรวจรูปแบบ, allowlist,
   ≤ 5 เอกสาร และรวม ≤ 120,000 ตัวอักษร แล้วคืน Markdown ทั้งไฟล์พร้อม `knowledge://source/<id>`
4. ความล้มเหลวทุกแบบคืน `{status: "error", error: {code, message}}` ที่ปลอดภัย (ดู CONTRACTS.md)

ไม่มี vector DB, embedding, chunk, RAG, MCP, คิว หรือ agent/LLM เพิ่มเติม

## ความปลอดภัย

- คีย์อยู่ใน environment เท่านั้น ไม่ log และไม่ส่งให้ browser
- ADK logger ถูกตั้งเป็น WARNING เพื่อไม่ให้ payload/resumption handle หลุดลง log
- Knowledge fail-closed: relative source ID เท่านั้น ไม่มี path traversal หรือการอ่านไฟล์นอก catalog

## การทดสอบ

- `app/api/tests`: route surface (มีแค่ `/health` + `/ws/live`), health, static UI, route ที่ถูกลบคืน 404/405
- `app/core/tests`: settings และ startup
- `tests/test_adk_runtime.py`: wire protocol, การแปลง event, PCM validation (ADK/Gemini จำลอง)
- `tests/test_adk_knowledge_tool.py`, `tests/test_knowledge_*.py`: เครื่องมือ, catalog, ขีดจำกัด, ไม่มี generative call
- `tests/test_architecture.py`: โค้ดแพลตฟอร์มเก่าถูกลบ, ไม่มี import ที่ตายแล้ว, เอกสารความรู้ยังครบ
- `tests/test_live_frontend_audio.py`: `web/pcm-processor.js`

การทดสอบเสียงจริงและ latency ยังเป็นงาน manual ที่ค้างอยู่ (ดู README.md)
