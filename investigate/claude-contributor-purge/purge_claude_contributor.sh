#!/usr/bin/env bash
#
# purge_claude_contributor.sh — remove the "claude Claude" contributor from
# the agent-torvalds repository.
#
# WHAT THIS IS FOR
# ----------------
# The operator does not want a "claude Claude" contributor in the repository.
# That contributor is NOT a pull-request footer.  GitHub builds its
# contributor list from the `Co-Authored-By:` trailers of the commit
# messages, and renders an unlinked trailer as a contributor with
# `login: "claude"` and a display name taken from the trailer itself —
# which is why the entry reads "claude" / "Claude Opus 4.8 (1M context)".
#
# Exactly one commit in the repository carries such a trailer:
#
#   6d330699c545fef9c97d5439632beeaf84f44f11  Initial commit: shodan-toolkit
#       Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
#
# It entered `master` through the `git subtree` merge 3e4eab8, so removing
# the trailer means **rewriting history**: every descendant of that commit
# gets a new SHA, and the affected branches have to be force-pushed.
#
# The rewrite is done in a scratch **mirror** clone, so the operator's
# working copy is never touched.  The push is a separate, explicit step.
#
# USAGE
#   ./purge_claude_contributor.sh              # dry run: rewrite + verify
#   ./purge_claude_contributor.sh --apply      # ...and force-push
#
# OPTIONS
#   --apply          push the rewritten branches to origin (destructive)
#   --scratch DIR    where to build the scratch clone
#                    (default: /tmp/agent-torvalds-claude-purge)
#
set -euo pipefail

REPO="KostiantynBushko/agent-torvalds"
REMOTE="git@github.com:${REPO}.git"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_CLONE="${SOURCE_CLONE:-/home/kbush/ai-agent-investiagte/agent-torvalds}"

APPLY=0
SCRATCH="/tmp/agent-torvalds-claude-purge"

while [ $# -gt 0 ]; do
  case "$1" in
    --apply)   APPLY=1; shift ;;
    --scratch) SCRATCH="$2"; shift 2 ;;
    -h|--help) sed -n '2,40p' "$0"; exit 0 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done

FILTER_REPO="$(command -v git-filter-repo || true)"
if [ -z "$FILTER_REPO" ]; then
  if [ -x "${SOURCE_CLONE}/.venv/bin/git-filter-repo" ]; then
    FILTER_REPO="${SOURCE_CLONE}/.venv/bin/git-filter-repo"
  else
    echo "git-filter-repo is not installed.  Install it with:" >&2
    echo "    pip install git-filter-repo" >&2
    exit 3
  fi
fi

say() { printf '\n\033[1m== %s\033[0m\n' "$*"; }

# ---------------------------------------------------------------- 1. baseline
say "1. baseline: the original refs"

cd "$SOURCE_CLONE"
ORIGINAL_MASTER_TREE="$(git rev-parse master^{tree})"
ORIGINAL_MASTER_COUNT="$(git rev-list --count master)"
OFFENDING="$(git log --all --regexp-ignore-case --fixed-strings \
  --grep=claude --format='%H' | sort -u)"
if [ -z "$OFFENDING" ]; then
  echo "no commit message mentions Claude — nothing to purge."
  exit 0
fi
echo "offending commit(s):"
echo "$OFFENDING" | sed 's/^/  /'
echo "master tree before: $ORIGINAL_MASTER_TREE"
echo "master commits before: $ORIGINAL_MASTER_COUNT"

# The branches that carry the offending commit — these are the ones that
# have to be rewritten and force-pushed.
AFFECTED_REFS="$(git for-each-ref --contains "$(echo "$OFFENDING" | head -1)" \
  --format='%(refname)' refs/heads refs/remotes/origin \
  | grep -v '/HEAD$' | sort -u)"
echo "refs to rewrite: $(echo "$AFFECTED_REFS" | wc -l)"

# ------------------------------------------------------------- 2. scratch copy
say "2. scratch mirror clone at $SCRATCH"

rm -rf "$SCRATCH"
git clone --mirror --quiet "$REMOTE" "$SCRATCH"
# A mirror clone of GitHub also fetches refs/pull/*, which must never be
# pushed back.  Drop them from the scratch clone.
if git -C "$SCRATCH" for-each-ref refs/pull --format='%(refname)' | grep -q .; then
  git -C "$SCRATCH" for-each-ref refs/pull --format='%(refname)' \
    | xargs -r -n1 git -C "$SCRATCH" update-ref -d
  echo "dropped the refs/pull/* mirrors"
fi
echo "heads in scratch: $(git -C "$SCRATCH" for-each-ref refs/heads | wc -l)"
echo "tags in scratch:  $(git -C "$SCRATCH" for-each-ref refs/tags | wc -l)"

