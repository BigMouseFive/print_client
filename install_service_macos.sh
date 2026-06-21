#!/bin/bash
# ============================================================
#  print-client macOS LaunchAgent 服务安装脚本
#  用法:
#    ./install_service_macos.sh          安装并启用服务
#    ./install_service_macos.sh --status 查看服务状态
#    ./install_service_macos.sh --logs   查看最近日志
#    ./install_service_macos.sh --uninstall 卸载服务
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
SERVICE_NAME="com.print-client"
PLIST_DIR="${HOME}/Library/LaunchAgents"
PLIST_FILE="${PLIST_DIR}/${SERVICE_NAME}.plist"
LOG_DIR="${HOME}/Library/Logs"
LOG_FILE="${LOG_DIR}/print-client.log"
ERROR_LOG_FILE="${LOG_DIR}/print-client.error.log"

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
RUN_SCRIPT="${PROJECT_DIR}/run.py"

# ------------------ 功能函数 ------------------

print_header() {
    echo "============================================================"
    echo "  ${SERVICE_NAME} macOS LaunchAgent 服务管理脚本"
    echo "============================================================"
    echo ""
}

check_python() {
    if [ -z "$PYTHON_BIN" ]; then
        echo -e "${RED}错误：未找到 python3，请先安装 Python。${NC}"
        exit 1
    fi
}

generate_plist_content() {
    # 如果安装时设置了 FNSKU_PRINTER / BOX_PRINTER，则写入 plist
    local extra_env=""
    if [ -n "${FNSKU_PRINTER:-}" ]; then
        extra_env="${extra_env}
        <key>FNSKU_PRINTER</key>
        <string>${FNSKU_PRINTER}</string>"
    fi
    if [ -n "${BOX_PRINTER:-}" ]; then
        extra_env="${extra_env}
        <key>BOX_PRINTER</key>
        <string>${BOX_PRINTER}</string>"
    fi

    cat <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>${SERVICE_NAME}</string>
    <key>ProgramArguments</key>
    <array>
        <string>${PYTHON_BIN}</string>
        <string>${RUN_SCRIPT}</string>
    </array>
    <key>WorkingDirectory</key>
    <string>${PROJECT_DIR}</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PYTHONPATH</key>
        <string>$(dirname "$PROJECT_DIR")</string>
        <key>PRINT_AGENT_PORT</key>
        <string>5050</string>${extra_env}
    </dict>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>${LOG_FILE}</string>
    <key>StandardErrorPath</key>
    <string>${ERROR_LOG_FILE}</string>
</dict>
</plist>
EOF
}

do_install() {
    print_header
    check_python

    echo "项目目录: ${PROJECT_DIR}"
    echo "Python:   ${PYTHON_BIN}"
    echo "启动脚本: ${RUN_SCRIPT}"
    echo "Plist:    ${PLIST_FILE}"
    echo "日志:     ${LOG_FILE}"
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

    # 确保目录存在
    mkdir -p "${PLIST_DIR}"
    mkdir -p "${LOG_DIR}"

    # 生成 plist 文件
    echo ""
    echo "生成 LaunchAgent plist 文件..."
    PLIST_CONTENT=$(generate_plist_content)
    echo "$PLIST_CONTENT" > "$PLIST_FILE"
    echo -e "${GREEN}已写入: ${PLIST_FILE}${NC}"

    # 加载服务
    echo ""
    echo "加载并启动服务..."
    if launchctl list | grep -q "^${SERVICE_NAME}\$"; then
        launchctl unload -w "$PLIST_FILE" 2>/dev/null || true
    fi
    launchctl load -w "$PLIST_FILE"

    echo ""
    echo -e "${GREEN}============================================================${NC}"
    echo -e "${GREEN}  安装完成！${NC}"
    echo -e "${GREEN}============================================================${NC}"
    echo ""
    echo "服务状态:"
    launchctl list | grep "${SERVICE_NAME}" || true
    echo ""
    echo "常用命令:"
    echo "  查看状态: ./install_service_macos.sh --status"
    echo "  查看日志: ./install_service_macos.sh --logs"
    echo "  卸载服务: ./install_service_macos.sh --uninstall"
    echo "  手动重启: launchctl unload -w ${PLIST_FILE} && launchctl load -w ${PLIST_FILE}"
}

do_uninstall() {
    print_header

    if [ ! -f "$PLIST_FILE" ]; then
        echo -e "${YELLOW}服务文件不存在，无需卸载。${NC}"
        exit 0
    fi

    echo "停止并卸载服务..."
    launchctl unload -w "$PLIST_FILE" 2>/dev/null || true

    echo "删除 plist 文件..."
    rm -f "$PLIST_FILE"

    echo ""
    echo -e "${GREEN}============================================================${NC}"
    echo -e "${GREEN}  卸载完成！${NC}"
    echo -e "${GREEN}============================================================${NC}"
}

do_status() {
    print_header

    if [ ! -f "$PLIST_FILE" ]; then
        echo -e "${YELLOW}服务未安装。${NC}"
        exit 0
    fi

    echo "Plist 文件: ${PLIST_FILE}"
    echo ""
    echo "服务状态:"
    launchctl list | grep "${SERVICE_NAME}" && echo "" || echo "服务未在运行"
    echo "最近日志 (最后 20 行):"
    tail -n 20 "${LOG_FILE}" 2>/dev/null || echo "暂无日志"
}

do_logs() {
    echo "正在查看 ${SERVICE_NAME} 日志 (按 Ctrl+C 退出)..."
    tail -f "${LOG_FILE}" "${ERROR_LOG_FILE}" 2>/dev/null || true
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
        echo "  (无)          安装并启用 LaunchAgent 服务"
        echo "  --status      查看服务状态"
        echo "  --logs        实时查看日志"
        echo "  --uninstall   卸载服务"
        echo "  --help        显示此帮助"
        ;;
    *)
        do_install
        ;;
esac
