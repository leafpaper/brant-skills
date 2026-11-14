"""查 Brant 某笔/某段操作的「为什么」:操作事件表 × 理念事件表 × 当天观点/小结 × 事后复盘。只用标准库。

用法(在技能目录下运行):
  python scripts/why.py TSLA --from 2025-01 --to 2025-06          某标的某段时间的买卖(默认:买入/减仓/清仓)
  python scripts/why.py 特斯拉 --from 2025-03 --kind sell          只看卖出(减仓/清仓,含止盈止损)
  python scripts/why.py TSLA --from 2025 --kind switch            只看转仓(他说了换仓,或同场一卖一买)
  python scripts/why.py TSLA --from 2025-03 --kind skip           他为什么不买/观望(avoid/watch)
  python scripts/why.py --position P0612                          一整段持仓:从开仓到平仓每一步
  python scripts/why.py --event E04567                            单个操作
  python scripts/why.py --idea P7 --from 2025-01 --to 2025-06     理念事件:某条理念那段时间怎么说、同场做了什么
  python scripts/why.py --date 2025-03-27                         某一天:小结、全部操作、讲到的理念
  python scripts/why.py --daily                                   最新一场直播的每日总结(--daily 2026-10-21 指定日期,--daily list 列出全部)
  python scripts/why.py --presets                                 他设下、还没了结的预设点位和认错条件(--presets TSLA 只看该标的,--presets all 含已了结)
  python scripts/why.py --lesson B5                               一类失误/一条裁决/一条理念的事后检验与项目裁决(B5、J2、S13 …)
  python scripts/why.py --grep "老王|王老师|沃尔老师" --from 2026      原文搜索:全部直播逐字稿 + 文字线里找关键词(人物、往事、某句话);
                                                                  --src talk|text 只搜一边,--ctx N 前后带几行。原文在技能的 data/ 里或 brant-lens 项目里
  python scripts/why.py --intro                                   这个技能能做什么(功能介绍 + 数据范围 + 从哪开始)
  python scripts/why.py --scorecard                               分类成绩单:哪类买入/离场/扛单赚钱(--scorecard 选股|离场|硬扛|大方向|期货|言行 只看一块)
  python scripts/why.py --dossier TSLA                            个股档案:一只票的看法演变、持仓段结果、复盘、未了结预设
  python scripts/why.py --open                                    数据里还没见平仓的持仓段(和真实持仓对账用;--open all 不限最近 180 天)
  python scripts/why.py --flag E03882 --note "实际是 TSLL"         更正入口:记一条更正/补充(--tag 事后补充;--flag list 看已记的)
  python scripts/why.py --unverified                              只有本人能核实的条目(--unverified ticker|reason 逐条列)
  python scripts/why.py --sql "select …"                          自由统计:对数据库提问(--sql schema 看表和列;只读)
  python scripts/why.py --ref overview                            参考资料:一页结论、已知问题、战绩报告、失误与修正版…(--ref list)
  python scripts/why.py --check-essay essays/某篇.md               核对文章:每句「原话」都在所标场次的原文里、每个 [[出处]] 都存在(同名 .json 里的图表标注一起核)
  python scripts/why.py --topic "杠杆|融资"                        按关键词找理念(不知道编号时用)
事后检验口径:B=入场后 12 周相对 QQQ;C=卖后 4 周相对 QQQ;D=跌破止损线(正股 −15%/杠杆 −25%)后继续拿 vs 当天止损;
K1–K13=再犯检测。只覆盖判定样本(≤2026-06-30),留出期不给数字。这些是对过去的事后评估,不是现在的买卖建议。
选项:--kind buy|sell|switch|hold|skip|trade|all(默认 trade=买入+减仓+清仓+其他)  --max N(默认 25 个事件)
      --brief 精简输出  --after N 事后复盘往后看 N 天(默认 120)  --hmax N 事后复盘最多列 N 条
"""
import argparse
import collections
import datetime as dt
import json
import os
import re
import sys

D = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data')
CN = {'特斯拉': 'TSLA', '英伟达': 'NVDA', '苹果': 'AAPL', '微软': 'MSFT', '亚马逊': 'AMZN', '谷歌': 'GOOGL',
      '脸书': 'META', 'Meta': 'META', '波音': 'BA', '阿里': 'BABA', '阿里巴巴': 'BABA', '比特币': 'BTC', '英特尔': 'INTC',
      '超微': 'AMD', '奈飞': 'NFLX', '高通': 'QCOM', '台积电': 'TSM', '美光': 'MU', '甲骨文': 'ORCL', '帕兰提尔': 'PLTR',
      '京东': 'JD', '拼多多': 'PDD', '蔚来': 'NIO', '黄金': 'GLD', '原油': 'USO', '纳指': 'QQQ', '标普': 'SPY',
      '小盘股': 'IWM', '迪士尼': 'DIS', '耐克': 'NKE', '星巴克': 'SBUX', '可口可乐': 'KO', '伯克希尔': 'BRK.B'}
MARKET = {'大盘', '纳指', '标普', '三大指数', '美股', 'QQQ', 'SPY', 'NQ', 'MNQ', 'ES', '道指', '纳斯达克'}
KIND = {'open': '买入/开仓', 'reduce': '减仓', 'exit': '清仓', 'hold': '持有', 'watch': '观望', 'avoid': '不买', 'other': '其他'}
KIND_SHORT = {'open': '开空/加空', 'reduce': '减空单', 'exit': '平空单', 'hold': '空单持有'}  # 做空一侧的叫法
ACT = {'buy': '买入', 'add': '加仓', 'sell': '卖出', 'trim': '减仓', 'hold': '持有', 'watch': '观望', 'avoid': '回避',
       'buy_call': '买 call', 'sell_put': '卖 put', 'buy_put': '买 put', 'sell_call': '卖 call',
       'short': '开空/加空', 'trim_short': '减空单', 'cover': '平空单', 'hold_short': '空单持有'}
KINDSET = {'buy': {'open'}, 'sell': {'reduce', 'exit'}, 'hold': {'hold'}, 'skip': {'watch', 'avoid'},
           'trade': {'open', 'reduce', 'exit', 'other'}, 'all': set(KIND), 'switch': set(KIND)}


def jl(name):
    with open(os.path.join(D, name), encoding='utf-8') as f:
        return [json.loads(l) for l in f if l.strip()]


def secs(t):
    m = re.match(r'(\d+):(\d+):(\d+)', t or '')
    return int(m[1]) * 3600 + int(m[2]) * 60 + int(m[3]) if m else None


def day(s, end=False):
    """2025 / 2025-03 / 2025-03-27 → 日期字符串;end=True 取区间末日"""
    if not s:
        return None
    p = s.split('-')
    if len(p) == 1:
        return f'{p[0]}-12-31' if end else f'{p[0]}-01-01'
    if len(p) == 2:
        if not end:
            return f'{p[0]}-{p[1]}-01'
        y, m = int(p[0]), int(p[1])
        nxt = dt.date(y + (m == 12), m % 12 + 1, 1)
        return (nxt - dt.timedelta(days=1)).isoformat()
    return s


