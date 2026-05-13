(function () {
  if (window.__ASHARE_POSTCLOSE_ENHANCEMENTS_LOADED__) {
    return;
  }
  window.__ASHARE_POSTCLOSE_ENHANCEMENTS_LOADED__ = true;

  const API_BASE = window.ASHARE_API_BASE || "";
  let reviewSession = "postclose";
  let qaLoading = false;
  let operationsLoading = false;
  let operationsDrafts = [];
  let operationsDraftLoaded = false;

  function qs(selector, root = document) {
    return root.querySelector(selector);
  }

  function setText(node, value) {
    if (node) {
      node.textContent = value;
    }
  }

  function renderList(node, items, fallback) {
    if (!node) {
      return;
    }
    const clean = Array.isArray(items)
      ? items.map((item) => String(item || "").trim()).filter(Boolean)
      : [];
    node.innerHTML = clean.length
      ? clean.map((item) => `<li>${item}</li>`).join("")
      : `<li>${fallback}</li>`;
  }

  function showToast(message) {
    const toast = qs(".toast");
    if (!toast) {
      return;
    }
    toast.textContent = message;
    toast.classList.add("show");
    window.setTimeout(() => toast.classList.remove("show"), 2200);
  }

  function renderNextExpectation(payload) {
    const block = payload.next_day_expectation || {};
    const sessionMeta = payload.session_meta || {};
    setText(qs("[data-nextday-label]"), block.label || sessionMeta.action_label || "次日预期");
    setText(qs("[data-nextday-headline]"), block.headline || "等待生成结构化预期");
    setText(qs("[data-nextday-session-tag]"), sessionMeta.label || "结构化输出");
    renderList(qs("[data-nextday-watchpoints]"), block.watchpoints, "等待生成观察重点");
    renderList(qs("[data-nextday-risks]"), block.risk_triggers, "等待生成风险触发");
    renderList(qs("[data-nextday-order]"), block.execution_order, "等待生成执行顺序");
  }

  function renderHoldingsNextActions(payload) {
    const block = payload.next_day_actions || {};
    if (!block) {
      return;
    }
    const title = qs("[data-holdings-plan-title]");
    const text = qs("[data-holdings-plan-text]");
    if (title && block.label) {
      title.textContent = block.label;
    }
    if (text && block.headline) {
      text.textContent = block.headline;
    }
  }

  function defaultOperationDraft() {
    return {
      id: `operation-${Date.now()}-${Math.random().toString(16).slice(2, 8)}`,
      symbol: "",
      side: "买入",
      price: "",
      position_change: "",
      operate_time: "",
      reason: "",
    };
  }

  function ensureOperationDrafts() {
    if (!operationsDrafts.length) {
      operationsDrafts = [defaultOperationDraft()];
    }
  }

  async function ensureSavedOperationsLoaded() {
    if (operationsDraftLoaded) {
      return;
    }
    operationsDraftLoaded = true;
    try {
      const response = await fetch(`${API_BASE}/api/postclose/operations-draft`);
      const payload = await response.json();
      if (response.ok && Array.isArray(payload.operations) && payload.operations.length) {
        operationsDrafts = payload.operations.map((item) => ({
          id: `operation-${Date.now()}-${Math.random().toString(16).slice(2, 8)}`,
          symbol: String(item.symbol || "").trim(),
          side: String(item.side || "买入").trim() || "买入",
          price: item.price ?? "",
          position_change: String(item.position_change || "").trim(),
          operate_time: String(item.operate_time || "").trim(),
          reason: String(item.reason || "").trim(),
        }));
      }
    } catch (error) {
      console.error(error);
    }
    ensureOperationDrafts();
  }

  function renderOperationDrafts() {
    const listNode = qs("[data-operations-list]");
    if (!listNode) {
      return;
    }
    ensureOperationDrafts();
    listNode.innerHTML = operationsDrafts
      .map(
        (draft, index) => `
          <article class="postclose-holding-editor-card" data-operation-row="${draft.id}">
            <div class="postclose-holding-editor-head">
              <div>
                <strong>操作 ${index + 1}</strong>
                <span>${draft.side}</span>
              </div>
              <button class="ghost-button" type="button" data-postclose-operation-remove="${draft.id}" ${operationsDrafts.length === 1 ? "disabled" : ""}>删除</button>
            </div>
            <div class="postclose-form-row">
              <label><span>代码 / 名称</span><input type="text" value="${draft.symbol}" data-operation-field="symbol" data-operation-id="${draft.id}" placeholder="如：002432 或 九安医疗" /></label>
              <label><span>买入 / 卖出</span><select data-operation-field="side" data-operation-id="${draft.id}"><option value="买入" ${draft.side === "买入" ? "selected" : ""}>买入</option><option value="卖出" ${draft.side === "卖出" ? "selected" : ""}>卖出</option></select></label>
            </div>
            <div class="postclose-form-row">
              <label><span>成交价</span><input type="text" value="${draft.price}" data-operation-field="price" data-operation-id="${draft.id}" placeholder="如：18.36" /></label>
              <label><span>操作时间</span><input type="text" value="${draft.operate_time}" data-operation-field="operate_time" data-operation-id="${draft.id}" placeholder="如：10:32" /></label>
            </div>
            <div class="postclose-form-row">
              <label><span>仓位变化</span><input type="text" value="${draft.position_change}" data-operation-field="position_change" data-operation-id="${draft.id}" placeholder="如：加仓 10%" /></label>
              <label><span>操作理由</span><input type="text" value="${draft.reason}" data-operation-field="reason" data-operation-id="${draft.id}" placeholder="记录这笔动作的触发理由" /></label>
            </div>
          </article>
        `
      )
      .join("");
  }

  function updateOperationField(id, field, value) {
    operationsDrafts = operationsDrafts.map((item) =>
      item.id === id ? { ...item, [field]: value } : item
    );
  }

  function addOperationDraft() {
    operationsDrafts = [...operationsDrafts, defaultOperationDraft()];
    renderOperationDrafts();
  }

  function clearOperationDrafts() {
    operationsDrafts = [defaultOperationDraft()];
    renderOperationDrafts();
  }

  function removeOperationDraft(id) {
    if (operationsDrafts.length <= 1) {
      return;
    }
    operationsDrafts = operationsDrafts.filter((item) => item.id !== id);
    renderOperationDrafts();
  }

  function renderOperationsReview(payload) {
    const panels = Array.from(document.querySelectorAll("#postclose-review .panel"));
    const panel = panels.find((node) => node.querySelector(".panel-head h3")?.textContent.includes("操作复盘结果"));
    if (!panel) {
      return;
    }
    const empty = panel.querySelector(".postclose-empty-state");
    if (empty) {
      empty.classList.add("is-hidden");
    }
    let resultNode = panel.querySelector("[data-operations-review-result]");
    if (!resultNode) {
      resultNode = document.createElement("div");
      resultNode.className = "postclose-holdings-result";
      resultNode.dataset.operationsReviewResult = "true";
      panel.appendChild(resultNode);
    }
    const review = payload.review || {};
    const items = Array.isArray(review.operations) ? review.operations : [];
    resultNode.innerHTML = `
      <div class="postclose-llm-hint">
        <span>操作复盘状态</span>
        <strong>${payload.llm_status?.message || "--"}</strong>
      </div>
      <div class="postclose-holdings-summary-grid">
        <article class="postclose-holding-summary-card">
          <span>整体总评</span>
          <strong>操作与环境匹配度</strong>
          <p>${review.summary || "--"}</p>
        </article>
        <article class="postclose-holding-summary-card">
          <span>风险提示</span>
          <strong>最需要回看的问题</strong>
          <p>${review.risk_flags || "--"}</p>
        </article>
        <article class="postclose-holding-summary-card">
          <span>次日复核</span>
          <strong>下一步执行重点</strong>
          <p>${review.plan || "--"}</p>
        </article>
      </div>
      <div class="postclose-holding-cards">
        ${items
          .map(
            (item) => `
              <article class="postclose-holding-card">
                <div class="postclose-holding-head">
                  <div>
                    <strong>${item.name || item.symbol || "--"}</strong>
                    <span>${item.symbol || "--"} / ${item.verdict || "--"}</span>
                  </div>
                  <div class="holding-meta-pack">
                    <span>${item.industry || "--"}</span>
                  </div>
                </div>
                <div class="postclose-holding-body">
                  <div>
                    <span>复盘评价</span>
                    <p>${item.review || "--"}</p>
                  </div>
                  <div>
                    <span>理由检查</span>
                    <p>${item.reason_check || "--"}</p>
                  </div>
                  <div>
                    <span>次日复核</span>
                    <p>${item.next_step || "--"}</p>
                  </div>
                </div>
              </article>
            `
          )
          .join("")}
      </div>
    `;
  }

  function renderQA(payload) {
    const shell = qs("[data-postclose-qa-result]");
    if (!shell) {
      return;
    }
    shell.classList.remove("is-hidden");
    setText(
      qs("[data-postclose-qa-status]"),
      payload.llm_status?.used
        ? `当前使用 ${payload.llm_status.provider || "LLM"} / ${payload.llm_status.model || "--"} 生成问答解释`
        : "当前使用复盘上下文保守回答"
    );
    setText(qs("[data-postclose-qa-answer]"), payload.answer || "--");
    renderList(qs("[data-postclose-qa-evidence]"), payload.evidence, "待补充证据");
    renderList(qs("[data-postclose-qa-followups]"), payload.followups, "待补充追问方向");
  }

  async function refreshHoldingsSummary(session) {
    const reviewNode = qs("[data-holdings-review-result]");
    if (!reviewNode || reviewNode.classList.contains("is-hidden")) {
      return;
    }
    try {
      const draftResponse = await fetch(`${API_BASE}/api/postclose/holdings-draft`);
      const draftPayload = await draftResponse.json();
      const holdings = draftPayload.holdings || [];
      if (!Array.isArray(holdings) || !holdings.length) {
        return;
      }
      const params = new URLSearchParams();
      params.set("session", session);
      const response = await fetch(`${API_BASE}/api/postclose/holdings-review?${params.toString()}`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ holdings }),
      });
      const payload = await response.json();
      if (!response.ok) {
        return;
      }
      renderHoldingsNextActions(payload);
    } catch (error) {
      console.error(error);
    }
  }

  async function fetchReview(session, forceRefresh) {
    const button = session === "midday" ? qs("[data-postclose-midday]") : qs("[data-postclose-generate]");
    const altButton = session === "midday" ? qs("[data-postclose-generate]") : qs("[data-postclose-midday]");
    const originalText = button ? button.textContent : "";
    if (button) {
      button.disabled = true;
      button.textContent = "生成中..";
    }
    if (altButton) {
      altButton.disabled = true;
    }

    try {
      const params = new URLSearchParams();
      if (forceRefresh) {
        params.set("refresh", "1");
      }
      params.set("session", session);
      const response = await fetch(`${API_BASE}/api/postclose/market-review?${params.toString()}`);
      const payload = await response.json();
      if (!response.ok) {
        throw new Error(payload.detail || payload.message || `review failed: ${response.status}`);
      }
      reviewSession = session;
      renderNextExpectation(payload);
      const sectionTitle = qs("#postclose-review .section-head h2");
      if (sectionTitle) {
        sectionTitle.textContent = session === "midday" ? "午间快照" : "盘后复盘";
      }
      showToast(session === "midday" ? "午间快照已更新" : "盘后复盘已更新");
      document.dispatchEvent(new CustomEvent("ashare:postclose-session-updated", { detail: { session, payload } }));
    } catch (error) {
      console.error(error);
      showToast(error.message || "复盘获取失败");
    } finally {
      if (button) {
        button.disabled = false;
        button.textContent = originalText || (session === "midday" ? "午间快照" : "生成盘后复盘");
      }
      if (altButton) {
        altButton.disabled = false;
      }
    }
  }

  async function submitQA() {
    if (qaLoading) {
      return;
    }
    const input = qs("[data-postclose-qa-input]");
    const button = qs("[data-postclose-qa-submit]");
    const question = String(input?.value || "").trim();
    if (!question) {
      showToast("先输入一个问题");
      return;
    }

    qaLoading = true;
    const originalText = button ? button.textContent : "";
    if (button) {
      button.disabled = true;
      button.textContent = "发送中..";
    }

    try {
      const response = await fetch(`${API_BASE}/api/postclose/qa`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          question,
          session: reviewSession,
          include_holdings: true,
        }),
      });
      const payload = await response.json();
      if (!response.ok) {
        throw new Error(payload.detail || payload.message || `qa failed: ${response.status}`);
      }
      renderQA(payload);
      showToast(payload.llm_status?.used ? "盘后问答已生成模型解释" : "盘后问答已生成");
    } catch (error) {
      console.error(error);
      showToast(error.message || "盘后问答生成失败");
    } finally {
      qaLoading = false;
      if (button) {
        button.disabled = false;
        button.textContent = originalText || "发送问题";
      }
    }
  }

  async function submitOperationsReview() {
    if (operationsLoading) {
      return;
    }
    const button = qs("[data-postclose-operation-submit]");
    const payload = {
      operations: operationsDrafts.map((item) => ({
        symbol: item.symbol,
        side: item.side,
        price: item.price,
        position_change: item.position_change,
        operate_time: item.operate_time,
        reason: item.reason,
      })),
    };
    const originalText = button ? button.textContent : "";
    operationsLoading = true;
    if (button) {
      button.disabled = true;
      button.textContent = "生成中..";
    }
    try {
      const params = new URLSearchParams();
      params.set("session", reviewSession);
      const response = await fetch(`${API_BASE}/api/postclose/operations-review?${params.toString()}`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(payload),
      });
      const result = await response.json();
      if (!response.ok) {
        throw new Error(result.detail || result.message || `operations failed: ${response.status}`);
      }
      renderOperationsReview(result);
      showToast("操作复盘已生成");
    } catch (error) {
      console.error(error);
      showToast(error.message || "操作复盘生成失败");
    } finally {
      operationsLoading = false;
      if (button) {
        button.disabled = false;
        button.textContent = originalText || "生成操作复盘";
      }
    }
  }

  document.addEventListener("input", (event) => {
    const target = event.target.closest("[data-operation-field]");
    if (!target) {
      return;
    }
    updateOperationField(target.dataset.operationId, target.dataset.operationField, target.value);
  });

  document.addEventListener("change", (event) => {
    const target = event.target.closest("[data-operation-field]");
    if (!target) {
      return;
    }
    updateOperationField(target.dataset.operationId, target.dataset.operationField, target.value);
  });

  document.addEventListener("click", (event) => {
    const midday = event.target.closest("[data-postclose-midday]");
    if (midday) {
      event.preventDefault();
      fetchReview("midday", true);
      return;
    }

    const qaSubmit = event.target.closest("[data-postclose-qa-submit]");
    if (qaSubmit) {
      event.preventDefault();
      submitQA();
      return;
    }

    const qaClear = event.target.closest("[data-postclose-qa-clear]");
    if (qaClear) {
      event.preventDefault();
      const input = qs("[data-postclose-qa-input]");
      const shell = qs("[data-postclose-qa-result]");
      if (input) {
        input.value = "";
      }
      if (shell) {
        shell.classList.add("is-hidden");
      }
      showToast("盘后问答已清空");
      return;
    }

    const operationAdd = event.target.closest("[data-postclose-operation-add]");
    if (operationAdd) {
      event.preventDefault();
      addOperationDraft();
      return;
    }

    const operationClear = event.target.closest("[data-postclose-operation-clear]");
    if (operationClear) {
      event.preventDefault();
      clearOperationDrafts();
      showToast("操作录入已清空");
      return;
    }

    const operationRemove = event.target.closest("[data-postclose-operation-remove]");
    if (operationRemove) {
      event.preventDefault();
      removeOperationDraft(operationRemove.dataset.postcloseOperationRemove);
      return;
    }

    const operationSubmit = event.target.closest("[data-postclose-operation-submit]");
    if (operationSubmit) {
      event.preventDefault();
      submitOperationsReview();
    }
  });

  ensureSavedOperationsLoaded().then(renderOperationDrafts);
})();
