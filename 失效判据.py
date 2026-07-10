# -*- coding: utf-8 -*-
"""
失效判据 v2（2026-07-10，外部审查P2改造）——快慢双层 + 实盘/影子分离，解除v1两个缺陷：
  v1缺陷①：60笔判据按实盘频率要3年+才启用；②：停做后实盘记录停增→"回正自动恢复"死锁。

数据源分离：
  实盘流 = 项目根目录 交割记录.csv（用户手动维护）→ 只喂**快开关**（控真实风险，反应快）
  影子流 = 数据助手/影子交割.csv（影子交割.py每日机械执行，A流）→ 喂**慢判据**（统计性，样本积累不依赖实际下单，停做期间照跑→可自动恢复）

判线（v2预注册起点，前向校准，不得因单次结果回调）：
  快开关F1：实盘连续5笔亏损（R<0）→ R减半+档位降一档
  快开关F2：实盘最近10笔累计R ≤ -6 → 卫星停做
  慢判据S1：影子A流滚动40笔平均R < 0 → R减半+档位降一档
  慢判据S2：影子A流连续两个检查点（每20笔）均值 < 0 → 卫星停做
  恢复：处于停做时，影子A流最近20笔平均R > 0 → 自动恢复正常
  合成：停做 > 减半 > 正常，实盘/影子取更严者；样本不足的层不启用（如实显示）。
账户回撤类熔断（-8%/-15%）系统看不到权益，仍由人工执行（手册§6.7）。

被 尾盘信号.py / pipeline._assemble 调用；单独运行查看状态：./.venv/bin/python 失效判据.py
"""
import os
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
CSV_REAL = os.path.join(os.path.dirname(HERE), "交割记录.csv")
CSV_SHADOW = os.path.join(HERE, "影子交割.csv")
F1_N, F2_N, F2_SUM = 5, 10, -6.0
S1_N, S2_STEP, REC_N = 40, 20, 20

def _rs(path, col):
    if not os.path.exists(path):
        return None
    try:
        df = pd.read_csv(path)
        return pd.to_numeric(df[col], errors="coerce").dropna().values
    except Exception:
        return None

def evaluate(csv_path=None):
    """返回 dict(level, n, mean60, text)。level: 0正常/1减半/2停做/-1无数据。（兼容v1字段名）"""
    real = _rs(csv_path or CSV_REAL, "R倍数")
    sh_all = None
    if os.path.exists(CSV_SHADOW):
        try:
            df = pd.read_csv(CSV_SHADOW)
            sh_all = pd.to_numeric(df.loc[df["流"] == "A", "R"], errors="coerce").dropna().values
        except Exception:
            pass
    parts, level = [], 0
    # ---- 快开关（实盘）----
    n_real = len(real) if real is not None else 0
    if n_real >= F1_N and all(r < 0 for r in real[-F1_N:]):
        level = max(level, 1); parts.append(f"⚠️F1实盘连亏{F1_N}笔→减半")
    if n_real >= F2_N and real[-F2_N:].sum() <= F2_SUM:
        level = max(level, 2); parts.append(f"⛔F2实盘近{F2_N}笔累计{real[-F2_N:].sum():+.1f}R→停做")
    # ---- 慢判据（影子A流）----
    n_sh = len(sh_all) if sh_all is not None else 0
    m40 = None
    if n_sh >= S1_N:
        m40 = sh_all[-S1_N:].mean()
        if m40 < 0:
            level = max(level, 1); parts.append(f"⚠️S1影子40笔均{m40:+.3f}R→减半")
        if n_sh >= S1_N + S2_STEP and sh_all[-(S1_N + S2_STEP):-S2_STEP].mean() < 0 and m40 < 0:
            level = max(level, 2); parts.append(f"⛔S2影子连续两检查点为负→停做")
    # ---- 恢复（停做时影子达标则降回）----
    if level == 2 and n_sh >= REC_N and sh_all[-REC_N:].mean() > 0:
        level = 1
        parts.append(f"↩️影子近{REC_N}笔均{sh_all[-REC_N:].mean():+.3f}R>0→解除停做(暂维持减半)")
    status = {0: "✅ 正常", 1: "⚠️ **R减半+档位降一档**", 2: "⛔ **卫星层停做**"}[level]
    txt = (f"📒 失效判据v2：{status}（实盘{n_real}笔"
           + (f"｜影子A流{n_sh}笔" + (f"·40笔均{m40:+.3f}R" if m40 is not None else "·样本积累中") if n_sh else "｜影子流未启动")
           + "）" + ("；".join([""] + parts) if parts else ""))
    if n_real == 0 and n_sh == 0:
        return dict(level=-1, n=0, mean60=None, text="📒 失效判据v2：实盘/影子均无记录（影子流每日18:55自动积累）")
    return dict(level=level, n=n_real, mean60=m40, text=txt)

if __name__ == "__main__":
    print(evaluate()["text"])
