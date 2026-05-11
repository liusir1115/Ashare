(function () {
  const API_BASE = window.ASHARE_API_BASE || "";
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
  const strategyQuery = document.querySelector("[data-strategy-query]");
  const strategyNotes = document.querySelector("[data-strategy-notes]");
  const strategyMapping = document.querySelector("[data-strategy-mapping]");
  const strategyConditions = document.querySelector("[data-strategy-conditions]");
  const strategyLLMStatus = document.querySelector("[data-strategy-llm-status]");
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
    chip_concentration: "筹码集中度",
    winner_rate: "获利盘比例",
    price_vs_chip: "现价相对筹码成本",
  };

  const STRATEGY_TAG_LIBRARY = [
    { id: "momentum", aliases: ["动量", "momentum", "强趋势", "趋势强化"] },
    { id: "reversal", aliases: ["反转", "反弹", "低吸", "reversal"] },
    { id: "pullback", aliases: ["回调", "回踩", "pullback", "缩量回调"] },
    { id: "volume_expand", aliases: ["放量", "量能放大", "volume expansion", "放量突破"] },
    { id: "volume_shrink", aliases: ["缩量", "量能收缩", "volume shrink", "缩量整理"] },
    { id: "breakout", aliases: ["突破", "平台突破", "breakout"] },
    { id: "new_high", aliases: ["新高", "阶段新高", "new high"] },
    { id: "oversold", aliases: ["超跌", "跌深反弹", "oversold"] },
    { id: "strong_tape", aliases: ["连板", "强势", "主升"] },
    { id: "chip_focus", aliases: ["筹码", "筹码集中", "筹码结构", "chip"] },
    { id: "winner_rate", aliases: ["获利盘", "套牢盘轻", "winner rate"] },
    { id: "chip_cost", aliases: ["成本附近", "回到成本", "筹码成本", "cost line"] },
    { id: "trend_acceleration", aliases: ["趋势加速", "加速", "加速段", "accelerate"] },
    { id: "ma_bull", aliases: ["均线多头", "多头排列", "沿均线走强", "ma bull"] },
    { id: "platform_breakout", aliases: ["平台突破", "箱体突破", "突破平台", "platform breakout"] },
    { id: "weak_to_strong", aliases: ["弱转强", "转强", "分歧转强", "weak to strong"] },
    { id: "leader_return", aliases: ["龙头回流", "核心回流", "主线回流", "leader return"] },
    { id: "small_cap_elasticity", aliases: ["小票弹性", "小市值弹性", "弹性票", "small cap"] },
  ];

  function showToast(message) {
    if (!toast) return;
    toast.textContent = message;
    toast.classList.add("show");
    window.setTimeout(() => toast.classList.remove("show"), 2200);
  }

  function splitNewsSummary(summary) {
    return String(summary || "")
      .split(/[；;。]\s*/)
      .map((part) => part.trim())
      .filter(Boolean)
      .slice(0, 4);
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
    if (minDays === null && maxDays === null) return null;
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
    conditionSummary.innerHTML = `<h4>当前条件摘要</h4>${
      summaries.length
        ? summaries.map((item) => `<span>${item}</span>`).join("")
        : '<span>当前未启用硬性筛选条件，只有你主动填写的项才会生效。</span>'
    }`;
  }

  function detectStrategyTags(query) {
    const text = String(query || "").trim().toLowerCase();
    if (!text) return [];
    return STRATEGY_TAG_LIBRARY
      .filter((tag) => (tag.aliases || []).some((alias) => text.includes(String(alias).toLowerCase())))
      .map((tag) => tag.id);
  }

  function setStrategyNotes(notes, unsupportedIntents) {
    if (!strategyNotes) return;
    const noteItems = Array.isArray(notes) ? notes.filter(Boolean) : [];
    const unsupported = Array.isArray(unsupportedIntents) ? unsupportedIntents.filter(Boolean) : [];
    const combined = [
      ...noteItems,
      ...unsupported.map((item) => `暂未接入：${item}`),
    ];

    strategyNotes.innerHTML = `<h4>解析说明</h4>${
      combined.length
        ? combined.map((item) => `<span>${item}</span>`).join("")
        : '<span>这里会解释系统如何把自然语言翻译成筛选条件。</span>'
    }`;
  }

  function setStrategyMapping(mappingSummary) {
    if (!strategyMapping) return;
    const rows = Array.isArray(mappingSummary) ? mappingSummary.filter(Boolean) : [];
    strategyMapping.innerHTML = `<h4>映射词与指标</h4>${
      rows.length
        ? rows.map((item) => `<span>${item}</span>`).join("")
        : '<span>这里会展示自然语言策略先被识别成哪些策略词，再映射到哪些量化指标。</span>'
    }`;
  }

  function formatStrategyCondition(key, value) {
    const label = FILTER_LABELS[key] || key;
    if (value === null || value === undefined || value === "") {
      return null;
    }

    if (Array.isArray(value)) {
      const unit = key.includes("market_cap") || key === "amount" ? "亿" : "%";
      if (key.includes("market_cap") || key === "amount") {
        return `${label}：${(value[0] / 1e8).toFixed(1)}-${(value[1] / 1e8).toFixed(1)} ${unit}`;
      }
      if (key === "volume_ratio") {
        return `${label}：${value[0]} - ${value[1]}`;
      }
      return `${label}：${value[0]} - ${value[1]}${["price_range", "volume_ratio", "chip_concentration", "winner_rate", "price_vs_chip", "change_pct", "turnover_rate", "amplitude"].includes(key) ? (key === "price_range" ? " 元" : " %") : ""}`;
    }

    if (typeof value === "object" && "bounds" in value) {
      return `${label}：近 ${value.days} 日，${value.bounds[0]} - ${value.bounds[1]}%`;
    }

    if (typeof value === "object" && "direction" in value) {
      const directionText = value.direction === "down" ? "连跌" : "连涨";
      return `${label}：${directionText} ${value.min_days}-${value.max_days} 天`;
    }

    const mapping = {
      above_ma5_ma10: "站上 5/10 日均线",
      near_ma20: "贴近 20 日均线",
      breakout_ma20: "突破 20 日均线",
      breakout_ma60: "突破 60 日均线",
      high_20d: "20 日新高",
      high_60d: "60 日新高",
      low_20d: "20 日新低",
      volume_expand_2d: "连续放量 2 日及以上",
      volume_shrink_2d: "连续缩量 2 日及以上",
    };
    return `${label}：${mapping[value] || value}`;
  }

  function setStrategyConditions(payload, quantifiedConditions) {
    if (!strategyConditions) return;
    const structuredRows = Array.isArray(quantifiedConditions)
      ? quantifiedConditions.filter(Boolean)
      : [];
    const filters = payload?.filters || {};
    const fallbackRows = Object.entries(filters)
      .map(([key, value]) => formatStrategyCondition(key, value))
      .filter(Boolean);
    const rows = structuredRows.length ? structuredRows : fallbackRows;

    strategyConditions.innerHTML = `<h4>量化后的条件</h4>${
      rows.length
        ? rows.map((item) => `<span>${item}</span>`).join("")
        : '<span>这里会展示策略最终量化成的具体筛选条件。</span>'
    }`;
  }

  function applyParsedPayloadToForm(payload) {
    if (!payload) return;

    const setValue = (selector, value) => {
      const node = document.querySelector(selector);
      if (node && value !== undefined && value !== null) {
        node.value = value;
      }
    };

    const setChecked = (selector, value) => {
      const node = document.querySelector(selector);
      if (node) {
        node.checked = Boolean(value);
      }
    };

    setValue("[data-field='screen_depth']", payload.screen_depth);
    setValue("[data-field='market_scope']", payload.market_scope);
    setChecked("[data-field='exclude_new_listing_90d']", payload.exclude_new_listing_90d);

    const filters = payload.filters || {};
    document.querySelectorAll("[data-filter]").forEach((card) => {
      const filterId = card.dataset.filter;
      const value = filters[filterId];
      if (value === undefined || value === null) {
        return;
      }

      const kind = card.dataset.filterKind;
      if (kind === "range" && Array.isArray(value)) {
        const scale = Number(card.dataset.scale || "1");
        const minNode = card.querySelector("[data-bound='min']");
        const maxNode = card.querySelector("[data-bound='max']");
        if (minNode) minNode.value = value[0] / scale;
        if (maxNode) maxNode.value = value[1] / scale;
        return;
      }

      if (kind === "day-range" && value && typeof value === "object") {
        const daysNode = card.querySelector("[data-day-field='days']");
        const minNode = card.querySelector("[data-day-field='min']");
        const maxNode = card.querySelector("[data-day-field='max']");
        if (daysNode) daysNode.value = value.days ?? "";
        if (minNode) minNode.value = value.bounds?.[0] ?? "";
        if (maxNode) maxNode.value = value.bounds?.[1] ?? "";
        return;
      }

      if (kind === "consecutive" && value && typeof value === "object") {
        const directionNode = card.querySelector("[data-consecutive-field='direction']");
        const minNode = card.querySelector("[data-consecutive-field='min']");
        const maxNode = card.querySelector("[data-consecutive-field='max']");
        if (directionNode) directionNode.value = value.direction ?? "up";
        if (minNode) minNode.value = value.min_days ?? "";
        if (maxNode) maxNode.value = value.max_days ?? "";
        return;
      }

      if (kind === "select") {
        const selectNode = card.querySelector("[data-select-value]");
        if (selectNode) {
          selectNode.value = value;
        }
      }
    });

    updateFullOnlyState();
    updateConditionSummary(readFormPayload());
  }

  async function parseStrategyToFilters() {
    const query = strategyQuery?.value?.trim();
    if (!query) {
      showToast("请先输入一句策略描述");
      return;
    }

    const currentPayload = readFormPayload();
    if (strategyLLMStatus) {
      strategyLLMStatus.textContent = "正在解析策略...";
    }

    try {
      const response = await fetch(`${API_BASE}/api/strategy/parse`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          query,
          current_payload: currentPayload,
          detected_strategy_tags: detectStrategyTags(query),
        }),
      });
      const payload = await response.json();
      if (!response.ok) {
        throw new Error(payload.detail || payload.message || `strategy parse failed: ${response.status}`);
      }

      applyParsedPayloadToForm(payload.merged_payload);
      setStrategyNotes(payload.parsed_strategy?.notes, payload.parsed_strategy?.unsupported_intents);
      setStrategyMapping(payload.strategy_mapping_summary);
      setStrategyConditions(payload.merged_payload, payload.quantified_conditions);

      if (strategyLLMStatus) {
        const llmStatus = payload.llm_status || {};
        strategyLLMStatus.textContent = llmStatus.used
          ? `当前使用 ${llmStatus.provider || "LLM"} / ${llmStatus.model || "--"} 解析策略`
          : "当前使用规则版解析，已翻译为可执行筛选条件并回填到面板。";
      }

      showToast("策略已转换成筛选条件，并已回填到筛选面板");
    } catch (error) {
      console.error(error);
      if (strategyLLMStatus) {
        strategyLLMStatus.textContent = "策略解析失败，请调整描述后重试。";
      }
      showToast(error.message || "策略解析失败");
    }
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
    document.querySelector("[data-result-filter-summary]").textContent = summarizePayload(payload).slice(0, 4).join(" / ") || "未启用硬性筛选条件";
    document.querySelector("[data-result-first-round]").textContent = String(responsePayload.first_round_count || 0);
    document.querySelector("[data-result-final-round]").textContent = String(responsePayload.final_result_count || 0);

    const stageMeta = responsePayload.stage_meta || {};
    const sourceMeta = [
      stageMeta.spot_cache_hit ? "Tushare 快照命中缓存" : "Tushare 快照实时拉取",
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
        title: "Tushare 行情",
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
        status: "ok",
        title: "筹码结构",
        text: "已接入日级代理字段：筹码集中度 / 获利盘比例 / 现价相对筹码成本",
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
            { progress: 12, title: "正在拉取实时行情", message: "等待 Tushare 返回市场快照..." },
            { progress: 38, title: "正在执行首轮硬筛", message: "按价格、成交额、换手率与量比进行首轮过滤..." },
            { progress: 66, title: "正在补充历史增强指标", message: "拉取候选股票历史 K 线，计算趋势与强弱信息..." },
            { progress: 88, title: "正在整理候选榜单", message: "增强计算完成，正在生成排序结果..." },
          ]
        : [
            { progress: 18, title: "正在拉取实时行情", message: "等待 Tushare 返回市场快照..." },
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
      const response = await fetch(`${API_BASE}/api/screen/run`, {
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
      const response = await fetch(`${API_BASE}/api/history`);
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
    briefTitle.textContent = payload?.source_label ? `?????? ? ${payload.source_label}` : "??????";
    briefUpdated.textContent = payload?.updated_at ? `?? ${String(payload.updated_at).slice(11, 16) || payload.updated_at}` : "???";

    if (!items.length) {
      briefList.innerHTML = `
        <article>
          <strong>??????</strong>
          <p>??????????????????????????</p>
        </article>
      `;
      return;
    }

    briefList.innerHTML = items
      .map((item) => {
        const footer = [item.source, item.published_at].filter(Boolean).join(" ? ");
        const link = item.url
          ? `<a class="brief-link" href="${item.url}" target="_blank" rel="noreferrer">????</a>`
          : "";
        const bullets = splitNewsSummary(item.summary)
          .map((part) => `<span class="brief-bullet">${part}</span>`)
          .join("");
        return `
          <article>
            <strong>${item.title || "????"}</strong>
            <div class="brief-bullets">${bullets || `<span class="brief-bullet">${item.summary || ""}</span>`}</div>
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
      const response = await fetch(`${API_BASE}/api/news/brief`);
      if (!response.ok) {
        throw new Error(`news failed: ${response.status}`);
      }
      const payload = await response.json();
      renderNewsBrief(payload);
    } catch (error) {
      console.error(error);
      renderNewsBrief({
        source_label: "??????",
        updated_at: "",
        items: [
          {
            title: "????????",
            summary: "AKShare ??????????????????????????",
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

      const strategyParseButton = event.target.closest("[data-strategy-parse]");
      if (strategyParseButton) {
        parseStrategyToFilters();
      }

      const strategyClearButton = event.target.closest("[data-strategy-clear]");
      if (strategyClearButton) {
        if (strategyQuery) strategyQuery.value = "";
        setStrategyNotes([], []);
        setStrategyMapping([]);
        setStrategyConditions({}, []);
        if (strategyLLMStatus) {
          strategyLLMStatus.textContent = "输入一句策略描述，系统会尝试翻译成量化筛选条件。";
        }
        showToast("已清空策略描述");
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
