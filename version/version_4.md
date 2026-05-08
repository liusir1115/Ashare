# Version 4 新闻简报接入开发记录

## 版本定位

Version 4 在 Version 3 的结构化筛选与前后端联调基础上，补全工作台里的“简报”板块，让页面不再只展示静态说明，而是直接读取 AKShare 的真实新闻接口结果。

这一版优先解决的是“同日重点新闻如何稳定展示给前端”这个问题，因此不继续推进数据库、行业映射和更细的盘前 / 盘后评分差异，而是把新闻数据单独抽成一个可复用的后端接口，并明确让它脱离模式切换逻辑。

## 已确认设计方向

- 简报板块展示“同一日的重点新闻”，不区分盘前新闻、盘后新闻。
- 盘前 / 盘后模式切换仍影响策略权重文案，但不再覆盖新闻区内容。
- 新闻数据优先使用 AKShare 的财联社重点电报接口。
- 如果当日重点电报不可用或无返回，则降级使用东方财富财经早餐接口。
- 新闻区只负责展示，不把新闻条目直接参与当前版本的选股评分。

## Version 4 包含内容

### 审查并确认 AKShare 新闻接口
- 审查了 AKShare 官方文档与本地安装源码中的新闻接口实现。
- 当前确认可用且与本项目相关的接口包括：
  - `stock_info_global_cls(symbol="重点")`：财联社重点电报
  - `stock_info_cjzc_em()`：东方财富财经早餐
  - `stock_info_global_sina()`：新浪 7x24 快讯
- 最终用于工作台简报的优先级为：
  1. 财联社重点电报
  2. 东方财富财经早餐降级兜底

### 后端新增新闻简报接口
- 更新 [service.py](D:/学习工作区/Ashare/akshare_backend/service.py)
- 新增：
  - `split_breakfast_summary()`：将财经早餐长摘要拆成多条要点
  - `fetch_cls_focus_brief()`：获取当日财联社重点电报
  - `fetch_eastmoney_breakfast_brief()`：获取东方财富财经早餐并拆分要点
  - `get_market_news_brief()`：统一新闻简报服务入口
- 新增新闻缓存：
  - `NEWS_CACHE`
  - `NEWS_CACHE_TTL_SECONDS = 600`
- 返回结构包含：
  - `status`
  - `brief_date`
  - `source`
  - `source_label`
  - `updated_at`
  - `generated_at`
  - `items`
  - `errors`

### 后端路由接入
- 更新 [app.py](D:/学习工作区/Ashare/akshare_backend/app.py)
- 新增接口：
  - `/api/news/brief`
- 支持：
  - 默认读取缓存
  - `?refresh=1` 强制刷新

### 前端简报板块改为真实数据渲染
- 更新 [index.html](D:/学习工作区/Ashare/frontend/index.html)
- 将简报区默认标题改为“今日重点新闻”
- 页面初始状态显示“正在拉取新闻简报”的占位内容

- 更新 [app.js](D:/学习工作区/Ashare/frontend/app.js)
- 将新闻区从盘前 / 盘后模式文案中剥离
- 模式切换现在只负责：
  - 当前模式标题
  - 模式摘要
  - 权重侧重
  - 结果模式标记

- 更新 [api-bridge.js](D:/学习工作区/Ashare/frontend/api-bridge.js)
- 新增：
  - `renderNewsBrief()`
  - `refreshNewsBrief()`
- 页面加载时自动调用 `/api/news/brief`
- 简报区会展示：
  - 新闻标题
  - 摘要
  - 来源
  - 发布时间
  - 可用时的原文链接

- 更新 [styles.css](D:/学习工作区/Ashare/frontend/styles.css)
- 新增新闻条目元信息样式：
  - `brief-meta`
  - `brief-link`

## Version 4 不包含内容

- 新闻内容参与选股打分
- 新闻情绪量化
- 新闻去重与主题聚类
- 新闻数据库落盘
- 新闻检索历史页
- 盘前 / 盘后差异化新闻源策略
- 人工编辑新闻摘要

## 测试与验证

- `node --check` 已通过：
  - [app.js](D:/学习工作区/Ashare/frontend/app.js)
  - [api-bridge.js](D:/学习工作区/Ashare/frontend/api-bridge.js)
- Python 语法编译检查已通过：
  - [service.py](D:/学习工作区/Ashare/akshare_backend/service.py)
  - [app.py](D:/学习工作区/Ashare/akshare_backend/app.py)
- Flask `test_client()` 已验证：
  - `/api/news/brief` 返回 `200`
- 本轮实际新闻接口返回结果：
  - 来源：`stock_info_global_cls`
  - 展示标签：`财联社重点电报`
  - 条目数：`3`
  - 最近更新时间：`2026-05-05 21:38:47`

## 下一版本建议

Version 5 建议进入以下方向：
1. 将新闻条目与行业 / 概念映射打通，给筛选结果补充更像样的题材解释。
2. 为新闻简报增加“手动刷新”与“仅看当日 A 股相关内容”过滤。
3. 将 Markdown 导出补成真实文件，并把简报摘要一起写入导出内容。
4. 为历史结果页补充“打开某次结果时对应的新闻快照”能力。
