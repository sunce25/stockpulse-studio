# -*- coding: utf-8 -*-
"""
Watchlist & Portfolio Management for StockPulse Studio.
Local JSON persistence with real-time profit/loss calculation, batch operations and grouping.
"""
import os
import json
import copy
import tempfile
from typing import List, Dict

DEFAULT_WATCHLIST_DATA = {
    "groups": ["全部", "美股科技", "A股龙头", "高股息防御", "核心ETF"],
    "items": [
        {
            "symbol": "NVDA",
            "name": "英伟达",
            "market": "美股",
            "group": "美股科技",
            "cost_price": 125.0,
            "shares": 20,
            "note": "AI芯片总龙头"
        },
        {
            "symbol": "AAPL",
            "name": "苹果",
            "market": "美股",
            "group": "美股科技",
            "cost_price": 220.0,
            "shares": 15,
            "note": "消费电子与生态"
        },
        {
            "symbol": "TSLA",
            "name": "特斯拉",
            "market": "美股",
            "group": "美股科技",
            "cost_price": 240.0,
            "shares": 20,
            "note": "智能车与自动驾驶"
        },
        {
            "symbol": "BABA",
            "name": "阿里巴巴",
            "market": "美股",
            "group": "美股科技",
            "cost_price": 95.0,
            "shares": 50,
            "note": "中概电商核心"
        },
        {
            "symbol": "600519",
            "name": "贵州茅台",
            "market": "A股",
            "group": "A股龙头",
            "cost_price": 1350.0,
            "shares": 100,
            "note": "白酒第一白马"
        },
        {
            "symbol": "300750",
            "name": "宁德时代",
            "market": "A股",
            "group": "A股龙头",
            "cost_price": 310.0,
            "shares": 200,
            "note": "动力电池龙头"
        },
        {
            "symbol": "002594",
            "name": "比亚迪",
            "market": "A股",
            "group": "A股龙头",
            "cost_price": 270.0,
            "shares": 200,
            "note": "新能源整车领头羊"
        },
        {
            "symbol": "600900",
            "name": "长江电力",
            "market": "A股",
            "group": "高股息防御",
            "cost_price": 28.5,
            "shares": 2000,
            "note": "水电现金流之王"
        },
        {
            "symbol": "510300",
            "name": "沪深300ETF",
            "market": "ETF",
            "group": "核心ETF",
            "cost_price": 3.95,
            "shares": 10000,
            "note": "A股大盘基准"
        },
        {
            "symbol": "513100",
            "name": "纳指ETF",
            "market": "ETF",
            "group": "核心ETF",
            "cost_price": 1.45,
            "shares": 15000,
            "note": "美股科技指数跟踪"
        }
    ]
}


