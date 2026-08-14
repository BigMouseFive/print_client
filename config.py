"""打印服务配置"""

import os
import sys

PORT = int(os.environ.get("PRINT_AGENT_PORT", "5050"))

# 打印机名称（CUPS 或 Windows）
FNSKU_PRINTER = os.environ.get("FNSKU_PRINTER", "GP-1326D")
BOX_PRINTER = os.environ.get("BOX_PRINTER", "GP-1326D")

# ── ERP 自注册（心跳上报，留空 ERP_URL 则不注册）──────────
ERP_URL = os.environ.get("ERP_URL", "")  # 如 http://192.168.1.10:8888
ERP_TOKEN = os.environ.get("ERP_TOKEN", "")  # 对应 ERP 配置项 PRINT_AGENT_TOKEN
PRINT_AGENT_NAME = os.environ.get("PRINT_AGENT_NAME", "")  # 节点名，默认主机名
PRINT_AGENT_ADVERTISE_URL = os.environ.get("PRINT_AGENT_ADVERTISE_URL", "")  # 手动指定上报地址（默认自动探测局域网 IP）
# 上报 IP 白名单前缀，逗号分隔（如 "192.168.,10.200.200."），多网卡/有 VPN 时用来锁定正确网段
PRINT_AGENT_IP_PREFIXES = [p.strip() for p in os.environ.get("PRINT_AGENT_IP_PREFIXES", "").split(",") if p.strip()]
ERP_HEARTBEAT_INTERVAL = int(os.environ.get("ERP_HEARTBEAT_INTERVAL", "30"))

VERSION = "2.1.0"

# SumatraPDF 路径（仅 Windows）
SUMATRA_PATHS = [
    r"C:\Program Files\SumatraPDF\SumatraPDF.exe",
    r"C:\Program Files (x86)\SumatraPDF\SumatraPDF.exe",
    os.path.join(os.environ.get("LOCALAPPDATA", ""), "SumatraPDF", "SumatraPDF.exe"),
]


def get_sumatra() -> str | None:
    for p in SUMATRA_PATHS:
        if os.path.exists(p):
            return p
    return None


def is_windows() -> bool:
    return sys.platform == "win32"


def is_macos() -> bool:
    return sys.platform == "darwin"
