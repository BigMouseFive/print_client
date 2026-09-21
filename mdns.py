"""IPv4 mDNS / DNS-SD publisher for the local print agent.

The publisher announces only the HTTP service contract needed by LAN discovery.
It does not know about ERP URLs or heartbeat registration.
"""
from __future__ import annotations

import asyncio
import ipaddress
import json
import logging
import socket
import uuid
from pathlib import Path

try:
    from zeroconf import IPVersion, ServiceInfo, Zeroconf
except ImportError:  # pragma: no cover - exercised only in incomplete installations
    IPVersion = ServiceInfo = Zeroconf = None  # type: ignore[assignment,misc]

logger = logging.getLogger("print_client.mdns")

SERVICE_TYPE = "_amz-print-agent._tcp.local."
SERVICE_NAME = "print-agent"
API_VERSION = 1
METADATA_PATH = "/.well-known/amazon-service"
READINESS_PATH = "/v1/readiness"


def _private_ipv4_candidates() -> list[str]:
    """Return private, non-loopback IPv4 addresses suitable for LAN discovery."""
    candidates: list[str] = []
    try:
        _, _, addresses = socket.gethostbyname_ex(socket.gethostname())
        candidates.extend(addresses)
    except OSError:
        pass

    # UDP connect does not send data; it asks the routing table for the usual
    # outbound interface, which is useful on multihomed macOS hosts.
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            probe.connect(("8.8.8.8", 80))
            candidates.insert(0, probe.getsockname()[0])
    except OSError:
        pass

    result: list[str] = []
    for candidate in candidates:
        try:
            address = ipaddress.ip_address(candidate)
        except ValueError:
            continue
        if address.version == 4 and address.is_private and not address.is_loopback:
            if candidate not in result:
                result.append(candidate)
    return result


def load_or_create_service_id(path: Path) -> str:
    """Load a stable UUID from *path*, creating it once when necessary."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        service_id = str(data.get("service_id") or "").strip()
        if service_id:
            uuid.UUID(service_id)
            return service_id
    except (OSError, ValueError, json.JSONDecodeError, AttributeError, TypeError):
        pass

    path.parent.mkdir(parents=True, exist_ok=True)
    service_id = str(uuid.uuid4())
    path.write_text(json.dumps({"service_id": service_id}, indent=2) + "\n", encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass
    return service_id


class MdnsPublisher:
    """Lifecycle-bound IPv4 DNS-SD publisher for the print agent."""

    def __init__(
        self,
        *,
        service_id: str,
        port: int,
        instance_name: str = "",
        advertise_address: str = "",
    ) -> None:
        self.service_id = service_id
        self.port = port
        self.instance_name = instance_name.strip() or socket.gethostname()
        self.advertise_address = advertise_address.strip()
        self._zeroconf = None
        self._info = None

    @property
    def service_name(self) -> str:
        safe_name = "-".join(self.instance_name.split()) or SERVICE_NAME
        return f"{safe_name}-{self.service_id[:8]}.{SERVICE_TYPE}"

    def start(self) -> bool:
        """Register the service synchronously; call via ``start_publisher_async``."""
        if Zeroconf is None or ServiceInfo is None or IPVersion is None:
            logger.warning("未安装 zeroconf，mDNS 服务发现未启动")
            return False

        addresses = [self.advertise_address] if self.advertise_address else _private_ipv4_candidates()
        if not addresses:
            logger.warning("未找到可公告的私有 IPv4 地址，mDNS 服务发现未启动")
            return False
        try:
            packed_addresses = [socket.inet_aton(address) for address in addresses]
        except OSError as error:
            logger.warning("mDNS 广播地址非法，服务发现未启动: %s", error)
            return False

        properties = {
            b"service_type": SERVICE_NAME.encode("utf-8"),
            b"service_id": self.service_id.encode("utf-8"),
            b"api_version": str(API_VERSION).encode("utf-8"),
            b"metadata_path": METADATA_PATH.encode("utf-8"),
            b"readiness_path": READINESS_PATH.encode("utf-8"),
        }
        try:
            self._zeroconf = Zeroconf(ip_version=IPVersion.V4Only)
            self._info = ServiceInfo(
                type_=SERVICE_TYPE,
                name=self.service_name,
                addresses=packed_addresses,
                port=self.port,
                properties=properties,
                server=f"{socket.gethostname()}.local.",
            )
            # A name collision must not make a stable service disappear during
            # a quick restart. The TXT service_id is the durable identity.
            self._zeroconf.register_service(
                self._info, cooperating_responders=True, allow_name_change=True
            )
        except Exception as error:
            logger.warning(
                "mDNS 服务公告启动失败(%s): %s", type(error).__name__, error or "无错误信息"
            )
            self.stop()
            return False

        logger.info("mDNS 已公告 %s，IPv4=%s，端口=%s", self.service_name, ",".join(addresses), self.port)
        return True

    def stop(self) -> None:
        """Unregister and close the publisher; safe to call more than once."""
        if self._zeroconf is not None:
            try:
                if self._info is not None:
                    self._zeroconf.unregister_service(self._info)
            except Exception:
                logger.debug("mDNS 服务注销失败", exc_info=True)
            finally:
                self._zeroconf.close()
        self._info = None
        self._zeroconf = None


async def start_publisher_async(publisher: MdnsPublisher) -> bool:
    """Run blocking zeroconf registration outside the ASGI event loop."""
    return await asyncio.to_thread(publisher.start)


async def stop_publisher_async(publisher: MdnsPublisher) -> None:
    """Run blocking zeroconf unregistration outside the ASGI event loop."""
    await asyncio.to_thread(publisher.stop)
