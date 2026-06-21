"""打印抽象层：Windows / Linux 双平台支持"""

import os
import subprocess
import tempfile
import threading
import time
from abc import ABC, abstractmethod

from ..config import get_sumatra, is_windows, FNSKU_PRINTER, BOX_PRINTER


class BasePrinter(ABC):
    """打印机抽象基类"""

    @abstractmethod
    def print_pdf(self, pdf_bytes: bytes, printer_name: str, copies: int = 1) -> None:
        """将 PDF 发送到指定打印机"""
        pass

    @abstractmethod
    def list_printers(self) -> list[str]:
        """列出可用打印机"""
        pass


class WindowsPrinter(BasePrinter):
    """Windows 打印实现：通过 SumatraPDF 静默打印"""

    def __init__(self):
        self.sumatra = get_sumatra()

    def print_pdf(self, pdf_bytes: bytes, printer_name: str, copies: int = 1) -> None:
        tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
        tmp.write(pdf_bytes)
        tmp.close()

        if self.sumatra:
            cmd = [
                self.sumatra,
                "-print-to", printer_name,
                "-print-settings", f"{copies}x,fit",
                "-silent",
                tmp.name,
            ]
            subprocess.run(cmd, check=True, timeout=30)
        else:
            os.startfile(tmp.name, "print")

        # 延迟清理临时文件
        def _cleanup():
            time.sleep(15)
            try:
                os.unlink(tmp.name)
            except Exception:
                pass

        threading.Thread(target=_cleanup, daemon=True).start()

    def list_printers(self) -> list[str]:
        try:
            result = subprocess.run(
                ["powershell", "-Command", "Get-Printer | Select-Object -ExpandProperty Name"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            return [n.strip() for n in result.stdout.strip().splitlines() if n.strip()]
        except Exception:
            return []


class CupsPrinter(BasePrinter):
    """Linux CUPS 打印实现：通过 lp 命令"""

    def print_pdf(self, pdf_bytes: bytes, printer_name: str, copies: int = 1, media_size: str = None) -> None:
        tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
        tmp.write(pdf_bytes)
        tmp.close()

        try:
            cmd = [
                "lp",
                "-d", printer_name,
                "-n", str(copies),
            ]
            if media_size:
                cmd.extend(["-o", f"media=Custom.{media_size}"])
            else:
                cmd.extend(["-o", "scaling=100"])
            cmd.append(tmp.name)
            subprocess.run(cmd, check=True, timeout=30)
        finally:
            # 延迟清理
            def _cleanup():
                time.sleep(15)
                try:
                    os.unlink(tmp.name)
                except Exception:
                    pass

            threading.Thread(target=_cleanup, daemon=True).start()

    def list_printers(self) -> list[str]:
        import re

        try:
            # lpstat -a 第一列就是打印机名，受系统语言影响小
            result = subprocess.run(
                ["lpstat", "-a"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            printers = []
            for line in result.stdout.splitlines():
                line = line.strip()
                # CUPS 打印机名通常只含 ASCII 字母、数字、下划线、连字符、点号
                match = re.match(r"([A-Za-z0-9_.-]+)", line)
                if match:
                    printers.append(match.group(1))
            return printers
        except Exception:
            return []


def get_printer() -> BasePrinter:
    """根据运行平台返回对应的打印机实现"""
    if is_windows():
        return WindowsPrinter()
    return CupsPrinter()
