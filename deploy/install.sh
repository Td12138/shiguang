#!/usr/bin/env bash
# 首次安装 / 修复（幂等，可重复跑）：cloudserver200m 上创建 shiguang 系统用户、venv、shared、systemd，并健康门校验
# 用法（root）: bash install.sh /opt/shiguang/releases/<时间戳>
# 说明：
#   - 既有 shared/.env 不会被覆盖；口令不打印到 stdout（去文件 / 台账查）
#   - 切 current → enable --now → restart → curl -fsS /api/health，失败打印日志并 exit 1
set -Eeuo pipefail
umask 022

APP_ROOT=/opt/shiguang
RELEASE_DIR="${1:-}"
PY_BIN=python3
PIP_INDEX="${PIP_INDEX:-https://pypi.tuna.tsinghua.edu.cn/simple}"  # 服务器默认镜像超时，用清华源
SERVICE_NAME=shiguang
SERVICE_USER=shiguang
HEALTH_URL=http://127.0.0.1:8720/api/health
HEALTH_TRIES=20
HEALTH_INTERVAL=1
HEALTH_TIMEOUT=3
RECOMMENDED_RATE_LIMIT=120

log() { printf '[install] %s\n' "$*"; }
die() { printf '[install] 错误: %s\n' "$*" >&2; exit 1; }

[[ "${EUID:-1}" -eq 0 ]] || die "请用 root 执行"
[[ -n "${RELEASE_DIR}" ]] || die "用法: install.sh ${APP_ROOT}/releases/<时间戳>"
[[ -f "${RELEASE_DIR}/apps/server/requirements.txt" ]] || die "release 缺 apps/server/requirements.txt: ${RELEASE_DIR}"
[[ -f "$(dirname "$0")/shiguang.service" ]] || die "缺少同目录的 shiguang.service"

# 1) 系统用户（幂等；无 home、不可登录）
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

# 2) 目录与归属
install -d -m 755 -o root -g root "${APP_ROOT}" "${APP_ROOT}/releases"
install -d -m 750 -o "${SERVICE_USER}" -g "${SERVICE_USER}" "${APP_ROOT}/shared" "${APP_ROOT}/shared/upload"

# 3) release 定权：owner=root:root、目录 755、文件 644
chown -R root:root "${RELEASE_DIR}"
find "${RELEASE_DIR}" -type d -exec chmod 755 {} +
find "${RELEASE_DIR}" -type f -exec chmod 644 {} +
if [[ -d "${RELEASE_DIR}/apps/server/scripts" ]]; then
  find "${RELEASE_DIR}/apps/server/scripts" -maxdepth 1 -type f \
       \( -name '*.py' -o -name '*.sh' \) -exec chmod 755 {} +
fi
ln -sfn "${APP_ROOT}/shared/.env" "${RELEASE_DIR}/apps/server/.env"
chown -h root:root "${RELEASE_DIR}/apps/server/.env"
log "release 权限已收紧"

# 4) venv 与依赖
if ! "${PY_BIN}" -m venv --help >/dev/null 2>&1; then
  log "系统缺 venv 模块，尝试安装 python3-venv"
  if command -v apt-get >/dev/null 2>&1; then
    apt-get update -qq && apt-get install -y -qq python3-venv || die "请手工执行: apt-get install -y python3-venv"
  else
    die "系统缺 venv 模块，请先安装（Debian/Ubuntu: apt-get install -y python3-venv）"
  fi
fi
if [[ ! -x "${APP_ROOT}/venv/bin/pip" ]]; then
  rm -rf "${APP_ROOT}/venv"
  "${PY_BIN}" -m venv "${APP_ROOT}/venv"
fi
"${APP_ROOT}/venv/bin/pip" install --quiet --index-url "${PIP_INDEX}" --upgrade pip
"${APP_ROOT}/venv/bin/pip" install --quiet --index-url "${PIP_INDEX}" \
    -r "${RELEASE_DIR}/apps/server/requirements.txt"
log "Python 依赖已安装"