def names_of(t):
    return {t} | {k for k, v in CN.items() if v == t}


def mentions(text, names):
    text = text or ''
    return any((re.search(rf'(?<![A-Za-z]){re.escape(n)}(?![A-Za-z])', text) if n.isascii() else n in text)
               for n in names)


def asset_hit(asset, names):
    toks = set(re.split(r'[/、,,()()\s]+', asset or ''))
    return bool(toks & names)


class DB:
    def __init__(self):
        self.trades = jl('trades.jsonl')
        self.tr = {t['event_id']: t for t in self.trades}
        self.pos = {p['position_id']: p for p in jl('positions.jsonl')}
        self.ideas = {i['card_id']: i for i in jl('ideas.jsonl')}
        self.rules = {r['id']: r for r in jl('rules.jsonl')}
        self.views = collections.defaultdict(list)
        for v in jl('views.jsonl'):
            self.views[v['date']].append(v)
        self.sess = collections.defaultdict(list)
        self.periods = {}
        for s in jl('sessions.jsonl'):
            if s.get('period'):
                self.periods[s['period']] = s
            else:
                self.sess[s['date']].append(s)
        self.hind = jl('hindsight.jsonl')
        self.presets = jl('presets.jsonl') if os.path.exists(os.path.join(D, 'presets.jsonl')) else []
        opt = lambda n: jl(n) if os.path.exists(os.path.join(D, n)) else []
        self.rulings = opt('rulings.jsonl')
        self.mis = {m['id']: m for m in opt('mistakes.jsonl')}

    def rulings_for(self, rid):
        return [j for j in self.rulings if rid in (j.get('ids') or []) or j['j'] == rid]

    def mis_name(self, bid):
        m = self.mis.get(bid)
        return f"{bid} {m['name']}" if m else bid

    def rule_tag(self, rid):
        r = self.rules.get(rid)
        if not r:
            return '未归入台账'
        st = r['status'] if r.get('judged') else '长尾'
        marks = [TAG.get(l, l) for l in r.get('labels') or [] if l in TAG or l.startswith('给听众的建议')]
        if r.get('skill_exclude'):
            marks.append('不进技能')
        return f"{rid} {r['name']}〔{st}〕" + ''.join(f'〔{m}〕' for m in marks)


# 4.4 收尾给理念加的标签(ADR-0007 J6/J36/J61/J68)。「给听众的建议(…)」括号里写的是指哪部分,原样显示
TAG = {'他本人做法': '含他本人做法', '他说得多、自己做得少': '他说得多、自己做得少', '改进建议,非 Brant 原话': '含改进建议',
       'B1例外': 'B1例外'}  # 「用户裁决」太多,只在 --idea / --lesson 里展开
LABEL_NOTE = {
    '他本人做法': '陈述里有他本人的做法(自述,实盘规模无法核实),和他对听众说的规则可能不一样,陈述里分开写了',
    '他说得多、自己做得少': '他讲得多,自己很少这么做',
    '改进建议,非 Brant 原话': '陈述里有项目补的改进建议,不是他的原话,引用时照样标出',
    '用户裁决': '陈述按用户的 4.4 裁决改过,见下面的相关裁决',
    'B1例外': '涉及他给最信的票(主要是特斯拉)开的例外,统一挂 B1,例外不当通则',
}
BASIS_NOTE = {
    '原话': '条件来自他的原话',
    '原话(主观)': '分界是他当时的主观看法(如有没有方向判断、还看不看好这只票),技能改成问使用者的检查题',
    '推断': '条件是整理时推断的,他原话没明说',
    '无稳定分界': '找不到稳定分界:同一时期两种说法并存,两边原话见陈述,不编条件',
}


def rule_extra_lines(r):
    """理念的 4.4 标注:不进技能、标签、条件依据、检查题、偏差提示(同票短期改口另列)"""
    out = []
    if r.get('skill_exclude'):
        out.append(f"不进技能:{r['skill_exclude'].get('reason')}")
    for l in r.get('labels') or []:
        note = LABEL_NOTE.get(l) or ('这部分是讲给听众的,不等于他本人这么做' if l.startswith('给听众的建议') else '')
        out.append(f"标签「{l}」" + (f":{note}" if note else ''))
    cb = r.get('condition_basis')
    if cb:
        out.append(f"条件依据「{cb}」" + (f":{BASIS_NOTE[cb]}" if cb in BASIS_NOTE else ''))
    for q in r.get('user_checks') or []:
        out.append(f"检查题:{q}")
    for b in r.get('bias_notes') or []:
        out.append(f"偏差提示(按自己持仓方向解读信号):{b}")
    return out


def flip_lines(db, r, d0=None, d1=None):
    """同票/同一件事短期改口:卡片对 + 间隔;d0/d1 给了就只列两张卡至少一张落在区间里的"""
    fl = r.get('flips') or []
    dd = lambda c: (db.ideas.get(c) or {}).get('date') or (f'{c[:4]}-{c[4:6]}-{c[6:8]}' if c[:8].isdigit() else '')
    keep = [f for f in fl if not (d0 or d1) or any((not d0 or dd(c) >= d0) and (not d1 or dd(c) <= d1) for c in f[:2])]
    if not keep:
        return []
    out = [f"\n## 同票/同一件事短期改口 {len(keep)} 处" + (f"(全部 {len(fl)} 处)" if len(keep) < len(fl) else '')
           + "(J36 审计标出的两张说法相反的卡;为什么改口看原话,不替他补原因)"]
    for f in keep:
        out.append(f"- {f[2]}:")
        for c in f[:2]:
            i = db.ideas.get(c)
            if not i:
                out.append(f"  - {dd(c)}({c}):这张卡不在理念事件表里(剔除了或不是理念卡),原文看 cards/ 那张")
                continue
            other = (f"(这张归在 {i['rule_id']} {(db.rules.get(i['rule_id']) or {}).get('name', '')})"
                     if i['rule_id'] != r['id'] else '')
            q = i['quote'] or ''
            out.append(f"  - {i['date']} {i['t'] or ''}{other}:{i['rule']}  「{q[:80]}{'…' if len(q) > 80 else ''}」({c})")
    return out


SHOWN = set()  # 文字线持仓卡常被一段里的多个事件引用,全文只打一次
BRIEF = False  # --brief:每笔只留理由、2 条理念,不打当天背景
AUDIENCE = re.compile(r'会员问|观众问|粉丝问|有人问|听众|回答会员|回答观众|会员说|给会员|建议会员|你们可以|大家可以')


