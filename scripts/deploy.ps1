# 部署到 cloudserver200m：本地构建 → 打包 → 上传 → 切软链 → 重启
# 用法：
#   pwsh -File scripts/deploy.ps1                 # 增量发布
#   pwsh -File scripts/deploy.ps1 -FirstRun       # 首次安装（建 venv、装 systemd）
param(
    [switch]$FirstRun,
    [string]$ServerHost = "100.77.67.31",
    [string]$SshKey = "$env:USERPROFILE\.ssh\TDserver_200M.pem",
    [string]$RemoteRoot = "/opt/shiguang"
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$releaseName = $stamp
$staging = Join-Path $env:TEMP "shiguang-$stamp"
$archive = Join-Path $env:TEMP "shiguang-$stamp.tar.gz"

Write-Host "[1/5] 构建前端"
Push-Location (Join-Path $projectRoot "apps/web")
pnpm build | Out-Host
Pop-Location

Write-Host "[2/5] 打包 $releaseName"
New-Item -ItemType Directory -Force -Path $staging | Out-Null
$include = @("apps/server/app", "apps/server/scripts", "apps/server/mcp", "apps/server/requirements.txt",
             "apps/web/dist", "README.md", "THIRD-PARTY-NOTICES.md")
foreach ($item in $include) {
    $src = Join-Path $projectRoot $item
    if (-not (Test-Path $src)) { continue }
    $dest = Join-Path $staging $item
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $dest) | Out-Null
    Copy-Item -Recurse -Force $src $dest
}
Get-ChildItem -Path $staging -Recurse -Directory -Filter "__pycache__" | Remove-Item -Recurse -Force
Get-ChildItem -Path $staging -Recurse -Include "*.pyc" | Remove-Item -Force

tar -czf $archive -C $staging .
Write-Host ("    包大小: {0:N1} MB" -f ((Get-Item $archive).Length / 1MB))

Write-Host "[3/5] 上传"
$remoteArchive = "/tmp/shiguang-$releaseName.tar.gz"
scp -i $SshKey -o StrictHostKeyChecking=accept-new $archive "root@${ServerHost}:$remoteArchive" | Out-Host

Write-Host "[4/5] 远端解包并切软链"
$remoteRelease = "$RemoteRoot/releases/$releaseName"
ssh -i $SshKey "root@$ServerHost" "set -e; mkdir -p $remoteRelease; tar -xzf $remoteArchive -C $remoteRelease; rm -f $remoteArchive; chmod +x $remoteRelease/apps/server/scripts/*.py 2>/dev/null || true; ln -sfn $remoteRelease $RemoteRoot/current"
if ($LastExitCode -ne 0) { throw "远端解包失败" }

if ($FirstRun) {
    Write-Host "[5/5] 首次安装依赖与 systemd"
    ssh -i $SshKey "root@$ServerHost" "mkdir -p /tmp/shiguang-deploy" | Out-Null
    scp -i $SshKey (Join-Path $PSScriptRoot "..\deploy\install.sh") "root@${ServerHost}:/tmp/shiguang-deploy/install.sh" | Out-Host
    scp -i $SshKey (Join-Path $PSScriptRoot "..\deploy\shiguang.service") "root@${ServerHost}:/tmp/shiguang-deploy/shiguang.service" | Out-Host
    ssh -i $SshKey "root@$ServerHost" "set -e; bash /tmp/shiguang-deploy/install.sh $remoteRelease"
    if ($LastExitCode -ne 0) { throw "首次安装失败，检查 /tmp/shiguang-deploy 与 journalctl -u shiguang" }
} else {
    Write-Host "[5/5] 重启服务"
    ssh -i $SshKey "root@$ServerHost" "systemctl restart shiguang; sleep 2; systemctl is-active shiguang"
    if ($LastExitCode -ne 0) { throw "重启失败，查看 journalctl -u shiguang -n 50" }
}

Write-Host "完成：http://${ServerHost}:8720  (release=$releaseName)"
Remove-Item -Recurse -Force $staging
Remove-Item -Force $archive
