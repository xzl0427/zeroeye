#!/usr/bin/env python3
"""Tests for legacy deployment history export."""

import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout

import deploy


class DeploymentHistoryExportTest(unittest.TestCase):
    def test_json_export_filters_and_redacts_history(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            old_cwd = os.getcwd()
            os.chdir(tmpdir)
            try:
                with open(".deploy_history_staging.json", "w") as history_file:
                    json.dump([
                        {
                            "timestamp": "2026-06-20T14:30:00",
                            "service": "backend",
                            "environment": "staging",
                            "tag": "v1.2.3",
                            "status": "success",
                            "deployed_by": "release-bot",
                            "registry_token": "plain-secret-token",
                            "notes": "token=abc123secret",
                        },
                        {
                            "timestamp": "2026-06-20T14:31:00",
                            "service": "frontend",
                            "version": "v1.2.4",
                            "status": "failed",
                            "operator": "web-ops",
                        },
                    ], history_file)

                output = io.StringIO()
                with redirect_stdout(output):
                    deploy.list_deployments("staging", service="backend",
                                            output_format="json")

                exported = json.loads(output.getvalue())
                self.assertEqual(1, len(exported))
                self.assertEqual({
                    "environment": "staging",
                    "operator": "release-bot",
                    "service": "backend",
                    "status": "success",
                    "timestamp": "2026-06-20T14:30:00",
                    "version": "v1.2.3",
                }, exported[0])
                self.assertNotIn("abc123secret", output.getvalue())
                self.assertNotIn("plain-secret-token", output.getvalue())
            finally:
                os.chdir(old_cwd)

    def test_text_export_includes_operator(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            old_cwd = os.getcwd()
            os.chdir(tmpdir)
            try:
                with open(".deploy_history_production.json", "w") as history_file:
                    json.dump([{
                        "timestamp": "2026-06-20T15:00:00",
                        "service": "market",
                        "version": "v9",
                        "status": "success",
                        "operator": "ops-user",
                    }], history_file)

                output = io.StringIO()
                with redirect_stdout(output):
                    deploy.list_deployments("production", output_format="text")

                rendered = output.getvalue()
                self.assertIn("Operator", rendered)
                self.assertIn("ops-user", rendered)
                self.assertIn("market", rendered)
            finally:
                os.chdir(old_cwd)


if __name__ == "__main__":
    unittest.main()
