# 项目：夜间自动化（三件事）

全部 `deliver=local` → 落收件箱，主人打开界面时领取。

| 作业 | 时间 | 干什么 |
| --- | --- | --- |
| `night-scan` | 01:00 | 上网找候选（广泛参考被认可的 agent 小工具与产品做法）→ 写入想法池 |
| `night-project` | 02:00 | **只做 `~/.hermes/night-approved.md` 里 `- [ ]` 的批准项** → 产出 `hub/preview-*.html` + 报告 |
| `night-watch` | 03:00 | 只读自检 + 清 7 天前的旧备份 |

## 想法池与批准清单

- 想法池 `~/.hermes/ideas.md`（候选 = 「## 可做的小工程（候选池）」节里的 `- [ ]` 行，行首带提出日期 `- [ ] YYYY-MM-DD · <内容>`；**候选只活一晚**——主人没批准的（点了「今晚先不做」/说「不做」/那晚没表态）过夜就用 `scripts/idea_pool.py prune` 删掉，不再第二次上桌；删掉的都归档进 `knowledge/idea-history.md` 只作去重依据。本节由 01:00 的调研补充，追加在末尾）。
- 批准清单 `~/.hermes/night-approved.md`：只有主人**明确点头**的项才写进去；02:00 只做本清单里 `- [ ]` 的项，做完勾成 `- [x]`。清单为空时夜间什么都不做。
- 维护脚本 `~/.hermes/scripts/idea_pool.py`：`list`（看池子）/ `approve <序号>`（批准，删候选行并写进批准清单）/ `drop <序号|--all>`（不要，删掉）/ `prune`（01:00 自动兜底，删过夜未批的）。**别手改 ideas.md / night-approved.md，一律走脚本。**

## 铁律

**任何想法先由晚报用 `::options` 征求主人批准，点头后才做，绝不自行挑活。** 晚报的选项块挑最多 3 条最值得做的 + 一条「今晚先不做」；顺序是 正文 → `::options` 块 → 最后单独一行 `::sysinfo`。

预览页 `preview-*.html` 会被站点页后端自动发现成只读灰条（见 `guga-hub.md`）。
