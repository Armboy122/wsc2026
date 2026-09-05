# D3.7 — บันทึกการตรวจสอบขั้นสุดท้ายและการซ้อมเดโม (P5)

> **สถานะ**: กองที่ agent รันเองได้ = **ตรวจแล้ว ณ วันที่ 2026-09-06** (worktree
> `agentandtool-plugin-v2-autonomous`, commit ฐาน `217a91dd5b7f851e0012655834dd5eabad424b8c`)
> กองที่ต้องมีมนุษย์เดินเอง = **รอมนุษย์ยืนยัน / ไม่ได้ทดสอบ** — ห้ามอ่านว่าผ่าน
> เอกสารนี้บันทึกคำสั่งจริง ผลลัพธ์จริง และข้อจำกัดตามตรงเท่านั้น (PRD §14)

---

## 1. กองที่ agent รันเอง — ผลจริง

### 1.1 `main_agent.py` ไม่มีชื่อ tool/action หลงเหลือ (D1.5)

```bash
$ grep -c "ToolName\.\|ToolAction\." app/agent/main_agent.py
0
```

ผล: **ผ่าน** — นับได้ 0 (grep คืน exit code 1 เพราะไม่พบบรรทัดใด ซึ่งคือพฤติกรรมที่ต้องการ)

### 1.2 `app/prompts/` ถูกลบแล้ว (D3.2)

```bash
$ ls app/prompts/
ls: app/prompts/: No such file or directory
```

ผล: **ผ่าน** — ไดเรกทอรีไม่มีอยู่จริง (prompt อยู่ใน DB ตาม D3.2)

### 1.3 Full pytest

```bash
$ .venv/bin/python -m pytest -q
634 passed, 7 warnings in 5.25s
```

ผล: **ผ่าน** — full suite 634 tests; จำนวนนี้คือผลที่รันจริง ณ วันตรวจ

### 1.4 SSRF — ปุ่ม "ลองยิงดู" ใน APP_ENV=production (D3.5)

**วิธีรันจริง**: คำสั่งต่อไปนี้สร้างรหัสผ่านชั่วคราวใน process, ใช้ cookie/log ชั่วคราว,
สตาร์ต server จริง **ไม่มี `--reload`**, ตรวจ health, ล็อกอิน, ยิง route และ cleanup
ทั้ง process กับไฟล์ชั่วคราวเมื่อจบ:

```bash
(
set -eu
P5_ADMIN_PASSWORD="$(openssl rand -hex 16)"
P5_COOKIE_JAR="$(mktemp)"
P5_SERVER_LOG="$(mktemp)"
export APP_ENV=production ADMIN_PASSWORD="$P5_ADMIN_PASSWORD"
P5_PID=""
cleanup() {
  if [ -n "$P5_PID" ]; then
    kill "$P5_PID" 2>/dev/null || true
    wait "$P5_PID" 2>/dev/null || true
  fi
  # remove temporary cookie/log files
  unlink "$P5_COOKIE_JAR" 2>/dev/null || true
  unlink "$P5_SERVER_LOG" 2>/dev/null || true
  unset APP_ENV ADMIN_PASSWORD P5_ADMIN_PASSWORD
}
trap cleanup EXIT
.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8123 >"$P5_SERVER_LOG" 2>&1 &
P5_PID=$!
P5_HEALTH=""
for attempt in $(seq 1 50); do
  if P5_HEALTH="$(curl -fsS http://127.0.0.1:8123/health 2>/dev/null)"; then break; fi
  sleep 0.1
done
printf 'health=%s\n' "$P5_HEALTH"
curl -fsS -X POST -c "$P5_COOKIE_JAR" -H 'content-type: application/json' \
  -d "{\"password\":\"$P5_ADMIN_PASSWORD\"}" \
  http://127.0.0.1:8123/api/v1/admin/login
printf '\n'
curl -fsS -X POST -b "$P5_COOKIE_JAR" -H 'content-type: application/json' \
  -d '{"httpMethod":"GET","urlTemplate":"https://127.0.0.1/","input":{}}' \
  http://127.0.0.1:8123/api/v1/admin/tools/try
printf '\n'
curl -fsS -X POST -b "$P5_COOKIE_JAR" -H 'content-type: application/json' \
  -d '{"httpMethod":"GET","urlTemplate":"https://169.254.169.254/latest/meta-data/","input":{}}' \
  http://127.0.0.1:8123/api/v1/admin/tools/try
printf '\n'
rg -n 'oms_tool.*disabled|failed validation.*oms_tool' "$P5_SERVER_LOG" || true
printf 'cleanup=registered\n'
)
```

