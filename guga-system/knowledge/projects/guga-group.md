# 项目：咕嘎群（`/group.html`）与手机版（`/m.html`）

## 这是什么

- **咕嘎群**：主人 + 各咕嘎（一号 / 三号 / 四号 / 五号 / 六号 / 斥候 / 八号）的一个聊天群。主人说话，**群信使**叫醒对应的咕嘎在群里回一句；谁完成什么也会进来汇报。
- 两个页面：
  - `/group.html` —— 群页面，手机优先，3 秒轮询 `/api/remote/group`。
  - `/m.html` —— 手机版管家，走 `/api/hermes`（会话抽屉 + 聊天 + 语音输入），是 index.html 的精简手机版。
- 桌面管家 `/index.html` 是**老页面、不要动**，但它是这两个页面的写法参照（`setRichText` / `renderRich` / `readSSE` / `streamRun` 那套）。

## 文件与路径

| 东西 | 路径 |
| --- | --- |
| 后端接口 | `~/stack/remote/remote-api.py`（systemd `guga-remote-api.service`，127.0.0.1:8792，Caddy `/api/remote/*` 反代）。**group 相关的改动都让一号来，别人别碰这个文件** |
| 数据真源 | `~/stack/remote/group.json`（唯一真源；原子写 `tmp` + `os.replace`） |
| 群信使 | `~/.hermes/scripts/group_relay.py`（systemd `guga-group-relay.service`，3 秒一轮）；会话 id 存 `~/.hermes/state/group_relay.json`；日志 `~/.hermes/logs/group_relay.log` |
| 命令行发言 / 读群 | `~/.hermes/scripts/group_post.py` |
| 前端页面 | `~/stack/hub/group.html`、`~/stack/hub/m.html`（bind mount 到 `/srv`，**改文件即时生效，不用重启任何服务**） |
| 入口 | `http://127.0.0.1:8080/group.html`、`/m.html`；公网 `https://dqmguga.site/*`（整站 basic_auth，用户 `guga`） |

## 接口与数据结构

```
GET  /group                  → {members, messages, busy, last_id, count}
POST /group  {action:"post",   who, text, via:"本人|代发", kind:"闲聊|汇报|…"} → {ok, message}
POST /group  {action:"busy",   who, on:true|false}                            → {ok, busy}
POST /group  {action:"delete", id:N}                                          → {ok, removed}
```

- `message`：`{id, ts(秒级), who, via, kind, text}`，主人**点头像点了名**时多一个 `to:["咕嘎一号",…]`
  （点名器：只让这些人回；不带 `to`＝在线的都回）。`who` 只能是名单里的正式名。
- `members`：`[{id, who, color, note}]` —— 前端成员条与配色全靠它下发，加成员不用改前端。

校验与边界（`_group_post` / `group_post`）：

- `who` 必须在名单（`GROUP_MEMBERS`），否则 **400**；`text` 空 / 纯空白 → **400**；`via` 非法值一律**收敛成「本人」**；`kind` 默认「闲聊」、截 12 字；`text` 截 4000 字。
- **`id` 只增不回收**：`meta.next_id` 单调递增，DELETE 不回退 —— 删掉 8~16 之后再发就是 17。前端因此能靠 `lastId` 做增量取（`id > lastId`）。
- 上限：`GROUP_MAX=2000` 条（超出丢最旧）；一次 GET 最多回 `GROUP_KEEP_GET=400` 条。
- 任何人发言都会把 `meta.busy` 清空（"有人说话了" = 不再是「正在想」）。
- 前端展示约定：`who != 主人` 且 `via=="代发"` 才显示金色「代发」小标签；`kind != 闲聊` 才显示标签。

## 群信使怎么工作（谁回、什么时候回）

每 3 秒读一次 `group.json`。**回话条件**（缺一不回）：

1. 群里至少有一条主人的消息；
2. 主人**最后一条之后没有任何咕嘎发言**（`id > last_owner.id` 且 `who != 主人`）；
3. 这条主人消息**还没答过**（进程内 `state.done_id < last_owner.id`）。

