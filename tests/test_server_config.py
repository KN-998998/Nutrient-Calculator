import unittest

from scripts.serve_web import server_settings


class ServerSettingsTests(unittest.TestCase):
    def test_defaults_are_ecs_friendly(self):
        self.assertEqual(server_settings({}), ("0.0.0.0", 8300))

    def test_environment_can_override_host_and_port(self):
        self.assertEqual(
            server_settings({"HOST": "127.0.0.1", "PORT": "8317"}),
            ("127.0.0.1", 8317),
        )

    def test_invalid_port_is_rejected(self):
        with self.assertRaises(ValueError):
            server_settings({"PORT": "70000"})


if __name__ == "__main__":
    unittest.main()
