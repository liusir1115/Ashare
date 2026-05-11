# Ashare Backend

这个目录现在承载两条明确分开的能力：

- 盘前主筛选：以 `Tushare` 为主数据源
- 新闻摘要与部分盘后辅助：保留 `AKShare` 资讯/快照能力

## 当前主文件

- `app.py`：Flask 入口，统一挂载前端页面与后端接口
- `service.py`：薄服务层，只做对外导出
- `premarket_tushare_screen_service.py`：盘前主筛选链路
- `tushare_provider.py`：Tushare client 和数据拉取封装
- `tushare_runtime_local.py`：本地统一初始化文件
- `premarket_news_service.py`：新闻摘要能力
- `postclose_market_service.py`：盘后市场复盘的数据骨架

## 当前运行前提

1. 本地 Python 依赖已安装
2. 项目默认从 `akshare_backend/tushare_runtime_local.py` 初始化 Tushare client
3. 如果本地初始化文件不存在，才回退到 `TUSHARE_TOKEN` 环境变量
4. 未配置有效 token 时，服务会明确报错，不会伪造演示数据

## 启动方式

```bash
python akshare_backend/app.py
```

启动后访问：

```text
http://127.0.0.1:5000
```

## 当前边界

- 已切掉旧的 AKShare 盘前主筛选定位
- 保留 AKShare 新闻/辅助能力，因为它们仍然被真实调用
- 临时实验脚本已移入 `archive/backend-helpers/`
- 当前这台机器的 Tushare 初始化已落到本地文件，后续统一复用该入口
