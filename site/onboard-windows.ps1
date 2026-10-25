<#
  Guga 远程操作 —— Windows 目标机一键接入（自有机器，长期可用）
  ============================================================
  以【管理员 PowerShell】运行。可重复运行（幂等）。

  做这些事：
    1. 安装并启动 OpenSSH Server（优先用系统可选功能；不行则用微软官方 Win32-OpenSSH 包）
    2. 防火墙放行 22
    3. 默认 shell 设为 PowerShell（避免 cmd 的引号 / 中文编码坑）
    4. 把服务器的 ops 公钥装进正确位置（管理员账户 vs 普通账户两套规则）
    5. 在本机生成一把"隧道密钥"（私钥留在本机，不外传）
    6. 建一个计划任务，保活"反向隧道"——让服务器能连回这台机器

  跑完会打印一段【可直接复制粘贴给咕嘎】的登记信息，发过去即可。

  对应服务器侧环境：106.55.38.108，受限隧道账户 tunnel。
  每台机器的回环端口必须不同，用 -Port 指定（服务器已放行 22022-22025）。
#>

param(
  [string]$ZipPath = '',   # 可选：已手动下载好 OpenSSH-Win64.zip 时，用 -ZipPath <路径> 指定
  [int]$Port = 22022       # 这台机器在服务器上的回环端口（每台机必须不同；服务器已放行 22022-22025）
)

$ErrorActionPreference = 'Stop'

# ---------- 可调参数（服务器侧已按此配置，一般不用改）----------
$ServerHost  = '106.55.38.108'
$ServerUser  = 'tunnel'          # 服务器上的受限隧道账户
$ServerPort  = 22
$ReversePort = $Port             # 服务器回环端口，须与服务器 permitlisten 一致（由 -Port 指定）
$OpsPubKey   = 'ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIEx74uiggtJG+54dgMQDcZsUBdYFp6pnVeVxI+UBeJv0 guga-ops@cloud'
$TunnelKey   = Join-Path $env:USERPROFILE '.ssh\guga_tunnel'
$KeepScript  = 'C:\guga\keep-tunnel.ps1'
$TaskName    = 'guga-tunnel'
# ----------------------------------------------------------------

function Say($m) { Write-Host "  $m" }
function Ok($m)  { Write-Host "  [OK] $m" -ForegroundColor Green }
function Warn($m){ Write-Host "  [!] $m" -ForegroundColor Yellow }

# ---- 0. 必须管理员 ----
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
  Write-Host "请用【管理员】PowerShell 运行本脚本（右键 PowerShell -> 以管理员身份运行）。" -ForegroundColor Red
  exit 1
}

Write-Host "`n=== Guga Windows 接入 ===`n"

