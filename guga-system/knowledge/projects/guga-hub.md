# 项目：hub 网页外壳（咕嘎的正面）

## 结构

前端 `/home/ubuntu/stack/hub/index.html`（docker caddy :8080 静态提供，`./hub:/srv:ro`），`/api/hermes/*` 反代 api_server:8642；systemd 服务 `hermes-todo-api.service`（`todo_service/todo_api.py:8790`）反代 `/api/todos*`、`/api/inbox*`、`/api/sysinfo*`、`/api/usage*`。**Caddyfile 是单文件挂载，改后须 `docker restart caddy`；`hub/` 内文件实时生效。** `sudo` 免密。技能：`guga-hub`。

**公网入口（2026-10-13 备案通过后）**：`https://dqmguga.site` / `www` 就是这套 hub；`:8080` 私网站点一字未改，只走隧道（**免密 —— 也是门卫出问题时的后门**）。Caddyfile 里公共路由抽成 `(huproutes)` 片段供两个站点 `import`。

**公网登录门卫（2026-10-13 晚，替掉了浏览器原生 `basic_auth`）**：整站走 `forward_auth` 打 `127.0.0.1:8790/api/gate/verify`（实现在 `todo_service/todo_api.py` 的「门卫」一节），没通过就由门卫**直接回 302** 到自己的登录页 `/login.html?next=…`（`handle_errors` 抓不住 forward_auth 传回来的非 2xx，所以让门卫自己发 302）。登录页 POST `/api/gate/login` 换一个 HMAC 签名 cookie `guga_gate`。两个账号（`~/.hermes/secrets/hub-gate-users.json`，只存 pbkdf2 哈希；密钥 `hub-gate.key`）：
- `mqd` → cookie 带 `Max-Age` 10 年，**长期免再验证**；
- `guga` → 会话 cookie（无 `Max-Age`），**关掉浏览器即失效**，页面也不让浏览器存账密（`autocomplete=off`）。

密码框**不显示原点**：输入框里是每次击键重掷的随机字符，真密码只存在页面 JS 变量里（`beforeinput` 拦截，覆盖打字/粘贴/输入法），发出去的是变量而不是输入框的值。`/api/gate/*` 已加进 `(huproutes)`（私网站点也能用，方便测）。备份与一键还原：`~/stack/backups/Caddyfile.bak-*-pregate`、`todo_api.py.bak-*-pregate` + `backups/restore-before-login-gate.sh`。

## 顶栏与 tab

顶栏：血条（DSK/MEM/SWP）+「今日 tok·$」徽章（`/api/usage`）。

tab 四个：咕嘎一号 / 编码 / **远程连接** / 站点。

> 2026-10-12 主人把第三个 tab 从「本机操作」改名为「远程连接」——同一件事，`data-tab="local"`、`#view-local`、`.local-*`、`localVP`/`localHP` 等技术标识一律不变；hub 站点页里 Hub 那条说明也同步改成「管家聊天 · 编码 · 远程连接」。文档里旧称「本机操作」＝现在的「远程连接」。

## 渲染约定（聊天区）

- `http…` 可点；
- 单行 `::options` 后每行「1. 文字」= 可点按钮（点了即发用户消息，其后可跟 `::sysinfo`）；
- 单行 `::sysinfo` = 资源面板；
- 单行 `•` = 蓝点。
- ⚠️ **聊天里贴图贴不出去**：hub 走 `POST /v1/runs`，**runs 端点不会内联 `MEDIA:` 标签**（只有 chat/completions/responses 端点会转 base64）——写 `MEDIA:/abs/path.png` 主人只会看到一行路径文字。要看图：把图拷进 `~/stack/hub/`（bind mount 到 /srv，实时生效），在聊天里给 `http://localhost:8080/<名>.png` 链接（前端把 `http…` 渲染成 `target=_blank` 的 `<a>`，点开新标签就能看）。2026-10-13 用这招做的 `help-443.html` 就是范例。

## 聊天通道

走**持久运行**：`POST /api/hermes/v1/runs` → `GET /v1/runs/<id>/events`（带 `seq`/`last_seq` 续传）；音效共用顶栏喇叭开关（`run.completed`→tada，打断→gugugaga）。

