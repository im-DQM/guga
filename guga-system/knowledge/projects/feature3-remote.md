# 项目：功能③ 远程操作（含接入新机器与咕嘎六号）

技能：`remote-ops`。图纸：`~/stack/docs/feature3-plan.md`。

## 一、自有机器（已通 ✅ 2026-10-10）

服务器保持 `terminal.backend=local`，多主机靠 **ssh 别名**——真相 `~/stack/remote/hosts.json`（只含自有机器），`~/stack/remote/gen-config.py` 生成到 `~/.ssh/config.d/guga-remote`，故 `ssh <别名>` 直接可用。

首个 `win-asus` ＝ 咕嘎五号（我的 ASUS 笔记本，NAT 后 → 反连隧道把自身 22 挂到服务器回环 22022），**`ssh win-asus "命令"` 即落到笔记本执行**。接入脚本 `~/stack/hub/onboard-windows.ps1`（可经 hub 下载）。

## 二、接入新机器（流程）

「远程连接」页左侧有 **「+ 接入」**按钮 → 面板自动生成步骤（Windows/Linux 两套，端口自动推荐，含服务器 ops 公钥），把新机器跑完打印的那段**粘回去**，它就拼出「给咕嘎的一句话」+ 复制按钮。主人把这句话贴给我，**我按 `remote-ops` 技能的「接入新机器」节登记**：

写 `/etc/guga/tunnel_authorized_keys` 限制键 → `hosts.json` → `gen-config.py` → `ssh -o ConnectTimeout=8 <别名> hostname` 验证。

坑：`permitlisten` 写 `localhost`（**不是** 127.0.0.1）、key 文件权限 `640 root:tunnel`。端口 22022–22025/22022–22039 已放行，超出要改 `60-guga-tunnel.conf` 的 PermitListen 再 reload ssh。`onboard-windows.ps1` 已参数化：`-Port`（每台机必须不同）。

## 三、咕嘎六号：别人的机器 · 网页授权接入（P7，服务器侧已跑通 + 真机实测 ✅）

对方在自己机器上打开一个网页点【同意】→ 那台机器连到服务器 → 被咕嘎六号协助。

落地物：
- 服务 `guga-join-api`（`/opt/guga-join/join_api.py`，`:8793`，系统账户 `gugajoin`，**读不到 `~/stack`**）—— 全系统**唯一准备挂公网**的东西
- **关键招**：sshd 的 `Match User tunnel` 里加 `AuthorizedKeysCommand /usr/local/bin/guga-join-keys %u` → 一次性隧道公钥只写在 **`/run/guga-join/authorized_keys`（tmpfs）**，**不用 sudo、不放宽服务硬化**，服务停/机器重启即空；`PermitListen` 已扩到 **22022–22039**
- 同意页 `~/stack/hub/join.html`；发起端 = 「远程连接」页机器列表头的 **「邀请」** 按钮
- **join.html 的视觉 2026-10-13 改版**（主人点头上线）：加了「① 选权限 → ② 跑命令」步骤条、权限从胶囊换成带说明的选项卡、密码框/同意按钮重做、命令块做成终端样式（带复制按钮）、状态条呼吸点、撤销按钮收成红色态、手机端（390px）适配。改前备份 `hub/join.html.bak-20261013_124141-joinredesign`，一键还原 `~/stack/backups/restore-before-join-redesign.sh`，草稿留 `~/.hermes/previews/preview-20261013-join-redesign.html`。**只动了 CSS/静态标记与一行 `#osLabel` 文案**，签 token / 心跳 / 轮询逻辑一字未改。
- **五号/六号分开**：六号在列表里标「临时」，有**自己那段对话**（不与五号共用）；但它**只活这一次**——撤销时连同会话一起删（实测撤销后 404），且**无专属记忆文件**。guest 的命令走 `/api/join/exec` + `/approve`（一律先确认；只读模式下写/危险 403）
- Caddy `handle_path /api/join/*`（注入 `X-Guga-Join-Admin`，密钥 `/etc/guga/join_admin_secret`）
- **公网那半已上线（2026-10-13，备案通过）**：`https://join.dqmguga.site` 免密但只白名单 —— `POST /api/join/{connect,heartbeat,claim,revoke_self}`、`GET /api/join/{status,alive}`、`GET /join/onboard*`、`/join/offboard*`、join 页本身（`/`、`/join`、`/join/`、`/join.html` 都重写到 `join.html`），兜底 `respond 404`；**绝不放** `/settings`（明文密码）、`/create`、`/guests`、`/exec`、`/revoke`（这几条只在私网站点，靠 Caddy 注入 admin 头）。公网用 `uri strip_prefix /api` 后再转 8793。join API 对外链接基址 = `GUGA_JOIN_BASE`（systemd 里已设成 `https://join.dqmguga.site`）。
- **`revoke_self`（2026-10-13 主人要的）：页面「断开并撤销」点一下就真断**。带自己那串令牌就撤自己这次连接：`POST /api/join/revoke_self {"t":<页面 token>}` → 校验 token → `_do_revoke(gid, why="对方在接入页点「断开并撤销」")` → 钥匙作废，隧道由目标机看门狗十几秒拆掉；**刻意不要求 admin**（令牌就是这次连接的凭证，只碰得到自己那一份），令牌无效一律 404 不泄漏。重复点返回 `revoked:false` 也算成功。页面上原「给条命令自己跑」降级成后路（成功后出现小按钮「跑不了？改在本机跑这条命令」；接口不通时自动回落到它）。
- 自测通过（拿服务器自己当"对方机器"）：签发→claim→密钥进 tmpfs→只用它建反向隧道成功→端口绑上→页面 connected→撤销后 key 行数 0、无残留

