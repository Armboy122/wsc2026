/* Pure form-builder rules shared by the admin UI and deterministic tests. */

const HTTP_METHODS = new Set(["GET", "POST", "PUT", "PATCH", "DELETE"]);
const CONTROLLED_OPERATION_KEYS = new Set([
  "action",
  "policy",
  "exposure",
  "mode",
  "submitAction",
  "httpMethod",
  "urlTemplate",
  "inputSchema",
]);
const CONTROLLED_PROPERTY_KEYS = new Set(["type", "description", "anyOf"]);

function clone(value) {
  if (value === undefined) return undefined;
  return JSON.parse(JSON.stringify(value));
}

function mergeObject(base, overrides) {
  return { ...(clone(base) || {}), ...(clone(overrides) || {}) };
}

function normalizeOperation(input = {}) {
  const mode = input.mode || "read";
  const operation = {
    action: String(input.action || "").trim(),
    policy: input.policy || "plain_read",
    exposure: mode === "submit" ? "internal" : input.exposure || "llm",
    mode,
    submitAction:
      mode === "prepare" ? String(input.submitAction || "").trim() || null : null,
    httpMethod: mode === "prepare" ? null : input.httpMethod || "GET",
    urlTemplate: mode === "prepare" ? null : String(input.urlTemplate || "").trim(),
    inputSchema:
      input.inputSchema || {
        type: "object",
        properties: {},
        required: [],
        additionalProperties: false,
      },
  };
  if (input.outputSchema !== undefined) operation.outputSchema = clone(input.outputSchema);
  if (input.limits !== undefined) operation.limits = clone(input.limits);
  if (input.clientContext !== undefined) operation.clientContext = clone(input.clientContext);
  return operation;
}

function mergeSchemaWithBaseline(schema, baseline) {
  if (!baseline) return clone(schema);
  const merged = mergeObject(baseline, schema);
  merged.properties = {};
  const baselineProperties = baseline.properties || {};
  const properties = schema.properties || {};
  Object.keys(properties).forEach((name) => {
    merged.properties[name] = mergeObject(baselineProperties[name], properties[name]);
  });
  return merged;
}

export function detectMetadataLoss(baseline, candidate, path = "") {
  if (baseline === undefined || baseline === null || typeof baseline !== "object") return [];
  if (candidate === undefined || candidate === null || typeof candidate !== "object") {
    return [path || "metadata"];
  }
  const losses = [];
  const readOnlyToolKeys = new Set(["hasAuth", "source", "editable", "selfDisabledReason"]);
  Object.keys(baseline).forEach((key) => {
    if (!(key in candidate) && !(path === "" && readOnlyToolKeys.has(key))) {
      losses.push(path ? `${path}.${key}` : key);
    }
  });
  if (baseline.properties && candidate.properties) {
    Object.keys(baseline.properties).forEach((name) => {
      if (!(name in candidate.properties)) {
        const property = baseline.properties[name] || {};
        const opaqueKeys = Object.keys(property).filter(
          (key) => !CONTROLLED_PROPERTY_KEYS.has(key),
        );
        if (opaqueKeys.length || property.anyOf) {
          losses.push(`${path ? `${path}.` : ""}properties.${name}`);
        }
      }
    });
  }
  if (baseline.items || candidate.items) {
    losses.push(...detectMetadataLoss(
      baseline.items,
      candidate.items,
      path ? `${path}.items` : "items",
    ));
  }
  if (Array.isArray(baseline.anyOf) && Array.isArray(candidate.anyOf)) {
    baseline.anyOf.forEach((branch, index) => {
      const matching = candidate.anyOf.find((item) => item.type === branch.type) || candidate.anyOf[index];
      losses.push(...detectMetadataLoss(
        branch,
        matching,
        `${path ? `${path}.` : ""}anyOf.${index}`,
      ));
    });
  }
  if (baseline.inputSchema || candidate.inputSchema) {
    losses.push(...detectMetadataLoss(
      baseline.inputSchema,
      candidate.inputSchema,
      path ? `${path}.inputSchema` : "inputSchema",
    ));
  }
  return losses;
}

export function mergeOperationWithBaseline(formValues, baseline) {
  const normalized = normalizeOperation(formValues);
  if (!baseline) return normalized;
  const merged = mergeObject(baseline, normalized);
  Object.keys(normalized).forEach((key) => {
    if (CONTROLLED_OPERATION_KEYS.has(key)) merged[key] = clone(normalized[key]);
  });
  if (!("submitAction" in baseline) && normalized.submitAction === null) {
    delete merged.submitAction;
  }
  merged.inputSchema = mergeSchemaWithBaseline(normalized.inputSchema, baseline.inputSchema);
  return merged;
}

