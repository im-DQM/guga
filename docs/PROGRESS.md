# 工作进度

> 更新：2026-10-12 ｜ 设计文档：`C:\Users\ASUS\.claude\plans\agent-goofy-breeze.md`（服务器副本 `~/stack/docs/agent-goofy-breeze.md`）
> **功能③ 施工图**：`~/stack/docs/feature3-plan.md`（P0–P7 全量计划；P7 见其 §10）

## 一句话

私人云端 Agent —— **咕嘎一号（管家）+ 编码（VS Code + 多开 claude 终端）+ 远程操作**，跑在腾讯云服务器上，浏览器访问。

---

## 服务器

- **IP**：`106.55.38.108`（Ubuntu 24.04，4 核 / 4G / 40G 盘）
- **登录**：`ssh ubuntu@106.55.38.108`（密钥 `~/.ssh/dqm_lighthouse_ed25519`，本机别名 `dqm`）
- **一键隧道**：双击 `启动隧道.bat`（开着即通，关掉即断）

---

## 2026-10-10 → 10-12 这轮做了什么

### 《我的夹心》· 数据改服务器存储（去「硬编码」）
- **痛点**：`hub/jiaxin/index.html` 是单文件网页，数据焊在 `DEFAULT_DATA()` 里；想让数据「真的更新」就得回来改 HTML，而本地 localStorage 又会盖住硬编码 —— 于是每次都在硬编码。
- **新服务 `guga-jiaxin-api`**（`~/stack/jiaxin_service/jiaxin_api.py`，`:8794`；Caddy 加 `handle_path /api/jiaxin/*`）：`GET/PUT/POST /data` 整包读写 `data.json`（原子写 + `.bak`），`GET /health`。`rev` 自增，**LWW**（后写覆盖），落后只回 `conflict:true` 提示。
- **前端**：`save()` 签名不变（20 处调用点零改动），改成「立即写 localStorage（离线缓存）＋防抖 800ms 推服务器」；首屏仍同步渲染、之后异步对齐服务器；关页/切后台 `sendBeacon`（POST）兜底；header 加了同步小圆点（绿/橙/红）。
- **判定**：服务器有数据且本地无未同步改动 → 服务器赢；服务器空 → 本地推上去播种；断网 → 用本地继续、联网补推（`dirty` 存在 `woDeJiaXin.sync.v1`）。**切 tab 只落本地**（`saveLocalOnly`），不算数据改动，避免每次开页回推。
- **首次播种**：部署后**先用存有真实数据的那台浏览器打开一次** `/jiaxin/`，否则可能以别的浏览器/种子数据播种。
- **页脚文案**：已从「不会上传到任何地方」改成如实描述（数据在服务器、本地留缓存）。

### 管家（咕嘎一号）
- 空状态精简成一行「**咕嘎一号随时待命**」：去掉原来的 logo 方块、示例 chip、以及相关死 CSS（`.empty .logo` / `.chips` / `.chip`）

### 编码页（大改）
- **VS Code 换深色**：给 `code-server` 配 `Default Dark Modern` + 一组自定义配色（底 `#0A0A0A`、面板、强调靛紫 `#7C8CFF`），和 hub 一致；**默认打开 `~/workspace`**（不再停欢迎页）；关掉受限模式横幅 / Chat 面板 / 遥测
- **布局**：左 VS Code ＋ 右上 claude 终端 ＋ 右下 shell 终端；两条**可拖拽**分隔线（默认 **54% / 69% / 31%**，记忆在 localStorage）
- **claude 终端多开**：一个 tmux 会话的多个窗口 = 多个 claude 对话。切换条 `guga [1] [2] … + ×`：点 `+` 新建、点数字切、点 `×` 删当前（保留最后一个）；**默认 1 个**
- **配色**：claude 终端 = 蓝 `#4C8DFF` ＋ 金 `#E4C57E`；shell 终端 = 靛紫 `#7C8CFF`；tmux 状态栏深色
- **终端能滚了**：tmux `mouse on`（滚轮进 copy-mode 看历史）＋ `history-limit 20000`

### 功能③ · 远程操作（自有机器打通 ✅）
- **服务器基建**：生成 `~/.ssh/guga_ops`（服务器→目标机）；`~/.ssh/config` 配连接复用/保活；主机注册表 `~/stack/remote/hosts.json`（只含自有机器）+ `gen-config.py` → `~/.ssh/config.d/guga-remote`（别名 `win-asus`）
- **入站隔离**：受限账户 `tunnel`（nologin）+ `/etc/guga/tunnel_authorized_keys`（每台机独立隧道公钥，`restrict,port-forwarding,permitlisten="localhost:22022"`）+ sshd drop-in `60-guga-tunnel.conf`（`Match User tunnel`：仅许反向监听 22022–22025、无 pty/agent/X11、`ForceCommand nologin`）。**被攻陷的极限 ＝ 占一个回环端口**
- **NAT 反向隧道**：笔记本（NAT 后）主动 `ssh -R 22022:localhost:22 tunnel@106.55.38.108`，把自身 22 挂到服务器回环 22022；服务器 `ssh win-asus "命令"` ＝ 落到笔记本执行。保活用 **Windows 计划任务 + PowerShell 循环**（`C:\guga\keep-tunnel.ps1`）
- **一键接入脚本**：`~/stack/hub/onboard-windows.ps1`（hub 可直接下载）。装 OpenSSH Server（优先系统可选功能，不行用**服务器代下的官方包** `http://localhost:8080/OpenSSH-Win64.zip`）、放行防火墙、默认 shell 设 PowerShell、按账户类型落 ops 公钥（管理员走 `administrators_authorized_keys` + ACL）、本机生成隧道密钥、建保活计划任务
- **Hermes 技能**：`~/.hermes/skills/devops/remote-ops/SKILL.md`
- **验证**：`ssh win-asus "hostname"` → `LAPTOP-G34VAKMG`；在笔记本上写/读文件、查磁盘、`whoami` 全通

