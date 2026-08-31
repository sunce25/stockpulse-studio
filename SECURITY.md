# StockPulse Studio 安全说明

StockPulse Studio 可以公开代码，但密钥、登录凭据和个人投资数据必须始终保持私密。

## 禁止提交的内容

- `.env` 与 `.env.*`（`.env.example` 除外）
- `.streamlit/secrets.toml`
- LLM API Key
- 养基宝 Token、Cookie、账号 ID 或原始响应
- 养基宝签名参数、二维码授权内容或扫码状态响应
- Supabase Secret / Service Role Key 与私有数据库 URL
- `credentials.json`、`secrets.json`、私钥和证书
- `data/watchlist.json` 或其他包含个人持仓、成本、份额的数据

所有敏感配置只能通过环境变量或 Streamlit Secrets 提供。应用只显示“已配置 / 未配置”，不得显示 Key、Token 或 Cookie 内容。

养基宝实验连接必须使用 HTTPS，并要求应用已配置访问密码。扫码 Token 不得通过调试日志、URL 参数、浏览器存储或第三方二维码生成服务传递。启用 Supabase 时，最小化只读授权使用 `cryptography` 的 Fernet 认证加密后保存，密钥由服务端 Supabase Secret 与应用密码派生；数据库不得保存明文 Token、Cookie、账户 ID 或养基宝原始响应。标准化基金快照与加密授权使用独立记录，用户可在页面主动清除已保存授权。

## 如果密钥曾进入 Git 历史

仅删除当前文件不够。应立即：

1. 在对应服务端撤销旧 Key、Token 或密码。
2. 生成新凭据并只写入环境变量或部署平台 Secrets。
3. 按 GitHub 官方指引清理仓库历史；通知所有协作者重新同步经过清理的仓库。
4. 检查访问日志和账单，确认旧凭据没有被滥用。

## 报告安全问题

请不要在公开 Issue 中粘贴真实凭据、个人持仓或可复现的私密数据。报告时只提供脱敏后的文件路径、行号、影响范围和复现步骤。

## 产品边界

本项目是 Decision Support / Investment Copilot。它不连接券商交易执行，不自动下单，不操作资产，也不是 Trading Bot。
