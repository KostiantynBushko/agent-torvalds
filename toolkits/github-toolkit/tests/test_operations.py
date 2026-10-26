"""
Tests for the GitHub toolkit's library half.

The GitHub toolkit is the first toolkit of the "every toolkit is a module"
refactoring that arrived **without** a test suite.  The other two had
tests that moved with them; this one had nothing, so a move here would
have been an entirely unverified refactoring.

These tests are that verification.  They pin the behaviour of every
operation, so the refactoring can be checked the way the others were:
the same tests, before and after, with the same result.

**The suite is offline.**  ``requests`` is stubbed at the transport
boundary, so no test reaches ``api.github.com`` and no test needs a
token.  The GitHub CLI is stubbed too, so a developer who happens to have
``gh`` installed - or a ``GITHUB_TOKEN`` exported - gets the same result
as everybody else.

They live inside the hyphenated package directory, so they use
**relative** imports (``from ..operations import ...``).

The suite runs under ``--import-mode=importlib``, which ``pytest.ini``
sets through ``addopts``.
"""

from __future__ import annotations

import json
import subprocess
from typing import Any

import pytest

from ..operations import (
    GITHUB_API_BASE,
    _get_github_token,
    _get_headers,
    _make_request,
    git_check_auth,
    git_configure_credentials,
    git_get_user_info,
    github_close_pull_request,
    github_comment_on_pull_request,
    github_create_pull_request,
    github_get_pull_request,
    github_get_pull_request_comments,
    github_get_pull_request_reviews,
    github_list_pull_requests,
    github_merge_pull_request,
    github_review_file_changes,
    github_update_pull_request,
)
from .. import operations


# ---------------------------------------------------------------------------
# The stubs
# ---------------------------------------------------------------------------


class FakeResponse:
    """A stand-in for a ``requests`` response.

    ``json_data=None`` with ``raise_json=True`` is the case of a body that
    is not JSON at all - the toolkit has to fall back to the raw text.
    """

    def __init__(
        self,
        status_code: int = 200,
        json_data: Any = None,
        text: str = "",
        raise_json: bool = False,
    ) -> None:
        self.status_code = status_code
        self._json_data = json_data
        self.text = text
        self._raise_json = raise_json

    def json(self) -> Any:
        if self._raise_json:
            raise ValueError("Expecting value: line 1 column 1 (char 0)")
        return self._json_data


class Recorder:
    """A stub for ``requests.request`` that records the call it received."""

    def __init__(self) -> None:
        self.calls: list[dict] = []
        # A JSON body by default: several operations read ``result["data"]``
        # without checking it first, and an empty object is the smallest
        # body that keeps them happy.
        self.response = FakeResponse(200, {})
        self.raises: Exception | None = None

    def __call__(self, method: str, url: str, **kwargs: Any) -> FakeResponse:
        self.calls.append({"method": method, "url": url, **kwargs})
        if self.raises is not None:
            raise self.raises
        return self.response

    @property
    def last(self) -> dict:
        assert self.calls, "no request was made"
        return self.calls[-1]


class FakeCompleted:
    """A stand-in for ``subprocess.CompletedProcess``."""

    def __init__(self, returncode: int = 0, stdout: str = "", stderr: str = "") -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch):
    """The developer's own token and GitHub CLI must not reach the tests."""
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)

    def no_gh_cli(*args, **kwargs):
        raise FileNotFoundError("gh")

    monkeypatch.setattr(subprocess, "run", no_gh_cli)


@pytest.fixture
def api(monkeypatch):
    """The stubbed ``requests.request``, with its call log."""
    recorder = Recorder()
    monkeypatch.setattr(operations.requests, "request", recorder)
    return recorder


@pytest.fixture
def token(monkeypatch):
    """Export a token, the way a configured environment would."""
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_testtoken")


# ---------------------------------------------------------------------------
# The token
# ---------------------------------------------------------------------------