export function buildOperationPayload(formValues, baseline) {
  return mergeOperationWithBaseline(formValues, baseline);
}

export function validateOperation(operation, index = 0, operations = [operation]) {
  const op = normalizeOperation(operation);
  const label = `Operation ที่ ${index + 1} (${op.action || "ยังไม่มีชื่อ"})`;
  if (!op.action) return `Operation ที่ ${index + 1}: กรุณากรอกชื่อ action`;
  if (op.mode === "prepare") {
    if (!op.submitAction) return `${label}: กรุณาเลือก submitAction`;
    const target = operations.find((candidate) => candidate.action === op.submitAction);
    if (!target || target.mode !== "submit") {
      return `${label}: submitAction ต้องชี้ไปยัง operation mode=submit`;
    }
  } else if (!op.urlTemplate) {
    return `${label}: กรุณากรอก URL template`;
  }
  if (op.mode !== "prepare" && !HTTP_METHODS.has(op.httpMethod)) {
    return `${label}: HTTP method ไม่ถูกต้อง`;
  }
  return null;
}

export function validateToolPayload(payload) {
  if (!/^[a-z0-9_-]+$/.test(payload.slug || "")) {
    return "ชื่อระบบ (slug) ต้องเป็น a-z 0-9 _ - เท่านั้น";
  }
  if (!payload.displayName) return "กรุณากรอกชื่อที่แสดง";
  const operations = (payload.operations || []).map(normalizeOperation);
  for (let index = 0; index < operations.length; index += 1) {
    const error = validateOperation(operations[index], index, operations);
    if (error) return error;
  }
  return null;
}

const REQUEST_OPERATION_KEYS = new Set([
  "action", "policy", "exposure", "mode", "submitAction", "httpMethod",
  "urlTemplate", "inputSchema", "outputSchema", "limits", "clientContext",
]);
const REQUEST_TOOL_KEYS = new Set([
  "slug", "displayName", "description", "enabled", "authEnvVar",
  "authHeaderName", "authScheme", "operations",
]);

function filterRequestKeys(value, keys) {
  return Object.fromEntries(Object.entries(value || {}).filter(([key]) => keys.has(key)));
}

function baselineOperationFor(operation, baselines, used) {
  const action = String(operation.action || "").trim();
  if (!action) return undefined;
  const index = (baselines || []).findIndex((candidate, candidateIndex) =>
    !used.has(candidateIndex) && candidate && candidate.action === action,
  );
  if (index < 0) return undefined;
  used.add(index);
  return baselines[index];
}

export function buildToolPayload(values, baseline) {
  const payload = filterRequestKeys(mergeObject(baseline, values), REQUEST_TOOL_KEYS);
  delete payload.authEnvVar;
  payload.slug = String(values.slug || "").trim();
  payload.displayName = String(values.displayName || "").trim();
  const usedBaselines = new Set();
  payload.operations = (values.operations || []).map((operation) =>
    filterRequestKeys(
      buildOperationPayload(operation, baselineOperationFor(
        operation, baseline && baseline.operations, usedBaselines,
      )),
      REQUEST_OPERATION_KEYS,
    ),
  );
  return payload;
}

export function buildTryPayload(options = {}) {
  const {
    httpMethod = "GET",
    urlTemplate = "",
    input = {},
    inputSchema = null,
    toolSlug = null,
    authEnv = "",
    authHeader = "Authorization",
    authScheme = "Bearer",
    removeAuth = false,
    hasSavedAuth = false,
  } = options;

  const payload = {
    httpMethod: String(httpMethod || "GET").trim(),
    urlTemplate: String(urlTemplate || "").trim(),
    input: input || {},
  };
  if (inputSchema) {
    payload.inputSchema = clone(inputSchema);
  }
  if (toolSlug) {
    payload.toolSlug = String(toolSlug).trim();
  }

  const trimmedAuthEnv = String(authEnv || "").trim();
  const trimmedHeader = String(authHeader || "").trim() || "Authorization";
  const trimmedScheme =
    authScheme !== null && authScheme !== undefined ? String(authScheme).trim() : "Bearer";

  if (removeAuth) {
    // เลือกลบ credential -> ลองโดยไม่ส่ง auth
    payload.authEnvVar = null;
  } else if (trimmedAuthEnv) {
    // ระบุชื่อ env var ใหม่ -> ใช้ credential ใหม่สำหรับการลอง
    payload.authEnvVar = trimmedAuthEnv;
    payload.authHeaderName = trimmedHeader;
    payload.authScheme = trimmedScheme;
  } else if (toolSlug && hasSavedAuth) {
    // แก้ tool เดิม ไม่เปลี่ยน credential (หรือแก้เฉพาะ header/scheme)
    // ละ authEnvVar ไว้เพื่อให้ server preserve secret_ref แต่ส่ง header/scheme ตามฟอร์ม
    payload.authHeaderName = trimmedHeader;
    payload.authScheme = trimmedScheme;
  }

  return payload;
}

