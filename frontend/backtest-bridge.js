(function () {
  const API_BASE = window.ASHARE_API_BASE || "";

  const state = {
    result: null,
    history: [],
    strategyPayload: null,
    strategyMeta: null,
    compareResult: null,
  };

  function qs(selector) {
    return document.querySelector(selector);
  }

  function qsa(selector) {
    return Array.from(document.querySelectorAll(selector));
  }

  function showToast(message) {
    const toast = qs(".toast");
    if (!toast) return;
    toast.textContent = message;
    toast.classList.add("show");
    window.setTimeout(() => toast.classList.remove("show"), 2400);
  }

  function readNumber(selector, fallback) {
    const raw = qs(selector)?.value ?? "";
    const value = Number(raw);
    return Number.isFinite(value) ? value : fallback;
  }

  function readOptionalNumber(input) {
    const raw = input?.value ?? "";
    if (String(raw).trim() === "") return null;
    const value = Number(raw);
    return Number.isFinite(value) ? value : null;
  }

  function formatPercent(value) {
    return value === null || value === undefined ? "--" : `${value}%`;
  }

  function toUserFriendlyBacktestError(message) {
    const text = String(message || "").trim();
    if (!text) return "回测失败，请稍后重试。";
    if (text.includes("交易日") || text.includes("历史窗口")) {
      return "当前窗口下可用于回测的有效交易日不足。建议先把历史窗口调到 5 年，或减少高周期条件后再试。";
    }
    if (text.includes("没有形成") || text.includes("回测样本")) {
      return "系统已经尝试完成回测，但没有形成有效交易样本。建议放宽条件、增加 top N，或缩短持有周期。";
    }
    return text;
  }

  function isMeaningfulValue(value) {
    if (value === null || value === undefined || value === "" || value === false) return false;
    if (Array.isArray(value)) {
      if (value.length !== 2) return false;
      const [min, max] = value;
      return Number.isFinite(min) && Number.isFinite(max) && !(min === 0 && max === 0);
    }
    if (typeof value === "object" && value?.bounds) {
      const [min, max] = value.bounds || [];
      return Number.isFinite(value.days) && Number.isFinite(min) && Number.isFinite(max) && !(min === 0 && max === 0);
    }
    if (typeof value === "object" && value?.direction) {
      return Number.isFinite(value.min_days) && Number.isFinite(value.max_days);
    }
    return true;
  }

  function hasAnyEffectiveFilters(payload) {
    return Object.values(payload?.filters || {}).some((value) => isMeaningfulValue(value));
  }

  function formatFilterLine(key, value) {
    if (!isMeaningfulValue(value)) return null;
    if (Array.isArray(value)) return `${key}: ${value[0]} ~ ${value[1]}`;
    if (typeof value === "object" && value?.bounds) return `${key}: 近 ${value.days} 日 ${value.bounds[0]} ~ ${value.bounds[1]}`;
    if (typeof value === "object" && value?.direction) {
      return `${key}: ${value.direction === "down" ? "连续下跌" : "连续上涨"} ${value.min_days} ~ ${value.max_days} 天`;
    }
    return `${key}: ${value}`;
  }

  function patchStaticBacktestCopy() {
    const workbench = qs("#backtest-workbench");
    const results = qs("#backtest-results");
    if (workbench) {
      workbench.querySelector(".eyebrow")?.replaceChildren(document.createTextNode("Backtest"));
      const title = workbench.querySelector(".section-head h2");
      if (title) title.textContent = "策略回测工作台";
      const buttons = workbench.querySelectorAll(".section-head .button-row button");
      if (buttons[0]) buttons[0].textContent = "复用筛选条件";
      if (buttons[1]) buttons[1].textContent = "开始回测";
      const panelHeads = workbench.querySelectorAll(".panel-head h3");
      if (panelHeads[0]) panelHeads[0].textContent = "回测策略输入";
      if (panelHeads[1]) panelHeads[1].textContent = "回测参数";
      const strategyBox = workbench.querySelector(".backtest-strategy-box");
      if (strategyBox) {
        const spans = strategyBox.querySelectorAll("span");
        if (spans[0]) spans[0].textContent = "自然语言策略";
        const strong = strategyBox.querySelector("strong");
        if (strong) strong.textContent = "例如：反转策略、缩量回调后放量突破、近 20 日新高且量比放大的票。";
        const textarea = strategyBox.querySelector("textarea");
        if (textarea) textarea.placeholder = "输入一句回测策略，系统会先翻译成量化条件，再拿历史数据去跑回测。";
        const actionButtons = strategyBox.querySelectorAll(".button-row button");
        if (actionButtons[0]) actionButtons[0].textContent = "清空策略";
        if (actionButtons[1]) actionButtons[1].textContent = "生成回测条件";
        if (actionButtons[2]) actionButtons[2].textContent = "去盘前页精调条件";
      }
      const labels = workbench.querySelectorAll(".form-grid label > span");
      if (labels[0]) labels[0].textContent = "历史窗口";
      if (labels[1]) labels[1].textContent = "持有周期";
      if (labels[2]) labels[2].textContent = "每轮取前 N 只";
      const fieldHelp = workbench.querySelector(".field-help");
      if (fieldHelp) fieldHelp.textContent = "意思是：某天满足策略后，默认下一交易日买入，再持有 1 / 3 / 5 个交易日后卖出。";
      const historyYears = qs("[data-backtest-field='history_years']");
      if (historyYears) {
        const options = historyYears.querySelectorAll("option");
        if (options[0]) options[0].textContent = "1 年";
        if (options[1]) options[1].textContent = "3 年";
        if (options[2]) options[2].textContent = "5 年";
      }
      const holdingDays = qs("[data-backtest-field='holding_days']");
      if (holdingDays) {
        const options = holdingDays.querySelectorAll("option");
        if (options[0]) options[0].textContent = "1 天";
        if (options[1]) options[1].textContent = "3 天";
        if (options[2]) options[2].textContent = "5 天";
      }
    }
    if (results) {
      results.querySelector(".eyebrow")?.replaceChildren(document.createTextNode("Backtest Result"));
      const title = results.querySelector(".section-head h2");
      if (title) title.textContent = "回测结果";
      const buttons = results.querySelectorAll(".section-head .button-row button");
      if (buttons[0]) buttons[0].textContent = "刷新记录";
      if (buttons[1]) buttons[1].textContent = "返回参数区";
      const heads = results.querySelectorAll(".panel-head h3");
      if (heads[0]) heads[0].textContent = "策略与执行信息";
      if (heads[1]) heads[1].textContent = "收益曲线预览";
      if (heads[2]) heads[2].textContent = "年度收益";
      if (heads[3]) heads[3].textContent = "样本交易";
    }
  }

  function readCurrentScreenPayload() {
    const screenDepth = qs("[data-field='screen_depth']")?.value || "full";
    const filters = {};
    qsa("[data-filter]").forEach((card) => {
      const filterId = card.dataset.filter;
      if (!filterId) return;
      if (card.dataset.fullOnly === "true" && screenDepth !== "full") {
        filters[filterId] = null;
        return;
      }
      const kind = card.dataset.filterKind;
      if (kind === "range") {
        const scale = Number(card.dataset.scale || "1");
        const min = readOptionalNumber(card.querySelector("[data-bound='min']"));
        const max = readOptionalNumber(card.querySelector("[data-bound='max']"));
        filters[filterId] = min !== null && max !== null ? [min * scale, max * scale] : null;
        return;
      }
      if (kind === "day-range") {
        const days = readOptionalNumber(card.querySelector("[data-day-field='days']"));
        const min = readOptionalNumber(card.querySelector("[data-day-field='min']"));
        const max = readOptionalNumber(card.querySelector("[data-day-field='max']"));
        filters[filterId] = days !== null && min !== null && max !== null ? { days, bounds: [min, max] } : null;
        return;
      }
      if (kind === "consecutive") {
        const direction = card.querySelector("[data-consecutive-field='direction']")?.value || "up";
        const minDays = readOptionalNumber(card.querySelector("[data-consecutive-field='min']"));
        const maxDays = readOptionalNumber(card.querySelector("[data-consecutive-field='max']"));
        filters[filterId] = minDays !== null && maxDays !== null ? { direction, min_days: minDays, max_days: maxDays } : null;
        return;
      }
      if (kind === "select") {
        const value = card.querySelector("[data-select-value]")?.value || null;
        filters[filterId] = value === "none" ? null : value;
      }
    });
    return {
      mode: "pre",
      screen_depth: screenDepth,
      market_scope: qs("[data-field='market_scope']")?.value || "沪深主板 + 创业板",
      exclude_st: qs("[data-field='exclude_st']")?.checked ?? true,
      exclude_paused: qs("[data-field='exclude_paused']")?.checked ?? true,
      exclude_new_listing_90d: qs("[data-field='exclude_new_listing_90d']")?.checked ?? true,
      exclude_bse: qs("[data-field='exclude_bse']")?.checked ?? true,
      filters,
    };
  }

  function getEffectiveScreenPayload() {
    return state.strategyPayload || readCurrentScreenPayload();
  }

  function ensureExecutionModeField() {
    if (qs("[data-backtest-field='execution_mode']")) return;
    const formGrid = qs("#backtest-workbench .form-grid");
    if (!formGrid) return;
    const label = document.createElement("label");
    label.innerHTML = `
      <span>执行模式</span>
      <select data-backtest-field="execution_mode">
        <option value="fast" selected>快速验证</option>
        <option value="full">完整回测</option>
      </select>
      <small class="field-help">快速验证只抽最近若干轮样本，先判断策略是否大致可用；完整回测才跑完整历史窗口。</small>
    `;
    formGrid.appendChild(label);
  }

  function ensureComparePanel() {
    if (qs("[data-backtest-compare-list]")) return;
    const strategyPanel = qs("#backtest-workbench .panel");
    if (!strategyPanel || !strategyPanel.parentElement) return;
    const panel = document.createElement("section");
    panel.className = "panel";
    panel.innerHTML = `
      <div class="panel-head">
        <h3>LLM 多策略对比</h3>
        <span class="panel-tag" data-backtest-compare-status>把一句策略自动扩成 3 个量化版本，再并排比较。</span>
      </div>
      <div class="postclose-llm-hint backtest-strategy-box">
        <span>对比说明</span>
        <strong>适合先看“基准版 / 放宽版 / 收紧版”哪一类样本更多、回撤更稳，再决定后续怎么优化参数。</strong>
        <div class="button-row">
          <button class="secondary-button" type="button" data-backtest-compare-run>生成并对比</button>
        </div>
        <div class="brief-list" data-backtest-compare-list>
          <article class="brief-list-item">
            <strong>暂无策略对比结果</strong>
            <p>先在上面输入一句回测策略，再生成三组对比结果。</p>
          </article>
        </div>
      </div>
    `;
    strategyPanel.insertAdjacentElement("afterend", panel);
  }

  function renderStrategySummary(payload, sourceText) {
    const root = qs("[data-backtest-strategy-summary]");
    if (!root) return;
    const filterRows = Object.entries(payload?.filters || {})
      .map(([key, value]) => formatFilterLine(key, value))
      .filter(Boolean);
    root.innerHTML = `
      <h4>当前回测条件</h4>
      <span>${sourceText}</span>
      ${filterRows.length ? filterRows.map((item) => `<span>${item}</span>`).join("") : "<span>当前没有有效的量化条件。你可以先生成一句回测策略，或去盘前页手动设置筛选条件。</span>"}
    `;
  }

  function renderStrategyExplanation(payload, meta) {
    const root = qs("[data-backtest-strategy-explanation]");
    if (!root) return;
    const notes = Array.isArray(meta?.notes) ? meta.notes.filter(Boolean) : [];
    const mappings = Array.isArray(meta?.mapping) ? meta.mapping.filter(Boolean) : [];
    const quantified = Array.isArray(meta?.quantified) ? meta.quantified.filter(Boolean) : [];
    const topN = readNumber("[data-backtest-field='top_n']", 10);
    const holdingDays = readNumber("[data-backtest-field='holding_days']", 3);
    const historyYears = readNumber("[data-backtest-field='history_years']", 3);
    const executionMode = qs("[data-backtest-field='execution_mode']")?.value || "fast";
    const modeText = executionMode === "full" ? "完整回测" : "快速验证";
    root.innerHTML = `
      <h4>策略如何执行</h4>
      <span>系统会先把自然语言翻译成量化条件，再在最近 ${historyYears} 年的历史窗口里筛选候选股。</span>
      <span>当前执行模式是 ${modeText}。快速验证优先先出结果；完整回测才是正式完整历史口径。</span>
      <span>每个选股日默认取前 ${topN} 只股票，下一交易日开盘视作买入，再持有 ${holdingDays} 个交易日后卖出。</span>
      ${quantified.length ? quantified.map((item) => `<span>${item}</span>`).join("") : "<span>当前还没有生成明确的量化执行条件。</span>"}
      ${mappings.length ? mappings.map((item) => `<span>${item}</span>`).join("") : ""}
      ${notes.length ? notes.map((item) => `<span>${item}</span>`).join("") : ""}
    `;
  }

  function renderSummary(result) {
    const summary = result?.summary || {};
    const windowMeta = result?.window || {};
    const execution = result?.execution || {};
    const isFastMode = execution.execution_mode !== "full";
    const metricsRoot = qs("[data-backtest-metrics]");
    if (!metricsRoot) return;
    metricsRoot.innerHTML = `
      <article class="metric-card">
        <span>累计收益</span>
        <strong>${formatPercent(summary.cumulative_return_pct)}</strong>
        <p>${isFastMode ? "快速验证口径下的抽样累计收益，只用于先看策略有没有基本可行性。" : "完整回测窗口内的累计收益表现。"}</p>
      </article>
      <article class="metric-card">
        <span>${isFastMode ? "样本跨度" : "年化收益"}</span>
        <strong>${isFastMode ? `${windowMeta.evaluated_span_days ?? "--"} 天` : formatPercent(summary.annual_return_pct)}</strong>
        <p>${isFastMode ? "快速验证不强调年化值，先看这次抽样覆盖时间、收益和回撤是否值得继续跑完整回测。" : "按完整历史跨度折算后的正式年化收益。"}</p>
      </article>
      <article class="metric-card warning">
        <span>最大回撤</span>
        <strong>${formatPercent(summary.max_drawdown_pct)}</strong>
        <p>${isFastMode ? "快速验证只覆盖少量抽样周期，回撤值也是参考值。" : "用于衡量策略在最差阶段的风险承受能力。"}</p>
      </article>
      <article class="metric-card">
        <span>胜率 / 盈亏比</span>
        <strong>${formatPercent(summary.win_rate_pct)} / ${summary.profit_loss_ratio ?? "--"}</strong>
        <p>${isFastMode ? "先用来看规则有没有正向迹象，不能直接当成正式统计结论。" : "辅助判断策略稳定性和赚赔结构。"}</p>
      </article>
    `;
  }

  function renderMeta(result) {
    const root = qs("[data-backtest-meta]");
    if (!root) return;
    const windowMeta = result?.window || {};
    const execution = result?.execution || {};
    const summaryLines = (result?.strategy?.summary || []).slice(0, 12);
    const executionModeText = execution.execution_mode === "full" ? "完整回测" : "快速验证";
    const scopeText = execution.evaluation_scope === "sampled_recent_cycles" ? "最近抽样周期" : "完整历史窗口";
    root.innerHTML = `
      <div class="condition-list">
        <h4>策略摘要</h4>
        ${summaryLines.length ? summaryLines.map((item) => `<span>${item}</span>`).join("") : "<span>暂无</span>"}
      </div>
      <div class="backtest-meta-grid">
        <article><span>历史窗口</span><strong>${windowMeta.start_date || "--"} 至 ${windowMeta.end_date || "--"}</strong></article>
        <article><span>实际评估区间</span><strong>${windowMeta.evaluated_start_date || "--"} 至 ${windowMeta.evaluated_end_date || "--"}</strong></article>
        <article><span>执行模式</span><strong>${executionModeText}</strong></article>
        <article><span>评估范围</span><strong>${scopeText}</strong></article>
        <article><span>买入规则</span><strong>${execution.buy_rule || "--"}</strong></article>
        <article><span>卖出规则</span><strong>${execution.sell_rule || "--"}</strong></article>
      </div>
    `;
  }

  function renderWarnings(result) {
    const root = qs("[data-backtest-meta]");
    if (!root) return;
    const warnings = Array.isArray(result?.warnings) ? result.warnings.filter(Boolean) : [];
    if (!warnings.length) return;
    const block = document.createElement("div");
    block.className = "condition-list";
    block.innerHTML = `
      <h4>系统建议</h4>
      ${warnings.map((item) => `<span>${item}</span>`).join("")}
    `;
    root.appendChild(block);
  }

  function renderCurve(result) {
    const root = qs("[data-backtest-curve]");
    if (!root) return;
    const sparkline = result?.sparkline || "";
    const curve = result?.equity_curve || [];
    const last = curve[curve.length - 1];
    const debug = result?.debug || {};
    const execution = result?.execution || {};
    const isFastMode = execution.execution_mode !== "full";
    root.innerHTML = `
      <article class="backtest-curve-card">
        <span>${isFastMode ? "抽样收益轨迹" : "收益曲线预览"}</span>
        <strong class="backtest-sparkline">${sparkline || "--"}</strong>
        <p>${isFastMode ? "当前是快速验证模式，只展示最近抽样周期的收益轨迹，不代表完整三年净值曲线。" : "首版先用字符曲线做快速预览，后续再接正式图表。"}</p>
        <em>${last ? `最新净值 ${last.equity}` : "暂无净值数据"}</em>
        <em>耗时 ${debug.total_elapsed_ms ?? "--"} ms / 抽取周期 ${debug.selection_cycles_used ?? "--"} / ${debug.selection_cycles_total ?? "--"}</em>
      </article>
    `;
  }

  function renderYearly(result) {
    const root = qs("[data-backtest-yearly]");
    if (!root) return;
    const rows = Array.isArray(result?.yearly_returns) ? result.yearly_returns : [];
    const execution = result?.execution || {};
    const isFastMode = execution.execution_mode !== "full";
    if (isFastMode) {
      root.innerHTML = `
        <div class="source-row">
          <strong>快速验证说明</strong>
          <em>这里只显示被抽样命中的年份，所以 3 年窗口里只出现某一年是正常的，不代表历史窗口没生效。</em>
        </div>
        ${rows.length ? rows.map((item) => `<div class="source-row"><strong>${item.year}</strong><em>${item.return_pct}%</em></div>`).join("") : '<div class="source-row"><strong>暂无年度样本</strong><em>请先执行快速验证或切换完整回测</em></div>'}
      `;
      return;
    }
    root.innerHTML = rows.length
      ? rows.map((item) => `<div class="source-row"><strong>${item.year}</strong><em>${item.return_pct}%</em></div>`).join("")
      : '<div class="source-row"><strong>暂无年度拆分</strong><em>请先执行回测</em></div>';
  }

  function renderTrades(result) {
    const root = qs("[data-backtest-trades]");
    if (!root) return;
    const rows = Array.isArray(result?.trade_samples) ? result.trade_samples : [];
    root.innerHTML = rows.length
      ? rows.map((item) => `
          <article class="brief-list-item">
            <strong>${item.stock} (${item.code})</strong>
            <p>选中 ${item.select_date}，买入 ${item.buy_date}，卖出 ${item.sell_date}，收益 ${item.return_pct}% ，持有 ${item.holding_days} 天。</p>
          </article>
        `).join("")
      : '<article class="brief-list-item"><strong>暂无样本交易</strong><p>执行回测后这里会展示最近的交易样本。</p></article>';
  }

  function renderBacktestHistory() {
    const root = qs("[data-backtest-history]");
    if (!root) return;
    root.innerHTML = state.history.length
      ? state.history.map((item) => `
          <article class="brief-list-item">
            <strong>${item.generated_at || "--"}</strong>
            <p>${item.history_years || "--"} 年 / ${item.execution_mode === "full" ? "完整回测" : "快速验证"} / 持有 ${item.holding_days || "--"} 天 / 前 ${item.top_n || "--"} 只 / 收益 ${item.cumulative_return_pct ?? "--"}%</p>
          </article>
        `).join("")
      : '<article class="brief-list-item"><strong>暂无回测记录</strong><p>执行一次回测后，这里会显示本地保存记录。</p></article>';
  }

  function renderCompareResult(payload) {
    const root = qs("[data-backtest-compare-list]");
    const status = qs("[data-backtest-compare-status]");
    if (!root) return;
    const items = Array.isArray(payload?.comparison) ? payload.comparison : [];
    if (status) {
      status.textContent = items.length
        ? `已生成 ${items.length} 组策略对比，当前推荐：${payload?.recommendation?.label || "--"}`
        : "暂无策略对比结果";
    }
    root.innerHTML = items.length
      ? items.map((item, index) => {
          const summary = item.summary || {};
          return `
            <article class="brief-list-item">
              <strong>${index + 1}. ${item.label}</strong>
              <p>${item.description}</p>
              <p>累计收益 ${summary.cumulative_return_pct ?? "--"}% / 最大回撤 ${summary.max_drawdown_pct ?? "--"}% / 样本交易 ${summary.trade_count ?? "--"} / 有效周期 ${summary.cycle_count ?? "--"}</p>
            </article>
          `;
        }).join("")
      : '<article class="brief-list-item"><strong>暂无策略对比结果</strong><p>先在上面输入一句回测策略，再生成三组对比结果。</p></article>';
  }

  function buildPayload() {
    return {
      screen_payload: getEffectiveScreenPayload(),
      history_years: readNumber("[data-backtest-field='history_years']", 3),
      holding_days: readNumber("[data-backtest-field='holding_days']", 3),
      top_n: readNumber("[data-backtest-field='top_n']", 10),
      execution_mode: qs("[data-backtest-field='execution_mode']")?.value || "fast",
      adj_type: "qfq",
      costs: {
        buy_fee: 0.0003,
        sell_fee: 0.0003,
        sell_tax: 0.001,
        slippage: 0.0005,
      },
      constraints: {
        skip_one_word_limit_up_buy: true,
        skip_limit_down_sell: true,
        skip_suspended: true,
        skip_st: true,
        skip_new_listing: true,
      },
    };
  }

  async function parseBacktestStrategy() {
    const query = qs("[data-backtest-strategy-query]")?.value?.trim();
    const status = qs("[data-backtest-strategy-status]");
    if (!query) {
      showToast("请先输入一句回测策略");
      return;
    }
    if (status) status.textContent = "正在生成回测条件...";
    try {
      const response = await fetch(`${API_BASE}/api/strategy/parse`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          query,
          current_payload: readCurrentScreenPayload(),
          detected_strategy_tags: [],
        }),
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail || payload.message || `strategy parse failed: ${response.status}`);
      state.strategyPayload = payload.merged_payload || null;
      state.strategyMeta = {
        notes: payload.parsed_strategy?.notes || [],
        mapping: payload.strategy_mapping_summary || [],
        quantified: payload.quantified_conditions || [],
      };
      if (!hasAnyEffectiveFilters(state.strategyPayload)) {
        renderStrategySummary(state.strategyPayload, "这次策略解析没有生成有效量化条件，请换一种更具体的说法，或直接去盘前页手动设置条件。");
        renderStrategyExplanation(state.strategyPayload, state.strategyMeta);
        if (status) status.textContent = "未解析出有效回测条件，请补充更具体的策略描述。";
        showToast("这次没有解析出有效回测条件");
        return;
      }
      renderStrategySummary(
        state.strategyPayload,
        payload.llm_status?.used
          ? `已使用 ${payload.llm_status.provider || "LLM"} / ${payload.llm_status.model || "--"} 生成回测条件`
          : "已使用规则解析生成回测条件",
      );
      renderStrategyExplanation(state.strategyPayload, state.strategyMeta);
      if (status) status.textContent = "回测策略条件已生成，可以直接开始回测。";
      showToast("回测策略已生成");
    } catch (error) {
      console.error(error);
      if (status) status.textContent = "策略翻译失败，请调整描述后重试。";
      showToast(error.message || "回测策略解析失败");
    }
  }

  function clearBacktestStrategy() {
    const input = qs("[data-backtest-strategy-query]");
    if (input) input.value = "";
    state.strategyPayload = null;
    state.strategyMeta = null;
    renderStrategySummary(readCurrentScreenPayload(), "当前未单独设置回测策略；默认复用盘前页筛选条件。");
    renderStrategyExplanation(null, null);
    const status = qs("[data-backtest-strategy-status]");
    if (status) status.textContent = "默认可直接复用盘前筛选条件，也可在这里单独输入回测策略。";
  }

  async function refreshHistory() {
    try {
      const response = await fetch(`${API_BASE}/api/backtest/history`);
      const payload = await response.json();
      state.history = Array.isArray(payload.items) ? payload.items : [];
      renderBacktestHistory();
    } catch (error) {
      console.error(error);
    }
  }

  async function compareStrategies() {
    const query = qs("[data-backtest-strategy-query]")?.value?.trim();
    const status = qs("[data-backtest-compare-status]");
    if (!query) {
      showToast("请先输入一句回测策略");
      return;
    }
    if (status) status.textContent = "正在生成并回测多组策略，请稍候...";
    try {
      const response = await fetch(`${API_BASE}/api/backtest/compare`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          query,
          current_payload: readCurrentScreenPayload(),
          history_years: readNumber("[data-backtest-field='history_years']", 3),
          holding_days: readNumber("[data-backtest-field='holding_days']", 3),
          top_n: readNumber("[data-backtest-field='top_n']", 10),
          execution_mode: qs("[data-backtest-field='execution_mode']")?.value || "fast",
        }),
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail || payload.message || `compare failed: ${response.status}`);
      state.compareResult = payload;
      renderCompareResult(payload);
      showToast("策略对比已生成");
    } catch (error) {
      console.error(error);
      if (status) status.textContent = error.message || "策略对比失败";
      showToast(error.message || "策略对比失败");
    }
  }

  async function runBacktest() {
    const status = qs("[data-backtest-status]");
    const executionMode = qs("[data-backtest-field='execution_mode']")?.value || "fast";
    if (status) {
      status.textContent =
        executionMode === "full"
          ? "正在执行完整回测，这一步会明显更慢，请耐心等待..."
          : "正在执行快速验证，优先先跑出可用结果...";
    }
    try {
      const response = await fetch(`${API_BASE}/api/backtest/run`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(buildPayload()),
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail || payload.message || `backtest failed: ${response.status}`);
      state.result = payload;
      renderSummary(payload);
      renderMeta(payload);
      renderWarnings(payload);
      renderCurve(payload);
      renderYearly(payload);
      renderTrades(payload);
      await refreshHistory();
      if (status) status.textContent = "回测完成，结果已更新。";
      showToast("回测完成");
      qs("#backtest-results")?.scrollIntoView({ behavior: "smooth", block: "start" });
    } catch (error) {
      console.error(error);
      const friendly = toUserFriendlyBacktestError(error.message);
      if (status) status.textContent = friendly;
      showToast(friendly);
    }
  }

  document.addEventListener("click", (event) => {
    if (event.target.closest("[data-run-backtest]")) runBacktest();
    if (event.target.closest("[data-refresh-backtest-history]")) refreshHistory();
    if (event.target.closest("[data-backtest-strategy-parse]")) parseBacktestStrategy();
    if (event.target.closest("[data-backtest-strategy-clear]")) clearBacktestStrategy();
    if (event.target.closest("[data-backtest-compare-run]")) compareStrategies();
  }, true);

  document.addEventListener("change", (event) => {
    if (event.target.matches("[data-backtest-field='execution_mode'], [data-backtest-field='history_years'], [data-backtest-field='holding_days'], [data-backtest-field='top_n']")) {
      renderStrategyExplanation(state.strategyPayload, state.strategyMeta);
    }
  });

  document.addEventListener("ashare:mode-change", (event) => {
    if (event.detail?.mode !== "backtest") return;
    const status = qs("[data-backtest-status]");
    if (status && !state.result) {
      status.textContent = "读取当前筛选条件后可直接执行历史回测。";
    }
  });

  patchStaticBacktestCopy();
  ensureExecutionModeField();
  ensureComparePanel();
  renderStrategySummary(readCurrentScreenPayload(), "当前未单独设置回测策略；默认复用盘前页筛选条件。");
  renderStrategyExplanation(null, null);
  refreshHistory();
})();
