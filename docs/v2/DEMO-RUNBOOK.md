# DEMO-RUNBOOK — เดโม PEA One Agent แบบทำซ้ำได้ (A5)

> เอกสารนี้เขียนจาก **การรันจริงทั้งหมดในเอกสาร** ณ วันที่ 2026-09-06 บน commit ฐาน
> `40fb967` (branch `v2`) ทุกคำสั่งรันบน test instance แยก ไม่แตะ `data/pea.db`,
> credentials จริง หรือระบบ PEA production
> หลักฐานรายขั้นของงาน A5 อยู่ที่ `docs/v2/ADMIN-DEMO-VERIFICATION.md` ส่วนท้าย (A5)
> และ `docs/v2/DEMO-VERIFICATION.md` (P5 — ยังรอมนุษย์ยืนยันตามที่บันทึกไว้)

## 0. สรุปสถานะ (ผ่าน / ไม่ผ่าน / ไม่ได้ทดสอบ)

| เส้นเดโม | สถานะ | หลักฐาน |
|---|---|---|
| Knowledge + citation + follow-up | ✅ ผ่าน (Gemini จริง, instance 8113) | A5 section ใน ADMIN-DEMO-VERIFICATION.md |
| OMS prepare → confirm → submit (ไม่ทราบ CA) | ✅ ผ่าน | `reportId OMS-ANON-0002` จาก OMS จำลองในเครื่อง |
| OMS (ทราบ CA) get_outage_by_ca → prepare → submit | ✅ ผ่าน | `eventId OMS-METER-0002` พร้อมพิกัด GIS |
| Admin: สร้าง tool → ลองยิง → เปิดใช้ → AI เรียกได้ | ✅ ผ่าน | `cat_fact_tool.get_random_fact` สำเร็จโดยไม่ restart |
| Prompt แก้แล้วมีผลเทิร์นถัดไป + คืนค่าเดิม | ✅ ผ่าน | `max_length=25` ตาม prompt ที่แก้; คืนค่า `isModified:false` |
| SSRF ปฏิเสธ private/link-local (production test config) | ✅ ผ่าน | `169.254.169.254`/`10.0.0.1` → `internal_ip`; `192.168.1.1`/`127.0.0.1` → `not_https` |
| `grep ToolName/ToolAction` ใน main_agent.py = 0 | ✅ ผ่าน | ตรวจซ้ำ ณ 2026-09-06 ทั้ง working tree และ HEAD |
| `app/prompts/` ไม่มีอยู่ | ✅ ผ่าน | ตรวจซ้ำ ณ 2026-09-06 |
| Full pytest | ✅ ผ่าน | 758 passed, 7 warnings (working tree) |
| `./scripts/evaluate` | ❌ ไม่ผ่าน (pre-existing) | exit 1, completion 0.0 — สาเหตุเดิมตาม A3 (ดู §6) |
| LINE end-to-end | ⏳ ไม่ได้ทดสอบ | มี `.env` ครบแต่การยิง webhook จริงจะส่งข้อความเข้า OA จริง — ต้องให้มนุษย์ทดสอบ; smoke ปลอดภัย (signature ไม่ถูก → 403) ผ่าน |
| Voice end-to-end | ⏳ ไม่ได้ทดสอบ | ต้องมีไมโครโฟน/เบราว์เซอร์จริง — agent ทำแทนไม่ได้ |

## 1. ขั้นเตรียม environment (ไม่มีค่าความลับในเอกสารนี้)

### 1.1 สิ่งที่ต้องมี

- Python venv ของ repo: `.venv` (pytest/uvicorn ติดตั้งใน venv เท่านั้น)
- ไฟล์ `.env` ที่ root ของ repo มีตัวแปรเหล่านี้ **ตั้งค่าแล้ว** (เอกสารนี้ตั้งใจไม่พิมพ์ค่า):
  - `GEMINI_API_KEY` — provider จริงสำหรับ Main Agent/Knowledge
  - `ADMIN_PASSWORD` — ล็อกอินหน้า admin
  - `OMS_API_KEY` — key ของ OMS จำลอง (ค่าทดสอบมาตรฐานตาม README คือ `88888888` — เป็นค่าเดโมที่ประกาศใน README อยู่แล้ว ไม่ใช่ความลับ)
  - `OMS_BASE_URL` ค่าเริ่มต้น `http://127.0.0.1:8080/api/v1/oms`
