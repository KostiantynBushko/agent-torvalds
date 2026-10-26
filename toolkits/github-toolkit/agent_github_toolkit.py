"""
GitHub Toolkit - the LlamaIndex agent adapter.

This module is the **agent-facing half** of the GitHub toolkit.  It turns
the GitHub operations of :mod:`operations` into LlamaIndex ``FunctionTool``
objects, so the agent can call them.

It is the **only** module of the toolkit that knows about LlamaIndex.  The
library half (``operations.py``) stays free of it, so the GitHub
operations remain usable - and testable - as a plain Python library.

Importing this adapter
----------------------
The toolkit lives in a hyphenated directory (``toolkits/github-toolkit/``),
which is not a valid Python identifier, so it is reached through the alias
that ``toolkits/__init__.py`` registers::

    from toolkits.github_toolkit.agent_github_toolkit import get_all_tools

The adapter pulls the core package in with a **relative** import
(``from . import ...``), so the adapter and the library share one set of
module objects - there is never a second copy of ``operations.py`` in
memory.

The adapter also re-exports the 13 GitHub functions, so a star import
keeps working the way it did when the toolkit was a single module::

    from toolkits.github_toolkit.agent_github_toolkit import *

Category: Version Control
Retriever Keywords: github, pull request, PR, api, review, comment, merge, authentication
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
    git_check_auth,
    git_get_user_info,
    git_configure_credentials,
    github_create_pull_request,
    github_list_pull_requests,
    github_get_pull_request,
    github_update_pull_request,
    github_close_pull_request,
    github_merge_pull_request,
    github_comment_on_pull_request,
    github_review_file_changes,
    github_get_pull_request_comments,
    github_get_pull_request_reviews,
)
from . import GITHUB_API_BASE

logger = logging.getLogger(__name__)


def get_all_tools() -> list[FunctionTool]:
    """
    Return all GitHub tools as FunctionTool objects for on-demand loading.

    Each tool includes category metadata for better retrieval.

    Returns:
        list[FunctionTool]: List of GitHub FunctionTool objects
    """
    logger.info("github get_all_tools called")
    return [
        # Tier 4: Authentication & Configuration
        FunctionTool.from_defaults(
            fn=git_check_auth,
            description="Verify GitHub authentication status. Use for checking if GitHub API access is working. Category: Version Control",
        ),
        FunctionTool.from_defaults(
            fn=git_get_user_info,
            description="Get GitHub user information. Use for retrieving profile and identity details. Category: Version Control",
        ),
        FunctionTool.from_defaults(
            fn=git_configure_credentials,
            description="Configure Git credentials. Use for setting up user identity for commits. Category: Version Control",
        ),
        # Tier 3: GitHub PR Operations
        FunctionTool.from_defaults(
            fn=github_create_pull_request,
            description="Create a Pull Request on GitHub. Use for submitting PRs from feature branches. Category: Version Control",
        ),
        FunctionTool.from_defaults(
            fn=github_list_pull_requests,
            description="List Pull Requests for a repository. Use for inspecting open/closed PRs. Category: Version Control",
        ),
        FunctionTool.from_defaults(
            fn=github_get_pull_request,
            description="Get details of a specific Pull Request. Use for viewing PR information. Category: Version Control",
        ),
        FunctionTool.from_defaults(
            fn=github_update_pull_request,
            description="Update a Pull Request's title, description, or other metadata. Use for modifying PRs. Category: Version Control",
        ),
        FunctionTool.from_defaults(
            fn=github_close_pull_request,
            description="Close a Pull Request without merging. Use for abandoning or dismissing PRs. Category: Version Control",
        ),
        FunctionTool.from_defaults(
            fn=github_merge_pull_request,
            description="Merge a Pull Request. Use for completing the PR workflow with merge/squash/rebase. Category: Version Control",
        ),
        FunctionTool.from_defaults(
            fn=github_comment_on_pull_request,
            description="Add a comment to a Pull Request. Use for leaving feedback or notes. Category: Version Control",
        ),
        FunctionTool.from_defaults(
            fn=github_review_file_changes,
            description="Get file changes in a Pull Request. Use for reviewing diffs and patches. Category: Version Control",
        ),
        FunctionTool.from_defaults(
            fn=github_get_pull_request_comments,
            description="Get all comments on a Pull Request. Use for retrieving discussion and feedback. Category: Version Control",
        ),
        FunctionTool.from_defaults(
            fn=github_get_pull_request_reviews,
            description="Get review submissions for a Pull Request. Use for checking approval status. Category: Version Control",
        ),
    ]


__all__ = [
    "get_all_tools",
    # The tool surface - re-exported so a star import keeps working.
    "git_check_auth",
    "git_get_user_info",
    "git_configure_credentials",
    "github_create_pull_request",
    "github_list_pull_requests",
    "github_get_pull_request",
    "github_update_pull_request",
    "github_close_pull_request",
    "github_merge_pull_request",
    "github_comment_on_pull_request",
    "github_review_file_changes",
    "github_get_pull_request_comments",
    "github_get_pull_request_reviews",
    "GITHUB_API_BASE",
    "logger",
]