踩过的两个坑（已修）：`_token_state` 返回的是**副本**，写回要用 `_tokens[tok]` 否则 token 不是一次性；`_key_fingerprint` 对带 options 的 authorized_keys 行要取**类型字段之后**那个（`parts[2]`），取 `parts[1]` 会拿到 `ssh-ed25519` 导致撤销删不掉 key。

## 四、常驻入口：连接密码 + 关网页自动断开（2026-10-11 主人要的）

`/join.html` **不带 token 打开 = 常驻入口**：页面自己调 `POST /api/join/connect` 现场签一个 token —— **谁都能打开、点【同意】就把自己那台电脑接进来**。主人明确选的三条：**不设放行门**（对方点同意就直接连）、**不加限流**、**公网那半等备案**。页面本身永不过期；token 仍是 10 分钟一次性，拖过头了常驻页会**自动换一条新命令**让他重跑。带 `?t=` 来的（「邀请」面板生成的那条）走**老路**，一字未改。`/connect` **刻意不要求 admin**（备案后公网只白名单 `/connect` + `/claim` + `/status`）。

两条规矩：**① 连接要先输密码；② 关掉网页约 2 分钟后自动断开。**

- **密码**：`/var/lib/guga-join/password`（首次启动自动生成 6 位，去掉 i l o 0 1 这些易混字）。**只管常驻入口**——直接开 `/join.html` 要输；带 `?t=` 的邀请链接是链接本身当凭证，不用输。在「远程连接」页**左侧栏最底下那块「接入页」**里可看可改可随机换（`#localGate`，常驻可见），**留空 = 不设密码**。回车即保存。服务端 `/connect` 用 `secrets.compare_digest` 校验。密码文件不能放 `/etc/guga/`（root + admin 密钥）→ 用 systemd `StateDirectory=guga-join`（自动建 `/var/lib/guga-join` 并进 ReadWritePaths）。
- **租约**：`LEASE=130` 秒。接入页开着就每 20 秒 `POST /api/join/heartbeat` 续租；服务端 `_sweeper` 线程每 10 秒扫一遍，租约一过就 `_do_revoke`。所以**关掉页面 ≈ 2 分钟后**服务器撤销会话。
- **真正拆隧道的是目标机**：服务器杀不掉已建立的隧道（连接跑在受限账户 `tunnel` 名下，join 服务只有 `gugajoin`，也不是 root）。onboard 脚本的保活循环「边连边盯」——每 15 秒问一次 `GET /api/join/alive?t=`，服务器说 `no` 就 kill 隧道 + 移除 ops 公钥 + 停掉保活。`alive()` **只有在服务器明确回 `no` 时**才算会话没了；curl 失败一律当「还活着」。撤销 → 目标机拆干净 ≈ 十几秒。
- 页面细节：常驻 token 存 **sessionStorage**，刷新页面不用重来（关标签页即清）。
- 测试脚本（可复用）：`/tmp/watchdog-test2.sh`、`/tmp/join-page-test2.mjs`、`/tmp/invite-test.mjs`。
- ⚠️ 备案后公网白名单（`feature3-plan.md §10.7`）要包含：`/api/join/connect`、`/api/join/alive`、`/api/join/heartbeat`、`/api/join/claim`、`/api/join/status`。**千万不要**放 `/settings`（它带密码明文，只给 hub 用）。

## 五、六号 token 安全模型（2026-10-11 主人问、我复核、拍板**不改**）

