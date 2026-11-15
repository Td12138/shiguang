# 部署到 cloudserver200m：本地构建 → 打包 → 上传 → 远端解包定权 → 切软链 → 重启 → 健康门（失败自动回滚）
# 用法：
#   pwsh -File scripts/deploy.ps1                 # 增量发布（保留最近 3 个 release）
#   pwsh -File scripts/deploy.ps1 -FirstRun       # 首次安装（建 shiguang 用户/venv/装 systemd），之后同样走健康门
# 约定：
#   - 所有 ssh/scp 都带 BatchMode（不会卡在交互口令）、10s 连接超时、accept-new 主机指纹
#   - release 内代码 owner=root:root、目录 755、文件 644；shared 归 shiguang:shiguang
#   - 重启后 curl -fsS http://127.0.0.1:8720/api/health 必须返回 "ok":true，否则切回上一 release 并 exit 1
param(
    [switch]$FirstRun,
    [string]$ServerHost = "100.77.67.31",
    [string]$SshKey = "$env:USERPROFILE\.ssh\TDserver_200M.pem",
    [string]$RemoteRoot = "/opt/shiguang",
    [string]$ServiceName = "shiguang",
    [string]$ServiceUser = "shiguang",
    [int]$HealthPort = 8720,
    [int]$KeepReleases = 3
)

$ErrorActionPreference = "Stop"
$PSNativeCommandUseErrorActionPreference = $false  # 原生命令失败不抛，统一用 $LASTEXITCODE 判定

# ------------------------------------------------------------------ 常量
$SSH_OPTIONS = @(
    "-o", "BatchMode=yes",
    "-o", "ConnectTimeout=10",
    "-o", "StrictHostKeyChecking=accept-new"
)
# 打包前必须存在的文件（缺一个就不发布，避免把半截产物推上线）
$REQUIRED_PATHS = @(
    "apps/web/dist/index.html",
    "apps/server/requirements.txt",
    "LICENSE"
)
$INCLUDE_PATHS = @(
    "apps/server/app",
    "apps/server/scripts",
    "apps/server/mcp",
    "apps/server/requirements.txt",
    "apps/web/dist",
    "README.md",
    "LICENSE",
    "THIRD-PARTY-NOTICES.md"
)
$HEALTH_TRIES = 20      # 健康门轮询次数（每次 1 次 curl）
$HEALTH_INTERVAL = 1    # 轮询间隔秒
$HEALTH_TIMEOUT = 3     # 单次 curl 超时秒

# ------------------------------------------------------------------ 路径
$projectRoot = Split-Path -Parent $PSScriptRoot
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$releaseName = $stamp
$staging = Join-Path $env:TEMP "shiguang-$stamp"
$archive = Join-Path $env:TEMP "shiguang-$stamp.tar.gz"
$uploadDir = Join-Path $env:TEMP "shiguang-deploy-$stamp"
$remoteArchive = "/tmp/shiguang-$releaseName.tar.gz"
$remoteRelease = "$RemoteRoot/releases/$releaseName"
$remoteHealthUrl = "http://127.0.0.1:$HealthPort/api/health"
$previousRelease = ""

function Write-Step {
    param([string]$Text)
    Write-Host ""
    Write-Host "== $Text" -ForegroundColor Cyan
}

function Write-Info {
    param([string]$Text)
    Write-Host "   $Text"
}

function Fail {
    param([string]$Text)
    throw $Text
}

# 把脚本经 stdin 交给远端 bash：避免多层引号与 $ 展开地狱；换行统一 LF，避免 bash 读到 \r
function ConvertTo-RemoteText {
    param([Parameter(Mandatory)][string]$Script)
    return ((($Script -replace "`r`n", "`n").TrimEnd()) + "`n")
}

function Invoke-Remote {
    param([Parameter(Mandatory)][string]$Script)
    ConvertTo-RemoteText $Script | & ssh -i $SshKey @SSH_OPTIONS "root@$ServerHost" "bash -s" | Out-Host
    if ($LASTEXITCODE -ne 0) { Fail "远端脚本失败（退出码 $LASTEXITCODE）" }
}

