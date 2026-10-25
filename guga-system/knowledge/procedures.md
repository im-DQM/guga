# 技能与流程（跨项目通用的做法与踩坑）

这里只放**能复用的做法和踩过的坑**；单个任务的细操作见 `~/.hermes/skills/` 下对应技能（`todo-butler` / `cron-briefings` / `guga-hub` / `remote-ops` / `lightvela-delegate`）。

## 0. 铁律

基础设施（Caddy / DNS / 端口 / 域名）改动前**必须先问主人确认**——我曾自行改 Caddyfile 加 `/api/todos` 并重启 caddy，造成过一次中断。域名 `dqmguga.site` 已实名、**2026-10-13 备案通过**，公网已上线：`dqmguga.site` + `www` 是 hub 整套（**整站 `basic_auth`**，用户 `guga`，密码存 `~/.hermes/secrets/hub-basic-auth.txt`）；`join.dqmguga.site` 免密但**只白名单** `/api/join` 的 claim/status/alive/connect/heartbeat/revoke_self 六条 + `/join/onboard*`、`/join/offboard*` + join 页本身，兜底 404；`:8080` 私网站点照旧只走隧道（ufw 没放行 8080，公网进不来）。

**Caddyfile 是「单文件」bind mount**：改完 `docker exec caddy caddy reload` 多半只会回一句 `config is unchanged`（容器里仍是旧的 inode）→ **必须 `docker restart caddy`** 才生效。改前必备份 `Caddyfile.bak-$(date +%Y%m%d_%H%M%S)-<名>`。

**公网 join 站的路由细节**：8793 只认「去掉 `/api`」后的 `/join/xxx`（它自己再剥 `/join`）——公网站点用 `uri strip_prefix /api` + `handle @matcher`；上游要 admin 头的路径只能留在私网站点（Caddy 注入 `X-Guga-Join-Admin`），公网白名单里**绝不能**出现 `/settings`（明文密码）、`/create`、`/guests`、`/exec`、`/revoke`。join API 对外链接的基址由 `GUGA_JOIN_BASE` 决定（已设为 `https://join.dqmguga.site`）。

**公网可达性只能用「外部视角」测**：本机 `curl` 自己的公网 IP / 域名会 hairpin 超时（腾讯云 NAT 不回环）→ 看到 `000` **别当故障**。真外部探测用 check-host.net 的 API：

```
rid=$(curl -sS -H 'Accept: application/json' "https://check-host.net/check-tcp?host=106.55.38.108:443&max_nodes=4" \
      | python3 -c 'import sys,json;print(json.load(sys.stdin)["request_id"])')
sleep 12
curl -sS -H 'Accept: application/json' "https://check-host.net/check-result/$rid"
```

2026-10-13 用它测出实事：**80 通 4/4、443 四个节点全超时** → 腾讯云**安全组没放 443**（host 侧 ufw 已 allow；`iptables -L ufw-user-input -v` 里 443 那条**计数为 0** 是旁证：从没有外部包到过 443）。放通 TCP 443 入站后才真正对外可用。

非对话类任务：先拿计划、用 `::options` 请主人拍板再动手；一眼可见的小调整（颜色/大小/位置）直接改，不用问。改任何前端文件前先备份：`cp index.html index.html.bak-$(date +%Y%m%d_%H%M%S)-<名>`。

**个人模型（2026-10-19 主人要的「真的记住我」）**：主人的条目库是唯一真源 `~/.hermes/knowledge/profile/entries.jsonl`，`~/.hermes/knowledge/主人画像.md` 由它生成、**不许手改**。规矩三条：

1. 对话里出现新的偏好、忌讳、习惯、目标或他自己下的判断 → 立刻 `python3 ~/.hermes/scripts/profile.py add --cat <类别> --fact "…" --evidence "原话" [--conf 推测]`，它会自动重生成画像。一次对话最多补 3 条，宁缺毋滥；他自己没说过的不许写。
2. 给建议、派活、写简报之前，先 `profile.py grep <关键词>` 或 `profile.py list --cat <类别>` 过一遍——**别凭印象**。
3. 服务规矩（怎么对他说话、什么不能碰）在同目录 `service-rules.md`，那是手写的，不受自动生成影响；发现他纠正了我，就往那儿补一条。

