# StockPulse 公网部署

支持公开 GitHub 代码仓库 + Streamlit Community Cloud + Supabase；所有真实凭据和个人持仓必须留在部署平台 Secrets / 私有数据库中。

## 1. 创建 Supabase 数据表

1. 创建一个 Supabase 项目。
2. 打开 SQL Editor，执行 `deployment/supabase.sql`。
3. 在项目的 Connect 或 Settings → API Keys 页面复制：
   - Project URL
   - Secret key（`sb_secret_...`，仅放在服务端 Secrets 中）

## 2. 一次性上传现有持仓

1. 新建 `.streamlit/secrets.toml`（变量名可参考 `.env.example` 和下方模板）。
2. 填入 `SUPABASE_URL`、`SUPABASE_SECRET_KEY` 和一个强且不与其他账户共用的访问密码。
3. 在项目根目录执行：

```powershell
python scripts/upload_watchlist.py --data-file data/watchlist.json
```

真实 `secrets.toml` 和 `data/watchlist.json` 已被 Git 忽略，不会进入仓库。

## 3. 发布到 Streamlit Community Cloud

1. 将项目提交到 GitHub；公开仓库只能包含代码和空白配置模板。
2. 在 `share.streamlit.io` 创建应用，入口文件填写 `app.py`。
3. Python 版本选择 3.12。
4. 在 Advanced settings → Secrets 中填写：

```toml
APP_PASSWORD = "你的网页访问密码"
SUPABASE_URL = "https://your-project.supabase.co"
SUPABASE_SECRET_KEY = "sb_secret_..."
WATCHLIST_RECORD_ID = "primary"
FUND_SNAPSHOT_RECORD_ID = "primary-funds"

# Gemini投资助手（Key只能保存在服务端Secrets）
LLM_PROVIDER = "gemini"
LLM_MODEL = "gemini-3.7-flash"
GEMINI_API_KEY = "你的Google AI Studio Gemini Auth Key"

# 其他Provider未来可复用的兼容字段；Gemini优先读取上面的专用Key
LLM_API_KEY = ""

# 养基宝实验性只读连接：确认接受非公开接口风险后再配置
YANGJIBAO_TOKEN = ""
YANGJIBAO_ACCOUNT_ID = ""
YANGJIBAO_SIGNING_SECRET = ""
YANGJIBAO_BASE_URL = "https://browser-plug-api.yangjibao.com"
YANGJIBAO_AUTH_RECORD_ID = "primary-yangjibao-auth"
```

5. 点击 Deploy。后续推送 GitHub 后，网页会自动更新。

页面和日志只能显示配置状态，不能输出任何 Secret 内容。若凭据曾进入 Git 历史，请立即撤销并重新生成；仅删除当前文件不能消除泄漏风险。

Gemini Key应在Google AI Studio创建为Auth Key并限制为Gemini API专用。AI页面只有在真实标准化持仓可用、Gemini配置完整且用户勾选单次数据发送授权后才会请求Google；请求不包含养基宝Token、Cookie、账户ID或Supabase Secret。

养基宝目前没有已确认的正式公开开发者 API。扫码与持仓同步只允许 HTTPS，并且必须先设置 `APP_PASSWORD`。不要从公开仓库复制或提交 Token、Cookie、手机号、账户 ID 或签名参数。配置 Supabase 后，同步得到的标准化基金持仓及最近 90 次不含凭据的同步差异摘要会保存到 `FUND_SNAPSHOT_RECORD_ID` 指定的私有记录，无需增加数据库表。只读 Token 与选定账户 ID 使用由服务端 Secrets 派生的密钥加密后保存到 `YANGJIBAO_AUTH_RECORD_ID`；明文 Token、Cookie 和原始响应不会写入数据库。应用重新打开时会恢复授权，基金页保持打开时每 5 分钟自动同步，也可手动立即同步，失败则继续展示最后一次快照。接口变化时应立即停用并回退到快照/Demo 模式。
