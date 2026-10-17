# 均线之花筹码峰四节课 NBLM 原味蒸馏

Generated: 2026-07-03
Channel: 均线之花
Method: NotebookLM imported YouTube sources, then source-bounded distillation
NotebookLM notebook: https://notebooklm.google.com/notebook/ba57e621-5e37-4d9c-9286-b5d1e62845bd

## Source Integrity

Direct YouTube subtitle extraction was tested first. `yt-dlp --list-subs` reported no public subtitles and no automatic captions for all four videos. The NotebookLM route was then tested through the logged-in Chrome session. NotebookLM accepted all four YouTube URLs as sources, displayed `4 sources`, and generated transcript-based source summaries and cited answers.

Evidence captures:

- `/Users/cuiyong/.codex/skills/youtube-investor-distiller/references/.subtitle-cache/junxianzhihua-chip-peak-four-videos-2026-07-03/nblm-full-page-capture-1.txt`
- `/Users/cuiyong/.codex/skills/youtube-investor-distiller/references/.subtitle-cache/junxianzhihua-chip-peak-four-videos-2026-07-03/nblm-full-page-capture-lesson1.txt`

This document does not invent rules from titles. It is based on NotebookLM's transcript-grounded answer, with NBLM citation numbers preserved where useful. It is not a verbatim full subtitle export.

## Source List

| Order | Video ID | Title | Duration | Upload Date | Status |
|---:|---|---|---:|---|---|
| 1 | `xTRvibpgEZg` | 第一节. 筹码峰单峰突破战法 | 55:13 | 2023-11-08 | NBLM source imported |
| 2 | `VnXooLWbluI` | 第二节. 成功率最高的股票K线双响炮 | 50:16 | 2023-11-08 | NBLM source imported |
| 3 | `jjNs4UuI6T4` | 第三节. 股票筹码峰一线天绝招 | 48:13 | 2023-11-08 | NBLM source imported |
| 4 | `LngmTmf-2gc` | 第四节. 筹码峰双峰填谷选股战法 | 44:30 | 2023-11-09 | NBLM source imported |

## Batch Thesis

这四节课是一套围绕“筹码峰识别主力行为”的短线/波段体系：先用筹码集中度和单峰密集判断主力是否已完成吸筹，再用放量突破、涨停结构、一线天、双峰填谷来判断是否进入可交易的启动点。讲师的核心假设不是消息面或基本面，而是“股价上涨来自主力存在及主力愿意拉升”；因此所有规则都围绕三个问题展开：

1. 主力是否在场。
2. 主力是否完成筹码收集或换手。
3. 当前买入点是否已经突破阻力，且风险位置清晰。

## 第一节：筹码峰单峰突破战法

### Core Theme

通过筹码分布识别主力在低位吸筹完成后的主升浪临界点。核心不是看到单峰就买，而是等待“低位单峰密集 + 放量突破 + 上方阻力消失”的组合。

### 原始逻辑链

- 股价上涨不是因为散户齐心，而是因为有主力并且主力愿意拉升。NBLM citations: 4, 5, 11.
- 筹码分布被视为追踪主力行为的核心工具；讲师强调筹码比消息和短期价格更接近资金真实状态。NBLM citations: 6, 109.
- 主力吸筹通常会在低位形成单峰密集。因为散户成本分散，很难自然形成高度一致的持仓成本。NBLM citations: 19, 35, 36.
- 单峰密集本身只是“主力可能收集完毕”，还不是买入信号；必须等待股价突破筹码密集区。NBLM citations: 41, 45.
- 上方仍有大量套牢筹码时，反弹容易被抛压压制；上方筹码峰消失，阻力才明显下降。NBLM citations: 42, 44.

### Copyable Trading Rule

| Module | Rule |
|---|---|
| Stock Pool | 低位、长期横盘震荡、筹码集中到单峰的个股。 |
| Chip Condition | 筹码峰呈单峰密集，形态类似尖锐的集中峰；90% 和 70% 筹码集中度都小于 10%，数值越小越好。NBLM citation: 23. |
| Volume Condition | 突破时需要成倍或数倍放量，不能只是无量站上。NBLM citations: 27, 46. |
| Entry 1 | 股价放量突破单峰密集最高点，且筹码峰在股价下方。NBLM citations: 27, 28. |
| Entry 2 | 突破后缩量回踩 10 日线或 20 日线，仍不破结构时介入。NBLM citations: 29, 31. |
| Entry 3 | 长时间横盘后当天直接突破的，讲师允许当天买入。NBLM citations: 33, 34. |
| Position | 波段首建约 2 成仓；后续加仓规则文字稿未明确。NBLM citation: 34. |
| Exit / Stop | 文字稿未给精确止损百分比；核心风险信号是上方筹码峰不消失、突破失败、形态走坏。 |
| Filter | 上方存在大量绿色套牢盘或上峰仍压制时，不做。NBLM citation: 42. |
| Misuse | 只看到单峰密集就提前买，容易买在主力尚未拉升的等待期。NBLM citation: 45. |