class WatchlistManager:
    def __init__(self, data_file: str = None):
        if not data_file:
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            data_file = os.path.join(base_dir, "data", "watchlist.json")
        self.data_file = data_file
        self.data = self._load()

    def reload(self) -> Dict:
        """重新从磁盘加载最新自选股数据"""
        self.data = self._load()
        return self.data

    def _load(self) -> Dict:
        """从本地 JSON 读取自选股列表，若不存在则初始化默认值"""
        if os.path.exists(self.data_file):
            try:
                with open(self.data_file, "r", encoding="utf-8") as f:
                    content = json.load(f)
                    if (
                        isinstance(content, dict)
                        and isinstance(content.get("items"), list)
                        and isinstance(content.get("groups", []), list)
                    ):
                        content.setdefault("groups", ["全部"])
                        if "全部" not in content["groups"]:
                            content["groups"].insert(0, "全部")
                        return content
            except (OSError, json.JSONDecodeError, UnicodeError):
                pass
        
        # 写入默认数据
        os.makedirs(os.path.dirname(self.data_file), exist_ok=True)
        default_data = copy.deepcopy(DEFAULT_WATCHLIST_DATA)
        if not os.path.exists(self.data_file):
            self._write_atomic(default_data)
        return default_data

    def _write_atomic(self, content: Dict) -> None:
        """Write a complete JSON document, then atomically replace the old file."""
        data_dir = os.path.dirname(os.path.abspath(self.data_file))
        os.makedirs(data_dir, exist_ok=True)
        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=data_dir, delete=False, suffix=".tmp"
            ) as tmp_file:
                json.dump(content, tmp_file, ensure_ascii=False, indent=2)
                tmp_file.flush()
                os.fsync(tmp_file.fileno())
                tmp_path = tmp_file.name
            os.replace(tmp_path, self.data_file)
        finally:
            if tmp_path and os.path.exists(tmp_path):
                os.unlink(tmp_path)

    def save(self):
        """保存到本地持久化文件"""
        self._write_atomic(self.data)

    def get_groups(self) -> List[str]:
        """获取所有分组"""
        self.reload()
        return self.data.get("groups", ["全部"])

    def add_group(self, group_name: str) -> bool:
        """添加新分组"""
        name = group_name.strip()
        if not name or name in self.data["groups"]:
            return False
        self.data["groups"].append(name)
        self.save()
        return True

    def rename_group(self, old_name: str, new_name: str) -> bool:
        """重命名分组，并同步更新该分组下所有股票。"""
        self.reload()
        old_name = str(old_name).strip()
        new_name = str(new_name).strip()
        groups = self.data.setdefault("groups", ["全部"])
        if (
            not old_name
            or old_name == "全部"
            or old_name not in groups
            or not new_name
            or new_name in groups
        ):
            return False

        group_index = groups.index(old_name)
        groups[group_index] = new_name
        for item in self.data.get("items", []):
            if item.get("group") == old_name:
                item["group"] = new_name
        self.save()
        return True

    def get_items(self, group: str = "全部", market: str = "全部") -> List[Dict]:
        """获取过滤后的自选股"""
        self.reload()
        items = self.data.get("items", [])
        filtered = []
        for it in items:
            if group != "全部" and it.get("group") != group:
                continue
            if market != "全部" and it.get("market") != market:
                continue
            filtered.append(it)
        return filtered

    def has_stock(self, symbol: str) -> bool:
        """判断某标的是否在自选股中"""
        self.reload()
        sym = symbol.strip().upper()
        return any(it["symbol"].upper() == sym for it in self.data.get("items", []))

    def get_stock(self, symbol: str) -> Dict:
        """获取单只自选股详情"""
        self.reload()
        sym = symbol.strip().upper()
        for it in self.data.get("items", []):
            if it["symbol"].upper() == sym:
                return it
        return None

    def add_stock(
        self,
        symbol: str,
        name: str,
        market: str = "A股",
        group: str = "默认",
        cost_price: float = 0.0,
        shares: float = 0.0,
        note: str = ""
    ) -> bool:
        """添加或更新自选股"""
        self.reload()
        sym = symbol.strip().upper()
        if not sym:
            return False

        # 检查是否已存在
        for item in self.data["items"]:
            if item["symbol"].upper() == sym:
                # 更新属性
                item["name"] = name or item["name"]
                item["market"] = market or item["market"]
                item["group"] = group or item["group"]
                item["cost_price"] = float(cost_price)
                item["shares"] = float(shares)
                item["note"] = note
                self.save()
                return True

        # 新增
        target_group = group if group in self.data.get("groups", []) else "全部"
        new_item = {
            "symbol": sym,
            "name": name or sym,
            "market": market,
            "group": target_group,
            "cost_price": float(cost_price),
            "shares": float(shares),
            "note": note
        }
        self.data["items"].append(new_item)
        self.save()
        return True

    def remove_stock(self, symbol: str) -> bool:
        """从自选股中删除单只股票"""
        return self.remove_stocks([symbol]) > 0

    def set_stocks_hidden(self, symbols: List[str], hidden: bool = True) -> int:
        """批量设置标的是否从组合视图及其汇总指标中隐藏。"""
        self.reload()
        sym_set = {s.strip().upper() for s in symbols if s and s.strip()}
        if not sym_set:
            return 0

        changed_count = 0
        for item in self.data.get("items", []):
            if item.get("symbol", "").upper() not in sym_set:
                continue
            current_value = bool(item.get("hidden_from_portfolio", False))
            if current_value == hidden:
                continue
            if hidden:
                item["hidden_from_portfolio"] = True
            else:
                item.pop("hidden_from_portfolio", None)
            changed_count += 1

        if changed_count:
            self.save()
        return changed_count

    def reorder_stocks(self, ordered_symbols: List[str]) -> bool:
        """Persist a custom order for the supplied subset while preserving other slots."""
        self.reload()
        normalized_order = []
        seen = set()
        for symbol in ordered_symbols:
            normalized = str(symbol).strip().upper()
            if normalized and normalized not in seen:
                normalized_order.append(normalized)
                seen.add(normalized)

        if len(normalized_order) < 2:
            return False

        item_by_symbol = {
            str(item.get("symbol", "")).upper(): item
            for item in self.data.get("items", [])
        }
        if any(symbol not in item_by_symbol for symbol in normalized_order):
            return False

        selected_set = set(normalized_order)
        reordered_selected = iter(item_by_symbol[symbol] for symbol in normalized_order)
        reordered_items = [
            next(reordered_selected) if str(item.get("symbol", "")).upper() in selected_set else item
            for item in self.data.get("items", [])
        ]

        old_symbols = [str(item.get("symbol", "")).upper() for item in self.data.get("items", [])]
        new_symbols = [str(item.get("symbol", "")).upper() for item in reordered_items]
        if old_symbols == new_symbols:
            return False

        self.data["items"] = reordered_items
        for index, item in enumerate(self.data["items"], start=1):
            item["sort_order"] = index
        self.save()
        return True

    def remove_stocks(self, symbols: List[str]) -> int:
        """批量从自选股中删除多只股票"""
        self.reload()
        sym_set = {s.strip().upper() for s in symbols if s and s.strip()}
        if not sym_set:
            return 0

        orig_len = len(self.data["items"])
        self.data["items"] = [it for it in self.data["items"] if it["symbol"].upper() not in sym_set]
        deleted_count = orig_len - len(self.data["items"])
        if deleted_count > 0:
            self.save()
        return deleted_count

    def clear_group(self, group: str) -> int:
        """清空指定分组的自选股"""
        self.reload()
        if group == "全部":
            count = len(self.data["items"])
            self.data["items"] = []
            self.save()
            return count
        else:
            orig_len = len(self.data["items"])
            self.data["items"] = [it for it in self.data["items"] if it.get("group") != group]
            count = orig_len - len(self.data["items"])
            if count > 0:
                self.save()
            return count
