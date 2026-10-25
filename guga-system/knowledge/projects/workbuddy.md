# 项目：咕嘎三号 —— WorkBuddy（网页版接入 ✅ 2026-10-12）

## 是什么

WorkBuddy（`https://www.workbuddy.cn`，标题「AI Agent 办公新范式」）是**网页版 AI Agent 办公平台**：左侧「新建任务 / 项目 / 专家·技能·连接器 / 更多」，中间是任务输入框（可切「日常办公 / 代码开发」，带幻灯片、视频生成、深度研究、文档处理、数据分析、可视化等技能条）。

> 主人 2026-10-12 先说它是「客户端软件」，随后给了网页地址 `https://www.workbuddy.cn/app` —— **网页版可用**，所以走浏览器这条路，不需要在目标机上做界面自动化。

## 擅长什么（2026-10-12 实地侦察 + 官方资料）

**定位**：腾讯「全场景 AI 办公工作台」（CodeBuddy 团队出品，2026-03 上线；国内办公 Agent 赛道第一）。核心口号就是**「交任务 → 自己拆解执行 → 给可直接验收的成品」**：文档、表格、幻灯片、数据分析、看板、视频都在交付范围。

**形态**：
- 桌面客户端（Windows/macOS）—— 能读写**授权过的本地文件夹**、支持云端沙箱 / 本机执行双模、多智能体并行、可被微信/企微/QQ/钉钉/飞书远程遥控（Claw）。
- 网页版 `workbuddy.cn/app` —— **我现在接的是这个**，跑在它的云端沙箱里，**拿不到主人本机的文件**。要本地文件操作，得在五号装客户端。

**技能市场（实测清单，分类很全）**：腾讯ima（笔记/知识库）、腾讯文档 PDFKit、企业微信套件、钉钉套件、腾讯自选股 / NeoData / 同花顺iFinD / 东方财富妙想 / 通达信（金融数据）、Excel 处理、PPT 演示文稿、PDF 处理、MarkItDown、**Web Access（浏览器自动化）**、QQ音乐助手、fbs-bookwriter（长文档/写书）、MiniMax H3 视频提示词、grill-me（方案深挖）、系统化问题定位、技能创建指南…（分类：办公协同 / 开发工具 / 投资理财 / 效率工具 / 内容创作 / 信息资讯 / 教育学习 / 数据分析 / 网站部署 / 生活服务 / 商业运营 / 知识与学习）

**连接器（MCP，实测有）**：腾讯文档、Notion、**GitHub MCP**、CNB（代码托管）、TAPD、Supabase、微云、金数据（表单）、乐享知识库、**可灵 AI（生图/生视频）**、COROS（运动健康）、同花顺法律AI、同花顺快查企业数据、氪云、薪人薪事、海尔智能体…

**能力条（任务里可切）**：幻灯片 / 视频生成 / 深度研究 / 文档处理 / 数据分析 / 可视化 / 金融服务 / 产品管理 / 设计 / 邮件编辑；模式分「日常办公 / 代码开发」。
**项目区模板**：市场调研与竞品分析、团队知识库、项目交付、Bug 跟踪/测试验收。

**额度（要省着用）**：免费版**每月 30 次智能体调用**、PPT 最长 10 页、带水印；个人 Pro ¥39/月。这套是主人的账号。

## 怎么调用（我这边）

- 常驻浏览器 + `python3 ~/.hermes/workbuddy/wb.py run <代码.py>`（代码里可用 `goto_url/js/cdp/…`）。
- 提交任务：进 `/app` → 聚焦输入框（`textarea,[contenteditable=true]`）→ `cdp('Input.insertText', text=…)` → 回车。任务**异步**跑，进度一条条出现在会话里，成品进「产物」区。
- 页面路由可直接跳：`/app`（首页/新建任务）、`/app/experts`（专家 / 技能 / 连接器）、`/app/skills`、`/app/connectors`、`/app/projects`。
- **点左边栏要点最里层那个文字元素**（`children.length === 0` 的 span），点外层容器没反应。

## 实测记录（2026-10-12）

提交了一个「3 页幻灯片：C++ 后端实习面试复习清单」——**跑通了，而且成品是文件**：

