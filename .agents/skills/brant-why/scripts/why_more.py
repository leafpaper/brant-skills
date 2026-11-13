"""why.py 的扩展查法:功能介绍、分类成绩单、个股档案、更正入口、待核实清单、自由统计、参考资料。只用标准库。

由 why.py 调用(why.py 把自己挂到本模块的 W 上,这里用它的 CN、day、names_of 等)。不要单独运行。
"""
import collections
import datetime as dt
import json
import os
import re
import sqlite3
import tempfile

W = None  # why.py 运行时注入
HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.dirname(HERE)
D = os.path.join(SKILL, 'data')
JUDGE_END = '2026-06-30'  # 判定样本截止日;之后是留出期,不给战绩数字


# ---------------------------------------------------------------- 小工具
def _ci(ci):
    if not ci or len(ci) != 2 or ci[0] is None:
        return ''
    cross = '跨 0' if ci[0] <= 0 <= ci[1] else '不跨 0'
    return f" [{ci[0]:+.1%}, {ci[1]:+.1%}]({cross})"


def _row(label, s, win_word='跑赢', unit='段'):
    """一行分组结果。s 形如 {n, mean, median, win_rate|win, ci}"""
    if not s:
        return f'- {label}:没有数据'
    if s.get('mean') is None:
        return f"- {label}:{s.get('n', 0)} {unit}(样本太少,没算)"
    w = s.get('win_rate', s.get('win'))
    return (f"- {label}:{s['n']} {unit},平均 {s['mean']:+.1%}"
            + (f",{win_word} {w:.0%}" if w is not None else '') + _ci(s.get('ci')))


def _inr(d, d0, d1):
    return bool(d) and (not d0 or d >= d0) and (not d1 or d <= d1)


def _clip(s, n=80):
    s = (s or '').strip().replace('\n', ' ')
    return s if len(s) <= n else s[:n] + '…'


def _pos_scope(db, p):
    e = next((db.tr[x] for x in p.get('event_ids') or [] if x in db.tr), None)
    return (e or {}).get('scope')


def _pos_tool(db, p):
    if p.get('option'):
        return '期权'
    if p.get('levered'):
        return '杠杆ETF'
    return {'macro': '指数期货/宏观品种', 'crypto': '加密货币', 'non_us': '非美股', 'basket': '一篮子'}.get(_pos_scope(db, p), '正股')


# ---------------------------------------------------------------- 功能介绍
def intro(db):
    ts = db.trades
    dates = sorted(t['date'] for t in ts if t.get('date'))
    n_sess = len({s.get('stem') for ss in db.sess.values() for s in ss})
    judged = sum(1 for r in db.rules.values() if r.get('judged'))
    open_pre = sum(1 for p in db.presets if p.get('status') not in W.DONE)
    dd = os.path.join(D, 'daily')
    daily = sorted(f for f in os.listdir(dd) if f.endswith('.md')) if os.path.isdir(dd) else []
    tdir = W.raw_dirs()[0]
    n_raw = len([f for f in os.listdir(tdir) if f.endswith('.host.txt')]) if os.path.isdir(tdir) else 0
    last_daily = f'{daily[-1][:4]}-{daily[-1][4:6]}-{daily[-1][6:8]}' if daily else '无'
    out = [
        '# 这个技能能做什么',
        '一句话:把 Brant(布布)2020-08 以来的直播、喊单、文字线整理成可以查、可以检验的记录——'
        '每笔操作当时怎么说的、每条理念怎么演变的、事后看哪些做法赚钱哪些在亏。只讲历史和检验结果,不给现在的买卖建议。',
        '',
        '## 数据范围',
        f'- 操作事件 {len(ts):,} 个({dates[0]} ~ {dates[-1]}),持仓段 {len(db.pos):,} 段,直播 {n_sess:,} 场' if dates else '- 没有操作事件',
        f'- 理念原话 {len(db.ideas):,} 条,归成 {len(db.rules):,} 条理念(其中 {judged} 条判过有效期和证据等级)',
        f'- 每日直播总结 {len(daily)} 篇(最新 {last_daily});预设点位与认错条件 {len(db.presets)} 条,还没了结 {open_pre} 条',
        f'- 直播逐字稿原文 {n_raw} 场' + ('(可全文搜索)' if n_raw else '(本机没有原文,全文搜索用不了)'),
        f'- 战绩检验只算到 {JUDGE_END}(之后的数据留着做以后的检验,不给收益数字);战绩依据是展示账户的喊单和直播里说的操作,不是实盘',
        '',
        '## 能做的十一类事(括号里是对应查法)',
        '1. **某笔操作当时为什么这么做**:「2025 年 4 月为什么清特斯拉」「为什么从正股换成 TSLL」「那段时间为什么不买英伟达」'
        '(`TSLA --from 2025-04 --kind sell|switch|skip`、`--position P0580`、`--date 2025-03-24`)',
        '2. **某条理念怎么说、怎么变的**:「杠杆什么时候加什么时候去」「这条是自己的做法还是讲给听众的」(`--idea P7`)',
        '3. **哪类做法赚钱、哪类在亏**:按买入理由、行情、年份、把握、仓位大小分组的成绩单;说「不买」准不准;'
        '清仓和减仓哪个有信息量(`--scorecard`,可只看一块:`--scorecard 选股|离场|硬扛|大方向|期货|言行`)',
        '4. **一只票的完整档案**:看法怎么变、哪里改过口、每段持仓的结果、相关的老毛病、还没了结的预设(`--dossier TSLA`)',
        '5. **老毛病与事后检验**:35 类自己承认过的失误,哪些数据确认有代价、哪些其实看不出代价;每条的修正版和裁决(`--lesson B2`、`--lesson J2`)',
        '6. **最近的直播和计划**:最新一场讲了什么、设过哪些「跌到 X 加」「破 Y 认错」、后来照做没有(`--daily`、`--presets`)',
        '7. **原文里找一句话、一个人、一件往事**:全部直播逐字稿和喊单全文搜索,自动带上转写听错的写法(`--grep "强平|爆仓"`)',
        '8. **临时想到的统计**:固定查法答不了的,直接对数据库提问,如「2024 年半导体买入按月胜率」(`--sql`,先 `--sql schema` 看有哪些表)',
        '9. **数据记错了、想补充**:说一句「这笔不对,实际是……」就记下来,回流给整理者改源头(`--flag E03881 --note "……"`;'
        '`--unverified` 列出只有本人能核实的条目)',
        '10. **(可选)和真实持仓对照**:会话里接了长桥、IBKR、Robinhood 这类券商连接器的话,可以只读地调出当前持仓和成交记录,'
        '逐只对照这里的历史档案、未了结预设,并核对数据里「还没见平仓」的仓位(`--open`)。不接也不影响其他功能;只读,不下单',
        '11. **写长文**:「把 2022 年熊市那段写成一篇文章」「写一篇我在特斯拉上这几年」——按时间拉出操作、原话和复盘,'
        '写成带出处的心路历程长文;每句引文都自动核对是不是逐字的原话(`--check-essay 文章.md`,「问题 0」才算过)',
        '',
        '## 建议从这里开始',
        '- `--ref overview`:一页结论,十条最重要的发现,每条带数字和出处',
        '- `--scorecard`:分类成绩单',
        '- `--ref known-issues`:已知的数据问题(先看这个,免得被记错的地方带偏)',
        '- `--ref list`:全部参考资料(战绩检验报告、失误与修正版、规则检验报告、理念目录、当前立场、术语表)',
        '',
        '## 做不了的',
        '- 不给现在的买卖建议,不帮忙筛股票:单条规则回测 7 项、机械规则检验 13 项都没有一项通过,现在拿这些规则选股等于用没验证的东西',
        '- 不知道实盘:只有展示账户喊单和直播里说的;期权一律按正股近似,期权本身的盈亏没算',
        '- 不会自己更新:数据定格在导出那天(见上面的日期),新数据要整理者重新导出',
        '- 临时分组的统计只能当线索:样本常常很小,不能推翻上面的正式检验结论',
    ]
    return out