### Thresholds / Parameters

- 90% 筹码集中度小于 10%。
- 70% 筹码集中度小于 10%。
- 集中度越小，筹码越集中。
- 关键均线：10 日线、20 日线用于回踩买点。
- 明确止损百分比：文字稿未明确。

### Review Fields

- 当前是否低位。
- 横盘时间是否足够长。
- 90%/70% 筹码集中度数值是多少。
- 是否从多峰变成单峰密集。
- 突破日是否倍量。
- 股价是否站在筹码峰上方。
- 上方是否还有明显套牢峰。
- 回踩 10/20 日线时是否缩量。

## 第二节：涨停双响炮与上升元阳

### Core Theme

这节把筹码逻辑推进到短线爆发形态：通过“涨停 + 洗盘 + 再涨停”或“阴线洗盘 + 阳线反包”识别主力洗盘结束后的快速拉升段。

### 原始逻辑链

- 涨停板被当作市场强信号，代表主力主动进攻。NBLM citations: 61, 64.
- 双响炮结构是前后两个涨停，中间夹杂震荡或洗盘 K 线；第二个涨停意味着主力完成洗盘并再次发动。NBLM citations: 62, 65.
- 上升元阳是另一类快速震仓后的反包结构，重在识别阴线恐慌后的阳线修复。NBLM citation: 85.
- 该类战法偏短线，讲师强调 3-5 天内看结果，不涨即走。NBLM citations: 78, 89.

### Copyable Trading Rule

| Module | Rule |
|---|---|
| Stock Pool | 低位启动或横盘后出现涨停的个股。NBLM citation: 62. |
| Double Cannon Shape | 两个涨停板，中间夹杂震荡 K 线或洗盘 K 线。NBLM citation: 62. |
| Rising Yuan Yang Shape | 一根中大阴线后接中大阳线，形成阳包阴。NBLM citation: 84. |
| Volume | 上升元阳中，阳线量能必须明显大于阴线量能。NBLM citations: 84, 89. |
| Entry: Double Cannon | 第二个涨停后的次日，开盘高开不超过 5%，或回踩时介入。NBLM citations: 65, 80. |
| Entry: Yuan Yang | 阳包阴当天尾盘，或次日回踩不破阳线实体一半时介入。NBLM citation: 88. |
| Stop: Double Cannon | 跌破两个涨停板中较低那个涨停板的开盘价。NBLM citations: 81, 82. |
| Stop: Yuan Yang | 回踩跌破组合底部，即最低开盘价。NBLM citations: 89, 90. |
| Take Profit | 短线持股 3-5 天，不涨即走。NBLM citations: 78, 89. |
| Filter | 两个涨停收盘价差过大则过滤，避免追高。NBLM citation: 79. |

### Thresholds / Parameters

- 双响炮两个涨停收盘价差：主板小于 10%。
- 双响炮两个涨停收盘价差：创业板小于 20%。
- 第二个涨停后次日高开：不超过 5% 更适合介入。
- 上升元阳阴线与阳线涨跌幅：均需大于 4%。
- 持股周期：3-5 天。

### Review Fields

- 两个涨停之间是否存在洗盘而非直接连续加速。
- 第二个涨停是否重新确认强度。
- 两个涨停收盘价差是否超过阈值。
- 次日高开是否超过 5%。
- 上升元阳阳线量能是否大于阴线量能。
- 止损位是否能明确落在较低涨停板开盘价或组合底部。

## 第三节：筹码峰一线天绝招

### Core Theme

用“一线天”筹码形态判断涨停或连板中的主力抢筹是否真实。它不是追所有强势股，而是追“涨停位置大量换手、筹码突然集中成顶格直线”的强中选强。

### 原始逻辑链

- 连板股不敢追的原因是看不懂主力是否真实抢筹；筹码可以帮助确认。NBLM citations: 104, 114.
- “一线天”是筹码分布中出现一条顶格直线，周围筹码极少，表示涨停位置出现集中成交。NBLM citations: 114, 116.
- 涨停当天必须放量；无量一字板不能作为有效一线天。NBLM citation: 115.
- 该战法以短线为主，次日高开不高时介入，3-4 天内看结果。NBLM citations: 122, 127.

### Copyable Trading Rule