## 定时消息横幅 / 收件箱

cron 输出落 `~/.hermes/cron/output/<job_id>/*.md`，界面打开时经 `GET /api/inbox` 领取，hub 顶部「定时消息」横幅展示。

## 右侧待办面板（三档：今天 / 明天 / 长期，2026-10-13）

`index.html` 的 `#todoPanel`：三档共用一个列表，前端变量 `todoDate` 取 `today` / `tomorrow` / `long`，一律走 `/api/todos?date=…`（后端 `todo_service/todo_api.py:8790`，读写同一份 `~/.hermes/todos.md`）。「长期」是主人要的**纯清单**（不挂期限、不进到点提醒、不参与每日播种），落在待办文件里的 `## 长期` 节（脚本 `todo.py --list long`）；手机版 `m.html` 的「待办」sheet 也是**三档**（今天 / 明天 / 长期，`#todoSeg`，2026-10-21 从「长期接在今日下方」改成独立档），底部一行输入框可**直接加一条**（加到当前档），未完成条目**右滑 = 挪到明天**（长期档 = 加到明天），逻辑与桌面版同源（`attachSwipe()`/`todoMove()`，同样 WAAPI 动画 + 兜底定时器）。改动的备份/一键还原：`~/stack/backups/long-todo-<时间戳>/`（`todos.md` / `todo.py` / `todo_api.py` / `index.html` + `restore.sh`）。

### 成就徽章墙（2026-10-21）

`plan.html` 在四条段位线下面多一面「成就 · 徽章」墙：12 枚小徽章，每枚铜 / 银 / 金三档，条件全部从 `todos.md` 与 `state/eod.json` 自动算（`plan_ranks.py` 的 `compute()["badges"]`），不靠手动打卡。徽章：全清日 3/10/25 次、连清 2/4/7 天、药不能停 7/21/60 天、举铁 3/20/40 次、开口 3/10/30 条、刷题 10/30/60 天、八股 10/30/60 天、项目 5/15/30 天、早睡 3/7/14 天、稳周（单周≥5天早睡）1/2/4 周、百条功 50/150/300 条、零拖欠 3/7/14 天。

解锁提示：`/api/todos` 快照里 `ranks.badges[].is_new` 由 `state/badges-seen.json`（`{id: level}` 水位，只增不减）算出；`index.html` / `m.html` 的 `checkBadges()` 在待办面板弹一句「★ 解锁徽章 N 枚：…」，随后 `POST /api/todos {"action":"badges_seen","items":[{id,level}]}` 登记并清 60 秒 ranks 缓存。想重看提示就删掉那个 seen 文件。

### 「成就 · 段位」下线，小徽章保留（2026-10-22 主人要的）

主人原话「删除破阵那些大成就，只留下小勋章和解锁弹窗」→ **删掉四条段位线（破阵 / 千锤 / 破壁 / 守夜 + 段位说明卡），保留 `#badgeGrid` 徽章墙与解锁弹窗**。做法：`plan.html` 删 `<h2>成就 · 段位</h2>` 到 `#achGrid` 那一整块，渲染入口只留 `renderPhase(...)` 与 `renderBadges(...)`（`renderRanks()` 成了死代码，留着不调用）。**三个阶段（断链 / 登岸 / 夺旗）不动**，那是路线图不是成就。后端 `plan_ranks.compute()` 照旧算 `lines`（没人读了）与 `badges`。备份 `~/stack/backups/nobadge-20261022_160331/`（拆段位前的原样）。

### 顶栏小咕嘎（2026-10-22 主人批准）

顶栏 `咕嘎` 品牌右边多了一只 SVG 小黄鸟 `#pet`，三态纯 CSS 动画：

- **趴着**（默认）：闭眼 + 身体压低（`petBreath` 4.6s 呼吸）+ 飘 z；
- **干活**（`.pk-work`）：睁眼、上下颠（`petBob`）、扇翅膀、点头 —— 由 `actStart()` / `actStep()` / `restoreTurn()` 接回在跑的轮次时点亮；
- **出错**（`.pk-err`）：抖 + 右上冒蓝汗 + 喙变红，`actFinish('fail')` 触发，4.2 秒后自己回到趴着。