# ---------------------------------------------------------------- 分类成绩单
SC_ALIAS = {'总表': '总表', '判定': '总表', '选股': 'B', 'b': 'B', '买入': 'B', '离场': 'C', 'c': 'C', '卖出': 'C',
            '硬扛': 'D', 'd': 'D', '扛单': 'D', '大方向': 'A', 'a': 'A', '期货': 'F', '指数期货': 'F',
            '言行': 'P', '预设': 'P', '纪律': 'P'}
CAT = [('conviction', '信仰长线'), ('valuation', '估值'), ('turnaround', '困境反转'), ('technical', '技术/事件'),
       ('theme', '主题'), ('unclear', '不明')]
DIMS = [('A', '大方向(看多/看空之后大盘是否真的更好/更差)'), ('B', '选股(买的票之后跑赢 QQQ 吗)'),
        ('C', '离场(卖掉的票之后真的走弱吗)'), ('D', '硬扛(跌破止损线后继续拿,比当时止损好吗)')]


def scorecard(db, arg):
    p = os.path.join(D, 'scorecard.json')
    if not os.path.exists(p):
        return ['# 分类成绩单', '缺 data/scorecard.json(在 brant-lens 项目里跑 build_why_extras.py 生成)。']
    with open(p, encoding='utf-8') as f:
        sc = json.load(f)
    want = None if arg in (None, 'all') else SC_ALIAS.get(arg.lower(), SC_ALIAS.get(arg))
    if arg not in (None, 'all') and not want:
        return [f'没有「{arg}」这一块。可选:总表、选股、离场、硬扛、大方向、期货、言行;不带值看全部。']
    on = lambda k: want in (None, k)
    out = ['# 分类成绩单', f"{sc['sample']}。数字用修订版检验(清掉重复场次和别的老师讲话段之后重算),和原版不同的地方并列写出。",
           '**读法**:只有「正式判定」能下结论;其余全是事后分组〔探索性〕——样本常常很小、区间多数跨 0,只能当待验证的线索,'
           '不能当规则,更不能当现在的买卖依据。「跨 0」= 现有数据分不出好坏。']
    if on('总表'):
        out.append('\n## 正式判定(四个维度,口径在算之前写定)')
        for d, name in DIMS:
            r, o = sc['verdicts'][d]['revised'], sc['verdicts'][d]['original']
            n = f"看多 {r.get('n_up')} 周 / 看空 {r.get('n_dn')} 周" if d == 'A' else f"n={r.get('n')}"
            line = f"- **{d} {name}**:{r['value']:+.2%}{_ci(r.get('ci'))},{n} → **{r['verdict']}**"
            if o.get('verdict') != r.get('verdict'):
                line += f";原版 {o['value']:+.2%}{_ci(o.get('ci'))} → {o['verdict']}(原版是正式结论,两版并列,按「不稳定」看)"
            out.append(line)
        out.append('- 指标:A=看多周后 4 周 QQQ 平均收益 − 看空周后;B=入场后 12 周相对 QQQ 超额;'
                   'C=卖后 4 周相对 QQQ 超额取负(正=卖对);D=继续拿的结果 − 触发当天止损的结果')
    if on('B'):
        b = sc['B']
        ex = b.get('explore') or {}
        out.append('\n## 选股(买入后 12 周相对 QQQ;正 = 跑赢)〔以下分组探索性〕')
        if ex:
            out.append(f"- 整体:买入后 12 周标的平均 {ex.get('mean_stock_return', 0):+.1%},同期 QQQ {ex.get('mean_qqq_return', 0):+.1%};"
                       f"中位超额 {ex.get('median', 0):+.1%},{ex.get('win_rate', 0):.0%} 的持仓段跑赢")
        st = b.get('strata') or {}
        out.append('### 按买入理由(机器打的标,约两成误差)')
        out += [_row(lab, (st.get('category') or {}).get(k)) for k, lab in CAT]
        out.append('### 按买入时的行情')
        out += [_row(k, v) for k, v in (st.get('regime') or {}).items()]
        out.append('### 按年份')
        out += [_row(k, v) for k, v in sorted((st.get('year') or {}).items())]
        out += [_row(f'{k}(2021-12 是他自述转型的时间)', v) for k, v in (st.get('period') or {}).items()]
        out.append('### 按他语气里的把握(抽卡时按说话的确定程度标的;「无」= 喊单没写理由)')
        out += [_row(k, (st.get('conviction') or {}).get(k)) for k in ('强', '中', '弱', '无')]
        out.append('### 按仓位大小(看原话里怎么说;没说大小的占多数)')
        for k, lab in (('大仓', '原话说重仓/满仓/半仓'), ('小仓', '原话说小仓/试仓/博一下'), ('没说', '没说大小')):
            s = ((sc.get('size') or {}).get(k) or {}).get('B')
            if s:
                out.append(_row(lab, s))
        su = sc.get('size_usd') or {}
        if su.get('hi'):
            out.append(f"- 喊单写了金额的 {su.get('n')} 段(中位约 ${su.get('median_usd', 0):,.0f},展示账户,只作相对参考):"
                       f"金额大的一半 {su['hi']['mean']:+.1%}{_ci(su['hi'].get('ci'))};小的一半 {su['lo']['mean']:+.1%}{_ci(su['lo'].get('ci'))}")
        out.append('### 回避、做空、实际持有期')
        out.append(_row('说「不买/别碰」之后 12 周,那只票相对 QQQ 取负(正 = 回避对了)', b.get('avoid_accuracy'), '说对', '次'))
        out.append(_row('做空选的票(正 = 空对了)', b.get('short_picks'), '空对'))
        hp = b.get('holding_period') or {}
        if hp:
            out.append(_row(f"按实际持有期算(有明确清仓的,中位持有 {hp.get('median_days', 0):.0f} 个交易日)", hp))
        lv = (st.get('levered') or {}).get('True')
        if lv:
            out.append(_row('用杠杆 ETF 买的(折回底层标的算)', lv))
    if on('C'):
        c = sc['C']
        st = c.get('strata') or {}
        out.append('\n## 离场(卖出后 4 周,标的相对 QQQ 取负;正 = 卖对)〔分组探索性〕')
        for k in ('全清', '减仓'):
            out.append(_row(k, (st.get('full') or {}).get(k), '卖对', '次'))
        for k in ('止盈', '止损', '不明'):
            out.append(_row(f'理由粗分:{k}', (st.get('pl') or {}).get(k), '卖对', '次'))
        if c.get('h12'):
            out.append(_row('把卖后观察期拉长到 12 周', c['h12'], '卖对', '次'))
        ae = sc.get('after_exit') or {}
        if ae.get('K1'):
            k1 = ae['K1']
            out.append(f"- 大赚清仓后又追高买回(再犯检测 K1):判定样本内 {k1['n']} 次,买回后 12 周相对 QQQ 平均 {k1['mean']:+.1%}{_ci(k1.get('ci'))};"
                       f"其余买入平均 {k1.get('others', 0):+.1%}")
        if ae.get('K9'):
            k9 = ae['K9']
            out.append(f"- 浮盈 ≥10% 却一股没减、最后吐掉一半以上(K9):{k9['den']} 次清仓里 {k9['n']} 次,其中 {k9.get('turned_loss')} 次转亏,"
                       f"回吐中位 {k9.get('giveback_median', 0):.0%}")
        if ae.get('K6'):
            k6 = ae['K6']
            out.append(f"- 卖后 20 天内又涨 15% 以上(K6,没有基准,只作描述):{k6['den']} 次清仓里 {k6['n']} 次")
        for k, lab in (('大仓', '原话说大仓的'), ('小仓', '原话说小仓的')):
            s = ((sc.get('size') or {}).get(k) or {}).get('C4')
            if s:
                out.append(_row(f'{lab}卖出', s, '卖对', '次'))
    if on('D'):
        d = sc['D']
        m = d.get('must_report') or {}
        out.append('\n## 硬扛(跌破止损线:正股 −15% / 杠杆 ETF −25%;正 = 继续拿比当天止损好)〔分组探索性〕')
        if m:
            qs = m.get('max_dd_quantiles') or {}
            out.append(f"- 代价(必须和平均数一起看):只有 {m.get('recovered_rate', 0):.0%} 最后回到成本价(回本的中位用 {m.get('days_to_recover_median')} 个交易日);"
                       f"扛的过程中最大浮亏中位 {qs.get('0.5', 0):.0%},四分之一的情况 ≤ {qs.get('0.25', 0):.0%},十分之一 ≤ {qs.get('0.1', 0):.0%}")
            w5 = m.get('worst5') or []
            if w5:
                out.append('- 最惨 5 笔:' + '、'.join(f"{x['ticker']}({x['trigger'][:7]} 触发,最终 {x['actual']:.0%})" for x in w5))
        st = d.get('strata') or {}
        for k, lab in (('False', '正股'), ('True', '杠杆 ETF')):
            out.append(_row(lab, (st.get('levered') or {}).get(k), '扛对', '次'))
        out += [_row(k, v, '扛对', '次') for k, v in (st.get('env') or {}).items()]
        ub = d.get('unknown_bounds') or {}
        if ub.get('best_mean') is not None:
            out.append(f"- 触发后再没提过的那些仓位(沉默的亏损票)怎么算,结论会变:都按触发日卖了算,整体平均 {ub['best_mean']:+.1%}{_ci(ub.get('best_ci'))};"
                       f"都按拿满 26 周算,整体平均 {ub['worst_mean']:+.1%}{_ci(ub.get('worst_ci'))}")
        s = ((sc.get('size') or {}).get('小仓') or {}).get('D')
        if s:
            out.append(_row('原话说小仓的扛单', s, '扛对', '次'))
    if on('A'):
        a = sc['A']
        v = sc['verdicts']['A']['revised']
        hr = a.get('hit_rate') or {}
        out.append('\n## 大方向')
        out.append(f"- 看多周之后 4 周 QQQ 平均 {v.get('mean_up', 0):+.2%},看空周之后 {v.get('mean_dn', 0):+.2%}")
        if hr:
            out.append(f"- 表态周的 4 周命中率 {hr.get('his', 0):.1%};同样这些周「一直看多」{hr.get('always_long_same_weeks', 0):.1%},"
                       f"全部周一直看多 {hr.get('always_long_all_weeks', 0):.1%}(n={hr.get('n')} 周)")
        tf = a.get('trend_following') or {}
        if tf:
            out.append(f"- 对照:只看「QQQ 在 50 日线上看多、下看空」的多空收益差 {tf.get('value', 0):+.2%}{_ci(tf.get('ci'))}")
        sd = a.get('say_do_agreement') or {}
        if sd:
            out.append(f"- 言行一致:表态的周里,指数期货/杠杆指数 ETF 的持仓净方向和嘴上方向一致的占 {sd.get('rate', 0):.0%}({sd.get('n_weeks')} 周)")
    if on('F'):
        fu = sc.get('futures') or {}
        by = fu.get('by') or {}
        out.append(f"\n## 指数期货波段(探索性,不是事先写定口径的检验;跨夜 {fu.get('n_swing')} 笔,日内 {fu.get('n_intraday')} 笔不计)")
        out.append('每笔收益是指数涨跌幅(没乘杠杆);「扣自然涨幅」= 减去同样持有天数里指数平均会涨多少,正 = 比随便挑个时点强。'
                   '没写价格的平仓按当天收盘近似。')
        for k in ('全部|做多', '全部|做空', '纳指|做多', '纳指|做空', '小盘|做多', '小盘|做空'):
            s = by.get(k)
            if s:
                out.append(f"- {k.replace('|', ' ')}:{s['n']} 笔,每笔平均 {s['mean']:+.2%},赚钱 {s['win']:.0%};"
                           f"扣自然涨幅后 {s.get('edge', 0):+.2%}{_ci(s.get('edge_ci'))}")
        rb = fu.get('robust_no_approx') or {}
        if rb:
            out.append('- 只算有成交价的:' + ';'.join(
                f"{k} {s['n']} 笔 扣自然涨幅后 {s.get('edge', 0):+.2%}{_ci(s.get('edge_ci'))}" for k, s in rb.items() if isinstance(s, dict)))
    if on('P'):
        out.append('\n## 言行对账:预设点位和认错条件(2026-10 起,每日总结登记;样本小)')
        cnt = collections.Counter(p.get('status') for p in db.presets)
        done, miss = cnt.get('已触发-照做', 0), cnt.get('已触发-没做', 0)
        out.append(f"- 共登记 {len(db.presets)} 条:" + '、'.join(f'{k} {v}' for k, v in cnt.most_common()))
        if done + miss:
            out.append(f"- 条件到了的 {done + miss} 条里,照做 {done} 条({done / (done + miss):.0%}),没做 {miss} 条;另有 {cnt.get('改口', 0)} 条中途改口")
        out.append('- 逐条看:`--presets all`')
    out.append('\n---\n口径与局限:期权一律按正股近似;2023-10 以前价格是收盘近似;42% 的持仓段没有明确清仓;'
               '战绩依据展示账户喊单和直播言论,不是实盘。详细报告:`--ref track-record`、`--ref track-record-v2`;已知数据问题:`--ref known-issues`。')
    return out