class TestGetGithubToken:
    """The token comes from the environment, or from the GitHub CLI."""

    def test_the_environment_variable_wins(self, token, api):
        assert _get_github_token() == "ghp_testtoken"

    def test_the_cli_is_the_fallback(self, monkeypatch):
        monkeypatch.setattr(
            subprocess, "run",
            lambda *a, **k: FakeCompleted(stdout="cli-token\n"),
        )
        assert _get_github_token() == "cli-token"

    def test_the_cli_token_is_stripped(self, monkeypatch):
        monkeypatch.setattr(
            subprocess, "run",
            lambda *a, **k: FakeCompleted(stdout="  cli-token  \n"),
        )
        assert _get_github_token() == "cli-token"

    def test_no_token_at_all(self):
        assert _get_github_token() is None

    def test_an_empty_environment_variable_falls_through(self, monkeypatch):
        """An empty ``GITHUB_TOKEN`` is falsy, so the CLI is tried."""
        monkeypatch.setenv("GITHUB_TOKEN", "")
        monkeypatch.setattr(
            subprocess, "run",
            lambda *a, **k: FakeCompleted(stdout="cli-token"),
        )
        assert _get_github_token() == "cli-token"

    def test_a_failing_cli_is_not_an_error(self, monkeypatch):
        def boom(*args, **kwargs):
            raise subprocess.CalledProcessError(1, "gh")

        monkeypatch.setattr(subprocess, "run", boom)
        assert _get_github_token() is None

    def test_a_missing_cli_is_not_an_error(self):
        # The autouse fixture already makes ``gh`` missing.
        assert _get_github_token() is None

    def test_a_hanging_cli_is_not_an_error(self, monkeypatch):
        def boom(*args, **kwargs):
            raise subprocess.TimeoutExpired("gh", 5)

        monkeypatch.setattr(subprocess, "run", boom)
        assert _get_github_token() is None

    def test_an_empty_cli_token_is_no_token(self, monkeypatch):
        monkeypatch.setattr(
            subprocess, "run",
            lambda *a, **k: FakeCompleted(stdout="   \n"),
        )
        assert _get_github_token() is None

    def test_the_cli_is_called_with_a_timeout(self, monkeypatch):
        seen = {}

        def spy(cmd, **kwargs):
            seen.update({"cmd": cmd, **kwargs})
            return FakeCompleted(stdout="cli-token")

        monkeypatch.setattr(subprocess, "run", spy)
        _get_github_token()
        assert seen["cmd"] == ["gh", "auth", "token"]
        assert seen["timeout"] == 5


# ---------------------------------------------------------------------------
# The headers
# ---------------------------------------------------------------------------


class TestGetHeaders:
    """The headers carry the token when there is one."""

    def test_the_base_headers(self):
        headers = _get_headers()
        assert headers["Accept"] == "application/vnd.github.v3+json"
        assert headers["User-Agent"] == "Torvalds-Agent/1.0"

    def test_no_token_means_no_authorization(self):
        assert "Authorization" not in _get_headers()

    def test_a_token_is_sent(self, token):
        assert _get_headers()["Authorization"] == "token ghp_testtoken"


# ---------------------------------------------------------------------------
# The transport
# ---------------------------------------------------------------------------


class TestMakeRequest:
    """Every status code maps to a documented shape."""

    def test_200_is_a_success(self, api):
        api.response = FakeResponse(200, {"login": "octocat"})
        result = _make_request("GET", "/user")
        assert result == {"success": True, "data": {"login": "octocat"}}

    def test_201_is_a_created(self, api):
        api.response = FakeResponse(201, {"number": 42})
        result = _make_request("POST", "/repos/o/r/pulls")
        assert result["success"] is True
        assert result["status"] == "created"
        assert result["data"] == {"number": 42}

    def test_204_is_a_no_content(self, api):
        api.response = FakeResponse(204)
        result = _make_request("DELETE", "/repos/o/r/pulls/1")
        assert result == {"success": True, "data": None, "status": "no_content"}

    def test_the_url_is_built_from_the_base(self, api):
        _make_request("GET", "/user")
        assert api.last["url"] == f"{GITHUB_API_BASE}/user"

    def test_the_request_has_a_timeout(self, api):
        _make_request("GET", "/user")
        assert api.last["timeout"] == 30

    def test_the_request_carries_the_headers(self, api, token):
        _make_request("GET", "/user")
        assert api.last["headers"]["Authorization"] == "token ghp_testtoken"

    def test_an_api_error_reports_the_message(self, api):
        api.response = FakeResponse(404, {"message": "Not Found"})
        result = _make_request("GET", "/nope")
        assert result["success"] is False
        assert result["status_code"] == 404
        assert result["error"] == "Not Found"

    def test_an_api_error_reports_the_details(self, api):
        api.response = FakeResponse(
            422,
            {"message": "Validation Failed", "errors": [{"field": "title"}]},
        )
        result = _make_request("POST", "/repos/o/r/pulls")
        assert result["error"] == "Validation Failed: {'field': 'title'}"

    def test_a_non_json_error_falls_back_to_the_text(self, api):
        api.response = FakeResponse(500, raise_json=True, text="Internal Server Error")
        result = _make_request("GET", "/user")
        assert result["error"] == "Internal Server Error"

    def test_the_text_is_truncated(self, api):
        api.response = FakeResponse(500, raise_json=True, text="x" * 500)
        result = _make_request("GET", "/user")
        assert len(result["error"]) == 200

    def test_an_empty_error_body_is_unknown(self, api):
        api.response = FakeResponse(500, raise_json=True, text="")
        result = _make_request("GET", "/user")
        assert result["error"] == "Unknown error"

    def test_a_transport_error_is_reported(self, api):
        api.raises = operations.requests.exceptions.RequestException("boom")
        result = _make_request("GET", "/user")
        assert result["success"] is False
        assert result["error"] == "Request failed: boom"

    def test_an_unexpected_error_is_reported(self, api):
        api.raises = ValueError("boom")
        result = _make_request("GET", "/user")
        assert result["success"] is False
        assert result["error"] == "Unexpected error: boom"

    def test_a_failure_never_raises(self, api):
        api.raises = RuntimeError("boom")
        assert _make_request("GET", "/user")["success"] is False


