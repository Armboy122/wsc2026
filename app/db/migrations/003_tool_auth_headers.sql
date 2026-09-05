-- P1: tool_auth เก็บรูปแบบ header ได้ต่อแถว — OMS ต้องการ X-API-Key ไม่ใช่ Authorization: Bearer
-- DEFAULT ทำให้ tool เดิมที่ไม่ได้ตั้งค่ายังยิง Authorization: Bearer เหมือนเดิม (พฤติกรรมไม่เปลี่ยน)
-- scheme ว่าง = ส่งค่า secret ตรง ๆ ไม่มี prefix (กรณี X-API-Key)
ALTER TABLE tool_auth ADD COLUMN header_name TEXT NOT NULL DEFAULT 'Authorization';
ALTER TABLE tool_auth ADD COLUMN scheme TEXT NOT NULL DEFAULT 'Bearer';

-- DB v2 แยกไม่ได้ว่า OMS ไม่เคยถูก seed หรือผู้ใช้ลบ auth ไปแล้ว จึงแก้ legacy ที่ขาด
-- credential เพียงครั้งเดียวระหว่าง migration เท่านั้น; หลังบันทึก version 3 แล้ว
-- seed_oms_tool จะไม่แตะ tool เดิม ทำให้การลบของผู้ใช้ยังคงเป็น authoritative.
INSERT INTO tool_auth (tool_id, type, secret_ref, header_name, scheme)
SELECT tool.id, 'api_key', 'OMS_API_KEY', 'X-API-Key', ''
FROM tool
WHERE tool.slug = 'oms_tool'
  AND tool.source = 'db'
  AND NOT EXISTS (
      SELECT 1 FROM tool_auth WHERE tool_auth.tool_id = tool.id
  );
