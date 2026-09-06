import {
  buildOperationPayload,
  buildToolPayload,
  buildTryPayload,
  describeTryOutcome,
  detectMetadataLoss,
  validateToolPayload,
} from "./admin-form.js";

/* ============================================================
   PEA One Agent — ตรรกะหน้าแอดมิน (D3.3/D3.4/D3.5/D3.6)

   HTML/JS ธรรมดา ไม่มี build step ไม่มีเฟรมเวิร์ก — ต่อยอดเส้นทาง
   /api/v1/admin/* ตาม CONTRACTS-V2 (camelCase ทั้งหมด) จุดสำคัญ:

   - ปุ่ม "ลองยิงดู" (D3.5) ยิงผ่าน API /admin/tools/try เท่านั้น —
     เส้นทางเดียวกับ executor จริง ฝั่งเบราว์เซอร์ไม่ยิง HTTP เอง
     จึงไม่มีทางลัดข้ามนโยบาย SSRF ได้เลย
   - secret รับเฉพาะ "ชื่อ environment variable" ไม่เคยแสดง/เก็บค่า
   - JSON Schema สร้างจาก form builder เสมอ — JSON เป็น read-only preview
   ============================================================ */
(function () {
  "use strict";

  var API = "/api/v1/admin";

  // ---------------------------------------------------------------- ตัวช่วย --

  function $(selector, root) {
    return (root || document).querySelector(selector);
  }

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  // เรียก API admin — คืน {ok, status, data} เสมอ; 401 = เซสชันหมด กลับหน้าล็อกอิน
  async function api(path, options) {
    var response;
    try {
      response = await fetch(API + path, Object.assign({ headers: {} }, options));
    } catch (error) {
      return { ok: false, status: 0, data: { detail: "เชื่อมต่อเซิร์ฟเวอร์ไม่ได้: " + error.message } };
    }
    var data = null;
    try {
      data = await response.json();
    } catch (_error) {
      data = null; // response ไม่ใช่ JSON (เช่น proxy error) — แสดงสถานะแทน
    }
    if (response.status === 401) {
      showLogin();
      return { ok: false, status: 401, data: data || {} };
    }
    return { ok: response.ok, status: response.status, data: data };
  }

  function errorText(result) {
    if (result && result.data && result.data.detail) return String(result.data.detail);
    return "คำขอล้มเหลว (HTTP " + (result ? result.status : "?") + ")";
  }

  function showHidden(node, hidden) {
    node.hidden = hidden;
  }

  // ---------------------------------------------------------------- สถานะ --

  var appEnv = "development";
  var editingSlug = null; // null = สร้างใหม่
  var editingBaseline = null;

  var views = {
    loginView: $("#login-view"),
    appView: $("#app-view"),
    loginForm: $("#login-form"),
    loginPassword: $("#login-password"),
    loginError: $("#login-error"),
    logoutBtn: $("#logout-btn"),
    envBadge: $("#env-badge"),
    toolsList: $("#tools-list"),
    toolsTable: $("#tools-table"),
    newToolBtn: $("#new-tool-btn"),
    toolForm: $("#tool-form"),
    toolFormTitle: $("#tool-form-title"),
    backToListBtn: $("#back-to-list-btn"),
    toolFormElement: $("#tool-form-element"),
    toolSlug: $("#tool-slug"),
    toolDisplayName: $("#tool-display-name"),
    toolDescription: $("#tool-description"),
    toolDescCount: $("#tool-desc-count"),
    toolAuthEnv: $("#tool-auth-env"),
     toolAuthHeader: $("#tool-auth-header"),
     toolAuthScheme: $("#tool-auth-scheme"),
     toolAuthStatus: $("#tool-auth-status"),
     toolRemoveAuthWrap: $("#tool-remove-auth-wrap"),
     toolRemoveAuth: $("#tool-remove-auth"),
    toolEnabled: $("#tool-enabled"),
    operationsContainer: $("#operations-container"),
    addOperationBtn: $("#add-operation-btn"),
    toolFormError: $("#tool-form-error"),
    tabPrompt: $("#tab-prompt"),
    promptContent: $("#prompt-content"),
    promptCharCount: $("#prompt-char-count"),
    promptPreview: $("#prompt-preview"),
    promptError: $("#prompt-error"),
    promptSuccess: $("#prompt-success"),
    savePromptBtn: $("#save-prompt-btn"),
    promptUpdatedAt: $("#prompt-updated-at"),
    promptStatusBadge: $("#prompt-status-badge"),
    operationTemplate: $("#operation-template"),
    fieldRowTemplate: $("#field-row-template"),
  };

  function showLogin() {
    views.appView.hidden = true;
    views.loginView.hidden = false;
    views.loginPassword.value = "";
  }

  function showApp() {
    views.loginView.hidden = true;
    views.appView.hidden = false;
    refreshTools();
  }

  // ------------------------------------------------------- แท็บ / การนำทาง --

  document.querySelectorAll(".nav-tab").forEach(function (tab) {
    tab.addEventListener("click", function () {
      document.querySelectorAll(".nav-tab").forEach(function (other) {
        other.setAttribute("aria-pressed", String(other === tab));
      });
      var isTools = tab.dataset.tab === "tools";
      $("#tab-tools").hidden = !isTools;
      views.tabPrompt.hidden = isTools;
      if (!isTools) refreshPrompt();
    });
  });

  // -------------------------------------------------------- ล็อกอิน (D3.1) --

  views.loginForm.addEventListener("submit", async function (event) {
    event.preventDefault();
    showHidden(views.loginError, true);
    var password = views.loginPassword.value;
    if (!password) {
      views.loginError.textContent = "กรุณากรอกรหัสผ่าน";
      showHidden(views.loginError, false);
      return;
    }
    var result = await api("/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ password: password }),
    });
    if (result.ok) {
      showApp();
    } else {
      views.loginError.textContent = errorText(result);
      showHidden(views.loginError, false);
    }
  });

  views.logoutBtn.addEventListener("click", async function () {
    await api("/logout", { method: "POST" });
    showLogin();
  });

  // --------------------------------------------------- รายการ tool (D3.3) --

  function sourceBadge(source) {
    return source === "code"
      ? el("span", "badge badge-code", "Python plugin (โค้ด)")
      : el("span", "badge badge-db", "declarative (DB)");
  }

  function enabledBadge(enabled) {
    return enabled
      ? el("span", "badge badge-ok", "เปิดใช้งาน")
      : el("span", "badge badge-off", "ปิดใช้งาน");
  }

  function renderToolCard(tool) {
    var card = el("div", "card tool-card");
    var head = el("div", "tool-head");
    var nameWrap = el("div");
    nameWrap.appendChild(el("p", "tool-name", tool.displayName || tool.slug));
    nameWrap.appendChild(el("p", "tool-slug", tool.slug));
    head.appendChild(nameWrap);

    var badges = el("div", "tool-badges");
    badges.appendChild(sourceBadge(tool.source));
    badges.appendChild(enabledBadge(tool.enabled));
     if (tool.hasAuth) badges.appendChild(el("span", "badge badge-ok", "มี credential"));
    head.appendChild(badges);
    card.appendChild(head);

    if (tool.description) {
      card.appendChild(el("p", "muted", tool.description));
    }

    // policy ของแต่ละ operation (D3.3: "แสดง policy ของแต่ละ operation")
    var ops = el("ul", "tool-ops");
    (tool.operations || []).forEach(function (op) {
      var li = el("li");
      li.appendChild(el("span", "op-chip", op.action));
      li.appendChild(el("span", null, "policy: " + op.policy));
      li.appendChild(el("span", "muted", "mode: " + op.mode + " · exposure: " + op.exposure));
      if (op.urlTemplate) {
        li.appendChild(el("span", "muted mono", op.httpMethod + " " + op.urlTemplate));
      }
      ops.appendChild(li);
    });
    card.appendChild(ops);

    // tool ที่ปิดตัวเองต้องแสดงเหตุผล — กัน "หายเงียบ" (D3.3)
    if (tool.selfDisabledReason) {
      card.appendChild(el("p", "hint-note", "tool นี้ถูกปิดโดยระบบ: " + tool.selfDisabledReason));
    }

    var actions = el("div", "tool-actions");
    var editBtn = el("button", "btn btn-secondary btn-sm", "แก้ไข");
    var toggleBtn = el("button", "btn btn-ghost btn-sm", tool.enabled ? "ปิดใช้งาน" : "เปิดใช้งาน");
    if (tool.editable) {
      editBtn.addEventListener("click", function () {
        openToolForm(tool.slug);
      });
      toggleBtn.addEventListener("click", function () {
        toggleTool(tool.slug, !tool.enabled);
      });
    } else {
      // P4: code tool แก้ definition จากเว็บไม่ได้ แต่ toggle อาจใช้ได้
      var editReason =
        "definition ของ tool นี้แก้ไขจากหน้าเว็บไม่ได้ — ต้องแก้ที่โค้ดแล้ว deploy แทน";
      editBtn.disabled = true;
      editBtn.title = editReason;
      card.appendChild(el("p", "hint-note", editReason));
      if (tool.toggleDisabledReason) {
        // ปุ่ม toggle มีเหตุผลแยกจากปุ่ม edit (เช่น knowledge ที่ห้ามปิด)
        toggleBtn.disabled = true;
        toggleBtn.title = tool.toggleDisabledReason;
        card.appendChild(el("p", "hint-note", tool.toggleDisabledReason));
      } else {
        toggleBtn.title = "เปิด/ปิด tool นี้ได้จากหน้าเว็บ (สถานะคงอยู่ข้าม restart)";
        toggleBtn.addEventListener("click", function () {
          toggleTool(tool.slug, !tool.enabled);
        });
      }
    }
    actions.appendChild(editBtn);
    actions.appendChild(toggleBtn);
    card.appendChild(actions);
    return card;
  }

  async function refreshTools() {
    var result = await api("/tools");
    if (!result.ok) {
      if (result.status !== 401) {
        views.toolsTable.replaceChildren(el("p", "error-note", errorText(result)));
      }
      return;
    }
    appEnv = (result.data && result.data.appEnv) || "development";
    views.envBadge.textContent =
      appEnv === "production" ? "production · นโยบายเครือข่ายเข้ม" : "development · เครือข่ายเปิด";
    views.envBadge.title =
      appEnv === "production"
        ? "ยิงได้เฉพาะ HTTPS + โดเมนใน allowlist — บล็อก private/metadata IP"
        : "ยิงได้ทุกปลายทาง รวม localhost (สำหรับซ้อมเดโม)";
    var tools = (result.data && result.data.tools) || [];
    if (tools.length === 0) {
      views.toolsTable.replaceChildren(el("p", "muted", "ยังไม่มี tool — กด “สร้าง tool ใหม่” เพื่อเริ่ม"));
      return;
    }
    views.toolsTable.replaceChildren.apply(
      views.toolsTable,
      tools.map(renderToolCard)
    );
  }

  async function toggleTool(slug, enabled) {
    var result = await api("/tools/" + encodeURIComponent(slug) + "/enabled", {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ enabled: enabled }),
    });
    if (!result.ok && result.status !== 401) {
      window.alert(errorText(result));
    }
    refreshTools();
  }

  // ----------------------------------------------- ฟอร์ม tool (D3.4) —

  // JSON Schema ที่ validator รับ — ค่า opaque ถูกแนบกับแถวและเก็บกลับตอน save
  function buildSchemaFromRows(fieldsContainer, baselineSchema) {

    var properties = {};
    var required = [];
    fieldsContainer.querySelectorAll(".field-row").forEach(function (row) {
      var name = $('[data-field="name"]', row).value.trim();
      if (!name) return;
      var baselineProperty = row.dataset.baselineProperty
        ? JSON.parse(row.dataset.baselineProperty)
        : {};
      var typeControl = $('[data-field="type"]', row);
       var isOpaqueObject = row.dataset.opaqueObject === "true";
       var selectedType = typeControl.value || baselineProperty.type || "string";
       var prop = isOpaqueObject
         ? JSON.parse(JSON.stringify(baselineProperty))
         : Object.assign({}, baselineProperty, {
        type: selectedType,
      });
      var description = $('[data-field="description"]', row).value.trim();
       if (isOpaqueObject) description = baselineProperty.description || "";
      if (description) prop.description = description;
      else delete prop.description;
       if (selectedType === "array") {
         var baselineItems = prop.items || {};
          prop.items = Object.assign({}, baselineItems, {
            type: $('[data-field="items-type"]', row).value || baselineItems.type || "string",
          });
       } else if (!isOpaqueObject) {
         delete prop.items;
       }
      var nullable = !isOpaqueObject && $('[data-field="nullable"]', row).checked;
      if (nullable) {
        var nullableType = Object.assign({}, (Array.isArray(baselineProperty.anyOf)
           ? baselineProperty.anyOf.find(function (item) { return item.type !== "null"; })
           : null) || {}, { type: prop.type });
         if (prop.type === "array") {
           var nullableBranch = Array.isArray(baselineProperty.anyOf)
             ? baselineProperty.anyOf.find(function (item) { return item.type !== "null"; })
             : null;
           nullableType.items = Object.assign({}, (nullableBranch && nullableBranch.items) || {}, prop.items || {});
         }
         prop.anyOf = [nullableType, { type: "null" }];
        delete prop.type;
      } else if (prop.anyOf) {
        if (!isOpaqueObject) delete prop.anyOf;
      }
      properties[name] = prop;
      if ($('[data-field="required"]', row).checked) required.push(name);
    });
    return Object.assign({}, baselineSchema || {}, {
      type: "object",
      properties: properties,
      required: required,
      additionalProperties: false,
    });
  }

  function addFieldRow(fieldsContainer, name, type, required, description, property) {
    var row = views.fieldRowTemplate.content.firstElementChild.cloneNode(true);
    var source = property || {};
    $('[data-field="name"]', row).value = name || "";
    var typeControl = $('[data-field="type"]', row);
    var effectiveType = type || source.type || "string";
    typeControl.value = effectiveType;
    row.dataset.opaqueObject = effectiveType === "object" ? "true" : "false";
    if (row.dataset.opaqueObject === "true") {
      typeControl.disabled = true;
      typeControl.title = "object เดิมเป็น opaque และแก้ไขใน form builder ไม่ได้";
      $('[data-field="nullable"]', row).disabled = true;
      $('[data-field="description"]', row).disabled = true;
    }
    $('[data-field="required"]', row).checked = !!required;
    var itemsType = $('[data-field="items-type"]', row);
    var sourceItems = source.items || (source.anyOf || []).find(function (item) {
      return item.type === "array";
    })?.items;
    itemsType.value = (sourceItems && sourceItems.type) || "string";
    $('[data-field-items-wrap]', row).hidden = effectiveType !== "array";
    $('[data-field="description"]', row).value = description || source.description || "";
    $('[data-field="nullable"]', row).checked = Array.isArray(source.anyOf)
      && source.anyOf.some(function (item) { return item.type === "null"; });
    row.dataset.baselineProperty = JSON.stringify(source);
    typeControl.addEventListener("change", function () {
      $('[data-field-items-wrap]', row).hidden = typeControl.value !== "array";
      updateSchemaPreview(fieldsContainer);
    });
    itemsType.addEventListener("change", function () {
      updateSchemaPreview(fieldsContainer);
    });
    row.addEventListener("input", function () {
      updateSchemaPreview(fieldsContainer);
    });
    $('[data-field-action="remove"]', row).addEventListener("click", function () {
      row.remove();
      updateSchemaPreview(fieldsContainer);
    });
    fieldsContainer.appendChild(row);
    updateSchemaPreview(fieldsContainer);
  }

  // JSON เป็น read-only preview — ไม่มีช่องแก้ JSON ตรง ๆ (D3.4 form builder)
  function updateSchemaPreview(fieldsContainer) {
    var card = fieldsContainer.closest(".operation-card");
    var preview = $('[data-op="schema-preview"]', card);
    preview.textContent = JSON.stringify(
      buildSchemaFromRows(fieldsContainer, JSON.parse(card.dataset.baselineSchema || "{}")),
      null,
      2,
    );
  }

  function populateFieldsFromSchema(fieldsContainer, schema) {
    fieldsContainer.replaceChildren();
    var properties = (schema && schema.properties) || {};
    var unsupported = Object.keys(properties).filter(function (name) {
      var property = properties[name] || {};
      return property.type === "object" || property.oneOf || property.$ref || property.properties
        || property.enum || property.default !== undefined;
    });
    var warning = $('[data-op="schema-warning"]', fieldsContainer.closest(".operation-card"));
    warning.textContent = unsupported.length
      ? "ฟิลด์ " + unsupported.join(", ")
        + " มี metadata ที่ฟอร์มแก้ไม่ได้ ระบบจะ preserve ไว้"
      : "";
    warning.hidden = unsupported.length === 0;
    var required = (schema && schema.required) || [];
    Object.keys(properties).forEach(function (name) {
      var prop = properties[name] || {};
      var type = prop.type || (prop.anyOf && prop.anyOf.find(function (item) {
        return item.type !== "null";
      }) || {}).type || "string";
      addFieldRow(fieldsContainer, name, type, required.indexOf(name) !== -1, prop.description || "", prop);
    });
    if (Object.keys(properties).length === 0) updateSchemaPreview(fieldsContainer);
  }

  function setOpTitle(card, index) {
    $(".op-title", card).textContent = "Operation " + (index + 1);
  }

  function addOperationCard(operation) {
    var card = views.operationTemplate.content.firstElementChild.cloneNode(true);
    var fieldsContainer = $('[data-op="fields"]', card);
    var baseline = operation || {};
    card.dataset.baselineOperation = JSON.stringify(baseline);
    card.dataset.baselineSchema = JSON.stringify(baseline.inputSchema || {});

    $('[data-op="action"]', card).value = (operation && operation.action) || "";
    $('[data-op="policy"]', card).value = (operation && operation.policy) || "plain_read";
    $('[data-op="exposure"]', card).value = (operation && operation.exposure) || "llm";
    $('[data-op="mode"]', card).value = (operation && operation.mode) || "read";
    $('[data-op="submitAction"]', card).value = (operation && operation.submitAction) || "";
    $('[data-op="httpMethod"]', card).value = (operation && operation.httpMethod) || "GET";
    $('[data-op="urlTemplate"]', card).value = (operation && operation.urlTemplate) || "";

    $('[data-op="action"]', card).addEventListener("input", function () {
      renumberOperations();
      views.operationsContainer.querySelectorAll(".operation-card").forEach(syncSubmitField);
    });
    $('[data-op="policy"]', card).addEventListener("change", function () {
      syncSubmitField(card);
    });
    $('[data-op="mode"]', card).addEventListener("change", function () {
      views.operationsContainer.querySelectorAll(".operation-card").forEach(syncSubmitField);
    });
    $('[data-op="exposure"]', card).addEventListener("change", function () {
      syncSubmitField(card);
    });

    $('[data-op-action="remove"]', card).addEventListener("click", function () {
      card.remove();
      renumberOperations();
    });

    $('[data-op-action="add-field"]', card).addEventListener("click", function () {
      addFieldRow(fieldsContainer, "", "string", false, "", {});
    });

    $('[data-op-action="try"]', card).addEventListener("click", function () {
      tryOperation(card);
    });

    populateFieldsFromSchema(fieldsContainer, operation && operation.inputSchema);
    syncSubmitField(card);
    views.operationsContainer.appendChild(card);
    return card;
  }

  // กติกา validator: prepare ต้องมี submitAction · submit ต้อง exposure=internal —
  // ซ่อน/แสดงและล็อกค่าให้ตรงตั้งแต่ในฟอร์ม เพื่อไม่ให้ save แล้วเจอ error ทีหลัง
  function syncSubmitField(card) {
    var mode = $('[data-op="mode"]', card).value;
    var exposure = $('[data-op="exposure"]', card);
    var submitField = $("[data-op-submit-field]", card);
    var submitInput = $('[data-op="submitAction"]', card);
    var httpMethod = $('[data-op="httpMethod"]', card);
    var urlTemplate = $('[data-op="urlTemplate"]', card);
    submitField.hidden = mode !== "prepare";
    httpMethod.disabled = mode === "prepare";
    urlTemplate.disabled = mode === "prepare";
    if (mode === "submit") {
      exposure.value = "internal";
      exposure.disabled = true;
    } else {
      exposure.disabled = false;
    }
    var submitActions = [];
    views.operationsContainer.querySelectorAll(".operation-card").forEach(function (other) {
      if ($('[data-op="mode"]', other).value === "submit") {
        var action = $('[data-op="action"]', other).value.trim();
        if (action) submitActions.push(action);
      }
    });
    var selected = submitInput.value;
    submitInput.replaceChildren(el("option", null, "— เลือก operation mode=submit —"));
    submitInput.firstElementChild.value = "";
    submitActions.forEach(function (action) {
      var option = el("option", null, action);
      option.value = action;
      submitInput.appendChild(option);
    });
    submitInput.value = submitActions.indexOf(selected) >= 0 ? selected : "";
    var tryButton = $('[data-op-action="try"]', card);
    tryButton.disabled = mode === "prepare";
    tryButton.title = mode === "prepare" ? "operation แบบ prepare ไม่มี HTTP request ให้ยิง" : "";
  }

  function renumberOperations() {
    var cards = views.operationsContainer.querySelectorAll(".operation-card");
    cards.forEach(setOpTitle);
  }

  function collectOperations() {
    var operations = [];
    views.operationsContainer.querySelectorAll(".operation-card").forEach(function (card) {
      operations.push(buildOperationPayload({
        action: $('[data-op="action"]', card).value,
        policy: $('[data-op="policy"]', card).value,
        exposure: $('[data-op="exposure"]', card).value,
        mode: $('[data-op="mode"]', card).value,
        httpMethod: $('[data-op="httpMethod"]', card).value,
        urlTemplate: $('[data-op="urlTemplate"]', card).value,
        submitAction: $('[data-op="submitAction"]', card).value,
        inputSchema: buildSchemaFromRows(
          $('[data-op="fields"]', card),
          JSON.parse(card.dataset.baselineSchema || "{}"),
        ),
      }, JSON.parse(card.dataset.baselineOperation || "{}")));
    });
    return operations;
  }

  function validateFormLocally(payload) {
    return validateToolPayload(payload);
  }

  function openNewToolForm() {
    editingSlug = null;
    editingBaseline = null;
    views.toolFormTitle.textContent = "สร้าง tool ใหม่";
    views.toolSlug.value = "";
    views.toolSlug.disabled = false;
    views.toolDisplayName.value = "";
    views.toolDescription.value = "";
    updateToolDescCount();
    views.toolAuthEnv.value = "";
     views.toolAuthEnv.disabled = false;
     // P1: ค่าเริ่มต้นรูปแบบ header เดิม — Authorization: Bearer
     views.toolAuthHeader.value = "Authorization";
     views.toolAuthScheme.value = "Bearer";
     views.toolAuthStatus.hidden = true;
     views.toolRemoveAuthWrap.hidden = true;
     views.toolRemoveAuth.checked = false;
    views.toolEnabled.checked = true;
    views.operationsContainer.replaceChildren();
    addOperationCard({
      action: "",
      policy: "plain_read",
      exposure: "llm",
      mode: "read",
      httpMethod: "GET",
      urlTemplate: "",
      inputSchema: { type: "object", properties: {}, required: [], additionalProperties: false },
    });
    showHidden(views.toolFormError, true);
    views.toolsList.hidden = true;
    views.toolForm.hidden = false;
    views.toolSlug.focus();
  }

  async function openToolForm(slug) {
    var result = await api("/tools/" + encodeURIComponent(slug));
    if (!result.ok) {
      if (result.status !== 401) window.alert(errorText(result));
      return;
    }
    var tool = result.data;
    editingBaseline = JSON.parse(JSON.stringify(tool));
    editingSlug = slug;
    views.toolFormTitle.textContent = "แก้ไข tool: " + (tool.displayName || slug);
    views.toolSlug.value = tool.slug;
    views.toolSlug.disabled = true; // slug คือคีย์ — แก้ slug = tool ใหม่
    views.toolDisplayName.value = tool.displayName || "";
    views.toolDescription.value = tool.description || "";
    updateToolDescCount();
    views.toolAuthEnv.value = "";
     views.toolAuthEnv.disabled = false;
     // P1: header/scheme ไม่ใช่ความลับ — API คืนค่าปัจจุบันมาแสดงได้ (secret_ref ยังเขียนได้อย่างเดียว)
     views.toolAuthHeader.value = tool.hasAuth ? (tool.authHeaderName || "Authorization") : "Authorization";
     views.toolAuthScheme.value = tool.hasAuth && tool.authScheme !== null && tool.authScheme !== undefined ? tool.authScheme : "Bearer";
     views.toolAuthStatus.hidden = !tool.hasAuth;
     views.toolRemoveAuthWrap.hidden = !tool.hasAuth;
     views.toolRemoveAuth.checked = false; // secret_ref เขียนได้อย่างเดียว — API ไม่คืนค่าเดิม
    views.toolEnabled.checked = !!tool.enabled;
    views.operationsContainer.replaceChildren();
    (tool.operations || []).forEach(addOperationCard);
    renumberOperations();
    showHidden(views.toolFormError, true);
    views.toolsList.hidden = true;
    views.toolForm.hidden = false;
  }

  function updateToolDescCount() {
    views.toolDescCount.textContent = views.toolDescription.value.length + " ตัวอักษร";
  }

  views.toolDescription.addEventListener("input", updateToolDescCount);
   views.toolRemoveAuth.addEventListener("change", function () {
     views.toolAuthEnv.disabled = views.toolRemoveAuth.checked;
     if (views.toolRemoveAuth.checked) views.toolAuthEnv.value = "";
   });
  views.newToolBtn.addEventListener("click", openNewToolForm);
  views.addOperationBtn.addEventListener("click", function () {
    addOperationCard(null);
    renumberOperations();
    views.operationsContainer.querySelectorAll(".operation-card").forEach(syncSubmitField);
  });

  function backToList() {
    views.toolForm.hidden = true;
    views.toolsList.hidden = false;
    editingSlug = null;
    editingBaseline = null;
    refreshTools();
  }

  views.backToListBtn.addEventListener("click", backToList);
  $("#cancel-tool-btn").addEventListener("click", backToList);

  views.toolFormElement.addEventListener("submit", async function (event) {
    event.preventDefault();
    showHidden(views.toolFormError, true);

    var authEnv = views.toolAuthEnv.value.trim();
    var authHeader = views.toolAuthHeader.value.trim() || "Authorization";
    var authScheme = views.toolAuthScheme.value.trim();
    var payload = buildToolPayload({
      slug: views.toolSlug.value,
      displayName: views.toolDisplayName.value,
      description: views.toolDescription.value,
      enabled: views.toolEnabled.checked,
      operations: collectOperations(),
    }, editingBaseline);
    if (views.toolRemoveAuth.checked) {
      payload.authEnvVar = null; // ลบ credential ทั้งแถว รวม header/scheme
    } else if (authEnv) {
      // ใส่ชื่อ env var ใหม่ = replace ทั้งหมดพร้อมรูปแบบ header
      payload.authEnvVar = authEnv;
      payload.authHeaderName = authHeader;
      payload.authScheme = authScheme;
    } else if (editingBaseline && editingBaseline.hasAuth) {
      // ไม่พิมพ์ชื่อ env var ซ้ำ — แก้เฉพาะรูปแบบ header โดยคง secret_ref เดิม (P1)
      payload.authHeaderName = authHeader;
      payload.authScheme = authScheme;
    }

    var metadataLoss = editingBaseline
      ? detectMetadataLoss(editingBaseline, payload)
      : [];
    if (metadataLoss.length) {
      views.toolFormError.textContent =
        "บันทึกไม่ได้ เพราะ metadata ของ " + metadataLoss.join(", ") + " จะหายไป";
      showHidden(views.toolFormError, false);
      return;
    }

    var localError = validateFormLocally(payload);
    if (localError) {
      views.toolFormError.textContent = localError;
      showHidden(views.toolFormError, false);
      return;
    }

    var path = editingSlug
      ? "/tools/" + encodeURIComponent(editingSlug)
      : "/tools";
    var result = await api(path, {
      method: editingSlug ? "PUT" : "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (result.ok) {
      backToList();
    } else if (result.status !== 401) {
      // error บอกชัดว่าผิดตรงไหน (D3.4) — ข้อความไทยจาก validator จุดเดียวกับ loader
      views.toolFormError.textContent = errorText(result);
      showHidden(views.toolFormError, false);
    }
  });

  // ------------------------------------------------ ปุ่ม "ลองยิงดู" (D3.5) --

  // สร้างช่องกรอกค่า input ต่อฟิลด์จาก schema — ค่าส่งผ่าน /admin/tools/try เสมอ
  // (ผู้ใช้กด "ลองยิงดู" ซ้ำ: tryOperation จะคงค่าที่พิมพ์ไว้ให้เอง)
  function renderTryInputs(tryPanel, schema) {
    var container = $(".try-inputs", tryPanel);
    if (container) container.remove();
    container = el("div", "try-inputs");
    var properties = (schema && schema.properties) || {};
    Object.keys(properties).forEach(function (name) {
      var prop = properties[name] || {};
      var field = el("label", "field");
      field.appendChild(el("span", null, name + " (" + (prop.type || "string") + ")"));
      var input = el("input");
      input.type = prop.type === "integer" || prop.type === "number" ? "number" : "text";
      input.dataset.tryField = name;
      input.dataset.tryType = prop.type || "string";
      input.placeholder = prop.description || "";
      field.appendChild(input);
      container.appendChild(field);
    });
    var fireBtn = $(".try-fire-btn", tryPanel);
    tryPanel.insertBefore(container, fireBtn);
  }

  function collectTryInput(tryPanel) {
    var input = {};
    var error = null;
    var fields = tryPanel.querySelectorAll("input[data-try-field]");
    if (fields.length === 0) return { input: input, error: null };
    fields.forEach(function (field) {
      if (error) return;
      var raw = field.value.trim();
      var type = field.dataset.tryType;
      if (raw === "") return; // ไม่กรอก = ไม่ส่งฟิลด์นี้
      if (type === "integer" || type === "number") {
        var num = Number(raw);
        if (Number.isNaN(num)) {
          error = "ฟิลด์ " + field.dataset.tryField + " ต้องเป็นตัวเลข";
          return;
        }
        input[field.dataset.tryField] = num;
      } else if (type === "boolean") {
        input[field.dataset.tryField] = raw === "true" || raw === "1";
      } else if (type === "array" || type === "object") {
        try {
          input[field.dataset.tryField] = JSON.parse(raw);
        } catch (_error) {
          error = "ฟิลด์ " + field.dataset.tryField + " ต้องเป็น JSON ที่ถูกต้อง";
        }
      } else {
        input[field.dataset.tryField] = raw;
      }
    });
    return { input: input, error: error };
  }

  async function tryOperation(card) {
    if ($('[data-op="mode"]', card).value === "prepare") return;
    var tryPanel = $("[data-op=\"try-result\"]", card);
    var schema = buildSchemaFromRows($('[data-op="fields"]', card));
    var existed = !tryPanel.hidden;
    var oldValues = {};
    if (existed) {
      tryPanel.querySelectorAll("input[data-try-field]").forEach(function (field) {
        oldValues[field.dataset.tryField] = field.value;
      });
    }
    tryPanel.replaceChildren(
      el(
        "p",
        "muted",
        "ยิงจริงผ่าน executor กลาง — ผ่านนโยบายเครือข่ายครบทุกขั้น (กรอกค่า input แล้วกด “ยิงจริง”)"
      )
    );
    tryPanel.hidden = false;
    renderTryInputs(tryPanel, schema);
    tryPanel.querySelectorAll("input[data-try-field]").forEach(function (field) {
      if (oldValues[field.dataset.tryField] !== undefined) {
        field.value = oldValues[field.dataset.tryField];
      }
    });

    var fire = async function () {
      clearTryStatus(tryPanel);
      var collected = collectTryInput(tryPanel);
      if (collected.error) {
        renderTryError(tryPanel, "invalid_input", collected.error);
        return;
      }
      var authEnv = views.toolAuthEnv.value.trim();
      var authHeader = views.toolAuthHeader.value.trim() || "Authorization";
      var authScheme = views.toolAuthScheme.value.trim();
      var removeAuth = views.toolRemoveAuth.checked;
      var currentSchema = buildSchemaFromRows(
        $('[data-op="fields"]', card),
        JSON.parse(card.dataset.baselineSchema || "{}")
      );
      var payload = buildTryPayload({
        httpMethod: $('[data-op="httpMethod"]', card).value,
        urlTemplate: $('[data-op="urlTemplate"]', card).value.trim(),
        input: collected.input,
        inputSchema: currentSchema,
        toolSlug: editingSlug,
        authEnv: authEnv,
        authHeader: authHeader,
        authScheme: authScheme,
        removeAuth: removeAuth,
        hasSavedAuth: !!(editingBaseline && editingBaseline.hasAuth),
      });
      var result = await api("/tools/try", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (result.status === 401) return;
      if (!result.ok) {
        renderTryError(tryPanel, "request_failed", errorText(result));
        return;
      }
      renderTryOutcome(tryPanel, result.data);
    };

    var fireBtn = el("button", "btn btn-primary btn-sm try-fire-btn", "ยิงจริง");
    fireBtn.type = "button";
    fireBtn.addEventListener("click", function (event) {
      event.preventDefault();
      fire();
    });
    tryPanel.appendChild(fireBtn);
  }

  function clearTryStatus(tryPanel) {
    tryPanel
      .querySelectorAll(
        ".try-status-ok, .try-status-warn, .try-status-blocked, .try-status-note, .try-output"
      )
      .forEach(function (node) {
        node.remove();
      });
  }

  function renderTryError(tryPanel, reason, message) {
    clearTryStatus(tryPanel);
    tryPanel.appendChild(
      el("p", "try-status-blocked", "ถูกปฏิเสธ (" + reason + "): " + message)
    );
  }

  function renderTryOutcome(tryPanel, data) {
    clearTryStatus(tryPanel);
    // แยกผล HTTP สำเร็จ/ไม่สำเร็จ/ระบบบล็อกก่อนยิง/เชื่อมต่อไม่ได้ให้ชัดเจน (A2) —
    // ok:true ของ backend หมายถึง "ได้ HTTP response แล้ว" เท่านั้น ไม่ใช่ 2xx เสมอไป
    var outcome = describeTryOutcome(data);
    tryPanel.appendChild(el("p", outcome.cssClass, outcome.label));
    if (outcome.note) {
      tryPanel.appendChild(el("p", "try-status-note", outcome.note));
    }
    if (outcome.kind !== "success" && outcome.kind !== "http_error") {
      // ok:false ไม่มี request/response จริงให้แสดงต่อ (CONTRACTS.md §POST /tools/try)
      return;
    }
    var response = data.response || {};
    // แสดงผลครบตามสเปก D3.5: method + final URL + query + request body + response
    // (headers ไม่ส่งกลับมาจาก API เลย — fail-safe กัน credential หลุดขึ้นจอ)
    var request = data.request || {};
    var query = request.query || {};
    var queryText = Object.keys(query).length
      ? "?" + Object.keys(query).map(function (key) { return key + "=" + query[key]; }).join("&")
      : "";
    var sections = [request.method + " " + request.url + queryText];
    if (request.body !== null && request.body !== undefined) {
      sections.push("\n[request body]\n" + JSON.stringify(request.body, null, 2));
    }
    sections.push("\n[response]");
    if (response.isJson) {
      sections.push(JSON.stringify(response.body, null, 2));
    } else {
      // response ไม่ใช่ JSON: แสดงเป็นข้อความ (backend ตัดความยาวแล้วแจ้งผ่าน textTruncated)
      sections.push(response.text || "(response ว่าง)");
      if (response.textTruncated) {
        sections.push("… (ข้อความถูกตัดให้สั้นลง — แสดงเฉพาะช่วงต้น)");
      }
    }
    var output = el("pre", "json-preview try-output");
    output.textContent = sections.join("\n");
    tryPanel.appendChild(output);
  }

  // ---------------------------------------------------- หน้าแก้ prompt (D3.6) --

  function updatePromptCount() {
    views.promptCharCount.textContent = views.promptContent.value.length + " ตัวอักษร";
    views.promptPreview.textContent = views.promptContent.value;
  }

  views.promptContent.addEventListener("input", updatePromptCount);

  async function refreshPrompt() {
    showHidden(views.promptError, true);
    showHidden(views.promptSuccess, true);
    var result = await api("/prompt");
    if (!result.ok) {
      if (result.status !== 401) {
        views.promptError.textContent = errorText(result);
        showHidden(views.promptError, false);
      }
      return;
    }
    views.promptContent.value = result.data.content || "";
    views.promptUpdatedAt.textContent = result.data.updatedAt
      ? "แก้ไขล่าสุด: " + result.data.updatedAt
      : "ยังไม่เคยแก้ — ใช้ค่าเริ่มต้นจากโค้ด";
    views.promptStatusBadge.textContent = result.data.isModified
      ? "แก้ไขแล้ว (ต่างจากค่าเริ่มต้น)"
      : "ค่าเริ่มต้น";
    views.promptStatusBadge.className = "status-badge " + (result.data.isModified ? "badge-db" : "");
    updatePromptCount();
  }

  views.savePromptBtn.addEventListener("click", async function () {
    showHidden(views.promptError, true);
    showHidden(views.promptSuccess, true);
    if (!views.promptContent.value.trim()) {
      // ค่าว่างทำให้ runtime fallback เงียบ ๆ — จับที่ปุ่ม save แทน (D3.6)
      views.promptError.textContent =
        "เนื้อหา prompt ต้องไม่ว่าง — ถ้าบันทึกค่าว่างระบบจะกลับไปใช้ค่าเริ่มต้นเงียบ ๆ";
      showHidden(views.promptError, false);
      return;
    }
    views.savePromptBtn.disabled = true;
    var result = await api("/prompt", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ content: views.promptContent.value }),
    });
    views.savePromptBtn.disabled = false;
    if (result.ok) {
      views.promptSuccess.textContent = "บันทึกแล้ว — มีผลตั้งแต่เทิร์นถัดไป ไม่ต้อง restart";
      showHidden(views.promptSuccess, false);
      views.promptUpdatedAt.textContent = result.data.updatedAt
        ? "แก้ไขล่าสุด: " + result.data.updatedAt
        : "";
      views.promptStatusBadge.textContent = "แก้ไขแล้ว (ต่างจากค่าเริ่มต้น)";
      views.promptStatusBadge.className = "status-badge badge-db";
    } else if (result.status !== 401) {
      views.promptError.textContent = errorText(result);
      showHidden(views.promptError, false);
    }
  });

  // ---------------------------------------------------------------- เริ่มระบบ --

  async function init() {
    updateToolDescCount();
    var result = await api("/session");
    if (result.ok) {
      showApp();
    } else {
      showLogin();
    }
  }

  init();
})();
