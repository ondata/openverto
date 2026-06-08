# Release procedure

Mirrors the `opensdmx` flow: manual, tag-based, published to PyPI with `twine`.

## Subrelease

Use a subrelease for a low-risk patch that does not change the release flow,
for example a bug fix, a small CLI UX correction, or a docs-only follow-up that
should ship as the next patch version.

Patch-version pattern:

- `0.1.0` -> `0.1.1`
- `1.2.3` -> `1.2.4`

## Prerequisites

- PyPI credentials configured for `twine` (token in `~/.pypirc` or env `TWINE_USERNAME=__token__` / `TWINE_PASSWORD=<pypi-token>`)
- `gh` CLI authenticated

## Steps

Every release MUST complete all steps in order.

```bash
# 1. Bump version in pyproject.toml
#    Edit version = "X.Y.Z" → "X.Y.Z+1"

# 2. Update the lockfile
uv lock

# 3. Update LOG.md with the changes

# 4. Run linter and full test suite — both must pass before any publish step
uv run ruff check src/
uv run pytest                 # offline suite (live tests skipped by default)
uv run pytest -m live         # optional: verify against the live IGM service

# 5. Commit and tag
git add -u
git commit -m "chore: bump version to vX.Y.Z"
git tag vX.Y.Z

# 6. Push with tags
git push origin main --tags

# 7. Create the GitHub release
gh release create vX.Y.Z --title "vX.Y.Z" --notes "release notes here"

# 8. Build and publish to PyPI
uv build
twine upload dist/openverto-X.Y.Z*

# 9. Update the local CLI install
uv tool install --editable .
```

## Checklist

- [ ] Version bumped in `pyproject.toml`
- [ ] `uv.lock` updated (`uv lock`)
- [ ] `LOG.md` updated
- [ ] Linter passes (`uv run ruff check src/`)
- [ ] Tests pass (`uv run pytest`)
- [ ] Commit created
- [ ] Git tag created (`git tag vX.Y.Z`)
- [ ] Pushed to GitHub with tags (`git push origin main --tags`)
- [ ] GitHub release created with notes (`gh release create`)
- [ ] Built and published to PyPI (`uv build && twine upload`)
- [ ] Local CLI updated (`uv tool install --editable .`)
