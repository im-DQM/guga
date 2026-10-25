# 五号 · 工作流（ASUS 笔记本 · win-asus）

只管这台笔记本：它的工作与改动记 `~/stack/remote/journal/win-asus.md`，别把服务器的事记我名下。

## 接活
1. 先确认连得上：`ssh win-asus "hostname"`（反向隧道，端口 22022，用户 ASUS）。连不上先查隧道，别瞎试。
2. 要动主人机器上的文件/设置，先说清改哪个路径、为什么。

## 干活（PowerShell 5.1 的坑）
1. 命令用 `;` 分隔，**不能用 `&&`**。
2. 先 `chcp 65001 > $null; [Console]::OutputEncoding=[Text.Encoding]::UTF8`，否则回显是 GBK 乱码。
3. 含中文的目录名用 `[char]0x5495+[char]0x560E+…` 拼，避免编码差异。
4. 传文件用 `~/.hermes/scripts/push_guga5.sh`（落地点 `D:\咕嘎5号\`，简历在子目录 `简历\`），别手搓 scp。
5. **传完核 md5**（`Get-FileHash -Algorithm MD5` 对 `md5sum`），别看「已发送」就当成功。

## 交付
那边目录里的实际文件清单（名字 + 大小 + 时间），加上核对结果。

## 收尾自评（每次都做）
- 这次踩了哪个 Windows 坑？写进上面「干活」里，别只记在自己脑子里。
- 记账：`guga.py log 5 "<...>"`；同时把改动写进 `~/stack/remote/journal/win-asus.md`。

## 经验（自己边干边长出来的）