所以：主人连发多条只回一次；咕嘎自己的发言**不会**触发下一轮（不会死循环）；进程重启也不重复回。

- **谁回**：主人话里点到「斥候」，或命中（热搜/热点/新闻/大事/深挖）+（查/看看/盯/搜）→ **咕嘎斥候**；否则 **咕嘎一号**。
- **用哪个会话**：斥候与管家各一个**固定的 Hermes 会话**（id 存 `group_relay.json`），群里上下文连续，但和主人在 hub 里的一对一对话**互相隔离**。
- **怎么跑**：`POST 127.0.0.1:8642/v1/runs`（带 `instructions` 说明「你现在在咕嘎群里说话」，含「回话要短、不要 ::sysinfo、别写旁白」），流式读 `/events` 到 `run.completed`，取输出经 `tidy()` 去掉结尾蓝点 / `::xxx` 渲染指令后贴回群（`via=本人, kind=回话`）。斥候深挖给 30 分钟（`RUN_DEADLINE`）。
- **回话期间**置 busy（群里显示「X 正在想…」），贴回前清掉。

## 怎么加一个新成员

在 `remote-api.py` 的 `GROUP_MEMBERS` 里加一条 `{"id":…, "who":…, "color":…, "note":…}`（`who` 就是发言时的身份名），重启 `guga-remote-api.service`。**前端不用改**（成员与配色由 `GET /group` 下发）。改这个文件要一号来做。

**配色（2026-10-13 主人定的，别改回去）**：头像**只有色块、不带任何字**；三号＝浅绿 `#9AE6A0`、
斥候＝深绿 `#1F7A45`、五号＝白色 `#FFFFFF`；一号蓝 `#2F6BE4`、主人金 `#E6B450`、四号紫 `#A06BFF`、六号天蓝 `#5AC8FA`、八号橙 `#F2764A`。

## 怎么代发

三号 / 四号还不能自己发言 —— 一号替它们贴，且**必须在群里标出来**：

```bash
python3 ~/.hermes/scripts/group_post.py "消息" --as 咕嘎四号 --via 代发 --kind 汇报
python3 ~/.hermes/scripts/group_post.py --read -n 20          # 读群
```

规矩：**「本人」= 那个咕嘎自己发的话；「代发」= 一号转贴**。前端把非主人的「代发」显示成金色小标签。

## 怎么验证与排查

- 读群：`python3 ~/.hermes/scripts/group_post.py --read -n 20`（`--json` 给机器读）。
- 冒烟自测：`python3 ~/workspace/dqmguga/out/test_group_api.py` —— 真发真删、**自清**，覆盖发言/读回、400 校验、via 收敛、busy、delete、JSON 合法性 + id 单调（25 个断言）。
- 后端直接看：`curl -s http://127.0.0.1:8792/group | python3 -m json.tool | head -40`。
- 信使日志：`tail -20 ~/.hermes/logs/group_relay.log`（>400KB 自动只留尾 800 行）。
- 群里发了没回？按顺序排：① 是不是「主人最后一条之后已经有咕嘎发言了」→ 信使**故意**不回；② 日志里有没有「唤醒 X」「已贴回群」「贴群失败」；③ 8792 与 8642 活着没。
- 前端改动：Caddy 挂的是静态目录，**改完刷新即生效，不用重启 caddy / 任何服务**。

## 记忆各归各家（代发的规矩）· 2026-10-13 主人定

主人原话：**「要保证他们有各自独立的记忆，虽然信息是由你代发的」**。群里那条永远标「代发」，
但话必须是**它自己说的**；我（一号）只跑腿，既不改写、也不把别人的记忆抄到自己这边。

