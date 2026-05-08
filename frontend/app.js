const modeContent = {
  pre: {
    title: "盘前预判",
    summary: "优先观察新闻催化、板块热度与题材扩散，寻找开盘前值得跟踪的候选池。",
    weightTag: "预期判断",
    resultMode: "盘前预判",
    weights: [
      ["高权重", "新闻催化、板块热度、题材扩散度"],
      ["中权重", "资金活跃度、龙头带动、市场情绪"],
      ["加分项", "个股热度与趋势延续性"],
    ],
  },
  post: {
    title: "盘后复盘",
    summary: "优先复核资金流、市场情绪、风格切换与涨停结构，筛出次日仍需跟踪的方向。",
    weightTag: "复盘判断",
    resultMode: "盘后复盘",
    weights: [
      ["高权重", "资金流向、市场情绪、涨停结构与风格切换"],
      ["中权重", "板块热度、龙头带动、题材扩散速度"],
      ["加分项", "个股热度、承接强度、回撤控制"],
    ],
  },
};

function renderMode(mode) {
  const content = modeContent[mode] || modeContent.pre;
  document.querySelector("[data-mode-title]").textContent = content.title;
  document.querySelector("[data-mode-summary]").textContent = content.summary;
  document.querySelector("[data-weight-tag]").textContent = content.weightTag;
  document.querySelector("[data-result-mode]").textContent = content.resultMode;

  document.querySelector("[data-weight-list]").innerHTML = content.weights
    .map(([label, text]) => `<div><span>${label}</span><strong>${text}</strong></div>`)
    .join("");
}

function updateModeButtons(mode) {
  document.querySelectorAll("[data-mode-button]").forEach((button) => {
    button.classList.toggle("active", button.dataset.modeButton === mode);
  });
}

function jumpTo(id) {
  document.querySelector(`#${id}`)?.scrollIntoView({ behavior: "smooth", block: "start" });
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
