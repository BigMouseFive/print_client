"""向 ERP 心跳注册本节点（局域网动态接入）。

ERP 侧接口：POST {ERP_URL}/api/system/service-nodes/heartbeat
body: {"service_type": "print-agent", "url": ..., "name": ..., "token": ..., "meta": {...}}
节点靠周期心跳保持在 ERP 的在线列表里；ERP 超过 PRINT_AGENT_NODE_STALE_SECONDS
收不到心跳会自动将节点判定为离线，因此进程退出无需注销。

仅使用标准库（urllib + threading），不引入新依赖。
"""

import ipaddress
import json
import logging
import socket
import threading
import urllib.error
import urllib.parse
import urllib.request

logger = logging.getLogger("print_client.registrar")

SERVICE_TYPE = "print-agent"

# RFC1918 私网段（局域网地址）
_PRIVATE_NETS = [ipaddress.ip_network(c) for c in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16")]
# 看似私网但实际不可用于 LAN 回连的段：VPN 虚拟网卡 / 运营商 NAT / 链路本地
_EXCLUDED_NETS = [ipaddress.ip_network(c) for c in ("198.18.0.0/15", "100.64.0.0/10", "169.254.0.0/16")]


def _is_lan_ip(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return any(addr in n for n in _PRIVATE_NETS) and not any(addr in n for n in _EXCLUDED_NETS)


def _udp_source_ip(host: str, port: int = 80) -> str | None:
    """UDP 连接法探测通往指定主机的出口 IP（不产生真实流量，仅查路由表）。"""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect((host, port))
        return s.getsockname()[0]
    except OSError:
        return None
    finally:
        s.close()


def _enum_local_ips() -> list[str]:
    """枚举本机全部 IPv4 地址（纯标准库，跨平台）。"""
    ips = []
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            if ip not in ips:
                ips.append(ip)
    except OSError:
        pass
    return ips


def detect_lan_ip(erp_url: str = "", prefer_prefixes: list[str] | None = None) -> str:
    """探测应上报给 ERP 的本机局域网 IP。

    策略（按优先级）：
    1. 向 ERP 主机做路由探测——出口网卡就是能到达 ERP 的网卡，其 IP 即 ERP 回连应使用的地址
    2. 向公网地址（8.8.8.8）探测（ERP_URL 未配置时的退化路径）
    3. 枚举本机全部 IP，匹配 prefer_prefixes 白名单（如 192.168. / 10.200.200.）或任意私网地址
    4. 回退 127.0.0.1 并告警（此时应手动配置 PRINT_AGENT_ADVERTISE_URL）

    探测结果若是 VPN 虚拟段（198.18/15 等）等非 LAN 地址，视为不可用继续往下找。
    """
    candidates: list[str] = []
    if erp_url:
        host = urllib.parse.urlparse(erp_url).hostname
        if host:
            port = urllib.parse.urlparse(erp_url).port or 80
            ip = _udp_source_ip(host, port)
            if ip:
                candidates.append(ip)
    ip = _udp_source_ip("8.8.8.8")
    if ip:
        candidates.append(ip)
    candidates.extend(_enum_local_ips())

    # 去重保序
    seen = set()
    candidates = [c for c in candidates if not (c in seen or seen.add(c))]

    if prefer_prefixes:
        for c in candidates:
            if any(c.startswith(p) for p in prefer_prefixes):
                return c
        logger.warning("没有匹配前缀 %s 的本机 IP（候选: %s）", prefer_prefixes, candidates)

    for c in candidates:
        if _is_lan_ip(c):
            return c

    logger.warning("未探测到可用的局域网 IP（候选: %s），回退 127.0.0.1；"
                   "请通过 PRINT_AGENT_ADVERTISE_URL 手动指定上报地址", candidates)
    return "127.0.0.1"


class ErpRegistrar:
    """周期向 ERP 发送心跳的后台线程。"""

    def __init__(self, erp_url: str, port: int, token: str = "",
                 node_name: str = "", interval: int = 30, meta: dict | None = None,
                 advertise_url: str = "", prefer_prefixes: list[str] | None = None):
        self.heartbeat_url = erp_url.rstrip("/") + "/api/system/service-nodes/heartbeat"
        ip = advertise_url or f"http://{detect_lan_ip(erp_url, prefer_prefixes)}:{port}"
        self.advertise_url = ip.rstrip("/")
        self.node_name = node_name or socket.gethostname()
        self.token = token
        self.interval = interval
        self.meta = meta or {}
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        logger.info("ERP 注册已启动：%s -> %s（%ds 间隔）",
                    self.advertise_url, self.heartbeat_url, self.interval)

    def stop(self) -> None:
        self._stop.set()

    def beat_once(self) -> bool:
        """发一次心跳，返回是否成功。"""
        payload = {
            "service_type": SERVICE_TYPE,
            "url": self.advertise_url,
            "name": self.node_name,
            "meta": self.meta,
        }
        if self.token:
            payload["token"] = self.token
        req = urllib.request.Request(
            url=self.heartbeat_url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                if resp.status == 200:
                    logger.debug("ERP 心跳成功")
                    return True
                logger.warning("ERP 心跳返回 %s（下轮重试）", resp.status)
                return False
        except (urllib.error.URLError, OSError) as e:
            logger.warning("ERP 心跳失败（下轮重试）: %s", e)
            return False

    def _loop(self) -> None:
        while not self._stop.is_set():
            self.beat_once()
            self._stop.wait(self.interval)