def card_lines(c):
    out = []
    if c['src'] == '文字线' and c['card_id'] in SHOWN:
        return [f"- **文字线持仓卡**({c['card_id']}):见上文"]
    SHOWN.add(c['card_id'])
    if c['src'] == '直播':
        act = ACT.get(c.get('action'), c.get('action'))
        opt = ''.join(f' {x}' for x in (c.get('strike'), c.get('expiry')) if x)
        px = f" @{c['price_ref']}" if c.get('price_ref') else ''
        warn = '(⚠ 讲者不确定)' if c.get('speaker_uncertain') else ''
        out.append(f"- **他当时说的理由**(直播 {c['card_id']},直播进度 {c.get('t') or '?'},{c.get('ticker')} {act}{opt}{px},"
                   f"他语气里的把握:{c.get('conviction') or '-'}){warn}:{c.get('reason') or '(卡上没记理由)'}")
        if AUDIENCE.search(c.get('reason') or ''):
            out.append('  - ⚠ 理由里像是在回答/建议听众,不一定是他自己的操作,看原话再定')
        out.append(f"  > 原话:「{c.get('quote')}」")
    elif c['src'] == '文字线':
        out.append(f"- **文字线持仓卡**({c['card_id']},这张卡汇总了 {c.get('start')} ~ {c.get('end') or '期末未平'} 整段持仓的每一步,"
                   f"不只是这一笔):{c.get('ticker')} {c.get('size') or ''}")
        if c.get('entry_reason'):
            out.append(f"  - 进场理由:{c['entry_reason']}")
        for s in c.get('steps') or []:
            out.append(f"  - {s.get('t')} {s.get('act')} @{s.get('px')}" + (f":{s['why']}" if s.get('why') else ''))
        if c.get('exit_reason'):
            out.append(f"  - 出场理由:{c['exit_reason']}")
        if c.get('outcome'):
            out.append(f"  - 结果:{c['outcome']}")
        out.append(f"  > 原话:「{c.get('quote')}」")
    else:
        out.append(f"- **喊单**({c['card_id']},美东 {c.get('t') or ''}):{(c.get('quote') or '').strip()}(喊单本身不带理由)")
    return out


def exit_hint(t):
    txt = ' '.join(c.get('reason') or '' for c in t['cards'] if c['src'] == '直播')  # 文字线卡跨整段持仓,不拿来标这一笔
    hits = [w for w in ('止盈', '止损', '到目标', '获利', '割肉', '对冲', '换仓', '换成') if w in txt]
    return f"(理由文字里出现:{'、'.join(hits)})" if hits else ''


def show_trade(db, t, names, ctx_done):
    pid = f" · 持仓段 {t['position_id']}" if t.get('position_id') else ''
    side = '做空' if t['side'] == 'short' else ''
    tool = '期权' if t['option'] else '杠杆ETF' if t['levered'] else \
        {'macro': '指数/期货/宏观品种', 'crypto': '加密货币', 'non_us': '非美股', 'basket': '一篮子'}.get(t.get('scope'), '正股')
    hint = exit_hint(t) if t['kind'] in ('reduce', 'exit') else ''
    if t['side'] == 'short' and t['option']:  # 买 put 这类:叫「开空」会误会成卖空正股
        what = '看跌期权' + KIND.get(t['kind'], t['kind'])
    elif t['side'] == 'short' and t['kind'] in KIND_SHORT:
        what = KIND_SHORT[t['kind']]
    else:
        what = side + KIND.get(t['kind'], t['kind'])
    out = [f"### {t['date']} {t.get('time') or ''} · {t['ticker']} {what}({tool}) · {t['event_id']}{pid} {hint}"]
    if t.get('caution'):
        out.append(f"- ⚠ 事件表标记:{t['caution']}(标的或价格没核实,引用时要说明)")
    for c in t['cards']:
        out += card_lines(c)
    if t['kind'] in ('reduce', 'exit'):
        out.append(c_line(db, t))
    for k in t.get('kchecks') or []:
        out.append(f"- ⚠ 再犯检测 {k['k']}({db.mis_name(k['b'])}):{k['note']}")
    sw = t.get('switch')
    if sw:
        bits = []
        if sw.get('said'):
            bits.append('他的理由里说了换仓/调仓')
        for k, lab in (('to', '同场接着买入'), ('from', '同场先卖出')):
            if sw.get(k):
                bits.append(lab + ' ' + '、'.join(f"{db.tr[e]['ticker']}{'(期权)' if db.tr[e]['option'] else ''}({e})"
                                                 for e in sw[k] if e in db.tr))
        note = '' if sw.get('said') else '(同场一卖一买、两边相关,但他没明说是换仓)'
        out.append(f"- **转仓线索**:{';'.join(bits)}{note}")
    # 同场理念:提到该标的的优先,其次按时间远近,最多 4 条
    s0 = secs(t.get('time'))
    ids = [db.ideas[i] for i in t.get('ideas', []) if i in db.ideas]
    ids.sort(key=lambda i: (not mentions((i['rule'] or '') + (i['quote'] or ''), names),
                            abs((secs(i['t']) or 0) - (s0 or 0))))
    if ids:
        out.append('- **同场 ±15 分钟讲到的理念**(时间接近不等于就是这笔的理由,要和上面的理由对照):')
        for i in ids[:2 if BRIEF else 4]:
            dtm = f"{abs((secs(i['t']) or 0) - (s0 or 0)) // 60} 分钟" if s0 is not None else ''
            gen = ' [他标的是本轮行情/个股判断]' if i.get('generality') not in (None, '通用') else ''
            out.append(f"  - {db.rule_tag(i['rule_id'])} · 相隔 {dtm}:{i['rule']}{gen}  「{i['quote']}」({i['card_id']})")
    # 当天背景:每个日期只打一次
    if t['date'] not in ctx_done and not BRIEF:
        ctx_done.add(t['date'])
        vs = db.views.get(t['date'], [])
        mine = [v for v in vs if asset_hit(v['asset'], names)][:3]
        mkt = [v for v in vs if v['asset'] in MARKET or v['kind'] == '大方向'][:3]
        for v in mine:
            out.append(f"- **当天他对 {v['asset']} 的{v['kind']}**({v['direction']}/{v['horizon']}):{v['chain']}  「{v['quote']}」")
        for v in mkt:
            out.append(f"- **当天对 {v['asset']} 的{v['kind']}**({v['direction']}/{v['horizon']}):{v['chain']}")
        for s in db.sess.get(t['date'], [])[:1]:
            out.append(f"- **当场小结**:{s.get('market_state')}({s.get('tone')})。依据:{s.get('basis')}")
    return out