类别只有这些：目标、动机、性格、偏好、雷区、习惯、学习、健康、兴趣、观念、关系。每月 1 号列出 90 天没复核的条目。

## 1. 改前端 → 真跑验证（hub 的固定套路）

改 hub 前端后，用**无头 Chromium 真跑页面**验证，比 curl 强：

```
~/.hermes/tools/chromium-1208/chrome-linux64/chrome --headless=new --no-sandbox \
  --virtual-time-budget=8000 --dump-dom http://127.0.0.1:8080/
```

看渲染出的 DOM。要点交互就加 `--remote-debugging-port=9222`，用 `~/.hermes/tools/node-26.7.0-linux-x64/bin/node` 走 CDP 执行 JS（**v26 才有全局 WebSocket**，系统 node 是 v20 没有）。

【前端加新 tab / 新模块的稳妥做法（站点页验证得来）】
1. 新 tab 只要 `data-tab` **不是** `butler`/`local`，切 tab 就**不会**走 `moveChatPane`/`switchChatPane`，也就**不会**触发 `switchChatPane` 的 else 分支 `clearChat()`（那会把管家正在进行的对话清空）——「站点」页与「编码」页同属**安全类型**。
2. 验证点击要**真·受信任事件**：CDP 里 `element.click()` **不是**用户手势，`target=_blank`/`window.open` 可能被按弹窗拦掉（我一开始误判成代码 bug），必须用 `Input.dispatchMouseEvent`（mousePressed + mouseReleased）才算真点击。
3. 比 CSS 颜色时 `el.style.background` 回读的是 `rgb(r, g, b)`，别直接拿 `#RRGGBB` 比。
4. 改前先 cp 备份（见 §0）。
5. 新模块的作用域坑：`const RAPI='/api/remote'` 声明在「远程连接」那段 IIFE **里面**，别的模块**取不到**——得自己再声明一个（第一版就栽在这：页面显示「读不到站点清单」，而 fetch 手动跑却是 200）。
6. **`browser_exec` 默认会话的浏览器每次重启都是空档案**（临时 profile 落在 `~/.hermes/cache/scratch/`，闲置 24h 被清）→ 网页登录态保不住。要持久登录就自带档案：起一台常驻 Chrome（固定 `--user-data-dir` + 固定 `--remote-debugging-port`），再用 `BU_CDP_URL=http://127.0.0.1:<port>` + 独立 daemon 名（`BU_NAME=xxx`）让 harness 接管（三号那套见 `projects/workbuddy.md`）。截图裁切用 harness venv 里的 PIL（系统 python3 没装）。

## 2. 进程定位（别把自己杀掉）
`pkill -f <串>` 会匹配到 bash 自己的命令行、**把自己杀掉**——要用端口/pid 定位进程。`pgrep -f 'guga_join_tunnel'` 同样会匹配到自己那条命令行 → 假报「还有残留进程」；要用 `ps -eo args | grep '[s]sh -N'` 这种括号技巧。

## 3. 远程接入 · 目标机的坑（真机踩出来的，很值钱）

