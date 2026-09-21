"""打印抽象层：Windows / Linux 双平台支持"""

import os
import re
import subprocess
import tempfile
import threading
import time
from abc import ABC, abstractmethod

from ..config import get_sumatra, is_windows


class BasePrinter(ABC):
    """打印机抽象基类"""

    @abstractmethod
    def print_pdf(
        self,
        pdf_bytes: bytes,
        printer_name: str,
        copies: int = 1,
        media_size: str | None = None,
    ) -> None:
        """将 PDF 发送到指定打印机"""
        pass

    @abstractmethod
    def list_printers(self) -> list[str]:
        """列出可用打印机"""
        pass

    def readiness(self, configured_printers: list[str]) -> dict:
        """Return bounded queue availability for the configured destinations."""
        configured = list(dict.fromkeys(name for name in configured_printers if name))
        available = self.list_printers()
        available_set = set(available)
        missing = [name for name in configured if name not in available_set]
        ready = bool(configured) and not missing
        return {
            "ready": ready,
            "accepting_tasks": ready,
            "configured_queues": configured,
            "available_queues": available,
            "missing_queues": missing,
        }


class WindowsPrinter(BasePrinter):
    """Windows 打印实现：通过 SumatraPDF 静默打印"""

    def __init__(self):
        self.sumatra = get_sumatra()

    def print_pdf(
        self,
        pdf_bytes: bytes,
        printer_name: str,
        copies: int = 1,
        media_size: str | None = None,
    ) -> None:
        # SumatraPDF uses its own print-settings syntax; media size remains a
        # CUPS concern, so this parameter is accepted for a shared interface.
        del media_size
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
    """macOS/Linux CUPS 打印实现：通过 lp 命令。"""

    @staticmethod
    def _cups_env() -> dict[str, str]:
        """让 lpstat 使用稳定英文格式，避免 macOS 本地化粘连队列名和状态文本。"""
        env = dict(os.environ)
        env["LC_ALL"] = "C"
        env["LANG"] = "C"
        return env

    def print_pdf(
        self,
        pdf_bytes: bytes,
        printer_name: str,
        copies: int = 1,
        media_size: str | None = None,
    ) -> None:
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
        """列出 CUPS 队列名，兼容 macOS 的中文本地化输出。"""
        try:
            # lpstat -v 的输出包含稳定的“device for <queue>:”/“用于<queue>的设备：”
            # 结构；lpstat -a 在中文环境会把队列名与“正在接受请求”直接粘连。
            result = subprocess.run(
                ["lpstat", "-v"],
                capture_output=True,
                text=True,
                timeout=5,
                check=True,
                env=self._cups_env(),
            )
            names: list[str] = []
            for line in result.stdout.splitlines():
                match = re.search(r"(?:device for |用于)(.+?)(?:的设备|:)", line)
                if match:
                    name = match.group(1).strip()
                    if name and name not in names:
                        names.append(name)
            return names
        except Exception:
            return []

    def readiness(self, configured_printers: list[str]) -> dict:
        """逐个探测已配置队列，不依赖本地化的列表文本解析。"""
        configured = list(dict.fromkeys(name for name in configured_printers if name))
        available: list[str] = []
        for queue_name in configured:
            try:
                subprocess.run(
                    ["lpstat", "-a", queue_name],
                    capture_output=True,
                    text=True,
                    timeout=5,
                    check=True,
                    env=self._cups_env(),
                )
                available.append(queue_name)
            except Exception:
                continue
        missing = [name for name in configured if name not in available]
        ready = bool(configured) and not missing
        return {
            "ready": ready,
            "accepting_tasks": ready,
            "configured_queues": configured,
            "available_queues": available,
            "missing_queues": missing,
        }


def get_printer() -> BasePrinter:
    """根据运行平台返回对应的打印机实现"""
    if is_windows():
        return WindowsPrinter()
    return CupsPrinter()