# ---------------------------------------------------------------------------
# Tier 4: authentication and configuration
# ---------------------------------------------------------------------------


class TestCheckAuth:
    """``git_check_auth`` reports the token source and the API access."""

    def test_without_a_token(self, api):
        result = git_check_auth()
        assert result["authenticated"] is False
        assert result["method"] == "none"
        assert result["user"] is None
        assert "No GitHub token found" in result["error"]
        assert api.calls == [], "no request may be made without a token"

    def test_with_a_token_and_a_working_api(self, api, token):
        api.response = FakeResponse(
            200,
            {"login": "octocat", "email": "o@example.com", "name": "Octo Cat"},
        )
        result = git_check_auth()
        assert result == {
            "authenticated": True,
            "method": "token",
            "user": "octocat",
            "email": "o@example.com",
            "name": "Octo Cat",
        }

    def test_the_cli_is_reported_as_gh_cli(self, api, monkeypatch):
        monkeypatch.setattr(
            subprocess, "run",
            lambda *a, **k: FakeCompleted(stdout="cli-token"),
        )
        api.response = FakeResponse(200, {"login": "octocat"})
        result = git_check_auth()
        assert result["method"] == "gh_cli"
        assert result["authenticated"] is True

    def test_a_token_that_the_api_rejects(self, api, token):
        api.response = FakeResponse(401, {"message": "Bad credentials"})
        result = git_check_auth()
        assert result["authenticated"] is False
        assert result["method"] == "token"
        assert result["user"] is None
        assert result["error"] == "Bad credentials"

    def test_a_failure_without_a_message(self, api, token):
        # The transport reports "Unknown error" for an empty body, so the
        # key is always there and the toolkit's own fallback is not used.
        api.response = FakeResponse(500, raise_json=True, text="")
        result = git_check_auth()
        assert result["error"] == "Unknown error"


class TestGetUserInfo:
    """``git_get_user_info`` is a thin wrapper over the transport."""

    def test_the_profile(self, api):
        api.response = FakeResponse(200, {"login": "octocat"})
        result = git_get_user_info()
        assert result == {"success": True, "data": {"login": "octocat"}}

    def test_the_failure(self, api):
        api.response = FakeResponse(404, {"message": "Not Found"})
        result = git_get_user_info()
        assert result["success"] is False
        assert result["error"] == "Not Found"


class TestConfigureCredentials:
    """``git_configure_credentials`` shells out to ``git config``."""

    def test_both_settings_are_written(self, monkeypatch):
        seen = []

        def spy(cmd, **kwargs):
            seen.append(cmd)
            return FakeCompleted()

        monkeypatch.setattr(subprocess, "run", spy)
        assert git_configure_credentials("Octo Cat", "o@example.com") is True
        assert seen == [
            ["git", "config", "user.name", "Octo Cat"],
            ["git", "config", "user.email", "o@example.com"],
        ]

    def test_a_failing_git_is_false(self, monkeypatch):
        def boom(*args, **kwargs):
            raise subprocess.CalledProcessError(1, "git")

        monkeypatch.setattr(subprocess, "run", boom)
        assert git_configure_credentials("Octo Cat", "o@example.com") is False

    def test_an_unexpected_error_is_false(self, monkeypatch):
        def boom(*args, **kwargs):
            raise OSError("no git here")

        monkeypatch.setattr(subprocess, "run", boom)
        assert git_configure_credentials("Octo Cat", "o@example.com") is False

    def test_a_nonzero_return_code_is_false(self, monkeypatch):
        monkeypatch.setattr(
            subprocess, "run",
            lambda *a, **k: FakeCompleted(returncode=1),
        )
        assert git_configure_credentials("Octo Cat", "o@example.com") is False


