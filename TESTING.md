# Testing

Run these commands from the repository root with Python 3.11 or later.

```sh
python -B -m unittest discover -s tests -v
python -B ci_checks.py
```

The tests cover ASCII decimal syntax and boundaries, strict date and JSON forms, exact budget equality, expiry, leap-day arithmetic, timezone environment changes, unsafe paths, descriptor revalidation and quiet broken stdout handling. The four synthetic examples check complete JSON reports, exit codes and empty stderr. CI runs the suite and the examples on Ubuntu and Windows.