# ---- 1. OpenSSH Server ----
Write-Host "[1/6] 确保 OpenSSH Server 可用"
if (Get-Service sshd -ErrorAction SilentlyContinue) {
  Ok "sshd 服务已存在（跳过安装）"
} else {
  $haveIt = $false
  try {
    $cap = Get-WindowsCapability -Online -Name 'OpenSSH.Server*' -ErrorAction Stop | Select-Object -First 1
    if ($cap -and $cap.State -eq 'Installed') { $haveIt = $true; Ok "系统可选功能里已安装（跳过）" }
  } catch { Warn "查询可选功能失败" }

  if (-not $haveIt) {
    # 优先从 hub 拉（走你已经通的 SSH 隧道，最快最稳）；失败再依次试加速镜像 / GitHub 直连
    $zip = "$env:TEMP\OpenSSH-Win64.zip"
    $dst = "$env:ProgramFiles\OpenSSH"
    if ($ZipPath) {
      if (-not (Test-Path -LiteralPath $ZipPath)) { throw "找不到指定的 zip：$ZipPath" }
      Copy-Item -LiteralPath $ZipPath -Destination $zip -Force
      Ok "使用你提供的本地包"
    } else {
      $urls = @(
        'http://localhost:8080/OpenSSH-Win64.zip',
        'https://gh-proxy.com/https://github.com/PowerShell/Win32-OpenSSH/releases/latest/download/OpenSSH-Win64.zip',
        'https://github.com/PowerShell/Win32-OpenSSH/releases/latest/download/OpenSSH-Win64.zip'
      )
      $oldPref = $ProgressPreference; $ProgressPreference = 'SilentlyContinue'   # 画进度条会拖慢几十倍
      [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
      $got = $false
      foreach ($u in $urls) {
        try { Warn "下载 OpenSSH 包：$u"; Invoke-WebRequest -Uri $u -OutFile $zip -UseBasicParsing -TimeoutSec 120; $got = $true; break }
        catch { Warn "  这个源不行，换下一个" }
      }
      $ProgressPreference = $oldPref
      if (-not $got) {
        Write-Host "  所有源都失败。手动下载 OpenSSH-Win64.zip 后运行：powershell -ExecutionPolicy Bypass -File <本脚本> -ZipPath <zip路径>" -ForegroundColor Red
        throw "OpenSSH 包下载失败"
      }
      Ok "下载完成"
    }
    Remove-Item $dst -Recurse -Force -ErrorAction SilentlyContinue
    Expand-Archive -Path $zip -DestinationPath $dst -Force
    & (Join-Path $dst 'OpenSSH-Win64\install-sshd.ps1')
    Ok "已用官方包安装 sshd"
  }
}
Set-Service -Name sshd -StartupType Automatic
if ((Get-Service sshd).Status -ne 'Running') { Start-Service sshd }
Ok "sshd 已启动并设为开机自启"

# ---- 2. 防火墙 ----
Write-Host "[2/6] 放行防火墙 22"
if (-not (Get-NetFirewallRule -Name 'guga-sshd' -ErrorAction SilentlyContinue)) {
  New-NetFirewallRule -Name 'guga-sshd' -DisplayName 'OpenSSH Server (sshd)' `
    -Enabled True -Direction Inbound -Protocol TCP -Action Allow -LocalPort 22 -Profile Any | Out-Null
  Ok "已添加规则"
} else { Ok "规则已存在（跳过）" }

# ---- 3. 默认 shell -> PowerShell ----
Write-Host "[3/6] 设置默认 shell"
$psExe = (Get-Command pwsh.exe -ErrorAction SilentlyContinue).Source
if (-not $psExe) { $psExe = "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe" }
if (-not (Test-Path 'HKLM:\SOFTWARE\OpenSSH')) { New-Item -Path 'HKLM:\SOFTWARE\OpenSSH' -Force | Out-Null }
New-ItemProperty -Path 'HKLM:\SOFTWARE\OpenSSH' -Name DefaultShell `
  -Value $psExe -PropertyType String -Force | Out-Null
Ok "默认 shell = $psExe"

# ---- 4. 装服务器 ops 公钥 ----
Write-Host "[4/6] 安装服务器公钥"
$userIsAdmin = $isAdmin   # 用了管理员令牌 => 该账户在 Administrators 组
if ($userIsAdmin) {
  $akf = Join-Path $env:ProgramData 'ssh\administrators_authorized_keys'
  if (-not (Test-Path $akf)) { New-Item -Path $akf -ItemType File -Force | Out-Null }
  $existing = (Get-Content $akf -ErrorAction SilentlyContinue) -join "`n"
  if ($existing -notmatch [regex]::Escape(($OpsPubKey -split ' ')[1])) {
    Add-Content -Path $akf -Value $OpsPubKey -Encoding ascii
    Ok "已写入 $akf"
  } else { Ok "公钥已存在（跳过）" }
  # ACL：只允许 Administrators 与 SYSTEM，且不继承 —— 否则 sshd 忽略该文件
  icacls.exe $akf /inheritance:r /grant 'Administrators:F' /grant 'SYSTEM:F' | Out-Null
  Ok "已修正 ACL"
} else {
  $sshDir = Join-Path $env:USERPROFILE '.ssh'
  if (-not (Test-Path $sshDir)) { New-Item -ItemType Directory -Path $sshDir | Out-Null }
  $akf = Join-Path $sshDir 'authorized_keys'
  $existing = (Get-Content $akf -ErrorAction SilentlyContinue) -join "`n"
  if ($existing -notmatch [regex]::Escape(($OpsPubKey -split ' ')[1])) {
    Add-Content -Path $akf -Value $OpsPubKey -Encoding ascii
    Ok "已写入 $akf"
  } else { Ok "公钥已存在（跳过）" }
}
Restart-Service sshd
Ok "sshd 已重启以生效"

# ---- 5. 生成隧道密钥（私钥留在本机）----
Write-Host "[5/6] 生成隧道密钥"
if (Test-Path $TunnelKey) {
  Ok "已存在，复用：$TunnelKey"
} else {
  New-Item -ItemType Directory -Path (Join-Path $env:USERPROFILE '.ssh') -Force | Out-Null
  # 用系统自带 ssh-keygen 生成，无口令。
  # 经 cmd 调用：PowerShell 5.1 会把空字符串参数吞掉，导致 -N 拿不到值。
  $kcmd = 'ssh-keygen -t ed25519 -f "{0}" -C "guga-tunnel-{1}" -N "" -q' -f $TunnelKey, $env:COMPUTERNAME
  cmd /c $kcmd
  Ok "已生成：$TunnelKey"
}
$TunnelPub = (Get-Content "$TunnelKey.pub").Trim()

# 预置 known_hosts，免得首次连接要人工确认
$kh = Join-Path $env:USERPROFILE '.ssh\known_hosts'
try {
  $scan = & ssh-keyscan -p $ServerPort $ServerHost 2>$null
  if ($scan) { Add-Content -Path $kh -Value $scan -Encoding ascii; Ok "已预置 known_hosts" }
} catch { Warn "known_hosts 预置失败（首次连接会自动接受）" }

# ---- 6. 建反向隧道保活计划任务 ----
Write-Host "[6/6] 建立反向隧道保活计划任务"
New-Item -ItemType Directory -Path (Split-Path $KeepScript) -Force | Out-Null

# 用 ssh.exe 的绝对路径：计划任务的环境里 PATH 常常不全，裸写 ssh 会静默失败
$sshExe = (Get-Command ssh.exe -ErrorAction SilentlyContinue).Source
if (-not $sshExe) {
  foreach ($c in @("$env:SystemRoot\System32\OpenSSH\ssh.exe", "$env:ProgramFiles\OpenSSH\OpenSSH-Win64\ssh.exe")) {
    if (Test-Path $c) { $sshExe = $c; break }
  }
}
if (-not $sshExe) { throw "找不到 ssh.exe，无法建立隧道" }
Ok "ssh.exe = $sshExe"
$logFile = Join-Path $env:USERPROFILE '.ssh\guga-tunnel.log'

$loop = @"
# 由 Guga 接入脚本生成 —— 保活反向隧道：把本机 22 暴露到服务器的回环端口 $ReversePort
`$ErrorActionPreference = 'Continue'
`$ssh = '$sshExe'
while (`$true) {
  # 注意 ${ReversePort} 必须带花括号：不带花括号、后面又直接跟冒号，会被 PowerShell 当成作用域限定，转发规格整段被吃掉
  & `$ssh -N -o ServerAliveInterval=30 -o ServerAliveCountMax=3 -o ExitOnForwardFailure=yes -o StrictHostKeyChecking=accept-new -i "`$env:USERPROFILE\.ssh\guga_tunnel" -R ${ReversePort}:localhost:22 $ServerUser@$ServerHost 2>&1 | Out-File -Append -Encoding utf8 "$logFile"
  Start-Sleep -Seconds 10
}
"@
Set-Content -Path $KeepScript -Value $loop -Encoding UTF8

Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
$action  = New-ScheduledTaskAction -Execute $psExe -Argument "-WindowStyle Hidden -ExecutionPolicy Bypass -File `"$KeepScript`""
$trigger = New-ScheduledTaskTrigger -AtLogOn
$set     = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $set -RunLevel Highest -Force | Out-Null
Start-ScheduledTask -TaskName $TaskName
Ok "计划任务 '$TaskName' 已注册并启动"

Start-Sleep -Seconds 3
Write-Host ""
Write-Host "=========== 把下面这整段复制，发给咕嘎 ===========" -ForegroundColor Cyan
Write-Host ""
Write-Host "接入新机器：端口 $ReversePort，用户名 $env:USERNAME"
Write-Host "隧道公钥：$TunnelPub"
Write-Host ""
Write-Host "=================================================" -ForegroundColor Cyan
Write-Host "`n咕嘎登记完就能远程操作这台机器了。`n"
