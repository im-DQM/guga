# 项目：私人云端 Agent（咕嘎一号的总项目）

## 是什么

咕嘎一号隶属「私人云端 Agent」项目（自建 / 单用户 / 国产模型），三功能：① 管家 = Hermes（我）② 编码 = Claude Code + code-server(8081) ③ 远程操作他机（命令行级、目标机零安装，backend=local 用 ssh 别名）。架构「换壳不换引擎」：ttyd + tmux + Caddy 把现成 TUI 搬上网页。

服务器：腾讯云 `106.55.38.108`（Ubuntu 24.04、4核4G/40G），ssh 别名 `dqm`；访问方式＝主人本机双击「启动隧道.bat」→ `localhost:8080`（hub）/ `localhost:3000`（Gitea）。`sudo` 免密。

> **Gitea 已默认停用（2026-10-25 主人决定省内存）**：容器 `gitea`（compose 里 `restart: unless-stopped`）现在是 Exited 状态，`localhost:3000` 不再监听，hub 站点页里那条 Gitea 入口点开是空的。要用时 `sudo docker start gitea`（或 `cd ~/stack && docker compose up -d gitea`），起来后入口照旧；不用了再 `sudo docker stop gitea`。省下约 70MB 内存在用。
实例身份（2026-10-13 查实）：这台是**轻量应用服务器 Lighthouse**，不是云服务器 CVM —— 元数据 `instance-name = lh-1502313268-lhins-k3vao65d`（`ins-7h76ngx6` 是底层 CVM 号），`ap-guangzhou-7`。**开/关端口要去「轻量应用服务器 → 实例 → 防火墙」页签，不是 CVM 的「安全组」**（两处界面长得像，别搞混）。默认只放通 22/80/ICMP，所以 443 要手加。

权威进度与图纸（原有文档，保持更新）：`~/stack/docs/agent-goofy-breeze.md`、`~/stack/docs/PROGRESS.md`、`~/stack/docs/feature3-plan.md`。

## 部署形态

Hermes api_server 无状态会话（网关 127.0.0.1:8642，无 chat_id）。cron 默认 `deliver='local'`，输出落 `~/.hermes/cron/output/<job_id>/*.md`，界面打开时经 `GET /api/inbox` 领取（hub 顶部「定时消息」横幅）；主人**不要即时推送**。未接消息平台，倾向飞书（=咕嘎二号，已停用）。

## 记忆隔离（2026-10-10）

**我是大管家，看得到所有记忆；远程操作那边是分身，看不到我的。** 两套 profile 共用一个网关：管家 = `default`（`~/.hermes/`，原样不动）；远程操作 = `~/.hermes/profiles/remote/`（空记忆）。共用**技能与工具**（remote 的 `skills/` 是软链到 `~/.hermes/skills`），remote 有自己 SOUL，`.env` 拷了模型密钥 + `API_SERVER_KEY`（**剔掉 `API_SERVER_ENABLED` 避免抢端口**；不补 `API_SERVER_KEY` 则 `/p/remote/*` 401）。前端「远程连接」页走 `/api/hermes/p/remote/...`（`apiBase()` 按面板切）。**新建 profile 后必须 `hermes gateway restart` 才进 multiplex**（需 `XDG_RUNTIME_DIR=/run/user/1000`）；改 profile 的 `.env` 热生效。

## 咕嘎编号总表（2026-10-10 主人确认）

- 一号 = 服务器本身（我就住在上面，看得到所有记忆）；**服务器不列入「远程连接」页的机器列表**——要操作服务器，直接跟我说。
- 二号 = 飞书（已停用）
- 三号 = WorkBuddy 上的智能体（**尚未接入，目前没有任何通道**）。2026-10-12 主人告知：WorkBuddy 是**客户端软件**（不是网页/API）——所以没有后台对接的路，只剩「在它装的那台机器上做界面自动化」这一条（脚本跑在主人登录会话里，用 Windows UI 自动化读窗口文字、点按钮；软件改版会让脚本失效，窗口得开着）。**待确认：装在哪台机器上、要它干什么。**
- 四号 = 腾讯 LightVela 上的智能体（技能 `lightvela-delegate`）
- 五号 = ASUS 笔记本（`win-asus`，自有·常驻，反向隧道，「远程连接」页目前唯一一台）
- 六号 = 以后新接的其他机器，**统一归六号、不递增**，多了靠括号描述区分（如「咕嘎六号（张三的电脑）」）

名字写在 `~/stack/remote/hosts.json` 的 `name`；在「远程连接」页聊天时会注入「你就是咕嘎N号」，它以此自称。

## 备案状态

域名 `dqmguga.site` 已实名、**2026-10-13 备案通过**，公网已上线（解析 @ / www / join → 106.55.38.108，DNSPod）：

- `https://dqmguga.site` + `https://www.dqmguga.site` = hub 整套（聊天 / 面板 / `/hermes` `/claude` `/shell` / 各 api），**整站 `basic_auth`**（用户 `guga`，密码存 `~/.hermes/secrets/hub-basic-auth.txt`）。
- `https://join.dqmguga.site` = 六号网页授权接入页，免密，但只白名单 join 的几条路径（见 `feature3-remote.md`）。
- 私网 `:8080` 站点一字未改，继续只走隧道（ufw 未放行 8080，公网进不来）。
- 细节与踩坑（Caddyfile 单文件挂载必须 restart、公网白名单内容）见 `~/.hermes/knowledge/procedures.md §0`。

## 我的知识分区

见 `~/.hermes/knowledge/README.md`：技能与流程 → `procedures.md`；每个工程 → `projects/<名>.md`；身份与操控记忆 → `~/.hermes/memories/MEMORY.md`；主人的想法与计划 → `~/.hermes/ideas.md`。