主人问：「先输密码后给连接命令，那他下次不是可以直接复制这个命令从而绕过密码了？」**结论：不会。** 命令里带的是 token，**一次性**（`_claim` 要求 `state=="waiting"`，连上后变 `claimed`，再跑 410）+ **10 分钟过期**（`TTL=600`）；新 token 只能由 `/connect` 发，`/connect` 要密码 ⇒ **重连必须重新打开页面 + 重输密码**。

**残余风险（已知、已接受）**：命令本质是**短命 bearer 凭证**——谁拿到它能在 ≤10 分钟内、一次、不输密码地连进来；同标签页刷新也能免密回到命令（token 存 sessionStorage，是**有意**设计，关标签页即清）。**将来若反悔**：① `TTL` 改 120（零代价，窗口缩 5 倍）；② `/connect` 记下浏览器 IP、`/claim` 要求同 IP（转发即失效，但「手机开页面、电脑跑命令」会误伤，且**只能对常驻入口做**）。复核记录存 `~/.claude/plans/splendid-shimmying-peacock.md`，技能 `remote-ops` 也补了这节。

## 六、真机验证记录：Windows 目标机（2026-10-11，拿咕嘎五号当 guest 实测）
用**主人真会走的那条路**跑的：计划任务里 `irm 'http://localhost:8080/join/onboard?t=…' | iex`（**不是 `-File`**，避免 BOM/编码问题；五号的 `Host dqm` 里有 `LocalForward 8080`，所以它 `localhost:8080` 真能到服务器）。全链通过：接入 → connected → 撤销后**10 秒内**隧道进程归零、公钥行归零、**计划任务已注销**，且五号自有通道不受影响。

同时在真机上验证：**命令先记进对方本机 `~\.guga\audit.log` 才执行**。

Windows 侧四个真机坑（详见 `../procedures.md §3、§4`）：
1. here-string 里 `$false` 被插值成 `False` → 计划任务永远注销不掉（原版 bug，五号上一直挂着旧任务）
2. `Stop-ScheduledTask` 停的就是脚本自己 → 必须放最后；注销任务放最前
3. 每次 join 装的是**当场的临时 ops 公钥** → 旧公钥累积（五号上攒了 5 条）
4. 我曾用 `-notmatch 'guga-join'` 清 authorized_keys，把自有机器那条 `guga-ops@cloud` 也删了（五号通道断掉，还被 ControlMaster 骗着没发现）；ASUS 属管理员组，钥匙在 `C:\ProgramData\ssh\administrators_authorized_keys`（**不是**用户级目录），修 ACL 用 `icacls /inheritance:r /grant Administrators:F /grant SYSTEM:F`

五号上跑完已全部清干净（`C:\guga` 空、无 guest 公钥残留、无计划任务），自有通道用新连接复验通过。

## 七、五号掉线怎么判、怎么恢复（2026-10-12 实战）
**判据（服务器侧，一条命令）**：`ss -ltn | grep 22022` —— 没有监听，且 sshd 日志里近十几分钟**根本没有它的连接尝试** ⇒ 隧道没起（笔记本关机/睡眠，或保活计划任务没在跑）。
注意：**只有任务在跑（State=Running）却连不上**，才怀疑密钥/端口配置；`Get-ScheduledTask` 显示 **Ready** 说明进程一起来就退了（脚本没了 = 上次清 `C:\guga` 的后遗症）。

**恢复**：在笔记本上（管理员 PowerShell）`Start-ScheduledTask -TaskName guga-tunnel`；任务已不存在或脚本丢了，就从 hub 重下 `onboard-windows.ps1` 跑一遍（幂等，密钥复用，服务器侧登记不用动）。

**服务器侧自查（确认不是我们这边的问题）**：`sudo cut -d' ' -f3- /etc/guga/tunnel_authorized_keys`（能看到 `guga-tunnel-<机器名>` 注释）＋ `sudo grep PermitListen /etc/ssh/sshd_config.d/60-guga-tunnel.conf`（端口段含 22022）。
五号：`listen_port=22022`、`user=ASUS`（在 `~/stack/remote/hosts.json`）。

## 九、粘到 PowerShell 的命令别带引号、别带 &（2026-10-13 真机踩到两次）

主人 2026-10-13 在 Windows 上跑接入命令连栽两次，两次都是命令字符串被解析错：

1. 老写法 `…SecurityProtocol='Tls12'; irm 'https://…&os=win&mode=read' | iex` → PowerShell 报
   `无法将“Tls12”项识别为 cmdlet`（那一对单引号在粘贴/输入法环节被吃掉／变形，Tls12 变成待执行命令名），整条 `-Command` 直接没跑。
