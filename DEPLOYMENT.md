# StockPulse 公网部署

支持公开 GitHub 代码仓库 + Streamlit Community Cloud + Supabase；所有真实凭据和个人持仓必须留在部署平台 Secrets / 私有数据库中。

## 1. 创建 Supabase 数据表

1. 创建一个 Supabase 项目。
2. 打开 SQL Editor，执行 `deployment/supabase.sql`。
3. 在项目的 Connect 或 Settings → API Keys 页面复制：
   - Project URL
   - Secret key（`sb_secret_...`，仅放在服务端 Secrets 中）

## 2. 一次性上传现有持仓

1. 将 `.streamlit/secrets.toml.example` 复制为 `.streamlit/secrets.toml`。
2. 填入 `SUPABASE_URL`、`SUPABASE_SECRET_KEY` 和一个强访问密码。
3. 在项目根目录执行：

```powershell
python scripts/upload_watchlist.py --data-file data/watchlist.json
```

真实 `secrets.toml` 和 `data/watchlist.json` 已被 Git 忽略，不会进入仓库。

## 3. 发布到 Streamlit Community Cloud

1. 将项目提交到私有 GitHub 仓库。
2. 在 `share.streamlit.io` 创建应用，入口文件填写 `app.py`。
3. Python 版本选择 3.12。
4. 在 Advanced settings → Secrets 中填写：

```toml
APP_PASSWORD = "你的网页访问密码"
SUPABASE_URL = "https://your-project.supabase.co"
SUPABASE_SECRET_KEY = "sb_secret_..."
WATCHLIST_RECORD_ID = "primary"

# AI 集成仍为占位功能
LLM_PROVIDER = ""
LLM_API_KEY = ""
LLM_MODEL = ""

# 养基宝实验性连接：未完成安全验证前请保持为空
YANGJIBAO_TOKEN = ""
YANGJIBAO_ACCOUNT_ID = ""
YANGJIBAO_SIGNING_SECRET = ""
YANGJIBAO_BASE_URL = "https://browser-plug-api.yangjibao.com"
```

5. 点击 Deploy。后续推送 GitHub 后，网页会自动更新。

页面和日志只能显示配置状态，不能输出任何 Secret 内容。若凭据曾进入 Git 历史，请立即撤销并重新生成；仅删除当前文件不能消除泄漏风险。

养基宝目前没有已确认的正式公开开发者 API。连接测试只允许 HTTPS，并且必须先设置 `APP_PASSWORD`。不要从公开仓库复制或提交 Token、Cookie、手机号、账户 ID 或签名参数；真实持仓同步在完成接口与授权风险验证前保持关闭。
