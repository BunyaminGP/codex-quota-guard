# Contributing to codex-quota-guard

Issues and pull requests are welcome. This document explains how to set up the development environment, run tests, and adhere to the project's core design principles.

## Setup

The runtime codebase requires only Python's standard library:

- Python 3.10+
- `git` (for testing hard-revert and repository status checks)
- `pytest` (`python -m pip install pytest`)

## Running Tests

Run the test suite locally before pushing:

```bash
python -m pytest -q
```

All tests run across Ubuntu, macOS, and Windows via GitHub Actions (`.github/workflows/ci.yml`).

## Design Principles

If your pull request touches quota detection, gate hooks, or the runner:

1. **Fail Open:**
   If quota cannot be determined (RPC timeout, network drop, or unsupported account), hooks and runner must never crash Codex or block tool calls. Quota protection should degrade gracefully with a warning rather than disrupting work.

2. **Opt-in for Destructive Actions:**
   Hard abort automatic revert (`git stash`) is disabled by default and requires explicit user opt-in (`--enable-hard-abort` or `CODEX_QUOTA_HARD_ABORT=1`). Automatic revert must only trigger if the task started with a clean working tree (`checkpoint_clean: true`), and must verify `refs/stash` changed.

3. **No Credential Access:**
   Never read tokens, session keys, or credential files from disk (`~/.codex/`, environment tokens, or keychain). Quota is read exclusively via the official Codex app-server RPC (`account/rateLimits/read`).

4. **Security Boundaries:**
   Settings like `hard_abort` or webhook URLs (`CODEX_QUOTA_NOTIFY_URL`) must never be loaded from project-controlled files (such as `.codex-quota/config.json`) to prevent untrusted repository exfiltration.

5. **Exact Thread Resumption:**
   The runner (`codex-run`) must capture the exact thread ID and resume only that thread ID. Never fall back to `--last` or ambiguous session continuation.

## Languages

User-facing messages support English (`en`) and Turkish (`tr`) defined in `scripts/common.py`. New messages or updates must provide both language variants.

## License

By contributing, you agree that your contributions are licensed under the [MIT License](LICENSE).
