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
            "COMMIT_MARK": os.path.join(self.tmp.name, "commit_pending.json"),
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
        good = {"A": {"open": []}, "C": {"open": []}, "last_run": "20260701"}
        with open(self.paths["STATE"] + ".bak", "w", encoding="utf-8") as f:
            json.dump(good, f)
        with open(self.paths["STATE"], "w", encoding="utf-8") as f:
            f.write("broken")
        # 复审修复(0719)契约：恢复后必须停止执行
        with self.assertRaises(RuntimeError):
            shadow.load_state()
        # .bak 原封不动
        with open(self.paths["STATE"] + ".bak", encoding="utf-8") as f:
            self.assertEqual(json.load(f)["last_run"], "20260701")
        # 主文件已被原子恢复为好状态
        with open(self.paths["STATE"], encoding="utf-8") as f:
            self.assertEqual(json.load(f)["last_run"], "20260701")
        # 损坏件被隔离留证
        corrupt = [x for x in os.listdir(self.tmp.name) if ".corrupt-" in x]
        self.assertEqual(len(corrupt), 1)
        # 复审二轮(0719)契约：恢复后写入持久锁，未人工确认前每次运行都停
        with open(self.paths["STATE"], encoding="utf-8") as f:
            self.assertIn("recovery_required", json.load(f))
        with self.assertRaises(RuntimeError):
            shadow.load_state()
        # 人工确认（--confirm-recovery）解锁后才能继续
        shadow.confirm_recovery()
        out = shadow.load_state()
        self.assertEqual(out["last_run"], "20260701")
        self.assertNotIn("recovery_required", out)

    def test_rerun_with_existing_snapshot_halts_on_actual_divergence(self):
        """复审二轮(0719)：补跑时既有快照actual与重算不一致→停止，不写NAV不推进last_run。"""
        st = ledger.ensure_state({}, 500000)
        with open(self.paths["STATE"], "w", encoding="utf-8") as f:
            json.dump(st, f)
        cands = [
            {"code": "600001", "name": "甲", "score": 99, "sec_rank": 1, "rs": 1, "prior60": -1,
             "amt20_yi": 3, "board": "main", "stop_price": 9.0, "close": 10.0},
            {"code": "600002", "name": "乙", "score": 80, "sec_rank": 2, "rs": 1, "prior60": -1,
             "amt20_yi": 3, "board": "main", "stop_price": 9.0, "close": 10.0},
        ]
        raw = ('window.STRATEGY_DATA = {"data_date": "2026-07-02", "state": {"cap": 40, "can_open": true},'
               ' "base": {}, "candidates": ' + json.dumps(cands, ensure_ascii=False) + '};')
        datapath = os.path.join(self.tmp.name, "data.js")
        with open(datapath, "w", encoding="utf-8") as f:
            f.write(raw)
        d = json.loads(raw[raw.find("{"):raw.rfind("}") + 1])
        # 预先落盘一份"actual=600001"的快照（模拟上次运行在保存状态前崩溃、但状态已含600001持仓→重算将排600002）
        actions0 = {k: {"queued_code": ("600001" if k == "A" else None), "queued_name": "甲",
                        "skip_reason": "queued", "held_excluded": [], "eligible_after_exclusion": 2}
                    for k in ("A", "C", "R")}
        shadow.write_decision_snapshot("20260702", d, raw, actions0)
        st["A"]["open"] = [{"code": "600001", "shares": 100, "entry_date": "20260701",
                            "entry": 10.0, "stop": 9.0, "target": 12.0, "half": False, "hold": 0}]
        with open(self.paths["STATE"], "w", encoding="utf-8") as f:
            json.dump(st, f)
        bars = pd.DataFrame([{"trade_date": "20260702", "open": 10, "high": 10.5, "low": 9.9, "close": 10.2}])
        with mock.patch.object(shadow.C, "DATA_JS_PATH", datapath), \
             mock.patch.object(shadow, "daily_bars", return_value=bars), \
             mock.patch.object(shadow.P, "_recent_trade_dates", return_value=["20260702"]):
            shadow.main(today="20260702")
        self.assertFalse(os.path.exists(self.paths["NAV"]))          # 背离→未写NAV
        with open(self.paths["STATE"], encoding="utf-8") as f:
            self.assertNotEqual(json.load(f).get("last_run"), "20260702")   # 未推进

    def test_held_stock_without_today_bar_marks_stale_and_logs_event(self):
        """复审二轮(0719)：个股持仓当日无K线→NAV照记但stale_px_codes显式标记+事件留痕。"""
        st = ledger.ensure_state({}, 500000)
        st["A"]["open"] = [{"code": "600001", "name": "甲", "board": "main", "shares": 100,
                            "entry_date": "20260701", "entry": 10.0, "stop": 9.0, "target": 12.0,
                            "half": False, "hold": 0, "last_px": 10.0, "entry_shares": 100,
                            "cost_basis": 1000.0, "buy_px": 10.0, "actual_risk_amt": 100.0}]
        with open(self.paths["STATE"], "w", encoding="utf-8") as f:
            json.dump(st, f)
        raw = ('window.STRATEGY_DATA = {"data_date": "2026-07-02", "state": {"cap": 0, "can_open": false},'
               ' "base": {}, "candidates": []};')
        datapath = os.path.join(self.tmp.name, "data.js")
        with open(datapath, "w", encoding="utf-8") as f:
            f.write(raw)
        bars_no_today = pd.DataFrame([{"trade_date": "20260701", "open": 10, "high": 10.2,
                                       "low": 9.9, "close": 10.0}])
        with mock.patch.object(shadow.C, "DATA_JS_PATH", datapath), \
             mock.patch.object(shadow, "daily_bars", return_value=bars_no_today), \
             mock.patch.object(shadow.P, "_recent_trade_dates", return_value=["20260702"]):
            shadow.main(today="20260702")
        nav = pd.read_csv(self.paths["NAV"], dtype=str)
        self.assertIn("600001", str(nav.iloc[-1]["stale_px_codes"]))   # 显式标记
        events = pd.read_csv(self.paths["EVENTS"])
        self.assertIn("当日无K线-沿用旧价(原因待确认)", set(events["事件"]))

    def _rerun_scene(self, prior_A_action, state_mutator=None):
        """构造补跑场景：既有快照+可控状态，返回运行后的产物路径检查闭包。"""
        st = ledger.ensure_state({}, 500000)
        cands = [
            {"code": "600001", "name": "甲", "score": 99, "sec_rank": 1, "rs": 1, "prior60": -1,
             "amt20_yi": 3, "board": "main", "stop_price": 9.0, "close": 10.0},
            {"code": "600002", "name": "乙", "score": 80, "sec_rank": 2, "rs": 1, "prior60": -1,
             "amt20_yi": 3, "board": "main", "stop_price": 9.0, "close": 10.0},
        ]
        raw = ('window.STRATEGY_DATA = {"data_date": "2026-07-02", "state": {"cap": 40, "can_open": true},'
               ' "base": {}, "candidates": ' + json.dumps(cands, ensure_ascii=False) + '};')
        datapath = os.path.join(self.tmp.name, "data.js")
        with open(datapath, "w", encoding="utf-8") as f:
            f.write(raw)
        d = json.loads(raw[raw.find("{"):raw.rfind("}") + 1])
        base_action = {"queued_code": None, "queued_name": None, "held_excluded": [],
                       "eligible_after_exclusion": 2, "skip_reason": "state_can_open_false"}
        actions0 = {"A": prior_A_action, "C": dict(base_action), "R": dict(base_action)}
        shadow.write_decision_snapshot("20260702", d, raw, actions0)
        if state_mutator:
            state_mutator(st)
        with open(self.paths["STATE"], "w", encoding="utf-8") as f:
            json.dump(st, f)
        bars = pd.DataFrame([{"trade_date": "20260702", "open": 10, "high": 10.5, "low": 9.9, "close": 10.2}])
        with mock.patch.object(shadow.C, "DATA_JS_PATH", datapath), \
             mock.patch.object(shadow, "daily_bars", return_value=bars), \
             mock.patch.object(shadow.P, "_recent_trade_dates", return_value=["20260702"]):
            shadow.main(today="20260702")

    def test_rerun_halts_when_full_actual_differs_even_if_queued_code_same(self):
        """复审三轮(0719)：queued_code相同但skip_reason不同→仍须停跑。"""
        # 快照：queued=None因pending_entry_exists；重算：queued=600001(排队成功)——queued不同必停已有覆盖；
        # 这里构造 queued 都为 None 但 skip_reason 不同：快照=pending_entry_exists，重算=portfolio_full
        prior = {"queued_code": None, "queued_name": None, "held_excluded": [],
                 "eligible_after_exclusion": 2, "skip_reason": "pending_entry_exists"}
        def mut(st):
            st["A"]["open"] = [{"code": f"60000{i}", "shares": 100, "entry_date": "20260701",
                                "entry": 10.0, "stop": 9.0, "target": 12.0, "half": True, "hold": 1,
                                "last_px": 10.0} for i in (3, 4, 5)]   # 满仓→重算skip=portfolio_full
        self._rerun_scene(prior, mut)
        self.assertFalse(os.path.exists(self.paths["NAV"]))
        with open(self.paths["STATE"], encoding="utf-8") as f:
            self.assertNotEqual(json.load(f).get("last_run"), "20260702")

    def test_rerun_divergence_leaves_zero_disk_side_effects(self):
        """复审三轮(0719)：背离停跑时，交割/事件/底仓成交一律不得落盘（含他流的平仓）。"""
        prior = {"queued_code": "600001", "queued_name": "甲", "held_excluded": [],
                 "eligible_after_exclusion": 2, "skip_reason": "queued"}
        def mut(st):
            # C流有一笔将在今日触发止损确认次日开盘卖的持仓（bar中close 10.2>stop不触发…改用exit_next_open直接触发平仓）
            st["C"]["open"] = [{"code": "600009", "name": "丙", "board": "main", "shares": 100,
                                "entry_date": "20260701", "entry": 10.0, "stop": 9.0, "target": 12.0,
                                "half": False, "hold": 0, "exit_next_open": "止损", "last_px": 10.0,
                                "entry_shares": 100, "cost_basis": 1000.0, "buy_px": 10.0,
                                "actual_risk_amt": 100.0}]
            # A流持有甲→重算将排乙→与快照(甲)背离
            st["A"]["open"] = [{"code": "600001", "shares": 100, "entry_date": "20260701",
                                "entry": 10.0, "stop": 9.0, "target": 12.0, "half": False, "hold": 0,
                                "last_px": 10.0}]
        self._rerun_scene(prior, mut)
        self.assertFalse(os.path.exists(self.paths["TRADES"]))       # C流平仓未落盘
        self.assertFalse(os.path.exists(self.paths["BASE_TRADES"]))
        self.assertFalse(os.path.exists(self.paths["NAV"]))
        with open(self.paths["STATE"], encoding="utf-8") as f:
            st_after = json.load(f)
        self.assertNotEqual(st_after.get("last_run"), "20260702")
        self.assertEqual(len(st_after["C"]["open"]), 1)              # 状态文件原样

    def test_recovery_check_failure_keeps_lock_and_state(self):
        """复审三轮(0719)：核对发现问题→不解锁、状态文件不变；--force-unlock才可带病解锁。"""
        st = ledger.ensure_state({}, 500000)
        st["last_run"] = "20260701"
        st["recovery_required"] = {"at": "2026-07-19 17:00", "quarantine": "x"}
        with open(self.paths["STATE"], "w", encoding="utf-8") as f:
            json.dump(st, f)
        # 制造问题：交割表存在晚于恢复点的平仓
        pd.DataFrame([{"流": "A", "开仓日": "20260625", "代码": "600001", "名称": "甲",
                       "平仓日": "20260715", "R": 1.0}]).to_csv(self.paths["TRADES"], index=False,
                                                              encoding="utf-8-sig")
        with open(self.paths["STATE"], encoding="utf-8") as f:
            before = f.read()
        self.assertFalse(shadow.confirm_recovery())                  # 不解锁
        with open(self.paths["STATE"], encoding="utf-8") as f:
            self.assertEqual(f.read(), before)                       # 状态未动
        self.assertTrue(shadow.confirm_recovery(force=True))         # 人工确认后强制解锁
        with open(self.paths["STATE"], encoding="utf-8") as f:
            self.assertNotIn("recovery_required", json.load(f))

    def test_commit_marker_blocks_next_run_until_cleared(self):
        """复审四轮(0719)：提交中途故障→COMMIT_MARK保留→下次运行停跑；删除后可继续。"""
        st = ledger.ensure_state({}, 500000)
        with open(self.paths["STATE"], "w", encoding="utf-8") as f:
            json.dump(st, f)
        raw = ('window.STRATEGY_DATA = {"data_date": "2026-07-02", "state": {"cap": 0, "can_open": false},'
               ' "base": {}, "candidates": []};')
        datapath = os.path.join(self.tmp.name, "data.js")
        with open(datapath, "w", encoding="utf-8") as f:
            f.write(raw)
        with mock.patch.object(shadow.C, "DATA_JS_PATH", datapath), \
             mock.patch.object(shadow.P, "_recent_trade_dates", return_value=["20260702"]):
            # 注入：NAV写入失败 → COMMIT_MARK应保留、last_run不推进
            with mock.patch.object(shadow, "write_nav", side_effect=OSError("disk full")):
                shadow.main(today="20260702")
            self.assertTrue(os.path.exists(shadow.COMMIT_MARK))
            with open(self.paths["STATE"], encoding="utf-8") as f:
                self.assertNotEqual(json.load(f).get("last_run"), "20260702")
            # 标记存在→下次运行直接停（不产生NAV）
            shadow.main(today="20260702")
            self.assertFalse(os.path.exists(self.paths["NAV"]))
            # 人工核对后删除标记→幂等补跑成功
            os.remove(shadow.COMMIT_MARK)
            shadow.main(today="20260702")
        self.assertTrue(os.path.exists(self.paths["NAV"]))
        self.assertFalse(os.path.exists(shadow.COMMIT_MARK))

    def test_save_state_never_rotates_corrupt_primary_into_backup(self):
        """复审修复(0719)：损坏主文件绝不覆盖好备份。"""
        good = {"A": {"open": []}, "C": {"open": []}, "last_run": "20260701"}
        with open(self.paths["STATE"] + ".bak", "w", encoding="utf-8") as f:
            json.dump(good, f)
        with open(self.paths["STATE"], "w", encoding="utf-8") as f:
            f.write("broken")
        shadow.save_state({"last_run": "20260702"})
        with open(self.paths["STATE"] + ".bak", encoding="utf-8") as f:
            self.assertEqual(json.load(f)["last_run"], "20260701")   # 备份仍是好的
        with open(self.paths["STATE"], encoding="utf-8") as f:
            self.assertEqual(json.load(f)["last_run"], "20260702")   # 主文件是新状态

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
        shadow._flush_staged()   # 复审三轮：副作用事务化，单测需显式提交
        trades = pd.read_csv(self.paths["TRADES"])
        self.assertEqual(str(trades.iloc[0]["平仓日"]), "20260704")
        self.assertAlmostEqual(float(trades.iloc[0]["平仓价"]), 93.0)

    def test_decision_snapshot_is_append_only(self):
        data = {"data_date": "2026-07-02", "generated_at": "18:31", "state": {"cap": 40},
                "base": {}, "candidates": []}
        actions = {k: {"queued_code": None, "skip_reason": "state_can_open_false",
                       "held_excluded": [], "eligible_after_exclusion": 0} for k in ("A", "C", "R")}
        self.assertFalse(shadow.check_snapshot_conflict("20260702", "raw-one"))
        shadow.write_decision_snapshot("20260702", data, "raw-one", actions)
        # 同日同输入：冲突检查返回True=免写
        self.assertTrue(shadow.check_snapshot_conflict("20260702", "raw-one"))
        shadow.write_decision_snapshot("20260702", data, "raw-one", actions, skip_write=True)
        with open(self.paths["DECISIONS"], encoding="utf-8") as f:
            lines = f.readlines()
        self.assertEqual(len(lines), 1)
        snap = json.loads(lines[0])
        self.assertEqual(snap["input_hash"], snap["data_sha256"])
        self.assertIn("strategy_commit", snap)
        self.assertEqual(snap["decisions"]["A"]["decision_id"], "20260702-A-v2")
        self.assertEqual(snap["decisions"]["A"]["skip_reason"], "state_can_open_false")
        # 同日输入变化：拒绝
        with self.assertRaises(RuntimeError):
            shadow.check_snapshot_conflict("20260702", "raw-two")

    def test_snapshot_actual_action_matches_queue_when_top1_already_held(self):
        """复审修复(0719)：快照的实际动作必须与真实排队一致（含已持有排除）。"""
        st = ledger.ensure_state({}, 500000)
        st["A"]["open"] = [{"code": "600001", "shares": 100}]
        cands = [
            {"code": "600001", "name": "甲", "score": 99, "sec_rank": 1, "rs": 1, "prior60": -1, "amt20_yi": 3},
            {"code": "600002", "name": "乙", "score": 80, "sec_rank": 2, "rs": 1, "prior60": -1, "amt20_yi": 3},
        ]
        action = shadow._queue_new_entry("A", st, "20260702", cands, True, 40)
        self.assertEqual(action["queued_code"], "600002")
        self.assertEqual(action["skip_reason"], "queued")
        self.assertIn("600001", action["held_excluded"])
        data = {"data_date": "2026-07-02", "generated_at": "18:31", "state": {"cap": 40, "can_open": True},
                "base": {}, "candidates": cands}
        shadow.write_decision_snapshot("20260702", data, "raw-x", {"A": action, "C": None, "R": None})
        with open(self.paths["DECISIONS"], encoding="utf-8") as f:
            snap = json.loads(f.readlines()[0])
        rec = snap["decisions"]["A"]
        self.assertEqual(rec["raw_top1"], "600001")                       # 原始排名第一=已持有的甲
        self.assertEqual(rec["actual"]["queued_code"], "600002")          # 实际排队=乙，两者并存不背离
        self.assertEqual(st["A"]["pending_entry"]["code"], "600002")

    def test_missing_base_price_fails_closed_without_nav(self):
        """复审修复(0719)：底仓价格缺失→当日不交易不记账（无NAV行），事件留痕。"""
        st = ledger.ensure_state({}, 500000)
        st["accounts"]["base"]["base"] = {"code": "510300", "shares": 1000, "last_px": 5.0}
        with open(self.paths["STATE"], "w", encoding="utf-8") as f:
            json.dump(st, f)
        data_js = ('window.STRATEGY_DATA = {"data_date": "2026-07-02", "state": {"cap": 40, "can_open": false},'
                   ' "base": {"etf": "510300", "weight": 30}, "candidates": []};')
        datapath = os.path.join(self.tmp.name, "data.js")
        with open(datapath, "w", encoding="utf-8") as f:
            f.write(data_js)
        with mock.patch.object(shadow.C, "DATA_JS_PATH", datapath), \
             mock.patch.object(shadow, "fund_close", return_value=None), \
             mock.patch.object(shadow.P, "_recent_trade_dates", return_value=["20260702"]):
            shadow.main(today="20260702")
        self.assertFalse(os.path.exists(self.paths["NAV"]))               # 未写NAV
        events = pd.read_csv(self.paths["EVENTS"])
        self.assertIn("行情缺失-失败关闭", set(events["事件"]))

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
