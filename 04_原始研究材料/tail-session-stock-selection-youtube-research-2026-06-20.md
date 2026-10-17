# Tail-Session Stock Selection YouTube Research - 2026-06-20

This note collects YouTube videos found under the `尾盘选股` theme and distills a working tail-session stock-selection framework from NotebookLM-imported YouTube transcript sources plus previously verified local frameworks.

- User query URL: `https://www.youtube.com/results?search_query=%E5%B0%BE%E7%9B%98%E9%80%89%E8%82%A1`
- Search date: `2026-06-20`
- Recent window used: `2024-06-20` to `2026-06-20`
- Candidate discovery path: YouTube search sorted by date across `尾盘选股`, `尾盘买入 股票`, and `14:50 选股 股票`
- Metadata path: `yt-dlp` with browser login state, used only to read public video metadata and subtitle availability
- Subtitle result: all 10 confirmed recent candidates exposed no requested public subtitles / automatic captions
- NotebookLM result: successful. A clean NotebookLM notebook imported all `10 sources` on 2026-06-20 and generated a transcript-based structured extraction.
- NotebookLM notebook title: `Mastering the Last 30 Minutes: The Overnight Trading Strategy`
- Source-by-source audit status: attempted twice in the same NotebookLM notebook on 2026-06-20; NotebookLM returned `I'm having trouble responding at the moment.` No source-by-source table is included until NotebookLM can answer smaller per-source or 2-source batches.
- NotebookLM limitation: NotebookLM imports YouTube transcript text only; it does not independently listen to audio/video. The rules below are therefore based on NotebookLM-readable transcript text, not visual chart inspection.
- Local audio transcription result: not used after NotebookLM import succeeded. Earlier installation of `faster-whisper` stalled on network/proxy errors.

This is educational trading-method research, not investment advice.

## 1. Confirmed Recent Candidate Videos

These are the YouTube search candidates whose upload dates were confirmed inside the last two years. All were checked for public Chinese/English subtitles through `yt-dlp`; none exposed usable public subtitle tracks. NotebookLM later imported all 10 as transcript sources.

| Date | Video ID | Channel | Duration | Views at collection | Title | URL | Source status |
| --- | --- | --- | --- | ---: | --- | --- | --- |
| 2025-04-12 | `q4rZBOER5ok` | `来自股市的猩猩` | 6:27 | 20310 | `尾盘30分钟选股，简称一夜持股法，成功率高达9成以上！` | `https://www.youtube.com/watch?v=q4rZBOER5ok` | NotebookLM imported |
| 2025-08-07 | `8XmH9inyAVk` | `炒股养家学` | 7:39 | 15251 | `神奇尾盘二十分钟买入法，半年从10W到300W！人人都可以学会！` | `https://www.youtube.com/watch?v=8XmH9inyAVk` | NotebookLM imported |
| 2025-08-19 | `mECeun_ZiLI` | `牛散赵哥2` | 8:06 | 1086 | `A股最强“尾盘选股法”，10万一年做到150W！！堪称一绝！真正做到“一买就涨”！` | `https://www.youtube.com/watch?v=mECeun_ZiLI` | NotebookLM imported |
| 2025-12-19 | `YqpwNvGtT9I` | `炒股养家学` | 7:39 | 1499 | `掌握神奇尾盘二十分钟买入法，半年从10W到300W！人人都可以学会！` | `https://www.youtube.com/watch?v=YqpwNvGtT9I` | NotebookLM imported; likely same theme as `8XmH9inyAVk` |
| 2025-06-02 | `qVf5ZZ3Pp0o` | `江浙陈某` | 11:35 | 40 | `尾盘选股有窍门，只要设置这几个条件，就能轻松找到短线机会` | `https://www.youtube.com/watch?v=qVf5ZZ3Pp0o` | NotebookLM imported |
| 2025-05-16 | `agKtDPg4rH4` | `江浙陈某` | 9:08 | 13 | `这才是真正的尾盘选股公式，每天花五分钟，有机会就去，建议收藏` | `https://www.youtube.com/watch?v=agKtDPg4rH4` | NotebookLM imported |
| 2026-01-28 | `oTlCx9Y2bqc` | `老罗开仓了` | 7:54 | 7 | `尾盘选股法，实盘版 #股票交流 #股市 #短线` | `https://www.youtube.com/watch?v=oTlCx9Y2bqc` | NotebookLM imported |
| 2024-10-03 | `frKecXMaYFU` | `阿哥在扫街` | 20:37 | 1 | `股票牛市来了吗？股票尾盘买入续集，以前买的课程，市场不好都忘了，发出来分享一下。` | `https://www.youtube.com/watch?v=frKecXMaYFU` | NotebookLM imported |
| 2025-11-11 | `yRmRhq6leeI` | `游资六一路` | 10:50 | 142 | `炒股从亏6位数到盈7位数，只坚持“尾盘选股法”隔天就吃大肉，从未被套，堪称一绝！成功率93%` | `https://www.youtube.com/watch?v=yRmRhq6leeI` | NotebookLM imported |
| 2025-12-01 | `NzbPpeup5Hc` | `游资上塘路` | 11:42 | 123 | `湖南一位炒股天才，仅用尾盘选股法，半年时间从5w做到300w!` | `https://www.youtube.com/watch?v=NzbPpeup5Hc` | NotebookLM imported |