def c_line(db, t):
    c = t.get('C')
    if not c:
        return '- **事后**:不在 C 检验口径内(只检验做多、美股个股/ETF、未排除的离场)'
    why = f"卖出理由粗分〔探索性〕:{c['reason']}"
    if c.get('group_of'):
        return f"- **事后**:和 {c['group_of']} 同组(同一标的 5 个交易日内的离场合并算一次,数字见那一笔);{why}"
    if c.get('holdout'):
        return f'- **事后**:留出期,不进判定;{why}'
    if 'score' not in c:
        return f"- **事后**:缺价格,没算({c.get('missing')});{why}"
    verdict = '卖后标的跑输 QQQ(按 C 口径算卖对)' if c['score'] > 0 else '卖后标的跑赢 QQQ(按 C 口径算卖早了)'
    grp = f";这一组合并了 {c['n']} 次离场" if c['n'] > 1 else ''
    return (f"- **事后(C 口径:卖后 4 周,相对 QQQ)**:标的 {c['r']:+.1%} / QQQ {c['q']:+.1%} → {verdict},差 {abs(c['score']):.1%}"
            f"{grp};{why}")


AFTER = 120  # --after:事后复盘看到区间结束后多少天
HMAX = 10    # --hmax:事后复盘最多列几条


def show_hindsight(db, names, d0, d1):
    end = (dt.date.fromisoformat(d1) + dt.timedelta(days=AFTER)).isoformat() if d1 else None
    hs = [h for h in db.hind if h['date'] and (not d0 or h['date'] >= d0) and (not end or h['date'] <= end)
          and mentions(f"{h.get('subject')} {h.get('lesson')} {h.get('quote')}", names)]
    if not hs:
        return []
    out = [f'\n## 事后他怎么说(复盘/自我修正,{d0} ~ 区间结束后 {AFTER} 天,提到该标的)']
    for h in hs[:HMAX]:
        out.append(f"- {h['date']} {h['kind']}:{h.get('subject')} → {h.get('lesson') or '(改法未说)'}  「{h.get('quote')}」({h['card_id']})")
    if len(hs) > HMAX:
        out.append(f'- ……另有 {len(hs) - HMAX} 条:加 --hmax {len(hs)} 看全,或用 --after 调整往后看的天数')
    return out


def show_positions(db, pids):
    out = []
    for pid in pids:
        p = db.pos.get(pid)
        if not p:
            continue
        end = f"{p['end']}({'明确平仓' if p['end_kind'] == 'explicit' else p['end_kind']})" if p['end'] else f"未见平仓(最后一次提到 {p['last_evidence']})"
        evs = [db.tr[e] for e in p['event_ids'] if e in db.tr]
        mix = collections.Counter('期权' if e['option'] else '杠杆ETF' if e['levered'] else
                                  {'macro': '指数/期货', 'crypto': '加密货币'}.get(e.get('scope'), '正股') for e in evs)
        out.append(f"- {pid} {p['ticker']} {'做空' if p['side'] == 'short' else '做多'}:"
                   f"{p['start']} 开仓 → {end};加仓 {p['n_adds']} 次;入场价约 {p['entry_price']};共 {len(p['event_ids'])} 个事件"
                   f"({'、'.join(f'{k}{v}' for k, v in mix.items())});事件表不记股数,「清仓」是否全部卖光要看原话")
        out += pos_checks(db, p)
    return ['\n## 涉及的持仓段'] + out if out else []


def pos_checks(db, p):
    out = []
    if p.get('sample') == '留出':
        out.append('  - 事后检验:留出期,不进判定')
    if p.get('B'):
        b = p['B']
        out.append(f"  - 入场后 12 周(B 口径):标的 {b['r']:+.1%} / QQQ {b['q']:+.1%} / 超额 {b['excess']:+.1%}")
    if p.get('D'):
        d = p['D']
        line = '杠杆 ETF −25%' if d.get('levered') else '正股 −15%'
        rec = f"已回本(用 {d['days_to_recover']} 天)" if d.get('recovered') else '没回本'
        diff = f"继续拿比当天止损 {d['diff']:+.1%}" if d.get('diff') is not None else '继续拿的结果未知(数据不全)'
        dd = f",最大浮亏 {d['max_dd']:.1%}" if d.get('max_dd') is not None else ''
        out.append(f"  - D 口径:{d['trigger']} 跌破止损线({line}),之后{diff}{dd},{rec}")
    for k in p.get('kchecks') or []:
        out.append(f"  - 再犯检测 {k['k']}({db.mis_name(k['b'])}):{k['note']}")
    sz = p.get('size')
    if sz and (sz['label'] != '未说' or sz.get('usd')):
        out.append(f"  - 仓位粗分〔探索性〕:{sz['label']}" + (f",喊单金额约 ${sz['usd']:,}(展示账户,只作相对参考)" if sz.get('usd') else ''))
    return out


def by_ticker(db, a):
    q = CN.get(a.ticker, a.ticker.upper())
    names = names_of(q)
    d0, d1 = day(a.frm), day(a.to, end=True)
    ks = KINDSET[a.kind]
    ts = [t for t in db.trades if (t['ticker'] == q or t['underlying'] == q) and t['kind'] in ks
          and (not d0 or t['date'] >= d0) and (not d1 or t['date'] <= d1)
          and (a.kind != 'switch' or t.get('switch'))]
    head = [f"# {q} 的操作:{d0 or '最早'} ~ {d1 or '最新'}({a.kind}),共 {len(ts)} 个事件"]
    if not ts:
        return head + ['没有记录。可以放宽时间、换 --kind all,或确认代码(杠杆ETF 按底层标的归并,如 TSLL 归 TSLA)。']
    if len(ts) > a.max:
        cnt = collections.Counter((t['date'][:7], KIND.get(t['kind'])) for t in ts)
        head.append(f"事件太多,只展示最早的 {a.max} 个。按月分布:" +
                    ';'.join(f"{m} {k}×{n}" for (m, k), n in sorted(cnt.items())))
        ts = ts[:a.max]
    out, ctx = head, set()
    for t in ts:
        out += [''] + show_trade(db, t, names, ctx)
    out += show_positions(db, sorted({t['position_id'] for t in ts if t.get('position_id')}))
    out += show_hindsight(db, names, d0 or ts[0]['date'], d1 or ts[-1]['date'])
    return out


def by_position(db, pid):
    p = db.pos.get(pid)
    if not p:
        return [f'没有持仓段 {pid}']
    names = names_of(p['underlying']) | names_of(p['ticker'])
    out, ctx = [f"# 持仓段 {pid}"] + show_positions(db, [pid])[1:], set()
    for e in p['event_ids']:
        if e in db.tr:
            out += [''] + show_trade(db, db.tr[e], names, ctx)
    out += show_hindsight(db, names, p['start'], p['end'] or p['last_evidence'])
    return out


def by_event(db, eid):
    t = db.tr.get(eid)
    if not t:
        return [f'没有事件 {eid}(或该事件因重复场次/讲者排除/转述被剔除)']
    names = names_of(t['underlying']) | names_of(t['ticker'])
    return show_trade(db, t, names, set()) + show_positions(db, [t['position_id']] if t.get('position_id') else [])


