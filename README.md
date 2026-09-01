# StockPulse Studio · 个人 AI 投资分析工作台

一个面向个人投资者的股票、基金、组合风险与 AI 解释工作台。StockPulse 只提供决策支持，不执行交易、不自动下单、不连接券商交易执行。

---

## 🌟 核心功能一览

1. **📈 多市场个股走势深度看板**
   - **支持市场**：A股 (沪深京)、美股 (纳斯达克/纽交所/中概股)、ETF 基金。
   - **交互图表**：基于 Plotly 构建，支持日K/周K/月K、多周期自由缩放平移、红绿涨跌风格切换。
   - **技术指标**：主图叠加 MA5/10/20/60/120/250、布林带 (BOLL)、EMA；副图支持 MACD、KDJ、RSI、ATR 及成交量均线。

2. **🔍 多维策略智能选股器**
   - **多因子组合**：股价区间、涨跌幅、市盈率 PE、市值规模自由调节。
   - **预置形态策略**：均线多头排列、MACD 底部/零上金叉、放量突破、低估值蓝筹。
   - **结果导出**：一键导出筛选结果为 Excel / CSV 表格。

3. **⭐ 跨市场自选股与组合追踪**
   - 本地 JSON 安全持久化，无须配置复杂数据库，重启不丢失。
   - 支持 A股 与 美股 混合持仓管理，自动批量刷新最新报价与浮动盈亏。

4. **🤖 智能形态诊断与研报摘要**
   - 自动扫描均线排列、量价配合、超买超卖，生成技术健康度评分 (0-100)。
   - 智能测算预估关键阻力位与支撑位，输出操作建议参考。

5. **💰 我的基金（架构骨架）**
   - 使用统一基金持仓模型展示组合资产、收益、仓位、集中度和风险评分。
   - 默认展示 Demo Data；完成实验性养基宝扫码后，可选择账户并只读同步真实基金持仓。配置 Supabase 后会保存标准化快照、最近 90 次同步审计摘要和加密只读授权，重新打开页面时自动恢复；基金页保持打开时每 5 分钟自动同步，也可手动立即同步，接口异常时回退到最后一次快照。
   - 同步审计会区分份额/成本变化（例如每日定投）与单纯净值/估值变化，并逐只展示净值日期、估值时间和数据新鲜度。

6. **🧠 AI 投资助手（占位模式）**
   - 已建立 Provider 无关的 Copilot 接口、Prompt 管理与 Structured Context。
   - 当前不会调用 OpenAI、Gemini、Claude、DeepSeek 或其他 LLM API。

---

## 🚀 启动与运行

### 方式一：Windows 一键启动 (推荐)
直接双击运行项目目录下的 `run.bat`，系统将自动拉起服务并在浏览器中打开 `http://localhost:8501`。

### 方式二：命令行启动
```bash
cd stockpulse_studio
python -m streamlit run app.py
```

### 公网托管

项目支持使用 Supabase 保存持仓数据，并部署到 Streamlit Community Cloud。详见 [DEPLOYMENT.md](DEPLOYMENT.md)。

## AI 与基金分析扩展架构

```text
养基宝 / 其他基金源       行情数据
          \               /
           标准化数据层
                 ↓
        Python / Quant Engine
   （收益、回撤、波动、仓位、集中度、风险）
                 ↓
         Structured Context
                 ↓
          LLM（未来可选）
                 ↓
         AI 解释 + AI 问答
```

原则是约 80% 的客观分析由可审计的 Python 规则引擎完成，LLM 只负责解释、总结、问答和有限等级建议。LLM 不得修改规则引擎结果；数据不足或过期时必须明确说明。

关键模块：

- `config/settings.py`：环境变量优先、兼容 Streamlit Secrets 的统一配置入口。
- `funds/yangjibao_client.py`：养基宝专属隔离边界；仅允许 HTTPS 下的扫码、账户发现和只读持仓同步。
- `funds/auth_store.py`：使用服务端派生密钥加密保存最小化只读授权，数据库不出现明文 Token。
- `funds/snapshot_store.py`：在私有 Supabase 中保存标准化基金快照，刷新或接口故障时恢复。
- `funds/holding_history.py`：生成不含凭据和账户 ID 的同步差异摘要，识别定投份额/成本变化。
- `funds/fund_adapter.py`：跨平台统一基金模型与数据新鲜度。
- `funds/fund_analyzer.py`、`funds/portfolio_analyzer.py`：纯 Python 规则分析。
- `ai/context_builder.py`：把规则结果整理为结构化上下文，并预留分析审计记录。
- `ai/copilot.py`、`ai/prompts.py`：Provider 无关接口和安全 Prompt；当前为占位模式。

QDII、海外指数与港股基金的数据模型预留了净值日期、盘中估值时间、市场时区与新鲜度。盘中估值不能当作最终确认净值。

## 配置与安全

复制 `.env.example` 或 `.streamlit/secrets.toml.example` 后在本机填写配置；真实文件不得提交。公开部署前请阅读 [SECURITY.md](SECURITY.md)。

养基宝连接属于实验功能，并非官方公开开发者 API。只有配置 `APP_PASSWORD`、`YANGJIBAO_SIGNING_SECRET` 且接口为 HTTPS 时页面才允许发起扫码和只读同步。配置 Supabase 后，扫码取得的只读 Token 与账户 ID 会经过认证加密后保存，标准化持仓保存为独立私有快照；两者都不显示、不写日志，数据库中不会出现明文凭据。StockPulse 不调用养基宝的新增、删除或修改接口。
