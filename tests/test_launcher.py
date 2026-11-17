import os
import socket
import sys
import unittest
from unittest import mock

PACKAGING_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "packaging")
sys.path.insert(0, os.path.normpath(PACKAGING_DIR))

import launcher  # noqa: E402


class ResourcePathTests(unittest.TestCase):
    def test_uses_meipass_when_frozen(self):
        with mock.patch.object(sys, "_MEIPASS", "C:/bundle", create=True):
            self.assertEqual(
                launcher.resource_path("app.py"),
                os.path.join("C:/bundle", "app.py"),
            )

    def test_uses_script_dir_when_not_frozen(self):
        if hasattr(sys, "_MEIPASS"):
            delattr(sys, "_MEIPASS")
        expected = os.path.join(
            os.path.dirname(os.path.abspath(launcher.__file__)), "app.py"
        )
        self.assertEqual(launcher.resource_path("app.py"), expected)


class FlagOptionsTests(unittest.TestCase):
    def test_flag_keys_use_underscore_form_and_apply_port(self):
        flags = launcher.build_flag_options(54321)
        self.assertEqual(flags["server_port"], 54321)
        self.assertEqual(flags["server_address"], "127.0.0.1")
        self.assertIs(flags["server_headless"], True)
        self.assertNotIn("server.port", flags)
        for key in flags:
            self.assertNotIn(".", key)


class PickFreePortTests(unittest.TestCase):
    def test_returns_port_that_can_be_bound_on_localhost(self):
        port = launcher.pick_free_port()
        self.assertIsInstance(port, int)
        self.assertTrue(1024 <= port <= 65535)
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", port))


if __name__ == "__main__":
    unittest.main()