def by_idea(db, a):
    rid = a.idea.upper()
    r = db.rules.get(rid)
    d0, d1 = day(a.frm), day(a.to, end=True)
    out = [f"# 理念 {db.rule_tag(rid)}:{d0 or '最早'} ~ {d1 or '最新'}"]
    if r:
        out.append(f"台账陈述:{r['statement']}")
        if r.get('status_note'):
            out.append(f"有效期说明:{r['status_note']}")
        if r.get('old') or r.get('new'):
            out.append(f"旧版:{r.get('old')}\n新版:{r.get('new')}")
        out += rule_extra_lines(r)
        out += grade_lines(db, r)
        out += flip_lines(db, r, d0, d1)
    flipped = {c for f in (r or {}).get('flips') or [] for c in f[:2]}
    xs = sorted((i for i in db.ideas.values() if i['rule_id'] == rid and i['date']
                 and (not d0 or i['date'] >= d0) and (not d1 or i['date'] <= d1)), key=lambda i: (i['date'], i['t'] or ''))
    out.append(f"\n## 这段时间他讲这条理念 {len(xs)} 次" + (f"(只列 {a.max} 次)" if len(xs) > a.max else '')
               + ('(标 ↔改口 的是上面短期改口里的卡)' if flipped & {i['card_id'] for i in xs[:a.max]} else ''))
    for i in xs[:a.max]:
        ev = [db.tr[e] for e in i['events'] if e in db.tr and db.tr[e]['kind'] in ('open', 'reduce', 'exit', 'other')]
        evs = ';同场 ±15 分钟的操作:' + '、'.join(f"{e['ticker']} {KIND[e['kind']]}({e['event_id']})" for e in ev) if ev else ''
        gen = ' [本轮行情/个股判断]' if i.get('generality') not in (None, '通用') else ''
        fm = ' ↔改口' if i['card_id'] in flipped else ''
        out.append(f"- {i['date']} {i['t'] or ''}{fm}:{i['rule']}{gen}  「{i['quote']}」({i['card_id']}){evs}")
    return out


def grade_lines(db, r):
    out = []
    if r.get('grade_v2'):
        out.append(f"证据等级:修订版 {r['grade_v2']}(原版 {r.get('grade')});言行一致约 {r.get('consistent_est')} 次,"
                   f"言行相反约 {r.get('contrary_v2')} 次(其中他自己检讨违反它 {r.get('violates_sc')} 次)")
        if r.get('grade_note'):
            out.append(f"  - C 级说明:{r['grade_note']}。C 级不等于规则错。")
    for t in r.get('tests') or []:
        ci = f" [{t['ci'][0]:+.1%}, {t['ci'][1]:+.1%}]" if t.get('ci') else ''
        mc = (f"遵守 {t['mean_comply']:+.1%}(n={t['n_comply']})vs 违反 {t['mean_violate']:+.1%}(n={t['n_violate']}),"
              if t.get('mean_comply') is not None and t.get('mean_violate') is not None else '')
        ph = f",Holm p={t['p_holm']:.2f}" if t.get('p_holm') is not None else ''
        out.append(f"单条回测 {t['t']}:{mc}差 {t['stat']:+.1%}{ci}{ph} → {t['verdict']}" + (f"({t['note']})" if t.get('note') else ''))
    for j in db.rulings_for(r['id']):
        out.append(f"相关裁决 {j['j']} {j['title']}:{j['conclusion']}(全文:--lesson {j['j']})")
    return out


def fmt_k(k, sm):
    if not sm:
        return ''
    if k == 'K3':
        d = sm['D 主检验']
        return (f"D 主检验:跌破止损线后继续拿平均比当天止损 {d['value']:+.1%} [{d['ci'][0]:+.1%}, {d['ci'][1]:+.1%}],"
                f"n={d['n']}({d['n_tickers']} 个标的,另有 {d.get('n_unknown')} 次结果未知)→ {d['verdict']}")
    bits = []
    for key in ('n', 'denominator', 'share', 'last', 'mean_excess', 'verdict', 'turned_loss', 'n_tp_labeled', 'n_loss'):
        if sm.get(key) is not None:
            v = sm[key]
            bits.append(f"{key}={v:.1%}" if key in ('share', 'mean_excess') else f"{key}={v}")
    for key in ('cost', 'giveback', 'instr_ret', 'cost_excess12w'):
        c = sm.get(key)
        if isinstance(c, dict) and c.get('mean') is not None:
            bits.append(f"{key} 均值 {c['mean']:+.1%}" + (f" [{c['ci'][0]:+.1%}, {c['ci'][1]:+.1%}]" if c.get('ci') else ''))
    if isinstance(sm.get('calls_era'), dict):
        ce = sm['calls_era']
        bits.append(f"2023-10 起主口径:{ce.get('n')}/{ce.get('n_positions')} 段,工具收益均值 {ce.get('instr_ret_mean', 0):+.1%}")
    return ';'.join(bits)


def by_lesson(db, arg):
    x = arg.upper()
    out = [f'# {x} 的事后检验与项目裁决', '(对过去模式的事后评估和修正,不是现在的买卖建议;裁决里标「改进建议,非 Brant 原话」的照样标出)']
    js = db.rulings_for(x)
    bids = [x] if x in db.mis else []
    if x.startswith('J'):
        bids = [i for j in js for i in j.get('ids') or [] if i in db.mis]
    # 台账里 B 族多是失误的同号占位(没有陈述);B1 在 4.4 J36③ 成了「给最信的票开例外」的汇总理念,有陈述就显示
    rids = [x] if x in db.rules and db.rules[x].get('statement') else []
    if x.startswith('J'):
        rids = [i for j in js for i in j.get('ids') or [] if i in db.rules and db.rules[i].get('statement')]
    if not (js or bids or rids):
        return out + [f'没有 {x} 的记录。失误类型是 B1–B35,裁决是 J1 起,理念是台账编号(如 P7、X3)。']
    for j in js:
        out += [f"\n## 裁决 {j['j']} {j['title']}({j.get('date')})", f"- 相关编号:{'、'.join(j.get('ids') or [])}",
                f"- 结论:{j['conclusion']}", f"- 数据:{j.get('data')}",
                f"- 修正版全文:失误与修正版(`--ref corrections`)「{j.get('corrections')}」节;决策记录 {j.get('adr')}"]
    for b in dict.fromkeys(bids):
        m = db.mis[b]
        out += [f"\n## 失误类型 {b} {m['name']}", f"- 定义:{m['pattern']}",
                f"- 他自己说了 {m.get('repeat_said')} 次 / 聚类卡 {m.get('n')} 张,{m.get('first')} ~ {m.get('last')};违反的理念:{'、'.join(m.get('violates') or []) or '-'}"]
        if m.get('his_fix'):
            out.append(f"- 他自己的改法:{m['his_fix']}  「{m.get('his_fix_quote') or ''}」({m.get('his_fix_card')})")
        else:
            out.append('- 他自己的改法:没说')
        if m.get('k'):
            out.append(f"- 再犯检测 {m['k']}:{fmt_k(m['k'], m.get('k_summary'))}")
        elif m.get('detectable'):
            out.append(f"- 再犯检测:{m['detectable'][:120]}")
        if m.get('example_ids'):
            out.append(f"- 例子:{'、'.join(m['example_ids'][:3])}")
    for rid in dict.fromkeys(rids):
        r = db.rules[rid]
        out += ([f"\n## 理念 {db.rule_tag(rid)}", f"- 台账陈述:{r['statement']}"] + ['- ' + l for l in rule_extra_lines(r)]
                + ['- ' + l for l in grade_lines(db, r) if not l.startswith('相关裁决')])
        if r.get('flips'):
            out.append(f"- 同票/同一件事短期改口 {len(r['flips'])} 处,时间线和原话见 --idea {rid}")
        vio = [m for m in db.mis.values() if rid in (m.get('violates') or [])]
        if vio:
            out.append('- 违反这条理念的失误类型:' + '、'.join(f"{m['id']} {m['name']}" for m in vio))
    return out