- Docker (สำหรับ Postgres ทดสอบของ OMS จำลอง) และ Go toolchain (สำหรับ migrate ของ `wsc2026-be`) — หรือใช้ OMS จำลองตัวที่เคยรันไว้แล้วถ้ามี
- ⚠️ โค้ด OMS จำลองอยู่โปรเจกต์ข้างเคียง `wsc2026-be` (Go + Fiber) — **ห้ามชี้ `.env` ของ PEA ไปที่ OMS จริง**

### 1.2 Postgres ทดสอบแยกสำหรับ OMS จำลอง (ไม่แตะ DB จริง)

`.env` เดิมของ `wsc2026-be` ชี้ไป Supabase ระยะไกล — **ห้ามใช้** (ตามกติกาห้ามเขียน DB ใช้งานจริง)
ให้สร้าง Postgres ทดสอบในเครื่องแทน:

```bash
docker run -d --name pea-a5-pg -e POSTGRES_USER=pea_test -e POSTGRES_PASSWORD=pea_test \
  -e POSTGRES_DB=pea_oms_test -p 54330:5432 pgvector/pgvector:pg16
# รอ pg_isready แล้วรัน migrations ของ wsc2026-be ลง DB ทดสอบ
cd ../wsc2026-be
GOOSE_DBSTRING="postgresql://pea_test:pea_test@127.0.0.1:54330/pea_oms_test?sslmode=disable" \
  GOOSE_MIGRATION_DIR=./migrations go run ./cmd/migrate up
```

Migrations จะ seed ตาราง OMS/VOC และ fixture CA ทดสอบ (เช่น `020007161258`) — เป็นข้อมูล
fixture ใน DB ทดสอบ ไม่ใช่ข้อมูลลูกค้า

### 1.3 สตาร์ต OMS จำลอง (port 8080)

```bash
cd ../wsc2026-be
GOOSE_DBSTRING="postgresql://pea_test:pea_test@127.0.0.1:54330/pea_oms_test?sslmode=disable" \
  API_KEY=88888888 PORT=8080 ./bin/server   # หรือ go run .
```

**คาดว่าจะเห็น**: `curl http://127.0.0.1:8080/health` → `{"status":"ok"}` และ
`curl -H "X-API-Key: 88888888" .../api/v1/oms/outages/by-ca/020007161258` → JSON ที่มี
`customerFound:true`

### 1.4 สตาร์ต PEA test instance (port 8113, DB แยก, ไม่มี `--reload`)

```bash
cd agentandtool
# สร้าง state key (Fernet) ครั้งเดียวต่อ demo DB — เก็บไว้ใช้ซ้ำ ห้ามเปลี่ยนกลางคัน
PEA_STATE_KEY=$(.venv/bin/python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
# export env จาก .env ให้ process อ่าน tool-auth secret ได้ (ดูข้อจำกัด §5.4)
set -a; source .env; set +a
DB_PATH=/tmp/pea-a5-demo/pea-a5.db PEA_STATE_KEY="$PEA_STATE_KEY" APP_ENV=development \
  .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8113
```

**คาดว่าจะเห็น**:

- `/health` → `{"status":"ok"}`
- log: `seeded declarative tool 'oms_tool' ... base_url=http://127.0.0.1:8080/api/v1/oms`
- ⚠️ ต้องรัน **ไม่มี `--reload`** (ข้อจำกัดเดิมของ P5 — module-level `asyncio.run()` พังเมื่อ reload)
- ⚠️ `PEA_STATE_KEY` ต้องเป็นค่าเดิมเสมอเมื่อใช้ DB เดิม — เปลี่ยน key แล้ว pending action เก่าถอดรหัสไม่ได้ (fail closed)

### 1.5 เปิด session

