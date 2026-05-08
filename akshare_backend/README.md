# AKShare 后端脚本

这个目录用于放置本项目第一版真实数据接入脚本。

## 文件说明

- `service.py`：AKShare 拉取、字段标准化、筛选和结果组装
- `app.py`：最小 Flask API，同时托管现有前端静态页面
- `probe_columns.py`：命令行探测脚本，用来检查 AKShare 列名和前端筛选项支持情况
- `requirements.txt`：环境依赖

## 已创建环境

推荐使用已创建的 conda 环境：

```bash
conda activate ashare-ak
```

## 先跑能力探测

```bash
python akshare_backend/probe_columns.py
```

## 启动最小前后端联调

```bash
python akshare_backend/app.py
```

启动后访问：

```text
http://127.0.0.1:5000
```

## 当前实现边界

当前版本优先验证：

1. AKShare 是否能提供前端主链路所需的核心字段
2. 哪些筛选项可以直接用 `stock_zh_a_spot_em()` 支持
3. 哪些筛选项需要额外历史 K 线或题材数据
4. 前端能否通过按钮直接请求后端并刷新结果表格

当前没有做：

1. 数据库存储
2. 历史记录持久化
3. 全量历史 K 线批处理
4. 完整概念 / 行业映射
5. 盘前 / 盘后两套完整评分模型
