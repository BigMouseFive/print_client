"""Print-client API tests with fake queues; no CUPS or multicast required."""
from __future__ import annotations

from fastapi.testclient import TestClient

from print_client.api import routes  # noqa: E402
from print_client.api.models import FnskuPrintRequest  # noqa: E402
from print_client.main import app  # noqa: E402


class FakePrinter:
    def print_pdf(self, *_args, **_kwargs):
        pass

    def list_printers(self):
        return ["GP-1326D"]

    def readiness(self, configured_printers):
        configured = list(dict.fromkeys(configured_printers))
        available = self.list_printers()
        missing = [name for name in configured if name not in available]
        ready = bool(configured) and not missing
        return {
            "ready": ready,
            "accepting_tasks": ready,
            "configured_queues": configured,
            "available_queues": available,
            "missing_queues": missing,
        }


def test_origin_is_backwards_compatible_alias():
    request = FnskuPrintRequest(fnsku="FNSKU", sku="SKU", origin="made in usa")
    assert request.msku_shipping == "made in usa"

    canonical = FnskuPrintRequest(
        fnsku="FNSKU",
        sku="SKU",
        msku_shipping="canonical",
        origin="legacy",
    )
    assert canonical.msku_shipping == "canonical"


def test_fnsku_endpoint_accepts_legacy_origin(monkeypatch):
    monkeypatch.setattr(routes, "printer", FakePrinter())
    monkeypatch.setattr(routes, "generate_fnsku_pdf", lambda *_args: b"pdf")

    with TestClient(app) as client:
        response = client.post(
            "/print/fnsku",
            json={"fnsku": "FNSKU", "sku": "SKU", "origin": "legacy"},
        )

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_metadata_and_readiness(monkeypatch):
    monkeypatch.setattr(routes, "printer", FakePrinter())
    monkeypatch.setattr(routes, "FNSKU_PRINTER", "GP-1326D")
    monkeypatch.setattr(routes, "BOX_PRINTER", "GP-1326D")

    with TestClient(app) as client:
        app.state.service_id = "12345678-1234-1234-1234-123456789abc"
        metadata = client.get("/.well-known/amazon-service")
        readiness = client.get("/v1/readiness")
        ping = client.get("/ping")

    assert metadata.status_code == 200
    assert metadata.json()["service_type"] == "print-agent"
    assert metadata.json()["service_id"] == app.state.service_id
    assert metadata.json()["api_version"] == 1
    assert metadata.json()["readiness_path"] == "/v1/readiness"
    assert readiness.status_code == 200
    assert readiness.json()["ready"] is True
    assert readiness.json()["accepting_tasks"] is True
    assert ping.status_code == 200


def test_readiness_is_false_when_a_configured_queue_is_missing(monkeypatch):
    monkeypatch.setattr(routes, "FNSKU_PRINTER", "GP-1326D")
    monkeypatch.setattr(routes, "BOX_PRINTER", "BOX-PRINTER")
    class MissingBoxPrinter(FakePrinter):
        def readiness(self, configured_printers):
            return {
                **super().readiness(configured_printers),
                "ready": False,
                "accepting_tasks": False,
                "missing_queues": ["BOX-PRINTER"],
            }

    monkeypatch.setattr(routes, "printer", MissingBoxPrinter())
    with TestClient(app) as client:
        body = client.get("/v1/readiness").json()

    assert body["ready"] is False
    assert body["accepting_tasks"] is False
    assert body["missing_queues"] == ["BOX-PRINTER"]