```bash
# web session (สำหรับหน้าแชต)
curl -s -c /tmp/pea-a5-demo/web.cookies -X POST http://127.0.0.1:8113/api/v1/web/session \
  -H 'content-type: application/json' -d '{}'
# admin session (สำหรับ /admin.html และ trace)
curl -s -c /tmp/pea-a5-demo/admin.cookies -X POST http://127.0.0.1:8113/api/v1/admin/login \
  -H 'content-type: application/json' -d "{\"password\":\"<ADMIN_PASSWORD จาก .env>\"}"
```

**คาดว่าจะเห็น**: `{"authenticated":true}` ทั้งคู่

### 1.6 production test config สำหรับ SSRF (port 8114 — แยกจากเดโมหลัก)

```bash
APP_ENV=production DB_PATH=/tmp/pea-a5-demo/pea-a5-prod.db PEA_STATE_KEY="$PEA_STATE_KEY" \
  ADMIN_PASSWORD="<รหัสชั่วคราว สร้างใหม่แล้วทิ้งหลังใช้>" \
  .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8114
```

**คาดว่าจะเห็น**: log เตือน `Declarative tool 'oms_tool' (id=1) failed validation and was
disabled: ... ไม่ใช่ HTTPS: production ต้องใช้ https:// เท่านั้น` — เป็นพฤติกรรม fail-closed
ที่ถูกต้อง ไม่ใช่ความผิดปกติ (เดโม OMS ใช้ instance development เท่านั้น)

## 2. สคริปต์เดโม ~8 นาที

| นาที | ทำอะไร | คาดว่าจะเห็น | พูดว่า |
|---|---|---|---|
| 0–1 | แชต (web session): "การขอเช่าเครื่องกำเนิดไฟฟ้าของ PEA มีเงื่อนไขอย่างไร" แล้ว follow-up "ถ้าต้องการขอเช่า ต้องแจ้งล่วงหน้ากี่วัน" | คำตอบภาษาไทย + panel citation ชี้ไฟล์จริงใน `knowledge/source` (เช่น `PEA_เช่าเครื่องกำเนิดไฟฟ้า_ฉนวนครอบสายแรงสูง.md`) — follow-up ตอบต่อประเด็นเดิมได้ | "ทุกคำตอบมีหลักฐานที่ตรวจกับไฟล์จริง" |
| 1–3 | แชต: "บ้านผมไฟดับ ไม่ทราบหมายเลขผู้ใช้ไฟ ไฟดับทั้งบ้าน อยู่ซอยลาดกระบัง 71 เขตลาดกระบัง เบอร์ 0812345678" → กดยืนยันในหน้า pending | ระบบถามข้อมูลที่ขาด (ถ้ามี) → `prepare_anonymous_outage` → การ์ดยืนยัน → กดยืนยันแล้วได้ `reportId OMS-ANON-xxxx` (RECEIVED) | "แชตเตรียมได้อย่างเดียว มนุษย์เป็นคนยืนยันเสมอ" |
| 3–4 | แชต: "ไฟดับ หมายเลขผู้ใช้ไฟ 020007161258 ตรวจสถานะให้หน่อย" | `get_outage_by_ca` ตอบสถานะจาก OMS (ทราบ CA) — ถ้าไม่มีเหตุขัดข้อง ระบบจะเสนอ prepare แจ้งเหตุต่อ | "เส้นทราบ CA ก็เดิน contract เดียวกัน" |
| 4–6 | เปิด `/admin.html` → สร้าง tool `cat_fact_tool` ตาม §3 → กด "ลองยิงดู" (`max_length=60`) → save | ลองยิงได้ `HTTP สำเร็จ · 200` พร้อม JSON; รายการแสดง tool ใหม่ `declarative (DB)` เปิดใช้งาน | "เพิ่มความสามารถใหม่โดยไม่ deploy" |
| 6–7 | กลับหน้าแชต: "ช่วยหาข้อเท็จจริงเกี่ยวกับแมว โดยกำหนดความยาวสูงสุด 60 ตัวอักษร" | AI เรียก `cat_fact_tool.get_random_fact` สำเร็จ — fact ที่ได้ยาว ≤ 60 | "ระบบรู้จัก tool ใหม่ทันทีในเทิร์นถัดไป" |
| 7–8 | (ก่อนเปิดเดโม: เตรียม instance 8114 ไว้แล้ว) บน 8114: ปุ่มลองยิงใส่ `https://169.254.169.254/latest/meta-data/` แล้วโชว์ผล | `{"ok":false,"reason":"internal_ip","error":"ปลายทางเป็น IP ภายใน/ไม่ปลอดภัย: 169.254.169.254"}` | "เปิดกว้างแต่ไม่ประมาท" |
| 8 (สำรอง) | ถ้ามีเวลา: `grep -c "ToolName\.\|ToolAction\." app/agent/main_agent.py` → `0`; รัน `pytest -q` | `0` / `758 passed` | "agent ไม่รู้จักชื่อ tool และของเดิมไม่พัง" |

