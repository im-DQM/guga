#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""候选池维护：晚报列过的候选项，主人没批准就删掉，绝不留到下一批。

规则（主人 2026-10-19 定）：只要没批准（含点了「今晚先不做」），那条建议就删掉，
下一次晚报换一批全新的给他看。

子命令：
  list                      列出池中待批候选（带序号）
  prune [--today YYYY-MM-DD] [--dry-run]
                            删掉「提出日期早于今天」或没日期的待批候选，归档到 idea-history.md
  approve <序号|关键词>      主人点头：从池里删掉，写进 night-approved.md
  drop <序号|关键词|--all>   主人不做：从池里删掉，归档到 idea-history.md

候选行格式（01:00 夜间调研写入）：- [ ] <YYYY-MM-DD> · <一句话>（来源：<工具> <链接>）
"""
import re
import sys
import fcntl
import datetime
import pathlib

IDEAS = pathlib.Path('/home/ubuntu/.hermes/ideas.md')
APPROVED = pathlib.Path('/home/ubuntu/.hermes/night-approved.md')
HIST = pathlib.Path('/home/ubuntu/.hermes/knowledge/idea-history.md')
SECTION = '## 可做的小工程（候选池）'
ROW = re.compile(r'^- \[ \]\s*(?:(\d{4}-\d{2}-\d{2})\s*[·・|]\s*)?(.+)$')
PLACEHOLDER = '（当前无待做项。）'


def load():
    lines = IDEAS.read_text(encoding='utf-8').split('\n')
    try:
        start = next(i for i, l in enumerate(lines) if l.strip() == SECTION)
    except StopIteration:
        sys.exit('找不到候选池小节')
    end = len(lines)
    for i in range(start + 1, len(lines)):
        if lines[i].startswith('## '):
            end = i
            break
    return lines, start, end


def candidates(lines, start, end):
    out = []
    for i in range(start + 1, end):
        m = ROW.match(lines[i].strip())
        if m:
            out.append((i, m.group(1), m.group(2).strip()))
    return out


def archive(kind, date, text):
    HIST.parent.mkdir(parents=True, exist_ok=True)
    if not HIST.exists():
        HIST.write_text('# 候选历史（去重依据，不展示给主人）\n\n'
                        '规则：提过但没被批准的候选也记在这里，夜间调研据此避免重复提同一个东西。\n\n',
                        encoding='utf-8')
    with HIST.open('a', encoding='utf-8') as f:
        f.write(f'- {date}｜{kind}｜{text}\n')


def pick(target, lines, start, end):
    """按序号或关键词选中一条候选。"""
    cands = candidates(lines, start, end)
    if not cands:
        sys.exit('候选池是空的')
    if target.isdigit():
        n = int(target)
        if not 1 <= n <= len(cands):
            sys.exit(f'序号超范围（1..{len(cands)}）')
        return cands[n - 1]
    hits = [c for c in cands if target in c[2]]
    if not hits:
        sys.exit('没有匹配的候选')
    if len(hits) > 1:
        sys.exit('匹配到多条，请用序号：\n' + '\n'.join(f'{k+1}. {c[2]}' for k, c in enumerate(cands) if c in hits))
    return hits[0]


def write_ideas(lines):
    IDEAS.write_text('\n'.join(lines), encoding='utf-8')


def cmd_list():
    lines, s, e = load()
    cands = candidates(lines, s, e)
    if not cands:
        print('（候选池空的）')
        return
    for k, (_, d, t) in enumerate(cands, 1):
        print(f'{k}. [{d or "无日期"}] {t}')


def cmd_prune(today, dry=False):
    lines, s, e = load()
    removed, kept = [], []
    for i in range(s + 1, e):
        m = ROW.match(lines[i].strip())
        if m:
            d = m.group(1)
            if d is None or d < today:
                removed.append((d or '无日期', m.group(2).strip()))
                continue
        kept.append(lines[i])
    if not removed:
        print('没有过期候选')
        return
    for d, t in removed:
        print(('· ' if dry else '删 ') + f'[{d}] {t}')
    if dry:
        return
    write_ideas(lines[:s + 1] + kept + lines[e:])
    for d, t in removed:
        archive('未批删除', d, t)


def cmd_approve(target):
    lines, s, e = load()
    idx, d, text = pick(target, lines, s, e)
    write_ideas(lines[:idx] + lines[idx + 1:])
    body = APPROVED.read_text(encoding='utf-8') if APPROVED.exists() else ''
    body = '\n'.join(l for l in body.split('\n') if l.strip() != PLACEHOLDER).rstrip('\n')
    if not body:
        body = '# 夜间小工程 · 批准清单\n\n规则：只有主人**明确点头**的项才写进这里；每晚 02:00 的任务只做本清单里 `- [ ]` 的项，做完勾成 `- [x]`。\n本清单为空（或没有 `- [ ]`）时，夜间什么都不做。'
    APPROVED.write_text(body + f'\n- [ ] {text}\n', encoding='utf-8')
    archive('批准', d or datetime.date.today().isoformat(), text)
    print(f'已批准：{text}')


def cmd_drop(target):
    lines, s, e = load()
    if target == '--all':
        cands = candidates(lines, s, e)
        if not cands:
            print('候选池是空的')
            return
        keep_idx = {c[0] for c in cands}
        write_ideas([l for i, l in enumerate(lines) if i not in keep_idx])
        for _, d, t in cands:
            archive('未批删除', d or datetime.date.today().isoformat(), t)
            print(f'删：{t}')
        return
    idx, d, text = pick(target, lines, s, e)
    write_ideas(lines[:idx] + lines[idx + 1:])
    archive('未批删除', d or datetime.date.today().isoformat(), text)
    print(f'删：{text}')


def main(argv):
    if not argv or argv[0] in ('-h', '--help'):
        print(__doc__)
        return
    cmd = argv[0]
    IDEAS.parent.joinpath('.idea-pool.lock').touch()
    with open(IDEAS.parent / '.idea-pool.lock', 'w') as lk:
        fcntl.flock(lk, fcntl.LOCK_EX)
        if cmd == 'list':
            cmd_list()
        elif cmd == 'prune':
            today = datetime.date.today().isoformat()
            if '--today' in argv:
                today = argv[argv.index('--today') + 1]
            cmd_prune(today, dry='--dry-run' in argv)
        elif cmd == 'approve':
            if len(argv) < 2:
                sys.exit('用法：idea_pool.py approve <序号|关键词>')
            cmd_approve(argv[1])
        elif cmd == 'drop':
            if len(argv) < 2:
                sys.exit('用法：idea_pool.py drop <序号|关键词|--all>')
            cmd_drop(argv[1])
        else:
            sys.exit(f'未知子命令：{cmd}')


if __name__ == '__main__':
    main(sys.argv[1:])
