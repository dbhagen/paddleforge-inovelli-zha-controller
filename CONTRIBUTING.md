# Contributing

Thanks for helping improve **Paddleforge Inovelli ZHA Controller**!

## Development setup

1. Fork and clone the repo.
2. Create a virtual environment and install tooling:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -U pip ruff homeassistant
   ```
3. Symlink (or copy) the integration into a dev Home Assistant config to test live:
   ```bash
   ln -s "$(pwd)/custom_components/paddleforge_inovelli_zha_controller" /path/to/ha/config/custom_components/
   ```
   Restart HA and add the integration.
4. Lint/format before committing:
   ```bash
   ruff check .
   ruff format --check .
   ```

## Commit messages — Conventional Commits

This repo uses [Conventional Commits](https://www.conventionalcommits.org/). The version and
`CHANGELOG.md` are generated automatically from commit history by
[release-please](https://github.com/googleapis/release-please), so the format matters.

Format: `type(optional scope): description`

| Type | Purpose | Release effect (pre-1.0) |
| --- | --- | --- |
| `feat` | New feature | minor |
| `fix` | Bug fix | patch |
| `perf` | Performance improvement | patch |
| `docs` | Docs only | none |
| `refactor` | Code change, no behavior change | none |
| `test` | Tests only | none |
| `chore` | Tooling/maintenance | none |
| `ci` | CI config | none |
| `build` | Build/deps | none |

Breaking changes: append `!` after the type/scope (`feat!:`) or add a `BREAKING CHANGE:`
footer. While pre-1.0, a breaking change bumps the **minor**.

Examples:
```
feat(led): cycle color palette on single tap
fix: ignore double-tap events from non-Inovelli devices
feat!: rename the pairing option keys
```

## Pull requests

1. Branch off `main`, keep changes focused.
2. Ensure `ruff check`, `ruff format --check`, hassfest, and HACS validation pass (CI runs
   these on every PR).
3. Open a PR against `main` and fill out the template. **The PR title must be a valid
   Conventional Commit** — it becomes the squash-merge commit that drives releases (a CI check
   enforces this).

## How releases work

- Merges to `main` are analyzed by **release-please**, which opens/updates a "release PR" that
  bumps the version in `custom_components/paddleforge_inovelli_zha_controller/manifest.json` and updates
  `CHANGELOG.md`.
- Merging that release PR tags a new version and publishes a GitHub Release; HACS then offers
  it as an update.
- You never edit `version` in `manifest.json` by hand.
