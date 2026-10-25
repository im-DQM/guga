# 项目：咕嘎四号 —— LightVela（腾讯轻量云托管的 Hermes）

技能：`lightvela-delegate`。位置：`~/.hermes/lightvela/`。

## 它是什么

腾讯**轻量云**团队的云端 Agent 托管产品，里面跑的就是 **Hermes Agent**（跟我同内核，我是 v0.21.6，它 v0.21.3）。**它不是我，但会干我能干的事**——而且有几样本机没有的本事。

- 实例 id：`ins-e832610d8a474b67923bcf2aa02369e4`；bot 名「咕嘎4号」。
- 家底（2026-10-12 实测）：**2 vCPU / 7.6 GB 内存 / 50 GB 盘**（本机是 4 vCPU / 3.7 GB，内存常年只剩 1.4 G —— **它内存比我们宽裕得多**）。
- 出口 IP `110.42.235.24`（上海·腾讯云）：**GitHub 能直连**（本机直连卡死）。
- 模型：走它自带的网关 `https://token.lightvela.com/v1`（`model.default: auto`），**不花我们这边的 key 和额度**（它是套餐+积分制）。
- 已装技能 22 个（18 builtin + 4 local）：本地那 4 个是**建站/部署专用**——`website-builder`、`vela-static-deploy`、`web-mobile-adaptation`、`static-web-project-collab`。

## 怎么调用（我把它当外援的两条路）

1. **直接对话**：`https://lightvela.com/agents/chat/`（浏览器，需登录态）。
2. **debug/exec（最常用、最可靠）**：`python3 ~/.hermes/lightvela/lv_exec.py "<shell 命令>"` —— 在它的实例里跑命令并拿 stdout。凭证在 `~/.hermes/lightvela/cookie.txt`（微信扫码得来，约 30 天）。

## 独门本事（本机没有的）

1. **飞书推送** —— 它的通道里连着飞书 DM（`feishu:oc_74189899ed152ec572508f8840568b99`），`hermes send --to feishu --file /tmp/x.txt` 即可。**这是我唯一能把消息送到主人手机的路**（本机没接任何消息平台）。
2. **Workbench 静态网站（发布到公网）** —— 它能把网页**建好并部署成一个公网地址**，托管它负责、不用备案域名。现有站点 `ws-967fb31fbeb6019f` → `https://ws-967fb31fbeb6019f.lightvela.tech/`。生成用 React/TS/Tailwind，内容可编辑、只用浏览器 localStorage（无服务端存储）。**想做「能发给别人打开看」的页面，用它比挂 hub 强**（hub 只有能进隧道的人打得开）。
3. **更宽的内存 + GitHub 直连** —— 本机跑不动的活（大依赖、重构建、批量下载）可以扔给它跑，结果我通过 exec 取回来。
4. **SkillHub / ClawHub 技能市场** —— `skills_store_cli.py` 可搜可装技能包，能力随时扩。
5. 它自己也有 cron（早报 08:00 / 晚报 20:00，`--deliver feishu`）和独立记忆。

## 咕嘎群的搬运通道（2026-10-13 建）

主人在群里点到「四号」，话就由 `~/.hermes/scripts/agent_carry.py` 送到它实例里跑一轮，
**用它的记忆、它自己的口吻**回答，原话贴回群（标「代发」）。要点：

- 驱动命令：在它实例里 `hermes -p default chat -Q --pass-session-id [--resume <sid>] --query-file /tmp/guga_group_q.txt`
  （`-Q` 出纯文本，`--query-file` 免转义；中文先 base64 落文件）。
- 它的「咕嘎群会话」id 存在我这边的 `~/.hermes/state/carry.json`（**它的记忆不在这儿**，这儿只记会话号）。
- 它的记忆是它的：`/home/agentuser/.hermes/memories/{MEMORY.md,USER.md}`（它记得主人的作息/饮食/决策尺子——
  我读它之前以为会没有，实测**真有**）。我只读、只驱动，**不代它写记忆**。
- 它的口吻是一只叫「喵之人」的猫（主人 2026-10-13 说不用改，传话就传原话）。
- 一次搬运约 15-20 秒；失败（凭证过期 / 会话没了）时脚本会自动重开一段会话重试一次。

## 早晚报同步（2026-10-13 主人要的）

主人要「四号也发我的早晚报内容」。做成了**单向照抄**：我生产，它播报。

- **它的两个 job 改成脚本任务**（不再是 agent prompt）：`早报` `6 8 * * *` → `guga_brief_morning.sh`，`晚报` `9 22 * * *` → `guga_brief_evening.sh`，均 `--deliver feishu`、`--no-agent`。脚本就是 `cat /home/agentuser/.hermes/brief/<今天>-{morning,evening}.txt`，没有文件则输出一句兜底提醒。**不用模型 → 一字不改。**
- **我这边推**：`~/.hermes/scripts/brief_to_lv.py`（cron 作业 `brief-to-lv`，`c688760ce482`，`4,9,14,19,24,29,34 8,22 * * *`，no-agent、成功静默）。取 `~/.hermes/cron/output/<job_id>/<今天>_*.md` 的 `## Response` 段 → 滤掉 `::xxx` 整行与末尾 `•` → base64 过桥写进四号 `/home/agentuser/.hermes/brief/`。状态在 `~/.hermes/state/brief_to_lv.json`，同一天同一条按内容哈希只推一次；没生成就静默等下一轮（5 分钟一档，30 分钟内共 7 次重试）。
- **时间顺序是关键**：我的简报 08:00 / 22:00 在前（agent 跑完才落盘），推送 08:04–08:34 / 22:04–22:34，四号 08:06 / 22:09 发飞书。它原本的 20:00 晚报已挪到 22:09——20:00 时我当晚的晚报还不存在。
- **滤掉的**：`::sysinfo`、`::options` 这类只有 hub 认的指令行和末尾蓝点；正文其余原样（含夜间小工程的候选行——飞书上只是文字，点了没用）。
- **验证**：四号侧 `hermes cron list` 看 Mode 是否 `no-agent (script stdout delivered directly)`；真送没送到看 `/home/agentuser/.hermes/cron/executions.db` 的 `delivery_outcome='delivered'`（list 里的 ok 只代表脚本跑完了）。手动试跑 `hermes cron run d2dca5a660e9` 会真发一条飞书。

## 边界与坑

- **没有回到本机的通道**（本机没公网入口）→ 联动只能**我主动调它的 exec**，它不能主动找我。
- 托管版 CLI 的坑：`hermes cron create` 不收位置参数 prompt（要 `cron edit --prompt`）；UI 时间框改不动（React 受控）；长中文先 base64 落文件再 `$(cat …)`。
- **不碰**它的套餐、支付、账号、实名设置。
- 凭证约 30 天到期：`cred_status.py` 实探一次接口（401/403 即死）+ 晚报提前提醒主人重扫；重扫后要更新 `meta.json`。

## 什么时候找它

- 要把消息推到主人手机 → 找它（唯一出口）。
- 要一个公网能打开的静态页面/小工具站 → 找它。
- 要装/跑本机放不下或不方便装的技能、要 GitHub 直连、要更宽内存跑重活 → 找它。
- 其余（本项目内的开发、hub 改造、待办与简报）→ 我自己干。
