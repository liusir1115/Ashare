const modeContent = {
  pre: {
    title: "盘前预判",
    summary: "优先观察新闻催化、板块热度与题材扩散，寻找开盘前值得跟踪的候选池。",
    weightTag: "预期判断",
    resultMode: "盘前预判",
    weights: [
      ["高权重", "新闻催化、板块热度、题材扩散速度"],
      ["中权重", "资金活跃度、龙头带动、市场情绪"],
      ["加分项", "个股热度与趋势延续性"],
    ],
  },
  post: {
    title: "盘后复盘",
    summary: "优先复核资金流、市场情绪、风格切换与涨停结构，沉淀出次日仍需跟踪的方向。",
    weightTag: "复盘判断",
    resultMode: "盘后复盘",
    weights: [
      ["高权重", "资金流向、市场情绪、涨停结构与风格切换"],
      ["中权重", "板块热度、龙头带动、题材扩散速度"],
      ["加分项", "个股热度、承接强度、回撤控制"],
    ],
  },
};

modeContent.backtest = {
  title: "策略回测",
  summary: "用真实历史日线验证量化条件在过去窗口里的收益、回撤和稳定性。",
  weightTag: "历史验证",
  resultMode: "策略回测",
  weights: [
    ["高权重", "累计收益、最大回撤、年化收益"],
    ["中权重", "胜率、盈亏比、交易次数"],
    ["加分项", "不同参数下的稳定性和可交易性"],
  ],
};

window.ASHARE_API_BASE = window.location.protocol === "file:" ? "http://127.0.0.1:5000" : "";

function qs(selector) {
  return document.querySelector(selector);
}

function qsa(selector) {
  return Array.from(document.querySelectorAll(selector));
}

function ensurePostcloseBridgeLoaded() {
  if (document.querySelector("script[data-postclose-bridge]")) {
    return;
  }

  const script = document.createElement("script");
  script.src = "./postclose-bridge.js";
  script.dataset.postcloseBridge = "true";
  document.body.appendChild(script);
}

function ensureBacktestBridgeLoaded() {
  if (document.querySelector("script[data-backtest-bridge]")) {
    return;
  }

  const script = document.createElement("script");
  script.src = "./backtest-bridge.js";
  script.dataset.backtestBridge = "true";
  document.body.appendChild(script);
}

function renderMode(mode) {
  const content = modeContent[mode] || modeContent.pre;

  qs("[data-mode-title]").textContent = content.title;
  qs("[data-mode-summary]").textContent = content.summary;
  qs("[data-weight-tag]").textContent = content.weightTag;
  qs("[data-result-mode]").textContent = content.resultMode;

  qs("[data-weight-list]").innerHTML = content.weights
    .map(([label, text]) => `<div><span>${label}</span><strong>${text}</strong></div>`)
    .join("");

  qsa("[data-mode-panel]").forEach((node) => {
    node.classList.toggle("is-hidden", node.dataset.modePanel !== mode);
  });

  qsa("[data-mode-scope]").forEach((node) => {
    const scope = node.dataset.modeScope || "both";
    const shouldShow = scope === "both" || scope === mode;
    node.classList.toggle("is-hidden", !shouldShow);
  });
}

function updateModeButtons(mode) {
  qsa("[data-mode-button]").forEach((button) => {
    button.classList.toggle("active", button.dataset.modeButton === mode);
  });
}

function ensureBacktestModeButton() {
  const segmented = document.querySelector(".segmented");
  if (!segmented || document.querySelector("[data-mode-button='backtest']")) {
    return;
  }

  const button = document.createElement("button");
  button.className = "segment";
  button.type = "button";
  button.dataset.modeButton = "backtest";
  button.textContent = "回测";
  segmented.appendChild(button);
}

function jumpTo(id) {
  qs(`#${id}`)?.scrollIntoView({ behavior: "smooth", block: "start" });
}

document.addEventListener("click", (event) => {
  const modeButton = event.target.closest("[data-mode-button]");
  if (modeButton) {
    const mode = modeButton.dataset.modeButton || "pre";
    updateModeButtons(mode);
    renderMode(mode);
    document.dispatchEvent(new CustomEvent("ashare:mode-change", { detail: { mode } }));
  }

  const jumpButton = event.target.closest("[data-jump]");
  if (jumpButton) {
    jumpTo(jumpButton.dataset.jump);
  }

  const reportToggleButton = event.target.closest("[data-toggle-report]");
  if (reportToggleButton) {
    const targetId = reportToggleButton.dataset.target;
    const target = targetId ? document.getElementById(targetId) : null;
    if (target) {
      const willShow = target.classList.contains("is-hidden");
      target.classList.toggle("is-hidden", !willShow);
      reportToggleButton.textContent = willShow ? "收起完整简报" : "查看完整简报";
      if (willShow) {
        target.scrollIntoView({ behavior: "smooth", block: "start" });
      }
    }
  }

  const modeAwareJumpButton = event.target.closest("[data-jump-target]");
  if (modeAwareJumpButton) {
    const activeMode = qs("[data-mode-button].active")?.dataset.modeButton || "pre";
    const target =
      activeMode === "post"
        ? modeAwareJumpButton.dataset.jumpPost
        : activeMode === "backtest"
          ? modeAwareJumpButton.dataset.jumpBacktest
          : modeAwareJumpButton.dataset.jumpPre;
    if (target) {
      jumpTo(target);
    }
  }

  if (event.target.closest("[data-close-drawer]")) {
    document.body.classList.remove("drawer-open");
  }
});

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") {
    document.body.classList.remove("drawer-open");
  }
});

renderMode("pre");
updateModeButtons("pre");
ensurePostcloseBridgeLoaded();
ensureBacktestBridgeLoaded();