2. 去掉引号后又炸第二次：**裸 URL 里的 `&`** 是保留运算符 → `不允许使用与号(&)`。
   （教训：不是「引号一律不要」，而是「**URL 里不能有 `&`，才可能完全不用引号**」。）

现在的做法（`hub/join.html` 的 `buildCmd()` / `manualOffboardCmd()`）：
**os/mode 放进路径，token 走查询串，整条 URL 不含 `&` → 命令里一个引号都不用**：

```
powershell -NoProfile -ExecutionPolicy Bypass -Command "[Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12; irm https://join.dqmguga.site/join/onboard/win/read?t=<token> | iex"
```

- 服务端同步认两种写法（`join_api.py` 的 `do_GET`：`/onboard/<os>/<mode>?t=` 与老的 `?t=&os=&mode=`，输出一致），
  **Caddy 不用改**——`@onboard path /join/onboard*` 早就把子路径一起放行了。
- 顺手修了 `detectOS()` 返回 `mac` 但服务端只认 `sh/linux/macos` → Mac 拿到 Windows 脚本的老 bug。
- 结论规矩：**凡是给主人复制去别处跑的命令，URL 里不要出现 `&`**，这样就能做到零引号；非要带参数就塞路径段。

**再补一层：页面自己认旧版（2026-10-13）** —— 光改服务端没用，主人那次就是拿着浏览器缓存里的旧页面复制的命令。
`join.html` 现在带 `const BUILD='…'`：①品牌栏右侧显示版本号；②命令框下方常驻一行提示「命令里不该出现 &，出现了就是旧页面，Ctrl+F5 强刷」；
③加载时用 `fetch('join.html?nc='+Date.now(),{cache:'no-store'})` **把服务器上这份抓回来对版本号**，不一致就顶上弹一条琥珀色横幅
「你打开的是旧版页面（服务器上已经是 vX）…按 Ctrl+F5」。
⇒ **动过 `hub/join.html` 就必须同步改 `BUILD`**，否则所有人（包括主人）打开新页面都会被自己误报成旧版。
实测方式（已跑通）：同源 `document.write` 一份把 BUILD 改成旧值的副本 → 横幅正常弹出、版本号显示 `v… · 旧`。

### 同一台机器还栽在「执行策略」上（2026-10-13）

那台 Windows 第 1 步下载完 OpenSSH 后卡在
`iex : 无法加载文件 C:\Program Files\OpenSSH\OpenSSH-Win64\install-sshd.ps1，因为在此系统上禁止运行脚本`（`Invoke-Expression…PSSecurityException`）。
即使用 `-ExecutionPolicy Bypass` 启动，若**执行策略是组策略锁的**（MachinePolicy/UserPolicy），Bypass 也无效 → 任何「加载 .ps1 文件」的步骤都会失败。

`onboard-win.ps1` 已改成**尽量不碰 .ps1 文件**：

- 开头先 `Get-ExecutionPolicy -List` **把策略表打出来**（排错全靠它）。
- 第 1 步**优先用系统能力包** `Add-WindowsCapability -Online -Name 'OpenSSH.Server~~~~0.0.1.0'`（装完服务自带，不执行任何脚本）；
  只有它不成才退到解包 zip，并且把 install-sshd 的失败原样报出来（不再静默）。
- 装服务器公钥时的**审计包装器**、以及**保活反向隧道的计划任务**，都从 `-File xxx.ps1` 改成
  `-EncodedCommand <base64>`（UTF-16LE）**把代码内联**——不加载文件，执行策略锁死也照跑。
  `.ps1` 原文仍写盘一份（`C:\guga\*.ps1`）方便人看，但不再是执行入口。
- `ssh-keygen` 改成先解析绝对路径，找不到就明确报错（原来裸调 `ssh-keygen` 失败也不吭声）。

## 八、咕嘎六号：接入记录官（常驻 · 2026-10-13 主人要的）

主人原话：「六号，连接过谁、干过什么、怎么连接都由他记录，也设置成一个常驻咕嘎。」
同期定的分工：**接入这摊归六号；五号只记它自己那台笔记本（ASUS）的工作与改动**，两边不串。