## 2. NotebookLM Distillation From The 10 Recent Sources

### 2.1 Repeated Core Conclusions

NotebookLM extracted these repeated conclusions across the 10 imported sources:

1. `14:30-14:50` is treated as the key window because the market has mostly revealed the day's direction and late capital behavior.
2. The method tries to avoid intraday uncertainty by buying near the close and selling the next morning.
3. The claimed edge is overnight / next-morning premium, not long-term holding.
4. The stock should be stronger than the broad index on the intraday chart.
5. Volume-price activity is mandatory: low-energy names without active volume are not candidates.
6. Turnover is used as an activity filter; `5%-10%` appears as the main range.
7. A daily gain of `3%-5%` is treated as the preferred zone: strong but not already sealed / exhausted.
8. Medium-small float market cap is preferred by many sources, especially `50亿-200亿`, though this is not unanimous.
9. If no stock meets the conditions, the rule is to stay empty rather than force a trade.
10. Execution matters more than the title promise: the next morning requires fast profit-taking or stop-loss.

### 2.2 Copyable System

NotebookLM's system extraction:

- Initial filter:
  - Daily gain: `3%-5%`.
  - Volume ratio: `> 1`; some sources mention `> 1.2`; one stricter variant uses `> 5`.
  - Turnover: `5%-10%` as the main range; some sources mention `> 3%`.
  - Float market cap: mostly `50亿-200亿`.
  - Exclude `ST` and obviously over-extended stocks.
- Technical filter:
  - Price above important moving averages, often `5日`, `10日`, and `20日`.
  - Moving averages should lean bullish / multi-line upward.
  - Intraday stock line should stay above the broad index line after overlaying the index.
- Tail-session buy point:
  - Observe after `14:30`.
  - Decide around `14:50`.
  - Buy after late-session volume-backed strength, a breakout of the day's high, or a pullback that does not break the intraday average.
- Next-day sell point:
  - Standard action is to sell into the next morning's strength, commonly before `10:00`.
  - A source-specific exception: if the stock gaps up more than about `5%` and shows possible board-sealing strength, observe rather than mechanically sell immediately.
- Position:
  - Beginners / training stage should use small size, around one layer / no more than 10%.
- Loss handling:
  - If there is no next-morning strength, leave before the trade turns into hope.
  - One source-level rule: if price breaks the prior day's bullish-candle bottom / starting point, stop-loss.
- Market environment:
  - Broad index should be stable or rising on a `15分钟K线` basis.
  - Avoid the method when the index is in a broad-volume decline or visibility is poor.

### 2.3 Consensus And Disagreement

Consensus:

- Operate after `14:30`.
- Gain should generally be above `3%`.
- Volume ratio should be above `1`.
- The trade is overnight / next-morning premium, not a medium-term thesis.

Disagreements / source-specific variants:

- Market cap:
  - Many sources prefer `50亿-200亿`.
  - One source prefers `>200亿` for stability.
- Buy trigger:
  - Some sources buy a late breakout of intraday high.
  - Some sources prefer a pullback to intraday average / moving-average support after strength.
- Amplitude:
  - One logic prefers smaller amplitude, e.g. `<5%`, for stability.
  - Another logic wants enough amplitude / volatility, e.g. `>4%`, to prove activity.
- Lookback:
  - Some sources use `20天内涨停`.
  - Others use `8天内涨停`.

### 2.4 Hype Filter

NotebookLM explicitly flagged the title claims as promotion rather than executable evidence:

- `成功率93%`, `成功率9成以上`, `10W到300W`, `5W到300W`, and similar claims should not determine position size.
- The transcript-level rules themselves still require exit if the market does not behave as expected.
- The practical profit target implied by several sources is often small next-morning premium, not fantasy compounding.

Manual rule:

