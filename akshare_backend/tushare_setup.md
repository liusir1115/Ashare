# Tushare 本地接入说明

## 1. 安装依赖

```bash
pip install tushare
```

## 2. 统一初始化方式

当前项目后续统一从这个文件初始化 Tushare：

- `akshare_backend/tushare_runtime_local.py`

当前标准写法：

```python
import tushare as ts

pro = ts.pro_api("你的 token")
pro._DataApi__http_url = "http://124.220.22.110:8020/"
```

说明：

- 如果出现 token 不正确，先检查有没有这一行：
  - `pro._DataApi__http_url = "http://124.220.22.110:8020/"`
- 后端业务代码不再要求每次手动设置环境变量
- 只有本地初始化文件不存在时，才回退到 `TUSHARE_TOKEN` 环境变量

## 3. 启动后端

```bash
python akshare_backend/app.py
```

## 4. 验证接口

先验证基础取数：

```text
http://127.0.0.1:5000/api/tushare/probe
```

再验证最小筛选样例：

```text
http://127.0.0.1:5000/api/tushare/sample-screen
```

## 5. 当前结论

当前这套初始化方式已经在本机实测通过：

- `index_basic(limit=5)` 可用
- `ts.pro_bar(api=pro, ts_code="000001.SZ", limit=3)` 可用
- 后续盘前主筛选统一复用同一个 client 初始化入口
