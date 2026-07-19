# -*- coding: utf-8 -*-
import json
import os
import tempfile
import unittest
import datetime as dt
from unittest import mock

import pandas as pd

import shadow_ledger as ledger
import 影子交割 as shadow
import 失效判据 as invalidation


class ShadowLedgerTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.paths = {
            "TRADES": os.path.join(self.tmp.name, "trades.csv"),
            "EVENTS": os.path.join(self.tmp.name, "events.csv"),
            "NAV": os.path.join(self.tmp.name, "nav.csv"),
            "BASE_TRADES": os.path.join(self.tmp.name, "base_trades.csv"),
            "DECISIONS": os.path.join(self.tmp.name, "decisions.jsonl"),
            "STATE": os.path.join(self.tmp.name, "state.json"),
        }
        self.patchers = [mock.patch.object(shadow, k, v) for k, v in self.paths.items()]
        for p in self.patchers:
            p.start()

    def tearDown(self):
        for p in reversed(self.patchers):
            p.stop()
        self.tmp.cleanup()

    def test_legacy_state_migrates_without_inventing_position_cashflows(self):
        st = {"A": {"open": [{"code": "600000"}]}, "C": {"open": []}}
        out = ledger.ensure_state(st, 500000)
        self.assertEqual(out["state_version"], 2)
        self.assertEqual(out["A"]["open"][0]["shares"], 0)
        self.assertFalse(out["A"]["open"][0]["accounted"])
        self.assertEqual(out["accounts"]["A"]["cash"], 500000)
        self.assertIn("R", out["accounts"])

    def test_corrupt_primary_state_recovers_from_backup(self):
        with open(self.paths["STATE"], "w", encoding="utf-8") as f:
            f.write("not-json")
        with open(self.paths["STATE"] + ".bak", "w", encoding="utf-8") as f:
            json.dump({"A": {"open": []}, "C": {"open": []}, "last_run": "20260701"}, f)
        out = shadow.load_state()
        self.assertEqual(out["last_run"], "20260701")
        self.assertEqual(out["state_version"], 2)

    def test_accounting_invariants_fail_closed(self):
        st = ledger.ensure_state({}, 500000)
        st["accounts"]["A"]["cash"] = -10
        with self.assertRaisesRegex(ValueError, "A账户现金异常"):
            ledger.validate_state(st)

    def test_satellite_round_trip_preserves_cash_equity_identity(self):
        st = ledger.ensure_state({}, 500000)
        account = st["accounts"]["A"]
        candidate = {"code": "600000", "board": "main", "ind": "银行"}
        pos = ledger.buy_satellite(
            account, [], candidate, 100, 95, "20260702", 60, 0.0075,
            shadow._board_rules(), 0.30, 0.30, 0.00025, 5,
        )
        self.assertIsNotNone(pos)
        pos.update(candidate)
        pos["entry"] = 100
        positions = [pos]
        marked = ledger.mark_account(account, positions)
        self.assertAlmostEqual(marked["equity"], account["cash"] + pos["shares"] * 100)
        ledger.sell_satellite(
            account, pos, pos["shares"], 105, "20260703", shadow._board_rules(),
            0.00025, 5, lambda _date: 0.0005,
        )
        self.assertEqual(pos["shares"], 0)
        self.assertAlmostEqual(ledger.mark_account(account, positions)["equity"], account["cash"])
        self.assertGreater(account["cash"], 500000)

    def test_base_account_rebalances_and_charges_cost(self):
        st = ledger.ensure_state({}, 500000)
        account = st["accounts"]["base"]
        prices = {("510300", "20260702"): 5.0, ("510300", "20260703"): 5.5}
        lookup = lambda code, date: prices.get((code, date))
        trades = ledger.rebalance_base(
            account, {"etf": "510300", "name": "沪深300", "weight": 30},
            "20260702", lookup, 0.0003, 0.05,
        )
        self.assertEqual(trades[0]["side"], "buy")
        first = ledger.snapshot_account(account, [], 500000)
        self.assertLess(first["nav"], 1.0)
        self.assertAlmostEqual(first["equity"], first["cash"] + first["base_mv"])
        trades2 = ledger.rebalance_base(
            account, {"etf": "510300", "name": "沪深300", "weight": 30},
            "20260703", lookup, 0.0003, 0.05,
        )
        self.assertEqual(trades2, [])  # 5%总资产再平衡带内不交易
        second = ledger.snapshot_account(account, [], 500000)
        self.assertGreater(second["daily_return"], 0)

    def test_pending_entry_cannot_use_a_bar_after_today(self):
        st = ledger.ensure_state({}, 500000)
        st["A"]["pending_entry"] = {
            "code": "600000", "name": "测试", "board": "main", "ind": "银行",
            "stop_price": 95, "decide_date": "20260701", "cap": 60,
            "score": 80, "sec_rank": 1,
        }
        bars = pd.DataFrame([
            {"trade_date": "20260701", "open": 99, "high": 101, "low": 98, "close": 100},
            {"trade_date": "20260702", "open": 101, "high": 103, "low": 100, "close": 102},
            {"trade_date": "20260703", "open": 80, "high": 82, "low": 79, "close": 81},
        ])
        with mock.patch.object(shadow, "daily_bars", return_value=bars):
            shadow._execute_pending_entry("A", st, "20260702")
        self.assertEqual(st["A"]["open"][0]["entry_date"], "20260702")
        self.assertEqual(st["A"]["open"][0]["entry"], 102)

    def test_stop_is_confirmed_at_close_and_sold_next_open(self):
        st = ledger.ensure_state({}, 500000)
        account = st["accounts"]["A"]
        sizing = ledger.buy_satellite(
            account, [], {"code": "600000", "board": "main", "ind": "银行"},
            100, 95, "20260702", 60, 0.0075, shadow._board_rules(), 0.30, 0.30, 0.00025, 5,
        )
        pos = dict(code="600000", name="测试", board="main", ind="银行", entry=100,
                   stop=95, target=110, entry_date="20260702", half=False, hold=0,
                   overlap="N", **sizing)
        st["A"]["open"] = [pos]
        bars = pd.DataFrame([
            {"trade_date": "20260702", "open": 100, "high": 101, "low": 98, "close": 100},
            {"trade_date": "20260703", "open": 98, "high": 99, "low": 93, "close": 94},
            {"trade_date": "20260704", "open": 93, "high": 95, "low": 92, "close": 94},
        ])
        with mock.patch.object(shadow, "daily_bars", return_value=bars):
            shadow._update_positions("A", st, "20260703")
            self.assertEqual(len(st["A"]["open"]), 1)
            self.assertIn("止损", st["A"]["open"][0]["exit_next_open"])
            shadow._update_positions("A", st, "20260704")
        self.assertEqual(st["A"]["open"], [])
        trades = pd.read_csv(self.paths["TRADES"])
        self.assertEqual(str(trades.iloc[0]["平仓日"]), "20260704")
        self.assertAlmostEqual(float(trades.iloc[0]["平仓价"]), 93.0)

    def test_decision_snapshot_is_append_only(self):
        data = {"data_date": "2026-07-02", "generated_at": "18:31", "state": {"cap": 40},
                "base": {}, "candidates": []}
        shadow.write_decision_snapshot("20260702", data, "raw-one")
        shadow.write_decision_snapshot("20260702", data, "raw-one")
        with open(self.paths["DECISIONS"], encoding="utf-8") as f:
            lines = f.readlines()
        self.assertEqual(len(lines), 1)
        snap = json.loads(lines[0])
        self.assertEqual(snap["input_hash"], snap["data_sha256"])
        self.assertIn("strategy_commit", snap)
        self.assertIn("source_hashes", snap)
        self.assertEqual(snap["decisions"]["A"]["decision_id"], "20260702-A-v1")
        self.assertEqual(snap["decisions"]["A"]["skip_reason"], "state_can_open_false")
        with self.assertRaises(RuntimeError):
            shadow.write_decision_snapshot("20260702", data, "raw-two")

    def test_random_rank_control_uses_frozen_sha256_rule(self):
        cands = [
            {"code": "600001", "score": 99, "sec_rank": 1, "rs": 1, "prior60": -1, "amt20_yi": 3},
            {"code": "600002", "score": 80, "sec_rank": 2, "rs": 1, "prior60": -1, "amt20_yi": 3},
            {"code": "600003", "score": 70, "sec_rank": 3, "rs": 1, "prior60": -1, "amt20_yi": 3},
        ]
        self.assertEqual(shadow._selected(cands, "A", "20260702")["code"], "600001")
        expected = min(cands, key=lambda c: shadow._random_key(c, "20260702"))["code"]
        self.assertEqual(shadow._selected(cands, "R", "20260702")["code"], expected)
        self.assertEqual(shadow._selected(list(reversed(cands)), "R", "20260702")["code"], expected)

    def test_random_stream_never_enters_existing_invalidation_rule(self):
        rows = ([{"流": "A", "R": 0.2}] * 40
                + [{"流": "R", "R": -5.0}] * 100
                + [{"流": "C", "R": -5.0}] * 100)
        pd.DataFrame(rows).to_csv(self.paths["TRADES"], index=False, encoding="utf-8-sig")
        missing_real = os.path.join(self.tmp.name, "missing-real.csv")
        with mock.patch.object(invalidation, "CSV_SHADOW", self.paths["TRADES"]):
            result = invalidation.evaluate(csv_path=missing_real)
        self.assertEqual(result["level"], 0)
        self.assertIn("影子A流40笔", result["text"])

    def test_nav_schema_migrates_old_rows_without_dropping_them(self):
        pd.DataFrame([{"date": "20260701", "tier": "空仓", "A_open": 0}]).to_csv(
            self.paths["NAV"], index=False, encoding="utf-8-sig")
        shadow.upsert_csv({"date": "20260702", "tier": "标准", "A_nav": 1.01},
                          self.paths["NAV"], ("date",))
        out = pd.read_csv(self.paths["NAV"], encoding="utf-8-sig")
        self.assertEqual(len(out), 2)
        self.assertIn("A_nav", out.columns)
        self.assertEqual(str(out.iloc[0]["date"]), "20260701")

    def test_main_end_to_end_writes_four_account_nav_and_v2_state(self):
        data_path = os.path.join(self.tmp.name, "data.js")
        payload = {
            "data_date": "2026-07-02", "generated_at": "2026-07-02 18:31:00",
            "state": {"tier": "防守", "cap": 20, "can_open": False},
            "base": {"etf": "510300", "name": "沪深300", "weight": 10},
            "candidates": [],
        }
        with open(data_path, "w", encoding="utf-8") as f:
            f.write("window.STRATEGY_DATA = " + json.dumps(payload, ensure_ascii=False) + ";")
        with open(self.paths["STATE"], "w", encoding="utf-8") as f:
            json.dump({"A": {"open": []}, "C": {"open": []}, "last_run": "20260701"}, f)

        class FixedDate(dt.date):
            @classmethod
            def today(cls):
                return cls(2026, 7, 2)

        with mock.patch.object(shadow.dt, "date", FixedDate), \
             mock.patch.object(shadow.P, "_recent_trade_dates", return_value=["20260702"]), \
             mock.patch.object(shadow.C, "DATA_JS_PATH", data_path), \
             mock.patch.object(shadow, "fund_close", return_value=5.0):
            shadow.main()

        nav = pd.read_csv(self.paths["NAV"], encoding="utf-8-sig")
        self.assertEqual(len(nav), 1)
        for col in ("cash_nav", "base_nav", "A_nav", "C_nav", "R_nav",
                    "A_cash", "A_base_mv", "A_sat_mv"):
            self.assertIn(col, nav.columns)
        self.assertAlmostEqual(float(nav.iloc[0]["cash_nav"]), 1.0)
        self.assertLess(float(nav.iloc[0]["base_nav"]), 1.0)  # 首次建底仓成本已扣
        with open(self.paths["STATE"], encoding="utf-8") as f:
            state = json.load(f)
        self.assertEqual(state["state_version"], 2)
        self.assertEqual(state["last_run"], "20260702")


if __name__ == "__main__":
    unittest.main()
