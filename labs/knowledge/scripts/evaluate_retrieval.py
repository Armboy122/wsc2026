"""ตัวอย่างตรวจเอกสารเป้าหมายในสามอันดับแรก ไม่วัดความถูกต้องคำตอบ AI"""
from pathlib import Path
from voice_assistant.contracts import SearchInput
from voice_assistant.plugins.knowledge import KnowledgePlugin

cases = [
    ("ขอคืนเงินประกันการใช้ไฟฟ้าต้องทำอย่างไร", "PEA_ขอคืนเงินประกันการใช้ไฟฟ้า.md"),
    ("ลงทะเบียนขอผ่อนชำระค่าไฟฟ้า", "PEA_ลงทะเบียนขอผ่อนชำระค่าไฟฟ้า.md"),
    ("ขอใช้ไฟฟ้าใหม่บุคคลธรรมดาต้องใช้เอกสารอะไร", "PEA_ขอใช้ไฟฟ้าใหม่_บุคคลธรรมดา.md"),
    ("ขึ้นทะเบียนซื้อขายใบรับรองพลังงานหมุนเวียน REC", "PEA_ขึ้นทะเบียนซื้อขายใบรับรองพลังงานหมุนเวียน_REC.md"),
]
plugin = KnowledgePlugin(Path("../../knowledge"))
passed = 0
for question, expected in cases:
    sources = [d.source_id for d in plugin.search(SearchInput(query=question)).evidence]
    ok = expected in sources
    passed += ok
    print(f"{'ผ่าน' if ok else 'ไม่ผ่าน'}: {question}\n  {sources}")
print(f"พบเอกสารเป้าหมายในสามอันดับแรก {passed}/{len(cases)} ตัวอย่าง")
raise SystemExit(0 if passed == len(cases) else 1)