> **踩坑记录（都已修，很值钱）**
> 1. **`permitlisten` 主机名必须写 `localhost`，不能写 `127.0.0.1`** —— Windows 客户端发的是**空绑定**，服务器按 `localhost` 匹配；写 `127.0.0.1` 会被拒（`port forwarding refused`）
> 2. **PowerShell 里 `$var:xxx` 会被当成作用域限定**（像 `$env:PATH`）→ `-R $ReversePort:localhost:22` 会把转发规格整段吃掉，必须写 **`${ReversePort}`**。这是保活任务一开始死活不工作的真正原因
> 3. `AuthorizedKeysFile` 必须**目标用户可读**（`640 root:tunnel`），否则 sshd 以该用户身份读不了 → `Permission denied`
> 4. 目标机要下载的东西一律**由服务器代取、放进 hub、让目标机从 `localhost:8080` 拉**（国内直连 GitHub 会卡死）
> 5. `.ps1` 存成 **UTF-8 带 BOM + CRLF**，否则 Windows PowerShell 读中文乱码

### 功能③ · 「本机操作」页（P2 ✅）
- **第三 tab 打通**：`hub/index.html` 去掉 `disabled`，`#view-local` 换成「**左机器列表** + **右上咕嘎 / 右下命令**」（两条可拖拽分隔线，记忆在 localStorage `localVP` / `localHP`）。
- **右上直接复用咕嘎**：切 tab 时把管家的 `.chatwrap`（聊天+输入框整块）**搬进/搬回** 本机操作页（不复制代码；正在进行的流式回复也不会断）。
- **每台机器一份独立记忆 + 一段独立对话**（后来升级成**完全隔离**：远程操作走独立 profile，连总记忆都不共用 —— 见下一节）。
  - 专属记忆文件：`~/stack/remote/memories/<别名>.md`（后端 `/api/remote/machine` 读写；没有就自动建模板）。
  - 每台机器一个自己的会话（标题「远程 · 机器名」，映射存 `~/stack/remote/sessions.json`）；切 tab / 换机器会自动切换，与管家页的对话**互不干扰**。
  - 在本机操作页发消息时，该机器的记忆会作为 **`instructions`（临时系统提示）** 注入 `/v1/runs`；管家页不注入。
- **新服务 `guga-remote-api`**（`~/stack/remote/remote-api.py`，`:8792`；Caddy 加 `handle_path /api/remote/*`）：
  - `GET /hosts` → 机器列表 + 在线状态（reverse 机器先探回环端口，再 `ssh … exit` 冒烟；缓存 20s；多台并发）
  - `POST /exec` → **确认门**：只读**直接跑**；写/危险先回 `need_confirm` + 待批 id（不执行）
  - `POST /approve` → 放行（**单次使用**，120s 过期）
  - 只读判定：含 shell 元字符（POSIX `; | & < > $ \``、Windows `& | < > %`）**一律危险**；否则取首 token 查白名单 + 子命令/flag 守卫；**default-deny**
  - 审计 JSONL → `~/stack/remote/audit.log`（只记大小不记输出正文）
- ~~「本机」伪主机~~ **已去掉**：服务器本身就是**咕嘎一号**，不列进机器列表 —— 要操作服务器直接跟管家说。（后端也一并拒了 `host=local`）
- **systemd 硬化**：`NoNewPrivileges`、`ProtectSystem=strict` + `ReadWritePaths=/home/ubuntu /tmp`、`CapabilityBoundingSet=` 清空、`RestrictAddressFamilies`、`MemoryMax=512M`。**不设 `ProtectHome`**（会挡 `~/.ssh/guga_ops` 与 control 套接字）；`ReadWritePaths` 放开 `/home/ubuntu /tmp`（否则「本机」写不了文件）。
- **验证**：无头 Chromium 经 CDP **真点页面**跑通 —— 切 tab、两台机器、选机器出常用命令、`hostname` → `LAPTOP-G34VAKMG`、`del foo.txt` → 弹**危险确认卡**、取消后不执行、切回管家未破坏。

### 功能③ · 远程操作「独立记忆」（Hermes profile 隔离 ✅）
- **两个 profile、两套记忆、一个网关**：
  - 管家 = `default`（`~/.hermes/`）—— **看得到所有记忆**，一个字没动。
  - 远程操作 = 新 profile `~/.hermes/profiles/remote/` —— **空记忆**，看不到主人的任何私事。
- **共用技能与工具**：remote 的 `skills/` 是指向 `~/.hermes/skills` 的**软链**；`.env` 拷了模型密钥，**剔掉 `API_SERVER_ENABLED/KEY`**（避免第二套端口），但**必须补上 `API_SERVER_KEY`**（Caddy 注入的是 default 那把 key，缺了 `/p/remote/*` 直接 401）。
- **自己的咕嘎人设**：`~/.hermes/profiles/remote/SOUL.md` —— 仍是咕嘎，但写明「你不记得主人的生活，那些在管家那边；技能工具与管家共用；别碰服务器基础设施」。
- **每台机器一份专属记忆**：`~/stack/remote/memories/<别名>.md`，在该页聊天时作 `instructions` 注入；**每台机器一段独立会话**（标题「远程 · 机器名」，映射 `~/stack/remote/sessions.json`）。
- **前端**：本机操作页的 Hermes 调用走 `/api/hermes/p/remote/...`（`apiBase()` 按面板切换）；管家页仍走无前缀。
- **运维**：新建 profile 后**必须重启网关**才进 multiplex（`gateway_state.json` → `served_profiles: ['default','remote']`）；命令 `hermes gateway restart`（本机需 `XDG_RUNTIME_DIR=/run/user/1000`）。**热生效**：改 profile 的 `.env` 不用重启。
- **验证**：远程侧问「这台机器主机名？我叫什么名字、饮食方案？」→ 答 `LAPTOP-G34VAKMG`（真跑了 `ssh win-asus hostname`）+「**不知道，那些在管家那份记忆里，我这边看不到**」；管家侧问同样问题 → 「主人是孟庆达…在准备实习」。`default` 里**没有**任何「远程 ·」会话。