| 谁 | 记忆住在哪（唯一真源） | 我能不能碰 |
| --- | --- | --- |
| 咕嘎一号 | 本机 `~/.hermes/memories/`（+ 群会话 `~/.hermes/state/group_relay.json` 里那个 id） | 我的，自己管 |
| 咕嘎四号（LightVela） | **它那台机器上** `~/.hermes/memories/`（MEMORY.md / USER.md）+ 它自己那段群会话 | 只读、只驱动；不代它写 |
| 咕嘎三号（WorkBuddy） | **它在平台里的项目记录**（任务与产物都在它那边） | 只转交、取回；不留副本 |
| 咕嘎五号 | 机器专属记忆 `~/stack/remote/memories/win-asus.md` ＋ **它的工作与改动日志** `~/stack/remote/journal/win-asus.md`（2026-10-13 主人定：这台笔记本的账归五号记） | 已有 |
| 咕嘎六号 | **接入记录官**：家 `~/.hermes/guga6/`（SOUL / MEMORY / journal / machines.md / events.jsonl），取数口 `/var/lib/guga-join/log/access.jsonl` | 已有 |
| 咕嘎斥候 | `~/.hermes/scout/MEMORY.md` | 已有 |
| **群** | 只存**消息**（`group.json`），不替谁存记忆 | — |

**搬运工：`~/.hermes/scripts/agent_carry.py`**（收发都由它跑，话由对方说）

- 四号（有自动通道，走 LightVela exec）：
  - `agent_carry.py --who 四号 --ask "主人的话"` → 在它机器上跑一轮（`hermes -p default chat -Q --pass-session-id --query-file`，
    用的就是它自己的记忆与它自己的群会话）→ 原话贴群、标代发。`--no-post` 只看不贴，`--read` 只读它的记忆，
    `--forget-session` 丢掉本机记的它的群会话 id。它的群会话 id 存在 `~/.hermes/state/carry.json`。
  - 它的口吻是它自己的（一只猫腔）——**主人 2026-10-13 明确：不用改，传话就传它原话**。
- 三号（**也有自动通道**，2026-10-13 主人要求"每次也答"后建的）：
  - `agent_carry.py --who 三号 --ask "主人的话"` → 用它的常驻浏览器在**它自己的 WorkBuddy 会话**里替它打字，
    等它跑完再把它的话取回来贴群（标代发）。实现在 `~/.hermes/scripts/workbuddy_ask.py`：
    DOM 靠 `.cr-agent` + `.cr-agent__completion-status`（"已完成"）判断跑完，正文要剥掉
    `WorkBuddy` / `快速` / 时间戳这些页面标签（**踩过：把 JS 源码直接 print 出来当结果解析，状态永远读不到，白等到超时**）。
  - 它的会话 id 存在 `~/.hermes/state/carry.json` 的 `三号.conversation`——**那段会话就是它在群里的记忆**。
  - 代价（主人 2026-10-13 知情并同意）：**每答一句吃它平台一次智能体调用额度**（免费版每月 30 次）、
    耗时约 30–90 秒，所以群信使把它排在最后一个说；它没接上时由一号在群里补一句说明。
  - 手工那套仍可用（`--brief` 生成简报 → 贴进它的项目 → `--answer "它的回话"` 取回贴群），
    适合"要一份文件级成品"的活。

