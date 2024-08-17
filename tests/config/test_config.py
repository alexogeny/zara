import unittest
from unittest.mock import mock_open, patch

from zara.config.config import Config


class TestConfig(unittest.TestCase):
    def setUp(self) -> None:
        self.config_content = """
        [server]
        port = 8080
        host = 127.0.0.1

        [database]
        user = myuser
        password = mypassword
        host = localhost
        port = 5432
        """

    def test_config_loading(self):
        with patch("builtins.open", mock_open(read_data=self.config_content)):
            config = Config("config.ini")

            print(
                f"Config sections: {config._config.sections()}"
            )  # Debugging: show sections

            self.assertEqual(config.server.port, "8080")
            self.assertEqual(config.server.host, "127.0.0.1")
            self.assertEqual(config.database.user, "myuser")
            self.assertEqual(config.database.password, "mypassword")
            self.assertEqual(config.database.host, "localhost")
            self.assertEqual(config.database.port, "5432")

    def test_missing_section(self):
        with patch("builtins.open", mock_open(read_data=self.config_content)):
            config = Config("config.ini")

            with self.assertRaises(AttributeError):
                _ = config.missing_section

    def test_missing_key_in_section(self):
        with patch("builtins.open", mock_open(read_data=self.config_content)):
            config = Config("config.ini")

            with self.assertRaises(AttributeError):
                _ = config.server.missing_key

    def test_singleton_behavior(self):
        with patch("builtins.open", mock_open(read_data=self.config_content)):
            config1 = Config("config.ini")
            config2 = Config("config.ini")

            self.assertIs(config1, config2)
            self.assertEqual(config1.server.port, config2.server.port)

    def test_no_such_file(self):
        with self.assertRaises(FileNotFoundError):
            Config("non_existent_file.ini")


if __name__ == "__main__":
    unittest.main()