**取数口（新加的）**：join 服务原来什么都不落盘（内存态）。`join_api.py` 里加了 `_audit()`，
往 `/var/lib/guga-join/log/access.jsonl` 追加一行一条 JSONL，埋了 6 个点：
`connect`（带 `how`=常驻入口/邀请链接、`client`=对方出口 IP）、`disconnect`（带 `why`、`lasted_s`）、
`exec_request`、`exec_ran`（带 `exit_code`/`duration_ms`）、`exec_denied`、`exec_blocked`。
- ⚠️ **`_audit()` 必须在 `_lock` 之外调用**（`_lock` 不可重入，锁内调用会死锁）。
- 改前备份：`~/stack/backups/join_api.py.bak-*-accesslog`；改完 `py_compile` + 重启 `guga-join-api`。
- 读权限：`/var/lib/guga-join` 改 711、`log/` 归 `gugajoin:ubuntu` 2750、`access.jsonl` 640 —— ubuntu（六号）能读，别的用户进不来；`password` 仍是 600。

**六号本体**：家 `~/.hermes/guga6/`（`SOUL.md` 身份规矩 / `MEMORY.md` 常客与坑 / `journal/<日期>.md` 人话流水 /
`events.jsonl` 原样流水 / `machines.md` 台账 / `state.json` 读偏移）。
记账手 `~/.hermes/scripts/guga6_watch.py`（systemd `guga6-watch.service`，20 秒一轮）：
读新流水 → 写日记/台账 → **有人接进来、断开、命令跑失败** 时在咕嘎群说一句（别的都不出声）。
自检：`GUGA6_NOSAY=1 python3 ~/.hermes/scripts/guga6_watch.py --once`（不发群，只走流程）。

**群里怎么找它**：咕嘎群里点名「六号」→ 群信使给它开自己的会话（`api_…`，key `guga6`），
它照自己的流水/台账答（时间、机器、权限、怎么连的、跑过什么、成没成），账上没有就说没有。**它不进"全体回"名单**（没人接入时它没什么可说的）。

**五号那半**：`~/.hermes/scripts/machine_journal.py`（`--add` 手记 / `--read` 看）→ 日志
`~/stack/remote/journal/<alias>.md`。
**只在"被叫去干活"时记一笔**（主人 2026-10-13 定的）：叫它干活、干完当场记一条；日常只读查看不记；
**不要定时搬**——原来那条每 15 分钟从审计里搬「写/危险命令」的 cron（`machine-journal-auto`）已按主人要求撤掉
（`--auto` 能力留着，默认不用）。
规矩写进了那台机器的记忆文件 `~/stack/remote/memories/win-asus.md`，所以无论在群里还是在 hub 的
「本机操作」页，五号分身都会照它记。

## 十、接入一台机器的标准动作（2026-10-13 沉淀成流程）

10-13 那天从 18:00 摸到 21:00 才把「六号接入」这一串收干净，教训是**顺序不对**：先发命令、再一条条查，
中间隔着一台别人的机器，一次来回十几分钟。以后照这个顺序走：

1. **先体检，再发命令**：`bash ~/.hermes/skills/devops/remote-ops/scripts/join-preflight.sh [read|full]`
   —— 服务 / token / 页面版本 / 脚本内容 / 权限真源 / 离线包哈希 / 模板语法 / 命令形态 一次查完，
   **末行就是可以发给对方的那条命令**（全绿才发）。
2. 对方在**管理员 PowerShell** 里粘一次就够（脚本自己走 6 步：装 sshd → 放行防火墙 → 设默认 shell →
   生成隧道密钥 → 向服务器登记 → 装公钥 + 起保活反向隧道）。
3. **权限接入后也能改**：接入页上点「改成完整协助」立刻生效，不用重跑命令（令牌说了算，见第七节那串）。
4. 想确认状态：`bash …/scripts/guest_cmd.sh`（无参＝列名单：谁、哪台、在线否、什么权限）；
   流水 `sudo tail -f /var/lib/guga-join/log/access.jsonl`（出现 `connect` 才算真接上，六号读的就是它）。

这一串上 10-13 修掉的四处（都在服务端，**对方不用做任何事**）：

- 权限的真源改成**令牌**：网址里写的、脚本正文里写的都不算数 → 手改命令换不来更高权限；
- 接入页**记住并显示**权限：刷新不再悄悄回落到「只读」，「跑命令」那页可一键切换（原来主人看到的
  「不管对方选什么都是只读」就是这个）；
- 发给对方的命令 **URL 里零 `&`、命令里零引号**；离线安装包改成**自家服务器直发 + sha256 校验**，
  不再等 GitHub / 微软更新源（那俩在国内会挂死十几分钟且不报错）；
- 目标机**执行策略被组策略锁死**时，装 OpenSSH 自动回落到「读原文、内存里跑」的内联执行（不加载 .ps1）。

细节、报错→处置速查表、以及「一条命令一次机会（token 600 秒 / 服务重启即清）」这些：见
`~/.hermes/skills/devops/remote-ops/references/windows-onboard.md`。