def by_date(db, d):
    out = [f'# {d}']
    for s in db.sess.get(d, []):
        out.append(f"小结:{s.get('market_state')}({s.get('tone')});依据:{s.get('basis')};值得注意:{s.get('notable')}")
    day_ts = [t for t in db.trades if t['date'] == d]
    ts = [t for t in day_ts if t['kind'] in KINDSET['trade']]
    rest = [t for t in day_ts if t['kind'] not in KINDSET['trade']]
    out.append(f'\n## 买卖 {len(ts)} 个' + (f'(另有持有/观望/不买 {len(rest)} 个,见下)' if rest else ''))
    ctx = {d}
    for t in ts:
        out += [''] + show_trade(db, t, names_of(t['underlying']) | names_of(t['ticker']), ctx)
    if rest:
        out.append(f'\n## 持有 / 观望 / 不买 {len(rest)} 个(要细节用 --event 编号)')
        for t in rest:
            c = next((c for c in t['cards'] if c['src'] == '直播'), t['cards'][0] if t['cards'] else {})
            out.append(f"- {t['ticker']} {KIND.get(t['kind'], t['kind'])} · {t['event_id']} · {c.get('t') or ''}:"
                       f"{c.get('reason') or '(卡上没记理由)'}  「{c.get('quote') or ''}」")
    vs = db.views.get(d, [])
    if vs:
        out.append(f'\n## 当天观点 {len(vs)} 条')
        out += [f"- {v['asset']} {v['kind']}({v['direction']}/{v['horizon']}):{v['chain']}" for v in vs[:15]]
    ids = [i for i in db.ideas.values() if i['date'] == d]
    cnt = collections.Counter(i['rule_id'] for i in ids if i['rule_id'])
    if cnt:
        out.append(f'\n## 当天讲到的理念(按次数)')
        out += [f"- {db.rule_tag(r)} ×{n}" for r, n in cnt.most_common(12)]
    new = [i for i in ids if not i['rule_id']]
    if new:
        out.append(f'\n## 当天讲到、台账里还没有的理念 {len(new)} 条')
        for i in sorted(new, key=lambda i: i['t'] or '')[:20]:
            gen = ' [本轮行情/个股判断]' if i.get('generality') not in (None, '通用') else ''
            chk = '(⚠ 还没做忠实度复核)' if i.get('fresh') and not i.get('checked') else ''
            out.append(f"- {i['t'] or ''}:{i['rule']}{gen}{chk}  「{i['quote']}」({i['card_id']})")
    if any(i.get('fresh') and not i.get('checked') for i in ids):
        out.append('\n⚠ 这一天的理念卡还没做忠实度复核,引用时以原话为准。')
    return out


DONE = {'已触发-照做', '已触发-没做', '改口', '作废', '过期'}


def age_note(d):
    """数据不会自己更新:最后一天距今超过 3 天就提醒(d 形如 2026-11-11 或 20261111)"""
    try:
        d = d if '-' in d else f'{d[:4]}-{d[4:6]}-{d[6:8]}'
        n = (dt.date.today() - dt.date.fromisoformat(d)).days
    except (ValueError, TypeError):
        return ''
    return f'⚠ 数据截至 {d},距今 {n} 天;之后的直播和操作这里没有,技能不会自己更新。' if n > 3 else ''


def by_daily(arg):
    dd = os.path.join(D, 'daily')
    fs = sorted(f for f in os.listdir(dd) if f.endswith('.md')) if os.path.isdir(dd) else []
    if not fs:
        return ['还没有每日总结。']
    if arg == 'list':
        return [f'# 每日总结 {len(fs)} 篇'] + [f'- {f[:4]}-{f[4:6]}-{f[6:8]}  {f[:-3]}' for f in fs]
    if arg == 'latest':
        fs = [f for f in fs if f[:8] == fs[-1][:8]]
    else:
        key = day(arg).replace('-', '')
        fs = [f for f in fs if f.startswith(key)]
        if not fs:
            return [f'{arg} 没有每日总结(可能那天没直播、回放还没转存,或还没跑每日更新)。用 --daily list 看有哪些。']
    out = []
    for f in fs:  # 同一天可能有两场
        with open(os.path.join(dd, f), encoding='utf-8') as fh:
            out.append(fh.read().rstrip())
    note = age_note(fs[-1][:8]) if arg == 'latest' else ''
    return ([note, ''] if note else []) + ['\n\n---\n\n'.join(out)]


def by_presets(db, arg):
    show_all = arg == 'all'
    q = None if arg in ('open', 'all') else CN.get(arg, arg.upper())

    def toks(p):  # 「SOXS/UVXY」「GLD/黄金」按单个代码匹配
        return {CN.get(t.strip(), t.strip().upper()) for t in (p.get('ticker') or 'UNKNOWN').split('/')}
    ps = [p for p in db.presets if (show_all or p.get('status') not in DONE) and (not q or q in toks(p))]
    ps.sort(key=lambda p: ((p.get('ticker') or 'UNKNOWN').split('/')[0], p.get('first') or '', p['preset_id']))  # 同一标的排在一起
    head = f"# 预设与认错条件:{'全部' if show_all else '还没了结的'}{(' · ' + q) if q else ''},共 {len(ps)} 条"
    if not ps:
        return [head, '没有记录。']
    out = [head, '(来自每日总结的登记;「待触发」= 他说过、之后的直播里还没见到了结。是否真到价以行情为准)']
    last = max((p.get('date') or p.get('first') or '' for p in db.presets), default='')
    if age_note(last):
        out.append(age_note(last))
    for p in ps:
        out.append(f"- **{p['preset_id']}** {p.get('first')} {p.get('ticker')} · {p.get('kind')}:{p.get('condition')} → {p.get('action')}"
                   f" 〔{p.get('status')}〕  「{p.get('quote')}」({p.get('card_id') or p.get('stem')})")
        for h in p.get('history', [])[1:]:
            out.append(f"  - {h['date']} 〔{h['status']}〕{h.get('note') or ''}" + (f"  「{h['quote']}」" if h.get('quote') else ''))
    return out