| Module | Rule |
|---|---|
| Stock Pool | 相对低位启动的涨停股，可包括一字板、T 字板、实体板，但必须能看到有效成交。NBLM citation: 116. |
| Chip Condition | 筹码分布出现一条软件中显示为最长的顶格直线，周围筹码极少。NBLM citations: 114, 116. |
| Volume Condition | 涨停当天必须放量；无量一字板无效。NBLM citation: 115. |
| Entry | 次日高开小于 5% 以内介入。NBLM citations: 122, 127. |
| Position | 单只约 1 成仓，偏短线试错。NBLM citation: 122. |
| Take Profit | 持股 3-4 天，或涨停封不住时离场。NBLM citation: 127. |
| Stop 1 | 跌破 20 日均线。NBLM citation: 128. |
| Stop 2 | 买入后 2 天内不向上突破一线天筹码峰则离场。NBLM citation: 128. |
| Filter | 次日高开超过 5% 不追；上方有重压套牢盘时谨慎。NBLM citations: 120, 127. |
| Misuse | 把无量一字板、无成交涨停、或上方重压结构误判为可追的一线天。 |

### Thresholds / Parameters

- 次日高开：小于 5%。
- 持股周期：3-4 天。
- 失败判定：买入后 2 天内不向上突破一线天筹码峰。
- 止损参考：20 日均线。
- “顶格”具体像素或百分比：文字稿未明确，只强调软件显示最长线且只有一条。

### Review Fields

- 涨停当天是否放量。
- 是否是真正低位或相对低位启动。
- 筹码是否形成顶格单线。
- 周围是否仍有大量分散筹码。
- 次日高开是否小于 5%。
- 买入后 2 天是否继续向上突破。
- 涨停是否封不住。
- 上方是否有套牢峰压制。

## 第四节：筹码峰双峰填谷选股战法

### Core Theme

通过“上方套牢峰 + 下方获利峰”之间的筹码转移，识别第一波上涨后的二波主升启动点。重点是看双峰是否被主力震荡换手成新的单峰密集。

### 原始逻辑链

- 真主力筹码有两个特征：获利后不急着抛，解套后也不急着卖。NBLM citation: 136.
- 双峰一般代表上方套牢峰与下方获利峰并存。NBLM citation: 150.
- “填谷”是通过震荡、对敲或换手，让上下两峰逐步消失，中间凹陷区域变成新的单峰密集。NBLM citation: 151.
- 填谷完成意味着主力完成二次换手，新的二波主升浪可能启动。NBLM citations: 153, 154.
- 二波主升常比第一波更快，交易上要等填谷完成后的突破，而不是在双峰刚出现时提前买。NBLM citation: 157.

### Copyable Trading Rule

| Module | Rule |
|---|---|
| Stock Pool | 经历第一波上涨后进入震荡整理的个股。NBLM citations: 154, 156. |
| Chip Condition | 从双峰逐渐转为单峰密集，中间谷部被填平并突出。NBLM citation: 151. |
| Volume | 填谷后再次突破时需要倍量。NBLM citation: 154. |
| Entry | 双峰填谷完成后的单峰密集突破日。NBLM citations: 154, 160. |
| Holding Logic | 二波主升可能更快，持仓依赖主力筹码是否仍稳定。NBLM citation: 157. |
| Exit / Stop | 文字稿未明确具体百分比止损；若突破失败、重新形成上方压制峰、或量价不跟随，应视为失效。 |
| Filter | 双峰尚未填谷完成、上方套牢峰未消失、突破无倍量时不做。 |
| Misuse | 在双峰仍然对立、筹码尚未完成换手时提前埋伏，会把整理期误当启动点。 |

### Thresholds / Parameters

- 集中度沿用第一节：90%/70% 筹码集中度小于 10%。
- 极端优秀案例集中度可低至 3.7 或 2.8。NBLM citation: 166.
- 二波突破需要倍量。
- 具体止损百分比：文字稿未明确。

### Review Fields

- 是否已经有第一波上涨。
- 是否进入充分震荡整理。
- 是否存在上方套牢峰和下方获利峰。
- 双峰是否被填成单峰密集。
- 突破日是否倍量。
- 集中度是否小于 10%，是否接近极端低值。
- 二波启动后是否比第一波更快。

## Integrated Trading System

### Market Assumption

股价上涨的根本驱动是主力存在和主力拉升意愿；筹码峰是识别主力行为的核心观测工具。该体系不以消息面为主要触发器，而以筹码集中、量价突破、涨停确认、阻力消失作为执行基础。

### Stock Pools

| Pool | Inclusion Rule |
|---|---|
| 低位吸筹池 | 低位横盘，筹码单峰密集，集中度小于 10%。 |
| 突破波段池 | 单峰密集后放量突破，或突破后缩量回踩 10/20 日线。 |
| 强势短线池 | 当日涨停股，用于筛选双响炮和一线天。 |
| 二波主升池 | 第一波上涨后整理，双峰逐渐填谷成单峰密集。 |

