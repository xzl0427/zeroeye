#!/usr/bin/env python3

import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest import mock

from tools import config_generator


class ConfigGeneratorMaskingTests(unittest.TestCase):
    def test_masks_nested_secrets_by_key_term(self):
        config = {
            "service": {
                "apiToken": "tok_live_123",
                "nested": {
                    "credentials": {
                        "username": "diagnostic-user",
                        "password": "pass_live_123",
                    },
                    "public_url": "https://example.test",
                },
            },
            "plain": "visible",
        }

        masked = config_generator.mask_sensitive(config)

        self.assertEqual(masked["service"]["apiToken"], config_generator.REDACTED_VALUE)
        self.assertEqual(masked["service"]["nested"]["credentials"]["username"], config_generator.REDACTED_VALUE)
        self.assertEqual(masked["service"]["nested"]["credentials"]["password"], config_generator.REDACTED_VALUE)
        self.assertEqual(masked["service"]["nested"]["public_url"], "https://example.test")
        self.assertEqual(masked["plain"], "visible")

    def test_masks_list_values_for_sensitive_keys(self):
        config = {
            "tokens": ["alpha", "bravo"],
            "allowed_instruments": ["BTC-USD", "ETH-USD"],
            "targets": [{"secret_key": "nested-list-secret"}, {"name": "public"}],
        }

        masked = config_generator.mask_sensitive(config)

        self.assertEqual(masked["tokens"], [config_generator.REDACTED_VALUE, config_generator.REDACTED_VALUE])
        self.assertEqual(masked["allowed_instruments"], ["BTC-USD", "ETH-USD"])
        self.assertEqual(masked["targets"][0]["secret_key"], config_generator.REDACTED_VALUE)
        self.assertEqual(masked["targets"][1]["name"], "public")

    def test_dotenv_output_masks_sensitive_values_but_keeps_public_values(self):
        config = config_generator.mask_sensitive({
            "auth": {"jwt_secret": "secret-value", "issuer": "tent"},
            "service": {"api_key": "api-key-value"},
        })

        output = config_generator.to_dotenv(config)

        self.assertIn("AUTH_JWT_SECRET=***REDACTED***", output)
        self.assertIn("AUTH_ISSUER=tent", output)
        self.assertIn("SERVICE_API_KEY=***REDACTED***", output)
        self.assertNotIn("secret-value", output)
        self.assertNotIn("api-key-value", output)

    def test_k8s_configmap_masks_nested_and_flattened_secrets(self):
        config = config_generator.mask_sensitive({
            "auth": {"jwt_secret": "secret-value", "issuer": "tent"},
            "service": {"credential_ref": "cred-value", "mode": "public"},
        })

        output = config_generator.to_k8s_configmap(config)

        self.assertIn('auth.jwt_secret: "***REDACTED***"', output)
        self.assertIn('service.credential_ref: "***REDACTED***"', output)
        self.assertIn('service.mode: "public"', output)
        self.assertNotIn("secret-value", output)
        self.assertNotIn("cred-value", output)

    def test_error_message_masks_sensitive_output_path(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            secret_dir = Path(tmp_dir) / "SECRET_TOKEN_dir"
            output_path = secret_dir / "config.json"

            stderr = io.StringIO()
            argv = [
                "config_generator.py",
                "--env",
                "production",
                "--format",
                "json",
                "--output",
                str(output_path),
            ]
            with mock.patch("sys.argv", argv), redirect_stderr(stderr):
                exit_code = config_generator.main()

        self.assertEqual(exit_code, 1)
        error = stderr.getvalue()
        self.assertIn(config_generator.REDACTED_VALUE, error)
        self.assertNotIn("SECRET_TOKEN_dir", error)

    def test_default_json_output_has_no_known_sample_secret_values(self):
        config = config_generator.generate_config("production", {
            "integrations": {
                "apiToken": "live-token-value",
                "public_name": "visible-name",
            }
        })

        masked = config_generator.mask_sensitive(config)
        output = json.dumps(masked)

        self.assertIn("visible-name", output)
        self.assertNotIn("live-token-value", output)


if __name__ == "__main__":
    unittest.main()