- 它先拿 `workbuddy-pptx` 工具链做了个 `test-deck.pptx` 自测（tsx/jsx 页面文件 → 构建 → 转 PNG 目视校验）；
- 然后正式建 `C++后端实习面试复习清单.pptx`：创建 `01.tsx` 封面 → 渲染 `slide-1.png` 自查「封面效果不错」→ 继续第 2 页「高频考点六宫格」→ 自己的任务清单（梳理叙事结构 / 设计视觉方案 / 逐页制作 / 交付）；
- 全程状态条写「思考中」，右边「产物」面板实时列出文件。
→ **结论：它交的是文件级成品（PPTX），不是聊天式建议；一次任务要跑几分钟，异步的。**

## 边界（别指望它做的）

- 网页版**看不到主人本机的文件**；要碰本地目录只能在五号装桌面客户端。
- 连接器要 OAuth 授权（GitHub/Notion/腾讯文档等），**授权得主人自己点**，我不替他点。
- 额度有限：重要交付前先跟主人打招呼，别拿它刷着玩。
- 它自己的页面就写着「内容由 AI 生成，请核实重要信息」——**成品要核**。

## 登录态「保鲜」✅（2026-10-12 主人批准后建成）

**关键坑（先说最值钱的）**：`browser_exec` 默认会话的浏览器**每次重启都是空档案**（临时 profile 在 `~/.hermes/cache/scratch/agent-browser-chrome-<uuid>/`，且会被 24h 清理）→ **扫码登进去，浏览器一重启就掉线**。所以三号的持久化必须自带档案：

- `~/.hermes/workbuddy/chrome.sh` —— 起一个**常驻** Chrome，固定档案 `~/.hermes/workbuddy/chrome-profile` + 固定调试端口 **9333（只监听 127.0.0.1）**。登录态从此跨重启保留。
- `~/.hermes/workbuddy/wb.py` —— 驱动它：`python3 wb.py`（看当前页）／`python3 wb.py run -`（从 stdin 喂 browser-harness 代码）。原理：harness 支持 `BU_CDP_URL=http://127.0.0.1:9333` 接管自有浏览器，用独立 daemon 名 `BU_NAME=gugawb` 不跟默认会话打架。
- `~/.hermes/workbuddy/cred_status.py` —— **保鲜探针**，一天一次，输出一行（对齐四号那套）：
  - `OK 剩 N 天（…）` = 正常，别打扰主人
  - `REMIND …` = 掉线或 ≤5 天到期 → **顺手把新二维码截到 hub**，主人扫一下即可
  - `WARN …` = 探测失败（原因进 `probe.log`），晚报不打扰主人
  - 状态记在 `meta.json`，历史记在 `probe.log`
- **已接入晚报**：`evening-todo-review`（22:00，job `1222f2e58b9b`）第 12 步会跑它，REMIND 时在正文里提一句（不放进 `::options`）。

### 抓二维码的坑（踩过三次，都是真金白银）

1. 二维码在**跨域 iframe**（`open.weixin.qq.com/connect/qrconnect`）里，JS 读不到内容——只能截图。
2. `cdp('Page.captureScreenshot', clip=...)` 的坐标与 DOM 视口坐标**对不上**（截出来偏了几百像素，抓到的是卡片下半截）。**改用：整页截屏 + PIL 按 iframe `getBoundingClientRect()` 裁切**（harness 的 venv 里有 PIL 12，可直接 `from PIL import Image`）。
3. 还要**等 iframe 真正渲染**（轮询 `iframe.getBoundingClientRect().width > 50`，最多 20 秒），否则截到空白。
4. ⚠️ **主人正在扫的时候，千万别反复重载登录页**：每次重载都会作废他手上那张码（我做了个「70 秒自动换新码」的循环，结果他每次都扫到已失效的码）。正确做法：**抓一张就不动**，让他有时间扫 + 在手机点确认（微信 QR 有效期约几分钟）。
5. 扫码后如果手机上要确认，主人不点「确认登录」就不会登入——报「好了」但页面仍在 /login 时先想到这条。

### 验证记录（2026-10-12）

- 扫码 → `cred_status.py` 输出 `OK 剩 6 天（2026-10-19 22:00）`，`meta.json` 记下 `expires_at`。
- **持久性实测**：`kill` 掉常驻 Chrome 主进程 → `chrome.sh` 重新拉起 → 探针仍报 OK（登录态在固定档案里，跨重启保留 ✅），harness daemon 也自动重连。