### 功能③ · 每台机器自己的会话栏（2026-10-11）
- 「本机操作」页选中一台机器后，**操作区顶部多一条会话栏**（`对话 N · 时间` 的药丸）+ 右上角 **「+ 新对话」**。
  → 五号/六号**各自能开多段对话、随时切回**，互不干扰；每段的空状态显示**它自己的名字**（「咕嘎N号随时待命」）。
- 实现：会话标题统一「远程 · <名字>」，**重名自动加「 · N」序号**；切换时把该会话 id 写回 `sessions.json`（自有机器）或 join 服务内存（guest）。
- **删除对话**：管家侧栏每条会话**悬停出 ✕**；机器会话栏每段药丸里也有 ✕。都带确认；
  删的若是当前那段，会自动切到另一段（没有别的就新建一段）。
- ⚠️ **踩坑**：**Hermes 不允许会话标题重复**（`Title '…' is already in use by session …`，400 `invalid_title`）——
  所以同一台机器的第二段对话必须取不撞的标题，否则 PATCH 失败、标题留空、会话栏就筛不到它。

### 功能③ · 咕嘎编号约定（2026-10-10 定）
**每台机器/连接有一个咕嘎编号**，在「本机操作」页和它的专属会话里用这个名字：

| 编号 | 是谁 | 状态 |
|---|---|---|
| **咕嘎一号** | **服务器本身**（管家就住在上面，看得到所有记忆）—— 正因如此，它**不列入**「本机操作」页的机器列表；要操作服务器直接跟管家说 | 在 |
| 咕嘎二号 | 之前接的 **飞书** | **已停用** |
| 咕嘎三号 | **WorkBuddy** 上的智能体 | 在 |
| 咕嘎四号 | 腾讯 **LightVela** 上的智能体（技能 `lightvela-delegate`） | 在 |
| **咕嘎五号** | **ASUS 笔记本**（`win-asus`，**自有 · 常驻** · 反向隧道）——「本机操作」页目前唯一一台 | 在 |
| **咕嘎六号** | **以后新接的其他机器** —— **统一归六号**（不递增）；多了就用括号里的描述区分，如「咕嘎六号（张三的电脑）」 | — |

- 名字写在 `~/stack/remote/hosts.json` 的 `name` 字段。
- 在本机操作页聊天时，会注入「**你就是「咕嘎N号」**——负责这台机器的咕嘎分身（不是管家）」，所以它会用这个身份自称。
- 新增机器：`name` 一律写「**咕嘎六号（简短描述）**」——**不递增**，全靠括号里的描述区分。

### 功能③ · 「接入新机器」模块（2026-10-10）
「本机操作」页左侧加了 **「+ 接入」** 按钮，点开是一个接入面板：

- **系统**：Windows / Linux·macOS 两套步骤（自动生成、端口和公钥都填好）
- **回环端口**：自动推荐下一个空闲端口（后端 `/api/remote/enroll` 算的；22022 已被五号占，推荐 22023）
- **别名**：自动生成 `m<端口>`，可改
- **名字**：默认「咕嘎六号（…）」——统一归六号
- **④ 粘回**：把新机器跑完打印的那段贴进来 → 自动解析出端口/用户名/公钥 → 拼成**给咕嘎的一句话** + 「复制这段」

**配套改动**
- `onboard-windows.ps1` **参数化**：`-Port`（每台机端口必须不同，之前写死 22022 会撞）；跑完改成打印**一段可直接粘给咕嘎的登记信息**
- 后端 `/api/remote/enroll`（ops 公钥 / 服务器地址 / 隧道账户 / 可用端口 / 推荐端口）；`/hosts` 增加 `listen_port`
- **`remote-ops` 技能新增「接入新机器」节**：咕嘎收到那句登记信息后，按①②③④做（写限制键 → hosts.json → gen-config.py → 验证），含 `permitlisten` 必须写 `localhost`、权限必须 `640 root:tunnel` 两个坑

**完整流程**：点「+ 接入」→ 按步骤在新机器上跑 → 复制它打印的话 → 贴给咕嘎 → 咕嘎登记 → 完

### 功能③ · 「别人的机器」网页授权接入（P7）—— **只定了设计，未开工**
- **需求**：对方在**他自己那台机器**上打开一个网页点【同意】，那台机器就连到服务器 → 被**咕嘎六号**接管，辅助那台机器工作。
- **已定**：授权页放**服务器**（给对方一个链接）；目标是**别人的机器**，与自有（咕嘎五号）那套**彻底分开**；**公网那半等备案 + 域名 + HTTPS**；主体可先建好、用隧道自测。
- **关键设计**（详见 `~/stack/docs/feature3-plan.md` **§10**）：
  - 新服务 `guga-join-api`（`:8793`，独立账户 `gugajoin`，**读不到 `~/stack`**）—— 它是**唯一要挂公网的东西**，与手里攥着 ops 密钥的 `remote-api` 隔离开
  - **绕开"给对方装临时密钥要 root"的死结**：用 sshd 的 `AuthorizedKeysCommand` 指向 **tmpfs** 上的密钥文件 → **不用 sudo、不放宽服务硬化、服务器一重启就清空**
  - **guest 无痕**：别名/密钥/日志/会话一律不落盘；操作记录**写回对方机器本地**（`~/.guga/audit.log`）
  - 同意页 `hub/join.html`（标题「**咕嘎六号请求访问**」）；「本机操作」页加「邀请别人的机器」按钮
  - 默认**只读协助**，要完整协助得对方主动切
