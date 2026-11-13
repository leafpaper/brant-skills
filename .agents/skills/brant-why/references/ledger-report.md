# 台账 v2 重建报告(2026-10-26)

v1(`data/ledger/`,阶段 4.1-4.3,2026-10-16)原样保留;v2 在 `data/ledger_v2/`。重建原因:补抽后理念卡从 1.2 万增到 2.4 万,且逐卡忠实度修正发现大量「个股/当期判断标成通用」(见 HANDOFF 顶部)。

## 流程与脚本
1. `build_ledger_v2_input.py`:套用 `data/rule_fix(_text)/` + `data/rule_fix_oneoff.jsonl`(drop 剔除、fix_rule 覆盖),排除讲者排除段与重复场次 20241225;v1 已归类卡沿用 `data/ledger/card_rule.json`,补抽卡带目录 ID 直接用,其余切块。
2. 聚类(7 块,`docs/ledger-cluster-brief.md`)→ `build_merge_input.py` → 合并(10 族,`docs/ledger-merge-brief.md`)→ `renumber_v2_merge.py`(新号避开 v1 已发出的长尾号)。
3. `build_ledger.py`(`LEDGER_DIR=data/ledger_v2 LEDGER_DEFS_FALLBACK=data/ledger/merge`;卷宗原话样本标出 [本轮行情])→ 判断 36 批(`docs/ledger-judge-brief.md` + 补充口径「有效期是重点,本轮行情卡集中一时期不能判持续」)→ `finalize_ledger.py` → `grade_ledger_v2.py`(修订版等级)。

## 输入
| 项 | 张数 |
|---|---|
| 进台账 rule 卡 | 22,849 |
| 沿用 v1 归类 / 目录 ID 直接并入 / 新聚类 | 11,655 / 9,569 / 1,625 |
| 剔除:忠实度修正 / 重复场次 | 1,790 / 15 |

## 结果(2026-10-26 终版:flags 处理 → 重判 → 逐条重写 → 第二轮复查修补)
| | v1 | v2 |
|---|---|---|
| 理念条数(台账级 / 长尾) | 720 | 1,013(676 / 337) |
| 已判(n≥8) | 289 | 494 |
| 有效期 持续/演进/情境化/过时 | 200/44/30/15 | 378/46/67/3 |
| 修订版证据等级 A/B/C(已判) | 53/218/18 | 149/327/18 |
| 可指标化/可清单化/仅背景 | — | 56/422/16 |

- 判「过时」只剩 3 条:D36 看全市场期权成交额与大单(他自己否定了)、F11 尾盘 put/call 比、F17 期权异动大单。初判的另 9 条过时,重写时按原话发现近两年仍在说,改回持续/演进/情境化。
- 5 条已判理念在 flags 处理后卡数 <8(D43、F17、S61、S65、T75),保留判断结论,样本偏少。

## 质量控制
1. **flags 落成动作**(`data/ledger_v2/overrides.jsonl`,`build_ledger.py` 读):move 266、conflict 93、剔卡 34、改写卡 3、merge 15、无法核实 2;动作先抽审(5 条驳回已手改),受影响理念重判(`judged/r00-r03`)。
2. **最终复查第一轮**(51 条,`final_check.jsonl`):陈述 26 / 有效期 13 / 可执行格式 20 条有问题——卡片没错,错在聚类/判断时写的概括(丢前提、补细节、当日观测值当阈值、个案拔成通则)。
3. **逐条重写**(494 条全部,`docs/ledger-rewrite-brief.md`,输出 `rewrite/`,`apply_ledger_rewrite.py` 合入;原台账备份 `ledger.pre_rewrite.jsonl`):每个判断都要在原话里找到,`evidence` 记依据卡。改了陈述 490、有效期 51、可执行格式 445 条。
4. **最终复查第二轮**(46 条,含第一轮有问题的 16 条;复查者须自挑不在 evidence 里的卡):陈述 / 有效期 / 可执行格式各 1 条有问题(P33 依据卡疑问——核原文后不成立,保留并补卡;D80 只在 2025-26 牛市说过,改情境化;R8 exec 多了「轻仓」),另 9 处轻微(当期说法未标时间、个案细节),全部按原话修补到 `rewrite/zz_final2.jsonl`。主会话另抽 3 处自核(P7、P11、第一轮点名的编造细节),与复查结论一致。

## 已知遗留
- H3 仍混 3 张理念卡 + 6 张 SC 反证卡(应归 H5)。
- 3 张 audit fix_wrong 卡待人工核(`input_report.json` 的 needs_manual)。
- 17 处跨类型卡键碰撞、2026Q3 一张 t 错、2025Q3 9/18 观点方向卡(见 `docs/rule-pass-recheck.md`)。
- `data/events.jsonl` 里两场重复场次(20241225_Dk1VsyvShmM、20260430_5L5zUdHrdGY)的 11 个事件未去重——修订版检验前要先去。

## 预注册与留出
ADR-0005/0007 原判定一律不改;v2 是修订版,与原版并列报告。单条回测 T1-T7(`compute_ledger_tests.py`)只依赖持仓/事件/价格,与台账内容无关,不需重跑。v2 台账仍含 2026-07-01 以后的卡(留出期,「破例纳入」两条除外),用于技能而非判定。
