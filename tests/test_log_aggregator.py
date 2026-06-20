#!/usr/bin/env python3
"""
Tests for the log_aggregator parse-error reporting feature.
"""

import json
import os
import sys
import tempfile
import unittest

# Add tools directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from tools.log_aggregator import (
    LogAggregator,
    JSONLogParser,
    TextLogParser,
    NginxLogParser,
)


class TestParseErrorReporting(unittest.TestCase):
    """Tests for the --parse-error-report feature."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

    def _write_log(self, filename: str, lines: list):
        path = os.path.join(self.temp_dir, filename)
        with open(path, 'w') as f:
            for line in lines:
                f.write(line + '\n')
        return path

    def test_valid_json_logs_no_failures(self):
        """Valid JSON logs should produce no parse failures."""
        path = self._write_log('valid.json', [
            '{"timestamp": "2024-01-15T10:00:00", "level": "info", "message": "startup"}',
            '{"timestamp": "2024-01-15T10:01:00", "level": "error", "message": "disk full"}',
        ])
        agg = LogAggregator()
        count = agg.process_file(path)
        report = agg.get_parse_failure_report()
        self.assertEqual(count, 2)
        self.assertEqual(report['total_parse_failures'], 0)

    def test_malformed_json_tracks_separate_failure(self):
        """Malformed JSON lines should be tracked as parse failures."""
        path = self._write_log('mixed.json', [
            '{"timestamp": "2024-01-15T10:00:00", "level": "info", "message": "ok"}',
            'this is not json at all and should fail parsing',
            '{"timestamp": "2024-01-15T10:02:00", "level": "warn", "message": "late"}',
        ])
        agg = LogAggregator()
        count = agg.process_file(path)

        # The malformed line should still be parsed by TextLogParser (non-empty),
        # so count should be 3, but JSON parser failure should be tracked
        self.assertEqual(count, 3)
        report = agg.get_parse_failure_report()
        self.assertEqual(report['total_parse_failures'], 1)

        # Verify the failure details
        failures_by_file = report['by_file']
        fail_path = os.path.basename(path)
        # Should have one file with failures
        self.assertEqual(len(failures_by_file), 1)

        # The failure should reference JSONLogParser
        file_failures = list(failures_by_file.values())[0]['failures']
        self.assertEqual(len(file_failures), 1)
        self.assertEqual(file_failures[0]['parser_type'], 'JSONLogParser')
        self.assertIn('JSON parse error', file_failures[0]['error'])
        self.assertEqual(file_failures[0]['line'], 2)

    def test_empty_lines_skipped(self):
        """Empty lines should not cause parse failures."""
        path = self._write_log('with_blanks.json', [
            '{"msg": "first"}',
            '',
            '{"msg": "third"}',
        ])
        agg = LogAggregator()
        count = agg.process_file(path)
        self.assertEqual(count, 2)
        report = agg.get_parse_failure_report()
        self.assertEqual(report['total_parse_failures'], 0)

    def test_sanitized_report_no_raw_content(self):
        """Parse error report must not include raw log line contents."""
        path = self._write_log('secret.json', [
            '{"api_key": "sk-abcdef1234567890", "level": "info", "msg": "ok"}',
            'password=super_secret_12345',
        ])
        agg = LogAggregator()
        agg.process_file(path)
        report = agg.get_parse_failure_report()
        report_str = json.dumps(report)

        # Should not contain the raw secret values
        self.assertNotIn('sk-abcdef1234567890', report_str)
        self.assertNotIn('super_secret_12345', report_str)
        self.assertNotIn('password=', report_str)

    def test_export_parse_error_report_creates_file(self):
        """export_parse_error_report should write a valid JSON file."""
        path = self._write_log('export_test.json', [
            '{"msg": "good"}',
            'corrupted garbage content here',
            '{"msg": "also good"}',
        ])
        agg = LogAggregator()
        agg.process_file(path)

        out_path = os.path.join(self.temp_dir, 'parse_errors.json')
        agg.export_parse_error_report(out_path)

        self.assertTrue(os.path.exists(out_path))
        with open(out_path) as f:
            data = json.load(f)
        self.assertIn('total_parse_failures', data)
        self.assertIn('by_file', data)
        self.assertIn('by_parser_type', data)
        self.assertIn('note', data)
        self.assertEqual(data['total_parse_failures'], 1)

    def test_multiple_files_aggregated(self):
        """Parse failures from multiple files should be tracked together."""
        path1 = self._write_log('file1.log', ['{"msg": "good"}', 'bad line'])
        path2 = self._write_log('file2.log', ['bad again', '{"msg": "fine"}'])
        agg = LogAggregator()
        agg.process_file(path1)
        agg.process_file(path2)
        report = agg.get_parse_failure_report()
        self.assertEqual(report['total_parse_failures'], 2)
        self.assertEqual(len(report['by_file']), 2)

    def test_backward_compatible(self):
        """Existing outputs must remain backward compatible when --parse-error-report is not used."""
        path = self._write_log('compat.log', [
            '{"level": "error", "msg": "something broke"}',
            'normal text line',
        ])
        agg = LogAggregator()
        count = agg.process_file(path)

        # Summary should work as before
        summary = agg.get_summary()
        self.assertIn('total_entries', summary)
        self.assertIn('by_level', summary)
        self.assertIn('by_service', summary)

        # CSV export should work
        csv_path = os.path.join(self.temp_dir, 'out.csv')
        agg.export_csv(csv_path)
        self.assertTrue(os.path.exists(csv_path))

        # JSON export should work
        json_path = os.path.join(self.temp_dir, 'out.json')
        agg.export_json(json_path)
        self.assertTrue(os.path.exists(json_path))


class TestParsers(unittest.TestCase):
    """Sanity checks for parser behavior."""

    def test_json_parser_valid(self):
        p = JSONLogParser()
        result = p.parse('{"msg": "hello", "level": "info"}')
        self.assertIsNotNone(result)
        self.assertEqual(result['format'], 'json')
        self.assertEqual(result['level'], 'info')

    def test_json_parser_malformed(self):
        p = JSONLogParser()
        result = p.parse('this is not json')
        self.assertIsNone(result)

    def test_text_parser_empty(self):
        p = TextLogParser()
        result = p.parse('')
        self.assertIsNone(result)

    def test_text_parser_valid(self):
        p = TextLogParser()
        result = p.parse('ERROR [api] something failed')
        self.assertIsNotNone(result)
        self.assertEqual(result['format'], 'text')
        self.assertEqual(result['level'], 'error')


if __name__ == '__main__':
    unittest.main()