# ----------------------------------------------------------------- 3. rewrite
say "3. rewrite: strip the Claude trailer from every commit message"

( cd "$SCRATCH" && "$FILTER_REPO" --force \
    --message-callback "$(cat "${SCRIPT_DIR}/strip_claude_trailer.py")" \
    --quiet ) 2>&1 | sed 's/^/  /' || true

# `git filter-repo` deletes the `origin` remote on purpose — it is a safety
# measure against pushing a rewritten history by accident.  The push below
# is the whole point of this script, so the remote is put back here, after
# the rewrite, and it is the only place the remote is re-added.
if git -C "$SCRATCH" remote get-url origin >/dev/null 2>&1; then
  git -C "$SCRATCH" remote set-url origin "$REMOTE"
else
  git -C "$SCRATCH" remote add origin "$REMOTE"
fi

# ------------------------------------------------------------------ 4. verify
say "4. verify"

NEW_MASTER_TREE="$(git -C "$SCRATCH" rev-parse master^{tree})"
NEW_MASTER_COUNT="$(git -C "$SCRATCH" rev-list --count master)"
FAILED=0

if [ "$NEW_MASTER_TREE" = "$ORIGINAL_MASTER_TREE" ]; then
  echo "  PASS  master's tree is byte-identical ($NEW_MASTER_TREE)"
else
  echo "  FAIL  master's tree changed:"
  echo "        before $ORIGINAL_MASTER_TREE"
  echo "        after  $NEW_MASTER_TREE"
  FAILED=1
fi

if [ "$NEW_MASTER_COUNT" = "$ORIGINAL_MASTER_COUNT" ]; then
  echo "  PASS  master's commit count is unchanged ($NEW_MASTER_COUNT)"
else
  echo "  FAIL  master's commit count changed: $ORIGINAL_MASTER_COUNT -> $NEW_MASTER_COUNT"
  FAILED=1
fi

REMAINING="$(git -C "$SCRATCH" log --all --regexp-ignore-case \
  --fixed-strings --grep=claude --format='%H' | sort -u)"
if [ -z "$REMAINING" ]; then
  echo "  PASS  no commit message of any ref mentions Claude any more"
else
  echo "  FAIL  these commits still mention Claude:"
  echo "$REMAINING" | sed 's/^/        /'
  FAILED=1
fi

# Every rewritten branch must keep its tree — only the commit messages and
# therefore the SHAs change.
echo "  branch check (tree identity):"
while read -r ref; do
  name="${ref#refs/heads/}"
  name="${name#refs/remotes/origin/}"
  [ -z "$name" ] && continue
  old_tree="$(git -C "$SOURCE_CLONE" rev-parse "$ref^{tree}" 2>/dev/null || true)"
  new_tree="$(git -C "$SCRATCH" rev-parse "refs/heads/$name^{tree}" 2>/dev/null || true)"
  old_sha="$(git -C "$SOURCE_CLONE" rev-parse "$ref" 2>/dev/null || true)"
  new_sha="$(git -C "$SCRATCH" rev-parse "refs/heads/$name" 2>/dev/null || true)"
  if [ "$old_tree" = "$new_tree" ] && [ -n "$old_tree" ]; then
    printf '    PASS  %-55s tree kept, %s -> %s\n' "$name" \
      "${old_sha:0:8}" "${new_sha:0:8}"
  else
    printf '    FAIL  %-55s tree changed\n' "$name"
    FAILED=1
  fi
done <<< "$AFFECTED_REFS"

if [ "$FAILED" -ne 0 ]; then
  echo
  echo "VERIFICATION FAILED — nothing was pushed."
  exit 1
fi

# ------------------------------------------------------------------- 5. push
say "5. push"

BRANCHES=()
while read -r ref; do
  name="${ref#refs/heads/}"
  name="${name#refs/remotes/origin/}"
  [ -z "$name" ] && continue
  case " ${BRANCHES[*]-} " in
    *" $name "*) continue ;;
  esac
  BRANCHES+=("$name")
done <<< "$AFFECTED_REFS"

if [ "$APPLY" -ne 1 ]; then
  echo "DRY RUN — nothing was pushed."
  echo "The following branches would be force-pushed:"
  printf '    %s\n' "${BRANCHES[@]}"
  echo
  echo "Re-run with --apply to push them."
  exit 0
fi

echo "force-pushing ${#BRANCHES[@]} branch(es) to origin..."
git -C "$SCRATCH" push --force --quiet origin "${BRANCHES[@]}"
echo "pushed."

say "done"
echo "Next: refresh the operator's clone and re-run the verifier."
echo "    git -C $SOURCE_CLONE fetch --all --prune"
echo "    git -C $SOURCE_CLONE reset --hard origin/master"
echo "    python3 $SCRIPT_DIR/verify_no_claude.py"