- **状态**：✅ **服务器侧已实现并跑通**（2026-10-11）。**公网那半（给对方一个 https 链接）仍等备案 + 域名 + HTTPS。**
- **已落地**
  - **新服务 `guga-join-api`**（`/opt/guga-join/join_api.py`，`:8793`，系统账户 `gugajoin`，**读不到 `~/stack`**）—— 全系统**唯一准备挂公网**的东西
  - **临时密钥通道**：sshd 的 `Match User tunnel` 里加 `AuthorizedKeysCommand /usr/local/bin/guga-join-keys %u` → 一次性隧道公钥只写在 **`/run/guga-join/authorized_keys`（tmpfs）** 上。**不用 sudo、不放宽服务硬化**（`NoNewPrivileges` 保留），服务一停/机器一重启即空
  - `PermitListen` 从 22022–22025 **扩到 22022–22039**（多 15 个 guest 槽；22022 仍归咕嘎五号）
  - **同意页** `~/stack/hub/join.html`（独立干净小页）：标题「**咕嘎六号请求访问**」→「只读协助 / 完整协助」（**默认只读**）→ 点同意给出一条一次性命令 → 轮询状态（等待连接 → **已连接 ✓**）→「断开并撤销」
  - **发起端**：「本机操作」页机器列表头新增 **「邀请」**（与「+ 接入」并列）→ 生成链接 + 复制 + 状态 + 按 guest 撤销
  - **五号 / 六号彻底分开**：六号有**自己那段对话**（标题「远程 · 咕嘎六号（…）」），**绝不共用五号的**；但它**只活在这次连接里** —— 撤销时**连同会话一起删**（实测：撤销后该会话 404），且**没有专属记忆文件**。
  - **guest 会出现在「本机操作」的机器列表里**（标「**临时**」）：选中即可用命令框操作，**每条命令都先弹确认卡**（别人的机器一律确认）；对方只给「只读协助」时，写/危险命令服务端直接 **403**。撤销 / 服务重启 / 机器重启后它就从列表消失（无痕）。
  - Caddy 加 `handle_path /api/join/*`（注入 `X-Guga-Join-Admin`，密钥在 `/etc/guga/join_admin_secret`，640 root:gugajoin）
- **实测通过**（拿服务器自己当"对方机器"模拟；端口 22023 避让咕嘎五号）：签发 → claim → 密钥进 tmpfs → **只用 tmpfs 那把密钥建反向隧道成功** → 端口绑上 → 页面转 **connected** → `/guests` 出现「咕嘎六号（…）」→ **撤销后 key 行数 0、密钥目录清空、端口释放、`~/stack` 与审计日志零残留**
- **修掉三个真 bug**：① `_token_state` 返回的是**副本**，claim 之后没写回存储 → **token 实际不是一次性**（第二次 claim 仍 200）；② `_key_fingerprint` 取错字段（带 options 的行是 `[选项 类型 base64 备注]`，base64 在 `parts[2]`）→ **撤销时 key 删不掉**；③ **Caddy 的 `handle` 不剥前缀**（`handle_path` 才剥）→ 页面生成的 `/join/onboard` 到了服务那边还是 `/join/onboard` 而服务只认 `/onboard` → **404**。修法：服务端兼容两种路径（开头是 `/join` 就去掉）
- ⚠️ **部署坑**：systemd unit **不允许指令行尾注释** —— `ProtectHome=yes  # 说明` 会让 systemd 把整条硬化**静默忽略**（日志里只有一行 "Failed to parse"）。注释必须单独一行。
- ⚠️ **Windows 计划任务坑（真机上才暴露）**：① **join 必须用专用隧道密钥**（`guga_join_tunnel`），不能复用自有机器那把 `guga_tunnel` —— 否则同一把 key 在**静态文件**里只有 `permitlisten=22022`，而 sshd **静态先命中就不再跑 `AuthorizedKeysCommand`**，会把 tmpfs 里的 22023 遮掉 → 转发被拒（实测日志：`remote port forwarding failed for listen port 22023`）；② Task Scheduler 默认「已在运行就 IgnoreNew」，**重复跑脚本不会换掉卡住的旧实例**（旧实例用着旧密钥一直重试）→ 脚本里要先 `Stop-ScheduledTask`，并把 `MultipleInstances` 设成 `StopExisting`；③ **保活循环里的 `-i` 路径必须跟着 `$TunnelKey` 变量走** —— 我一开始写死成 `.ssh\guga_tunnel`，结果"密钥生成用新的、循环用旧的"，白折腾一轮；④ **`$cur | Where-Object {...}` 只剩一个元素时 PowerShell 会解包成标量** → `$cur + $line` 变成**字符串拼接**，把授权文件的两行并成一行（sshd 因此读不出那条 key）→ 必须套 `@()`；⑤ **`New-ScheduledTaskSettingsSet -MultipleInstances StopExisting` 在老版 Windows 的枚举里不存在**（只有 Parallel/Queue/IgnoreNew）→ 脚本报 `ParameterBindingArgumentTransformationException`；改用「先显式 `Stop-ScheduledTask` 再 Register+Start」
- ✅ **2026-10-11 11:06 在真·Windows 笔记本（ASUS）上实测通过**：同意页 → 命令 → 脚本 → 登记 → 反向隧道 → **服务器用本次专属密钥登进去跑 `hostname` 返回 `LAPTOP-G34VAKMG`**，且 **命令先被记进笔记本本地的 `~\.guga\audit.log` 才执行**（记录写回对方机器 ✅）
- ✅ **2026-10-11 已在真·Windows 目标机（ASUS 笔记本）上完整验过** —— 详见下面「常驻接入页」节。原「还没验：真·Windows 目标机」一条**已作废**。
- ⏳ **仍未做**：公网 `https://join.<域名>` 那条链（等备案 + 域名 + HTTPS）
- ⚠️ 计划文档里旧版的「连接设备 tab」一节（**我最初理解有误**）**已标作废**，别照做