# ---------------------------------------------------------------------------
# Tier 3: Pull Request operations
# ---------------------------------------------------------------------------


class TestCreatePullRequest:
    """``github_create_pull_request`` opens a PR."""

    def test_the_pull_request_is_created(self, api):
        api.response = FakeResponse(
            201,
            {"number": 42, "html_url": "https://github.com/o/r/pull/42"},
        )
        result = github_create_pull_request(
            owner="o", repo="r", title="t", body="b", head="feature",
        )
        assert result["success"] is True
        assert result["pr_number"] == 42
        assert result["pr_url"] == "https://github.com/o/r/pull/42"

    def test_the_payload(self, api):
        github_create_pull_request(
            owner="o", repo="r", title="t", body="b", head="feature",
        )
        assert api.last["method"] == "POST"
        assert api.last["url"] == f"{GITHUB_API_BASE}/repos/o/r/pulls"
        assert api.last["json"] == {
            "title": "t",
            "body": "b",
            "head": "feature",
            "base": "main",
            "draft": False,
            "maintainer_can_modify": True,
        }

    def test_the_defaults(self, api):
        github_create_pull_request(
            owner="o", repo="r", title="t", body="b", head="feature",
        )
        assert api.last["json"]["base"] == "main"
        assert api.last["json"]["draft"] is False
        assert api.last["json"]["maintainer_can_modify"] is True

    def test_the_failure(self, api):
        api.response = FakeResponse(422, {"message": "Validation Failed"})
        result = github_create_pull_request(
            owner="o", repo="r", title="t", body="b", head="feature",
        )
        assert result["success"] is False
        assert result["error"] == "Validation Failed"


class TestListPullRequests:
    """``github_list_pull_requests`` lists and filters."""

    def test_the_list(self, api):
        api.response = FakeResponse(200, [{"number": 1}, {"number": 2}])
        result = github_list_pull_requests(owner="o", repo="r")
        assert result["success"] is True
        assert result["count"] == 2
        assert result["data"] == [{"number": 1}, {"number": 2}]

    def test_the_default_query(self, api):
        github_list_pull_requests(owner="o", repo="r")
        assert api.last["method"] == "GET"
        assert api.last["url"] == f"{GITHUB_API_BASE}/repos/o/r/pulls"
        assert api.last["params"] == {
            "state": "open",
            "sort": "created",
            "direction": "desc",
            "per_page": 30,
        }

    def test_the_filters_are_optional(self, api):
        github_list_pull_requests(owner="o", repo="r", head="u:feature", base="main")
        assert api.last["params"]["head"] == "u:feature"
        assert api.last["params"]["base"] == "main"

    def test_no_filters_means_no_parameters(self, api):
        github_list_pull_requests(owner="o", repo="r")
        assert "head" not in api.last["params"]
        assert "base" not in api.last["params"]

    def test_per_page_is_capped_at_100(self, api):
        """The GitHub API refuses more than 100."""
        github_list_pull_requests(owner="o", repo="r", per_page=500)
        assert api.last["params"]["per_page"] == 100

    def test_the_failure(self, api):
        api.response = FakeResponse(404, {"message": "Not Found"})
        result = github_list_pull_requests(owner="o", repo="r")
        assert result["success"] is False


class TestGetPullRequest:
    """``github_get_pull_request`` returns one PR."""

    def test_the_pull_request(self, api):
        api.response = FakeResponse(200, {"number": 42, "title": "t"})
        result = github_get_pull_request(owner="o", repo="r", pr_number=42)
        assert result == {"success": True, "data": {"number": 42, "title": "t"}}

    def test_the_url(self, api):
        github_get_pull_request(owner="o", repo="r", pr_number=42)
        assert api.last["url"] == f"{GITHUB_API_BASE}/repos/o/r/pulls/42"

    def test_the_failure(self, api):
        api.response = FakeResponse(404, {"message": "Not Found"})
        result = github_get_pull_request(owner="o", repo="r", pr_number=42)
        assert result["success"] is False


