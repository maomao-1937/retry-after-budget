"""Replay a saved Retry-After hint against a fixed UTC observation."""

from datetime import datetime, timezone
import json
import os
import posixpath
import re
import stat
import sys


MAX_BYTES = 256 * 1024
MAX_SECONDS = 2**31 - 1
FIELDS = {"retry_after", "observed_at", "max_delay_seconds"}
DELTA = re.compile(r"[0-9]+")
OBSERVED = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z")
HTTP_DATE = re.compile(
    r"(?P<weekday>[A-Z][a-z]{2}), (?P<day>[0-9]{2}) (?P<month>[A-Z][a-z]{2}) "
    r"(?P<year>[0-9]{4}) (?P<hour>[0-9]{2}):(?P<minute>[0-9]{2}):(?P<second>[0-9]{2}) GMT"
)
MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
DEVICE = re.compile(r"CON|PRN|AUX|NUL|CONIN\$|CONOUT\$|(?:COM|LPT)[0-9¹²³]")
NATIVE_ROOTS = {"??", "device", "dosdevices", "global??", "systemroot", "globalroot"}


def check_path(path):
    spelling = path.replace("\\", "/")
    if not spelling or spelling == "-" or spelling.startswith("//") or spelling.endswith("/"):
        raise ValueError
    if any(ord(char) < 32 for char in spelling):
        raise ValueError
    if spelling.startswith("/"):
        for version in (spelling, posixpath.normpath(spelling)):
            root = version[1:].partition("/")[0].rstrip(" .").lower()
            if root in NATIVE_ROOTS:
                raise ValueError
    tail = spelling[2:] if re.match(r"^[A-Za-z]:/", spelling) else spelling
    if ":" in tail:
        raise ValueError
    for part in tail.split("/"):
        if part in {"", ".", ".."}:
            continue
        stem = part.partition(".")[0].rstrip(" ").upper()
        if part.endswith((" ", ".")) or DEVICE.fullmatch(stem):
            raise ValueError


def check_file(info):
    if not stat.S_ISREG(info.st_mode) or not 0 <= info.st_size <= MAX_BYTES:
        raise ValueError


def read_input(path):
    check_file(os.stat(path))
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NONBLOCK", 0)
    descriptor = os.open(path, flags)
    try:
        check_file(os.fstat(descriptor))
        with os.fdopen(descriptor, "rb", closefd=False) as stream:
            data = stream.read(MAX_BYTES + 1)
    finally:
        os.close(descriptor)
    if len(data) > MAX_BYTES:
        raise ValueError
    return data


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError
        result[key] = value
    return result


def reject_constant(_token):
    raise ValueError


def bounded_integer(token):
    # The budget is the only valid JSON number. Longer integer tokens cannot fit.
    if len(token) > 10:
        raise ValueError
    return int(token)


def parse_http_date(hint):
    fields = HTTP_DATE.fullmatch(hint)
    if fields is None:
        raise ValueError
    year = int(fields["year"])
    if year < 1900:
        raise ValueError
    result = datetime(year, MONTHS.index(fields["month"]) + 1, int(fields["day"]),
                      int(fields["hour"]), int(fields["minute"]), int(fields["second"]), tzinfo=timezone.utc)
    if WEEKDAYS[result.weekday()] != fields["weekday"]:
        raise ValueError
    return result


def audit(document):
    if not isinstance(document, dict) or document.keys() != FIELDS:
        raise ValueError
    hint = document["retry_after"]
    observed = document["observed_at"]
    budget = document["max_delay_seconds"]
    if not isinstance(hint, str) or len(hint) > 128:
        raise ValueError
    if not isinstance(observed, str) or not OBSERVED.fullmatch(observed):
        raise ValueError
    if type(budget) is not int or not 0 <= budget <= MAX_SECONDS:
        raise ValueError
    observed_at = datetime.fromisoformat(observed)

    hint = hint.strip(" \t")
    if DELTA.fullmatch(hint):
        form = "delta_seconds"
        seconds = int(hint)
        if seconds > MAX_SECONDS:
            raise ValueError
    else:
        form = "http_date"
        difference = parse_http_date(hint) - observed_at
        seconds = difference.days * 86400 + difference.seconds

    delay = max(0, seconds)
    return {
        "status": "within_budget" if delay <= budget else "over_budget",
        "form": form,
        "delay_seconds": delay,
        "expired": seconds < 0,
    }


def emit(data, code):
    remaining = memoryview(data)
    try:
        while remaining:
            written = os.write(1, remaining)
            if written <= 0:
                return 2
            remaining = remaining[written:]
    except OSError:
        return 2
    return code


def main(args):
    if args in (["--help"], ["-h"]):
        return emit(b"Usage: python retry_after_budget.py INPUT.json\n", 0)
    try:
        path, = args
        check_path(path)
        document = json.loads(read_input(path).decode("utf-8"), object_pairs_hook=unique_object,
                              parse_int=bounded_integer, parse_constant=reject_constant)
        report = audit(document)
        code = int(report["status"] == "over_budget")
    except (OSError, ValueError, RecursionError):
        report, code = {"status": "invalid"}, 2
    return emit(json.dumps(report, separators=(",", ":")).encode("ascii") + b"\n", code)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
