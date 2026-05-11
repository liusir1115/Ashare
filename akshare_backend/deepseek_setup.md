# DeepSeek 接入说明

## 当前接入位置

盘后市场总复盘解释层当前已经预留好 DeepSeek 接口。

相关文件：

- `akshare_backend/llm_config.py`
- `akshare_backend/deepseek_provider.py`
- `akshare_backend/postclose_llm_service.py`
- `akshare_backend/postclose_market_service.py`

---

## 需要配置的环境变量

至少需要：

- `DEEPSEEK_API_KEY`

可选：

- `DEEPSEEK_BASE_URL`
- `DEEPSEEK_MODEL`
- `DEEPSEEK_REASONING_EFFORT`
- `DEEPSEEK_THINKING_TYPE`
- `DEEPSEEK_TIMEOUT_SECONDS`

推荐默认值：

- `DEEPSEEK_BASE_URL=https://api.deepseek.com`
- `DEEPSEEK_MODEL=deepseek-v4-flash`
- `DEEPSEEK_REASONING_EFFORT=minimal`
- `DEEPSEEK_THINKING_TYPE=disabled`
- `DEEPSEEK_TIMEOUT_SECONDS=90`

---

## Windows 本地设置示例

PowerShell 临时设置：

```powershell
$env:DEEPSEEK_API_KEY="你的_key"
$env:DEEPSEEK_MODEL="deepseek-v4-flash"
```

然后重新启动后端：

```powershell
python akshare_backend/app.py
```

---

## 生效后的验证方式

访问：

```text
http://127.0.0.1:5000/api/postclose/market-review?refresh=1
```

检查返回字段：

- `llm_status.used` 应为 `true`
- `llm_status.model` 应显示当前模型名

前端页面上也会显示：

- `解释层状态`

如果未填 API key：

- 系统会自动回退到规则版解释层
- 不会阻塞盘后页面使用