class TestUpdatePullRequest:
    """``github_update_pull_request`` patches only what was given."""

    def test_the_update(self, api):
        api.response = FakeResponse(200, {"number": 42})
        result = github_update_pull_request(
            owner="o", repo="r", pr_number=42, title="new",
        )
        assert result["success"] is True
        assert api.last["method"] == "PATCH"
        assert api.last["url"] == f"{GITHUB_API_BASE}/repos/o/r/pulls/42"
        assert api.last["json"] == {"title": "new"}

    def test_every_field(self, api):
        github_update_pull_request(
            owner="o", repo="r", pr_number=42,
            title="t", body="b", state="closed", base="main",
            maintainer_can_modify=False,
        )
        assert api.last["json"] == {
            "title": "t",
            "body": "b",
            "state": "closed",
            "base": "main",
            "maintainer_can_modify": False,
        }

    def test_nothing_to_update_is_an_error(self, api):
        result = github_update_pull_request(owner="o", repo="r", pr_number=42)
        assert result == {"success": False, "error": "No update fields provided"}
        assert api.calls == [], "no request may be made without a field"

    def test_the_failure(self, api):
        api.response = FakeResponse(404, {"message": "Not Found"})
        result = github_update_pull_request(
            owner="o", repo="r", pr_number=42, title="t",
        )
        assert result["success"] is False


class TestClosePullRequest:
    """``github_close_pull_request`` is an update with ``state='closed'``."""

    def test_the_pull_request_is_closed(self, api):
        api.response = FakeResponse(200, {"number": 42, "state": "closed"})
        result = github_close_pull_request(owner="o", repo="r", pr_number=42)
        assert result["success"] is True
        assert api.last["method"] == "PATCH"
        assert api.last["json"] == {"state": "closed"}

    def test_the_failure(self, api):
        api.response = FakeResponse(404, {"message": "Not Found"})
        result = github_close_pull_request(owner="o", repo="r", pr_number=42)
        assert result["success"] is False


class TestMergePullRequest:
    """``github_merge_pull_request`` completes the PR workflow."""

    def test_the_merge(self, api):
        api.response = FakeResponse(200, {"merged": True, "sha": "abc123"})
        result = github_merge_pull_request(owner="o", repo="r", pr_number=42)
        assert result["success"] is True
        assert result["merged"] is True
        assert result["merge_commit_sha"] == "abc123"

    def test_the_url_and_the_method(self, api):
        github_merge_pull_request(owner="o", repo="r", pr_number=42)
        assert api.last["method"] == "PUT"
        assert api.last["url"] == f"{GITHUB_API_BASE}/repos/o/r/pulls/42/merge"

    def test_the_default_method_is_a_merge_commit(self, api):
        github_merge_pull_request(owner="o", repo="r", pr_number=42)
        assert api.last["json"] == {"merge_method": "merge"}

    def test_the_squash_method(self, api):
        github_merge_pull_request(
            owner="o", repo="r", pr_number=42, merge_method="squash",
        )
        assert api.last["json"]["merge_method"] == "squash"

    def test_the_commit_title_and_message(self, api):
        github_merge_pull_request(
            owner="o", repo="r", pr_number=42,
            commit_title="t", commit_message="m",
        )
        assert api.last["json"]["commit_title"] == "t"
        assert api.last["json"]["commit_message"] == "m"

    def test_the_failure(self, api):
        api.response = FakeResponse(405, {"message": "Pull Request is not mergeable"})
        result = github_merge_pull_request(owner="o", repo="r", pr_number=42)
        assert result["success"] is False
        assert result["error"] == "Pull Request is not mergeable"


class TestCommentOnPullRequest:
    """``github_comment_on_pull_request`` leaves feedback."""

    def test_the_comment(self, api):
        api.response = FakeResponse(
            201,
            {"id": 123, "html_url": "https://github.com/o/r/pull/42#issuecomment-123"},
        )
        result = github_comment_on_pull_request(
            owner="o", repo="r", pr_number=42, comment="LGTM",
        )
        assert result["success"] is True
        assert result["comment_id"] == 123
        assert result["comment_url"].endswith("#issuecomment-123")

    def test_the_url_and_the_payload(self, api):
        github_comment_on_pull_request(
            owner="o", repo="r", pr_number=42, comment="LGTM",
        )
        assert api.last["method"] == "POST"
        assert api.last["url"] == f"{GITHUB_API_BASE}/repos/o/r/issues/42/comments"
        assert api.last["json"] == {"body": "LGTM"}

    def test_the_failure(self, api):
        api.response = FakeResponse(404, {"message": "Not Found"})
        result = github_comment_on_pull_request(
            owner="o", repo="r", pr_number=42, comment="LGTM",
        )
        assert result["success"] is False