## 3. Tool definition ตัวอย่าง (cat_fact_tool)

กรอกผ่านฟอร์ม `/admin.html` (form builder) หรือ `POST /api/v1/admin/tools` ด้วย JSON เดียวกัน:

```json
{
  "slug": "cat_fact_tool",
  "displayName": "ข้อเท็จจริงเกี่ยวกับแมว",
  "description": "ขอข้อเท็จจริงเกี่ยวกับแมวจาก catfact.ninja ระบุความยาวสูงสุดของข้อความได้ (ชื่อ field ต้องตรงกับ API ของ upstream: max_length จะถูกใส่ใน query string สำหรับ GET)",
  "enabled": true,
  "operations": [{
    "action": "get_random_fact",
    "policy": "plain_read",
    "exposure": "llm",
    "mode": "read",
    "httpMethod": "GET",
    "urlTemplate": "https://catfact.ninja/fact",
    "inputSchema": {
      "type": "object",
      "properties": {"max_length": {"type": "integer", "description": "ความยาวสูงสุดของข้อความ (ตัวอักษร)"}},
      "additionalProperties": false
    },
    "outputSchema": {
      "type": "object",
      "properties": {"fact": {"type": "string"}, "length": {"type": "integer"}},
      "required": ["fact", "length"],
      "additionalProperties": false
    }
  }]
}
```

**ข้อควรระวังตาม schema subset validator (D1.2)**: ทุก `type:"object"` ต้องประกาศ
`"additionalProperties": false` — ไม่งั้น save/ลองยิงจะถูกปฏิเสธพร้อมข้อความบอกตำแหน่ง
(พฤติกรรมถูกต้องตามสัญญา)

**คำถามตัวอย่างที่ใช้**: "ช่วยหาข้อเท็จจริงเกี่ยวกับแมว โดยกำหนดความยาวสูงสุด 60 ตัวอักษร"

**คำถาม knowledge ตัวอย่าง** (ตอบได้จากเอกสารจริง): เช่าเครื่องกำเนิดไฟฟ้า / ฉนวนครอบสายแรงสูง
— ถามนอกเอกสาร ระบบจะปฏิเสธแบบ grounded ("ยังไม่พบคำตอบที่มีแหล่งอ้างอิงเพียงพอ") — เป็น
พฤติกรรมตามออกแบบ ไม่ใช่ข้อผิดพลาด

## 4. เริ่มรอบเดโมใหม่โดยไม่ล้าง audit/config

- **สร้าง web session ใหม่** (`POST /api/v1/web/session`) = บทสนทนาใหม่ ไม่กระทบอะไรทั้ง trace เก่าและ config
- `POST /api/v1/reset` (ต้องมี admin session) ล้าง **เฉพาะ**: บทสนทนาใน RAM, pending action,
  idempotency key, สถานะ backend จำลองใน process — **ไม่ล้าง**: trace (append-only),
  tool/prompt config ใน SQLite และไม่แตะตาราง `prompt`/`tool*` เลย