- Treat performance claims as marketing.
- Only trade the measurable filters: time, gain, volume, turnover, market cap, moving averages, index-relative strength, market environment, and next-morning exit.

## 3. Existing Transcript-Verified Baseline Framework

The durable rules below come from existing transcript-verified notes in the local corpus and serve as a stricter risk wrapper around the newly imported NotebookLM batch:

- `dahuzi-ten-day-line-tail-session-framework.md`
- `dahuzi-market-breadth-mechanical-framework.md`
- `dahuzi-objective-signal-real-fake-capital-framework.md`
- `aguzuoshou-swing-industry-correlation-position-discipline-framework.md`

### 3.1 Tail Session Is A Noise Filter, Not A Magic Signal

The strongest verified idea is not "buy at the close because it will rise tomorrow." The usable idea is:

- Waiting until `14:40` or `14:50` lets most of the day's price, volume, and market-breadth information reveal itself.
- Tail-session buying reduces the chance of chasing morning emotion.
- The late entry must still pass stock structure, market environment, and next-day exit rules.

Mechanical rule:

- If the only reason to buy is "it is almost the close," do not buy.
- Tail-session timing is a final confirmation window, not a stock-picking reason by itself.

### 3.2 Market Gate Comes Before Individual Pattern

From the market-breadth mechanical framework:

- If rising stocks are below roughly `3000`, do not open new positions.
- If falling stocks exceed roughly `3000`, cut total exposure by half.
- If falling stocks exceed roughly `4000`, clear exposure first.
- Buying is allowed only before `10:40` or after `14:40`; `10:40-14:40` is a no-buy zone.

Manual adaptation:

- Use these thresholds as an A-share broad-risk switch, not as a bullish prediction.
- If the market is in broad selloff, a pretty tail-session K-line is not enough.

### 3.3 Candidate Pool: Prior Capital Participation

Verified filters from the Dahuzi ten-day-line framework:

- The stock should have a prior heavy-volume bullish candle or obvious capital participation.
- The current day should be a controlled pullback, not a chase candle.
- The pullback should shrink in volume relative to the earlier participation day.
- The stock should have enough liquidity to buy near the close and sell next morning.

Related filter from the market-breadth framework:

- Prefer stocks with recent limit-up or doubled-volume activity within about one month.
- If there was no recent sign that money cared, do not force the trade.

### 3.4 The Cleanest Verified Setup

The clearest transcript-supported setup can be written as:

`prior heavy-volume bullish participation -> low-volume bearish pullback -> near ten-day moving average -> tail-session confirmation -> next-morning exit`

Entry checklist:

1. Prior strong candle had real volume.
2. Current pullback is low volume, not heavy-volume distribution.
3. Price is near the ten-day moving average.
4. Ten-day, twenty-day, and thirty-day lines are not all turning down.
5. The broader market is not in collapse mode.
6. Entry waits until after `14:40`, ideally around `14:50`.
7. Position size is small enough to obey the next-morning exit.

Skip conditions:

- Heavy-volume bearish candle.
- Decisive break of the ten-day line.
- Downtrend bottom-fishing disguised as "tail-session selection."
- Midday impulse buy before the late-session rule has matured.
- Social-media crowded names without objective market confirmation.

### 3.5 Objective Signal Layer

From the objective-signal framework:

- Tail-session decisions should be based on objective evidence, not personal hope.
- For uncertain / sideways names, the two meaningful processing windows are `9:35前` and `14:50后`.
- `14:50后` is for final adjustment, retention decision, or putting a sold-but-not-dead name into the backup pool.
- Do not predict the close too early.
- Do not chase irrational late-session noise.

Practical rule:

- Before buying at the close, write the objective signal in one sentence.
- If the sentence contains "I feel", "maybe", "should", or "it has fallen enough", skip.

### 3.6 Position And Overnight Risk

The tail-session method is naturally overnight risk. It cannot be treated like intraday scalp.

Rules:

- Use predefined units; do not all-in one name.
- Treat each trade as one sample in a probability system.
- If using a rolling / T-style position, confirm no accidental overnight add-on remains.
- If a board fails and cannot repair into the close, reduce risk rather than hope for tomorrow.
- Do not add to a failed setup to improve cost.

### 3.7 Next-Day Exit Is Part Of The Entry

The verified Dahuzi framework treats the next morning as the planned payoff window:

- Default exit: around or before `10:00` next trading day unless exceptional strength appears.
- If morning price spikes and then breaks the intraday average, sell.
- If price rallies into the five-day moving average and cannot break through, sell.
- If a weak open cannot reclaim the intraday average within about 15 minutes, sell.
- If price breaks the ten-day line by about `3%`, forced stop-loss triggers.

