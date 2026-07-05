# -*- coding: utf-8 -*-
"""
失效判据（手册修订提案-2026-07-03 提案1 · 机械执行）
读 交割记录.csv（项目根目录），计算卫星层滚动期望，输出三档状态：

  正常          ：最近60笔平均R ≥ 0（或样本不足60笔）
  R减半+降档    ：最近60笔平均R < 0
  停做          ：最近60笔平均R < 0 且 20笔之前的"当时最近60笔"平均R 也 < 0
                  （= 连续两个检查点失败的无状态等价形式，检查点间隔20笔）

交割记录.csv 格式（表头固定，UTF-8，每平仓一笔加一行）：
  平仓日期,代码,名称,R倍数,备注
  20260703,600000,浦发银行,-1.0,止损
R倍数 = 该笔净盈亏 ÷ 该笔计划风险额（手册§6：R=总资金×0.75%）。卖一半分两行或合计一行均可，口径自己保持一致。

被 尾盘信号.py 每日调用；也可单独运行查看当前状态：
  ./.venv/bin/python 失效判据.py
"""
import os, sys
import pandas as pd

CSV = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "交割记录.csv")
N_ROLL, N_STEP = 60, 20

def evaluate(csv_path=CSV):
    """返回 dict(level, text)；level: 0=正常 1=减半降档 2=停做 -1=无记录/样本不足"""
    if not os.path.exists(csv_path):
        return dict(level=-1, n=0, mean60=None,
                    text="📒 失效判据：未找到 交割记录.csv（在项目根目录建立后自动启用）")
    try:
        df = pd.read_csv(csv_path, dtype={"平仓日期": str})
        r = pd.to_numeric(df["R倍数"], errors="coerce").dropna().values
    except Exception as e:
        return dict(level=-1, n=0, mean60=None, text=f"📒 失效判据：交割记录.csv 读取失败（{str(e)[:40]}）")
    n = len(r)
    if n < N_ROLL:
        m = r.mean() if n else None
        return dict(level=-1, n=n, mean60=None,
                    text=f"📒 失效判据：累计 {n}/60 笔（样本不足，暂不启用"
                         + (f"；当前全部均值 {m:+.3f}R" if m is not None else "") + "）")
    m_now = r[-N_ROLL:].mean()
    if m_now >= 0:
        return dict(level=0, n=n, mean60=m_now,
                    text=f"📒 失效判据：✅ 正常（近60笔期望 {m_now:+.3f}R，共{n}笔）")
    if n >= N_ROLL + N_STEP and r[-(N_ROLL + N_STEP):-N_STEP].mean() < 0:
        m_prev = r[-(N_ROLL + N_STEP):-N_STEP].mean()
        return dict(level=2, n=n, mean60=m_now,
                    text=f"📒 失效判据：⛔ **卫星层停做**（近60笔 {m_now:+.3f}R，20笔前检查点 {m_prev:+.3f}R，"
                         f"连续两点为负）。今日起不开新仓，转模拟盘复盘，直至滚动期望回正。")
    return dict(level=1, n=n, mean60=m_now,
                text=f"📒 失效判据：⚠️ **R减半+档位降一档**（近60笔期望 {m_now:+.3f}R < 0）。"
                     f"再连续负20笔将触发停做。")

if __name__ == "__main__":
    print(evaluate()["text"])