- **ทดสอบ prompt**: บันทึกเนื้อค่าเดิมไว้ก่อนแก้ (`GET /api/v1/admin/prompt`) พอทดสอบเสร็จ
  `PUT /api/v1/admin/prompt` ด้วยเนื้อค่าเดิม → ตรวจ `isModified:false` ว่ากลับเท่าเดิมแล้ว
  (อย่าใช้ reset แทนการคืนค่า prompt เพราะ reset ไม่แตะตาราง prompt)
- **tool ทดลอง**: ปิดผ่าน `PATCH /api/v1/admin/tools/{slug}/enabled` หรือเก็บไว้ได้ —
  config อยู่ใน demo DB แยกอยู่แล้ว
- **เลขรายงาน OMS (OMS-ANON-xxxx / OMS-METER-xxxx)** นับต่อจาก DB ของ OMS จำลอง — ถ้าอยากได้
  เลขเริ่มต้นใหม่ ให้สร้าง Postgres ทดสอบใหม่ (§1.2) ไม่ต้องแตะ PEA
- **trace เก่า** คือ audit ที่ตั้งใจเก็บไว้ — อย่าลบ และอย่าลบ demo DB เพื่อ "เคลียร์ความผิดพลาด"

## 5. ตัวอย่างสำรองเมื่อ upstream ล่ม (ทั้งหมดเป็นของที่ "เตรียมไว้ล่วงหน้า" — ห้ามแสดงเสมือนสร้างสด)

1. **catfact.ninja ล่ม**: ใช้เส้นสำรองที่ประกาศชัดว่า "เป็นการสาธิตด้วยปลายทางสำรองที่เตรียมไว้" —
   สร้าง tool ใหม่ชี้ไป `GET https://<ปลายทางสำรอง HTTPS ที่เตรียมไว้>` แทน หรือสาธิตปุ่มลองยิงกับ
   OMS จำลองในเครื่อง (`http://127.0.0.1:8080/...` บน development) — เครื่องไม้เครื่องเดียวกับ
   สิ่งที่พิสูจน์ไว้คือ contract ไม่ใช่ catfact เอง
2. **OMS จำลอง (8080) ล่ม**: prepare ยังทำงานได้ (mode=prepare ไม่มี HTTP call) แต่ submit จะตอบ
   error `unavailable` แบบปลอดภัย — ให้พูดตามจริงว่า "upstream ล่ม ระบบ fail closed ไม่ปลอมผล"
   แล้วสาธิตส่วนอื่นแทน
3. **Gemini/API key ล่ม**: ไม่มี fallback ของโมเดล — เหลือเดโมที่ไม่ต้องใช้โมเดล: SSRF (§1.6),
   grep ToolName = 0, pytest และการปฏิเสธ grounded เมื่อไม่มี citation ให้พูดตามจริงว่า
   "ส่วน AI ไม่พร้อมสาธิตสด" — **ห้าม**โชว์ผลย้อนหลังแล้วอ้างว่าเรียกสด

## 6. ข้อจำกัดที่ต้องพูดตามจริง (PRD §14)

1. **OMS/VOC เป็น simulation** — ผลจาก OMS จำลองในเครื่อง/Supabase demo ทุกผล tool มี
   `simulation:true` ไม่ได้เชื่อม PEA production write เลย
2. **evaluate script ไม่ผ่าน (pre-existing)** — `./scripts/evaluate` exit 1 / completion 0.0
   เพราะ (ก) script ไม่ส่ง API key ขณะ `POST /api/v1/chat` และ `POST /api/v1/reset` บังคับ auth
   ตาม CONTRACTS-V2 → 401, (ข) script เช็ค `health.knowledgeBackend` ซึ่งเป็น field เก่า
   ปัญหานี้เหมือนที่ A3 บันทึกไว้แล้ว ไม่ใช่ regression ของ A5 และไม่ได้รับการแก้ในงานนี้
   (อยู่นอกขอบเขตเอกสาร) — ใช้ pytest + เดโมสดแทนการอ้าง evaluate
3. **tool auth secret อ่านจาก `os.environ` ตอน execute** — สตาร์ต uvicorn แบบไม่ export `.env`
   (เช่นลืม `set -a; source .env`) แล้วเรียก submit OMS จะได้ error `unavailable`
   (fail closed เพราะ `missing_secret`) — runbook จึงสั่ง export ก่อนสตาร์ต (§1.4)
