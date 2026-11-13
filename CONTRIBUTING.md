# Contributing

Contributions should improve reliability, clarity, reproducibility, or integrations without introducing hidden network calls into the core evaluation path.

1. Open an issue describing the failure mode and a minimal reproducible trace.
2. Include failing regression tests before or alongside the fix.
3. Run `python -m unittest discover -s tests -v` and `python -m jev eval examples/suite.json`.
4. Keep policy reason codes stable unless a versioned change is intended.
5. Do not include credentials, personal data, real customer logs, or proprietary traces in issues or tests.

Pull requests should describe the behavior change, negative cases, and the expected compatibility impact. The core currently targets Python 3.11+ and uses the standard library at runtime.
