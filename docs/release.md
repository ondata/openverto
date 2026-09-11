# Release procedure

Mirrors the `opensdmx` flow: manual, tag-based, published to PyPI with `twine`.

This document is the source of truth. Two automations point back to it, and
neither replaces it:

- `/release` (`.claude/skills/release/SKILL.md`) walks these steps. It is
  user-invocable only, because step 8 must never be model-triggered.
- `.claude/hooks/lock-version-sync.sh` flags a `uv.lock` left behind by a
  version bump, which is the step-2 failure that shipped in v0.2.4.

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
- Working tree clean and `main` up to date (`git pull`)

> A published PyPI version is permanent: a version number can never be reused,
> even after deleting the release. Everything before step 8 is reversible, step 8
> is not. Do not start unless the linter and the test suite pass.

## Steps

Every release MUST complete all steps in order.

```bash
# 1. Bump version in pyproject.toml
#    Edit version = "X.Y.Z" → "X.Y.Z+1"
#    Already bumped by a merged PR? Skip to step 2 and keep going: the remaining
#    steps still apply, and step 2 in particular is the one that gets missed.

# 2. Update the lockfile, then CHECK it actually moved
uv lock
grep -A1 'name = "openverto"' uv.lock      # must print the new X.Y.Z
#    uv.lock pins openverto's own version, so it goes stale on every bump. A PR
#    that bumps pyproject.toml without running `uv lock` leaves it behind.
#    A project hook warns about this after any edit to pyproject.toml, but the
#    hook only fires when Claude does the edit: keep checking it here.

# 3. Update LOG.md with the changes

# 4. Run linter and full test suite — both must pass before any publish step
uv run ruff check src/
uv run pytest                 # offline suite (live tests skipped by default)
uv run pytest -m live         # verify against the live IGM service

# 5. Commit and tag
git add -u
git commit -m "chore: bump version to vX.Y.Z"   # skip if nothing is staged
git tag vX.Y.Z

# 6. Push with tags
git push origin main --tags

# 7. Create the GitHub release
gh release create vX.Y.Z --title "vX.Y.Z" --notes "release notes here"

# 8. Build, check, then publish to PyPI  <-- IRREVERSIBLE
uv build
twine check dist/openverto-X.Y.Z*          # metadata/README must render
twine upload dist/openverto-X.Y.Z*

# 9. Update the local CLI install
uv tool install --editable . --force       # --force: replaces the current install

# 10. Verify what users will actually get
curl -sS https://pypi.org/pypi/openverto/json | jq -r .info.version   # = X.Y.Z
openverto --version                                                   # = X.Y.Z
```

## Post-release smoke test

`--version` only proves the install. Run one real conversion against an empty
cache, because a cache hit can mask a broken service path entirely:

```bash
OPENVERTO_CACHE_DIR=$(mktemp -d) openverto convert --from 4265 --to 6706 11.2558 43.7696
```

It must exit 0 and print converted coordinates. `mktemp -d` is what makes this a
real check: it forces a cache miss, so the request actually reaches the service.
Running the same command against the normal cache proves nothing. Keep the
coordinate inside the IGM grid (Italy and surrounding seas), or the service
rejects it and the check fails for the wrong reason.

## Checklist

- [ ] Version bumped in `pyproject.toml`
- [ ] `uv.lock` updated **and verified** to show the new version (`uv lock`)
- [ ] `LOG.md` updated
- [ ] Linter passes (`uv run ruff check src/`)
- [ ] Offline tests pass (`uv run pytest`)
- [ ] Live tests pass (`uv run pytest -m live`)
- [ ] Commit created
- [ ] Git tag created (`git tag vX.Y.Z`)
- [ ] Pushed to GitHub with tags (`git push origin main --tags`)
- [ ] GitHub release created with notes (`gh release create`)
- [ ] Artifacts pass `twine check`
- [ ] Published to PyPI (`twine upload`)
- [ ] Local CLI updated (`uv tool install --editable . --force`)
- [ ] PyPI reports the new version as latest
- [ ] Post-release smoke test passes (one live conversion, empty cache)