# 5) shared 运行时文件：.env 640 root:shiguang；app.db 640 shiguang:shiguang
ENV_FILE="${APP_ROOT}/shared/.env"
if [[ ! -f "${ENV_FILE}" ]]; then
  if command -v openssl >/dev/null 2>&1; then
    DEMO_PASS="$(openssl rand -hex 12)"
  else
    DEMO_PASS="$(head -c 16 /dev/urandom | od -An -tx1 | tr -d ' \n')"
  fi
  ( umask 077; cat > "${ENV_FILE}" <<ENVEOF
SHIGUANG_LLM_PROVIDER=mock
SHIGUANG_LLM_MODEL=glm-4-flash
SHIGUANG_VLM_MODEL=glm-4v-flash
SHIGUANG_DB_PATH=${APP_ROOT}/shared/app.db
SHIGUANG_UPLOAD_DIR=${APP_ROOT}/shared/upload
SHIGUANG_PORT=8720
SHIGUANG_WEB_DIST=${APP_ROOT}/current/apps/web/dist
SHIGUANG_SSL_VERIFY=os
SHIGUANG_BASIC_AUTH=demo:${DEMO_PASS}
SHIGUANG_RATE_LIMIT_PER_MIN=${RECOMMENDED_RATE_LIMIT}
ENVEOF
  )
  log "已生成 ${ENV_FILE}（640 root:${SERVICE_USER}）"
  log "演示口令未打印：请从该文件取值，并登记到工作区 user/凭证/台账.md"
else
  if grep -q '^SHIGUANG_RATE_LIMIT_PER_MIN=' "${ENV_FILE}"; then
    current_limit="$(grep '^SHIGUANG_RATE_LIMIT_PER_MIN=' "${ENV_FILE}" | tail -n 1 | cut -d= -f2 | tr -dc '0-9')"
    if [[ -n "${current_limit}" && "${current_limit}" -lt "${RECOMMENDED_RATE_LIMIT}" ]]; then
      log "提示: 现有 .env 限流为 ${current_limit}，低于 ${RECOMMENDED_RATE_LIMIT}；本脚本不改既有 .env，请按 docs/09 手工调高后重启"
    fi
  else
    log "提示: 现有 .env 没有 SHIGUANG_RATE_LIMIT_PER_MIN，建议补 ${RECOMMENDED_RATE_LIMIT}"
  fi
  log "沿用既有 ${ENV_FILE}（仅修正归属/权限）"
fi

chown -R "${SERVICE_USER}:${SERVICE_USER}" "${APP_ROOT}/shared"
chmod 750 "${APP_ROOT}/shared" "${APP_ROOT}/shared/upload"
# .env 最后再定权：上面 -R 会把 .env 也改成服务用户
chown root:"${SERVICE_USER}" "${ENV_FILE}"
chmod 640 "${ENV_FILE}"  # 服务用户需读：config.load_env_file 在进程内还会读一次

# app.db 及其 -wal/-shm 一并归服务用户，避免换用户后 SQLite 打不开旧 WAL
touch "${APP_ROOT}/shared/app.db"
chown "${SERVICE_USER}:${SERVICE_USER}" "${APP_ROOT}/shared"/app.db*
chmod 640 "${APP_ROOT}/shared/app.db"

# 5.1) 无认证不得上线：空 SHIGUANG_BASIC_AUTH 等于公网裸奔（fail-closed）
auth_value="$(grep -E '^SHIGUANG_BASIC_AUTH=' "${ENV_FILE}" | tail -n 1 | cut -d= -f2- || true)"
if [[ -z "${auth_value//[[:space:]]/}" ]]; then
  die "${ENV_FILE} 的 SHIGUANG_BASIC_AUTH 为空：公网不允许无认证启动，请填 demo:<强口令> 后重跑"
fi

# 6) systemd 单元 + 软链必须在 enable/start 之前（否则单位文件里的 WorkingDirectory 不存在）
install -m 644 "$(dirname "$0")/shiguang.service" "/etc/systemd/system/${SERVICE_NAME}.service"
systemctl daemon-reload
ln -sfn "${RELEASE_DIR}" "${APP_ROOT}/current"
systemctl enable --now "${SERVICE_NAME}"
systemctl restart "${SERVICE_NAME}"

# 7) 健康门：curl -fsS 拿到 "ok":true 才算成功（4xx/5xx/连接失败都算失败）
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
  printf '[install] 错误: 健康检查失败 %s（%s 次）\n' "${HEALTH_URL}" "${HEALTH_TRIES}" >&2
  journalctl -u "${SERVICE_NAME}" -n 40 --no-pager >&2 || true
  systemctl status "${SERVICE_NAME}" --no-pager -l >&2 || true
  exit 1
fi

log "health: ${body}"
log "服务已启动：$(systemctl is-active "${SERVICE_NAME}") / $(systemctl is-enabled "${SERVICE_NAME}")"
systemctl show "${SERVICE_NAME}" -p User -p Group -p NoNewPrivileges -p ProtectSystem --no-pager
log "回滚一条命令: ln -sfn ${APP_ROOT}/releases/<上一个时间戳> ${APP_ROOT}/current && systemctl restart ${SERVICE_NAME}"
