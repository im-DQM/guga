# 八号的记忆

## 我在看什么（当前状态，随巡检更新）

- 机器：腾讯云 CVM，3.6G 内存 + 1.9G swap（`/swap.img`），根分区 40G。
- 2026-10-15 交班时的底账：swap 曾用到 89%（1734/1988MB），清掉 11 个残留 daemon 与测试会话后回到 **74%**（可用内存约 1.9G）。
- 当时压在 swap 里的大头：一号自己（hermes 网关，约 420MB）、claude CLI（约 383MB，长期没动）、code-server（约 328MB）、常驻 chrome（约 224MB）。这三个我没动——要动得主人点头。
- 台账：`state/swap-watch.jsonl`（历史）、`state/swap-status.json`（当前）、`state/browser-daemon-reaper.log`（清理记录）。

## 我记住的教训

- daemon 只增不退是这台机器的老毛病；清残留是日常，不要等爆了才做。
- 清理的底线：有连接的不碰、常驻档案不碰、拿不准就放过——**宁可留垃圾，不许误杀正在干活的会话**。

## 待办 / 隐患

- claude CLI 与 code-server 是否算"该清的残留"，等主人拍板。
- 若 swap 长期停在 70% 以上，建议主人考虑扩容（磁盘还剩 26G）或收缩常驻进程。
