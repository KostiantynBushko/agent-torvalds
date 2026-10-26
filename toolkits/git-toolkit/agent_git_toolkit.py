"""
Git Toolkit - the LlamaIndex agent adapter.

This module is the **agent-facing half** of the Git toolkit.  It turns the
Git operations of :mod:`operations` into LlamaIndex ``FunctionTool`` objects,
so the agent can call them.

It is the **only** module of the toolkit that knows about LlamaIndex.  The
library half (``operations.py``) stays free of it, so the Git operations
remain usable - and testable - as a plain Python library.

Importing this adapter
----------------------

The toolkit lives in a hyphenated directory (``toolkits/git-toolkit/``),
which is not a valid Python identifier, so it is reached through the alias
that ``toolkits/__init__.py`` registers::

    from toolkits.git_toolkit.agent_git_toolkit import get_all_tools

The adapter pulls the core package in with a **relative** import
(``from . import ...``), so the adapter and the library share one set of
module objects - there is never a second copy of ``operations.py`` in
memory.

The adapter also re-exports the 27 Git functions, so a star import keeps
working the way it did when the toolkit was a single module::

    from toolkits.git_toolkit.agent_git_toolkit import *

Category: Version Control
Retriever Keywords: git, repository, commit, branch, remote, changelog, version control, diff, merge, sync
"""

from __future__ import annotations

import logging

from llama_index.core.tools import FunctionTool

# The core package is imported with a *relative* import.  That is the only
# form that resolves both inside this repository (where the directory name
# carries a hyphen) and in a standalone installation of the package.
#
# The names come from the package itself, so the adapter and the library
# always share one set of module objects.
from . import (
    git_get_latest_commit,
    git_init_repo,
    git_add_files,
    git_commit,
    git_get_status,
    git_generate_changelog,
    git_get_recent_changes,
    git_update_changelog,
    git_get_email,
    git_init_and_commit,
    git_add_all_changes,
    git_remote_add,
    git_push,
    git_remote_get,
    git_set_upstream,
    git_pull,
    git_fetch,
    git_branch_list,
    git_branch_create,
    git_branch_checkout,
    git_branch_delete,
    git_branch_rename,
    git_diff,
    git_diff_staged,
    git_merge,
    git_rebase,
    git_log_compare,

)

# The operations carry the logger; the adapter re-exports it so that the
# whole toolkit logs through one logger, as it did when the toolkit was a
# single module.
from . import logger

__all__ = [
    "get_all_tools",
    "logger",
    "git_get_latest_commit",
    "git_init_repo",
    "git_add_files",
    "git_commit",
    "git_get_status",
    "git_generate_changelog",
    "git_get_recent_changes",
    "git_update_changelog",
    "git_get_email",
    "git_init_and_commit",
    "git_add_all_changes",
    "git_remote_add",
    "git_push",
    "git_remote_get",
    "git_set_upstream",
    "git_pull",
    "git_fetch",
    "git_branch_list",
    "git_branch_create",
    "git_branch_checkout",
    "git_branch_delete",
    "git_branch_rename",
    "git_diff",
    "git_diff_staged",
    "git_merge",
    "git_rebase",
    "git_log_compare",
]


