import subprocess
from types import SimpleNamespace

from r1_agent.interface import resolve_interface


def test_explicit_interface_is_kept():
    assert resolve_interface("en5") == "en5"
    assert resolve_interface("enp7s0") == "enp7s0"


def test_auto_picks_mac_robot_nic(monkeypatch):
    monkeypatch.setattr("r1_agent.interface.platform.system", lambda: "Darwin")

    def fake_run(*args, **kwargs):
        return SimpleNamespace(stdout="en0: flags=8863\n\tinet 192.168.195.1\nen5: flags=8863\n\tinet 192.168.123.100 netmask 0xffffff00\n")

    monkeypatch.setattr(subprocess, "run", fake_run)
    assert resolve_interface("auto") == "en5"


def test_auto_picks_linux_robot_nic(monkeypatch):
    monkeypatch.setattr("r1_agent.interface.platform.system", lambda: "Linux")

    def fake_run(*args, **kwargs):
        return SimpleNamespace(stdout="2: enp7s0    inet 192.168.123.100/24 brd 192.168.123.255 scope global enp7s0\n")

    monkeypatch.setattr(subprocess, "run", fake_run)
    assert resolve_interface("auto") == "enp7s0"
