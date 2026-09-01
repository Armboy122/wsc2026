/* ============================================================
 * linkify.js — แปลง URL http/https ในข้อความ HTML ที่ escape แล้ว
 * ให้เป็นลิงก์เปิดแท็บใหม่แบบปลอดภัย
 *
 * สัญญาการใช้งาน:
 *   - ฟังก์ชันนี้รับข้อความที่ผ่าน escapeHtml() มาแล้วเท่านั้น
 *     (ห้ามส่ง raw text) เพื่อให้อักขระ `<`, `>`, `"`, `'`, `&`
 *     ถูกแปลงเป็นเอนทิตีเรียบร้อยก่อน จึงไม่มีทางเกิด XSS
 *   - linkify เฉพาะ http:// และ https:// เท่านั้น ไม่มี scheme อื่น
 *   - ทุกลิงก์มี target="_blank" + rel="noopener noreferrer"
 * ============================================================ */

const URL_PATTERN = /https?:\/\/[^\s<>"']+/g;

/**
 * แปลง URL http/https ในข้อความที่ escape แล้วเป็น <a> เปิดแท็บใหม่
 * @param {string} escapedText ข้อความที่ผ่าน escapeHtml() มาแล้ว
 * @returns {string} ข้อความ HTML ที่มีลิงก์เฉพาะ http/https
 */
export function linkifySafeHtml(escapedText) {
  return String(escapedText).replace(URL_PATTERN, (url) =>
    `<a href="${url}" target="_blank" rel="noopener noreferrer">${url}</a>`
  );
}