### 功能③ · 咕嘎六号「常驻接入页」+ 连接密码 + 关网页自动断开（2026-10-11 → 10-12）

主人三句原话：「把咕嘎六号的邀请页做成常驻站点，**谁都能打开连接我的咕嘎六号**」→「**先连接要先输入密码**，并且**关闭网页后自动断开连接**」→「我可以在我的主机上的**本机操作模块里随意更改**」。

- **常驻入口（无 token）**：`/join.html` **不带 `?t=`** 时 = 常驻入口 —— 页面自己调 `POST /api/join/connect` 现场签一个 token。**谁打开都能自己接**（但仍要过密码）。
  - `/connect` **刻意不要求 admin**（备案后公网白名单只放它 + `/claim` `/status` `/alive` `/heartbeat`，**绝不放 `/settings`**）。
  - 带 `?t=` 的一次性邀请链接走**老路**，一字未改（链接即凭证，**不用**密码）。
- **连接密码**：`/var/lib/guga-join/password`（首次启动自动生成 6 位好念的，去掉 `i l o 0 1`）。
  - **只管常驻入口**；`/connect` 用 `secrets.compare_digest` 校验；**留空 = 不设密码**。
  - 在 hub「本机操作」页**左侧栏最底那块「接入页」**（`#localGate`）里**看 / 改 / 随机换**，回车即保存，**改完立刻生效**（不用重启服务）。原来放在「邀请」弹窗里，主人要求挪出来常驻可见 —— 弹窗现在只管一次性邀请，**避免两处不同步**。
  - ⚠️ 密码文件**不能放 `/etc/guga/`**（那里归 root、还有 admin 密钥，绝不能让这个公网服务能写）→ 改用 systemd 的 **`StateDirectory=guga-join`**（自动建 `/var/lib/guga-join` 并加进 `ReadWritePaths`）。
- **关网页自动断开**：页面开着每 20 秒 `POST /api/join/heartbeat` 续租（`LEASE=130`）；页面一关心跳停 → 服务端 `_sweeper` 线程（每 10 秒）自动 `_do_revoke`。
  - **服务器杀不掉已建立的隧道**（那个连接跑在受限账户 `tunnel` 名下，而 join 服务只有 `gugajoin`，也不是 root）→ 所以 onboard 脚本的保活循环加了**看门狗**：每 15 秒问一次 `GET /api/join/alive?t=`，服务器说 `no` 就 kill 隧道 + 移除公钥 + 注销保活任务。`alive()` **只在服务器明确回 `no` 时**才算会话没了；请求失败（网断/服务器重启）一律当「还活着」，免得网络抖一下就把连接拆了。
- **实测（拿咕嘎五号当 guest，走真实用户那条路 `irm '…' | iex`）**：
  - 点「断开并撤销」→ **10 秒内**隧道进程归零、公钥行归零、**计划任务已注销**
  - 关网页（不发心跳）→ 服务器 **+90s** 自动撤销（日志 `租约到期，自动撤销 …（页面已关闭）`）→ 五号随即自拆
  - 五号**自有通道全程完好**（用 `-o ControlPath=none -o ControlMaster=no` 新连接复验）；服务器 `guests=0`、tmpfs 0 行
  - **操作记录确实写回对方机器本机**：`%USERPROFILE%\.guga\audit.log` 实测拿到 `时间戳 / SSH_CLIENT / hostname` 那行，服务器侧无副本
