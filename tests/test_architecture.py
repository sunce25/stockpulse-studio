import os
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from ai.context_builder import ANALYSIS_HISTORY_FIELDS, build_analysis_context
from ai.copilot import AICopilot, NOT_CONFIGURED_MESSAGE
from config.settings import get_setting
from funds.fund_adapter import (
    FUND_HOLDING_FIELDS,
    assess_data_freshness,
    get_demo_holdings,
    normalize_fund_holding,
)
from funds.fund_analyzer import FundAnalyzer
from funds.portfolio_analyzer import PortfolioAnalyzer
from funds.yangjibao_client import YangJiBaoClient


class SettingsTests(unittest.TestCase):
    def test_environment_takes_precedence(self):
        with patch.dict(os.environ, {"STOCKPULSE_TEST_SETTING": "env-value"}):
            self.assertEqual(get_setting("STOCKPULSE_TEST_SETTING", "fallback"), "env-value")

    def test_missing_setting_uses_default(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(get_setting("STOCKPULSE_MISSING_SETTING", "fallback"), "fallback")


class FundArchitectureTests(unittest.TestCase):
    def test_normalized_model_contains_required_and_qdii_fields(self):
        holding = normalize_fund_holding({"fund_code": "X", "shares": 10, "latest_nav": 2})
        self.assertTrue(set(FUND_HOLDING_FIELDS).issubset(holding))
        self.assertIn("estimated_nav_time", holding)
        self.assertIn("market_timezone", holding)

    def test_string_boolean_and_future_timestamp_are_safe(self):
        holding = normalize_fund_holding(
            {"fund_code": "X", "is_qdii": "false", "stale_data": "false"}
        )
        self.assertFalse(holding["is_qdii"])
        future = datetime.now(timezone.utc) + timedelta(hours=2)
        freshness, stale = assess_data_freshness(future)
        self.assertEqual(freshness, "invalid_future_time")
        self.assertTrue(stale)

    def test_demo_portfolio_matches_expected_total(self):
        holdings = get_demo_holdings()
        result = PortfolioAnalyzer().analyze(holdings)
        self.assertEqual(result["total_assets"], 86420.0)
        self.assertEqual(result["fund_count"], 3)
        self.assertIn("industry_concentration", result)
        self.assertIn("overseas_asset_ratio", result)
        self.assertEqual(result["risk_scope"], "结构风险")

    def test_rule_engine_and_context_keep_freshness(self):
        holding = get_demo_holdings()[0]
        analysis = FundAnalyzer().analyze(holding, nav_history=range(1, 31))
        portfolio = PortfolioAnalyzer().analyze([holding])
        context = build_analysis_context(
            portfolio_summary=portfolio,
            holdings=[holding],
            technical_signals=[analysis],
        )
        self.assertEqual(analysis["rule_version"], "fund-rules-v1")
        self.assertIn("stale_data", context)
        self.assertTrue(set(ANALYSIS_HISTORY_FIELDS))

    def test_missing_history_does_not_produce_holding_advice(self):
        analysis = FundAnalyzer().analyze(get_demo_holdings()[0])
        self.assertFalse(analysis["historical_metrics_available"])
        self.assertEqual(analysis["risk_status"], "数据不足")
        self.assertEqual(analysis["recommendation"], "观察")

    def test_integrations_are_placeholders(self):
        client = YangJiBaoClient(token="", account_id="")
        self.assertFalse(client.is_configured())
        with self.assertRaises(NotImplementedError):
            client.get_holdings()
        copilot = AICopilot(provider="", api_key="", model="")
        self.assertEqual(copilot.answer_question({}, "test"), NOT_CONFIGURED_MESSAGE)
        self.assertNotIn("api_key", copilot.configuration_status())


if __name__ == "__main__":
    unittest.main()