function Invoke-RemoteCapture {
    param([Parameter(Mandatory)][string]$Script)
    $output = @(ConvertTo-RemoteText $Script | & ssh -i $SshKey @SSH_OPTIONS "root@$ServerHost" "bash -s")
    $code = $LASTEXITCODE
    return [pscustomobject]@{ ExitCode = $code; Lines = $output }
}

try {
    # ------------------------------------------------------------ 1/6 预检
    Write-Step "[1/6] 预检：SSH、远端命令、上一 release"
    if (-not (Test-Path -LiteralPath $SshKey)) { Fail "找不到 SSH 私钥：$SshKey" }

    $preflightScript = @'
set -uo pipefail
fail=0
for bin in curl systemctl tar readlink bash; do
  command -v "$bin" >/dev/null 2>&1 || { echo "missing: $bin"; fail=1; }
done
[[ "${EUID:-1}" -eq 0 ]] || { echo "not-root"; fail=1; }
APP_ROOT="__APP_ROOT__"
[ -d "$APP_ROOT/shared" ] && echo "shared: ok" || echo "shared: missing"
[ -d "$APP_ROOT/shared/upload" ] && echo "upload: ok" || echo "upload: missing"
[ -d "$APP_ROOT/venv" ] && echo "venv: ok" || echo "venv: missing"
if id -u __SERVICE_USER__ >/dev/null 2>&1; then echo "user: ok"; else echo "user: missing"; fi
echo "prev=$(readlink -f "$APP_ROOT/current" 2>/dev/null || true)"
exit "$fail"
'@
    $preflightScript = $preflightScript.Replace("__APP_ROOT__", $RemoteRoot).Replace("__SERVICE_USER__", $ServiceUser)
    $preflight = Invoke-RemoteCapture $preflightScript
    foreach ($line in $preflight.Lines) { if ("$line".Trim() -ne "") { Write-Info "$line" } }
    if ($preflight.ExitCode -ne 0) { Fail "预检失败：远端缺命令或不是 root（检查密钥/主机）" }

    $prevLine = @($preflight.Lines | Where-Object { "$_" -like "prev=*" })[0]
    $previousRelease = if ($prevLine) { ("$prevLine" -replace "^prev=", "").Trim() } else { "" }
    if ($previousRelease) { Write-Info "上一 release: $previousRelease" } else { Write-Info "上一 release: <无，首次发布>" }

    if (-not $FirstRun) {
        $preflightText = ($preflight.Lines -join "`n")
        if ($preflightText -match "venv: missing" -or $preflightText -match "user: missing") {
            Fail "远端尚未初始化（缺 venv 或 $ServiceUser 用户）：首次部署请加 -FirstRun"
        }
    }

    # ------------------------------------------------------------ 2/6 依赖与构建
    Write-Step "[2/6] 依赖与构建（apps/web）"
    if (-not (Get-Command pnpm -ErrorAction SilentlyContinue)) { Fail "本机找不到 pnpm" }
    $webDir = Join-Path $projectRoot "apps/web"
    Push-Location $webDir
    try {
        & pnpm install --frozen-lockfile
        if ($LASTEXITCODE -ne 0) { Fail "pnpm install --frozen-lockfile 失败（退出码 $LASTEXITCODE）" }
        & pnpm build
        if ($LASTEXITCODE -ne 0) { Fail "pnpm build 失败（退出码 $LASTEXITCODE）" }
    } finally {
        Pop-Location
    }

    foreach ($rel in $REQUIRED_PATHS) {
        $full = Join-Path $projectRoot $rel
        if (-not (Test-Path -LiteralPath $full)) { Fail "必需文件缺失：$rel（构建或仓库不完整，停止发布）" }
    }
    Write-Info "构建产物与必需文件齐全"

    # ------------------------------------------------------------ 3/6 打包
    Write-Step "[3/6] 打包 $releaseName"
    New-Item -ItemType Directory -Force -Path $staging | Out-Null
    foreach ($item in $INCLUDE_PATHS) {
        $src = Join-Path $projectRoot $item
        if (-not (Test-Path -LiteralPath $src)) { Fail "打包清单中的路径不存在：$item" }
        $dest = Join-Path $staging $item
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $dest) | Out-Null
        Copy-Item -Recurse -Force -LiteralPath $src -Destination $dest
    }
    Get-ChildItem -Path $staging -Recurse -Directory -Filter "__pycache__" -ErrorAction SilentlyContinue |
        Remove-Item -Recurse -Force
    Get-ChildItem -Path $staging -Recurse -Filter "*.pyc" -File -ErrorAction SilentlyContinue |
        Remove-Item -Force

    & tar -czf $archive -C $staging .
    if ($LASTEXITCODE -ne 0) { Fail "tar 打包失败（退出码 $LASTEXITCODE）" }
    Write-Info ("包大小: {0:N1} MB" -f ((Get-Item -LiteralPath $archive).Length / 1MB))

    # ------------------------------------------------------------ 4/6 上传
    Write-Step "[4/6] 上传到 ${ServerHost}:$remoteArchive"
    & scp -i $SshKey @SSH_OPTIONS $archive "root@${ServerHost}:$remoteArchive"
    if ($LASTEXITCODE -ne 0) { Fail "scp 上传失败（退出码 $LASTEXITCODE）" }

    # ------------------------------------------------------------ 5/6 解包与定权
    Write-Step "[5/6] 远端解包、定权（umask 022 / 目录 755 / 文件 644）"
    $extractScript = @'
