"""Offline regression tests; no server access or real credentials."""
import argparse
import contextlib
import importlib.util
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location(
    "vpnctl", Path(__file__).resolve().parents[1] / "wireguard/vpnctl.py")
vpnctl = importlib.util.module_from_spec(spec)
spec.loader.exec_module(vpnctl)


class CredentialTests(unittest.TestCase):
    def test_missing_local_encoder_never_sends_config_to_server(self):
        with patch.object(vpnctl, "have", return_value=False), \
             patch.object(vpnctl, "ssh") as remote:
            self.assertFalse(vpnctl.qr_terminal(Path("nonexistent.conf")))
            remote.assert_not_called()

    def test_local_qr_never_uses_ssh(self):
        with patch.object(vpnctl, "have", return_value=True), \
             patch.object(vpnctl, "run", return_value="QR") as run, \
             patch.object(vpnctl, "ssh") as remote, \
             contextlib.redirect_stdout(io.StringIO()):
            self.assertTrue(vpnctl.qr_terminal(Path("device.conf")))
            run.assert_called_once_with(
                ["qrencode", "-t", "ansiutf8", "-r", "device.conf"])
            remote.assert_not_called()

    def test_add_captures_ipv6_without_authorizing_it_on_server(self):
        with tempfile.TemporaryDirectory() as directory, \
             patch.object(vpnctl, "OUT_DIR", Path(directory)), \
             patch.object(vpnctl, "peers_from_conf", return_value=[]), \
             patch.object(vpnctl, "have", return_value=True), \
             patch.object(vpnctl, "run", side_effect=["test-private", "test-public"]), \
             patch.object(vpnctl, "server_pubkey", return_value="test-server"), \
             patch.object(vpnctl, "ssh") as remote, \
             patch.object(vpnctl, "qr_png", return_value=False), \
             contextlib.redirect_stdout(io.StringIO()):
            vpnctl.cmd_add(argparse.Namespace(name="test", device="mac", platform="mac"))
            config = Path(directory) / "test.conf"
            self.assertIn("AllowedIPs = 0.0.0.0/0, ::/0\n", config.read_text())
            self.assertEqual(config.stat().st_mode & 0o777, 0o600)
            command = remote.call_args.args[0]
            self.assertNotIn("test-private", command)
            self.assertIn("allowed-ips 10.66.0.2/32", command)
            self.assertNotIn("::/0", command)


if __name__ == "__main__":
    unittest.main()
