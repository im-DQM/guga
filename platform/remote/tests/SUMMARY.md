# 咕嘎群 + 手机版收尾小结（2026-10-13）

干完了，咕嘎一号。下面是小结。

---

## 一、改了什么（改最小必要处，保持原设计语言）

### `~/stack/hub/group.html`

**正确性（日期分隔）** — `appendNew()` 原来靠 `main.querySelector('.daysep')`「页面上有没有分隔条」判断要不要插日期分隔，跨天 / 空态切换时就错了（昨天一条、今天再来就不补「今天」）。
- 新增 `dayLabel()`/`makeSep()` 帮助函数（:170 区），并把「最后一天」记进模块级 `lastDayKey`（:124）；`render()`（:203/211）与 `appendNew()`（:237）统一改成 **`dayKey(ts)!==lastDayKey` 才补分隔**。

**并发（轮询去重、防回退）** — `poll()` 原来 `lastId=list[last].id`：3 秒轮询和「用户刚发的乐观插入」并发、两次请求乱序返回时，旧的响应会把 `lastId` 顶回去，下一轮就把同一条**重复补**进 DOM。
- `poll()`（:261-273）加**请求序号** `pollSeq/appliedSeq`，过期响应直接丢（:267）；`lastId` 改为**只前进不回退**（`if(maxId>lastId) lastId=maxId`，:273）。乐观插入那条也不再被重复补。

**移动端 / 无障碍**
- 输入框 `font-size:15px→16px`（:71）—— 防 iOS 聚焦时自动放大页面。
- 补 `:active` 反馈：`.back`(:28)、`.hlink`(:34)、`.opt`(:58)、`.btn`(:76)（手机没有 hover，原来点下去没反馈）。
- 装饰性 svg 全部 `aria-hidden="true" focusable="false"`；返回链接补 `aria-label`。
- 新增 `visualViewport` 跟随（:340），iOS 键盘弹起时把 body 高度改成可视高度，**输入框不会被键盘顶住**。
- 安全：原本就全部走 `paint()`/`textContent`，链接正则只收 `http(s)`，无 `innerHTML` 拼用户内容 —— 已复核，无需改。

### `~/stack/hub/m.html`

- **修了一个真 bug**：底部「回到最新」按钮原来写在 `<footer>` **外面**，`.tobottom{position:absolute;bottom:calc(100% + 10px)}` 会按**视口**算 → 实际被顶到屏幕外，永远看不见。已把它**移进 `<footer>`**（:160，footer 本身 `position:relative`，:101），位置才对。
- 顺带把它 `<div>` 改成 `<button type="button">`（可聚焦、可读屏），补 `:active`、`cursor`、`padding:0`。
- 补 `.btn:active`(:109)、`.btn.send.stop`(:112，发送键变停止时的配色反馈)、`.sess:active`(:133)、`.newbtn:active`、`.ack:active`。
- 装饰 svg 加 `aria-hidden`（含 `IC_SEND`/`IC_STOP` 注入的那两个）。
- `refreshSessions` 里 `s.id.startsWith('cron')` 加空值保护（`s&&s.id&&!String(s.id).startsWith(...)`），避免脏数据崩。
- 同样加 `visualViewport` 跟随。

**没动**：`Caddyfile`、`index.html`、`remote-api.py`、`memories/`、`todos.md`；没 `sudo`、没重启任何服务。

---

## 二、跑了什么验证（真实结果）

**1. `node --check`（抽出 `<script>` 检查）** —— 两个页面都通过：
```
group.html   node --check 通过
m.html       node --check 通过
```

**2. headless chromium 截图** → `~/workspace/out/`：`group-m.png`、`group-d.png`、`m-m.png`、`m-d.png`
- 附带发现：`--headless=new` 会把**窗口最小宽度卡在 500px**（量到 `innerWidth=500 docSW=500`），所以直接 `--window-size=390` 出来的 390 图其实是 500 布局的裁切，**不是页面有横向溢出**。我改用「390px iframe + 纯 stdlib 裁图」拿到**真·390 渲染**，并逐元素量过：`docSW==iw==390`，**除设计上就横向滚动的成员条外，没有任何元素越界**。真机要点全部成立：`今天` 分隔、长链接 `break-all` 换行、底部输入条到位。

**3. 测试脚本 `~/workspace/out/test_group_api.py`（只用 stdlib，真发真删、自清）** —— 实跑输出：

```
起点 last_id=7（count=7, members=7）
  PASS 发言→读回：POST 成功  — id=8
  PASS 发言→读回：text/who/kind/via/ts 一致
  PASS 未知发言人：返回 400  — '发言人要是群名单里的：主人、咕嘎一号…'
  PASS 空正文(空串/纯空白)：返回 400  — '正文不能是空的'
  PASS via 非法值：收敛成「本人」    PASS via 合法值：代发保留
  PASS busy：置位 / GET 读到 / 清零 / GET 为空
  PASS delete：删存在的 removed=1；删不存在 removed=0；id 非数字 400
  PASS group.json：仍是合法 JSON；id 严格单调递增 [1,2,3]…[14,15,16]；next_id=17 领先 max=16
【收尾】已删 8 条；残留带标记的 0 条；他人新增 0 条
==== 结果：25/25 通过 ====    清场：干净，没留垃圾     退出码=0
```
清场后复查：群里仍是 **7 条 / last_id=7 / 无 `[自测]` 残留**（测试消息统一用「咕嘎六号」发，避免触发信使回话）。脚本只删**自己造的** id，不碰主人在测试期间发的消息。

---

## 三、工程文档
`~/.hermes/knowledge/projects/guga-group.md`（照 `guga-hub.md` 风格）。覆盖：是什么 / 文件与路径表 / 接口与数据结构（含**id 只增不回收**、2000/400/4000 上限）/ 信使「谁回、什么时候回」的三条条件 / 怎么加成员 / 怎么代发 / 怎么验证排查（含日志位置）/ 已知限制与下一步。`knowledge/README.md` 的索引里**本来就已有**这条，无需再改。

---

## 四、还剩什么 / 建议
1. **`::sysinfo` 我按「剥掉不画卡片」保留**：群里放资源面板不合适，且信使的 instructions 明确叫咕嘎别发。与 `index.html`/`m.html` 画卡片**有意不同**，已在文档里写明。若你觉得群里也该出面板，说一声，我把那 ~30 行 CSS 搬过去。
2. **iOS 键盘 / 安全区**只能在真机确认 —— 我加的是 `visualViewport` 跟随（业界常用解），headless 里验证不到，建议你手机过一眼。
3. 上面那条「每个咕嘎独立 token 的公网入口」仍是**基础设施改动，等你点头**才动，没碰。
4. 「回到最新」按钮修好后，**建议真机点一下**确认浮在输入框上方位置合适（headless 里那个按钮 `display:none` 起，量不到展示态）。

交付物都在 `~/workspace/out/`（截图 4 张 + `test_group_api.py`）；文档已直接写进 `~/.hermes/knowledge/projects/guga-group.md`。