Core principle:

- A tail-session rebound trade that fails next morning is not allowed to become a medium-term holding.

## 4. A Copyable Tail-Session Trading Rule Set

### Pre-Market / Watchlist

1. Build a candidate pool from stocks with recent strong capital participation.
2. Mark prior heavy-volume bullish days and key ten-day-line zones.
3. Apply the NotebookLM batch filters: `3%-5%` gain, `量比 > 1`, `5%-10%` turnover, `50亿-200亿` float market cap where applicable.
4. Remove `ST`, cold, illiquid, purely promotional, or social-media crowded names.
5. Write the next-day buy/invalid/sell conditions before the market opens.

### Intraday Before Tail Session

1. Check broad market breadth.
2. If market breadth blocks buying, do not let a single stock override it.
3. Do not buy in the `10:40-14:40` no-buy zone.
4. Watch whether candidate pullbacks remain low-volume and controlled.

### 14:40-14:50 Entry Decision

Buy only if all are true:

1. Broad market risk is acceptable.
2. Stock had prior real capital participation.
3. Stock is stronger than the index on intraday overlay.
4. Today's gain / turnover / volume ratio pass the selected variant's thresholds.
5. The late move is either volume-backed breakout or controlled pullback that does not break the intraday average.
6. Price remains near but not decisively below the relevant moving-average support.
7. The original buy reason can be written in one objective sentence.
8. The next-morning sell plan is already defined.

### Next Morning

1. Observe the opening and first 15 minutes.
2. Sell weak opens that cannot reclaim the intraday average.
3. Sell rebound failures near resistance.
4. Protect early profits when intraday average breaks.
5. Do not hold past the planned window without a new objective strength signal.

## 5. Common Misuses

- Treating "tail-session" as a magic time rather than a confirmation window.
- Buying any late-day pull-up.
- Buying because the title or teacher claims a high success rate.
- Ignoring broad market breadth.
- Calling heavy-volume distribution a low-volume pullback.
- Buying a broken ten-day-line downtrend and naming it a rebound trade.
- Forgetting the next-day sell rule.
- Concentrating in one stock while claiming to use a probability method.
- Saving transaction fees while losing the entire trade premise.
- Turning a failed overnight trade into a long-term story.
- Believing `成功率93%` or `10W到300W` title claims and increasing size before personal sample statistics exist.
- Mixing contradictory variants, e.g. demanding both `<5%` stable amplitude and `>4%` active amplitude without defining which model is being tested.

## 6. Backtest / Replay Fields

To test this theme properly, each trade sample should record:

| Field | Why It Matters |
| --- | --- |
| Trade date | Separates regime differences |
| Entry time | Confirms after-14:40 discipline |
| Market rising / falling count | Tests market-breadth gate |
| Prior heavy-volume candle date | Confirms capital participation |
| Current pullback volume vs prior volume | Tests low-volume pullback premise |
| Distance to ten-day line | Defines support and stop |
| Entry price | Measures slippage near close |
| Next-day open / high / 10:00 price | Tests morning payoff window |
| Exit reason | Separates planned exits from emotional exits |
| Max adverse excursion | Shows overnight risk |
| Result | Builds expectancy |
| Error tag | Selection, timing, volume, market, or execution error |

## 7. Review Questions

1. Was the broad market permissive, or did I force a trade?
2. Did the stock have prior real capital participation?
3. Was today's pullback truly low-volume?
4. Was price near a valid ten-day-line support, or had support already failed?
5. Did I wait until after `14:40`?
6. Could I write the objective signal in one sentence?
7. Did I define the next-morning exit before buying?
8. Did I sell when the morning rebound failed?
9. Did I turn a sample trade into a belief trade?
10. Which part of the setup actually created edge: market, stock structure, time window, or luck?

## 8. Next Work

To improve this theme further, ask NotebookLM source-by-source or 2-source follow-up questions instead of relying only on one cross-source synthesis. A 10-source table prompt failed twice, so keep the next prompts smaller. Priority order:

1. `q4rZBOER5ok`
2. `8XmH9inyAVk`
3. `qVf5ZZ3Pp0o`
4. `agKtDPg4rH4`
5. `oTlCx9Y2bqc`
6. `yRmRhq6leeI`

Future prompts should ask each source for:

- Exact screener formula / software settings.
- Whether `3%-5%`, `5%-10%`, and `50亿-200亿` are literal or illustrative.
- Which sell rule overrides the next-morning `10:00` default.
- Failure examples where the same tail-session shape should be skipped.