# ---------------------------------------------------------------- 个股档案
def dossier(db, a):
    q = W.CN.get(a.dossier, a.dossier.upper())
    names = W.names_of(q)
    d0, d1 = W.day(a.frm), W.day(a.to, end=True)
    ts = [t for t in db.trades if (t['ticker'] == q or t['underlying'] == q) and _inr(t['date'], d0, d1)]
    vs = sorted((v for d, lst in db.views.items() if _inr(d, d0, d1) for v in lst if W.asset_hit(v['asset'], names)),
                key=lambda v: (v['date'], v.get('t') or ''))
    if not ts and not vs:
        return [f'# {q} 个股档案', '没有记录。确认代码(杠杆 ETF 按底层标的归并,如 TSLL 归 TSLA),或放宽时间。']
    alld = sorted([t['date'] for t in ts] + [v['date'] for v in vs])
    out = [f"# {q} 个股档案:{alld[0]} ~ {alld[-1]}",
           '(把这只票的看法、操作、结果、复盘拼在一页;每块只列要点,细节按末尾的查法往下查。单只票的数字只是这只票的样本,不能说明整体)']
    # 1 概览
    cnt = collections.Counter(W.KIND.get(t['kind'], t['kind']) for t in ts)
    yr = collections.Counter(t['date'][:4] for t in ts if t['kind'] in ('open', 'reduce', 'exit', 'other'))
    tools = collections.Counter('期权' if t['option'] else '杠杆ETF' if t['levered'] else '正股' for t in ts
                                if t['kind'] in ('open', 'reduce', 'exit', 'other'))
    out.append('\n## 概览')
    out.append(f"- 操作事件 {len(ts)} 个:" + '、'.join(f'{k} {v}' for k, v in cnt.most_common()))
    if yr:
        out.append('- 买卖按年:' + '、'.join(f'{k}×{v}' for k, v in sorted(yr.items())) + ';工具:' + '、'.join(f'{k} {v}' for k, v in tools.most_common()))
    # 2 持仓段
    ps = sorted((p for p in db.pos.values() if (p['ticker'] == q or p['underlying'] == q) and _inr(p['start'], d0, d1)),
                key=lambda p: p['start'])
    if ps:
        out.append(f'\n## 持仓段 {len(ps)} 段' + (f'(只列最近 {a.max} 段)' if len(ps) > a.max else ''))
        bs = [p['B']['excess'] for p in ps if p.get('B')]
        if bs:
            out.append(f"- 其中 {len(bs)} 段有 12 周结果(只算到 {JUDGE_END}):相对 QQQ 平均 {sum(bs) / len(bs):+.1%},"
                       f"{sum(x > 0 for x in bs)}/{len(bs)} 段跑赢")
        for p in ps[-a.max:]:
            end = (f"{p['end']}({'明确平仓' if p['end_kind'] == 'explicit' else p['end_kind']})" if p['end']
                   else f"未见平仓(最后提到 {p['last_evidence']})")
            bits = [f"{p['position_id']} {p['ticker']} {'做空' if p['side'] == 'short' else '做多'}({_pos_tool(db, p)})", f"{p['start']} → {end}"]
            if p.get('B'):
                bits.append(f"12 周超额 {p['B']['excess']:+.1%}")
            elif p.get('sample') == '留出':
                bits.append('留出期,不给数字')
            if p.get('D'):
                dd = p['D']
                bits.append(f"跌破止损线后继续拿({dd['trigger']} 触发" + (f",最大浮亏 {dd['max_dd']:.0%}" if dd.get('max_dd') is not None else '')
                            + (',已回本' if dd.get('recovered') else ',没回本') + ')')
            ks = collections.Counter(k['k'] + ' ' + (db.mis.get(k['b']) or {}).get('name', k['b']) for k in p.get('kchecks') or [])
            if ks:
                bits.append('再犯检测:' + '、'.join(k + (f' ×{n}' if n > 1 else '') for k, n in ks.items()))
            out.append('- ' + ';'.join(bits))
    # 3 看法时间线
    if vs:
        out.append(f'\n## 看法时间线({len(vs)} 条观点,按季度)')
        qt = collections.OrderedDict()
        for v in vs:
            key = f"{v['date'][:4]}Q{(int(v['date'][5:7]) - 1) // 3 + 1}"
            qt.setdefault(key, collections.Counter())[v['direction'] if v['direction'] in ('看多', '看空', '震荡', '不确定') else '其他'] += 1
        for k, c in qt.items():
            out.append(f"- {k}:" + ' · '.join(f'{d} {n}' for d, n in c.most_common()))
        hard = [v for v in vs if v['direction'] in ('看多', '看空')]
        flips = []
        for prev, cur in zip(hard, hard[1:]):
            if prev['direction'] != cur['direction']:
                gap = (dt.date.fromisoformat(cur['date']) - dt.date.fromisoformat(prev['date'])).days
                if gap <= 14:
                    flips.append((prev, cur, gap))
        if flips:
            out.append(f'\n### 两周内看法反转 {len(flips)} 处(列最近 {min(5, len(flips))} 处;为什么变看原话,不替他补原因)')
            for prev, cur, gap in flips[-5:]:
                out.append(f"- {prev['date']} {prev['direction']}「{_clip(prev['quote'], 50)}」({prev['card_id']})→ "
                           f"{cur['date']} {cur['direction']}「{_clip(cur['quote'], 50)}」({cur['card_id']}),隔 {gap} 天")
        out.append(f"- 最近一条:{vs[-1]['date']} {vs[-1]['direction']}/{vs[-1]['horizon']}:{_clip(vs[-1]['chain'], 100)}  「{_clip(vs[-1]['quote'], 60)}」({vs[-1]['card_id']})")
    # 4 不买/观望
    sk = [t for t in ts if t['kind'] in ('watch', 'avoid')]
    if sk:
        c = collections.Counter(t['date'][:4] for t in sk)
        out.append(f"\n## 观望 / 不买 {len(sk)} 次(按年:" + '、'.join(f'{k}×{v}' for k, v in sorted(c.items())) + ')')
        for t in sk[-3:]:
            card = next((x for x in t['cards'] if x['src'] == '直播'), t['cards'][0] if t['cards'] else {})
            out.append(f"- {t['date']} {W.KIND.get(t['kind'])} · {t['event_id']}:{_clip(card.get('reason') or '(卡上没记理由)', 90)}")
    # 5 复盘
    hs = [h for h in db.hind if _inr(h.get('date'), d0, d1)
          and W.mentions(f"{h.get('subject')} {h.get('lesson')} {h.get('quote')}", names)]
    if hs:
        out.append(f'\n## 事后复盘 / 自我修正里提到它 {len(hs)} 次(列最近 5 次)')
        for h in hs[-5:]:
            out.append(f"- {h['date']} {h['kind']}:{_clip(h.get('subject'), 60)} → {_clip(h.get('lesson') or '(改法未说)', 90)}({h['card_id']})")
    # 6 预设
    pre = [p for p in db.presets if p.get('status') not in W.DONE
           and q in {W.CN.get(x.strip(), x.strip().upper()) for x in (p.get('ticker') or '').split('/')}]
    if pre:
        out.append(f'\n## 还没了结的预设 {len(pre)} 条')
        for p in pre:
            out.append(f"- {p['preset_id']} {p.get('first')} · {p.get('kind')}:{p.get('condition')} → {p.get('action')}")
    out.append(f"\n---\n往下查:每笔的理由和原话 `{q} --from 年-月 --kind all`;一整段持仓 `--position 编号`;"
               f"只看为什么不买 `{q} --kind skip`;原文里搜 `--grep \"{q}\"`。")
    return out


