#!/bin/bash
# ============================================================
#  print-client systemd 服务安装脚本
#  用法:
#    ./install_service.sh          安装并启用服务
#    ./install_service.sh --status 查看服务状态
#    ./install_service.sh --logs   查看最近日志
#    ./install_service.sh --uninstall 卸载服务
# ============================================================

set -e

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 项目路径
PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_NAME="$(basename "$PROJECT_DIR")"
SERVICE_NAME="print-client"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"

# 检测 Python 解释器
find_python() {
    if [ -f "${PROJECT_DIR}/.venv/bin/python3" ]; then
        echo "${PROJECT_DIR}/.venv/bin/python3"
    elif [ -f "${PROJECT_DIR}/venv/bin/python3" ]; then
        echo "${PROJECT_DIR}/venv/bin/python3"
    elif command -v python3 &>/dev/null; then
        command -v python3
    else
        echo ""
    fi
}

PYTHON_BIN=$(find_python)

# 检测 uvicorn
find_uvicorn() {
    if [ -f "${PROJECT_DIR}/.venv/bin/uvicorn" ]; then
        echo "${PROJECT_DIR}/.venv/bin/uvicorn"
    elif [ -f "${PROJECT_DIR}/venv/bin/uvicorn" ]; then
        echo "${PROJECT_DIR}/venv/bin/uvicorn"
    elif command -v uvicorn &>/dev/null; then
        command -v uvicorn
    else
        echo ""
    fi
}

UVICORN_BIN=$(find_uvicorn)

# 获取项目父目录（用于 PYTHONPATH）
PROJECT_PARENT="$(dirname "$PROJECT_DIR")"

# 获取当前用户
CURRENT_USER=$(whoami)

# ------------------ 功能函数 ------------------

print_header() {
    echo "============================================================"
    echo "  ${SERVICE_NAME} systemd 服务管理脚本"
    echo "============================================================"
    echo ""
}

check_systemd() {
    if ! command -v systemctl &>/dev/null; then
        echo -e "${RED}错误：未检测到 systemd，此脚本仅支持 systemd 系统。${NC}"
        exit 1
    fi
}

check_sudo() {
    if [ "$EUID" -ne 0 ]; then
        echo -e "${YELLOW}需要 sudo 权限来操作 systemd 服务文件。${NC}"
        if ! sudo -n true 2>/dev/null; then
            echo "请输入 sudo 密码："
        fi
    fi
}

generate_service_content() {
    cat <<EOF
[Unit]
Description=佳博打印代理服务 (FastAPI)
After=network.target

[Service]
Type=simple
User=${CURRENT_USER}
WorkingDirectory=${PROJECT_DIR}
Environment=PYTHONPATH=${PROJECT_PARENT}
Environment=PRINT_AGENT_PORT=5050
EOF

    if [ -n "$UVICORN_BIN" ]; then
        echo "ExecStart=${UVICORN_BIN} ${PROJECT_NAME}.main:app --host 0.0.0.0 --port 5050"
    else
        echo "ExecStart=${PYTHON_BIN} -m uvicorn ${PROJECT_NAME}.main:app --host 0.0.0.0 --port 5050"
    fi

    cat <<EOF
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal
SyslogIdentifier=${SERVICE_NAME}

[Install]
WantedBy=multi-user.target
EOF
}

do_install() {
    print_header
    check_systemd

    if [ -z "$PYTHON_BIN" ]; then
        echo -e "${RED}错误：未找到 python3，请先安装 Python。${NC}"
        exit 1
    fi

    echo "项目目录: ${PROJECT_DIR}"
    echo "Python:   ${PYTHON_BIN}"
    if [ -n "$UVICORN_BIN" ]; then
        echo "Uvicorn:  ${UVICORN_BIN}"
    fi
    echo "用户:     ${CURRENT_USER}"
    echo ""

    # 检查依赖
    echo "检查依赖..."
    if ! $PYTHON_BIN -c "import fastapi, uvicorn" 2>/dev/null; then
        echo -e "${YELLOW}警告：未检测到 fastapi 或 uvicorn，服务可能无法启动。${NC}"
        echo "建议先执行: ${PYTHON_BIN} -m pip install -r ${PROJECT_DIR}/requirements.txt"
        read -p "是否继续安装? [y/N] " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            echo "已取消安装。"
            exit 0
        fi
    else
        echo -e "${GREEN}依赖检查通过。${NC}"
    fi

    # 生成 service 文件
    echo ""
    echo "生成 systemd service 文件..."
    SERVICE_CONTENT=$(generate_service_content)

    # 写入 service 文件
    check_sudo
    echo "$SERVICE_CONTENT" | sudo tee "$SERVICE_FILE" > /dev/null
    echo -e "${GREEN}已写入: ${SERVICE_FILE}${NC}"

    # reload
    sudo systemctl daemon-reload

    # enable & start
    echo ""
    echo "启用并启动服务..."
    sudo systemctl enable --now "${SERVICE_NAME}.service"

    echo ""
    echo -e "${GREEN}============================================================${NC}"
    echo -e "${GREEN}  安装完成！${NC}"
    echo -e "${GREEN}============================================================${NC}"
    echo ""
    echo "服务状态:"
    sudo systemctl status "${SERVICE_NAME}.service" --no-pager || true
    echo ""
    echo "常用命令:"
    echo "  查看状态: sudo systemctl status ${SERVICE_NAME}"
    echo "  查看日志: sudo journalctl -u ${SERVICE_NAME} -f"
    echo "  重启服务: sudo systemctl restart ${SERVICE_NAME}"
    echo "  停止服务: sudo systemctl stop ${SERVICE_NAME}"
}

do_uninstall() {
    print_header
    check_systemd

    if [ ! -f "$SERVICE_FILE" ]; then
        echo -e "${YELLOW}服务文件不存在，无需卸载。${NC}"
        exit 0
    fi

    check_sudo
    echo "停止并禁用服务..."
    sudo systemctl stop "${SERVICE_NAME}.service" 2>/dev/null || true
    sudo systemctl disable "${SERVICE_NAME}.service" 2>/dev/null || true

    echo "删除服务文件..."
    sudo rm -f "$SERVICE_FILE"

    sudo systemctl daemon-reload

    echo ""
    echo -e "${GREEN}============================================================${NC}"
    echo -e "${GREEN}  卸载完成！${NC}"
    echo -e "${GREEN}============================================================${NC}"
}

do_status() {
    print_header
    check_systemd

    if ! systemctl list-unit-files | grep -q "${SERVICE_NAME}.service"; then
        echo -e "${YELLOW}服务未安装。${NC}"
        exit 0
    fi

    echo "服务状态:"
    sudo systemctl status "${SERVICE_NAME}.service" --no-pager || true
}

do_logs() {
    check_systemd
    echo "正在查看 ${SERVICE_NAME} 日志 (按 Ctrl+C 退出)..."
    sudo journalctl -u "${SERVICE_NAME}.service" -n 100 -f
}

# ------------------ 主入口 ------------------

case "${1:-}" in
    --uninstall)
        do_uninstall
        ;;
    --status)
        do_status
        ;;
    --logs)
        do_logs
        ;;
    --help|-h)
        echo "用法: $0 [选项]"
        echo ""
        echo "选项:"
        echo "  (无)          安装并启用 systemd 服务"
        echo "  --status      查看服务状态"
        echo "  --logs        查看服务日志"
        echo "  --uninstall   卸载服务"
        echo "  --help        显示此帮助"
        ;;
    *)
        do_install
        ;;
esac
