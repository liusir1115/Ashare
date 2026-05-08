# Version 2 数据源接入与最小联调开发记录
## 版本定位

Version 2 是在 Version 1 前端展示版基础上，补齐真实数据源接入与最小前后端交互能力的版本。
本版本的目标不是直接完成完整生产后端，而是先把“前端页面 -> 后端接口 -> AKShare 数据抓取 -> DataFrame 条件筛选 -> 结果返回 -> 本地结果落盘”这条主链路跑通。

这一版聚焦于以下事情：

1. 明确 AKShare 在本项目中的真实接入方式。
2. 用 Python 脚本验证 AKShare 可返回的字段与前端筛选需求的匹配程度。
3. 建立一个最小可运行的后端接口层。
4. 将前端展示页与后端接口做简单联调。
5. 在每次筛选执行后，把结果 DataFrame 导出为本地 Excel 文件，便于回看和调试。

## 已确认设计方向

- 数据源首选 AKShare，接入方式为 Python 调用 + pandas DataFrame 处理，不是直接由前端请求第三方数据源。
- 当前版本仍以本地运行、单机验证为主，不接入正式数据库。
- 筛选逻辑以 DataFrame 条件过滤为核心，不做 SQL 筛选。
- 先区分两层筛选：
  - 快速现货筛选：基于 `stock_zh_a_spot_em`
  - 历史增强筛选：基于 `stock_zh_a_hist`
- 前端允许编辑条件文本，但后端只接收解析后的结构化数值。
- 每轮筛选执行结束后，需要保存一份本地 xlsx 结果文件。
- 继续沿用轻量 SaaS + 金融工具信息密度的展示方式，不在这一版扩展登录和权限体系。

## Version 2 包含内容

### AKShare 接入验证
- 新建独立 conda 虚拟环境 `ashare-ak`
- 安装：
  - `akshare`
  - `flask`
  - `flask-cors`
  - `pandas`
  - `openpyxl`
- 验证 AKShare 可正常拉取 A 股实时快照数据
- 验证 AKShare 可返回 `DataFrame`
- 编写探测脚本输出字段、样例数据和筛选能力报告

### 数据字段映射与筛选能力梳理
- 将 `stock_zh_a_spot_em` 返回字段映射到项目内部统一字段，例如：
  - `symbol`
  - `name`
  - `latest_price`
  - `change_pct`
  - `amount`
  - `amplitude`
  - `volume_ratio`
  - `turnover_rate`
  - `total_market_cap`
  - `circulating_market_cap`
  - `change_pct_60d`
- 明确当前可直接支持的前端筛选项：
  - 股价区间
  - 总市值区间
  - 流通市值区间
  - 涨跌幅区间
  - 换手率区间
  - 成交额区间
  - 量比区间
  - 振幅区间
- 明确需要历史 K 线增强计算的筛选项：
  - 近 N 日涨幅
  - 近 N 日回撤
  - 均线位置
  - 均线突破
  - N 日新高 / 新低
  - 连续上涨 / 下跌天数
  - 持续放量 / 缩量
  - 90 天内新股过滤
- 明确当前暂未真正接入的筛选项：
  - 所属行业 / 概念
  - 筹码集中度

### 后端服务骨架
- 新建 `akshare_backend` 文件夹，包含：
  - [app.py](D:/学习工作区/Ashare/akshare_backend/app.py)
  - [service.py](D:/学习工作区/Ashare/akshare_backend/service.py)
  - [probe_columns.py](D:/学习工作区/Ashare/akshare_backend/probe_columns.py)
  - [test_integration.py](D:/学习工作区/Ashare/akshare_backend/test_integration.py)
  - [start_server.py](D:/学习工作区/Ashare/akshare_backend/start_server.py)
  - [requirements.txt](D:/学习工作区/Ashare/akshare_backend/requirements.txt)
- 实现接口：
  - `/api/health`
  - `/api/capability`
  - `/api/probe`
  - `/api/screen/run`
- 实现前端静态文件代理，使 Flask 可以直接返回前端页面

### DataFrame 筛选与增强计算
- 使用 pandas DataFrame 进行条件筛选
- 实现市场范围过滤：
  - 沪深主板
  - 科创板
  - 沪深主板 + 创业板
- 实现默认排除逻辑：
  - 排除 ST
  - 排除北交所
  - 排除停牌股
- 实现快筛函数：
  - `apply_fast_filters()`
- 实现历史增强链路：
  - 候选股票历史数据拉取
  - 均线与突破计算
  - 连涨连跌统计
  - 放量缩量统计
  - 上市天数判断
- 支持 `fast` 与 `full` 两种筛选深度

### 排序与结果组织
- 在快筛结果之上增加基础评分排序
- 区分盘前 / 盘后两套评分倾向：
  - 盘前更重趋势、量比、换手与资金活跃度
  - 盘后更重当日涨跌、换手、资金与复盘价值
- 将结果整理成前端可直接消费的结构：
  - 排名
  - 分数
  - 优先级
  - 股票名称 / 代码
  - 市场
  - 第一轮命中摘要
  - 第二轮排序原因
  - 风险提示
  - 指标摘要
  - 维度摘要

### 前后端最小联调
- 新增 [api-bridge.js](D:/学习工作区/Ashare/frontend/api-bridge.js)
- 前端点击“开始筛选”时可请求 `/api/screen/run`
- 前端可根据返回结果刷新：
  - 结果表格
  - 右侧详情抽屉
  - 结果摘要
  - 加载进度条
- 前端会把条件面板中的输入值解析成结构化 payload 后再提交给后端

### 结果导出与本地落盘
- 新建 `result` 文件夹作为筛选结果输出目录
- 每次 `run_screen()` 执行结束后，自动保存一份 xlsx 文件
- 文件名规则：
  - 当前时间
  - 精确到分钟
  - 若同一分钟重复执行，则自动追加序号，避免覆盖
- 导出内容为最终参与排序的结果 DataFrame
- 对股票代码列进行文本格式处理，避免前导零丢失

### 文档更新
- 覆写 [data-source-spec.md](D:/学习工作区/Ashare/docs/data-source-spec.md)
- 重新以 AKShare 的真实用法说明数据接入方式
- 明确 MVP 阶段可以不接数据库，但正式版建议补数据库与缓存

## Version 2 不包含内容

- 正式数据库接入
- Redis 缓存服务部署
- 用户体系与登录功能
- 真实管理员页
- 行业 / 概念筛选正式接入
- 筹码集中度接入
- 自然语言生成筛选条件
- 历史回测
- 盘中实时监控
- 多用户任务管理
- 正式异步任务队列
- 生产级错误重试与告警系统

## 下一版本建议

Version 3 建议进入以下方向：

1. 将前端自由文本条件改成结构化控件，避免“数字 + 中文”混输带来的解析歧义。
2. 为 `/api/screen/run` 增加更严格的参数校验、范围校验和错误提示。
3. 补齐行业 / 概念映射，让结果页不再只显示占位文本。
4. 优化 AKShare 拉取耗时，加入更清晰的缓存策略和降级策略。
5. 将筛选结果保存与历史页正式打通，让前端可查看本地历史执行记录。
6. 考虑引入 SQLite 或 PostgreSQL，保存任务、结果、配置和数据源状态。
7. 清理前端展示代码与联调桥接代码的重复逻辑，收拢为单一可维护实现。
8. 继续补盘前 / 盘后差异化策略说明与更多历史增强指标。