# ---------------------------------------------------------------- 还没见平仓的持仓段(和真实持仓对账用)
def open_positions(db, a):
    dates = [t['date'] for t in db.trades if t.get('date')]
    asof = max(dates) if dates else ''
    ps = [p for p in db.pos.values() if not p.get('end')]
    total = len(ps)
    if a.open_ != 'all' and asof:
        cut = (dt.date.fromisoformat(asof) - dt.timedelta(days=180)).isoformat()
        ps = [p for p in ps if (p.get('last_evidence') or p['start']) >= cut]
    ps.sort(key=lambda p: (p.get('last_evidence') or p['start']), reverse=True)
    out = [f"# 数据里还没见平仓的持仓段:{len(ps)} 段" + ('' if a.open_ == 'all' else f'(最近 180 天提到过的;全部 {total} 段用 --open all)')
           + f",数据截至 {asof}",
           '「没见平仓」只表示之后的直播和喊单里没记到卖出:可能真的还拿着,也可能卖了没说,或者卖出没对上这一段。'
           '这是展示账户喊单和直播言论拼出来的,不是任何券商账户的真实持仓,也不记股数。',
           '和真实持仓不一致的,用 `--flag 持仓段号 --note "已于某日清仓 / 实际没买"` 记一句。']
    for p in ps[:a.max]:
        pre = sum(1 for x in db.presets if x.get('status') not in W.DONE
                  and p['underlying'] in {W.CN.get(y.strip(), y.strip().upper()) for y in (x.get('ticker') or '').split('/')})
        px = f"入场价约 {p['entry_price']}" if p.get('entry_price') is not None else '入场价没记'
        out.append(f"- {p['position_id']} {p['ticker']} {'做空' if p['side'] == 'short' else '做多'}({_pos_tool(db, p)}):{p['start']} 开仓,"
                   f"{px},加仓 {p.get('n_adds')} 次,最后一次提到 {p.get('last_evidence')}"
                   + (f";这只票还有 {pre} 条没了结的预设" if pre else ''))
    if len(ps) > a.max:
        out.append(f'(只列 {a.max} 段,加 --max N 调大)')
    return out