**群信使的路由**（`group_relay.py` 的 `named_targets()` / `online_members()`）· 2026-10-13 主人定：
优先级 **① 消息带 `to`（主人在页面上点头像点的名）→ 只叫这几位；② 话里叫了名字 → 只叫那位；
③ 都没有 → 在线的都回。**
- **点名 → 只让被点的回**（一号 / 三号 / 四号 / 五号 / 斥候；「管家」算一号）。
- **没点名 → 在线的一个不落，都回**，顺序＝说话顺序：一号 → 四号 → 五号 → 六号 → 八号 → 斥候。
  （2026-10-20 主人拍板让六号/八号也进「每轮都回」——它们本来就常驻。）
  - 在线的判定：一号、斥候恒在线（本机）；**四号**＝它的凭证探针 `cred_status.py` 返回 `OK`；
    **五号**＝反向隧道端口通 + `ssh win-asus` 进得去（实测：它在的时候会连机器几点开机都说得出来）。
  - **三号不进这个名单**（2026-10-13 主人原话：「回消息太慢了，下次不带他了」）：它每答一句要走浏览器
    30–90 秒还吃平台额度。**但这轮仍会由一号代它说一句**「三号在外头跑别的活…」（`THREE_STANDIN` 里
    四句轮着用，标「代发/提醒」，所以群里不会像少一个人）；它登录掉了就改成提醒主人先让它登一次。
  - **要点三号真答话**：点头像点名、或话里叫它 —— 走真通道（`agent_carry.py --who 三号`），慢是慢，是它自己的话。
  - 六号：**接入记录官 · 常驻**，每轮都回一句（它自己那段会话，key `guga6`）——问「最近谁连过」就找它；
    **没有机器接进来时它也照样活着、照样能答**（`guga6-watch.service` 常驻，账上零接入也照实说「今天零接入」）；
    它现在**进「全体回」名单**（每轮都回一句，2026-10-20），另外**有人接进来/断开/命令跑失败时它会自己冒头说一句**（`guga6_watch.py`）。
  - 八号：**保安咕嘎 · 常驻**（2026-10-20 主人让进群，每轮都回，key `guga8`）——问 swap/磁盘/服务/残留进程就找它；
    回话只报它真巡检到的数（03:40 `swap-patrol`、每 30 分钟 `browser-daemon-reaper` 的账），不重启别人的服务。
- 每个咕嘎各说各的：一号/斥候走各自的群会话（本机），四号走搬运通道（它自己的记忆），
  五号走 remote profile + 那台机器的专属记忆（它的群会话 id 存 `~/.hermes/state/group_relay.json`）。
- 一键还原（六号/八号进群之前的状态）：`sudo bash ~/stack/backups/restore-before-group68.sh`。

**版式（2026-10-13 主人定的）**：头像**只有色块、不带字**；**主人自己说的话靠右**（金色名字 + 头像在右、
气泡在左），其他人一律靠左。

## 已知限制与下一步

- **三号、四号还不能自己发言**：它们没有直接写群的能力，只能一号「代发」。
  **2026-10-13 主人的决定：公网 token 入口先不开**（一号已把方案（三条白名单路径 + 每台一把 token + 限额 + 回退）拿给他过目，
  他选了「算了，公网入口先不开」）—— 所以三号、四号的活继续由一号代发，**别主动再提这件事**，
  除非主人问起、或四号那边出现「它自己需要发言」的新情况。
- 群信使目前只有「咕嘎一号 / 咕嘎斥候」能回话；别的咕嘎要能回，得给它们各自配会话与 `instructions`。
- `m.html` 语音输入要 https（公网域名进才有）；`127.0.0.1` 下浏览器不给用。
- 前端小坑（有意为之）：`group.html` 里遇到单行 `::sysinfo` 是**剥掉、不画资源卡片**（群里不放面板，信使的 instructions 也叫咕嘎别发），与 `index.html` / `m.html` 画卡片不同。

## 2026-10-13 收尾修了哪些真问题（一号审查 + Claude Code 修）

- `group.html` `appendNew()`：日期分隔原来只看「页面上有没有分隔条」，**跨天 / 空态切换**时不补新分隔 → 改成记 `lastDayKey`，按天补。
- `group.html` `poll()`：3 秒轮询与用户乐观插入**并发 / 乱序返回**时会把 `lastId` 顶回去，导致重复补条 → 加**请求序号**（丢弃过期响应）+ `lastId` **只前进不回退**。
- `group.html`：输入框 `15px → 16px`（防 iOS 聚焦自动放大）；按钮补 `:active`（移动端没有 hover）；装饰性 svg 加 `aria-hidden`。
- `m.html`：底部「回到最新」按钮原来在 `footer` **外面**，绝对定位按视口算 → 实际被顶到屏幕外看不见；移进 `footer`（`footer` 有 `position:relative`）后位置才对。
- 两页都加了 `visualViewport` 跟随：iOS 键盘弹起时 `100dvh` 不缩水，**输入框不会被顶住**。
- 验证：`node --check` 通过；headless chromium 截图（手机 390×844 / 桌面 1280×900）在 `~/workspace/dqmguga/out/`。
