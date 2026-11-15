#!/usr/bin/env bash
# 首次安装：在 cloudserver200m 上执行一次（幂等，可重复跑）
set -Eeuo pipefail

APP_ROOT=/opt/shiguang
RELEASE_DIR="${1:-}"
PY_BIN=python3
PIP_INDEX="${PIP_INDEX:-https://pypi.tuna.tsinghua.edu.cn/simple}"  # 服务器默认镜像超时，用清华源

if [[ -z "${RELEASE_DIR}" ]]; then
  echo "用法: install.sh /opt/shiguang/releases/<时间戳>" >&2
  exit 2
fi

mkdir -p "${APP_ROOT}/releases" "${APP_ROOT}/shared/upload"
touch "${APP_ROOT}/shared/app.db"

if [[ ! -x "${APP_ROOT}/venv/bin/pip" ]]; then
  rm -rf "${APP_ROOT}/venv"
  "${PY_BIN}" -m venv "${APP_ROOT}/venv"
fi
"${APP_ROOT}/venv/bin/pip" install --quiet --index-url "${PIP_INDEX}" --upgrade pip
"${APP_ROOT}/venv/bin/pip" install --quiet --index-url "${PIP_INDEX}" -r "${RELEASE_DIR}/apps/server/requirements.txt"

if [[ ! -f "${APP_ROOT}/shared/.env" ]]; then
  cat > "${APP_ROOT}/shared/.env" <<'ENVEOF'
SHIGUANG_LLM_PROVIDER=mock
SHIGUANG_LLM_MODEL=glm-4-flash
SHIGUANG_VLM_MODEL=glm-4v-flash
SHIGUANG_DB_PATH=/opt/shiguang/shared/app.db
SHIGUANG_PORT=8720
SHIGUANG_SSL_VERIFY=os
SHIGUANG_BASIC_AUTH=demo:changeme
SHIGUANG_RATE_LIMIT_PER_MIN=30
ENVEOF
  chmod 600 "${APP_ROOT}/shared/.env"
  echo "已生成 ${APP_ROOT}/shared/.env（请按需填 key 并改口令）"
fi

install -m 644 "$(dirname "$0")/shiguang.service" /etc/systemd/system/shiguang.service
systemctl daemon-reload
systemctl enable --now shiguang

ln -sfn "${RELEASE_DIR}" "${APP_ROOT}/current"
systemctl restart shiguang
sleep 2
systemctl is-active --quiet shiguang && echo "shiguang 已启动" || { journalctl -u shiguang -n 40 --no-pager; exit 1; }
curl -s -o /dev/null -w "health: %{http_code}\n" http://127.0.0.1:8720/api/health
