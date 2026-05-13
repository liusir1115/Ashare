(function () {
  if (window.__ASHARE_POSTCLOSE_BRIDGE_LOADED__) {
    return;
  }
  window.__ASHARE_POSTCLOSE_BRIDGE_LOADED__ = true;

  const API_BASE = window.ASHARE_API_BASE || "";
  const state = {
    loading: false,
    payload: null,
    holdingsLoading: false,
    holdingsDrafts: [],
    holdingsDraftLoaded: false,
  };

  function qs(selector, root = document) {
    return root.querySelector(selector);
  }

  function qsa(selector, root = document) {
    return Array.from(root.querySelectorAll(selector));
  }

  function setText(node, value) {
    if (node) {
      node.textContent = value;
    }
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

  function joinValues(values, fallback = "待补充") {
    if (!Array.isArray(values)) {
      return fallback;
    }
    const clean = values.map((item) => String(item || "").trim()).filter(Boolean);
    return clean.length ? clean.join(" / ") : fallback;
  }

  function formatTradeDate(value) {
    const raw = String(value || "").trim();
    if (!raw) {
      return "--";
    }
    if (/^\d{8}$/.test(raw)) {
      return `${raw.slice(0, 4)}-${raw.slice(4, 6)}-${raw.slice(6, 8)}`;
    }
    return raw;
  }

  function formatSourceValue(value, fallback = "--") {
    if (Array.isArray(value)) {
      return value.length ? value.join(" / ") : fallback;
    }
    const text = String(value || "").trim();
    return text || fallback;
  }

  function formatReportParagraph(value) {
    const text = String(value || "").trim();
    if (!text) {
      return "--";
    }
    return text
      .replace(/\n•\s*/g, "\n\n• ")
      .replace(/。•/g, "。\n\n•")
      .replace(/；•/g, "；\n\n•")
      .replace(/\n{3,}/g, "\n\n");
  }

  function getPostcloseRoot() {
    return qs("#postclose-review");
  }

  function defaultHoldingDraft() {
    return {
      id: `holding-${Date.now()}-${Math.random().toString(16).slice(2, 8)}`,
      symbol: "",
      asset_type: "stock",
      direction: "持有",
      cost: "",
      position_pct: "",
      reason: "",
    };
  }

  function normalizeDraft(rawDraft) {
    return {
      id: rawDraft.id || `holding-${Date.now()}-${Math.random().toString(16).slice(2, 8)}`,
      symbol: String(rawDraft.symbol || "").trim(),
      asset_type: rawDraft.asset_type === "etf" ? "etf" : "stock",
      direction: String(rawDraft.direction || "持有").trim() || "持有",
      cost: rawDraft.cost ?? "",
      position_pct: rawDraft.position_pct ?? "",
      reason: String(rawDraft.reason || "").trim(),
    };
  }

  function ensureDrafts() {
    if (!state.holdingsDrafts.length) {
      state.holdingsDrafts = [defaultHoldingDraft()];
    }
  }

  async function ensureSavedDraftsLoaded() {
    if (state.holdingsDraftLoaded) {
      return;
    }
    state.holdingsDraftLoaded = true;
    try {
      const response = await fetch(`${API_BASE}/api/postclose/holdings-draft`);
      const payload = await response.json();
      if (response.ok && Array.isArray(payload.holdings) && payload.holdings.length) {
        state.holdingsDrafts = payload.holdings.map(normalizeDraft);
      }
    } catch (error) {
      console.error(error);
    }
    ensureDrafts();
  }

  function getDashboardArticles() {
    return qsa(".postclose-dashboard-quicklook .brief-list article");
  }

  function getMarketSummaryCards() {
    return qsa(".postclose-summary-grid article:not(.postclose-holding-summary-card)");
  }

  function getEvidenceItems() {
    return qsa(".postclose-evidence-list > div");
  }

  function getFactNodes() {
    return {
      date: qs("[data-postclose-fact-date]"),
      breadth: qs("[data-postclose-fact-breadth]"),
      turnover: qs("[data-postclose-fact-turnover]"),
      emotion: qs("[data-postclose-fact-emotion]"),
    };
  }

  function getPostDashboardNodes() {
    return {
      title: qs("[data-post-dashboard-title]"),
      text: qs("[data-post-dashboard-text]"),
    };
  }

  function getLLMStatusNode() {
    return qs("[data-postclose-llm-status]");
  }

  function getReportSections() {
    return {
      close: qs('[data-report-section="close"] p'),
      environment: qs('[data-report-section="environment"] p'),
      funds: qs('[data-report-section="funds"] p'),
      focus: qs('[data-report-section="focus"] p'),
      rotation: qs('[data-report-section="rotation"] p'),
      emotion: qs('[data-report-section="emotion"] p'),
      reason: qs('[data-report-section="reason"] p'),
      plan: qs('[data-report-section="plan"] p'),
    };
  }

  function findPanelByTitle(keyword) {
    const root = getPostcloseRoot();
    return qsa(".panel", root).find((panel) => {
      const title = qs(".panel-head h3", panel);
      return title && title.textContent.includes(keyword);
    });
  }

  async function ensureHoldingsUI() {
    const root = getPostcloseRoot();
    if (!root) {
      return null;
    }
    await ensureSavedDraftsLoaded();

    const holdingsFormPanel = findPanelByTitle("持仓录入");
    const holdingsResultPanel = findPanelByTitle("持仓复盘结果");
    if (!holdingsFormPanel || !holdingsResultPanel) {
      return null;
    }

    let editorRoot = qs("[data-holdings-editor-root]", holdingsFormPanel);
    if (!editorRoot) {
      const firstShell = qsa(".postclose-form-shell", holdingsFormPanel)[0];
      if (firstShell) {
        firstShell.innerHTML = "";
        firstShell.dataset.holdingsEditorRoot = "true";
        editorRoot = firstShell;
      }
    }

    if (editorRoot) {
      editorRoot.innerHTML = `
        <div class="postclose-holdings-toolbar">
          <div>
            <strong>持仓批量录入</strong>
            <span>支持股票和 ETF，多条持仓一起提交复盘，提交后会自动保存本地草稿。</span>
          </div>
          <div class="button-row">
            <button class="secondary-button" type="button" data-postclose-holding-add>新增一条</button>
            <button class="secondary-button" type="button" data-postclose-holding-clear>清空全部</button>
            <button class="primary-button" type="button" data-postclose-holding-submit>生成持仓复盘</button>
          </div>
        </div>
        <div class="postclose-holdings-list" data-holdings-list></div>
      `;
      renderHoldingDrafts();
    }

    const panelHeadTag = qs(".panel-head .panel-tag", holdingsResultPanel);
    if (panelHeadTag && !panelHeadTag.dataset.holdingsReviewTag) {
      panelHeadTag.dataset.holdingsReviewTag = "true";
    }

    const emptyState = qs(".postclose-empty-state", holdingsResultPanel);
    if (emptyState && !qs("[data-holdings-review-result]", holdingsResultPanel)) {
      emptyState.dataset.holdingsEmptyState = "true";
      const result = document.createElement("div");
      result.className = "postclose-holdings-result is-hidden";
      result.dataset.holdingsReviewResult = "true";
      result.innerHTML = `
        <div class="postclose-llm-hint">
          <span>持仓解释层状态</span>
          <strong data-holdings-llm-status>--</strong>
        </div>
        <div class="postclose-holdings-summary-grid">
          <article class="postclose-holding-summary-card">
            <span>组合总评</span>
            <strong data-holdings-summary-title>--</strong>
            <p data-holdings-summary-text>--</p>
          </article>
          <article class="postclose-holding-summary-card">
            <span>风险提示</span>
            <strong data-holdings-risk-title>--</strong>
            <p data-holdings-risk-text>--</p>
          </article>
          <article class="postclose-holding-summary-card">
            <span>次日执行</span>
            <strong data-holdings-plan-title>--</strong>
            <p data-holdings-plan-text>--</p>
          </article>
        </div>
        <div class="postclose-holding-cards" data-holding-cards></div>
      `;
      holdingsResultPanel.appendChild(result);
    }

    return {
      root,
      holdingsFormPanel,
      holdingsResultPanel,
    };
  }

  function renderHoldingDrafts() {
    const root = getPostcloseRoot();
    const listNode = qs("[data-holdings-list]", root);
    if (!listNode) {
      return;
    }

    listNode.innerHTML = state.holdingsDrafts
      .map(
        (draft, index) => `
          <article class="postclose-holding-editor-card" data-holding-row="${draft.id}">
            <div class="postclose-holding-editor-head">
              <div>
                <strong>持仓 ${index + 1}</strong>
                <span>${draft.asset_type === "etf" ? "ETF" : "股票"} 条目</span>
              </div>
              <button class="ghost-button" type="button" data-postclose-holding-remove="${draft.id}" ${state.holdingsDrafts.length === 1 ? "disabled" : ""}>删除</button>
            </div>
            <div class="postclose-form-row">
              <label>
                <span>标的类型</span>
                <select data-draft-field="asset_type" data-draft-id="${draft.id}">
                  <option value="stock" ${draft.asset_type === "stock" ? "selected" : ""}>股票</option>
                  <option value="etf" ${draft.asset_type === "etf" ? "selected" : ""}>ETF</option>
                </select>
              </label>
              <label>
                <span>代码 / 名称</span>
                <input type="text" value="${draft.symbol}" placeholder="${draft.asset_type === "etf" ? "如：512930 或 AI人工智能ETF" : "如：002432 或 九安医疗"}" data-draft-field="symbol" data-draft-id="${draft.id}" />
              </label>
            </div>
            <div class="postclose-form-row">
              <label>
                <span>持仓方向</span>
                <select data-draft-field="direction" data-draft-id="${draft.id}">
                  <option value="持有" ${draft.direction === "持有" ? "selected" : ""}>持有</option>
                  <option value="观察仓" ${draft.direction === "观察仓" ? "selected" : ""}>观察仓</option>
                </select>
              </label>
              <label>
                <span>当前仓位</span>
                <input type="text" value="${draft.position_pct}" placeholder="如：25" data-draft-field="position_pct" data-draft-id="${draft.id}" />
              </label>
            </div>
            <div class="postclose-form-row">
              <label>
                <span>持仓成本</span>
                <input type="text" value="${draft.cost}" placeholder="如：12.45" data-draft-field="cost" data-draft-id="${draft.id}" />
              </label>
              <label>
                <span>备注</span>
                <input type="text" value="${draft.reason}" placeholder="可选，记录最初逻辑或今天的新判断" data-draft-field="reason" data-draft-id="${draft.id}" />
              </label>
            </div>
          </article>
        `
      )
      .join("");
  }

  function updateDraftField(draftId, field, value) {
    state.holdingsDrafts = state.holdingsDrafts.map((draft) =>
      draft.id === draftId ? { ...draft, [field]: value } : draft
    );
    if (field === "asset_type") {
      renderHoldingDrafts();
    }
  }

  function addHoldingDraft() {
    state.holdingsDrafts = [...state.holdingsDrafts, defaultHoldingDraft()];
    renderHoldingDrafts();
  }

  function removeHoldingDraft(draftId) {
    if (state.holdingsDrafts.length <= 1) {
      return;
    }
    state.holdingsDrafts = state.holdingsDrafts.filter((draft) => draft.id !== draftId);
    renderHoldingDrafts();
  }

  function clearHoldingForm() {
    state.holdingsDrafts = [defaultHoldingDraft()];
    renderHoldingDrafts();
  }

  function buildHeadline(payload) {
    return payload.report_detail?.close || "待生成市场总收口。";
  }

  function renderDashboard(payload) {
    const articles = getDashboardArticles();
    const marketFacts = payload.market?.facts || {};
    const factSummary = payload.fact_summary || {};
    const firstNews = payload.news?.items?.[0];
    const dashboardNodes = getPostDashboardNodes();

    if (articles[0]) {
      setText(qs("strong", articles[0]), `市场主线候选：${joinValues(factSummary.mainline_candidates)}`);
      setText(
        qs("p", articles[0]),
        `交易日 ${formatTradeDate(payload.postclose_facts?.trade_date || payload.trade_date)}，上涨 ${marketFacts.up_count || 0} 家，下跌 ${marketFacts.down_count || 0} 家，成交额 ${marketFacts.turnover_total_text || "--"}。`
      );
    }

    if (articles[1]) {
      setText(qs("strong", articles[1]), payload.status === "ok" ? "市场总复盘已生成" : "市场总复盘已降级生成");
      setText(qs("p", articles[1]), firstNews?.summary || payload.news?.message || "暂无补充新闻摘要。");
    }

    setText(dashboardNodes.title, payload.status === "ok" ? "市场总复盘已生成" : "市场总复盘已降级生成");
    setText(dashboardNodes.text, buildHeadline(payload));
  }

  function renderHeadline(payload) {
    const headlineCard = qs(".postclose-headline-card");
    if (!headlineCard) {
      return;
    }
    const sourceNotes = payload.report_detail?.source_notes || {};
    const newsSource = formatSourceValue(sourceNotes.news || payload.news?.source_label);
    const marketSource = formatSourceValue(sourceNotes.market || payload.data_sources?.market);

    setText(qs("span", headlineCard), "一句话总收口");
    setText(qs("strong", headlineCard), buildHeadline(payload));
    setText(qs("p", headlineCard), `事实层来自 ${marketSource}，新闻层来自 ${newsSource}。完整简报会在下方逐章展开。`);
  }

  function renderLLMStatus(payload) {
    const node = getLLMStatusNode();
    if (!node) {
      return;
    }
    const llmStatus = payload.llm_status || {};
    if (llmStatus.used) {
      setText(node, `当前使用 ${llmStatus.provider || "LLM"} / ${llmStatus.model || "--"} 生成解释层`);
      return;
    }
    setText(node, "当前使用事实层解释版本，模型不可用时会自动降级，不会卡住。");
  }

  function renderFactStrip(payload) {
    const nodes = getFactNodes();
    const marketFacts = payload.market?.facts || {};
    const emotion = payload.fact_summary?.emotion_snapshot || {};

    setText(nodes.date, formatTradeDate(payload.postclose_facts?.trade_date || payload.trade_date));
    setText(nodes.breadth, `上涨 ${marketFacts.up_count || 0} / 下跌 ${marketFacts.down_count || 0}`);
    setText(nodes.turnover, marketFacts.turnover_total_text || "--");
    setText(nodes.emotion, `涨停 ${emotion.limit_up_count || 0} / 最高板 ${emotion.highest_board || 0}`);
  }

  function renderSummaryCards(payload) {
    const cards = getMarketSummaryCards();
    const marketFacts = payload.market?.facts || {};
    const factSummary = payload.fact_summary || {};
    const emotion = factSummary.emotion_snapshot || {};
    const detail = payload.report_detail || {};

    const values = [
      {
        strong: joinValues(factSummary.mainline_candidates),
        text: detail.focus || `当前最值得保留的主线，主要映射到 ${joinValues(factSummary.hot_topics)}。`,
      },
      {
        strong: joinValues(factSummary.concept_candidates, "待继续观察轮动补位"),
        text: detail.rotation || "用于识别次主线、承接方向与失败轮动。",
      },
      {
        strong: `最高板 ${emotion.highest_board || 0} / 跌停 ${marketFacts.limit_down_count || 0}`,
        text: "这里聚焦情绪边界、接力风险与不应盲目追逐的区域。",
      },
      {
        strong: joinValues(emotion.limit_focus, "优先看核心承接"),
        text: detail.plan || "次日先看这些核心焦点是否继续获得承接。",
      },
    ];

    cards.forEach((card, index) => {
      const value = values[index];
      if (!value) {
        return;
      }
      setText(qs("strong", card), value.strong);
      setText(qs("p", card), value.text);
    });
  }

  function renderEvidence(payload) {
    const evidenceItems = getEvidenceItems();
    const marketFacts = payload.market?.facts || {};
    const factSummary = payload.fact_summary || {};
    const emotion = factSummary.emotion_snapshot || {};
    const sourceNotes = payload.report_detail?.source_notes || {};

    const texts = [
      `市场宽度：上涨 ${marketFacts.up_count || 0} / 下跌 ${marketFacts.down_count || 0} / 平盘 ${marketFacts.flat_count || 0}。\n平均涨跌幅 ${marketFacts.avg_change_pct || 0}% 。`,
      `主线候选：${joinValues(factSummary.mainline_candidates)}。\n热点题材：${joinValues(factSummary.hot_topics)}。`,
      `次主线候选：${joinValues(factSummary.concept_candidates)}。\n活口焦点：${joinValues(emotion.limit_focus)}。`,
      `情绪锚点：涨停 ${emotion.limit_up_count || 0}，最高板 ${emotion.highest_board || 0}。\n数据来自 ${formatSourceValue(sourceNotes.postclose_facts || payload.data_sources?.postclose_facts)}。`,
    ];

    evidenceItems.forEach((item, index) => {
      setText(qs("p", item), texts[index] || "--");
    });
  }

  function renderDetailReport(payload) {
    const detail = payload.report_detail || {};
    const sections = getReportSections();

    setText(sections.close, formatReportParagraph(detail.close));
    setText(sections.environment, formatReportParagraph(detail.environment));
    setText(sections.funds, formatReportParagraph(detail.funds));
    setText(sections.focus, formatReportParagraph(detail.focus));
    setText(sections.rotation, formatReportParagraph(detail.rotation));
    setText(sections.emotion, formatReportParagraph(detail.emotion));
    setText(sections.reason, formatReportParagraph(detail.reason));
    setText(sections.plan, formatReportParagraph(detail.plan));
  }

  function renderSourceNotes(payload) {
    const sourceNotes = payload.report_detail?.source_notes || {};
    const nodes = {
      tradeDate: qs("[data-source-trade-date]"),
      market: qs("[data-source-market]"),
      postcloseFacts: qs("[data-source-postclose-facts]"),
      news: qs("[data-source-news]"),
      updatedAt: qs("[data-source-updated-at]"),
    };

    setText(nodes.tradeDate, formatTradeDate(sourceNotes.trade_date || payload.trade_date));
    setText(nodes.market, formatSourceValue(sourceNotes.market || payload.data_sources?.market));
    setText(nodes.postcloseFacts, formatSourceValue(sourceNotes.postclose_facts || payload.data_sources?.postclose_facts));
    setText(nodes.news, formatSourceValue(sourceNotes.news || payload.data_sources?.news));
    setText(nodes.updatedAt, formatSourceValue(sourceNotes.news_updated_at || payload.news?.updated_at));
  }

  function renderNextDayExpectation(payload) {
    const block = payload.next_day_expectation || {};
    const sessionMeta = payload.session_meta || {};
    const watchpoints = Array.isArray(block.watchpoints) ? block.watchpoints : [];
    const risks = Array.isArray(block.risk_triggers) ? block.risk_triggers : [];
    const order = Array.isArray(block.execution_order) ? block.execution_order : [];

    setText(qs("[data-nextday-label]"), block.label || sessionMeta.action_label || "次日预期");
    setText(qs("[data-nextday-headline]"), block.headline || "等待生成结构化预期");
    setText(qs("[data-nextday-session-tag]"), sessionMeta.label || "结构化输出");

    const renderList = (selector, items, fallback) => {
      const node = qs(selector);
      if (!node) {
        return;
      }
      node.innerHTML = items.length
        ? items.map((item) => `<li>${String(item || "").trim()}</li>`).join("")
        : `<li>${fallback}</li>`;
    };

    renderList("[data-nextday-watchpoints]", watchpoints, "等待生成观察重点");
    renderList("[data-nextday-risks]", risks, "等待生成风险触发");
    renderList("[data-nextday-order]", order, "等待生成执行顺序");
  }

  function renderTradeDate(payload) {
    const tag = qs("#postclose-review .panel-head .panel-tag");
    if (!tag) {
      return;
    }
    tag.textContent = `交易日 ${formatTradeDate(payload.postclose_facts?.trade_date || payload.trade_date)}`;
  }

  function renderPayload(payload) {
    renderDashboard(payload);
    renderTradeDate(payload);
    renderHeadline(payload);
    renderLLMStatus(payload);
    renderFactStrip(payload);
    renderSummaryCards(payload);
    renderEvidence(payload);
    renderDetailReport(payload);
    renderSourceNotes(payload);
    renderNextDayExpectation(payload);
  }

  function collectHoldingPayload() {
    return {
      holdings: state.holdingsDrafts.map((draft) => ({
        symbol: draft.symbol,
        asset_type: draft.asset_type,
        direction: draft.direction,
        cost: draft.cost,
        position_pct: draft.position_pct,
        reason: draft.reason,
      })),
    };
  }

  function buildHoldingFactChips(item) {
    const concepts = item.concepts || {};
    const chips = [];
    if (Array.isArray(concepts.driver_candidates) && concepts.driver_candidates.length) {
      chips.push(`核心驱动：${concepts.driver_candidates.slice(0, 3).join(" / ")}`);
    }
    if (Array.isArray(concepts.market_overlap) && concepts.market_overlap.length) {
      chips.push(`市场共振：${concepts.market_overlap.slice(0, 3).join(" / ")}`);
    }
    if (Array.isArray(concepts.all) && concepts.all.length) {
      chips.push(`概念覆盖：${concepts.all.slice(0, 4).join(" / ")}`);
    }
    return chips;
  }

  function formatHoldingText(value) {
    const text = String(value || "").trim();
    if (!text) {
      return "--";
    }
    return text
      .replace(/。/g, "。\n")
      .replace(/；/g, "；\n")
      .replace(/\n{3,}/g, "\n\n")
      .trim();
  }

  function renderHoldingsReview(payload) {
    const root = getPostcloseRoot();
    const emptyState = qs("[data-holdings-empty-state]", root);
    const resultNode = qs("[data-holdings-review-result]", root);
    const tag = qs("[data-holdings-review-tag]", root);
    const llmStatus = payload.llm_status || {};
    const review = payload.review || {};
    const factsBySymbol = new Map((payload.holdings_facts || []).map((item) => [item.symbol, item]));
    const cardsRoot = qs("[data-holding-cards]", root);

    if (emptyState) {
      emptyState.classList.add("is-hidden");
    }
    if (resultNode) {
      resultNode.classList.remove("is-hidden");
    }
    if (tag) {
      tag.textContent = `已生成 ${payload.holdings_input_count || 0} 条`;
    }

    setText(
      qs("[data-holdings-llm-status]", root),
      llmStatus.used
        ? `当前使用 ${llmStatus.provider || "LLM"} / ${llmStatus.model || "--"} 生成持仓解释层`
        : "当前使用事实层持仓解释版本"
    );
    setText(qs("[data-holdings-summary-title]", root), "组合与市场风格匹配度");
    setText(qs("[data-holdings-summary-text]", root), review.portfolio_summary || "--");
    setText(qs("[data-holdings-risk-title]", root), "当前最重要的风险边界");
    setText(qs("[data-holdings-risk-text]", root), review.risk_flags || "--");
    setText(qs("[data-holdings-plan-title]", root), "次日观察与处理顺序");
    setText(qs("[data-holdings-plan-text]", root), review.action_plan || "--");

    if (cardsRoot) {
      const items = Array.isArray(review.holdings) ? review.holdings : [];
      cardsRoot.innerHTML = items
        .map((item) => {
          const fact = factsBySymbol.get(item.symbol) || {};
          const chips = buildHoldingFactChips(fact)
            .map((text) => `<span class="holding-chip">${text}</span>`)
            .join("");
          const evidence = (fact.concepts?.driver_evidence || [])
            .slice(0, 2)
            .map((text) => `<li>${text}</li>`)
            .join("");
          return `
            <article class="postclose-holding-card">
              <div class="postclose-holding-head">
                <div>
                  <strong>${item.name || item.symbol || "--"}</strong>
                  <span>${item.symbol || "--"} · ${item.verdict || "--"}</span>
                </div>
                <div class="holding-meta-pack">
                  <span>${fact.industry || "--"}</span>
                  <span>${fact.day_change_pct != null ? `当日 ${fact.day_change_pct}%` : "当日 --"}</span>
                  <span>${fact.pnl_pct != null ? `浮盈亏 ${fact.pnl_pct}%` : "浮盈亏 --"}</span>
                </div>
              </div>
              <div class="holding-chip-row">${chips || '<span class="holding-chip">概念证据待补充</span>'}</div>
              <div class="postclose-holding-body">
                <div>
                  <span>为什么这样判断</span>
                  <p>${formatHoldingText(item.thesis || "--")}</p>
                </div>
                <div>
                  <span>当前风险</span>
                  <p>${formatHoldingText(item.risk || "--")}</p>
                </div>
                <div>
                  <span>次日动作</span>
                  <p>${formatHoldingText(item.next_step || "--")}</p>
                </div>
              </div>
              <div class="holding-evidence-block">
                <span>驱动证据</span>
                <ul>${evidence || "<li>当前暂无更多结构化驱动证据。</li>"}</ul>
              </div>
            </article>
          `;
        })
        .join("");
    }
  }

  async function fetchPostcloseReview(forceRefresh) {
    if (state.loading) {
      return;
    }
    state.loading = true;

    const button = qs("[data-postclose-generate]");
    const originalText = button ? button.textContent : "";
    if (button) {
      button.disabled = true;
      button.textContent = "生成中...";
    }

    try {
      const suffix = forceRefresh ? "?refresh=1" : "";
      const response = await fetch(`${API_BASE}/api/postclose/market-review${suffix}`);
      const payload = await response.json();
      if (!response.ok) {
        throw new Error(payload.detail || payload.message || `postclose failed: ${response.status}`);
      }
      state.payload = payload;
      renderPayload(payload);
      showToast(payload.llm_status?.used ? "盘后复盘已切换到模型解释层" : "盘后复盘已更新");
    } catch (error) {
      console.error(error);
      showToast(error.message || "盘后复盘获取失败");
    } finally {
      state.loading = false;
      if (button) {
        button.disabled = false;
        button.textContent = originalText || "生成盘后复盘";
      }
    }
  }

  async function submitHoldingsReview(forceRefresh) {
    if (state.holdingsLoading) {
      return;
    }
    const payload = collectHoldingPayload();
    const button = qs("[data-postclose-holding-submit]");
    const originalText = button ? button.textContent : "";
    state.holdingsLoading = true;

    if (button) {
      button.disabled = true;
      button.textContent = "生成中...";
    }

    try {
      const suffix = forceRefresh ? "?refresh=1" : "";
      const response = await fetch(`${API_BASE}/api/postclose/holdings-review${suffix}`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(payload),
      });
      const result = await response.json();
      if (!response.ok) {
        throw new Error(result.detail || result.message || `holdings review failed: ${response.status}`);
      }
      renderHoldingsReview(result);
      showToast(result.llm_status?.used ? "持仓复盘已生成模型解释层" : "持仓复盘已按事实层生成");
    } catch (error) {
      console.error(error);
      showToast(error.message || "持仓复盘生成失败");
    } finally {
      state.holdingsLoading = false;
      if (button) {
        button.disabled = false;
        button.textContent = originalText || "生成持仓复盘";
      }
    }
  }

  document.addEventListener("input", (event) => {
    const target = event.target.closest("[data-draft-field]");
    if (!target) {
      return;
    }
    updateDraftField(target.dataset.draftId, target.dataset.draftField, target.value);
  });

  document.addEventListener("change", (event) => {
    const target = event.target.closest("[data-draft-field]");
    if (!target) {
      return;
    }
    updateDraftField(target.dataset.draftId, target.dataset.draftField, target.value);
  });

  document.addEventListener("click", async (event) => {
    const trigger = event.target.closest("[data-postclose-generate]");
    if (trigger) {
      event.preventDefault();
      fetchPostcloseReview(true);
      return;
    }

    const holdingsTrigger = event.target.closest("[data-postclose-holding-submit]");
    if (holdingsTrigger) {
      event.preventDefault();
      submitHoldingsReview(true);
      return;
    }

    const addTrigger = event.target.closest("[data-postclose-holding-add]");
    if (addTrigger) {
      event.preventDefault();
      addHoldingDraft();
      return;
    }

    const clearTrigger = event.target.closest("[data-postclose-holding-clear]");
    if (clearTrigger) {
      event.preventDefault();
      clearHoldingForm();
      showToast("持仓输入已清空");
      return;
    }

    const removeTrigger = event.target.closest("[data-postclose-holding-remove]");
    if (removeTrigger) {
      event.preventDefault();
      removeHoldingDraft(removeTrigger.dataset.postcloseHoldingRemove);
    }
  });

  document.addEventListener("ashare:mode-change", async (event) => {
    const mode = event.detail?.mode || "pre";
    if (mode === "post") {
      await ensureHoldingsUI();
      if (!state.payload) {
        fetchPostcloseReview(false);
      }
    }
  });

  ensureHoldingsUI();
})();
