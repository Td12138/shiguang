#!/usr/bin/env bash
# 一次性迁移脚本：把“已经在线、但以 root 跑且文件 666/777”的 shiguang 演示站收紧到目标形态。
#
# 变更内容（不改 .env 内容、不切 release、不动数据库数据）：
#   1) 建 shiguang 系统用户（幂等）
#   2) releases/*：owner root:root、目录 755、文件 644，脚本入口 755
#   3) shared：目录/upload 750 shiguang:shiguang，app.db 640，.env 640 root:shiguang
#   4) 安装 deploy/shiguang.service（User=shiguang + 加固项）并 daemon-reload
#   5) 重启 → curl -fsS /api/health 必须 "ok":true，否则打印日志并 exit 1
#
# 使用（本仓库不自动调用；主会话审核后手工执行）：
#   scp deploy/shiguang.service deploy/harden-existing.sh root@<host>:/tmp/shiguang-deploy/
#   ssh root@<host> 'bash /tmp/shiguang-deploy/harden-existing.sh --yes'
#
# 只收紧权限，不打印口令；限流 120 需由主会话按 docs/09 修改 shared/.env 后重启。
set -Eeuo pipefail
umask 022

APP_ROOT=/opt/shiguang
SERVICE_NAME=shiguang
SERVICE_USER=shiguang
UNIT_SRC="$(dirname "$0")/shiguang.service"
HEALTH_URL=http://127.0.0.1:8720/api/health
HEALTH_TRIES=20
HEALTH_INTERVAL=1
HEALTH_TIMEOUT=3
RECOMMENDED_RATE_LIMIT=120

log() { printf '[harden] %s\n' "$*"; }
die() { printf '[harden] 错误: %s\n' "$*" >&2; exit 1; }

[[ "${EUID:-1}" -eq 0 ]] || die "请用 root 执行"
[[ -d "${APP_ROOT}" ]] || die "找不到 ${APP_ROOT}（本机不是 shiguang 演示机？）"
[[ -f "${UNIT_SRC}" ]] || die "缺少同目录 shiguang.service: ${UNIT_SRC}"

if [[ -t 0 && "${1:-}" != "--yes" ]]; then
  printf '[harden] 将收紧 %s 权限并重启 %s，继续？[y/N] ' "${APP_ROOT}" "${SERVICE_NAME}"
  read -r answer
  [[ "${answer}" == "y" || "${answer}" == "Y" ]] || die "已取消"
fi

# 0) 配置体检：不生成空配置，也不在无认证状态下重启公网服务
env_file="${APP_ROOT}/shared/.env"
[[ -f "${env_file}" ]] || die "缺少 ${env_file}：请先用 deploy/install.sh 初始化，本脚本不生成空配置（避免无认证裸奔）"
auth_value="$(grep -E '^SHIGUANG_BASIC_AUTH=' "${env_file}" | tail -n 1 | cut -d= -f2- || true)"
[[ -n "${auth_value//[[:space:]]/}" ]] || die "${env_file} 的 SHIGUANG_BASIC_AUTH 为空：先填口令再跑本脚本（否则重启后公网无认证）"

# 1) 系统用户
if ! id -u "${SERVICE_USER}" >/dev/null 2>&1; then
  if command -v useradd >/dev/null 2>&1; then
    useradd --system --user-group --no-create-home --home-dir "${APP_ROOT}" \
            --shell /usr/sbin/nologin "${SERVICE_USER}"
  else
    adduser --system --no-create-home --home "${APP_ROOT}" \
            --shell /usr/sbin/nologin "${SERVICE_USER}"
  fi
  log "已创建系统用户 ${SERVICE_USER}"
else
  log "系统用户 ${SERVICE_USER} 已存在"
fi

# 2) 顶层与 releases 定权（先记录回滚要用的上一版，本脚本不切软链）
pre_health="$(curl -fsS --max-time "${HEALTH_TIMEOUT}" "${HEALTH_URL}" 2>/dev/null || true)"
[[ -n "${pre_health}" ]] && log "变更前 health: ${pre_health}" || log "变更前 health: 未通过（继续执行）"
current_real="$(readlink -f "${APP_ROOT}/current" 2>/dev/null || true)"
[[ -n "${current_real}" ]] && log "current -> ${current_real}"

chown root:root "${APP_ROOT}" "${APP_ROOT}/releases"
chmod 755 "${APP_ROOT}" "${APP_ROOT}/releases"