1. `permitlisten` 主机名必须写 **localhost**，写 `127.0.0.1` 会被拒——Windows 客户端发的是空绑定，服务器按 localhost 匹配。
2. PowerShell 里 `-R $ReversePort:localhost:22` 的 `$ReversePort:` 会被当成作用域限定、转发规格整段吃掉 → 必须写 **`${ReversePort}`**（保活任务不工作的真凶）。
3. `AuthorizedKeysFile` 要 `640 root:tunnel`（目标用户可读），否则 sshd 读不了。
4. 目标机要下载的东西一律**服务器代取放 hub、让它从 localhost:8080 拉**（国内直连 GitHub 卡死）。
5. `.ps1` 存 **UTF-8 带 BOM + CRLF**，否则 Windows 中文乱码。
6. 计划任务里用 **ssh.exe 绝对路径**（任务环境 PATH 不全）。
7. here-string 里 `$false` 会被插值成 `False` → 生成 `-Confirm:False`，参数绑定失败；必须写 `` -Confirm:`$false ``。**凡是往 here-string 塞 PowerShell 代码，每个该保留的 `$` 都要转义。**
8. 通过 ssh 跑 Windows PowerShell **别在命令行嵌套引号**（bash→ssh→PowerShell 三层转义必炸）：本地写 `.ps1` → scp → `-File` 跑；`schtasks /tr "长命令"` 同理，改用 `.bat`。
9. 计划任务里 `powershell … > log` **抓不到 `Write-Host`**（走 information 流）→ 日志永远 0 字节；用 `Invoke-Expression $s *>> log`。
10. 判断一条 ssh 通道是否真的还通，必须 `ssh -o ControlPath=none -o ControlMaster=no`——否则会被 ControlMaster 复用（`ControlPersist 300`）骗过去。
11. 解析 JSON 别写死「冒号后紧跟引号」：服务端是 `"port": 123`（**冒号后有空格**）→ `sed` 要写 `[ ]*`（`onboard-sh.sh` 原有 bug，害得 Linux 目标机一律「登记失败」）。
12. 调接口走对前缀：`/api/join/*` **不能**写成 `/join/*`——Caddy 只给 `/join/onboard*`、`/join/offboard*` 建了路由，其余落静态站 → 404；而 `curl -f` 失败 + `|| return 0` 的 fail-safe 会把 404 当成「还活着」，**静默掩盖** bug。
13. `PermitListen` 端口段 22022–22039 已放行；超出要改 `60-guga-tunnel.conf` 再 reload ssh。
14. **Windows PowerShell 5.1 不支持 `&&`**（五号默认 shell 就是它）→ 远程执行命令用 `;` 分隔；报错长相是「`&&` 不是此版本中的有效语句分隔符」。
15. **别在双引号 here-string（`@"…"@`）里写含 `$变量:` 的注释**——PowerShell 会把它当成「作用域限定」→ 整份脚本解析失败，报错行号指向注释本身（`onboard-windows.ps1` 第 185 行就这么崩的，害得接入脚本一跑就死）。改法：别让 `$` 紧跟冒号（改写措辞或加花括号）。
16. 远程 ssh 进 Windows 时 **`Get-Process` 看不到主人桌面上的窗口**（不在同一个会话）——界面自动化必须让脚本跑在主人的登录会话里（计划任务），别指望在 ssh 会话里看得见窗口。

## 4. 清场与顺序类教训

- **清理目标机时先分清「谁的目录」**：`C:\guga\` 是**自有隧道**保活脚本 `keep-tunnel.ps1` 的家（计划任务 `guga-tunnel` 指向它）；做六号真机测试清 `C:\guga` 曾把它一起清掉——任务还在、脚本没了，任务一起来就退出，`Get-ScheduledTask` 显示 **State=Ready**（不是 Running），表现就是「机器在线但服务器连不进去」。修法：重跑 `onboard-windows.ps1 -Port <该机端口>`（幂等，会重建脚本与任务）。
- **onboard 脚本有两份副本**：`~/stack/hub/onboard-windows.ps1`（hub 供下载的那份，主人实际跑的）与 `~/stack/remote/onboard-windows.ps1`（源副本）——改一处必须同步另一处，否则下次从 hub 下载的还是坏的。
- `Stop-ScheduledTask` 停的就是**脚本自己** → 必须放**最后**；注销计划任务放**最前**。
- 清理 `authorized_keys` 别用 `-notmatch 'guga-join'` 这类宽过滤——会把自有机器那条 `guga-ops@cloud` 一起删掉（五号自有通道当场断，还被 ControlMaster 骗着没发现）。每次 join 装的都是**当场生成的一次性 ops 公钥**（`/claim` 返回 `_gen_keypair()` 那把，注释 `guga-join@cloud`），脚本里的 dedupe 只按自己的 base64 比 → **旧的会累积**。
- 验证「拆干净」不能只看进程名，要同时查公钥行数、tmpfs（`/run/guga-join/authorized_keys`）、计划任务。

## 5. 常驻入口 / 令牌（可复用规律）

- **别在页面加载时预签 token**：开几次就把名额挤满（`/create` 全 429）。改成**用户点「同意」才签**，并且不同入口的名额**分开算**（用 `src` 字段区分）。
- 终态 token（expired/revoked）过 `TOKEN_KEEP`(=3×TTL) 自动回收，免得常驻入口把内存撑大。
- 公网服务**永远不要**把带密钥、带密码明文的接口放进白名单（如 `/settings`）；密码文件不能放 `/etc/guga/`（root 且带 admin 密钥）→ 用 systemd `StateDirectory=`（自动建 `/var/lib/<名>` 并进 ReadWritePaths）。
- 服务器杀不掉别人机器上已建立的隧道（受限账户 + 非 root）：撤销要**由目标机自己拆**，靠它轮询 `GET /api/join/alive?t=`；客户端判断要**只在服务器明确回 `no` 时**才算会话没了，curl 失败（网断/重启）一律当「还活着」。

## 6. 给「要主人扫码」的活儿留余地

- 主人扫码期间**不要反复重载登录页**——每次重载都作废他手上那张二维码（做过「每 70 秒自动换新码」的循环，害得主人连扫三次都提示「二维码失效」）。抓一张、发布、然后**别动页面**，等他自己说扫完。
- 二维码截图**可以**当码用（他扫的是屏幕上的图片，等价），但要在**手机上点「确认登录」**才算登入；他说「好了」却仍在登录页，先想到这条。
- 「自动续期」要挑不打扰的时机（例：每天一次的探针），别在主人扫码时高频动页面。
- 要图给主人看（hub 聊天走 runs 通道，**不认 `MEDIA:` 标签**）：放 hub 静态目录 + 给可点链接（如 `/workbuddy-qr.html`），别贴服务器路径。

## 7. 给主人送文件的落地点：笔记本 `D:\咕嘎5号\`

- 主人 2026-10-25 定：**往后一号要给他的文件都传到五号笔记本的 `D:\咕嘎5号\`**，不再散落。简历在子目录 `简历\`。
- 工具：`~/.hermes/scripts/push_guga5.sh [-s 子目录] 文件...`；`-l [子目录]` 看那边目录。别再手搓 scp。
- Windows OpenSSH 默认是 PowerShell 5.1：命令里用 `;` 不用 `&&`；输出中文要先 `chcp 65001` + `[Console]::OutputEncoding=[Text.Encoding]::UTF8`，否则回显是 GBK 乱码。
- 中文文件名可以走 ssh/scp（UTF-8 直通），但**命令里要建含中文的目录**时，稳妥做法是用 `[char]0x5495+[char]0x560E+...` 拼，避免终端编码差异。
- 传完必核 md5（`Get-FileHash -Algorithm MD5` 对 `md5sum`），别看「已发送」就当成功。

## 8. GitHub 代码托管（2026-10-25 起）

- 账号 `im-DQM`（主人本人），**认证只走 SSH**：服务器私钥 `~/.ssh/guga_github`（ed25519，已登记在他账号）。**主机 443 到 github.com 不通、22 通**，所以 HTTPS 克隆/推送会卡死，一律用 `git@github.com:` 形式。
- 两个仓库：`im-DQM/guga`（整站源码 + 咕嘎系统：site/ platform/ guga-system/ docs/）、`im-DQM/dqm-mini-Llama`（C++ 推理内核，代码在 `sampler` 分支，`main` 与它同步；`models/chat/*.gguf` 不入库）。
- **服务器上不留仓库副本**（主人 2026-10-25 要求省空间）：`~/.hermes/scripts/guga_repo_push.sh` 会临时 clone 到 scratch、rsync 覆盖、提交推送、自动删临时目录。改完网站跑一次即可。
- 笔记本上的源码在 WSL：`/home/mqd/mini-llama/dqm-mini-llama`（`mini-llama-cpp` 是另一份 1.1G 的副本）。WSL 里没配 GitHub 密钥，**推法**：`git bundle create /tmp/x.bundle --all` → `cp` 到 `/mnt/e/` → 服务器 `scp win-asus:E:/x.bundle` → 以 bundle 为源推 GitHub → 删掉两端临时文件。
- 传密码/令牌一律不做：主人给的密码不进对话、不进配置，要权限就用 SSH 密钥或 fine-grained PAT。