def get_all_tools() -> list[FunctionTool]:
    """
    Return all Git tools as FunctionTool objects for on-demand loading.
    
    Each tool includes category metadata for better retrieval.
    
    Returns:
        list[FunctionTool]: List of Git FunctionTool objects
    """
    logger.info("get_all_tools called")
    return [
        FunctionTool.from_defaults(
            fn=git_get_latest_commit,
            description="Get the latest commit hash. Use for tracking current revision. Category: Version Control",
        ),
        FunctionTool.from_defaults(
            fn=git_init_repo,
            description="Initialize a new Git repository. Use for creating fresh repos. Category: Version Control",
        ),
        FunctionTool.from_defaults(
            fn=git_add_files,
            description="Add files to staging area. The 'files' parameter must be a list of file path strings, e.g. ['file.py', 'README.md'] or ['.'] for all files. Verifies staging success via git status. Use for preparing commits. Category: Version Control",
        ),
        FunctionTool.from_defaults(
            fn=git_commit,
            description="Create a commit with a message. Use for saving staged changes. Category: Version Control",
        ),
        FunctionTool.from_defaults(
            fn=git_get_status,
            description="Get repository status. Use for inspecting changes and untracked files. Category: Version Control",
        ),
        FunctionTool.from_defaults(
            fn=git_generate_changelog,
            description="Generate changelog from commit history. Use for release notes and documentation. Category: Version Control",
        ),
        FunctionTool.from_defaults(
            fn=git_get_recent_changes,
            description="Get recent commits with author and date. Use for inspecting history. Category: Version Control",
        ),
        FunctionTool.from_defaults(
            fn=git_update_changelog,
            description="Update changelog with a new entry. Use for manual changelog management. Category: Version Control",
        ),
        FunctionTool.from_defaults(
            fn=git_get_email,
            description="Get user email from Git config. Use for identity inspection. Category: Version Control",
        ),
        FunctionTool.from_defaults(
            fn=git_init_and_commit,
            description="Initialize repo and make first commit. Use for quick bootstrap. Category: Version Control",
        ),
        FunctionTool.from_defaults(
            fn=git_add_all_changes,
            description="Add all changed and untracked files to staging area. Uses git_get_status internally, supports relative paths like '.', validates path existence. Use for auto-staging all changes. Category: Version Control",
        ),
        FunctionTool.from_defaults(
            fn=git_remote_add,
            description="Add a remote repository. Use for configuring push/pull URLs. Category: Version Control",
        ),
        FunctionTool.from_defaults(
            fn=git_push,
            description="Push changes to remote. Use for uploading commits. Category: Version Control",
        ),
        FunctionTool.from_defaults(
            fn=git_remote_get,
            description="List configured remotes. Use for inspecting remote URLs. Category: Version Control",
        ),
        FunctionTool.from_defaults(
            fn=git_set_upstream,
            description="Set upstream tracking for a branch. Use for linking local to remote branches. Category: Version Control",
        ),
        # Branch Management Tools
        FunctionTool.from_defaults(
            fn=git_branch_list,
            description="List all branches (local or remote). Use for inspecting available branches. Category: Version Control",
        ),
        FunctionTool.from_defaults(
            fn=git_branch_create,
            description="Create a new branch. Use for creating feature/fix branches. Category: Version Control",
        ),
        FunctionTool.from_defaults(
            fn=git_branch_checkout,
            description="Switch to a branch. Use for changing the working branch. Category: Version Control",
        ),
        FunctionTool.from_defaults(
            fn=git_branch_delete,
            description="Delete a branch. Use for cleaning up merged/abandoned branches. Category: Version Control",
        ),
        FunctionTool.from_defaults(
            fn=git_branch_rename,
            description="Rename the current branch. Use for fixing branch naming. Category: Version Control",
        ),
        # Diff & Sync Tools
        FunctionTool.from_defaults(
            fn=git_diff,
            description="Show file differences. Use for comparing working tree, branches, or commits. Category: Version Control",
        ),
        FunctionTool.from_defaults(
            fn=git_diff_staged,
            description="Show staged differences. Use for reviewing changes before commit. Category: Version Control",
        ),
        FunctionTool.from_defaults(
            fn=git_pull,
            description="Pull from remote. Use for fetching and merging changes. Category: Version Control",
        ),
        FunctionTool.from_defaults(
            fn=git_fetch,
            description="Fetch from remote. Use for updating remote refs without merging. Category: Version Control",
        ),
        FunctionTool.from_defaults(
            fn=git_merge,
            description="Merge branches. Use for integrating feature branches. Category: Version Control",
        ),
        FunctionTool.from_defaults(
            fn=git_rebase,
            description="Rebase commits. Use for cleaning up commit history. Category: Version Control",
        ),
        FunctionTool.from_defaults(
            fn=git_log_compare,
            description="Compare branch logs. Use for seeing what's diverged between branches. Category: Version Control",
        ),
    ]