ผลจริงจากการรันบน port 8123 (PID ที่คำสั่งสร้างถูกหยุดโดย `cleanup`):

```text
health={"status":"degraded","llmAdapter":"unavailable","knowledgeBackend":"unavailable","simulationMode":true}
{"authenticated":true}
{"ok":false,"reason":"internal_ip","error":"ปลายทางเป็น IP ภายใน/ไม่ปลอดภัย: 127.0.0.1"}
{"ok":false,"reason":"internal_ip","error":"ปลายทางเป็น IP ภายใน/ไม่ปลอดภัย: 169.254.169.254"}
1:Declarative tool 'oms_tool' (id=1) failed validation and was disabled: urlTemplate ของ action 'get_outage_by_ca' ไม่ผ่าน network policy: ไม่ใช่ HTTPS: production ต้องใช้ https:// เท่านั้น
cleanup=registered
```

เวลาที่วัดจากการรัน block นี้ล่าสุด: **0.705 วินาทีรวม** (รวม startup, health, login,
และสอง SSRF requests; เวลาอาจเปลี่ยนตามเครื่อง)

ผล: **ผ่าน** — ทั้ง `127.0.0.1` และ `169.254.169.254` ถูกปฏิเสธที่ชั้นนโยบาย **ก่อนมีการยิง
HTTP จริง** (`reason: internal_ip` มาจาก `CONTRACTS-V2.md §7.2` และ implementation ใน
`app/tools/network_policy.py`)
พร้อมเหตุผลภาษาไทยที่ admin อ่านได้. Health HTTP request สำเร็จแต่แอปตอบสถานะ `degraded`
เพราะ provider ไม่พร้อมใน process นี้ — ไม่ถือเป็นการยืนยัน provider integration

ข้อจำกัดที่สังเกตได้จาก startup log จริง: declarative `oms_tool` ถูกปิดเพราะ
`urlTemplate` ของ `get_outage_by_ca` ไม่ผ่าน production HTTPS policy
(`ไม่ใช่ HTTPS: production ต้องใช้ https:// เท่านั้น`); ไม่ได้สรุปว่า OMS demo path ผ่าน

### 1.5 ตรวจ environment (boolean เท่านั้น — ไม่มีการพิมพ์ค่าใด)

```bash
printf '.env exists: '
if [ -f .env ]; then printf 'yes'; else printf 'no'; fi
printf '\n'
for key in LINE_CHANNEL_SECRET LINE_CHANNEL_ACCESS_TOKEN; do
  printf '%s set: ' "$key"
  if [ -n "${!key:-}" ]; then printf 'yes'; else printf 'no'; fi
  printf '\n'
done
```

ผลจริง:

```text
.env exists: no
LINE_CHANNEL_SECRET set: no
LINE_CHANNEL_ACCESS_TOKEN set: no
```

ผล: ตรวจ boolean แล้วพบว่าไม่มีไฟล์ `.env` และไม่มีตัวแปร LINE ทั้งสองค่าใน process นี้
→ เส้นทาง LINE **ไม่ได้ทดสอบ** (ดูข้อ 2.4)

### 1.6 Mutation test (กติกาข้อ 10 — พิสูจน์ว่าเทสไม่ vacuous)

