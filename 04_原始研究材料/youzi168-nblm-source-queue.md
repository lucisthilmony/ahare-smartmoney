# @youzi168 频道 NBLM 投喂清单（第一批）

说明：此文件只作为 NotebookLM/NBLM 的来源投喂清单，不是内容蒸馏结论。NotebookLM 官方要求 YouTube 来源必须是公开视频，且有上传字幕或自动字幕；导入后应以 NBLM 生成的带来源回答为准。

官方限制依据：NotebookLM Help 说明 YouTube 来源只支持带字幕的公开视频，并且导入的是视频文字转录稿，不是视频画面本身。参考：https://support.google.com/notebooklm/answer/16215270

本地检查结果：直接字幕抓取和 YouTube 单视频字幕列表检查显示，前几条样本未发现可用字幕；但仍应以 NBLM 实际导入结果为准，因为 NotebookLM 和 YouTube 前端可能有不同的访问路径。

## 导入方式

1. 打开 NotebookLM，新建 notebook：`A股游资-youzi168-视频蒸馏`。
2. 逐条添加下面的 YouTube URL 作为来源。
3. 对导入成功的视频，让 NBLM 先生成“摘要 / 关键观点 / 可操作规则 / 风险条件 / 原话证据”。
4. 对导入失败的视频，在表格里标注：`无字幕`、`太新`、`私密/删除` 或 `地区/验证限制`，不要蒸馏。

## 导入状态表

NBLM 实测结果（2026-06-20）：第一批 20 条 YouTube 来源均已成功导入 NotebookLM，并生成了基于来源的蒸馏回答。Notebook 链接：https://notebooklm.google.com/notebook/41d32606-3c8d-4ce9-b8d6-3cbff128dc6e

| 视频 URL | NBLM 导入状态 | 失败原因 | 备注 |
|---|---|---|---|
| https://www.youtube.com/watch?v=Nh26oA7VsEw | 成功 |  | NBLM 已导入 |
| https://www.youtube.com/watch?v=4kr73RNeqIg | 成功 |  | NBLM 已导入 |
| https://www.youtube.com/watch?v=xFIZ1BncwHU | 成功 |  | NBLM 已导入 |
| https://www.youtube.com/watch?v=lyPMKg7ZWho | 成功 |  | NBLM 已导入 |
| https://www.youtube.com/watch?v=k6jRyrJ8ARU | 成功 |  | NBLM 已导入 |
| https://www.youtube.com/watch?v=P1ihkPavPHM | 成功 |  | NBLM 已导入 |
| https://www.youtube.com/watch?v=zbZAlKJgBig | 成功 | 本地 yt-dlp 检查为无字幕 | NBLM 实测可导入 |
| https://www.youtube.com/watch?v=OkEKHow3bW8 | 成功 |  | NBLM 已导入 |
| https://www.youtube.com/watch?v=sn3tw8lgb1Q | 成功 |  | NBLM 已导入 |
| https://www.youtube.com/watch?v=DDqGq1ja_vQ | 成功 | 本地字幕接口失败 | NBLM 实测可导入 |
| https://www.youtube.com/watch?v=plGwGH78ejU | 成功 |  | NBLM 已导入 |
| https://www.youtube.com/watch?v=9W_xivfrHuQ | 成功 |  | NBLM 已导入 |
| https://www.youtube.com/watch?v=KoVF-MzUtIE | 成功 |  | NBLM 已导入 |
| https://www.youtube.com/watch?v=sEYn2rQdyRs | 成功 |  | NBLM 已导入 |
| https://www.youtube.com/watch?v=DR5QxRkcXp8 | 成功 |  | NBLM 已导入 |
| https://www.youtube.com/watch?v=AdxzioMd_4E | 成功 |  | NBLM 已导入 |
| https://www.youtube.com/watch?v=O4JnUNUHmyQ | 成功 |  | NBLM 已导入 |
| https://www.youtube.com/watch?v=tBovVv6cH-I | 成功 |  | NBLM 已导入 |
| https://www.youtube.com/watch?v=cMazfPDA_DM | 成功 |  | NBLM 已导入 |
| https://www.youtube.com/watch?v=-pgWpWWbikc | 成功 |  | NBLM 已导入 |