set -euo pipefail
umask 022
APP_ROOT="__APP_ROOT__"
RELEASE="__RELEASE__"
ARCHIVE="__ARCHIVE__"
SERVICE_USER="__SERVICE_USER__"

[ -f "$ARCHIVE" ] || { echo "缺少上传包: $ARCHIVE" >&2; exit 1; }

mkdir -p "$APP_ROOT/releases" "$APP_ROOT/shared/upload"
chown root:root "$APP_ROOT" "$APP_ROOT/releases"
chmod 755 "$APP_ROOT" "$APP_ROOT/releases"

rm -rf -- "$RELEASE"
mkdir -p "$RELEASE"
tar -xzf "$ARCHIVE" -C "$RELEASE"
rm -f -- "$ARCHIVE"

find "$RELEASE" -type d -exec chmod 755 {} +
find "$RELEASE" -type f -exec chmod 644 {} +
chown -R root:root "$RELEASE"
# 脚本入口保留可执行位（仍只有属主可写）
if [ -d "$RELEASE/apps/server/scripts" ]; then
  find "$RELEASE/apps/server/scripts" -maxdepth 1 -type f \( -name '*.py' -o -name '*.sh' \) -exec chmod 755 {} +
fi

# .env 只在 shared 里有一份（640 root:shiguang），release 内放软链
ln -sfn "$APP_ROOT/shared/.env" "$RELEASE/apps/server/.env"
chown -h root:root "$RELEASE/apps/server/.env"

# shared 归服务用户；.env 例外保持 root:shiguang 640（服务用户组只读）
# 首次运行时用户还不存在：shared 归属交给紧随其后的 install.sh
if id -u "$SERVICE_USER" >/dev/null 2>&1; then
  touch "$APP_ROOT/shared/app.db"
  chown -R "$SERVICE_USER:$SERVICE_USER" "$APP_ROOT/shared"
  chmod 750 "$APP_ROOT/shared" "$APP_ROOT/shared/upload"
  if [ -f "$APP_ROOT/shared/.env" ]; then
    chown root:"$SERVICE_USER" "$APP_ROOT/shared/.env"
    chmod 640 "$APP_ROOT/shared/.env"
  fi
  chown "$SERVICE_USER:$SERVICE_USER" "$APP_ROOT/shared/app.db"
  chmod 640 "$APP_ROOT/shared/app.db"
  # -wal/-shm 也收紧（旧线上可能是 666）
  chown "$SERVICE_USER:$SERVICE_USER" "$APP_ROOT/shared"/app.db* 2>/dev/null || true
  chmod 640 "$APP_ROOT/shared"/app.db* 2>/dev/null || true
else
  echo "提示: 系统用户 $SERVICE_USER 不存在，shared 归属由 install.sh 处理（首次部署请带 -FirstRun）" >&2
fi