- **本轮修掉的真 bug（都是真机才暴露的）**：
  1. **`/alive` 必须走 `/api/join/alive`** —— Caddy 只给 `/join/onboard*`、`/join/offboard*` 建了路由，其余 `/join/*` 落到底部静态站返回 **404**；而我给 `curl` 加的是 fail-safe（请求失败就当还活着），于是 404 被当「会话还在」，**静默掩盖**了 bug（单独 curl `/alive` 看着好好的，其实走的是错路径）。改用 `/api/join/*` 后**不必动 Caddyfile**。
  2. **`onboard-sh.sh` 解析 claim 响应的 `sed` 写死了「冒号后紧跟引号」**，而服务端 JSON 是 `"port": 123`（**冒号后有空格**）→ **Linux 目标机一直「登记失败」**。这是**原有** bug，之前只拿 Windows 真机测过所以没暴露；已改成 `[ ]*`。
  3. **`@"…"@` 双引号 here-string 里 `$false` 会被插值成 `False`** → 生成出 `-Confirm:False` → `Unregister-ScheduledTask` 参数绑定失败 → **计划任务永远注销不掉**（**原版就有**这个 bug，所以五号上一直挂着上一轮留下的旧任务）。必须写 `` -Confirm:`$false ``。
  4. **清理顺序**：`Stop-ScheduledTask` 停的就是**脚本自己** → 必须放**最后**；注销任务要放**最前**，否则后面全不执行。
  5. **每次 join 装的是「当场生成的一次性 ops 公钥」** —— `/claim` 返回的是 `_gen_keypair()` 那把**临时**钥匙（注释 `guga-join@cloud`），**不是**长期 `guga_ops.pub`。所以每次接入都往对方机器加**一条新**公钥，脚本里的去重只按自己的 base64 比 → 旧的清不掉、**会累积**（五号上就攒了 5 条）。
  6. ⚠️ **我犯的错（值得记牢）**：清五号残留时按 `guga-join` 过滤 `administrators_authorized_keys`，**把自有机器那条 `guga-ops@cloud` 也删了** → 五号自有通道当场断掉；**而 `ssh win-asus` 看着还是通的**，因为 ssh 复用了 `ControlMaster`（`ControlPersist 300`）。**教训：判断一条通道是否真通，必须 `ssh -o ControlPath=none -o ControlMaster=no`。**（修法：把 `~/.ssh/guga_ops.pub` 追加回去并修 ACL。注意 ASUS 是管理员组，钥匙放 `administrators_authorized_keys`，**不是**用户级 `~/.ssh/authorized_keys`。）
- **token 安全模型（2026-10-11 复核 · 主人拍板**不改**）**：主人问「先输密码后给连接命令，那他下次直接复制这条命令不就绕过密码了？」**结论：不会** —— 命令里的 token **一次性**（`_claim` 要求 `state=="waiting"`，连上后变 `claimed`，再跑返回 410）+ **10 分钟过期**（`TTL=600`）；而新 token 只能由 `/connect` 发，`/connect` **要密码** ⇒ **重连必须重新打开页面 + 重输密码**。残余风险（已告知、已接受）：命令本质是**短命 bearer 凭证**，谁拿到它能在 ≤10 分钟内、**一次**、不输密码地连进来。将来若要收紧：`TTL` 改 120（零代价，窗口缩 5 倍）/ `/connect` 记浏览器 IP 而 `/claim` 要求同 IP（转发即失效，但「手机开页面、电脑跑命令」会误伤）。详见 `~/.hermes/skills/devops/remote-ops/SKILL.md` 的「token 的安全模型」小节。

### hub 第④ tab「站点地图」（2026-10-11）

主人原话：「新增一个模块，专门用来存储网站的子域名……一个列表，每个前面用**特殊颜色标识**，后面是具体域名，并且可以**快速跳转**，鼠标**悬停显示该网页具体功能**」。拍板：**顶部第 4 个 tab**、**颜色每条自己选**、**存服务器**、**也列临时入口**、**能删除/编辑 + 置顶/排序**、不做搜索框。

- **hub 顶部现在四个 tab**：咕嘎一号 / 编码 / 本机操作 / **站点**。
- **站点页** = 「本网站所有页面入口的清单」：每条 = **主人自己选的颜色点** + 名称 +（可带「临时」标）+ **完整网址**；**整行点击新标签打开**；**悬停浮出功能说明**；行尾悬停才出 **★置顶 / ✎编辑 / ✕删除**；可**拖动排序**；**+ 新增**带取色器 + 8 个预设色块。
- **存服务器** `~/stack/remote/sites.json`，读写走**已有**的 `/api/remote/sites`（实现在 `remote-api.py`）—— **零基础设施改动**（Caddy 的 `handle_path /api/remote/*` 与 systemd 的 `ReadWritePaths=/home/ubuntu` 都已覆盖）：**没动 Caddyfile、没开端口、没加服务**。
- 种子 9 条首次自动写入（Hub / 管家终端 / 三个 claude / shell / code-server / Gitea / 六号接入页）；`preview-*.html`（夜间小工程预览页）由后端**自动发现**成只读灰条，文件出现/删除即自动增减。
- **安全**：`url` 只收 `http(s)://` 或以 `/` 开头（挡 `javascript:` / `data:` / `//evil`）；`color` 只收 `#RRGGBB`；所有文字一律 `textContent`。
- **坑**：`const RAPI='/api/remote'` 是声明在「本机操作」那个 IIFE **里面**的，新模块的作用域**取不到** —— 得自己再声明一个（我第一版就栽在这：页面一直显示「读不到站点清单」，可手动 `fetch` 却是 200）。
- **加新 tab 的稳妥做法（可复用）**：新 tab 只要 `data-tab` **不是** `butler` / `local`，切 tab 就**不会**走 `moveChatPane` / `switchChatPane`，也就**不会**触发 `switchChatPane` 的 else 分支 `clearChat()`（那会把管家正在进行的对话清空）—— 「站点」与「编码」同属**安全类型**。另：CDP 里 `element.click()` **不是**用户手势，`target=_blank` 可能被当弹窗拦掉；要验真点击得用 `Input.dispatchMouseEvent`。

### 新增 / 改动的服务与文件（服务器）
| 项 | 说明 |
|---|---|
| `guga-term-api.service` | `:8791`，管 claude 的 tmux 窗口（Caddy `/api/term/*`） |
| `~/stack/term/term-api.py` | 上面那个小服务的实现（`/list` `/new` `/select` `/kill`） |
| `~/stack/term/ttyd-run.sh` | 参数化 ttyd 启动器（`TTYD_ACCENT`/`TTYD_GOLD` 配主题色） |
| `ttyd-shell` | `:7683`（`/shell`），workspace 里的 shell |
| `~/.tmux.conf` | 深色状态栏 + `mouse on` |
| `~/.local/share/code-server/User/settings.json` | VS Code 深色主题 + 默认打开 workspace |

> ✅ **已清理（2026-10-12）**：`ttyd-claude2/3`（7684/7685）已 **stop + disable**，Caddy 的 `/claude2` `/claude3` 路由已删，孤儿 tmux 会话 `claude-2` `claude-3` 已杀。它们是早期"预建多个终端"方案的产物，早被 `guga-term-api`（tmux 窗口）取代。
>
> ⚠️ **顺手踩到的坑（值得记牢）**：删完路由 `/claude2` 仍是 302 —— 因为 **`handle /claude*` 是前缀匹配，把 `/claude2` 也悄悄兜住了**。改成 `handle /claude` + `handle /claude/*` 两个**精确**匹配才真正 404。
> ⚠️ **更隐蔽的坑**：改完 Caddyfile 后 `caddy reload` **不生效** —— 宿主文件与容器里的 `/etc/caddy/Caddyfile` **inode 不同**（编辑工具是"写新文件再改名"，换了 inode，而 **Docker 单文件 bind mount 钉在旧 inode 上**）。容器一直读到旧内容。**必须 `docker compose restart caddy`** 让它重新解析挂载 —— 这就是"改后须重启 caddy"那条经验的真正原因。**判断方法**：`stat -c %i` 比宿主与容器的 inode，或直接问 Caddy admin API（`curl localhost:2019/config/`）看真正生效的路由。

### 试过但撤掉的
- **像素版咕嘎头像**（拿参考图做的）：试放在空状态 / 切换条，最终**撤掉**，未采用
- 想改 **Claude Code 启动 logo**：那是二进制里写死的块画、无开关 → **决定不动二进制**

---

## 已完成 ✅（累计）

| 项 | 说明 |
|---|---|
| 服务器加固 | `ufw` 只放 22/80/443 + `fail2ban` |
| 交互外壳 | `http://localhost:8080/` —— 顶栏 **四个 tab**：咕嘎一号 / 编码 / 本机操作 / **站点** |
| **咕嘎一号** | Hermes 管家，自建聊天 UI（会话列表 + 流式 + 工具卡片 + 停止 + 错误/空态） |
| 咕嘎一号人设 | 自称「咕嘎一号」、每次回复以「咕嘎」开头、已同步用户资料 |
| **编码** | **深色 VS Code Web（code-server）** ＋ **可多开、可切换、可删除的 claude 终端** ＋ workspace shell 终端 |
| 代码托管 | **Gitea**（`127.0.0.1:3000`，管理员 `guga`） |
| 工具 | 待办 / 定时任务 / 浏览器（Chromium）/ 终端 / 文件 / 联网 / 记忆 |
| 视觉 | 靛紫主色 + 暗金点缀 + 极淡光晕 + 面板微透明 + 内联 SVG 图标 |
| **远程操作（自有机器）** | 服务器经 SSH 操作自有 Windows 笔记本：NAT 反向隧道 + 受限入站账户 + 保活；咕嘎可用自然语言驱动 |
| **「本机操作」页** | hub 第③ tab：**左机器列表 + 右上咕嘎 + 右下命令框**；**只读直跑、写/危险先确认**；两条可拖拽分隔线（`localVP`/`localHP`） |
| **「+ 接入」模块** | 列表头的「+ 接入」：自动生成接入步骤 + 端口自动分配；把新机器打印的登记信息**粘回**即拼成给咕嘎的一句话 |
| **咕嘎编号** | 一号=服务器（**不列在机器列表**）/ 二号=飞书(停用) / 三号=WorkBuddy / 四号=LightVela / **五号=ASUS 笔记本** / **六号=以后其他机器（统一归六号，不递增）** |
| **远程操作独立记忆** | 别人的机器那侧走**独立 Hermes profile**：自己的记忆、自己的会话，与管家**共用技能与工具**（用户明确："我是大管家，看得到所有记忆"） |
| **咕嘎六号（别人的机器）** | 网页授权接入**全链打通**：常驻入口（谁都能打开）+ **连接密码** + 点同意出一次性命令 + 反向隧道 + **关网页约 2 分钟自动断开**（心跳租约 + 目标机看门狗）；服务器零残留、操作记录写回**对方机器本机**；真·Windows 实测通过 |
| **站点地图** | hub 第④ tab：本网站所有页面入口的清单 —— **自选颜色点 + 完整网址 + 悬停说明 + 点击跳转**，可增删改 / 置顶 / 拖动排序；存 `~/stack/remote/sites.json`（零基础设施改动） |

### 咕嘎一号的"家"（服务器上）
- 人设：`~/.hermes/SOUL.md`（名字 + "以咕嘎开头"规矩）
- 用户资料：`~/.hermes/USER.md`（孟庆达 / 目标 C++ 后端 / 当前**准备实习**）
- 记忆、技能、定时：`~/.hermes/` 下

---

## 访问方式（本机 Windows）

双击 **`启动隧道.bat`** → 浏览器打开：

| 地址 | 是什么 |
|---|---|
| **http://localhost:8080/** | 外壳（咕嘎一号 / 编码） |
| http://localhost:3000/ | Gitea |

---

## 关键目录（服务器上）

| 路径 | 是什么 |
|---|---|
| `~/workspace/` | 你的代码工作区（VS Code / claude / shell 都在这里） |
| `~/stack/` | 部署配置（`Caddyfile`、`docker-compose.yml`、`hub/` 前端、`term/` 终端脚本、`docs/` 文档） |
| `~/.claude/` | 编码内核配置（`settings.json` = DeepSeek 配置） |
| `~/.hermes/` | 咕嘎一号（`SOUL.md`/`USER.md`/`.env`/`config.yaml`/`memories`/`skills`/`cron`） |
| `~/.tmux.conf` | tmux 深色状态栏 + 鼠标滚轮 |
| `~/stack/remote/` | 功能③：`hosts.json`（自有机器清单，**只含自有**）+ `gen-config.py`（生成 ssh 别名）+ `onboard-windows.ps1`（可参数化 `-Port`）+ `remote-api.py` |
| `~/stack/remote/memories/` | 每台机器的**专属记忆**（`<别名>.md`）；在本机操作页聊天时作为 `instructions` 临时注入 |
| `~/stack/remote/sessions.json` | 机器 → 它自己那段对话的 id（和管家页、其他机器互不干扰） |
| `~/stack/remote/sites.json` | **「站点」tab 的清单**（自己登记、可拖动排序；后端自动附上 `preview-*.html` 只读灰条） |
| `~/.hermes/profiles/remote/` | **远程操作的独立 profile**（空记忆、独立会话、自己的 SOUL；`skills/` 软链到 `~/.hermes/skills` **共用技能**） |
| `/opt/guga-join/` | **P7 的 join 服务**（`join_api.py` + 给对方跑的三份模板）；账户 `gugajoin`，`~` 都读不到 |
| `/run/guga-join/` + `/usr/local/bin/guga-join-keys` | 一次性隧道密钥的 **tmpfs** 落点 + 给 sshd 读它的 helper（`AuthorizedKeysCommand`） |
| `/var/lib/guga-join/password` | 常驻接入页的**连接密码**（走 systemd `StateDirectory`；**留空/删掉 = 不设密码**）——**不能放 `/etc/guga/`**，那里归 root 且含 admin 密钥 |
| `~/stack/hub/join.html` | 对方看到的**同意页**（「咕嘎六号请求访问」） |
| `~/stack/docs/feature3-plan.md` | 功能③ **P0–P7 全量施工图**（P7 = 别人的机器网页授权接入） |
| `~/.ssh/` | `guga_ops`（服务器→目标机密钥）、`config`（连接复用/保活）、`config.d/guga-remote`（生成的别名） |
| `/etc/guga/` + `/etc/ssh/sshd_config.d/60-guga-tunnel.conf` | 反向隧道受限入口（`tunnel` 账户，只能绑回环端口） |

---

## 服务清单（服务器）

| 服务 | 端口 | 作用 |
|---|---|---|
| `code-server@ubuntu` | 8081 | 编码（VS Code Web，深色） |
| `guga-term-api` | 8791 | claude 的 tmux 窗口管理（`/api/term/*`） |
| `guga-remote-api` | 8792 | 「本机操作」后端（`/api/remote/*`）：机器列表 + 命令执行 + 确认门 |
| `guga-join-api` | 8793 | **咕嘎六号：别人的机器·网页授权接入** —— 唯一准备挂公网的服务（账户 `gugajoin`，状态只在内存 + `/run/guga-join` tmpfs）。常驻入口 + **连接密码** + **心跳租约**（`LEASE=130`，页面一关约 2 分钟自动撤销） |
| `guga-jiaxin-api` | 8794 | 《我的夹心》数据接口（`/api/jiaxin/*`）：整包读写 `jiaxin_service/data.json`，网页改动自动保存 |
| `ttyd-claude` | 7682 (`/claude`) | claude 网页终端（tmux 会话 `claude`） |
| `ttyd-shell` | 7683 (`/shell`) | workspace shell |
| `hermes-gateway` | 8642 | 咕嘎一号的 API（外壳聊天调它） |
| `hermes-todo-api` | 8790 | 待办/收件箱/系统信息 API |
| `ttyd-hermes` | 7681 (`/hermes`) | 网页终端（回退） |
| docker `caddy` | 8080 | 反代 + 托管外壳 |
| docker `gitea` | 3000 | 代码托管 |

---

## 待办 ⏳

1. **域名 `dqmguga.site`**：已注册 + 已实名 ✅ → **已提交 ICP 备案（审核中，1–3 周）**
2. **备案通过后**：DNS 加 `@` / `git` 两条 A 记录 → `106.55.38.108`；Caddy 切**绑域名 + 自动 HTTPS**。**另开 `https://join.<域名>` 站点时，白名单要含 `/api/join/connect`、`/alive`、`/heartbeat`、`/claim`、`/status`，绝不放 `/settings`（它返回密码明文）**
3. **认证**：对外前**必须**加 密码 + TOTP
4. **功能③**：远程操作其他电脑 —— **自有机器 ✅**（`win-asus` = 咕嘎五号）；**「本机操作」页 ✅**；**「+ 接入」✅**；**P7「别人的机器·网页授权接入」✅ 服务器侧 + 真机全链都验过了**（`guga-join-api` + 同意页 + **常驻入口** + **连接密码** + **关网页自动断开**；真·Windows（五号）实测撤销 10 秒 / 关网页 2 分钟拆干净）；**只剩最后一步** → **公网 HTTPS 那条链（等备案 + 域名）**；**另待做**：执行沙箱（`gugaops` 专用身份）、远端网页终端、**限流**（主人当前选择「不加」，17 个 guest 端口可被刷满）
5. 编码页：VS Code 右侧那条空面板（存浏览器本地，点它 ✕ 关一次即可）
6. **两层入口导航** 💡*（想法，未实现）*：首屏第一层选「咕嘎管家 / 远程连接 / 后续新增」；选「咕嘎管家」→ 第二层选「管家 / 编码（当前界面即可）」；选「远程连接」→ 操作提示页。**「远程连接」＝「本机操作」（同一件事，已确认）**。详见设计文档「两层入口导航」节。
7. **管家 / 编码 每日 token 分开计** 💡*（想法，未实现）*：现在顶栏 token 是合并的一个数（基本只含管家侧）；目标两模式各算各的。**待查明编码侧（Claude Code）用量从哪取**。详见设计文档「管家 / 编码 · 每日 token 分开计」节。

---

## 备忘 / 提醒

- ⚠️ **咕嘎一号有 `terminal`，能改服务器配置**。基础设施（Caddy/DNS/端口）改动建议先确认，否则会互相打架。
- ⚠️ **改 `Caddyfile` 后必须 `docker compose restart caddy`，`reload` 不管用** —— Caddyfile 是**单文件 bind mount**，编辑工具换 inode 后容器仍钉在旧 inode 上。**依据**：`stat -c %i` 宿主 vs 容器，或 `curl localhost:2019/config/` 看实际生效的路由。改前先 `caddy validate`。
- ⚠️ **Caddy 的 `handle /xxx*` 是前缀匹配** —— `handle /claude*` 会把 `/claude2` 也兜住。要精确就用 `handle /x` + `handle /x/*` 两条。
- **备案期间铁律**：别在 80/443 开站、电话畅通、别让咕嘎一号碰域名/DNS/Caddy。
- 模型：DeepSeek（`deepseek-flash`）。编码配置在 `~/.claude/settings.json`；咕嘎一号在 `~/.hermes/.env`。
- Gitea 管理员 `guga`（密码当时已给出，**建议改掉**）。
- 本机 `C:\Users\ASUS\.claude` 是**本机** Claude Code，和服务器无关。
