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
      // ปลั๊กอิน Python: ช่องที่แก้ไม่ได้ถูก disable พร้อมบอกเหตุผล (D3.3)
      var reason = "tool จากโค้ด (Python plugin) — ต้องแก้ที่ plugin.yaml แล้ว deploy";
      editBtn.disabled = true;
      toggleBtn.disabled = true;
      editBtn.title = reason;
      toggleBtn.title = reason;
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

  // JSON Schema ที่ validator รับ (D1.2 subset) — สร้างจากแถวฟิลด์เสมอ
  function buildSchemaFromRows(fieldsContainer) {
    var properties = {};
    var required = [];
    fieldsContainer.querySelectorAll(".field-row").forEach(function (row) {
      var name = $('[data-field="name"]', row).value.trim();
      if (!name) return; // แถวที่ยังไม่ตั้งชื่อ = ไม่อยู่ใน schema
      var prop = { type: $('[data-field="type"]', row).value };
      var description = $('[data-field="description"]', row).value.trim();
      if (description) prop.description = description;
      properties[name] = prop;
      if ($('[data-field="required"]', row).checked) required.push(name);
    });
    return { type: "object", properties: properties, required: required, additionalProperties: false };
  }

  function addFieldRow(fieldsContainer, name, type, required, description) {
    var row = views.fieldRowTemplate.content.firstElementChild.cloneNode(true);
    $('[data-field="name"]', row).value = name || "";
    $('[data-field="type"]', row).value = type || "string";
    $('[data-field="required"]', row).checked = !!required;
    $('[data-field="description"]', row).value = description || "";
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
    preview.textContent = JSON.stringify(buildSchemaFromRows(fieldsContainer), null, 2);
  }

  function populateFieldsFromSchema(fieldsContainer, schema) {
    fieldsContainer.replaceChildren();
    var properties = (schema && schema.properties) || {};
    var required = (schema && schema.required) || [];
    Object.keys(properties).forEach(function (name) {
      var prop = properties[name] || {};
      addFieldRow(fieldsContainer, name, prop.type || "string", required.indexOf(name) !== -1, prop.description || "");
    });
    if (Object.keys(properties).length === 0) {
      updateSchemaPreview(fieldsContainer);
    }
  }

  function setOpTitle(card, index) {
    $(".op-title", card).textContent = "Operation " + (index + 1);
  }

  function addOperationCard(operation) {
    var card = views.operationTemplate.content.firstElementChild.cloneNode(true);
    var fieldsContainer = $('[data-op="fields"]', card);

    $('[data-op="action"]', card).value = (operation && operation.action) || "";
    $('[data-op="policy"]', card).value = (operation && operation.policy) || "plain_read";
    $('[data-op="exposure"]', card).value = (operation && operation.exposure) || "llm";
    $('[data-op="mode"]', card).value = (operation && operation.mode) || "read";
    $('[data-op="httpMethod"]', card).value = (operation && operation.httpMethod) || "GET";
    $('[data-op="urlTemplate"]', card).value = (operation && operation.urlTemplate) || "";

    $('[data-op="action"]', card).addEventListener("input", function () {
      renumberOperations();
    });
    $('[data-op="policy"]', card).addEventListener("change", function () {
      syncSubmitField(card);
    });
    $('[data-op="mode"]', card).addEventListener("change", function () {
      syncSubmitField(card);
    });
    $('[data-op="exposure"]', card).addEventListener("change", function () {
      syncSubmitField(card);
    });

    $('[data-op-action="remove"]', card).addEventListener("click", function () {
      card.remove();
      renumberOperations();
    });

    $('[data-op-action="add-field"]', card).addEventListener("click", function () {
      addFieldRow(fieldsContainer, "", "string", false, "");
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
    if (mode === "prepare") {
      submitField.hidden = false;
    } else {
      submitField.hidden = true;
      submitInput.value = "";
    }
    if (mode === "submit") {
      exposure.value = "internal";
      exposure.disabled = true;
    } else {
      exposure.disabled = false;
    }
  }

  function renumberOperations() {
    var cards = views.operationsContainer.querySelectorAll(".operation-card");
    cards.forEach(setOpTitle);
  }

  function collectOperations() {
    var operations = [];
    views.operationsContainer.querySelectorAll(".operation-card").forEach(function (card) {
      var op = {
        action: $('[data-op="action"]', card).value.trim(),
        policy: $('[data-op="policy"]', card).value,
        exposure: $('[data-op="exposure"]', card).value,
        mode: $('[data-op="mode"]', card).value,
        httpMethod: $('[data-op="httpMethod"]', card).value,
        urlTemplate: $('[data-op="urlTemplate"]', card).value.trim(),
        inputSchema: buildSchemaFromRows($('[data-op="fields"]', card)),
      };
      var submitAction = $('[data-op="submitAction"]', card).value.trim();
      if (submitAction) op.submitAction = submitAction;
      operations.push(op);
    });
    return operations;
  }

  function validateFormLocally(payload) {
    if (!/^[a-z0-9_-]+$/.test(payload.slug)) {
      return "ชื่อระบบ (slug) ต้องเป็น a-z 0-9 _ - เท่านั้น";
    }
    if (!payload.displayName) return "กรุณากรอกชื่อที่แสดง";
    for (var i = 0; i < payload.operations.length; i += 1) {
      var op = payload.operations[i];
      if (!op.action) return "Operation ที่ " + (i + 1) + ": กรุณากรอกชื่อ action";
      if (!op.urlTemplate) return "Operation ที่ " + (i + 1) + " (" + op.action + "): กรุณากรอก URL template";
    }
    return null;
  }

  function openNewToolForm() {
    editingSlug = null;
    views.toolFormTitle.textContent = "สร้าง tool ใหม่";
    views.toolSlug.value = "";
    views.toolSlug.disabled = false;
    views.toolDisplayName.value = "";
    views.toolDescription.value = "";
    updateToolDescCount();
    views.toolAuthEnv.value = "";
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
    editingSlug = slug;
    views.toolFormTitle.textContent = "แก้ไข tool: " + (tool.displayName || slug);
    views.toolSlug.value = tool.slug;
    views.toolSlug.disabled = true; // slug คือคีย์ — แก้ slug = tool ใหม่
    views.toolDisplayName.value = tool.displayName || "";
    views.toolDescription.value = tool.description || "";
    updateToolDescCount();
    views.toolAuthEnv.value = ""; // secret_ref เขียนได้อย่างเดียว — API ไม่คืนค่าเดิม
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
  views.newToolBtn.addEventListener("click", openNewToolForm);
  views.addOperationBtn.addEventListener("click", function () {
    addOperationCard(null);
    renumberOperations();
  });

  function backToList() {
    views.toolForm.hidden = true;
    views.toolsList.hidden = false;
    editingSlug = null;
    refreshTools();
  }

  views.backToListBtn.addEventListener("click", backToList);
  $("#cancel-tool-btn").addEventListener("click", backToList);

  views.toolFormElement.addEventListener("submit", async function (event) {
    event.preventDefault();
    showHidden(views.toolFormError, true);

    var authEnv = views.toolAuthEnv.value.trim();
    var payload = {
      slug: views.toolSlug.value.trim(),
      displayName: views.toolDisplayName.value.trim(),
      description: views.toolDescription.value,
      enabled: views.toolEnabled.checked,
      operations: collectOperations(),
    };
    if (authEnv) payload.authEnvVar = authEnv;

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

    // ส่วนกรอกค่า + ปุ่มยิง — สร้างครั้งเดียวต่อการกด
    var authEnv = views.toolAuthEnv.value.trim();
    var fire = async function () {
      clearTryStatus(tryPanel);
      var collected = collectTryInput(tryPanel);
      if (collected.error) {
        renderTryError(tryPanel, "invalid_input", collected.error);
        return;
      }
      var result = await api("/tools/try", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          httpMethod: $('[data-op="httpMethod"]', card).value,
          urlTemplate: $('[data-op="urlTemplate"]', card).value.trim(),
          input: collected.input,
          inputSchema: schema,
          authEnvVar: authEnv || null,
        }),
      });
      if (result.status === 401) return;
      if (!result.ok) {
        renderTryError(tryPanel, "request_failed", errorText(result));
        return;
      }
      renderTryOutcome(tryPanel, result.data);
    };

    var fireBtn = el("button", "btn btn-primary btn-sm try-fire-btn", "ยิงจริง");
    fireBtn.addEventListener("click", fire);
    tryPanel.appendChild(fireBtn);
  }

  function clearTryStatus(tryPanel) {
    tryPanel
      .querySelectorAll(".try-status-ok, .try-status-blocked, .try-output")
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
    if (!data.ok) {
      // ถูกนโยบายบล็อก เช่น 169.254.169.254 — แสดงเหตุผลตรงจุด (D3.5)
      tryPanel.appendChild(
        el("p", "try-status-blocked", "ถูกปฏิเสธ (" + data.reason + "): " + data.error)
      );
      return;
    }
    var response = data.response || {};
    tryPanel.appendChild(
      el(
        "p",
        "try-status-ok",
        "สำเร็จ · HTTP " + response.statusCode + " · " + response.elapsedMs + " ms"
      )
    );
    var request = data.request || {};
    var query = request.query || {};
    var queryText = Object.keys(query).length
      ? "?" + Object.keys(query).map(function (key) { return key + "=" + query[key]; }).join("&")
      : "";
    var output = el("pre", "json-preview try-output");
    output.textContent =
      request.method + " " + request.url + queryText + "\n\n" +
      (response.isJson ? JSON.stringify(response.body, null, 2) : "(response ไม่ใช่ JSON)");
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