// เหตุผลจาก POST /tools/try ที่หมายถึง "ระบบบล็อกก่อนส่งคำขอ" (นโยบาย/validation) —
// ทุกตัวไม่เคยมี HTTP response จริงจากปลายทาง ต่างจาก "request_failed" ซึ่งพยายาม
// เชื่อมต่อแล้วแต่ล้มเหลว (DNS/refused/timeout — httpx.RequestError ทุกชนิด)
const TRY_CONNECTION_FAILED_REASON = "request_failed";

function classifyHttpStatus(statusCode) {
  if (typeof statusCode !== "number" || Number.isNaN(statusCode)) return "unknown";
  if (statusCode >= 200 && statusCode < 300) return "success";
  if (statusCode >= 400 && statusCode < 500) return "client_error";
  if (statusCode >= 500 && statusCode < 600) return "server_error";
  return "unknown";
}

function httpErrorHint(statusCode) {
  if (statusCode === 401 || statusCode === 403) {
    return "ตรวจสิทธิ์หรือ credential ที่ตั้งค่าไว้กับปลายทางนี้";
  }
  if (statusCode === 404) {
    return "ตรวจ endpoint/resource ปลายทาง — URL หรือ path อาจไม่ถูกต้อง";
  }
  if (statusCode === 429) {
    return "ปลายทางจำกัดอัตราการเรียก (rate limit) — ลองใหม่ภายหลัง";
  }
  if (statusCode >= 500) {
    return "ปลายทางมีปัญหาฝั่งเซิร์ฟเวอร์";
  }
  return "ปลายทางปฏิเสธคำขอ";
}

// ตีความผล /tools/try เป็นสถานะที่ผู้ดูแลแยกได้ 4 แบบ (A2):
// HTTP สำเร็จ (2xx) / HTTP ไม่สำเร็จแต่ปลายทางตอบแล้ว (4xx/5xx) /
// ระบบบล็อกก่อนส่งคำขอ (นโยบาย/validation) / เชื่อมต่อปลายทางไม่ได้
// คืนค่าล้วน ๆ ไม่แตะ DOM — เพื่อให้เทสได้โดยไม่ต้องมี browser/jsdom
export function describeTryOutcome(data) {
  if (!data || data.ok !== true) {
    const reason = (data && data.reason) || "unknown";
    const message = (data && data.error) || "";
    if (reason === TRY_CONNECTION_FAILED_REASON) {
      return {
        kind: "connection_failed",
        cssClass: "try-status-blocked",
        label: "เชื่อมต่อปลายทางไม่ได้ (" + reason + "): " + message,
      };
    }
    return {
      kind: "blocked",
      cssClass: "try-status-blocked",
      // "บล็อก" ในที่นี้คือระบบเอง (นโยบาย/validation) ไม่ใช่ปลายทางตอบมาแล้ว
      label: "ระบบบล็อกก่อนส่งคำขอ (" + reason + "): " + message,
    };
  }

  const response = data.response || {};
  const statusCode = response.statusCode;
  const elapsedMs = response.elapsedMs;
  const category = classifyHttpStatus(statusCode);

  if (category === "success") {
    return {
      kind: "success",
      cssClass: "try-status-ok",
      label: "HTTP สำเร็จ · " + statusCode + " · " + elapsedMs + " ms",
      note:
        "HTTP สำเร็จบอกแค่ว่าระบบเชื่อมต่อปลายทางได้ — ยังไม่พิสูจน์ว่า AI จะเรียกใช้ tool นี้ได้ครบทุกกรณี",
    };
  }

  const hint = category === "unknown" ? "" : httpErrorHint(statusCode);
  return {
    kind: "http_error",
    cssClass: "try-status-warn",
    label:
      "HTTP ไม่สำเร็จ · " + statusCode + " · " + elapsedMs + " ms" + (hint ? " — " + hint : ""),
  };
}
