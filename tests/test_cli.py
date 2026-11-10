import importlib.util
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / "retry_after_budget.py"
INVALID = {"status": "invalid"}
OBSERVED = "1994-11-06T08:49:37Z"
LIMIT = 256 * 1024
MAX_SECONDS = 2**31 - 1


def load_subject():
    if not SCRIPT.is_file():
        raise AssertionError("CLI entry point is missing")
    spec = importlib.util.spec_from_file_location("retry_under_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def fixture(hint="0", observed=OBSERVED, budget=0):
    return {"retry_after": hint, "observed_at": observed, "max_delay_seconds": budget}


def expected(form, seconds, expired=False, over=False):
    return {"status": "over_budget" if over else "within_budget", "form": form,
            "delay_seconds": seconds, "expired": expired}


class RetryBudgetTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.input = Path(directory.name) / "private-input.json"

    def command(self, *args, **options):
        return subprocess.run([sys.executable, "-B", str(SCRIPT), *map(str, args)], timeout=10, **options)

    def report(self, code, *args):
        result = self.command(*args, capture_output=True)
        self.assertEqual((result.returncode, result.stderr), (code, b""))
        self.assertEqual(len(result.stdout.splitlines()), 1)
        self.assertNotIn(b"private", result.stdout)
        return json.loads(result.stdout)

    def audit(self, document, code):
        data = document if isinstance(document, bytes) else json.dumps(document).encode("utf-8")
        self.input.write_bytes(data)
        report = self.report(code, self.input)
        self.assertEqual(self.input.read_bytes(), data)
        return report

    def test_delta_seconds_and_inclusive_budget(self):
        for hint, seconds, budget, code in (("0", 0, 0, 0), (" \t00030\t ", 30, 30, 0),
                                             ("00030", 30, 29, 1), ("0" * 128, 0, 0, 0),
                                             (str(MAX_SECONDS), MAX_SECONDS, MAX_SECONDS, 0)):
            with self.subTest(hint=hint, budget=budget):
                self.assertEqual(self.audit(fixture(hint, budget=budget), code),
                                 expected("delta_seconds", seconds, over=bool(code)))

    def test_invalid_delta_grammar_and_boundaries(self):
        for hint in ("", " \t", "-0", "+1", "1.0", "1e2", "1 2", "1\t2", "1\n", "\r0", "1\v",
                     "１２", "١٢", "\u00a00", "0" * 129, str(MAX_SECONDS + 1), "private-header"):
            with self.subTest(hint=hint):
                self.assertEqual(self.audit(fixture(hint), 2), INVALID)

    def test_date_zero_past_exact_and_future(self):
        cases = (
            ("Sun, 06 Nov 1994 08:49:36 GMT", 0, 0, True, 0),
            ("Sun, 06 Nov 1994 08:49:37 GMT", 0, 0, False, 0),
            ("\t Sun, 06 Nov 1994 08:49:38 GMT \t", 1, 1, False, 0),
            ("Sun, 06 Nov 1994 08:49:38 GMT", 0, 1, False, 1),
        )
        for hint, budget, seconds, expired, code in cases:
            with self.subTest(hint=hint, budget=budget):
                self.assertEqual(self.audit(fixture(hint, budget=budget), code),
                                 expected("http_date", seconds, expired, bool(code)))

    def test_date_leap_day_midnight_and_delta_cap_independence(self):
        examples = (
            ("Tue, 29 Feb 2000 00:00:00 GMT", "2000-02-28T23:59:59Z", 1, 1, 0),
            ("Mon, 01 Jan 1900 00:00:00 GMT", "1899-12-31T23:59:59Z", 1, 1, 0),
            ("Tue, 19 Jan 2038 03:14:08 GMT", "1970-01-01T00:00:00Z", MAX_SECONDS, 2**31, 1),
        )
        for hint, observed, budget, seconds, code in examples:
            with self.subTest(hint=hint):
                self.assertEqual(self.audit(fixture(hint, observed, budget), code),
                                 expected("http_date", seconds, over=bool(code)))

    def test_rejects_noncanonical_and_invalid_http_dates(self):
        for hint in ("Sunday, 06-Nov-94 08:49:37 GMT", "Sun Nov  6 08:49:37 1994",
                     "sun, 06 Nov 1994 08:49:37 GMT", "Sun, 06 NOV 1994 08:49:37 GMT",
                     "Sun, 06 Nov 1994 08:49:37 gmt", "Sun, 06 Nov 1994 08:49:37 +0000",
                     "Mon, 06 Nov 1994 08:49:37 GMT", "Sun, 6 Nov 1994 08:49:37 GMT",
                     "Sun,  06 Nov 1994 08:49:37 GMT", "Sun,\t06 Nov 1994 08:49:37 GMT",
                     "Sun, 06 Nov 1994 8:49:37 GMT", "Sun, 06 Nov 1994 08:49:60 GMT",
                     "Sun, 06 Nov 1994 08:60:00 GMT", "Sun, 06 Nov 1994 24:00:00 GMT",
                     "Sun, 31 Nov 1994 08:49:37 GMT", "Thu, 29 Feb 1900 00:00:00 GMT",
                     "Sun, 31 Dec 1899 23:59:59 GMT",
                     "Sun, 06 Nov 1994 08:49:37 GMT\n"):
            with self.subTest(hint=hint):
                self.assertEqual(self.audit(fixture(hint), 2), INVALID)

    def test_observed_at_is_exact_utc_even_with_delta_seconds(self):
        for observed in ("1994-11-06t08:49:37Z", "1994-11-06T08:49:37z", "1994-11-06T08:49:37+00:00",
                         " 1994-11-06T08:49:37Z", "1994-11-06T08:49:37.0Z", "1994-11-06T08:49:60Z",
                         "1994-2-06T08:49:37Z", "1900-02-29T08:49:37Z", "0000-01-01T00:00:00Z", None):
            with self.subTest(observed=observed):
                self.assertEqual(self.audit(fixture("0", observed), 2), INVALID)
        self.assertEqual(self.audit(fixture("0", "0001-01-01T00:00:00Z"), 0), expected("delta_seconds", 0))

    def test_same_output_across_tz_environment(self):
        self.input.write_text(json.dumps(fixture("Sun, 10 Mar 2024 10:00:00 GMT",
                                                 "2024-03-10T09:59:58Z", 2)), encoding="utf-8")
        outputs = []
        for zone in ("UTC0", "PST8PDT", "SGT-8"):
            result = self.command(self.input, env={**os.environ, "TZ": zone}, capture_output=True)
            self.assertEqual((result.returncode, result.stderr), (0, b""))
            self.assertEqual(json.loads(result.stdout), expected("http_date", 2))
            outputs.append(result.stdout)
        self.assertEqual(outputs, [outputs[0]] * len(outputs))

    def test_strict_json_shape_and_budget_type(self):
        raw = json.dumps(fixture()).encode()
        invalid = ([], {}, {**fixture(), "extra": 0}, {**fixture(), "retry_after": 0},
                   *(fixture(budget=value) for value in (True, False, -1, MAX_SECONDS + 1, 0.0, "0", None)),
                   b"\xef\xbb\xbf" + raw, raw + b" {}", b'{"retry_after":"\xff"}',
                   raw.replace(b'"0"', br'"\ud800"'), raw.replace(b': 0', b': NaN'),
                   raw[:-1] + br',"retry\u005fafter":"0"}', raw.replace(b': 0', b': ' + b"9" * 5000),
                   b'{"unknown":' + b"[" * 4000 + b"0" + b"]" * 4000 + b"}")
        for document in invalid:
            with self.subTest(size=len(document)):
                self.assertEqual(self.audit(document, 2), INVALID)

    def test_exact_file_byte_cap_and_unreadable_input(self):
        raw = json.dumps(fixture()).encode()
        limit = raw + b" " * (LIMIT - len(raw))
        self.assertEqual(self.audit(limit, 0), expected("delta_seconds", 0))
        self.assertEqual(self.audit(limit + b" ", 2), INVALID)
        self.input.unlink()
        for path in (self.input, self.input.parent):
            self.assertEqual(self.report(2, path), INVALID)

    def test_unsafe_paths_rejected_before_file_access(self):
        module = load_subject()
        paths = ("https://host/private", "file:///private", r"/\host\share", r"\??\private", r"\Device\private",
                 "/dir/../GLOBALROOT/private", r"\dir/../SystemRoot\private", r"C:private.json",
                 "private.json:stream", "C:/private.json:stream", "p/NUL .json", "p/LPT³.json",
                 "p/file.json. ", "p/file.json/", "p/\x00.json", "-")
        for path in paths:
            with (
                self.subTest(path=path),
                patch.object(module.os, "stat", side_effect=AssertionError("stat called")),
                patch.object(module.os, "open", side_effect=AssertionError("open called")),
                patch.object(module, "emit", return_value=2) as emit,
            ):
                self.assertEqual(module.main([path]), 2)
                self.assertEqual(json.loads(emit.call_args.args[0]), INVALID)
        module.check_path(r"C:\ordinary\CLOCK$.json")

    def test_nonregular_or_oversized_descriptor_is_closed_before_read(self):
        module = load_subject()
        self.input.write_text(json.dumps(fixture()), encoding="utf-8")
        for mode, size in ((stat.S_IFCHR, 0), (stat.S_IFREG, LIMIT + 1)):
            with (
                self.subTest(mode=mode, size=size),
                patch.object(module.os, "fstat", return_value=SimpleNamespace(st_mode=mode, st_size=size)) as fstat,
                patch.object(module.os, "fdopen", side_effect=AssertionError("invalid descriptor read")),
                patch.object(module, "emit", return_value=2) as emit,
            ):
                self.assertEqual(module.main([str(self.input)]), 2)
                self.assertEqual(json.loads(emit.call_args.args[0]), INVALID)
            with self.assertRaises(OSError):
                os.fstat(fstat.call_args.args[0])

    def test_argument_help_and_broken_stdout(self):
        self.assertEqual(self.report(2), INVALID)
        self.assertEqual(self.report(2, self.input, "extra"), INVALID)
        help_run = self.command("--help", capture_output=True)
        self.assertEqual((help_run.returncode, help_run.stderr), (0, b""))
        self.assertIn(b"retry_after_budget.py INPUT.json", help_run.stdout)
        self.input.write_text(json.dumps(fixture()), encoding="utf-8")
        for args in ((self.input,), ("--help",), ()):
            reader, writer = os.pipe()
            os.close(reader)
            with os.fdopen(writer, "wb") as pipe:
                process = self.command(*args, stdout=pipe, stderr=subprocess.PIPE)
            self.assertEqual((process.returncode, process.stderr), (2, b""))


if __name__ == "__main__":
    unittest.main()
