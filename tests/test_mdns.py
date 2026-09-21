"""mDNS publisher tests: no multicast sockets are created."""
from __future__ import annotations

import asyncio
import json
import socket
import threading

from print_client import mdns


def test_service_identity_is_persistent(tmp_path):
    path = tmp_path / "data" / "service-identity.json"
    first = mdns.load_or_create_service_id(path)
    second = mdns.load_or_create_service_id(path)

    assert first == second
    assert json.loads(path.read_text(encoding="utf-8"))["service_id"] == first


class FakeZeroconf:
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.registered = []
        self.unregistered = []
        self.closed = False

    def register_service(self, info, **kwargs):
        self.registered.append((info, kwargs))

    def unregister_service(self, info):
        self.unregistered.append(info)

    def close(self):
        self.closed = True


class FakeServiceInfo:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


class FakeIPVersion:
    V4Only = object()


def test_publisher_is_ipv4_only_and_publishes_contract(monkeypatch):
    fake = FakeZeroconf()

    def make_zeroconf(**kwargs):
        fake.kwargs = kwargs
        return fake

    monkeypatch.setattr(mdns, "Zeroconf", make_zeroconf)
    monkeypatch.setattr(mdns, "ServiceInfo", FakeServiceInfo)
    monkeypatch.setattr(mdns, "IPVersion", FakeIPVersion)
    monkeypatch.setattr(mdns, "_private_ipv4_candidates", lambda: ["192.168.1.20"])
    monkeypatch.setattr(socket, "gethostname", lambda: "test-host")

    publisher = mdns.MdnsPublisher(
        service_id="12345678-1234-1234-1234-123456789abc", port=5050
    )
    assert publisher.start() is True

    assert fake.kwargs["ip_version"] is mdns.IPVersion.V4Only
    info, options = fake.registered[0]
    assert info.type_ == mdns.SERVICE_TYPE
    assert info.addresses == [socket.inet_aton("192.168.1.20")]
    assert info.properties == {
        b"service_type": b"print-agent",
        b"service_id": b"12345678-1234-1234-1234-123456789abc",
        b"api_version": b"1",
        b"metadata_path": b"/.well-known/amazon-service",
        b"readiness_path": b"/v1/readiness",
    }
    assert options == {"cooperating_responders": True, "allow_name_change": True}

    publisher.stop()
    assert fake.unregistered == [info]
    assert fake.closed is True


def test_publisher_lifecycle_runs_off_event_loop():
    async def exercise():
        calls: list[tuple[str, int]] = []

        class RecordingPublisher(mdns.MdnsPublisher):
            def start(self):
                calls.append(("start", threading.get_ident()))
                asyncio.run(asyncio.sleep(0))
                return True

            def stop(self):
                calls.append(("stop", threading.get_ident()))

        publisher = RecordingPublisher(
            service_id="12345678-1234-1234-1234-123456789abc", port=5050
        )
        loop_thread = threading.get_ident()

        assert await mdns.start_publisher_async(publisher) is True
        await mdns.stop_publisher_async(publisher)

        assert [name for name, _ in calls] == ["start", "stop"]
        assert all(thread_id != loop_thread for _, thread_id in calls)

    asyncio.run(exercise())