点一下：有活动记录就把聊天头那条忙碌胶囊（`#busyPill` / `#busyBar`）展开/收起，并弹一句当前状态（`actTxt()`，例如「干活中 · 已 17 秒 · 正在 lark_send」）；没在跑就弹「我现在闲着，趴着呢」。整套复用已有的 `actRec` 机制，没加新接口。备份 `~/stack/backups/pet-20261022_225040/index.html`。

### 早晨打卡 · 到教室（2026-10-22 主人要的）

- 入口：桌面 `index.html` 右侧「计划」面板、手机 `m.html` 待办 sheet，都在「结束一天」上面一行（`#ckRow` / `#ckBtn` / `#ckInfo`，两端同名）。两端读**同一份数据**（15s 轮询 + 操作后即时刷新）。主人 2026-10-22 说**不要**在「已到教室」后面标来源（电脑/手机），那格现在留空。
- **整屏大按钮（2026-10-22 当天又改的）**：两端 `<body>` 开头各有一层 `#ckBig` 遮罩（fixed、z-index 9998），平时 `display:none`，今天还没打卡就盖住整个界面，中间一个大圆按钮 `#ckBigBtn`「到教室打卡 / 8:00 前算准时」，底部一行「今天先不打卡」。打开页面时靠 `ckBoot()`（各自文件里）单独取一次 `/api/todos?date=today` 驱动，**不依赖待办面板是否展开**；点完变成绿色「HH:MM 到了」1.35 秒后自动收起。跳过写 `localStorage['ck_skip_<日期>']`，当天不再弹。`ckHoldUntil` 那个时间戳是防止成功动画被 15s 轮询的 `paintCheckin()` 提前关掉。
- 规则（**2026-10-23 主人订正**）：**周一到周五 8:00 前、周日 9:00 前算准时**，周六整休不打卡（截止返回空串，前端据此把打卡行和整屏按钮都藏掉），之后算迟到但照记；**当天第一次为准**，再点只回显第一次的时刻、不改记录。截止时间走 `todo.checkin_deadline(日期)`（`CHECKIN_DEADLINE = "08:00"` / `CHECKIN_DEADLINE_SUNDAY = "09:00"`，`CHECKIN_RULE_FROM = "2026-10-23"`；之前的日子按旧口径 9:00 / 7:00 判，旧账不翻成迟到）；`plan_ranks.py` 里 `_ck_deadline()` 是同一规则的副本，改一处要同步另一处。前端不写死，读快照里的 `checkin.deadline`。
- 数据 `~/.hermes/state/checkin.json`：`{日期: {time, at, src}}`；写入 `todo.py:record_checkin()`，命令行 `python3 ~/.hermes/scripts/todo.py checkin`。
- 接口**零基础设施改动**，走已有 `/api/todos`：POST `{"action":"checkin","src":"pc|mobile"}`；快照多一个 `checkin` 字段（`time`/`at`/`src`/`deadline`/`late`）。
- 成就：`plan_ranks.py` 的 `punctual`「守时」，按**连续准时天数**（`checkin_ontime()`）铜 3 / 银 7 / 金 14 天。
- 打卡行只在「今天」档显示（`paintCheckin()` 里按 `todoDate` 藏）。
- 备份：`~/stack/backups/checkin-20261022_153023/`（`todo.py` / `todo_api.py` / `plan_ranks.py` / `index.html` / `m.html`，拷回原处 + `sudo systemctl restart hermes-todo-api` 即还原）。

### 「结束一天」的撤回（2026-10-22 主人要的）

- 误点救回：桌面 `.todo-eod`、手机 `.teod` 里「结束一天」右边多一个 ✕（`#eodUndo`，只有今天记过才显示）。点了确认后 `POST /api/todos {"action":"eod_undo"}` → `todo.clear_eod()`：删掉 `state/eod.json` 当天那条，并把 `plan-log.md` 里该时刻的「结束一天」行删掉。
- **坑（已修）**：旧 `_log_eod()` 用全局 `re.sub` 改「结束一天」行，导致新记录会覆盖**别的日期**那一行（10-22 测试时就串到了 10-17 那节）。现在 `_log_eod()` 只在 `## <当天>` 那一节里增删；`clear_eod()` 按「时刻字符串精确匹配」删，不怕历史错位。