ทดสอบ guard production จริงที่ตัดสินผล SSRF โดยลบบรรทัด
`ipaddress.ip_network("169.254.0.0/16")` จาก `_BLOCKED_NETWORKS` ใน
`app/tools/network_policy.py` ชั่วคราวด้วย `apply_patch` แล้วรัน:

```bash
.venv/bin/python -m pytest -q app/tools/tests/test_network_policy.py
```

ผล mutation จริง: **3 failed, 34 passed** — ล้มที่
`test_production_blocks_cloud_metadata_ip`,
`test_production_blocks_ipv4_mapped_ipv6_metadata` และ
`test_production_blocklist_overrides_allowlist` ตามคาด. จากนั้น restore บรรทัดเดิมด้วย
`apply_patch`, รันซ้ำได้ **37 passed**, และ `git diff -- app/tools/network_policy.py`
ว่างเปล่า. ไม่มี production mutation ค้างอยู่ใน commit นี้

---

## 2. กองที่ต้องมีมนุษย์เดินเอง — รอมนุษย์ยืนยัน / ไม่ได้ทดสอบ

> ช่องผลลัพธ์ด้านล่าง**เว้นไว้ให้มนุษย์กรอกเอง** ห้ามกรอกแทน
> แต่ละรายการระบุคำสั่ง/ขั้นตอนที่ต้องทำและเงื่อนไขที่จะนับว่าผ่าน

### 2.1 `./scripts/evaluate http://127.0.0.1:8000` — ⏳ รอมนุษย์ยืนยัน

- ต้องสตาร์ต server จริง (ไม่มี `--reload`) ก่อน: `uvicorn app.main:app --host 127.0.0.1 --port 8000`
- agent ไม่รันสคริปต์นี้เอง เพราะเป็นการประเมินคุณภาพคำตอบที่ต้องใช้ provider key จริง
  และการตัดสินผลลัพธ์เป็นของมนุษย์
- ผลลัพธ์: _(เว้นไว้ให้กรอก)_

### 2.2 เส้นทาง knowledge (ถามความรู้ → เห็น citation) — ⏳ รอมนุษย์ยืนยัน

- ถามผ่านหน้าเว็บ, ตรวจว่าคำตอบ grounded พร้อม citation ที่ชี้ไฟล์จริงใน `knowledge/source`
- ทดสอบถามต่อ (follow-up) หลังได้คำตอบ knowledge ด้วย
- ผลลัพธ์: _(เว้นไว้ให้กรอก)_

### 2.3 แจ้งไฟดับ prepare → confirm → submit — ⏳ รอมนุษย์ยืนยัน

- เดินทาง OMS: เตรียมคำขอ → เห็นหน้ายืนยัน → กดยืนยันเอง → สถานะเปลี่ยน
- กรรมการต้องเห็นว่า "แชตเตรียมได้อย่างเดียว มนุษย์เป็นคนยืนยันเสมอ"
- ผลลัพธ์: _(เว้นไว้ให้กรอก)_

### 2.4 LINE — ❌ ไม่ได้ทดสอบ (ข้อจำกัดชัดเจน)

- ตรวจสอบแล้ว (ข้อ 1.5): worktree นี้ไม่มี `.env` และไม่มี `LINE_CHANNEL_SECRET` /
  `LINE_CHANNEL_ACCESS_TOKEN` ทั้งคู่
- ตามกติกา P5 และข้อจำกัดของ environment: ถ้าไม่มี credentials ต้องบันทึกว่า "ไม่ได้ทดสอบ"
  **ห้ามเขียนว่าผ่าน**
- จะทดสอบได้เมื่อมนุษย์ตั้งค่าทั้งสองตัวแล้วเดิน webhook จริง
- ผลลัพธ์: ไม่ได้ทดสอบ — ยังไม่มี credentials

### 2.5 Voice — ❌ ไม่ได้ทดสอบ (ข้อจำกัดชัดเจน)