echo "release 权限:"
find "$RELEASE" -maxdepth 2 -printf '%M %u:%g %p\n' | sed -n '1,8p'
'@
    $extractScript = $extractScript.Replace("__APP_ROOT__", $RemoteRoot).
        Replace("__RELEASE__", $remoteRelease).
        Replace("__ARCHIVE__", $remoteArchive).
        Replace("__SERVICE_USER__", $ServiceUser)
    Invoke-Remote $extractScript

    # ------------------------------------------------------------ 6/6 首次安装 / 切换重启 + 健康门
    if ($FirstRun) {
        Write-Step "[6/6] 首次安装：上传 install.sh + unit 并执行（幂等）"
        $installDir = Join-Path $projectRoot "deploy"
        # Windows checkout 可能是 CRLF：统一转 LF 再上传，避免远端 bash 把 \r 当命令的一部分
        New-Item -ItemType Directory -Force -Path $uploadDir | Out-Null
        foreach ($name in @("install.sh", "shiguang.service")) {
            $text = ([IO.File]::ReadAllText((Join-Path $installDir $name))) -replace "`r`n", "`n"
            [IO.File]::WriteAllText((Join-Path $uploadDir $name), $text, (New-Object Text.UTF8Encoding($false)))
        }
        Invoke-Remote @'
set -euo pipefail
mkdir -p /tmp/shiguang-deploy
'@
        & scp -i $SshKey @SSH_OPTIONS (Join-Path $uploadDir "install.sh") "root@${ServerHost}:/tmp/shiguang-deploy/install.sh"
        if ($LASTEXITCODE -ne 0) { Fail "上传 install.sh 失败（退出码 $LASTEXITCODE）" }
        & scp -i $SshKey @SSH_OPTIONS (Join-Path $uploadDir "shiguang.service") "root@${ServerHost}:/tmp/shiguang-deploy/shiguang.service"
        if ($LASTEXITCODE -ne 0) { Fail "上传 shiguang.service 失败（退出码 $LASTEXITCODE）" }

        $installScript = @'
set -euo pipefail
bash /tmp/shiguang-deploy/install.sh "__RELEASE__"
'@
        Invoke-Remote $installScript.Replace("__RELEASE__", $remoteRelease)
    } else {
        Write-Step "[6/6] 切软链、重启、健康门"
    }

    # 健康门：curl -fsS 必须拿到 "ok":true；失败切回上一 release 并 exit 1
    $gateScript = @'
set -uo pipefail
APP_ROOT="__APP_ROOT__"
RELEASE="__RELEASE__"
PREV="__PREV__"
SERVICE="__SERVICE__"
HEALTH_URL="__HEALTH_URL__"
TRIES=__TRIES__
INTERVAL=__INTERVAL__
TIMEOUT=__TIMEOUT__

ln -sfn "$RELEASE" "$APP_ROOT/current"
systemctl restart "$SERVICE"

ok=0
body=""
i=0
while [ "$i" -lt "$TRIES" ]; do
  i=$((i + 1))
  sleep "$INTERVAL"
  if body="$(curl -fsS --max-time "$TIMEOUT" "$HEALTH_URL" 2>/dev/null)" \
     && printf '%s' "$body" | grep -Eq '"ok"[[:space:]]*:[[:space:]]*true'; then
    ok=1
    break
  fi
done

if [ "$ok" -ne 1 ]; then
  echo "健康检查失败（$TRIES 次 x ${INTERVAL}s）：$HEALTH_URL" >&2
  systemctl status "$SERVICE" --no-pager -l 2>&1 | tail -n 20 >&2 || true
  journalctl -u "$SERVICE" -n 40 --no-pager 2>&1 >&2 || true
  if [ -n "$PREV" ] && [ "$PREV" != "$RELEASE" ] && [ -d "$PREV" ]; then
    echo "自动回滚到上一 release: $PREV" >&2
    ln -sfn "$PREV" "$APP_ROOT/current"
    systemctl restart "$SERVICE"
    sleep 3
    if curl -fsS --max-time "$TIMEOUT" "$HEALTH_URL" 2>/dev/null; then
      echo "回滚后健康检查通过" >&2
    else
      echo "回滚后仍不健康，需要人工介入" >&2
    fi
  else
    echo "没有可回滚的上一 release" >&2
  fi
  exit 1