class TestReviewFileChanges:
    """``github_review_file_changes`` returns the diff."""

    def test_the_files(self, api):
        api.response = FakeResponse(200, [{"filename": "a.py"}, {"filename": "b.py"}])
        result = github_review_file_changes(owner="o", repo="r", pr_number=42)
        assert result["success"] is True
        assert result["files_changed"] == 2

    def test_the_url(self, api):
        github_review_file_changes(owner="o", repo="r", pr_number=42)
        assert api.last["url"] == f"{GITHUB_API_BASE}/repos/o/r/pulls/42/files"

    def test_the_failure(self, api):
        api.response = FakeResponse(404, {"message": "Not Found"})
        result = github_review_file_changes(owner="o", repo="r", pr_number=42)
        assert result["success"] is False


class TestGetPullRequestComments:
    """``github_get_pull_request_comments`` returns the thread."""

    def test_the_comments(self, api):
        api.response = FakeResponse(200, [{"id": 1}, {"id": 2}, {"id": 3}])
        result = github_get_pull_request_comments(owner="o", repo="r", pr_number=42)
        assert result["success"] is True
        assert result["count"] == 3

    def test_the_url(self, api):
        github_get_pull_request_comments(owner="o", repo="r", pr_number=42)
        assert api.last["url"] == f"{GITHUB_API_BASE}/repos/o/r/issues/42/comments"

    def test_the_failure(self, api):
        api.response = FakeResponse(404, {"message": "Not Found"})
        result = github_get_pull_request_comments(owner="o", repo="r", pr_number=42)
        assert result["success"] is False


class TestGetPullRequestReviews:
    """``github_get_pull_request_reviews`` returns the review state."""

    def test_the_reviews(self, api):
        api.response = FakeResponse(200, [{"id": 1, "state": "APPROVED"}])
        result = github_get_pull_request_reviews(owner="o", repo="r", pr_number=42)
        assert result["success"] is True
        assert result["count"] == 1

    def test_the_url(self, api):
        github_get_pull_request_reviews(owner="o", repo="r", pr_number=42)
        assert api.last["url"] == f"{GITHUB_API_BASE}/repos/o/r/pulls/42/reviews"

    def test_the_failure(self, api):
        api.response = FakeResponse(404, {"message": "Not Found"})
        result = github_get_pull_request_reviews(owner="o", repo="r", pr_number=42)
        assert result["success"] is False


# ---------------------------------------------------------------------------
# The error contract
# ---------------------------------------------------------------------------


class TestErrorContract:
    """A failure is reported, never raised."""

    OPERATIONS = (
        (git_get_user_info, ()),
        (github_get_pull_request, ("o", "r", 1)),
        (github_list_pull_requests, ("o", "r")),
        (github_review_file_changes, ("o", "r", 1)),
        (github_get_pull_request_comments, ("o", "r", 1)),
        (github_get_pull_request_reviews, ("o", "r", 1)),
    )

    @pytest.mark.parametrize("operation,args", OPERATIONS)
    def test_an_api_failure_is_a_dict(self, api, operation, args):
        api.response = FakeResponse(404, {"message": "Not Found"})
        result = operation(*args)
        assert result["success"] is False
        assert result["error"] == "Not Found"

    @pytest.mark.parametrize("operation,args", OPERATIONS)
    def test_a_transport_failure_is_a_dict(self, api, operation, args):
        api.raises = operations.requests.exceptions.ConnectionError("down")
        result = operation(*args)
        assert result["success"] is False
        assert result["error"].startswith("Request failed:")

    @pytest.mark.parametrize("operation,args", OPERATIONS)
    def test_nothing_is_ever_raised(self, api, operation, args):
        api.raises = RuntimeError("boom")
        result = operation(*args)
        assert result["success"] is False
        assert result["error"].startswith("Unexpected error:")


# ---------------------------------------------------------------------------
# The response shapes are JSON-serialisable
# ---------------------------------------------------------------------------


class TestSerialisable:
    """The agent has to be able to hand the result to the model."""

    def test_a_success_is_serialisable(self, api):
        api.response = FakeResponse(200, {"login": "octocat"})
        assert json.loads(json.dumps(git_get_user_info()))["success"] is True

    def test_a_failure_is_serialisable(self, api):
        api.response = FakeResponse(404, {"message": "Not Found"})
        assert json.loads(json.dumps(git_get_user_info()))["success"] is False