- ต้องมีไมโครโฟนจริงและเบราว์เซอร์ที่เปิดสิทธิ์ microphone — agent ไม่มีทางรันแทนได้
- ผลลัพธ์จากมนุษย์: _(เว้นไว้ให้กรอก)_
- ผลลัพธ์: ไม่ได้ทดสอบ — ต้องมีมนุษย์พูดผ่านไมโครโฟนจริง

### 2.6 สร้าง tool ใหม่จากหน้า admin → ลองยิง → เปิดใช้ → AI เรียก — ⏳ รอมนุษย์ยืนยัน

- ขั้นตอน: ล็อกอิน admin → สร้าง declarative tool ใหม่ (ปลายทาง REST จริงที่อนุญาต)
  → กด "ลองยิงดู" เห็น response จริง → เปิดใช้ → ถาม AI แล้ว AI เรียก tool ใหม่ได้ในเทิร์นถัดไป
- ส่วน SSRF ของปุ่ม "ลองยิงดู" ถูกพิสูจน์แล้วโดย agent (ข้อ 1.4) — ที่เหลือคือภาพรวม
  end-to-end ผ่าน UI ซึ่งต้องเดินด้วยมือ
- ผลลัพธ์: _(เว้นไว้ให้กรอก)_

---

## 3. ข้อจำกัดที่บันทึกตามจริง

1. **uvicorn ต้องรันไม่มี `--reload`** — `app/main.py` เรียก `asyncio.run()` ระดับ module
   ซึ่งพังเมื่อ reload โหลดแอปใน running event loop (แผนแก้อยู่ที่ P9) การตรวจทั้งหมดใน
   เอกสารนี้จึงรันแบบไม่มี `--reload`
2. **ADMIN_PASSWORD ไม่ได้ตั้งถาวรใน worktree นี้** — การล็อกอิน admin สำหรับทดสอบ SSRF
   ใช้ shell environment ชั่วคราวสำหรับรันครั้งเดียวเท่านั้น (ค่าถูกใช้แล้วทิ้ง
   ไม่บันทึกในเอกสาร/ไฟล์ใด)
3. **LINE credentials ไม่มี** — เส้นทาง LINE ไม่ได้ทดสอบ (ข้อ 2.4)
4. **ปลายทางที่ทดสอบ SSRF เป็น literal IP** — ครอบคลุม blocklist ตรง ๆ ตามสเปก D3.5;
   กรณี DNS rebinding มีเทสครอบอยู่ใน `app/tools/tests/test_network_policy.py` แล้ว (37 ตัว)
5. **ไม่ได้ทดสอบ provider LLM จริง** — การเรียกโมเดลจริง (Gemini/อื่น) ไม่อยู่ในกองที่
   agent ตรวจ; ไม่มีการตรวจหรือบันทึกค่า secret ใด

---

## 4. สรุปสถานะ ณ วันตรวจ

| รายการ | สถานะ |
|---|---|
| grep ToolName/ToolAction ใน main_agent.py = 0 | ✅ ตรวจแล้ว ผ่าน |
| app/prompts/ ถูกลบ | ✅ ตรวจแล้ว ผ่าน |
| Full pytest | ✅ 634 passed |
| SSRF 127.0.0.1 / 169.254.169.254 ปฏิเสธพร้อมเหตุผล (APP_ENV=production) | ✅ ตรวจแล้ว ผ่าน |
| Mutation test (production metadata guard) | ✅ 3 failures เมื่อ guard หาย แล้ว 37 passed หลัง restore |
| `./scripts/evaluate` | ⏳ รอมนุษย์ยืนยัน |
| เส้นทาง knowledge | ⏳ รอมนุษย์ยืนยัน |
| OMS prepare → confirm | ⏳ รอมนุษย์ยืนยัน |
| LINE | ❌ ไม่ได้ทดสอบ (ไม่มี credentials) |
| Voice | ❌ ไม่ได้ทดสอบ (ต้องมีไมโครโฟนจริง) |
| สร้าง tool จากหน้า admin แบบ end-to-end ผ่าน UI | ⏳ รอมนุษย์ยืนยัน |
