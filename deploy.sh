#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

cmd="${1:-help}"

require_docker() {
  if ! command -v docker >/dev/null 2>&1; then
    echo "错误: 未找到 docker，请先安装并启动 Docker 服务。"
    exit 1
  fi
  if ! docker compose version >/dev/null 2>&1; then
    echo "错误: 未检测到 Docker Compose v2（docker compose）。请升级 Docker 或安装 Compose v2。"
    exit 1
  fi
}

usage() {
  cat <<'USAGE'
用法:
  ./deploy.sh start    # 启动全部服务（后台）
  ./deploy.sh stop     # 停止并移除容器
  ./deploy.sh restart  # 重启并强制重构镜像
  ./deploy.sh logs     # 查看全部服务日志（跟随）
  ./deploy.sh status   # 查看服务状态
  ./deploy.sh help     # 显示帮助
USAGE
}

cmd_start() {
  require_docker
  docker compose up -d
  echo "完成: 服务已启动。"
}

cmd_stop() {
  require_docker
  docker compose down
  echo "完成: 服务已停止。"
}

cmd_restart() {
  require_docker
  echo "正在强制重构并重启镜像..."
  docker compose up -d --build
  echo "完成: 服务已重组启动。"
}

cmd_logs() {
  require_docker
  docker compose logs -f --tail=200
}

cmd_status() {
  require_docker
  docker compose ps
}

case "$cmd" in
  start)   cmd_start ;;
  stop)    cmd_stop ;;
  restart) cmd_restart ;;
  logs)    cmd_logs ;;
  status)  cmd_status ;;
  help|"") usage ;;
  *)
    echo "错误: 未知命令 '$cmd'"
    usage
    exit 1
    ;;
esac
