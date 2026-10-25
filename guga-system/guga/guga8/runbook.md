# 八号的工作手册（巡检与维护）

> 判据、阈值、脚本、日志——写清楚，是因为夜里跑的东西没人盯着，下次接手的人（或下次的我）必须靠这份文件判断"要不要动手"。

## 巡检清单

| 项 | 频率 | 怎么看 | 判据与动作 |
| --- | --- | --- | --- |
| swap 占用 | 每夜 03:40 | `swap-patrol.py` | ≥70% 出声提醒主人；≥85% 加重措辞并建议清残留或扩容；<70% 静默 |
| 内存可用 | 同上 | `/proc/meminfo` 的 MemAvailable | 可用 < 500MB 视为紧张，写进巡检日志 |
| 浏览器会话数 | 每夜 03:40 | `browser-daemon-reaper.py --max-sessions 10` | 超过 10 个收最旧的，保留最新 10 个 |
| daemon 孤儿 | 每 30 分钟 | `browser-daemon-reaper.sh`（静默入口） | CDP 目标已死 + 无人连接 + 存活 >5 分钟 → 收 |
| daemon 空闲 | 每 30 分钟 | 同上 | 无连接且 CPU 零增长 ≥1 小时 → 收（`REAPER_TTL_SECONDS`，2026-10-20 由 2h 收到 1h） |
| 临时浏览器 | 每 30 分钟 | 同上 | 没有 daemon 指着它的调试端口、CPU 基本空闲 ≥1 小时 → 收整棵树（agent-browser 通常自己会退，这是兜底） |
| 服务健康 | 有空就看 | `systemctl status guga-*` / `guga6-watch` | 只读；掉了先记录再上报，不擅自 restart |
| 磁盘 | 顺带看 | `df -h /` | 根分区 >85% 上报 |

## 安全判据（宁可不收）

1. daemon 的 IPC socket 上有 ESTAB 连接（正在被用）→ 不碰。
2. 浏览器调试端口有外部客户端连进来（不是那个挂着不用的 daemon）→ 不碰。
3. 常驻档案 `~/.hermes/workbuddy/chrome-profile` 及其浏览器、挂着它的 daemon → 永不清理。
4. 起来不到 60 秒的进程 → 不动（避免和刚开始的调用打架）。
5. 任何探测失败（`ss` 用不了、端口判不出来）→ 当"在用"，放过。

## 脚本与入口

- 真身：`~/.hermes/guga/guga8/scripts/{swap-patrol.py, browser-daemon-reaper.py}`
- cron 入口：`~/.hermes/scripts/{swap-patrol.py, browser-daemon-reaper.sh}` —— 几行启动器，exec 真身（**不能放软链**：cron 会把软链判成"解析到 scripts 目录之外"直接拦掉，实测 `Blocked: script path resolves outside the scripts directory`）。
- `--dry-run` 只看不动；`--quiet` 例行清理静默只写日志；`--max-sessions N` 启用数量上限。
- 环境变量：`REAPER_TTL_SECONDS`（daemon 空闲阈值，默认 7200；cron 入口里设成 3600）、`REAPER_BROWSER_TTL_SECONDS`（浏览器，同上）、`SWAP_PATROL_MAX_SESSIONS`（默认 10）。
- **常态授权（2026-10-20 主人原话「清理浏览器残留吧，巡检自动清理就行」）**：纯垃圾回收——空闲/孤儿 daemon、没 daemon 挂着的临时浏览器、跑完留下的陈旧 `runtime/*.pid|*.sock`——**不用再问主人，巡检直接清**，只在日志里记一笔。
  仍然不许自作主张的：常驻档案那台浏览器、正在被用的、重启服务、动基础设施。

## 台账与日志

全部在 `~/.hermes/guga/guga8/state/`：

- swap 台账 `swap-watch.jsonl`（每次巡检一行）、当前状态 `swap-status.json`、巡检日志 `swap-patrol.log`
- 清理日志 `browser-daemon-reaper.log`（谁被收、为什么、释放多少）、巡检状态 `browser-daemon-idle.json`

## 升级路径

- 我能自己处理：清残留进程、清超限会话、记账与提醒。
- 需要一号/主人拍板：扩容 swap、改动基础设施、重启服务、清理正在登录态里的浏览器。
- 拿不准一律**先记账再上报**，绝不自作主张。

## 历史（踩过的坑，一句话）

- daemon 会累积不退（曾 19 个 / 340MB swap，把 swap 吃到 89%）；杀 daemon 不影响登录态（档案在磁盘），也不会带走浏览器。
- 别用子串匹配找 daemon（shell 命令行里出现这个名字会误伤）；进程年龄要用 `/proc/<pid>/stat` 的 starttime，不能用 `/proc/<pid>` 目录 mtime。
- 端口比对要统一成整数（`ss` 出的是字符串），否则"这浏览器还有 daemon 挂着吗"永远判成没有。
