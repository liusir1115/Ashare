(function () {
  const state = {
    mode: "pre",
    stocks: [],
    lastPayload: null,
    lastResponse: null,
    history: [],
  };

  const resultRows = document.querySelector("#resultRows");
  const drawerContent = document.querySelector("#drawerContent");
  const toast = document.querySelector(".toast");
  const loadingStrip = document.querySelector("[data-loading-strip]");
  const loadingTitle = document.querySelector("[data-loading-title]");
  const loadingText = document.querySelector("[data-loading-text]");
  const loadingFill = document.querySelector("[data-loading-fill]");
  const tablePanel = document.querySelector(".table-panel");
  const historyList = document.querySelector("[data-history-list]");
  const strategyState = document.querySelector("[data-strategy-state]");
  const sourceList = document.querySelector("[data-source-list]");
  const conditionSummary = document.querySelector("[data-condition-summary]");
  const briefTitle = document.querySelector("[data-brief-title]");
  const briefUpdated = document.querySelector("[data-brief-updated]");
  const briefList = document.querySelector("[data-brief-list]");

  let loadingTimer = null;
  let loadingResetTimer = null;
  let loadingProgress = 0;

  const FILTER_LABELS = {
    price_range: "股价",
    total_market_cap: "总市值",
    circulating_market_cap: "流通市值",
    change_pct: "涨跌幅",
    rise_n_days: "近 N 日涨幅",
    pullback_n_days: "近 N 日回撤",
    turnover_rate: "换手率",
    amount: "成交额",
    volume_ratio: "量比",
    amplitude: "振幅",
    volume_expansion_shrink: "持续放量 / 缩量",
    ma_position: "均线位置",
    ma_breakout: "均线突破",
    new_high_low: "N 日新高 / 新低",
    consecutive_up_down: "连续涨跌",
  };

  function showToast(message) {
    if (!toast) return;
    toast.textContent = message;
    toast.classList.add("show");
    window.setTimeout(() => toast.classList.remove("show"), 2200);
  }

  function getNumberValue(input) {
    if (!input) return null;
    const raw = input.value.trim();
    if (!raw) return null;
    const parsed = Number(raw);
    return Number.isFinite(parsed) ? parsed : null;
  }

  function readRangeFilter(card) {
    const scale = Number(card.dataset.scale || "1");
    const minValue = getNumberValue(card.querySelector("[data-bound='min']"));
    const maxValue = getNumberValue(card.querySelector("[data-bound='max']"));
    if (minValue === null || maxValue === null) return null;
    return [minValue * scale, maxValue * scale];
  }

  function readDayRangeFilter(card) {
    const days = getNumberValue(card.querySelector("[data-day-field='days']"));
    const minValue = getNumberValue(card.querySelector("[data-day-field='min']"));
    const maxValue = getNumberValue(card.querySelector("[data-day-field='max']"));
    if (days === null || minValue === null || maxValue === null) return null;
    return { days, bounds: [minValue, maxValue] };
  }

  function readConsecutiveFilter(card) {
    const direction = card.querySelector("[data-consecutive-field='direction']")?.value || "up";
    const minDays = getNumberValue(card.querySelector("[data-consecutive-field='min']"));
    const maxDays = getNumberValue(card.querySelector("[data-consecutive-field='max']"));
    if (minDays === null || maxDays === null) return null;
    return { direction, min_days: minDays, max_days: maxDays };
  }

  function readFilterCard(card, screenDepth) {
    if (card.dataset.fullOnly === "true" && screenDepth !== "full") {
      return null;
    }

    const filterId = card.dataset.filter;
    const kind = card.dataset.filterKind;
    if (!filterId || !kind) return null;

    if (kind === "range") return readRangeFilter(card);
    if (kind === "day-range") return readDayRangeFilter(card);
    if (kind === "consecutive") return readConsecutiveFilter(card);
    if (kind === "select") return card.querySelector("[data-select-value]")?.value || null;
    return null;
  }

  function applyExcludeTemplate(payload) {
    const template = document.querySelector("[data-field='exclude_template']")?.value || "default";
    if (template === "minimal") {
      payload.exclude_bse = false;
      if (payload.screen_depth !== "full") {
        payload.exclude_new_listing_90d = false;
      }
    }
  }

  function readFormPayload() {
    const screenDepth = document.querySelector("[data-field='screen_depth']")?.value || "fast";
    const payload = {
      mode: state.mode,
      screen_depth: screenDepth,
      market_scope: document.querySelector("[data-field='market_scope']")?.value || "沪深主板 + 创业板",
      exclude_st: document.querySelector("[data-field='exclude_st']")?.checked ?? true,
      exclude_paused: document.querySelector("[data-field='exclude_paused']")?.checked ?? true,
      exclude_new_listing_90d: screenDepth === "full" ? (document.querySelector("[data-field='exclude_new_listing_90d']")?.checked ?? true) : false,
      exclude_bse: document.querySelector("[data-field='exclude_bse']")?.checked ?? true,
      filters: {},
    };

    document.querySelectorAll("[data-filter]").forEach((card) => {
      const filterId = card.dataset.filter;
      const value = readFilterCard(card, screenDepth);
      payload.filters[filterId] = value;
    });

    applyExcludeTemplate(payload);
    state.lastPayload = payload;
    return payload;
  }

  function summarizePayload(payload) {
    const summaries = [];
    Object.entries(payload.filters || {}).forEach(([key, value]) => {
      if (value === null || value === "" || value === undefined) return;
      const label = FILTER_LABELS[key] || key;

      if (Array.isArray(value)) {
        const display = key.includes("market_cap") || key === "amount"
          ? `${(value[0] / 1e8).toFixed(1)}-${(value[1] / 1e8).toFixed(1)}`
          : `${value[0]}-${value[1]}`;
        summaries.push(`${label} ${display}`);
        return;
      }

      if (typeof value === "object" && "bounds" in value) {
        summaries.push(`${label} ${value.days}天 ${value.bounds[0]}-${value.bounds[1]}`);
        return;
      }

      if (typeof value === "object" && "direction" in value) {
        const directionText = value.direction === "down" ? "连跌" : "连涨";
        summaries.push(`${label} ${directionText} ${value.min_days}-${value.max_days}天`);
        return;
      }

      summaries.push(`${label} ${value}`);
    });

    return summaries.slice(0, 6);
  }

  function updateConditionSummary(payload) {
    if (!conditionSummary) return;
    const summaries = summarizePayload(payload);
    conditionSummary.innerHTML = `<h4>当前条件摘要</h4>${summaries
      .map((item) => `<span>${item}</span>`)
      .join("")}`;
  }

  function renderRows() {
    if (!resultRows) return;
    if (!state.stocks.length) {
      resultRows.innerHTML = `
        <tr data-api-row="true">
          <td colspan="9" style="text-align:center;padding:24px 16px;">当前条件没有命中结果，可以放宽部分硬筛条件后重试。</td>
        </tr>
      `;
      return;
    }

    resultRows.innerHTML = state.stocks
      .map(
        (stock) => `
          <tr data-api-row="true">
            <td>${stock.rank}</td>
            <td class="score">${stock.score}</td>
            <td><span class="priority ${stock.priorityClass}">${stock.priority}</span></td>
            <td class="stock-cell"><strong>${stock.name}</strong><span>${stock.code} / ${stock.market}</span></td>
            <td>${stock.sectors}</td>
            <td>${stock.first}</td>
            <td>${stock.reason}</td>
            <td>${stock.risk}</td>
            <td><button class="detail-button" type="button" data-api-stock="${stock.code}">查看</button></td>
          </tr>
        `,
      )
      .join("");
  }

  function openDrawer(stock) {
    if (!drawerContent || !stock) return;
    drawerContent.innerHTML = `
      <div class="drawer-title">
        <h3>${stock.name} <span>${stock.code}</span></h3>
        <p>${stock.market} / ${stock.sectors} / 排名 ${stock.rank} / ${stock.score} 分</p>
      </div>

      <section class="detail-block">
        <h4>第一轮命中情况</h4>
        <ul>${(stock.metrics || []).map((item) => `<li>${item}</li>`).join("")}</ul>
        <p>${stock.first}</p>
      </section>

      <section class="detail-block">
        <h4>第二轮排序解释</h4>
        <p><strong>排序原因：</strong>${stock.reason}</p>
        <p><strong>题材与催化：</strong>${stock.sectors}</p>
        <p><strong>风险提示：</strong>${stock.risk}</p>
      </section>

      <section class="detail-block">
        <h4>评分摘要</h4>
        <div class="dimension-grid">
          ${Object.entries(stock.dimensions || {})
            .map(([key, value]) => `<div><span>${key}</span><strong>${value}</strong></div>`)
            .join("")}
        </div>
      </section>
    `;

    document.body.classList.add("drawer-open");
  }

  function updateSummary(payload, responsePayload) {
    document.querySelector("[data-result-mode]").textContent = state.mode === "post" ? "盘后复盘" : "盘前预判";
    document.querySelector("[data-result-scope]").textContent = payload.market_scope;
    document.querySelector("[data-result-filter-summary]").textContent = summarizePayload(payload).slice(0, 4).join(" / ") || "默认条件";
    document.querySelector("[data-result-first-round]").textContent = String(responsePayload.first_round_count || 0);
    document.querySelector("[data-result-final-round]").textContent = String(responsePayload.final_result_count || 0);

    const stageMeta = responsePayload.stage_meta || {};
    const sourceMeta = [
      stageMeta.spot_cache_hit ? "AKShare 快照命中缓存" : "AKShare 快照实时拉取",
      payload.screen_depth === "full" ? `增强 ${Math.round(stageMeta.enhancement_ms || 0)}ms` : `快筛 ${Math.round(stageMeta.fast_filter_ms || 0)}ms`,
    ];
    document.querySelector("[data-result-source-meta]").textContent = sourceMeta.join(" / ");

    document.querySelector("[data-first-round-metric]").textContent = `${responsePayload.first_round_count || 0} 只`;
    document.querySelector("[data-final-round-metric]").textContent = `${responsePayload.final_result_count || 0} 只`;
  }

  function updateSourceStatus(responsePayload) {
    if (!sourceList) return;
    const stageMeta = responsePayload.stage_meta || {};
    const histInfo = stageMeta.hist_enhancement || {};
    const rows = [
      {
        status: "ok",
        title: "AKShare 行情",
        text: stageMeta.spot_cache_hit ? "正常 · 命中缓存" : "正常 · 本轮拉取",
      },
      {
        status: histInfo.applied ? "ok" : "warn",
        title: "历史 K 线增强",
        text: histInfo.applied ? `执行 ${histInfo.success_count || 0}/${histInfo.candidate_count || 0}` : "本轮未启用",
      },
      {
        status: "warn",
        title: "行业 / 概念映射",
        text: "暂未接入，结果页保持占位说明",
      },
      {
        status: "warn",
        title: "筹码集中度",
        text: "暂未接入，不参与本轮筛选",
      },
      {
        status: responsePayload.results?.length ? "off" : "warn",
        title: "核心数据缺失",
        text: responsePayload.results?.length ? "未触发" : "本轮无结果，请检查条件",
      },
    ];

    sourceList.innerHTML = rows
      .map(
        (row) =>
          `<div class="source-row"><span class="status-dot ${row.status}"></span><strong>${row.title}</strong><em>${row.text}</em></div>`,
      )
      .join("");
  }

  function setLoadingProgress(progress, title, message) {
    loadingProgress = Math.max(0, Math.min(100, progress));
    if (loadingFill) loadingFill.style.width = `${loadingProgress}%`;
    if (title && loadingTitle) loadingTitle.textContent = title;
    if (message && loadingText) loadingText.textContent = message;
  }

  function clearLoadingTimers() {
    if (loadingTimer) {
      window.clearInterval(loadingTimer);
      loadingTimer = null;
    }
    if (loadingResetTimer) {
      window.clearTimeout(loadingResetTimer);
      loadingResetTimer = null;
    }
  }

  function startLoading(payload) {
    clearLoadingTimers();
    if (tablePanel) tablePanel.classList.add("is-loading");
    if (loadingStrip) loadingStrip.hidden = false;

    const steps =
      payload.screen_depth === "full"
        ? [
            { progress: 12, title: "正在拉取实时行情", message: "等待 AKShare 返回市场快照..." },
            { progress: 38, title: "正在执行首轮硬筛", message: "按价格、成交额、换手率与量比进行首轮过滤..." },
            { progress: 66, title: "正在补充历史增强指标", message: "拉取候选股票历史 K 线，计算趋势与强弱信息..." },
            { progress: 88, title: "正在整理候选榜单", message: "增强计算完成，正在生成排序结果..." },
          ]
        : [
            { progress: 18, title: "正在拉取实时行情", message: "等待 AKShare 返回市场快照..." },
            { progress: 54, title: "正在执行首轮硬筛", message: "按价格、成交额、换手率、振幅和量比进行快速筛选..." },
            { progress: 86, title: "正在整理候选榜单", message: "快速筛选完成，正在组织表格与详情数据..." },
          ];

    let stepIndex = 0;
    setLoadingProgress(steps[0].progress, steps[0].title, steps[0].message);
    loadingTimer = window.setInterval(() => {
      stepIndex += 1;
      if (stepIndex >= steps.length) {
        window.clearInterval(loadingTimer);
        loadingTimer = null;
        return;
      }
      const step = steps[stepIndex];
      setLoadingProgress(step.progress, step.title, step.message);
    }, payload.screen_depth === "full" ? 2400 : 1600);
  }

  function finishLoading(success, responsePayload) {
    clearLoadingTimers();
    if (success) {
      const count = responsePayload?.final_result_count || 0;
      setLoadingProgress(100, "结果已更新", count ? `已完成筛选，当前展示 ${count} 只候选股票。` : "已完成筛选，本轮条件下暂无候选股票。");
    } else {
      setLoadingProgress(Math.max(loadingProgress, 100), "请求失败", "本次数据拉取没有完成，页面保留上一轮结果。");
    }

    loadingResetTimer = window.setTimeout(() => {
      if (tablePanel) tablePanel.classList.remove("is-loading");
      if (loadingStrip) loadingStrip.hidden = true;
      if (loadingFill) loadingFill.style.width = "0%";
      loadingProgress = 0;
    }, success ? 700 : 1200);
  }

  function setStrategyState(payload, label) {
    if (!strategyState) return;
    strategyState.textContent = label || (payload.screen_depth === "full" ? "增强计算中" : "快筛进行中");
  }

  function updateFullOnlyState() {
    const screenDepth = document.querySelector("[data-field='screen_depth']")?.value || "fast";
    document.querySelectorAll("[data-full-only='true']").forEach((card) => {
      card.classList.toggle("is-inactive", screenDepth !== "full");
    });
  }

  async function runScreening() {
    const payload = readFormPayload();
    updateConditionSummary(payload);

    if (tablePanel?.classList.contains("is-loading")) {
      showToast("上一轮筛选还在执行中，请稍等。");
      return;
    }

    startLoading(payload);
    setStrategyState(payload);

    try {
      const response = await fetch("/api/screen/run", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      const responsePayload = await response.json();
      if (!response.ok) {
        throw new Error(responsePayload.detail || responsePayload.message || `Request failed: ${response.status}`);
      }

      state.stocks = Array.isArray(responsePayload.results) ? responsePayload.results : [];
      state.lastResponse = responsePayload;
      renderRows();
      updateSummary(payload, responsePayload);
      updateSourceStatus(responsePayload);
      setStrategyState(payload, state.stocks.length ? "已完成" : "无结果");
      finishLoading(true, responsePayload);
      await refreshHistory();
      showToast(
        payload.screen_depth === "full"
          ? `首轮 ${responsePayload.first_round_count || 0} 只，增强后 ${responsePayload.enhanced_count || 0} 只，展示 ${responsePayload.final_result_count || 0} 只`
          : `首轮 ${responsePayload.first_round_count || 0} 只，展示 ${responsePayload.final_result_count || 0} 只`,
      );
      document.querySelector("#results")?.scrollIntoView({ behavior: "smooth", block: "start" });
    } catch (error) {
      console.error(error);
      finishLoading(false);
      setStrategyState(payload, "接口异常");
      showToast(error.message || "后端接口暂时不可用。");
    }
  }

  function renderHistory() {
    if (!historyList) return;
    if (!state.history.length) {
      historyList.innerHTML = `
        <article>
          <strong>暂无记录</strong>
          <span>执行一次筛选后，这里会显示本地保存的 xlsx 结果。</span>
          <button type="button" disabled>打开</button>
        </article>
      `;
      return;
    }

    historyList.innerHTML = state.history
      .map(
        (item) => `
          <article>
            <strong>${item.generated_at} · ${item.mode_label}</strong>
            <span>${item.scope} · 深度 ${item.screen_depth} · 文件 ${item.file_name}</span>
            <button type="button" data-history-open="${item.file_path}">定位</button>
          </article>
        `,
      )
      .join("");
  }

  async function refreshHistory() {
    try {
      const response = await fetch("/api/history");
      if (!response.ok) {
        throw new Error(`history failed: ${response.status}`);
      }
      const payload = await response.json();
      state.history = Array.isArray(payload.items) ? payload.items : [];
      renderHistory();
    } catch (error) {
      console.error(error);
    }
  }

  function renderNewsBrief(payload) {
    if (!briefList || !briefTitle || !briefUpdated) return;

    const items = Array.isArray(payload?.items) ? payload.items : [];
    briefTitle.textContent = payload?.source_label ? `今日重点新闻 · ${payload.source_label}` : "今日重点新闻";
    briefUpdated.textContent = payload?.updated_at ? `更新 ${String(payload.updated_at).slice(11, 16) || payload.updated_at}` : "更新中";

    if (!items.length) {
      briefList.innerHTML = `
        <article>
          <strong>暂无新闻数据</strong>
          <p>当前没有拿到可展示的新闻条目，可以稍后刷新页面重试。</p>
        </article>
      `;
      return;
    }

    briefList.innerHTML = items
      .map((item) => {
        const footer = [item.source, item.published_at].filter(Boolean).join(" · ");
        const link = item.url
          ? `<a class="brief-link" href="${item.url}" target="_blank" rel="noreferrer">查看原文</a>`
          : "";
        return `
          <article>
            <strong>${item.title || "重点新闻"}</strong>
            <p>${item.summary || ""}</p>
            <div class="brief-meta">
              <span>${footer}</span>
              ${link}
            </div>
          </article>
        `;
      })
      .join("");
  }

  async function refreshNewsBrief() {
    try {
      const response = await fetch("/api/news/brief");
      if (!response.ok) {
        throw new Error(`news failed: ${response.status}`);
      }
      const payload = await response.json();
      renderNewsBrief(payload);
    } catch (error) {
      console.error(error);
      renderNewsBrief({
        source_label: "新闻接口异常",
        updated_at: "",
        items: [
          {
            title: "新闻简报加载失败",
            summary: "AKShare 新闻源本轮没有成功返回内容，稍后刷新页面可再次尝试。",
            source: "fallback",
            published_at: "",
          },
        ],
      });
    }
  }

  function resetForm() {
    window.location.reload();
  }

  function showExportMessage(kind) {
    if (!state.lastResponse?.export_file) {
      showToast(`${kind === "excel" ? "Excel" : "Markdown"} 导出入口已保留，请先执行一次筛选。`);
      return;
    }

    if (kind === "excel") {
      showToast(`本轮 Excel 已保存到 ${state.lastResponse.export_file}`);
      return;
    }

    showToast("Markdown 导出按钮已保留，当前版本先完成 Excel 落盘。");
  }

  document.addEventListener("ashare:mode-change", (event) => {
    state.mode = event.detail?.mode || "pre";
    document.querySelector("[data-result-mode]").textContent = state.mode === "post" ? "盘后复盘" : "盘前预判";
  });

  document.addEventListener("change", (event) => {
    if (event.target.matches("[data-field='screen_depth']")) {
      updateFullOnlyState();
    }

    if (
      event.target.closest("[data-filter]") ||
      event.target.matches("[data-field='screen_depth']") ||
      event.target.matches("[data-field='market_scope']") ||
      event.target.matches(".exclude-strip input")
    ) {
      updateConditionSummary(readFormPayload());
    }
  });

  document.addEventListener(
    "click",
    (event) => {
      const runButton = event.target.closest("[data-run-screen]");
      if (runButton) {
        event.preventDefault();
        event.stopPropagation();
        if (typeof event.stopImmediatePropagation === "function") {
          event.stopImmediatePropagation();
        }
        window.setTimeout(runScreening, 0);
        return;
      }

      const detailButton = event.target.closest("[data-api-stock]");
      if (detailButton) {
        event.preventDefault();
        const stock = state.stocks.find((item) => item.code === detailButton.dataset.apiStock);
        openDrawer(stock);
      }

      const historyButton = event.target.closest("[data-refresh-history]");
      if (historyButton) {
        refreshHistory();
      }

      const loadHistoryButton = event.target.closest("[data-load-history]");
      if (loadHistoryButton) {
        refreshHistory();
        showToast("已刷新历史记录列表。");
      }

      const resetButton = event.target.closest("[data-reset-form]");
      if (resetButton) {
        resetForm();
      }

      const exportButton = event.target.closest("[data-export]");
      if (exportButton) {
        showExportMessage(exportButton.dataset.export);
      }

      const addButton = event.target.closest("[data-add-condition]");
      if (addButton) {
        showToast("当前版本已固定全部指标，并改为结构化输入。");
      }

      const historyOpenButton = event.target.closest("[data-history-open]");
      if (historyOpenButton) {
        showToast(`结果文件位于 ${historyOpenButton.dataset.historyOpen}`);
      }

      const fullButton = event.target.closest("[data-view-full]");
      if (fullButton) {
        showToast("当前版本结果页展示前 10 名，完整榜单将在后续版本接入。");
      }
    },
    true,
  );

  updateFullOnlyState();
  updateConditionSummary(readFormPayload());
  renderRows();
  refreshNewsBrief();
  refreshHistory();
})();