### Hard Filters

- 上方套牢峰明显，不做。
- 单峰密集但未突破，不追。
- 突破无倍量，不做。
- 一线天无放量，不做。
- 双响炮第二个涨停后高开超过 5%，不追。
- 双响炮两涨停价差超过主板 10% 或创业板 20%，过滤。
- 上升元阳阳线量能不明显大于阴线，不做。
- 买入后 2 天不能突破一线天筹码峰，离场。

### Entry Playbooks

1. 单峰突破：低位单峰密集，集中度小于 10%，放量突破筹码峰最高点。
2. 单峰回踩：突破后缩量回踩 10 日线或 20 日线，结构不破。
3. 双响炮：第二个涨停确认后，次日高开小于 5% 或回踩介入。
4. 上升元阳：中大阴线后中大阳线反包，阳线放量，尾盘或次日不破阳线实体一半介入。
5. 一线天：涨停放量形成顶格筹码单线，次日高开小于 5%。
6. 双峰填谷：第一波后震荡整理，双峰填谷成新单峰密集，再次倍量突破。

### Exit / Stop Framework

| Setup | Stop / Exit |
|---|---|
| 单峰突破 | 明确百分比未给；若上方筹码峰不消失、突破失败、形态走坏，降低或退出。 |
| 双响炮 | 跌破两个涨停板中较低那个涨停板的开盘价。 |
| 上升元阳 | 跌破组合底部，即最低开盘价。 |
| 一线天 | 跌破 20 日均线；或买入后 2 天不突破一线天筹码峰。 |
| 短线强势类 | 3-5 天不涨即走，涨停封不住即走。 |
| 双峰填谷 | 具体止损未明确；以突破失败、重新出现压制峰、量能不跟随为失效信号。 |

### Position / Risk

- 单峰突破波段首建约 2 成仓。
- 一线天短线单只约 1 成仓。
- 其他形态的仓位细则文字稿未明确。
- 该体系大量依赖形态和量价确认，不能把任何一个信号单独当作满仓理由。

## Explicit Rules vs Inferred Rules

### Explicit In Transcript / NBLM Answer

- 90% 和 70% 筹码集中度都小于 10%。
- 单峰突破买点是股价在筹码峰之上、筹码峰在下方。
- 双响炮两个涨停收盘价差：主板小于 10%，创业板小于 20%。
- 第二个涨停后次日高开不超过 5% 更适合介入。
- 一线天必须放量，且筹码呈顶格直线。
- 一线天次日高开超过 5% 不追。
- 一线天买入后 2 天不突破筹码峰则退出。
- 双响炮止损为跌破两个涨停板中较低那个涨停板的开盘价。

### Inferred Synthesis

- 均线在这套筹码体系里更像买点支撑和止损参考，不是主信号。
- 单峰密集是底层结构，双响炮、一线天、双峰填谷是不同阶段的触发器。
- 单峰突破偏波段，双响炮和一线天更偏 3-5 天短线。
- 所有战法都在寻找“主力筹码稳定 + 阻力下降 + 放量确认”的交集。

## Executable Checklist

Before entry:

- 这只股属于哪一个池：低位单峰、强势涨停、二波填谷？
- 筹码集中度是否小于 10%？
- 上方是否还有明显套牢峰？
- 是否存在倍量或有效放量？
- 买点属于突破、回踩、次日低吸，还是尾盘确认？
- 止损位是否能提前写出来？
- 当前高开是否超过 5%？
- 这个形态的预期持股周期是波段还是 3-5 天短线？

After entry:

- 是否按预期继续突破？
- 一线天买入后 2 天是否突破筹码峰？
- 双响炮是否跌破较低涨停板开盘价？
- 上升元阳是否跌破组合底部？
- 涨停是否封不住？
- 筹码峰是否重新变成上方压制？

Post-trade review:

- 入场时是否满足完整组合，而不是只满足一个漂亮形态？
- 是否因为高开超过 5% 仍追入？
- 是否忽视了上方套牢峰？
- 是否把无量一字板误判为一线天？
- 是否在双峰尚未填谷完成时提前埋伏？
- 是否遵守了 3-5 天短线失效规则？

## Non-Copyable / Risk Notes

讲师使用的软件显示、筹码峰视觉判断、案例股票背景和盘中经验不完全可复制。最容易被误用的是把“事后漂亮形态”当成实时可执行信号，或者只记住买点而忽略过滤条件。此文只用于交易技术研究和复盘模板沉淀，不构成任何投资建议。
