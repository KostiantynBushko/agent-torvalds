---
name: release
description: Prepare and publish a release of this project. Use it when the user asks to release, publish, ship or tag a version.
---

# Release

A release is a **changelog entry, a version declaration, a merge into master
and a tag**.  Nothing is published from a feature branch, and the operator
pushes.

## The version is read, not chosen

The version is declared in two places, and a release makes those declarations
true:

| file | what it holds |
|---|---|
| `deploy/deploy-torvalds.sh` | `readonly SCRIPT_VERSION="1.0.0"` |
| `project_manager/__init__.py` | `__version__ = "1.0.0"` |

Read the version from there.  Do not invent one, and do not bump one of the
two without the other — the deployment script and the project manager must
name the same version.

There is no `pyproject.toml` at the root of this project; the version lives
only in those two files.

## The checklist

1. **The tests.**  `.venv/bin/python scripts/ci_test_gate.py` — `new failures`
   must be `0`.  The suite is always red; the gate is what decides.
2. **The changelog.**  In `CHANGELOG.md`, turn the `## [Unreleased]` heading
   into `## [<version>] - <YYYY-MM-DD>`, and update the link block at the
   bottom of the file:

   ```
   [Unreleased]: https://github.com/KostiantynBushko/agent-torvalds/compare/v<version>...HEAD
   [<version>]: https://github.com/KostiantynBushko/agent-torvalds/releases/tag/v<version>
   ```

   The `[Unreleased]` link then points at the version that was just released.
3. **The version declarations.**  Both files of the table above, to the new
   version.
4. **The summary.**  The release section opens with a short paragraph that
   says what the release *is* — how many tools, what changed, and the two or
   three things that matter.  The entry of `v1.0.0` is the model.
5. **The commit**, on a branch, reviewed through a pull request:

   ```bash
   git checkout -b release/v<version> master
   git commit -am "docs: the changelog for v<version>"
   ```

   The changelog, the version declarations and the summary go together.  They
   are one commit, because a tag that names a version the code does not carry
   is a lie.
6. **The merge.**  The operator merges the pull request into `master`.
7. **The tag**, after the merge:

   ```bash
   git tag -a v<version> -m "v<version> — <one line about the release>"
   git push origin v<version>
   ```

8. **The GitHub release**, with the same text as the tag message:

   ```bash
   gh release create v<version> --title "v<version>" --notes "<the summary>"
   ```

## The rules that hold at every step

* **Never push without the operator's approval.**  The branch, the tag and
  the release are three separate pushes, and each of them needs it.
* **Never merge.**  The pull request is opened and reviewed; the operator
  merges it.
* **The changelog is the history.**  Every entry carries the reason, not only
  the change: what was wrong, what was measured, and why the fix is the one
  that was chosen.  The entries of `v1.0.0` are the model.
