"""打印服务配置"""

import os
import sys

PORT = int(os.environ.get("PRINT_AGENT_PORT", "5050"))

# 打印机名称（CUPS 或 Windows）
FNSKU_PRINTER = os.environ.get("FNSKU_PRINTER", "GP-1326D")
BOX_PRINTER = os.environ.get("BOX_PRINTER", "GP-1326D")

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