# ---------------------------------------------------------------- 更正入口
def _fb_file():
    return os.path.join(SKILL, 'feedback', 'corrections.jsonl')


def _resolve(db, target):
    """编号 → (类型, 现在记的是什么)。事件号会随数据重建顺移,所以把当前内容一起记下,整理者按内容对回源头"""
    t = target.strip()
    u = t.upper()
    if u in db.tr:
        e = db.tr[u]
        return u, '操作事件', {'date': e['date'], 'time': e.get('time'), 'ticker': e['ticker'], 'kind': e['kind'], 'action': e.get('action'),
                           'price': e.get('price'), 'position_id': e.get('position_id'), 'cards': [c['card_id'] for c in e['cards']]}
    if u in db.pos:
        p = db.pos[u]
        return u, '持仓段', {'ticker': p['ticker'], 'side': p['side'], 'start': p['start'], 'end': p['end'], 'end_kind': p['end_kind'],
                          'entry_price': p.get('entry_price'), 'category': p.get('category'), 'n_events': len(p['event_ids'])}
    for p in db.presets:
        if p['preset_id'].upper() == u:
            return p['preset_id'], '预设', {'first': p.get('first'), 'ticker': p.get('ticker'), 'condition': p.get('condition'),
                                          'action': p.get('action'), 'status': p.get('status')}
    if t in db.ideas:
        i = db.ideas[t]
        return t, '理念卡', {'date': i['date'], 't': i.get('t'), 'rule_id': i.get('rule_id'), 'rule': i.get('rule'), 'quote': _clip(i.get('quote'), 60)}
    for e in db.trades:
        for c in e['cards']:
            if c['card_id'] == t:
                return t, '操作卡', {'event_id': e['event_id'], 'date': e['date'], 'ticker': e['ticker'], 'kind': e['kind'], 'quote': _clip(c.get('quote'), 60)}
    if u in db.rules:
        return u, '理念', {'name': db.rules[u].get('name'), 'statement': _clip(db.rules[u].get('statement'), 120)}
    if u in db.mis:
        return u, '失误类型', {'name': db.mis[u].get('name')}
    if re.fullmatch(r'J\d+', u):
        return u, '裁决', {}
    return t, '其他', {}


def flag(db, a):
    f = _fb_file()
    if a.flag == 'list':
        rows = []
        for p in (f, os.path.join(os.getcwd(), 'brant-feedback.jsonl')):
            if os.path.exists(p):
                with open(p, encoding='utf-8') as fh:
                    rows += [json.loads(l) for l in fh if l.strip()]
        if not rows:
            return ['# 更正记录', '还没有记录。用法:`--flag <编号> --note "实际是……"`(编号可以是事件 E…、持仓段 P…、卡片出处、理念编号;没有编号就写标的或「总体」)。']
        out = [f'# 更正记录 {len(rows)} 条(文件:{f})']
        for r in rows:
            out.append(f"- {r['ts'][:16]} 〔{r.get('tag')}〕{r['target']}({r.get('target_kind')}):{r['note']}")
        return out
    if not a.note:
        return ['要写更正内容:`--flag <编号> --note "实际是……"`。事后才想起来的理由用 `--tag 事后补充`(会单独标注,不混进当场原话)。']
    target, kind, snap = _resolve(db, a.flag)
    dates = [t['date'] for t in db.trades if t.get('date')]
    rec = {'ts': dt.datetime.now().isoformat(timespec='seconds'), 'target': target, 'target_kind': kind,
           'tag': a.tag or '更正', 'note': a.note, 'snapshot': snap, 'data_asof': max(dates) if dates else None}
    line = json.dumps(rec, ensure_ascii=False)
    used = None
    for p in (f, os.path.join(os.getcwd(), 'brant-feedback.jsonl')):  # 技能目录写不了(沙箱)就写到当前目录
        try:
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with open(p, 'a', encoding='utf-8') as fh:
                fh.write(line + '\n')
            used = p
            break
        except OSError:
            continue
    if not used:
        return ['# 更正没有写进文件(技能目录和当前目录都不可写)', '请把下面这一行原样发给整理者:', line]
    out = [f"# 已记下:〔{rec['tag']}〕{target}({kind})", f"- 内容:{a.note}"]
    if snap:
        out.append('- 现在数据里记的是:' + json.dumps(snap, ensure_ascii=False))
    elif kind == '其他':
        out.append('- 没找到这个编号,按自由备注记下了;能给出事件号(E…)或持仓段号(P…)的话,整理者更容易对上')
    out += [f'- 写在:{used}',
            '- 这条更正**还没有改动数据**:查询结果在整理者改完源头、重新导出之前不会变。把这个文件提交推送(或发给整理者)才会回流。']
    return out