### 每日播种模板（2026-10-26 起的新节奏）

`todo.py` 的 `items_for()` 按日期分流：`NEW_SINCE = "2026-10-26"` 之前沿用旧锚点（学习项目 / 算法 / 八股 / 口述 / 健身），之后是「喝蛋白粉 + 肌酸（第一条）、复习项目、刷四道算法题、健身（只在周日 / 周二 / 周三 / 周五 —— `GYM_WEEKDAYS = {6,1,2,4}`）、看八股文、投递岗位、60 秒口述录制、吃药 22:00」。周六仍是整休（2026-10-22 主人把「早晨打卡」「上课」从待办里撤了——打卡走整屏按钮，上课不算待办）（只吃药 + 早晨复盘）。主人定这套时同时定了 7:00 起床、23:00 睡（周日到周四）。

### 向右滑 → 挪到明天（2026-10-21）

未完成条目向右滑过 70px 松手：先悬浮高亮 ~0.23s（`.lift`），再用 WAAPI 划出屏幕淡出，然后 `POST /api/todos {"action":"tomorrow","n":…,"date":todoDate}`；长期档滑走 = 落到明天、截止日保持原样；日期档带 ⏰ 的项到期时刻改到目标日期。动画结束才发请求（`todoSwipeBusy` 期间跳过 15s 轮询重渲染）。前端 `attachSwipe()` 在 `renderTodos()` 里按未完成项挂载，用 pointer 事件 + `touch-action:pan-y`（竖向仍是滚动），刚滑过的行用 `row.dataset.swiped` 抑制那一次 click。后端 `todo_api.py` 的 `do_move()`。**动画别用 CSS transition 字符串（有些手机会吞掉），一律 `element.animate()` + 兜底定时器收尾。** 备份：`~/stack/hub/index.html.bak-swipe-20261021_115647`、`~/stack/todo_service/todo_api.py.bak-swipe-20261021_115647`（拷回原处 + `sudo systemctl restart hermes-todo-api` 即还原）。

## 「远程连接」页（第③ tab，P2 ✅ 2026-10-10）

= **左机器列表 + 右命令框**，只读直跑、**写/危险先确认**。

- 后端 `guga-remote-api`（`~/stack/remote/remote-api.py`，:8792，Caddy `handle_path /api/remote/*`）；确认门 `classify()` 就在该文件里：含 shell 元字符一律 danger，否则查只读白名单，**default-deny**；审计 JSONL `~/stack/remote/audit.log`。
- **服务器（咕嘎一号）不列入机器列表**——要操作服务器直接找管家。
- 前端：`#view-local`、`.local-*` CSS、拖拽键 `localVP`/`localHP`。
- **每台机器自己的会话栏**：选中机器后操作区顶部有 `对话 N` 药丸 + 「+ 新对话」，五号/六号各自可开多段、随时切回；**空状态显示它自己的名字**（「咕嘎N号随时待命」）。坑：**Hermes 不允许会话标题重复**（重名 400 `invalid_title`），所以同机器第 2 段起标题要加「 · N」序号。
- **删对话**：管家侧栏悬停出 ✕；机器会话栏每段药丸里也有 ✕（都带确认；删当前那段会自动切走）。
- **右上角是咕嘎聊天区**（切 tab 时把管家的 `.chatwrap` 整块搬进/搬回，`window.moveChatPane`），但**每台机器有自己的专属记忆和自己的那段对话**——共用的只有总记忆文档，**不共享实时对话**。专属记忆 `~/stack/remote/memories/<别名>.md`（后端 `/api/remote/machine`）→ 在该页发消息时作为 `instructions` 临时系统提示注入；机器→会话映射在 `~/stack/remote/sessions.json`（每台机器一个「远程 · 机器名」会话）。
- 左侧栏最底下是**「接入页」常驻块**（连接密码，见 `feature3-remote.md`）；另有「+ 接入」按钮与「邀请」按钮（见同文档）。

