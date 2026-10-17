# -*- coding: utf-8 -*-
"""Credential-free example configuration; copy to ignored config.py only in a new deployment.
Capital is an illustrative default, not a personal account balance.
"""
import os as _os
TUSHARE_TOKEN = _os.environ.get("TUSHARE_TOKEN", "")
DISCORD_WEBHOOK = _os.environ.get("DISCORD_WEBHOOK", "")

DATA_SOURCE = "auto"

# ========= 2. 可交易范围（股票池硬规则，对齐手册 §1）=========
PRICE_MIN = 4.0          # 低于此价不做（仙股）
PRICE_MAX = 80.0         # 高于此价不做（单手占用大；科创板普遍高价已放宽到80）
MIN_AMOUNT_20D = 2e8     # 近20日日均成交额下限（元），低于则流动性差不做
MIN_LIST_DAYS = 60       # 上市不满N个交易日的次新不做
EXCLUDE_ST = True        # 排除 ST / *ST
EXCLUDE_BSE = True       # 排除北交所(8/4开头)

# AKShare 兜底模式下，只筛这个自选清单（代码,如 "600519" "300750" "688111"）
# 因为 AKShare 免费源无法承受全市场逐只拉取。Tushare 模式自动全市场扫描，忽略此项。
WATCHLIST = []  # Set a private watchlist in your ignored config.py.

# ========= 3. 板块差异化参数（对齐手册 §6）=========
# stop=止损宽度  cap=单票上限(占总资金)  lot=最小手数  gap=高开放弃阈值
BOARDS = {
    "main":    {"name": "主板",   "stop": 0.05, "cap": 0.20, "lot": 100, "gap": 0.04},
    "chinext": {"name": "创业板", "stop": 0.08, "cap": 0.12, "lot": 100, "gap": 0.07},
    "star":    {"name": "科创板", "stop": 0.08, "cap": 0.12, "lot": 200, "gap": 0.07},
}
EXPOSURE_20CM_CAP = 0.30   # 创业板+科创板 合计敞口上限

# ========= 4. 资金与风险（对齐手册 §3/§6）=========
DEFAULT_CAPITAL = 100000  # Example only; not the user account balance.
RISK_PCT = 0.0075          # 单笔风险 = 总资金 × 0.75%

# ========= 5. 选股参数（对齐手册 §4）=========
SCREEN = {
    "pullback_band": 0.03,     # 回踩判定：收盘在 MA10 ±3% 内
    "shrink_ratio": 1.0,       # 缩量：当日量 < 5日均量 × 此系数
    "fund_lookback": 20,       # 资金参与回看天数
    "fund_big_yang_pct": 0.05, # “放量大阳”涨幅阈值
    "fund_big_yang_vol": 2.0,  # “放量大阳”量能倍数（>前一日×2）
    "rfgs_lookback": 10,       # 红肥绿瘦回看天数
    "rfgs_ratio": 1.2,         # 阳线实体均值 ≥ 阴线实体均值 × 此系数
    "long_yin_pct": 0.05,      # 放量长阴：跌幅>5% 且放量 视为破位
    "use_industry_gate": True, # 主线/板块门：个股所属行业指数 > 行业MA20（需更高积分；缺数据自动跳过）
}

# 只抱最强主线：只在"按20日涨幅排名前 N 的板块"里选股（回测验证：窄市里能把期望从0.02拉到0.58）。
# 设 0 关闭（做所有过门板块）；建议 3–8。
TOP_SECTORS = 5

# 卫星层开仓资格门（2026-07-03 复核Codex Alpha后采纳，手册v6.3）：
#   "codexA" = 仅做回踩修复型：主线排名≤5 且 RS>0 且 60日涨幅<0 且 20日日均成交额2-5亿
#              （双窗口复核：样本内+50.7%/-7.2%、样本外-4.6%/-16.5%，均优于旧门与纯底仓；
#               证据等级=历史筛选所得，非预注册验证，最终裁判是前向记账）
#   "classic" = 旧门（全部过§4筛选的候选）。门只作用于尾盘信号执行层，data.js候选池保持完整（前向对照用）。
SATELLITE_GATE = "codexA"

# 核心战略主线白名单（AI/算力等结构性主线，长期国家战略，不只看短期动量）：
# 享受更宽的排名门（排到 ≤CORE_RANK 也保留，而非掉出前TOP_SECTORS就被踢）+ 评分加分。
# 行业名用 Tushare 口径——对照工具「📡数据」里"主线(排名)"列看到的名字增删；设 [] 关闭。
# 提醒：这是一个"押注该主线不退潮"的主观判断；若它彻底走坏(排名>CORE_RANK)，动量网仍会把你救出来。
# v6.4.1：行业分类源迁移到申万2021-L2（时点成分），白名单同步映射（旧→新：元器件→元件、IT设备/电脑设备→计算机设备、
# 软件服务→软件开发+IT服务Ⅱ、互联网→互联网电商；消费电子为AI硬件候选可自行增删）
CORE_THEMES = ["半导体", "元件", "通信设备", "计算机设备", "软件开发", "IT服务Ⅱ", "光学光电子", "互联网电商", "通信服务"]
CORE_RANK = 10      # 白名单板块排名 ≤ 此值即保留（普通板块要 ≤ TOP_SECTORS）
CORE_BONUS = 6      # 白名单候选评分加分（封顶100）

# ========= 6. 指数代码（市场状态/板块门，对齐手册 §3）=========
IDX_HS300 = "000300.SH"    # 沪深300：大盘趋势
IDX_GEM   = "399006.SZ"    # 创业板指：创业板状态门
IDX_STAR  = "000688.SH"    # 科创50：科创板状态门

# ========= 7. 服务 =========
SERVER_HOST = "127.0.0.1"
SERVER_PORT = 8787
# data.js 与 HTML 放在上级目录（与 .html 同目录），HTML 离线也能读
import os
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HTML_NAME = "A股短线波段操作助手.html"
DATA_JS_PATH = os.path.join(BASE_DIR, "data.js")