## 第一批优先视频

| 优先级 | 视频 | 时长 | URL | 放入 NBLM 的原因 |
|---:|---|---:|---|---|
| 1 | 【实盘赛高手】【小彬彬】 5000万实盘，牛市我是如何把波段做到利润最大化的分享（2） | 29:50 | https://www.youtube.com/watch?v=Nh26oA7VsEw | 波段 |
| 2 | 【实盘赛高手】【博古通今】我是这么理解行情与模式匹配的，这几点缺一不可 | 28:52 | https://www.youtube.com/watch?v=4kr73RNeqIg | 行情与模式 |
| 3 | 【实盘赛冠军】【刘逸铭 】我是怎么把龙模式做大！做精的，这几个时间节点的把握，必不可少！ | 24:11 | https://www.youtube.com/watch?v=xFIZ1BncwHU | 实盘赛冠军、龙模式 |
| 4 | 【实盘赛高手】在不确定中寻找确定性……抵制一切抵制不了的诱惑#交易人生 #心态 #干货分享 | 19:59 | https://www.youtube.com/watch?v=lyPMKg7ZWho | 长访谈/方法论密度可能较高 |
| 5 | 【实盘赛高手】【鄂华少】今年已翻倍，明星实盘选手，情绪核心流战法分享（下） | 18:49 | https://www.youtube.com/watch?v=k6jRyrJ8ARU | 情绪核心 |
| 6 | 【实盘赛高手】越是形式不好，越要有战略定力#解放思想 #实事求是 #世界和平 | 18:13 | https://www.youtube.com/watch?v=P1ihkPavPHM | 长访谈/方法论密度可能较高 |
| 7 | 【牵牛哥】职业作手如何给股票贴标签？ 20年游资职业复盘指南系列2，复盘底层干货无私分享，内容很干，建议收藏反复观看 | 16:02 | https://www.youtube.com/watch?v=zbZAlKJgBig | 复盘、贴标签 |
| 8 | 【实盘赛高手】【小彬彬】5000万实盘，牛市我是如何把波段做到利润最大化的分享（1） | 7:50 | https://www.youtube.com/watch?v=OkEKHow3bW8 | 波段 |
| 9 | 【实盘赛冠军】【管住手】股民必看，一个实盘冠军的真心话：股市里没有神，只有活下来的人 | 1:04:01 | https://www.youtube.com/watch?v=sn3tw8lgb1Q | 实盘赛冠军 |
| 10 | 【北京炒家】WC，真人北京炒家采访视频，北京炒家老师开诚布公讲出最核心的东西 | 55:18 | https://www.youtube.com/watch?v=DDqGq1ja_vQ | 北京炒家 |
| 11 | 【交易理解】【牵牛哥】如果能遇见刚炒股那年的自己，纯干货的股票交流会！ | 46:13 | https://www.youtube.com/watch?v=plGwGH78ejU | 交易理解 |
| 12 | 【北京炒家】北京炒家4月10直播回放，讲述近期自己的操作 | 45:25 | https://www.youtube.com/watch?v=9W_xivfrHuQ | 北京炒家 |
| 13 | 【实盘赛高手】2025年7倍（下）稳健分仓高手，2025七倍，超级大干货（下）#股民 #股票 | 27:48 | https://www.youtube.com/watch?v=KoVF-MzUtIE | 长访谈/方法论密度可能较高 |
| 14 | 【实盘赛高手】【我是会发光的男人】怎么全方位个角度的分析市场，从而精准定位到个股，精彩分享片段 | 26:40 | https://www.youtube.com/watch?v=sEYn2rQdyRs | 长访谈/方法论密度可能较高 |
| 15 | 【实盘赛高手】【飘忽之间】我是怎么理解战争题材的，现场答疑精选 | 25:21 | https://www.youtube.com/watch?v=DR5QxRkcXp8 | 长访谈/方法论密度可能较高 |
| 16 | 【实盘赛高手】1年7倍稳健分仓高手，2025七倍，超级大干货（上）#股民 #股票 | 25:20 | https://www.youtube.com/watch?v=AdxzioMd_4E | 长访谈/方法论密度可能较高 |
| 17 | 【实盘赛高手】【三川万里红】直播连线第二届屠龙杯亚军，我是怎么悟透行情的好坏的，判断的标准在哪（上） | 24:49 | https://www.youtube.com/watch?v=O4JnUNUHmyQ | 长访谈/方法论密度可能较高 |
| 18 | 【实盘赛高手】【三川万里红】（二）市场永远在变，唯有总结与反思是永恒的利器。听高手畅谈从量变到质变。 | 23:39 | https://www.youtube.com/watch?v=tBovVv6cH-I | 长访谈/方法论密度可能较高 |
| 19 | 【实盘赛高手】曾手握国企省公司一把手的橄榄枝，却靠炒股赚大钱，这狗血剧情不是短剧，而是在实盘赛。（二） | 23:01 | https://www.youtube.com/watch?v=cMazfPDA_DM | 长访谈/方法论密度可能较高 |
| 20 | 【实盘赛高手】 【黑到被嫌弃】（二）九年的悟道路，冠军的心得，我理解的追根溯源是哪些 | 20:40 | https://www.youtube.com/watch?v=-pgWpWWbikc | 长访谈/方法论密度可能较高 |