fi

printf 'release=%s\nprevious=%s\ntime=%s\n' "$RELEASE" "$PREV" "$(date -Is)" > "$APP_ROOT/last-deploy.txt"
chown root:root "$APP_ROOT/last-deploy.txt"
chmod 644 "$APP_ROOT/last-deploy.txt"

echo "health: $body"
systemctl is-enabled "$SERVICE"
systemctl show "$SERVICE" -p User -p Group -p NoNewPrivileges -p ProtectSystem --no-pager
'@
    $gateScript = $gateScript.Replace("__APP_ROOT__", $RemoteRoot).
        Replace("__RELEASE__", $remoteRelease).
        Replace("__PREV__", $previousRelease).
        Replace("__SERVICE__", $ServiceName).
        Replace("__HEALTH_URL__", $remoteHealthUrl).
        Replace("__TRIES__", "$HEALTH_TRIES").
        Replace("__INTERVAL__", "$HEALTH_INTERVAL").
        Replace("__TIMEOUT__", "$HEALTH_TIMEOUT")
    Invoke-Remote $gateScript

    # ------------------------------------------------------------ 收尾：保留最近 N 个 release（清理失败不影响已上线的这次发布）
    Write-Step "收尾：清理旧 release（保留最近 $KeepReleases 个 + current + 上一版）"
    $pruneScript = @'
set -uo pipefail
APP_ROOT="__APP_ROOT__"
KEEP=__KEEP__
CURRENT_REAL="$(readlink -f "$APP_ROOT/current" 2>/dev/null || true)"
PREV_REAL="__PREV__"
mapfile -t LIST < <(ls -1 "$APP_ROOT/releases" 2>/dev/null | sort -r)
idx=0
for name in "${LIST[@]}"; do
  idx=$((idx + 1))
  path="$APP_ROOT/releases/$name"
  [ -d "$path" ] || continue
  [ "$idx" -le "$KEEP" ] && { echo "保留: $name"; continue; }
  [ "$path" = "$CURRENT_REAL" ] && { echo "保留(current): $name"; continue; }
  if [ -n "$PREV_REAL" ] && [ "$path" = "$PREV_REAL" ]; then echo "保留(上一版): $name"; continue; fi
  rm -rf -- "$path"
  echo "已清理: $name"
done
'@
    $pruneScript = $pruneScript.Replace("__APP_ROOT__", $RemoteRoot).
        Replace("__KEEP__", "$KeepReleases").
        Replace("__PREV__", $previousRelease)
    try {
        Invoke-Remote $pruneScript
    } catch {
        Write-Host "   [警告] 旧 release 清理失败（不影响本次发布）：$($_.Exception.Message)" -ForegroundColor Yellow
    }
} catch {
    Write-Host ""
    Write-Host "部署失败：$($_.Exception.Message)" -ForegroundColor Red
    if ($previousRelease) {
        Write-Host "线上当前指向可用版本：$previousRelease" -ForegroundColor Yellow
        Write-Host "手工回滚：ssh -i `"$SshKey`" root@$ServerHost `"ln -sfn $previousRelease $RemoteRoot/current && systemctl restart $ServiceName`"" -ForegroundColor Yellow
    }
    exit 1
} finally {
    # 本地临时目录/包一律清掉
    if (Test-Path -LiteralPath $staging) { Remove-Item -Recurse -Force -LiteralPath $staging -ErrorAction SilentlyContinue }
    if (Test-Path -LiteralPath $archive) { Remove-Item -Force -LiteralPath $archive -ErrorAction SilentlyContinue }
    if (Test-Path -LiteralPath $uploadDir) { Remove-Item -Recurse -Force -LiteralPath $uploadDir -ErrorAction SilentlyContinue }
}

Write-Step "完成"
Write-Info "release      : $releaseName"
Write-Info "上一 release : $(if ($previousRelease) { $previousRelease } else { '<无>' })"
Write-Info "访问         : http://${ServerHost}:$HealthPort"
Write-Info "健康检查     : $remoteHealthUrl"