## 第④ tab「站点地图」（2026-10-11 主人要的）

站点页 = **本网站所有页面入口的清单**（Hub、各终端、code-server、Gitea、六号邀请页、我的夹心…），每条自带**主人自己选的颜色** + 悬停显示的功能说明，**整行点击新标签打开**；行尾悬停才出 ★置顶 / ✎编辑 / ✕删除，可**拖动排序**，可 **+ 新增**（带取色器 + 8 个预设色块）。

- **存服务器** `~/stack/remote/sites.json`，读写走**已有**的 `/api/remote/sites`（在 `remote-api.py` 里，**零基础设施改动**——Caddy 的 `handle_path /api/remote/*` 与 systemd 的 `ReadWritePaths=/home/ubuntu` 都已覆盖）。
- 种子首次自动写入；`preview-*.html`（夜间小工程预览页）由后端**自动发现**成只读灰条，文件出现/删除即自动增减。
- **分两份（2026-10-13 主人要的）**：每条多一个 `murl`（**手机版地址**，空＝只适合电脑）。渲染时有 `murl` 的排在上半部分、带 `M`（独立手机版页）/ `自`（自适应，murl 等于自己的 url）小标 + 右侧「手机版 /xxx」；自适应的那条**不再重复写同一地址**（只留 `自` 标）；没 `murl` 的收在下面 `Only PC · N` 那节（没有手机版条目时不显示这行标题）。`murl` 填了但不合 url 规则 → 整条拒掉。编辑弹窗多了「手机版地址」输入框；**拖动排序禁止跨节**（分组是算出来的，跨节拖看不出效果）。
- **六号接入页那条必须填公网地址**（`https://join.dqmguga.site/join.html`，免密、可复制发人），**别用 `/join.html`**——那是 hub 同源页，整站在门卫后面，发出去别人打不开；它自适应、也不填 `murl`（否则会被标成「手机版」）。
- **手机版 hub 的「站点」按钮**（`m.html` 抽屉底部，待办 / 站点 / 咕嘎群）：弹出 sheet 只列有 `murl` 的（点一行新标签打开手机版地址），底下 `Only PC · N` 可展开收起。数据同样走 `/api/remote/sites`。
- 种子里的默认配对在 `remote-api.py` 的 `_MOB_DEFAULT`（`/`→`/m.html` 等）；现网活数据在 `sites.json`。备份/一键还原：`~/stack/hub/*.bak-*-sites2`、`remote-api.py.bak-sites2` + `restore-before-sites2.sh`。
- 安全：url 只收 `http(s)://` 或以 `/` 开头（挡 `javascript:`/`data:`/`//evil`），color 只收 `#RRGGBB`，所有文字一律 `textContent`。
- 踩坑：`const RAPI='/api/remote'` 声明在「远程连接」那个 IIFE **里面**，新模块作用域取不到——得自己再声明一个（第一版就栽在这）。详见 `../procedures.md §1`。

## 附件投递（回形针 · 2026-10-13 主人要的）

- 桌面 `index.html`、手机 `m.html` 的输入框左侧各一个回形针（`#clip` + 隐藏 `#clipFile`）：点选文件、拖进输入区、`Ctrl+V` 粘图都行；选中的文件在输入框上方排成芯片（图片显示圆形缩略图，其他显示扩展名标签 + 大小），点 × 可撤。只发文件不写字也允许。
- 后端在 `todo_api.py`（:8790）加了两条，**不用改 Caddyfile**——故意走已放行的 `/api/inbox*`：
  - `POST /api/inbox/upload`：**raw 字节当 body**（不用 multipart，省解析），文件名放 `X-File-Name`（percent-encoded）。
  - `GET /api/inbox/uploads`：最近 50 条（读 `uploads/index.jsonl`）。