def unverified(db, a):
    d0, d1 = W.day(a.frm), W.day(a.to, end=True)
    ev = [t for t in db.trades if t.get('caution') and _inr(t['date'], d0, d1)]
    tick = sorted((t for t in ev if t['caution'] in ('unknown_ticker', 'low_conf_unverified', 'speaker_uncertain')),
                  key=lambda t: t['date'], reverse=True)
    # 买入理由只给美股个股/ETF 的持仓分过类;指数期货、加密货币、非美股本来就不在分类范围,不算「没核实」
    nocat = sorted((p for p in db.pos.values() if _inr(p['start'], d0, d1)
                    and (p.get('category') == 'unclear' or (p.get('category') is None and _pos_scope(db, p) == 'equity'))),
                   key=lambda p: p['start'], reverse=True)
    n_unclear = sum(1 for p in nocat if p.get('category') == 'unclear')
    mode = a.unverified
    lab = {'unknown_ticker': '标的没认出来', 'low_conf_unverified': '标的拿不准', 'speaker_uncertain': '讲者拿不准(可能是别的老师)'}
    if mode == 'summary':
        c = collections.Counter(t['caution'] for t in tick)
        out = ['# 只有本人能核实的条目', '(这些是整理时拿不准的地方;本人一眼能认出来的,用 `--flag 编号 --note "……"` 记一句就行)',
               f"- 标的或讲者没核实的事件 {len(tick)} 个:" + '、'.join(f'{lab[k]} {v}' for k, v in c.most_common()),
               '  - 按年:' + '、'.join(f'{k}×{v}' for k, v in sorted(collections.Counter(t['date'][:4] for t in tick).items())),
               f"- 买入理由说不清的个股持仓段 {len(nocat)} 段:{n_unclear} 段分过类但理由不明(成绩单里的「不明」组),"
               f"{len(nocat) - n_unclear} 段是 2026-07 以后的新仓还没分类。指数期货、加密货币、非美股不在分类范围,没算在内",
               '  - 按年:' + '、'.join(f'{k}×{v}' for k, v in sorted(collections.Counter(p['start'][:4] for p in nocat).items())),
               '- 逐条看:`--unverified ticker`(标的/讲者)、`--unverified reason`(买入理由);加 `--from 2025 --max 40` 限定范围',
               '- 买入理由的类别:信仰长线 / 估值 / 困境反转 / 技术或事件 / 主题。事后补的理由用 `--tag 事后补充`']
        return out
    if mode == 'ticker':
        out = [f'# 标的或讲者没核实的事件 {len(tick)} 个(从近到远,列 {min(a.max, len(tick))} 个)']
        for t in tick[:a.max]:
            card = next((x for x in t['cards'] if x['src'] == '直播'), t['cards'][0] if t['cards'] else {})
            out.append(f"- {t['event_id']} {t['date']} {card.get('t') or t.get('time') or ''} · 记成 {t['ticker']} {W.KIND.get(t['kind'], t['kind'])}"
                       f"〔{lab.get(t['caution'], t['caution'])}〕:「{_clip(card.get('quote'), 90)}」({card.get('card_id')})")
        return out
    out = [f'# 买入理由说不清的个股持仓段 {len(nocat)} 段(从近到远,列 {min(a.max, len(nocat))} 段)']
    for p in nocat[:a.max]:
        e = next((db.tr[x] for x in p['event_ids'] if x in db.tr), None)
        card = next((x for x in (e or {}).get('cards', []) if x['src'] == '直播'), ((e or {}).get('cards') or [{}])[0])
        why = card.get('reason') or card.get('entry_reason') or '(卡上没记理由)'
        out.append(f"- {p['position_id']} {p['ticker']} {'做空' if p['side'] == 'short' else '做多'} {p['start']} 开仓:{_clip(why, 100)}")
    return out


# ---------------------------------------------------------------- 自由统计(SQLite)
def _b(x):
    return None if x is None else int(bool(x))


def _first_card(t):
    return next((c for c in t['cards'] if c['src'] == '直播'), t['cards'][0] if t['cards'] else {})


def _tool(t):
    return '期权' if t.get('option') else '杠杆ETF' if t.get('levered') else \
        {'macro': '指数期货宏观', 'crypto': '加密货币', 'non_us': '非美股', 'basket': '一篮子'}.get(t.get('scope'), '正股')


def _r_trade(t):
    c, x = _first_card(t), t.get('C') or {}
    return {'event_id': t['event_id'], 'date': t['date'], 'year': int(t['date'][:4]), 'time': t.get('time'), 'ticker': t['ticker'],
            'underlying': t['underlying'], 'kind': t['kind'], 'action': t.get('action'), 'side': t.get('side'), 'tool': _tool(t),
            'scope': t.get('scope'), 'price': t.get('price'), 'price_kind': t.get('price_kind'), 'regime': t.get('regime'),
            'position_id': t.get('position_id'), 'caution': t.get('caution'), 'src': c.get('src'), 'conviction': c.get('conviction'),
            'reason': c.get('reason') or c.get('entry_reason'), 'quote': c.get('quote'), 'card_id': c.get('card_id'),
            'n_ideas': len(t.get('ideas') or []), 'switch_said': _b((t.get('switch') or {}).get('said')),
            'c_score': x.get('score'), 'c_stock': x.get('r'), 'c_qqq': x.get('q'), 'c_reason': x.get('reason'),
            'sample': '判定' if t['date'] <= JUDGE_END else '留出'}


def _r_pos(p):
    b, d, s = p.get('B') or {}, p.get('D') or {}, p.get('size') or {}
    return {'position_id': p['position_id'], 'ticker': p['ticker'], 'underlying': p['underlying'], 'side': p['side'], 'start': p['start'],
            'start_year': int(p['start'][:4]) if p.get('start') else None, 'end': p.get('end'), 'end_kind': p.get('end_kind'),
            'last_evidence': p.get('last_evidence'), 'entry_price': p.get('entry_price'), 'n_adds': p.get('n_adds'),
            'n_events': len(p.get('event_ids') or []), 'option': _b(p.get('option')), 'levered': _b(p.get('levered')),
            'regime': p.get('regime'), 'category': p.get('category'), 'sample': p.get('sample'), 'size_label': s.get('label'),
            'size_usd': s.get('usd'), 'b_excess': b.get('excess'), 'b_stock': b.get('r'), 'b_qqq': b.get('q'), 'b_conviction': b.get('conviction'),
            'd_trigger': d.get('trigger'), 'd_diff': d.get('diff'), 'd_max_dd': d.get('max_dd'), 'd_recovered': _b(d.get('recovered')) if d else None,
            'd_days_to_recover': d.get('days_to_recover'), 'kchecks': ','.join(k['k'] for k in p.get('kchecks') or []) or None}


def _r_idea(i):
    return {'card_id': i['card_id'], 'date': i.get('date'), 'year': int(i['date'][:4]) if i.get('date') else None, 't': i.get('t'),
            'rule_id': i.get('rule_id'), 'rule_name': i.get('rule_name'), 'rule': i.get('rule'), 'trigger': i.get('trigger'),
            'quote': i.get('quote'), 'generality': i.get('generality'), 'source': i.get('source'), 'fresh': _b(i.get('fresh')),
            'n_events': len(i.get('events') or [])}


def _r_rule(r):
    return {'id': r['id'], 'name': r.get('name'), 'statement': r.get('statement'), 'status': r.get('status'), 'judged': _b(r.get('judged')),
            'grade': r.get('grade'), 'grade_v2': r.get('grade_v2'), 'n': r.get('n'), 'first': r.get('first'), 'last': r.get('last'),
            'tier': r.get('tier'), 'consistent_est': r.get('consistent_est'), 'contrary_v2': r.get('contrary_v2'),
            'violates_sc': r.get('violates_sc'), 'labels': ','.join(r.get('labels') or []) or None,
            'skill_exclude': _b(r.get('skill_exclude')), 'condition_basis': r.get('condition_basis')}


