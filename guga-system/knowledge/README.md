# 咕嘎的知识分区（2026-10-12 主人定的规矩）

四类知识，各归其位。常驻记忆（`~/.hermes/memories/MEMORY.md`）只放跨会话必须知道的身份与操控规矩，其余都在这棵树下。

| 类别 | 去哪找 |
| --- | --- |
| 技能与流程（跨项目通用做法与踩坑） | `procedures.md`；单个任务的细操作在 `~/.hermes/skills/<技能>/SKILL.md` |
| 每个工程项目 | `projects/<项目名>.md`，一项目一份 |
| 我自己的身份与操控记忆 | `~/.hermes/memories/MEMORY.md`（常驻） |
| 主人的想法与计划 | `~/.hermes/ideas.md`；价值观 `~/.hermes/life-principles.md`、饮食 `~/.hermes/diet-guide.md`（保留原路径，ideas.md 链过去） |
| **主人这个人（性格/习惯/爱好/动机）** | `knowledge/主人画像.md`（生成物，别手改）← 真源 `knowledge/profile/entries.jsonl`，工具 `~/.hermes/scripts/profile.py`（add/list/grep/render/stale），服务规矩 `knowledge/profile/service-rules.md` |
| 项目权威图纸与进度（原有，不动） | `~/stack/docs/agent-goofy-breeze.md`、`PROGRESS.md`、`feature3-plan.md` |

## projects 索引

- `projects/goofy-agent.md` —— 私人云端 Agent 项目总览（三功能、架构、服务器、部署形态、记忆隔离、备案）
- `projects/guga-hub.md` —— hub 网页外壳（顶栏、tab、聊天通道、站点页、远程连接页前端）
- `projects/guga-group.md` —— 咕嘎群（`/group.html`）与手机版（`/m.html`）：成员与消息模型、群信使、代发、怎么加成员
- `projects/feature3-remote.md` —— 功能③ 远程操作（自有机器接入、确认门、接入新机器、咕嘎六号、常驻入口与令牌模型）
- `projects/todo-and-briefings.md` —— 待办系统与定时简报（todos.md / todo.py / 每日固定项 / cron 作业 / 收件箱）
- `projects/night-automation.md` —— 夜间自动化（night-scan / night-project / night-watch、想法池与批准清单）
- `projects/workbuddy.md` —— 咕嘎三号 WorkBuddy（网页版浏览器接入、扫码登录怎么发码、能力与连接器清单、怎么派活）
- `projects/lightvela.md` —— 咕嘎四号 LightVela（托管 Hermes、飞书推送、公网静态站、exec 调用）
- `projects/resume.md` —— 孟庆达简历（原件/LaTeX 正式版路径、重出 PDF 命令、中文字体坑、内容待补的量化指标）

## 外援对照（什么时候找谁）

**派活规矩（2026-10-12 主人定）**：拿到任务先按各家优势决定派谁，**派之前先把「派谁、为什么」告诉主人，再动手**。

**八个咕嘎各有自己的家**：`~/.hermes/guga/guga0/` … `guga8/`（每个含 SOUL.md / MEMORY.md / journal/，有活儿的还有 scripts/ 与 state/）。**完整职责索引在 `~/.hermes/guga/INDEX.md`**——它是权威版本，下表只是摘要；搬迁与新增的规矩见技能 `guga-roster`。

| 找谁 | 独门本事 | 怎么叫 |
| --- | --- | --- |
| **零号 编码咕嘎**（**主人真正的工作主力**） | **编码相关的一切**：规则、工作流、项目实现；工作区一个项目一个目录，交付要能跑 | 在 `~/workspace` 里开 Claude Code（根目录 `CLAUDE.md` 就是他的规则书） |
| **三号 WorkBuddy**（腾讯办公 Agent） | 交付**文件级成品**：PPT/Word/Excel/PDF/看板/视频；技能市场 + 一堆 MCP 连接器（腾讯文档、GitHub、Notion、可灵生图生视频、金融数据…）；桌面客户端能碰本地文件 | 浏览器（常驻档案）+ `~/.hermes/workbuddy/wb.py`；异步跑，成品在「产物」区 |
| **四号 LightVela**（腾讯轻量云·托管 Hermes） | **推消息到主人手机（飞书）**；**建站并发布到公网 URL**；内存更宽（7.6G）；**GitHub 直连**；SkillHub 装技能 | `~/.hermes/lightvela/lv_exec.py "<命令>"`（exec API）；或直接对话 |
| **我自己（一号）** | **日常辅助**：hub 界面、待办与简报、远程操作、记忆与知识管理、夜间自动化（编码规矩归零号） | 就在这儿说 |

## 既有技能索引（会被按需加载）

`todo-butler`（待办）、`cron-briefings`（定时简报与提醒任务）、`guga-hub`（hub 界面与后端）、`remote-ops`（远程操作）、`lightvela-delegate`（咕嘎四号）、`obsidian`、`maps` 等。
