-- D2.6 / pre-D2.7: เพิ่ม http_method และ url_template สำหรับ declarative tools
ALTER TABLE tool_operation ADD COLUMN http_method TEXT CHECK (http_method IN ('GET', 'POST', 'PUT', 'PATCH', 'DELETE'));
ALTER TABLE tool_operation ADD COLUMN url_template TEXT;