4. **OAuth/token flow ไม่รองรับ** — tool auth เป็น static header จาก env var เท่านั้น
5. **conversation history อยู่ใน RAM** — รีสตาร์ต server แล้วบทสนทนาหาย (trace ยังอยู่)
6. **Telegram / public API ยังไม่ implement** — ออกแบบไว้ใน TASKS.md เท่านั้น
7. **LINE/voice ต้องทดสอบด้วยมนุษย์** — agent ยิง webhook จริงแทนไม่ได้เพราะจะส่งข้อความ
   เข้า OA จริง / voice ต้องไมโครโฟนจริง
8. **oms_tool ถูกปิดใน APP_ENV=production** — urlTemplate เป็น http ภายใน ไม่ผ่าน policy;
   เดโม OMS ต้องใช้ instance development (fail-closed ตามดีไซน์)

## 7. commit / environment / provider mode ของผลตรวจล่าสุด

- commit ฐาน: `40fb967` (branch `v2`) — ผลตรวจรันบน working tree ของ commit นี้
  (มี dirty changes จากงาน cumulative review หลัง A4 ที่ยังไม่ถูก commit — ระบุไว้ใน §8)
- วันที่ตรวจ: 2026-09-06
- environment: macOS, test instances 127.0.0.1:8113 (development) และ 8114 (production ชั่วคราว),
  DB: `/tmp/pea-a5-demo/*.db`, OMS จำลอง `wsc2026-be` + Postgres ทดสอบ 127.0.0.1:54330
- provider mode: Gemini `gemini-3.5-flash-lite` (จริง ผ่าน `.env`), knowledge backend
  `full_document`, judge provider `demo`

## 8. คำสั่งและผล validation ล่าสุด (2026-09-06)

```text
$ grep -c "ToolName\.\|ToolAction\." app/agent/main_agent.py
0                                  # exit 1 = ไม่พบบรรทัด (พฤติกรรมที่ต้องการ)

$ ls app/prompts/
ls: app/prompts/: No such file or directory

$ .venv/bin/python -m pytest -q            # working tree (HEAD + dirty งาน S1/S2)
758 passed, 7 warnings in 43.01s

# แยก pre-existing vs regression: รันซ้ำบน worktree สะอาดของ HEAD 40fb967
2 failed, 744 passed            # 2 failed = tests/test_p9_bootstrap.py
# → รันซ้ำด้วย env เดียวกับ repo หลัก (มี .env): 5 passed — failure เป็น environment
#   artifact (worktree ไม่มี .env → health degraded) ไม่ใช่ code regression

$ ./scripts/evaluate http://127.0.0.1:8113
exit 1 · completion 0.0 · healthStatus 200
notes: reset ก่อน/หลังประเมินคืน HTTP 401 · "ไม่มีการกำหนดค่า Gemini..." (field เก่า)
→ ไม่ผ่านแบบ pre-existing (สาเหตุเดิมตาม A3 — ดู §6.2) ไม่ใช่ regression
```

## 9. สิ่งที่ยังต้องให้มนุษย์ทำก่อนเดโมจริง

1. ยืนยัน `.env` ของเครื่องเดโมครบและเป็นค่าที่อนุมัติ (เอกสารนี้ไม่เก็บค่าใด)
2. ทดสอบ LINE จริง (ส่งข้อความเข้า OA แล้วได้รับการตอบ) และ voice ผ่านไมโครโฟนจริง —
   ช่องผลใน `DEMO-VERIFICATION.md` §2.4/§2.5 เว้นไว้ให้กรอกเอง
3. เดินสคริปต์ §2 ซ้อมอย่างน้อย 1 รอบบนเครื่องจริงที่ใช้เดโม
4. ตัดสินใจว่าจะ commit งาน dirty เดิม (S1/S2 — code + tests) ก่อนวันเดโมหรือไม่
   ปัจจุบัน pytest ผ่านบน working tree ที่รวมงานนั้นแล้ว