# ---- 原文搜索:直播逐字稿 + 文字线。不在打包数据里,直接读 brant-lens 项目的原文 ----
TS = re.compile(r'^\[(\d+:\d+:\d+)\]\s*')
TL = re.compile(r'^\[(\d{4}-\d{2}-\d{2}) (\d{2}:\d{2})\]\s*')


def project_root():
    """brant-lens 项目目录:环境变量 BRANT_LENS 优先;否则从脚本真实路径往上三层(技能目录可能是指向项目的链接)"""
    return os.environ.get('BRANT_LENS') or os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.dirname(os.path.realpath(__file__)))))


def raw_dirs():
    """原文在哪 → (逐字稿目录, 文字线目录, 讲者排除表)。技能自带的(data/transcripts、data/corpus,发行包)优先,
    否则读 brant-lens 项目里的"""
    if os.path.isdir(os.path.join(D, 'transcripts')):
        return os.path.join(D, 'transcripts'), os.path.join(D, 'corpus'), os.path.join(D, 'speaker_exclusions.jsonl')
    root = project_root()
    return os.path.join(root, 'transcripts'), os.path.join(root, 'corpus'), os.path.join(root, 'data', 'speaker_exclusions.jsonl')


def clip(s, m, before=70, after=110):
    """逐字稿有的一行就是一大段,只留命中附近"""
    a, b = max(0, m.start() - before), min(len(s), m.end() + after)
    return ('…' if a else '') + s[a:b] + ('…' if b < len(s) else '')


ALIASES = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'aliases.json')


def expand(pattern):
    """关键词(按 | 拆开)里有对照表某组的写法,就把同组的错字写法都带上 → (新正则, 用到的组名)"""
    try:
        with open(ALIASES, encoding='utf-8') as f:
            groups = json.load(f)['groups']
    except (OSError, ValueError, KeyError):
        return pattern, []
    toks = [t for t in pattern.split('|') if t]
    have, used = {t.lower() for t in toks}, []
    for g in groups:
        ws = g.get('words', [])
        if have & {w.lower() for w in ws}:
            for w in ws:
                if w.lower() not in have:
                    toks.append(re.escape(w))
                    have.add(w.lower())
            used.append(g['name'])
    return '|'.join(toks), used


def by_grep(a):
    tdir, cdir, excl_path = raw_dirs()
    if not os.path.isdir(tdir):
        return ['# 原文搜索', f'找不到逐字稿目录 {tdir}。原文搜索读的是技能目录里的 data/transcripts、data/corpus(发行包自带),'
                '或 brant-lens 项目里的 transcripts/ 和 corpus/;项目不在默认位置时设环境变量 BRANT_LENS=项目路径。']
    query, used = (a.grep, []) if a.exact else expand(a.grep)
    try:
        pat = re.compile(query, re.I)
        tokpats = [(t.replace('\\', ''), re.compile(t, re.I)) for t in query.split('|') if t] if '|' in query else []
    except re.error as e:
        return [f'关键词不是合法的正则({e})。几种写法用 | 连,如:老王|王老师|沃尔老师']
    vcnt = collections.Counter()  # 各写法命中行数,用来维护对照表
    lo, hi = day(a.frm), day(a.to, end=True)
    inside = lambda d: (not lo or d >= lo) and (not hi or d <= hi)
    excl = collections.defaultdict(list)  # 代班/别的老师讲话段
    p = excl_path
    if os.path.exists(p):
        for e in (json.loads(l) for l in open(p, encoding='utf-8') if l.strip()):
            excl[e['stem']].append((secs(e['from']), secs(e['to']), e.get('who') or '别的老师'))

    talk = []  # (日期, 场次, [显示行])
    if a.src in ('all', 'talk'):
        for fn in sorted(os.listdir(tdir)):
            if not fn.endswith('.host.txt'):
                continue
            stem = fn[:-len('.host.txt')]
            d = f'{stem[:4]}-{stem[4:6]}-{stem[6:8]}'
            if not inside(d):
                continue
            lines = open(os.path.join(tdir, fn), encoding='utf-8').read().splitlines()
            shown = -1
            for i, ln in enumerate(lines):
                if not pat.search(ln):
                    continue
                for w, tp in tokpats:
                    vcnt[w] += bool(tp.search(ln))
                if i <= shown:
                    continue
                j = i  # 后面的命中和这一处的上下文挨着或重叠,就并成一块
                while True:
                    nxt = next((k for k in range(j + 1, min(len(lines), j + 2 * a.ctx + 2)) if pat.search(lines[k])), None)
                    if nxt is None:
                        break
                    j = nxt
                block = []
                for k in range(max(0, i - a.ctx), min(len(lines), j + a.ctx + 1)):
                    t = TS.match(lines[k])
                    tt, body = (t[1], lines[k][t.end():]) if t else ('', lines[k])
                    m = pat.search(body)
                    if m:
                        txt = clip(body, m)
                        s = secs(tt)
                        who = next((w for f0, t0, w in excl.get(stem, []) if s is not None and f0 <= s <= t0), None)
                        block.append(f'▶ {tt} {txt}' + (f'  ⚠ 这段是{who}在讲,不是 Brant' if who else ''))
                    else:
                        block.append(f'  {tt} {body[:60]}{"…" if len(body) > 60 else ""}')
                shown = j + a.ctx
                talk.append((d, stem, block))
    text = []  # (日期, 显示行)
    if a.src in ('all', 'text') and os.path.isdir(cdir):
        for fn in sorted(os.listdir(cdir)):
            if not fn.endswith('.txt'):
                continue
            for ln in open(os.path.join(cdir, fn), encoding='utf-8'):
                t = TL.match(ln)
                if not t or not inside(t[1]):
                    continue
                body = ln[t.end():].rstrip()  # 「喊单: …」「聊天: …」
                m = pat.search(body)
                if m:
                    for w, tp in tokpats:
                        vcnt[w] += bool(tp.search(body))
                    text.append((t[1], f'- {t[1]} {t[2]} {clip(body, m)}'))

    rng = f"{lo or '最早'} 至 {hi or '最新'}"
    out = [f'# 原文搜索「{a.grep}」({rng}):直播 {len({s for _, s, _ in talk})} 场 {len(talk)} 处 · 文字线 {len(text)} 条',
           '(这是没经过抽卡核对的原始转写:人名和代码常被听错,对照表 aliases.json 里有的会自动带上,没有的自己多试几种写法用 | 连;'
           '逐字稿只录他的声音,但他常把观众留言念出来,引用前看上下文,分清是他说的还是他念的;直播时间是进度(开播后多久),文字线是美东时间)']
    if used:
        out.append(f"自动带上了对照表里的错字写法({'、'.join(used)});只搜原词加 --exact")
    if tokpats:
        out.append('各写法命中行数:' + ' · '.join(f'{w} {vcnt[w]}' for w, _ in sorted(tokpats, key=lambda x: -vcnt[x[0]]))
                   + '(0 次的可能是没用的写法;发现新写法确认后补进 aliases.json)')
    if not talk and not text:
        return out + ['没有命中。换个写法、放宽时间,或用 --src text / talk 单看一边。']
    span = {d[:7] for d, _, _ in talk} | {d[:7] for d, _ in text}
    unit = 7 if len(span) <= 24 else 4  # 跨度大按年,小按月
    cnt = collections.Counter(d[:unit] for d, _, _ in talk) + collections.Counter(d[:unit] for d, _ in text)
    out.append(('按月' if unit == 7 else '按年') + '分布:' + ';'.join(f'{k}×{n}' for k, n in sorted(cnt.items())))
    if talk:
        out += ['', '## 直播逐字稿']
        if len(talk) > a.max:
            out.append(f'(共 {len(talk)} 处,只列最早的 {a.max} 处;用 --from/--to 缩小范围,或 --max 调大)')
        last = None
        for d, stem, block in talk[:a.max]:
            if stem != last:
                out.append(f'### {d} 直播 {stem}')
                last = stem
            out += block + ['']
    if text:
        out += ['## 文字线(喊单/聊天,美东时间)']
        if len(text) > a.max:
            out.append(f'(共 {len(text)} 条,只列最早的 {a.max} 条)')
        out += [s for _, s in text[:a.max]]
    return out


