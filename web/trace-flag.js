/* ============================================================
 * PEA One Agent — เงื่อนไขการเปิดแผง trace ของหน้าเดโม
 *
 * แผง "การตรวจสอบ" ถูกซ่อนไว้เป็นค่าเริ่มต้นเพื่อให้หน้าจอเดโมสะอาด
 * แต่ PRD (Auditable, not introspective) ยังต้องเรียกดูได้ทันทีเมื่อกรรมการถาม
 * จึงเปิดด้วย query string เช่น index.html?trace=1
 * แยกเป็นโมดูลเพื่อให้เทสรันเงื่อนไขจริงได้ด้วย Node.js โดยไม่ต้องมี DOM
 * ============================================================ */

export function isTracePanelEnabled(search) {
  const value = new URLSearchParams(search).get('trace');
  return value === '1';
}
