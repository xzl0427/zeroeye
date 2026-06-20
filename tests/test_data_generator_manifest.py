import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GENERATOR = ROOT / "tools" / "data_generator.py"


class DataGeneratorManifestTest(unittest.TestCase):
    def run_generator(self, *args, check=True):
        return subprocess.run(
            [sys.executable, str(GENERATOR), *args],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=check,
        )

    def test_manifest_generation_and_verification(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            output_dir = tmp_path / "data"
            manifest = tmp_path / "manifest.json"

            self.run_generator(
                "--output-dir", str(output_dir),
                "--seed", "123",
                "--users", "2",
                "--orders", "3",
                "--trades", "4",
                "--ticks", "2",
                "--candles", "1",
                "--format", "both",
                "--manifest", str(manifest),
            )

            payload = json.loads(manifest.read_text())
            self.assertEqual(payload["manifest_version"], 1)
            self.assertEqual(payload["arguments"]["seed"], 123)
            paths = [entry["path"] for entry in payload["files"]]
            self.assertEqual(paths, sorted(paths))
            self.assertIn("users.json", paths)
            self.assertIn("users.csv", paths)
            self.assertTrue(all(len(entry["sha256"]) == 64 for entry in payload["files"]))

            verified = self.run_generator("--verify-manifest", str(manifest))
            self.assertIn("Manifest verified", verified.stdout)

    def test_verify_manifest_fails_when_file_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            output_dir = tmp_path / "data"
            manifest = tmp_path / "manifest.json"

            self.run_generator(
                "--output-dir", str(output_dir),
                "--seed", "123",
                "--users", "2",
                "--orders", "3",
                "--trades", "4",
                "--ticks", "2",
                "--candles", "1",
                "--manifest", str(manifest),
            )

            (output_dir / "users.json").write_text("[]\n")
            result = self.run_generator("--verify-manifest", str(manifest), check=False)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Manifest verification failed", result.stderr)


if __name__ == "__main__":
    unittest.main()
