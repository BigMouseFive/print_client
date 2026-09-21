"""CUPS readiness tests without invoking the host CUPS daemon."""
from __future__ import annotations

import subprocess
from types import SimpleNamespace

from print_client.core.printer import CupsPrinter


def test_cups_readiness_uses_bounded_configured_queue_availability(monkeypatch):
    calls = []

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        if command == ["lpstat", "-a", "FNSKU"]:
            return SimpleNamespace(stdout="FNSKU accepting requests since now\n")
        if command == ["lpstat", "-a", "BOX"]:
            raise subprocess.CalledProcessError(1, command)
        raise AssertionError(f"unexpected CUPS command: {command}")

    monkeypatch.setattr("print_client.core.printer.subprocess.run", fake_run)

    result = CupsPrinter().readiness(["FNSKU", "BOX", "FNSKU"])

    assert calls == [
        (
            ["lpstat", "-a", "FNSKU"],
            {
                "capture_output": True,
                "text": True,
                "timeout": 5,
                "check": True,
                "env": CupsPrinter._cups_env(),
            },
        ),
        (
            ["lpstat", "-a", "BOX"],
            {
                "capture_output": True,
                "text": True,
                "timeout": 5,
                "check": True,
                "env": CupsPrinter._cups_env(),
            },
        ),
    ]
    assert result == {
        "ready": False,
        "accepting_tasks": False,
        "configured_queues": ["FNSKU", "BOX"],
        "available_queues": ["FNSKU"],
        "missing_queues": ["BOX"],
    }
