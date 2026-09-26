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
  │  instruction = app/prompts/adk_voice.md (ไม่มี catalog)
  │  tools = [search_knowledge]
  ▼
Gemini Live  ──calls──►  AdkKnowledgeTool (search_knowledge)
                            ▼
                         IndexManager  (app/knowledge/index/manager.py)
                            ▼
                         KnowledgeIndex: Q&A lane + BM25/dense + RRF
                            ▼
                         knowledge/source/**/*.md  (chunk แล้ว, Q&A มาก่อน)
```

Gemini Live ผ่าน ADK เป็นโมเดลสนทนาและผู้ตัดสินใจเพียงตัวเดียว: รับเสียง, เรียก
`search_knowledge` ด้วยคำถามภาษาไทย, อ่านผลลัพธ์ (approved Q&A ก่อน แล้วตามด้วย chunk
พร้อมแหล่งอ้างอิง) แล้วตอบด้วยเสียงใน session เดิม

## โมดูล

| โมดูล | หน้าที่ | ข้อห้าม |
| --- | --- | --- |
| `app/main.py` | โหลด settings → สร้าง catalog/index manager → `create_platform_app` → router health/live → mount `web/` | ไม่มี business logic |
| `app/core/` | config, DI ของ Knowledge catalog (health), logging, request-id middleware, validation handler, `create_platform_app` (ปิด docs/openapi) | ไม่มี CORS, ไม่มี provider อื่น |
| `app/api/routes.py` | `GET /health` (รวม `knowledgeIndex`) | |
| `app/api/live.py` | entry point WebSocket; ตรวจ `GEMINI_API_KEY` และ index manager แล้วส่งต่อให้ `AdkLiveSession` | ไม่มี runtime selector |
| `app/runtime/adk_live.py` | สะพานระหว่าง wire protocol ของเว็บกับ ADK bidi streaming; ตรวจ PCM frame; แปลง ADK event เป็น event ที่ปลอดภัย | ไม่ส่ง raw event/thought/tool payload/provider error ให้ browser; JSON จาก browser ถูกเพิกเฉย |
| `app/agent/adk_agent.py` | สร้าง ADK `Agent` และ `AdkKnowledgeTool` (`search_knowledge`) | มีเครื่องมือเดียว; ไม่เรียก `generate_content`; instruction ไม่มี catalog JSON |
| `app/knowledge/catalog.py`, `aliases.py` | allowlist ของไฟล์ `.md` ที่อนุมัติ และ alias metadata สำหรับ index | ไม่เรียก LLM/embedding/network |
| `app/knowledge/index/` | chunking, tokenizer, BM25, embedder seam, RRF, Q&A lane, lifecycle/auto-reindex | ไม่เรียก generative model; ไม่ import torch/sentence-transformers ตอน import |
| `app/contracts.py` | `FrozenModel`, `ToolErrorCode`, `HealthResponse` | |
| `web/` | UI เสียง (ปุ่มไมโครโฟน, transcript) และหน้าจำลองโทรศัพท์ | ไม่มีแชตพิมพ์/REST API/geolocation |

## Knowledge (deterministic)

1. เมื่อเริ่มระบบ `IndexManager` สแกน `.md` ที่อนุมัติใต้ `KNOWLEDGE_SOURCE_ROOT`
   (ข้าม README และไฟล์ซ่อน) chunk แบบ heading-aware และสร้าง index ใน background thread
   โดยเขียน cache ไว้ใต้ `KNOWLEDGE_INDEX_DIR` (derived artefact, gitignored)
2. Approved Q&A ใต้ `knowledge/source/qa/` ถูก index เป็น lane แยกที่จัดอันดับเหนือ chunk เสมอ;
   chunk ของเอกสารใช้ BM25 (PyThaiNLP) + dense cosine หลอมด้วย RRF
3. Gemini Live เรียก `search_knowledge(query)`; เครื่องมือรัน index แบบ off-loop
   (`asyncio.to_thread`) แล้วคืน approved Q&A ก่อน ตามด้วย chunk พร้อม `knowledge://source/<id>`
4. ความล้มเหลวทุกแบบคืน `{status: "error", error: {code, message}}` ที่ปลอดภัย (ดู CONTRACTS.md)
   ด้วย code `invalid_input` / `unavailable` / `internal`
5. เอกสารที่อนุมัติไม่ถูกแก้ไข เปลี่ยนชื่อ หรือลบโดยโค้ด; index เป็นเพียงสำเนาที่สร้างใหม่ได้
   และ rebuild อัตโนมัติเมื่อไฟล์เปลี่ยน

ไม่มี vector DB server, RAGFlow, MCP, คิว หรือ agent/LLM สนทนาเพิ่มเติม; embedding model
ที่ self-host (`BAAI/bge-m3`) ไม่ใช่ generative model

## ความปลอดภัย

- คีย์อยู่ใน environment เท่านั้น ไม่ log และไม่ส่งให้ browser
- ADK logger ถูกตั้งเป็น WARNING เพื่อไม่ให้ payload/resumption handle หลุดลง log
- Knowledge fail-closed: relative source ID เท่านั้น ไม่มี path traversal หรือการอ่านไฟล์นอก catalog

## การทดสอบ

- `app/api/tests`: route surface (มีแค่ `/health` + `/ws/live`), health, static UI, route ที่ถูกลบคืน 404/405
- `app/core/tests`: settings และ startup
- `tests/test_adk_runtime.py`: wire protocol, การแปลง event, PCM validation (ADK/Gemini จำลอง)
- `tests/test_adk_knowledge_tool.py`: schema/declaration ของ `search_knowledge`, การตรวจ argument,
  payload สำเร็จ/ผิดพลาด, การ off-load ด้วย `asyncio.to_thread`, instruction และไม่มี generative call
- `tests/knowledge_index/`, `tests/test_knowledge_catalog.py`: chunking, hybrid search, Q&A precedence,
  lifecycle/auto-reindex, allowlist
- `tests/test_architecture.py`: โค้ดแพลตฟอร์มเก่าถูกลบ, ไม่มี import ที่ตายแล้ว, เอกสารความรู้ยังครบ
- `tests/test_live_frontend_audio.py`: `web/pcm-processor.js`

การทดสอบเสียงจริงและ latency ยังเป็นงาน manual ที่ค้างอยู่ (ดู README.md)