def _keep(keys):
    return lambda r: {k: (','.join(map(str, r[k])) if isinstance(r.get(k), list) else r.get(k)) for k in keys}


SQL_TABLES = [  # 表名, 来源文件, 行函数, 一句话说明
    ('trades', 'trades.jsonl', _r_trade, '操作事件:每个买入/加仓/减仓/清仓/持有/观望/不买;c_score 是卖后 4 周相对 QQQ 取负(正=卖对)'),
    ('positions', 'positions.jsonl', _r_pos, '持仓段:从开仓到平仓;b_excess 是入场后 12 周相对 QQQ 超额;d_* 是跌破止损线后的结果'),
    ('views', 'views.jsonl', _keep(['card_id', 'date', 't', 'asset', 'kind', 'direction', 'horizon', 'chain', 'quote']),
     '观点:对某只票/板块/大盘的看法(direction 看多/看空/震荡/不确定,horizon 期限)'),
    ('ideas', 'ideas.jsonl', _r_idea, '理念原话:他每一次讲某条理念;rule_id 对应 rules.id'),
    ('rules', 'rules.jsonl', _r_rule, '理念台账:每条理念的陈述、有效期 status、证据等级 grade_v2'),
    ('presets', 'presets.jsonl', _keep(['preset_id', 'first', 'date', 'ticker', 'kind', 'condition', 'action', 'status', 'quote', 'note', 'stem']),
     '预设点位与认错条件(2026-10 起)'),
    ('hindsight', 'hindsight.jsonl', _keep(['card_id', 'date', 'kind', 'subject', 'result', 'lesson', 'quote']), '事后复盘与自我修正'),
    ('sessions', 'sessions.jsonl', _keep(['date', 'stem', 'source', 'market_state', 'tone', 'basis', 'notable', 'key_tickers']), '每场直播小结'),
    ('mistakes', 'mistakes.jsonl', _keep(['id', 'name', 'pattern', 'n', 'repeat_said', 'first', 'last', 'k', 'his_fix']), '失误类型 B1–B35'),
    ('rulings', 'rulings.jsonl', _keep(['j', 'title', 'date', 'ids', 'conclusion', 'data']), '整理者逐条定的裁决 J1 起'),
]
SQL_EXAMPLES = [
    "select start_year, count(*) n, round(avg(b_excess)*100,1) 平均超额pct, round(avg(b_excess>0)*100) 跑赢pct "
    "from positions where b_excess is not null group by start_year",
    "select category, count(*) n, round(avg(b_excess)*100,1) 平均超额pct from positions where b_excess is not null group by category order by n desc",
    "select substr(date,1,7) 月, count(*) n from trades where underlying='NVDA' and kind='open' group by 月 order by 月",
    "select direction, count(*) from views where asset='TSLA' and date>='2026-01' group by direction",
]


def _sql_connect():
    srcs = [os.path.join(D, f) for _, f, _, _ in SQL_TABLES if os.path.exists(os.path.join(D, f))]
    newest = max(os.path.getmtime(p) for p in srcs)
    tag = re.sub(r'\W', '', os.path.basename(SKILL)) + '-' + format(abs(hash(SKILL)) % 10 ** 8, 'd')
    for path in (os.path.join(D, '.cache', 'why.sqlite'), os.path.join(tempfile.gettempdir(), f'{tag}-why.sqlite')):
        try:
            if not (os.path.exists(path) and os.path.getmtime(path) >= newest):
                os.makedirs(os.path.dirname(path), exist_ok=True)
                tmp = path + '.tmp'
                if os.path.exists(tmp):
                    os.remove(tmp)
                con = sqlite3.connect(tmp)
                _sql_build(con)
                con.close()
                os.replace(tmp, path)
            return sqlite3.connect('file:' + path.replace('\\', '/') + '?mode=ro', uri=True)
        except (OSError, sqlite3.Error):
            continue
    con = sqlite3.connect(':memory:')  # 哪都写不了就每次在内存里建(慢几秒)
    _sql_build(con)
    return con


def _sql_build(con):
    for name, fn, rowf, _ in SQL_TABLES:
        p = os.path.join(D, fn)
        if not os.path.exists(p):
            continue
        with open(p, encoding='utf-8') as f:
            rows = [rowf(json.loads(l)) for l in f if l.strip()]
        if name == 'sessions':
            rows = [r for r in rows if r.get('date')]
        if not rows:
            continue
        cols = list(rows[0].keys())
        con.execute(f"create table {name} ({', '.join(cols)})")
        con.executemany(f"insert into {name} values ({', '.join('?' * len(cols))})", [[r.get(c) for c in cols] for r in rows])
    con.commit()


def sql(a):
    q = a.sql.strip().rstrip(';')
    con = _sql_connect()
    if q.lower() == 'schema':
        out = ['# 自由统计:有哪些表', '(SQLite;只读,只能 select。日期是文本 YYYY-MM-DD;比例是小数,0.05 = 5%;布尔是 0/1)']
        for name, _, _, note in SQL_TABLES:
            try:
                cols = [r[1] for r in con.execute(f'pragma table_info({name})')]
                n = con.execute(f'select count(*) from {name}').fetchone()[0]
            except sqlite3.Error:
                continue
            out += [f'\n## {name}({n:,} 行):{note}', '列:' + '、'.join(cols)]
        out += ['\n## 取值', '- trades.kind:open 买入/开仓、reduce 减仓、exit 清仓、hold 持有、watch 观望、avoid 不买、other',
                '- trades.tool:正股 / 期权 / 杠杆ETF / 指数期货宏观 / 加密货币 / 非美股;杠杆 ETF 的 underlying 是底层标的(TSLL → TSLA)',
                '- positions.category(买入理由,机器打标约两成误差):conviction 信仰长线、valuation 估值、turnaround 困境反转、technical 技术/事件、theme 主题、unclear 不明、空 = 没分类',
                '- positions.sample / trades.sample:判定(≤2026-06-30,有战绩数字)/ 留出(之后,不给数字)',
                '\n## 例子'] + [f'- `{e}`' for e in SQL_EXAMPLES]
        return out
    if not re.match(r'(?is)^\s*(select|with)\b', q):
        return ['只能查询(select / with 开头)。先 `--sql schema` 看有哪些表和列。']
    try:
        cur = con.execute(q)
        rows = cur.fetchmany(a.max + 1)
    except sqlite3.Error as e:
        return [f'查询出错:{e}', '用 `--sql schema` 核对表名和列名。']
    cols = [d[0] for d in cur.description or []]
    fmt = lambda v: '' if v is None else (f'{v:.4g}' if isinstance(v, float) else _clip(str(v), 70))
    out = ['# 自由统计结果', ' | '.join(cols), ' | '.join('---' for _ in cols)]
    out += [' | '.join(fmt(v) for v in r) for r in rows[:a.max]]
    if len(rows) > a.max:
        out.append(f'(只显示前 {a.max} 行,加 --max N 调大)')
    out += ['', '**这是临时统计,不是正式检验**:回答时必须说明样本量;分组小于 20 的只当例子;结论只能说「待验证的线索」,'
            '不能推翻 `--scorecard` 里的正式判定。留出期(2026-07 起)没有战绩数字,不要自己拿行情去算。']
    return out