- 落盘 `~/stack/hub/uploads/<日期>/<HHMMSS>-<原名>`，单文件上限 64 MB；hub 目录由 caddy 静态提供，所以图片缩略图直接用 `<img src="/uploads/…">`（公网也在门卫后面）。
- 发消息时前端把附件拼成消息开头几行：`【附件】<宿主绝对路径>（原名，大小）`，之后才是主人写的话——**一号据此 `read_file` / `vision_analyze`**（图片直接看，pdf/word/excel/代码能解析）。
- 备份 + 一键还原：四个 `.bak-20261013_174001-upload` + `restore-before-upload.sh`。
- 踩坑：`make-m6.py` 靠**精确锚点**改 `m.html`，动了被锚定的片段（这次是 `addUser(text)` → `addUser(text, files)`）必须同步改脚本，否则生成以「锚点不匹配」中断。

## 其它页面

- `/join.html` —— 咕嘎六号接入页（常驻入口，见 `feature3-remote.md`）
  - **2026-10-24：只读档取消**，接入页只剩「完整协助」（页面、`#permBadge`、`permSwitch` 全删；老邀请里记的 read 由页中心跳直接推成 full，脚本 `{{MODE}}` 随之为 full）。
  - **2026-10-24：Windows 接入脚本 1/6 卡死的两个真凶已修**（`/opt/guga-join/onboard-win.ps1`，备份 `onboard-win.ps1.bak-20261024_204621`）：①`Get-WindowsCapability -Online` 无超时会挂在 Windows Update → 现丢进 Start-Job、45 秒上限；②下载离线包时原来只有一行提示、慢网像卡死 → 改成 28 格进度条（`[####----] 54%  2.9 / 5.4 MB`，每 2% 刷新、失败带原因）。令牌 TTL 10 分钟：页面关了心跳就停，跑晚了会 403 退回 gh-proxy，看着也像卡死。
- `/m6.html` —— **咕嘎六号 · 手机端**（2026-10-13 主人要的）：**主界面就是对话**，顶栏那个链接图标（`#connBtn`）打开「连接信息」；抽屉里也有入口（`#connBtn2`）＋回到 `/m.html` 的「管家」。连接信息卡显示 名字/系统/用户名/权限/端口/在线状态 + 「跟它对话」「断开并撤销」（真断，打 `/api/join/revoke`）。发消息时把「你就是咕嘎六号…」那段身份提示当 `instructions` 带上（不落进历史），并把当前会话绑到这台 guest（`/api/join/session`）；启动时优先接上那台机器已绑的会话（`guest.session_id`）。它由 `hub/make-m6.py` 从 `m.html` 生成（改 m.html 后重跑一次即可，别手改 m6.html）。
- **六号不跟管家共用会话（2026-10-13 主人明确提出）**：`m6.html` 的 API 基址是 `/api/hermes/p/remote`（**远程操作分身**那个 profile），不是 `/api/hermes`。于是它的会话列表只有 `远程 · …` 那批、自己的记忆在 `~/.hermes/profiles/remote/memories/`，**看不到一号的管家会话**；拿到的身份提示是「你是咕嘎一号的远程操作分身，不记得主人的生活」，长期事实写它自己那份 `~/.hermes/guga6/MEMORY.md`（按机器名分节）。新对话会顺手把标题改成「六号 · <机器名> · HH:MM」。
- `/jiaxin/` —— 「我的夹心」（她的档案 / 约会 / 故事日记）
- `/hermes`（管家终端 ttyd+tmux）、`/claude`（编码终端）、`/shell`（工作区 shell）、`http://localhost:8081/`（code-server）、`http://localhost:3000/`（Gitea）

## 手机语音输入（2026-10-19 主人已放弃，别再主动提）

- 安卓 Chrome 的 Web Speech API 是把音频送谷歌识别，国内 8s 零响应 → 页面上麦克风点了没反应，前端改不好。
- 正解只有两条：服务器自建 Whisper（免费/不出网/常驻约 0.5G 内存/一句话两三秒）或接国内云端 ASR（火山/腾讯/硅基流动，需密钥、可能有费）。两条都解释过，主人一句「算了吧」收场。
- 现在 `m.html` 里那套 SR 代码留着不动，当 iPhone Safari（走苹果识别，国内一般通）的备用；主人再问就说「这事你说过算了」，不要重新推销方案。
