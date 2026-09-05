/* Pure form-builder rules shared by the admin UI and deterministic tests. */
const HTTP_METHODS = new Set(["GET", "POST", "PUT", "PATCH", "DELETE"]);
export function normalizeOperation(input = {}) {
  const mode = input.mode || "read";
  const operation = { action: String(input.action || "").trim(), policy: input.policy || "plain_read", exposure: mode === "submit" ? "internal" : (input.exposure || "llm"), mode, submitAction: mode === "prepare" ? String(input.submitAction || "").trim() || null : null, httpMethod: mode === "prepare" ? null : (input.httpMethod || "GET"), urlTemplate: mode === "prepare" ? null : String(input.urlTemplate || "").trim(), inputSchema: input.inputSchema || { type: "object", properties: {}, required: [], additionalProperties: false } };
  if (input.outputSchema !== undefined) operation.outputSchema = input.outputSchema;
  if (input.limits !== undefined) operation.limits = input.limits;
  if (input.clientContext !== undefined) operation.clientContext = input.clientContext;
  return operation;
}
export function buildOperationPayload(formValues) { return normalizeOperation(formValues); }
export function validateOperation(operation, index = 0, operations = [operation]) {
  const op = normalizeOperation(operation); const label = `Operation ที่ ${index + 1} (${op.action || "ยังไม่มีชื่อ"})`;
  if (!op.action) return `Operation ที่ ${index + 1}: กรุณากรอกชื่อ action`;
  if (op.mode === "prepare") { if (!op.submitAction) return `${label}: กรุณาเลือก submitAction`; const target = operations.find((candidate) => candidate.action === op.submitAction); if (!target || target.mode !== "submit") return `${label}: submitAction ต้องชี้ไปยัง operation mode=submit`; }
  else if (!op.urlTemplate) return `${label}: กรุณากรอก URL template`;
  if (op.mode !== "prepare" && !HTTP_METHODS.has(op.httpMethod)) return `${label}: HTTP method ไม่ถูกต้อง`;
  return null;
}
export function validateToolPayload(payload) {
  if (!/^[a-z0-9_-]+$/.test(payload.slug || "")) return "ชื่อระบบ (slug) ต้องเป็น a-z 0-9 _ - เท่านั้น";
  if (!payload.displayName) return "กรุณากรอกชื่อที่แสดง";
  const operations = (payload.operations || []).map(normalizeOperation);
  for (let index = 0; index < operations.length; index += 1) { const error = validateOperation(operations[index], index, operations); if (error) return error; }
  return null;
}
export function buildToolPayload(values) { return { ...values, slug: String(values.slug || "").trim(), displayName: String(values.displayName || "").trim(), operations: (values.operations || []).map(buildOperationPayload) }; }