# ---------------------------------------------------------------- 核对文章里的原话和出处
_NORM = lambda s: re.sub(r'[\W_]', '', re.sub(r'\[\d{1,2}:\d{2}:\d{2}\]', '', s))


def check_essay(db, a):
    """每句「原话」必须出现在它后面所标场次的逐字稿(或文字线)里,找不到再全库搜;每个出处 [[场次#卡号]] / [[场次 进度]] 必须存在。
    最后一行「问题 0」才算通过。只读,不改文章。"""
    path = a.check_essay
    if not os.path.exists(path):
        return [f'找不到文章 {path}']
    tdir, cdir, _ = W.raw_dirs()
    if not os.path.isdir(tdir):
        return ['本机没有逐字稿原文,核对不了。']
    with open(path, encoding='utf-8') as f:
        art = f.read()
    cache, allnorm = {}, {}

    def raw(stem):  # 场次 → 原文;text:2025Q2 → 那个季度的文字线;call:… → 全部文字线
        if stem not in cache:
            if stem.startswith('text:'):
                p = os.path.join(cdir, stem[5:] + '.txt')
                cache[stem] = open(p, encoding='utf-8').read() if os.path.exists(p) else None
            elif stem.startswith('call:'):
                cache[stem] = '\n'.join(open(os.path.join(cdir, x), encoding='utf-8').read()
                                        for x in sorted(os.listdir(cdir)) if x.endswith('.txt')) if os.path.isdir(cdir) else None
            else:
                p = os.path.join(tdir, stem + '.host.txt')
                cache[stem] = open(p, encoding='utf-8').read() if os.path.exists(p) else None
        return cache[stem]

    def everywhere(nq):  # 全库搜(第一次用到时把全部原文归一化读进来)
        if not allnorm:
            for x in sorted(os.listdir(tdir)):
                if x.endswith('.host.txt'):
                    allnorm[x[:-9]] = _NORM(open(os.path.join(tdir, x), encoding='utf-8').read())
            if os.path.isdir(cdir):
                for x in sorted(os.listdir(cdir)):
                    if x.endswith('.txt'):
                        allnorm['text:' + x[:-4]] = _NORM(open(os.path.join(cdir, x), encoding='utf-8').read())
        return [k for k, v in allnorm.items() if nq in v][:3]

    known = set(db.ideas) | {c['card_id'] for t in db.trades for c in t['cards']} | {h['card_id'] for h in db.hind} \
        | {v['card_id'] for vs in db.views.values() for v in vs}
    cards_dir = os.path.join(W.project_root(), 'cards')  # 在 brant-lens 项目里能直接对卡片文件
    out, bad, soft, nosrc, n, srcs = [f'# 核对 {path}'], 0, 0, 0, 0, set()
    for line in art.splitlines():
        for m in re.finditer(r'\[\[([^\]]+)\]\]', line):
            srcs.add(m[1])
        for m in re.finditer(r'「([^「」]+)」', line):
            q = m[1]
            n += 1
            nq = _NORM(q)
            if not nq or re.fullmatch(r'[\W\w]{0,3}#\S*', q) or q == '场次#卡号':  # 讲解出处写法的占位词,不是引文
                continue
            after = re.search(r'\[\[([^\]]+)\]\]', line[m.end():])
            stem = after[1].split('#')[0].split(' ')[0] if after else None
            t = raw(stem) if stem else None
            if t is not None and nq in _NORM(t):
                continue
            hit = everywhere(nq)
            if hit and not stem:  # 标题、摘要里重复引用、没标出处的:原话确实存在,只提示
                nosrc += 1
                out.append(f"没标出处「{_clip(q, 40)}」:原话在 {'、'.join(hit)}(标题、速览里重复引用可以不标;正文里要补上)")
            elif hit:
                soft += 1
                out.append(f"⚠ 出处标错「{_clip(q, 40)}」:标的是 {stem},实际在 {'、'.join(hit)} → 改出处")
            else:
                bad += 1
                out.append(f"❌ 没找到「{_clip(q, 40)}」(标的出处 {stem or '没标'})→ 不是原话:改成逐字的原话,或去掉「」")
    for s in sorted(srcs):
        stem = s.split('#')[0].split(' ')[0]
        if '#' in s:
            cid = s.split('#', 1)[1]
            cf = os.path.join(cards_dir, stem + '.jsonl')
            if os.path.exists(cf):
                rows = [json.loads(l) for l in open(cf, encoding='utf-8') if l.strip()]
                ok = cid.isdigit() and (any(str(r.get('id', '')) == cid for r in rows) or int(cid) < len(rows))
            elif s in known:
                ok = True
            else:
                ok = raw(stem) is not None and not stem.startswith(('text:', 'call:'))
                if ok:
                    out.append(f'? 出处 {s}:场次存在,但这张卡不在打包数据里(可能是小结或复盘卡),卡号核对不了')
        else:
            t = raw(stem)
            ok = t is not None and len(s.split(' ')) > 1 and ('[' + s.split(' ')[1] + ']') in t
        if not ok:
            bad += 1
            out.append(f'❌ 出处不存在 [[{s}]]')
    out.append(f'原话 {n} 处 · 出处 {len(srcs)} 个 · 没标出处 {nosrc} 处 · 出处标错 {soft} 处 · 问题 {bad + soft}')
    if bad + soft == 0:
        out.append('通过:每句标了出处的原话都在所标场次的原文里,出处都存在。')
    return out


# ---------------------------------------------------------------- 参考资料
def _ref_locate(r):
    local = os.path.join(SKILL, 'references', r['file'])
    if os.path.exists(local):
        return local
    if r.get('src'):
        p = os.path.join(W.project_root(), *r['src'].split('/'))
        if os.path.exists(p):
            return p
    return None


def ref(a):
    man = os.path.join(SKILL, 'references', 'refs.json')
    if not os.path.exists(man):
        return ['# 参考资料', '缺 references/refs.json。']
    with open(man, encoding='utf-8') as f:
        refs = json.load(f)['refs']
    if a.ref == 'list':
        out = ['# 参考资料(`--ref 名字` 读其中一份)']
        for r in refs:
            p = _ref_locate(r)
            size = f'{os.path.getsize(p) / 1024:.0f}KB' if p else '本机没有这份'
            out.append(f"- **{r['name']}**({size}):{r['title']}。{r['when']}" + (f"\n  文件:{p}" if p else ''))
        return out
    r = next((x for x in refs if x['name'] == a.ref.lower()), None)
    if not r:
        return [f'没有「{a.ref}」这份。`--ref list` 看有哪些。']
    p = _ref_locate(r)
    if not p:
        return [f"「{r['name']}」不在本机(发行包里才带,或 brant-lens 项目不在默认位置)。"]
    with open(p, encoding='utf-8') as f:
        text = f.read()
    if len(text.encode('utf-8')) <= 40 * 1024:
        return [text.rstrip()]
    heads = [l for l in text.splitlines() if l.startswith('#')]
    return [f"# {r['title']}(文件较大,{len(text):,} 字,只列目录)", f'文件:{p}', '直接读这个文件,或按下面的小节标题搜索要看的那一段。', ''] + heads
