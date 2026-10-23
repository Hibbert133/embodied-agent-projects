import unittest

from scripts.check_tracked_secrets import find_secret_rule


class SecretScanTest(unittest.TestCase):
    def test_detects_provider_shaped_key_without_echoing_value(self):
        candidate = "sk-proj-" + "A" * 32
        self.assertEqual(find_secret_rule(candidate), "provider_key_prefix")

    def test_detects_assigned_generic_key(self):
        candidate = "ANTHROPIC_API_KEY=" + "x" * 32
        self.assertEqual(find_secret_rule(candidate), "assigned_api_key")

    def test_placeholders_and_environment_lookups_are_allowed(self):
        self.assertIsNone(find_secret_rule("ANTHROPIC_API_KEY=your-api-key"))
        self.assertIsNone(find_secret_rule('os.environ.get("ANTHROPIC_API_KEY")'))


if __name__ == "__main__":
    unittest.main()