## 给 NBLM 的固定提问模板

把每个成功导入的视频按下面格式回答，必须引用来源，不要补充来源外的信息：

```text
请只基于当前 notebook 的来源，蒸馏这些 A 股交易视频。
输出：
1. 每个视频 5-8 条要点，标注来源视频名。
2. 合并成一套交易框架：市场判断、题材/个股筛选、买点、卖点、仓位、风控、复盘。
3. 把“观点/规则”拆成可验证条件，例如出现什么信号才成立，什么情况失效。
4. 单独列出不能直接落地或存在幸存者偏差的说法。
5. 不要输出任何来源里没有说的内容。
```

## 二次整理输出格式

- `NBLM 原始摘录`：保存 NBLM 的带引用答案。
- `策略规则表`：只收录有视频来源支持的规则。
- `待验证假设`：需要回测或盘后人工验证的规则。
- `不可蒸馏清单`：NBLM 无法导入或无字幕的视频。

## 深挖进度

| 批次 | 方式 | 覆盖视频 | 输出文件 | 结论 |
|---|---|---|---|---|
| long-videos-deep-dive | 12 条长视频一次追问 | 管住手、北京炒家、牵牛哥、小彬彬、博古通今、刘逸铭、三川万里红等 | `youzi168-nblm-long-videos-deep-dive-raw.md` | 比第一轮总纲更厚，但仍偏摘要化 |
| small-batch-01 | 2 条长视频小批次追问 | 管住手、北京炒家 WC 采访 | `youzi168-nblm-small-batch-01-管住手-北京炒家-raw.md` | 明显更接近完整字幕后的可执行提炼，并暴露了上一轮残留的无证据表述 |
| small-batch-02 | 2 条长视频小批次追问 | 牵牛哥“如果能遇见刚炒股那年的自己”、北京炒家 4 月 10 直播回放 | `youzi168-nblm-small-batch-02-牵牛哥-北京炒家0410-raw.md`; `youzi168-nblm-small-batch-02-evidence-patch.md` | 已按 A-F 结构输出段落顺序、规则表、案例、不可落地内容和盘后验证字段；另用证据补丁补齐可复制来源标记，并标出 1 条“来源中未见明确证据”的跨视频残留 |
| small-batch-03 | 2 条上下集一起追问 | 2025 七倍稳健分仓高手（上/下） | - | NotebookLM 返回 `I'm having trouble responding at the moment.`；因此改为单条长视频拆问 |
| small-batch-03A | 1 条长视频单条追问 | 2025 七倍稳健分仓高手（上） | `youzi168-nblm-small-batch-03A-2025七倍上-raw.md` | 已完成来源 7 的单视频深挖：龙头-补涨-切换、1进2零轴承接、补涨终结、主板/创业板分仓、不可量化经验项和盘后验证字段 |
| small-batch-03B | 1 条长视频单条追问 | 2025 七倍稳健分仓高手（下） | `youzi168-nblm-small-batch-03B-2025七倍下-raw.md` | 已完成来源 8 的单视频深挖：不做 T、拉萨席位反向指标、20% 回撤红线、四位一体买点、中位股分歧日回避、闲钱红线 |
| small-batch-04A | 1 条长视频单条追问 | 我是会发光的男人：全方位分析市场、精准定位个股 | `youzi168-nblm-small-batch-04A-我是会发光的男人-raw.md` | 已完成来源 14 的单视频深挖：供需稀缺、预期交易、低迷期独苗报团、主板新股密度、盘面反馈优先、AI 产业供需缺口、盘前极限推演和策略迭代 |
| small-batch-04B | 1 条长视频单条追问 | 飘忽之间：战争题材现场答疑精选 | `youzi168-nblm-small-batch-04B-飘忽之间战争题材-raw.md` | 已完成来源 16 的单视频深挖：长期逻辑储备、超级事件催化、首日分歧介入、趋势股突破、右侧跟随、30 亿成交额门槛、预期不符退出、弹性优先；完整提示失败两次后改短提示成功 |
| small-batch-05A | 1 条长视频单条追问 | 鄂华少：情绪核心流战法分享（下） | `youzi168-nblm-small-batch-05A-鄂华少情绪核心流下-raw.md` | 已完成来源 15 的单视频深挖：主龙存续、补涨龙切换、T 字回封加仓、回封速度卖点、禁止纠结式加仓、极端行情分仓回撤、明牌只做绝对核心、卡位规避、混沌期核心池低吸；保留字幕音译个股名的证据不足提示 |
| small-batch-05B | 1 条长视频单条追问 | 在不确定中寻找确定性 | `youzi168-nblm-small-batch-05B-不确定中寻找确定性-raw.md` | 已完成来源 17 的单视频深挖：不确定中找胜率溢价、趋势延续、打板/趋势模式门槛、牛熊市趋势容错率、题材三要素、国内外共振、高位股惯性、卖点证据不足；保留“2025年牛市”为来源语境而非当前市场判断 |
| small-batch-05C | 1 条长视频单条追问 | 越是形式不好，越要有战略定力 | `youzi168-nblm-small-batch-05C-战略定力-raw.md` | 已完成来源 19 的单视频深挖：高位惯性获利、卖飞后认错买回、牛熊趋势模式差异、题材多轮滚动、题材重于个股、细分题材套利；保留音译个股名与“完全不看 K 线”的过度简化风险 |
| small-batch-06A | 1 条长视频单条追问 | 小彬彬：5000万实盘，牛市如何把波段利润最大化（2） | `youzi168-nblm-small-batch-06A-小彬彬波段2-raw.md` | 已完成来源 12 的单视频深挖：盈亏比优先、开仓前深度推演、产业瓶颈定位、外部黑天鹅处理、卖点毛点化、拒绝 T+0、原厂核心筛选、重仓/满融风险；复制出的 Markdown 未保留弹窗引用编号，需以后从 NotebookLM UI 复核编号 |
| small-batch-06B | 1 条长视频单条追问 | 博古通今：行情与模式匹配 | `youzi168-nblm-small-batch-06B-博古通今行情模式匹配-raw.md` | 已完成来源 11 的单视频深挖：扫板/排板随行情切换、板块共振与纯技术首板、10 倍前机械化固化模式、资产台阶防守、预期验证、系统补漏、行情不匹配时休眠；复制出的 Markdown 保留了 `[11: ...]` 引用 |
| small-batch-06C | 1 条长视频单条追问 | 刘逸铭：龙模式做大做精 | `youzi168-nblm-small-batch-06C-刘逸铭龙模式-raw.md` | 已完成来源 4 的单视频深挖：二进三核心筛选、龙空龙、补涨龙、板上确认买点、二板爆量三板秒板、老龙断板后的题材切换、核心锁仓、禁补仓；复制稿部分引用列为空，但来源确认保留 `[来源 4: 85-94]` |
| small-batch-06D | 1 条长视频单条追问 | 牵牛哥：职业作手如何给股票贴标签 | `youzi168-nblm-small-batch-06D-牵牛哥股票贴标签-raw.md` | 已完成单视频深挖：股票贴标、价格先行、庄股/情绪股/趋势股/合力中军/股性记忆/高景气/补涨/主线/复合标签、量化时代生存法则；NotebookLM UI 显示有弹窗引用，但复制出的 Markdown 引用列为空，需后续回 UI 复核编号 |
| small-batch-06E | 1 条短视频单条追问 | 小彬彬：5000万实盘，牛市如何把波段利润最大化（1） | `youzi168-nblm-small-batch-06E-小彬彬波段1-raw.md` | 已完成来源 13 的单视频深挖：短线转波段、产业趋势锚定、技术分析局限、庄股禁入、杠杆红线、认知与情绪稳定、融资复利；复制稿保留 `[13: ...]` 引用 |
| small-batch-06F | 1 条长视频单条追问 | 三川万里红：悟透行情好坏（上） | `youzi168-nblm-small-batch-06F-三川万里红上-raw.md` | 已完成来源 9 的单视频深挖：实战化心法、消息面定性、新题材极点首板、题材无缝衔接、量能审美切换、20cm/30cm 弹性传导、逻辑支撑验证、看盘版面和板块分类监控；复制稿保留 `[9: ...]` 引用，个股音译和成交额口径需后续核实 |
| small-batch-06G | 1 条长视频单条追问 | 三川万里红：市场永远在变，总结与反思（  二） | `youzi168-nblm-small-batch-06G-三川万里红二-raw.md` | 已完成来源 10 的单视频深挖：极点股票研究、三四年量变到质变、异动监管博弈、分歧入核心、错误数据库、突发事件首板、补涨 A 杀、资金认可、认知内收益、题材持续性；NotebookLM UI 显示弹窗引用，但复制稿引用列为空，需后续回 UI 复核编号 |
| small-batch-06H | 1 条长视频单条追问 | 国企省公司一把手橄榄枝，实盘赛（二） | `youzi168-nblm-small-batch-06H-国企省公司二-raw.md` | 已完成来源 18 片段 278-289 的单视频深挖：龙头第一波后震荡/二波、主线非 A 杀定义、蓝色光标震荡套利、龙超旧模式、每日涨跌放缩预判、慢即是快、龙空龙、创新药预期、职业炒股财务防火墙、流动性红线、3 万亿量能极端环境；复制稿引用列为空，仅保留来源片段范围 |
| small-batch-06I | 1 条长视频单条追问 | 黑到被嫌弃：九年的悟道路、追根溯源（二） | `youzi168-nblm-small-batch-06I-黑到被嫌弃二-raw.md` | 已完成单视频深挖：模式外亏损根源、第三视角内观、流量定价、半路介入、硬板次日预期陷阱、买入即预期、量化流动性价值、逻辑加业绩模式；NotebookLM UI 显示弹窗引用，但复制稿引用列为空，来源片段范围也未复制完整，个股音译需后续核实 |

后续长视频继续按 `youzi168-nblm-small-batch-protocol.md` 执行：每批 2 个，先按视频讲话顺序抽段落，再抽规则、案例和不可落地内容。