def main():
    sys.stdout.reconfigure(encoding='utf-8')  # Windows 控制台默认 GBK,中文帮助和输出都会乱码
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('ticker', nargs='?')
    ap.add_argument('--from', dest='frm')
    ap.add_argument('--to')
    ap.add_argument('--kind', default='trade', choices=sorted(KINDSET))
    ap.add_argument('--max', type=int, default=25)
    ap.add_argument('--position')
    ap.add_argument('--event')
    ap.add_argument('--idea')
    ap.add_argument('--date')
    ap.add_argument('--daily', nargs='?', const='latest', help='每日直播总结:不带值=最新一场;日期;list')
    ap.add_argument('--presets', nargs='?', const='open', help='预设点位/认错条件:不带值=未了结;标的;all')
    ap.add_argument('--lesson', help='失误类型/裁决/理念的事后检验与项目裁决,如 B5、J2、S13')
    ap.add_argument('--brief', action='store_true', help='精简:每笔只留理由和 2 条理念,不打当天背景')
    ap.add_argument('--after', type=int, default=120, help='事后复盘看到区间结束后多少天(默认 120)')
    ap.add_argument('--hmax', type=int, default=10, help='事后复盘最多列几条(默认 10)')
    ap.add_argument('--grep', help='原文搜索:在全部直播逐字稿和文字线里找关键词(正则,几种写法用 | 连)')
    ap.add_argument('--src', default='all', choices=['all', 'talk', 'text'], help='--grep 搜哪边:all/talk 直播/text 文字线')
    ap.add_argument('--ctx', type=int, default=1, help='--grep 每处命中前后各带几行(默认 1)')
    ap.add_argument('--exact', action='store_true', help='--grep 只搜输入的词,不自动带上 aliases.json 里的错字写法')
    ap.add_argument('--intro', action='store_true', help='这个技能能做什么:功能介绍、数据范围、从哪开始')
    ap.add_argument('--scorecard', nargs='?', const='all', help='分类成绩单:不带值=全部;总表/选股/离场/硬扛/大方向/期货/言行')
    ap.add_argument('--dossier', help='个股档案:一只票的看法演变、持仓段结果、复盘、未了结预设')
    ap.add_argument('--open', dest='open_', nargs='?', const='recent', help='数据里还没见平仓的持仓段:不带值=最近 180 天提到过的;all=全部')
    ap.add_argument('--flag', help='更正入口:编号(事件 E…/持仓段 P…/卡片出处/理念编号/标的/总体),配 --note;list=看已记的')
    ap.add_argument('--note', help='--flag 的更正内容')
    ap.add_argument('--tag', help='--flag 的类别:更正(默认)/事后补充/确认无误/其他')
    ap.add_argument('--unverified', nargs='?', const='summary', choices=['summary', 'ticker', 'reason'],
                    help='只有本人能核实的条目:不带值=汇总;ticker=标的/讲者没核实的事件;reason=没有买入理由分类的持仓段')
    ap.add_argument('--sql', help='自由统计:只读 select 查询;schema=看有哪些表和列')
    ap.add_argument('--ref', nargs='?', const='list', help='参考资料:不带值=列表;overview/known-issues/track-record/corrections/…')
    ap.add_argument('--check-essay', dest='check_essay', help='核对一篇文章:每句「原话」都在所标场次的原文里、每个 [[出处]] 都存在;「问题 0」才算通过')
    ap.add_argument('--topic', help='按关键词找理念:不知道理念编号时用(正则,几种说法用 | 连,如 "杠杆|融资")')
    a = ap.parse_args()
    if a.grep:  # 原文搜索不用加载打包数据
        print('\n'.join(by_grep(a)))
        return
    global BRIEF, AFTER, HMAX
    BRIEF, AFTER, HMAX = a.brief, a.after, a.hmax
    more = None
    if a.intro or a.scorecard or a.dossier or a.open_ or a.flag or a.unverified or a.sql or a.ref or a.check_essay or a.topic:
        import why_more as more  # 扩展查法放在同目录的 why_more.py
        more.W = sys.modules[__name__]
        if a.sql or a.ref:  # 这两种不用加载打包数据
            print('\n'.join(more.sql(a) if a.sql else more.ref(a)))
            return
    db = DB()
    if more:
        out = (more.intro(db) if a.intro else more.scorecard(db, a.scorecard) if a.scorecard
               else more.dossier(db, a) if a.dossier else more.open_positions(db, a) if a.open_
               else more.flag(db, a) if a.flag else more.check_essay(db, a) if a.check_essay
               else more.topic(db, a) if a.topic else more.unverified(db, a))
    elif a.position:
        out = by_position(db, a.position.upper())
    elif a.event:
        out = by_event(db, a.event.upper())
    elif a.idea:
        out = by_idea(db, a)
    elif a.date:
        out = by_date(db, day(a.date))
    elif a.daily:
        out = by_daily(a.daily)
    elif a.presets:
        out = by_presets(db, a.presets)
    elif a.lesson:
        out = by_lesson(db, a.lesson)
    elif a.ticker:
        out = by_ticker(db, a)
    else:
        ap.print_help()
        return
    print('\n'.join(out))


if __name__ == '__main__':
    main()