shopt -s nullglob
for release in "${APP_ROOT}"/releases/*/; do
  release="${release%/}"
  [[ -d "${release}" ]] || continue
  chown -R root:root "${release}"
  find "${release}" -type d -exec chmod 755 {} +
  find "${release}" -type f -exec chmod 644 {} +
  if [[ -d "${release}/apps/server/scripts" ]]; then
    find "${release}/apps/server/scripts" -maxdepth 1 -type f \
         \( -name '*.py' -o -name '*.sh' \) -exec chmod 755 {} +
  fi
  if [[ -e "${release}/apps/server/.env" || -L "${release}/apps/server/.env" ]]; then
    ln -sfn "${APP_ROOT}/shared/.env" "${release}/apps/server/.env"
    chown -h root:root "${release}/apps/server/.env"
  fi
  log "已收紧 $(basename "${release}")"
done
shopt -u nullglob

# 3) shared：服务用户可写，.env 只给服务用户读
[[ -d "${APP_ROOT}/shared" ]] || die "缺少 ${APP_ROOT}/shared"
chown -R "${SERVICE_USER}:${SERVICE_USER}" "${APP_ROOT}/shared"
chmod 750 "${APP_ROOT}/shared"
install -d -m 750 -o "${SERVICE_USER}" -g "${SERVICE_USER}" "${APP_ROOT}/shared/upload"

touch "${APP_ROOT}/shared/app.db"
chown "${SERVICE_USER}:${SERVICE_USER}" "${APP_ROOT}/shared"/app.db*
chmod 640 "${APP_ROOT}/shared/app.db"

chown root:"${SERVICE_USER}" "${env_file}"
chmod 640 "${env_file}"  # 服务用户需读：config.load_env_file 在进程内还会读一次
log ".env -> 640 root:${SERVICE_USER}"
if grep -q '^SHIGUANG_RATE_LIMIT_PER_MIN=' "${env_file}"; then
  current_limit="$(grep '^SHIGUANG_RATE_LIMIT_PER_MIN=' "${env_file}" | tail -n 1 | cut -d= -f2 | tr -dc '0-9')"
  if [[ -n "${current_limit}" && "${current_limit}" -lt "${RECOMMENDED_RATE_LIMIT}" ]]; then
    log "待办: .env 限流为 ${current_limit}，需手工改为 ${RECOMMENDED_RATE_LIMIT} 后重启（本脚本不改配置）"
  fi
else
  log "待办: .env 缺 SHIGUANG_RATE_LIMIT_PER_MIN，建议补 ${RECOMMENDED_RATE_LIMIT}"
fi

# 4) 安装加固后的 unit
install -m 644 "${UNIT_SRC}" "/etc/systemd/system/${SERVICE_NAME}.service"
systemctl daemon-reload
log "已安装 ${SERVICE_NAME}.service"

# 5) 重启 + 健康门
systemctl enable "${SERVICE_NAME}"
systemctl restart "${SERVICE_NAME}"

ok=0
body=""
i=0
while [[ "${i}" -lt "${HEALTH_TRIES}" ]]; do
  i=$((i + 1))
  sleep "${HEALTH_INTERVAL}"
  if body="$(curl -fsS --max-time "${HEALTH_TIMEOUT}" "${HEALTH_URL}" 2>/dev/null)" \
      && printf '%s' "${body}" | grep -Eq '"ok"[[:space:]]*:[[:space:]]*true'; then
    ok=1
    break
  fi
done

if [[ "${ok}" -ne 1 ]]; then
  printf '[harden] 错误: 健康检查失败 %s（%s 次）\n' "${HEALTH_URL}" "${HEALTH_TRIES}" >&2
  journalctl -u "${SERVICE_NAME}" -n 60 --no-pager >&2 || true
  systemctl status "${SERVICE_NAME}" --no-pager -l >&2 || true
  printf '[harden] 排障提示: 若是权限导致读写失败，先看 shared 归属；确需回退 unit 可恢复备份并 daemon-reload\n' >&2
  exit 1
fi

log "health: ${body}"
systemctl show "${SERVICE_NAME}" -p User -p Group -p NoNewPrivileges -p ProtectSystem -p PrivateTmp -p ReadWritePaths --no-pager
log "完成。后续发布用 scripts/deploy.ps1；回滚: ln -sfn ${APP_ROOT}/releases/<上一时间戳> ${APP_ROOT}/current && systemctl restart ${SERVICE_NAME}"