## 怎么接的

- 登录页 `https://www.workbuddy.cn/login/?...redirect_uri=.../app`，**扫码方式是微信（open.weixin.qq.com 的 iframe 二维码）**，另有企业微信 / 手机号 / 邮箱 / SSO。
- **服务器上跑一个真浏览器**（browser_exec / browser-harness 的默认会话），登录态存在这台服务器的浏览器 profile 里，**长期有效**（掉了要主人重扫）。
- 给主人看二维码的办法：把二维码 iframe 区域截图写进 hub 静态目录 + 一个自动刷新的页面：
  - `/home/ubuntu/stack/hub/workbuddy-qr.png`（每次重抓覆盖）
  - `/home/ubuntu/stack/hub/workbuddy-qr.html`（页面每 3 秒带随机参数重新拉图，免得看到缓存里的旧码）
  - 主人打开 `http://localhost:8080/workbuddy-qr.html` 用手机微信扫 → 服务器浏览器即登录。
- ⚠️ **hub 聊天走 runs 通道，不认 `MEDIA:` 标签**（会显示成一行路径字面量）——给主人看图/文件一律**放 hub 静态目录 + 给可点链接**。

## 抓二维码的小抄（真跑过）

```python
goto_url("https://www.workbuddy.cn/app"); wait_for_load(); time.sleep(5)
rect = js("(() => {const f=[...document.querySelectorAll('iframe')].find(f=>/open.weixin.qq.com/.test(f.src)); if(!f) return null; const r=f.getBoundingClientRect(); return {x:r.x,y:r.y,w:r.width,h:r.height};})()")
# 二维码在跨域 iframe 里：JS 读不到内容，但可以按 rect 截图
shot = cdp('Page.captureScreenshot', format='png', clip={...rect 外扩 6px, scale 4})
```

## 咕嘎群的搬运规矩（2026-10-13）

**自动通道（主人点名时才走）**：`~/.hermes/scripts/workbuddy_ask.py`
——用常驻浏览器在它自己的会话里替它打字、等「已完成」、把正文取回来（正文要剥掉页面标签）。
群信使经由 `agent_carry.py --who 三号 --ask "…"` 调它，回话贴群标「代发」；它的会话 id 存在
`~/.hermes/state/carry.json` 的 `三号.conversation`。

**它不在「没点名就全体回」的名单里**（主人 2026-10-13：太慢，不带他了）；那种场合由一号代它说
一句「三号在外头跑别的活…」（`group_relay.py` 的 `THREE_STANDIN`，标「代发」）。主人点头像或
叫它名字才走真通道，**每问一次吃一次智能体调用额度**（免费版 30/月），耗时 30–90 秒。

**要文件级成品的活**走手工：把任务交给它自己的项目做，记录留在它那边——**那就是它的记忆**，
我只转交、取回，不在本机留副本：

- 生成简报：`python3 ~/.hermes/scripts/agent_carry.py --who 三号 --brief "主人的话"`
  → 把打印出来的那段贴进它的项目/任务框（浏览器，步骤见上）。
- 它回话后贴群：`python3 ~/.hermes/scripts/agent_carry.py --who 三号 --answer "它的回话"`
  （长文本用 `--answer-file /tmp/x.txt`）——群里会标「代发」，主人知道是我带的。

## 现状与待办

- 已登录，停在 `/app` 首页（截图 2026-10-12 晚）。
- **登录态有多久**：`session` / `session_2` 两个 cookie 的过期时间是 **2026-10-19 21:32（约 7 天）**，其余是统计类 cookie。所以大概一周要重扫一次（若平台在活动时给续期则更久，不保证）。
- **还没替主人做过任何事**——具体要它干什么（派活 / 读结果 / 定时任务）等主人交待。
- 主人心里「三号」= WorkBuddy 上的智能体；在 hub 里聊天出现的新需求，按「找它办」理解。

## 对比：四号（LightVela）的凭据是长期的

`~/.hermes/lightvela/`：`cookie.txt` 存 `lc_session`（服务端约 30 天），`meta.json` 记 `logged_in_at` / `expires_at`（登录日 +30 天估算），`cred_status.py` **实探一次接口**（401/403 即失效）+ 到期前 5 天提醒 → 晚报里给主人一句话。**三号要不要照这套做「保鲜」，等主人拍板。**
