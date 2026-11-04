"""
Tests for the project_manager module.

Tests cover:
- ProjectScanner: directory scanning and type detection
- WorkspaceConfig: config persistence and project management
- ProjectManager: orchestration and action execution
- ActionExecutor: command execution with timeout
- ToolRecommender: project-aware tool recommendations

Run with:
    pytest tests/test_project_manager.py -v
"""

import json
import os
import tempfile
import time
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

# Import modules under test
from project_manager.scanner import ProjectScanner
from project_manager.config import WorkspaceConfig, validate_config, migrate_config
from project_manager.manager import ProjectManager
from project_manager.executor import ActionExecutor, ActionResult
from project_manager.recommender import ToolRecommender
from project_manager.types import (
    PROJECT_INDICATORS,
    EXTENSION_INDICATORS,
    DEFAULT_CONFIG,
    DEFAULT_PROJECT,
)


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def temp_workspace():
    """Create a temporary workspace directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture
def python_project(temp_workspace):
    """Create a mock Python project directory."""
    project_dir = Path(temp_workspace) / "my-python-project"
    project_dir.mkdir()

    # Create indicator files
    (project_dir / "pyproject.toml").write_text("[build-system]\n")
    (project_dir / "requirements.txt").write_text("pytest\n")
    (project_dir / "main.py").write_text("print('hello')\n")

    yield str(project_dir)


@pytest.fixture
def nodejs_project(temp_workspace):
    """Create a mock Node.js project directory."""
    project_dir = Path(temp_workspace) / "my-node-project"
    project_dir.mkdir()

    # Create indicator files
    (project_dir / "package.json").write_text('{"name": "test"}\n')
    (project_dir / "index.js").write_text("console.log('hello');\n")

    yield str(project_dir)


@pytest.fixture
def rust_project(temp_workspace):
    """Create a mock Rust project directory."""
    project_dir = Path(temp_workspace) / "my-rust-project"
    project_dir.mkdir()

    # Create indicator files
    (project_dir / "Cargo.toml").write_text('[package]\nname = "test"\n')
    (project_dir / "main.rs").write_text('fn main() {}\n')

    yield str(project_dir)


@pytest.fixture
def manager(temp_workspace):
    """Create a ProjectManager instance."""
    return ProjectManager(workspace_path=temp_workspace, auto_save=True)


# ============================================================================
# ProjectScanner Tests
# ============================================================================

class TestProjectScanner:
    """Tests for the ProjectScanner class."""

    def test_scan_python_project(self, python_project):
        """Test scanning a Python project directory."""
        scanner = ProjectScanner()
        scores = scanner.scan_directory(python_project)

        assert "Python" in scores
        assert scores["Python"] > 0.5

    def test_scan_nodejs_project(self, nodejs_project):
        """Test scanning a Node.js project directory."""
        scanner = ProjectScanner()
        scores = scanner.scan_directory(nodejs_project)

        assert "Node.js" in scores
        assert scores["Node.js"] > 0.5

    def test_scan_rust_project(self, rust_project):
        """Test scanning a Rust project directory."""
        scanner = ProjectScanner()
        scores = scanner.scan_directory(rust_project)

        assert "Rust" in scores
        assert scores["Rust"] > 0.5

    def test_detect_project_type(self, python_project):
        """Test project type detection."""
        scanner = ProjectScanner(confidence_threshold=0.5)
        detected = scanner.detect_project_type(python_project)

        assert detected == "Python"

    def test_get_candidates(self, python_project):
        """Test getting candidate project types."""
        scanner = ProjectScanner()
        candidates = scanner.get_candidates(python_project)

        assert len(candidates) > 0
        # Python should be the top candidate
        assert candidates[0][0] == "Python"

    def test_scan_nonexistent_directory(self):
        """Test scanning a non-existent directory."""
        scanner = ProjectScanner()
        scores = scanner.scan_directory("/nonexistent/path/that/does/not/exist")

        assert scores == {}

    def test_get_supported_types(self):
        """Test getting all supported project types."""
        scanner = ProjectScanner()
        types = scanner.get_supported_types()

        assert "Python" in types
        assert "Node.js" in types
        assert "Rust" in types
        assert "Go" in types

    def test_get_project_indicators(self):
        """Test getting indicators for a project type."""
        scanner = ProjectScanner()
        indicators = scanner.get_project_indicators("Python")

        assert len(indicators) > 0
        # Check that pyproject.toml is an indicator
        indicator_files = [ind for ind, _ in indicators]
        assert "pyproject.toml" in indicator_files

    def test_scan_with_max_depth(self, python_project):
        """Test scanning with limited depth."""
        scanner = ProjectScanner(max_depth=1)
        scores = scanner.scan_directory(python_project)

        # Should still detect Python with shallow scan
        assert "Python" in scores


# ============================================================================
# WorkspaceConfig Tests
# ============================================================================

class TestWorkspaceConfig:
    """Tests for the WorkspaceConfig class."""

    def test_create_config(self, temp_workspace):
        """Test creating a new workspace config."""
        config = WorkspaceConfig(workspace_path=temp_workspace, auto_save=False)

        assert config.config["version"] == "1.0"
        assert config.config["projects"] == []

    def test_add_project(self, temp_workspace):
        """Test adding a project to the workspace."""
        config = WorkspaceConfig(workspace_path=temp_workspace, auto_save=False)

        project = config.add_project(
            name="test-project",
            path="./test-project",
            project_type="Python",
            indicators=["pyproject.toml"],
            confidence=0.95,
        )

        assert project["name"] == "test-project"
        assert project["type"] == "Python"
        assert project["confidence"] == 0.95

    def test_get_project(self, temp_workspace):
        """Test getting a project by name."""
        config = WorkspaceConfig(workspace_path=temp_workspace, auto_save=False)
        config.add_project(
            name="test-project",
            path="./test-project",
            project_type="Python",
            indicators=[],
            confidence=0.9,
        )

        project = config.get_project("test-project")
        assert project is not None
        assert project["name"] == "test-project"

    def test_get_nonexistent_project(self, temp_workspace):
        """Test getting a non-existent project."""
        config = WorkspaceConfig(workspace_path=temp_workspace, auto_save=False)

        project = config.get_project("nonexistent")
        assert project is None

    def test_remove_project(self, temp_workspace):
        """Test removing a project."""
        config = WorkspaceConfig(workspace_path=temp_workspace, auto_save=False)
        config.add_project(
            name="test-project",
            path="./test-project",
            project_type="Python",
            indicators=[],
            confidence=0.9,
        )

        removed = config.remove_project("test-project")
        assert removed is True
        assert config.get_project("test-project") is None

    def test_rename_project(self, temp_workspace):
        """Test renaming a project."""
        config = WorkspaceConfig(workspace_path=temp_workspace, auto_save=False)
        config.add_project(
            name="old-name",
            path="./test-project",
            project_type="Python",
            indicators=[],
            confidence=0.9,
        )

        project = config.rename_project("old-name", "new-name")
        assert project["name"] == "new-name"
        assert config.get_project("old-name") is None
        assert config.get_project("new-name") is not None

    def test_set_actions(self, temp_workspace):
        """Test setting project actions."""
        config = WorkspaceConfig(workspace_path=temp_workspace, auto_save=False)
        config.add_project(
            name="test-project",
            path="./test-project",
            project_type="Python",
            indicators=[],
            confidence=0.9,
        )

        config.set_actions("test-project", {"build": "make", "test": "pytest"})

        project = config.get_project("test-project")
        assert project["actions"]["build"] == "make"
        assert project["actions"]["test"] == "pytest"

    def test_set_single_action(self, temp_workspace):
        """Test setting a single action."""
        config = WorkspaceConfig(workspace_path=temp_workspace, auto_save=False)
        config.add_project(
            name="test-project",
            path="./test-project",
            project_type="Python",
            indicators=[],
            confidence=0.9,
        )

        config.set_action("test-project", "build", "make build")

        project = config.get_project("test-project")
        assert project["actions"]["build"] == "make build"

    def test_duplicate_project_name(self, temp_workspace):
        """Test adding a project with duplicate name."""
        config = WorkspaceConfig(workspace_path=temp_workspace, auto_save=False)
        config.add_project(
            name="test-project",
            path="./test-project",
            project_type="Python",
            indicators=[],
            confidence=0.9,
        )

        with pytest.raises(ValueError, match="already exists"):
            config.add_project(
                name="test-project",
                path="./another-path",
                project_type="Node.js",
                indicators=[],
                confidence=0.8,
            )

    def test_save_and_load(self, temp_workspace):
        """Test saving and loading config from disk."""
        config1 = WorkspaceConfig(workspace_path=temp_workspace, auto_save=True)
        config1.add_project(
            name="test-project",
            path="./test-project",
            project_type="Python",
            indicators=[],
            confidence=0.9,
        )

        # Load config in a new instance
        config2 = WorkspaceConfig(workspace_path=temp_workspace, auto_save=False)
        project = config2.get_project("test-project")

        assert project is not None
        assert project["type"] == "Python"

    def test_clear_projects(self, temp_workspace):
        """Test clearing all projects."""
        config = WorkspaceConfig(workspace_path=temp_workspace, auto_save=False)
        config.add_project(
            name="project1",
            path="./project1",
            project_type="Python",
            indicators=[],
            confidence=0.9,
        )
        config.add_project(
            name="project2",
            path="./project2",
            project_type="Node.js",
            indicators=[],
            confidence=0.8,
        )

        config.clear_projects()
        assert len(config.get_all_projects()) == 0

    def test_get_project_types(self, temp_workspace):
        """Test grouping projects by type."""
        config = WorkspaceConfig(workspace_path=temp_workspace, auto_save=False)
        config.add_project(
            name="py1",
            path="./py1",
            project_type="Python",
            indicators=[],
            confidence=0.9,
        )
        config.add_project(
            name="py2",
            path="./py2",
            project_type="Python",
            indicators=[],
            confidence=0.8,
        )
        config.add_project(
            name="node1",
            path="./node1",
            project_type="Node.js",
            indicators=[],
            confidence=0.85,
        )

        types = config.get_project_types()
        assert "Python" in types
        assert len(types["Python"]) == 2
        assert "Node.js" in types
        assert len(types["Node.js"]) == 1


# ============================================================================
# ProjectManager Tests
# ============================================================================

class TestProjectManager:
    """Tests for the ProjectManager class."""

    def test_scan_and_detect(self, python_project):
        """Test scanning and detecting project type."""
        manager = ProjectManager(workspace_path=Path(python_project).parent)
        detected = manager.detect(python_project)

        assert detected == "Python"

    def test_discover_and_register(self, python_project):
        """Test discovering and registering a project."""
        manager = ProjectManager(workspace_path=Path(python_project).parent)
        project = manager.discover_and_register(python_project)

        assert project is not None
        assert project["type"] == "Python"

    def test_get_workspace_summary(self, temp_workspace):
        """Test getting workspace summary."""
        manager = ProjectManager(workspace_path=temp_workspace)
        summary = manager.get_workspace_summary()

        assert "workspace_path" in summary
        assert "total_projects" in summary
        assert "projects" in summary

    def test_set_and_get_action(self, temp_workspace):
        """Test setting and getting actions."""
        manager = ProjectManager(workspace_path=temp_workspace)
        manager.config.add_project(
            name="test-project",
            path="./test-project",
            project_type="Python",
            indicators=[],
            confidence=0.9,
        )

        manager.set_action("test-project", "build", "make build")
        action = manager.get_action("test-project", "build")

        assert action == "make build"


# ============================================================================
# ActionExecutor Tests
# ============================================================================

class TestActionExecutor:
    """Tests for the ActionExecutor class."""

    def test_execute_successful_command(self):
        """Test executing a successful command."""
        executor = ActionExecutor(default_timeout=10)
        result = executor.execute(
            project_name="test",
            action_name="echo",
            command="echo hello",
        )

        assert result.success is True
        assert result.return_code == 0
        assert "hello" in result.stdout
        assert result.duration_ms > 0

    def test_execute_failing_command(self):
        """Test executing a failing command."""
        executor = ActionExecutor(default_timeout=10)
        result = executor.execute(
            project_name="test",
            action_name="fail",
            command="exit 1",
        )

        assert result.success is False
        assert result.return_code == 1

    def test_execute_with_timeout(self):
        """Test executing a command that times out."""
        executor = ActionExecutor(default_timeout=1)
        result = executor.execute(
            project_name="test",
            action_name="sleep",
            command="sleep 10",
        )

        assert result.success is False
        assert result.timed_out is True

    def test_execute_empty_command(self):
        """Test executing an empty command."""
        executor = ActionExecutor()

        with pytest.raises(ValueError, match="empty"):
            executor.execute(
                project_name="test",
                action_name="empty",
                command="",
            )

    def test_dry_run(self):
        """Test dry run mode."""
        executor = ActionExecutor()
        result = executor.dry_run(
            project_name="test",
            action_name="build",
            command="make build",
        )

        assert result["status"] == "preview"
        assert result["command"] == "make build"

    def test_result_to_dict(self):
        """Test serializing ActionResult to dict."""
        result = ActionResult(
            action_name="test",
            project_name="my-project",
            command="pytest",
            success=True,
            return_code=0,
            stdout="passed",
            stderr="",
            duration_ms=100.5,
        )

        data = result.to_dict()
        assert data["action_name"] == "test"
        assert data["success"] is True
        assert data["duration_ms"] == 100.5


# ============================================================================
# ToolRecommender Tests
# ============================================================================

class TestToolRecommender:
    """Tests for the ToolRecommender class."""

    def test_recommend_for_python(self):
        """Test recommendations for Python projects."""
        recommender = ToolRecommender()
        recs = recommender.recommend_for_type("Python")

        assert "priority_tools" in recs
        assert "recommended_actions" in recs
        assert "execute_shell_command" in recs["priority_tools"]

    def test_recommend_for_unknown_type(self):
        """Test recommendations for unknown project types."""
        recommender = ToolRecommender()
        recs = recommender.recommend_for_type("UnknownType")

        assert "priority_tools" in recs
        assert recs["description"] == "Generic project - no specific recommendations available"

    def test_recommend_for_project(self):
        """Test recommendations for a registered project."""
        recommender = ToolRecommender()
        project = {
            "name": "my-python-project",
            "type": "Python",
            "actions": {"build": "make"},
        }

        recs = recommender.recommend_for_project(project)

        assert recs["project_name"] == "my-python-project"
        assert recs["configured_actions"]["build"] == "make"

    def test_get_supported_types(self):
        """Test getting supported recommendation types."""
        recommender = ToolRecommender()
        types = recommender.get_supported_types()

        assert "Python" in types
        assert "Node.js" in types
        assert "Rust" in types

    def test_has_recommendations(self):
        """Test checking if recommendations exist."""
        recommender = ToolRecommender()

        assert recommender.has_recommendations("Python") is True
        assert recommender.has_recommendations("UnknownType") is False

    def test_build_context_string(self):
        """Test building context string for system prompt."""
        recommender = ToolRecommender()
        project = {
            "name": "my-python-project",
            "type": "Python",
            "actions": {},
        }

        context = recommender.build_context_string(project)

        assert "Python" in context
        assert "Recommended tools" in context


# ============================================================================
# Config Validation Tests
# ============================================================================

class TestConfigValidation:
    """Tests for config validation and migration."""

    def test_validate_valid_config(self):
        """Test validating a valid config."""
        config = {
            "version": "1.0",
            "workspace_path": "/tmp",
            "created_at": "2024-01-01",
            "updated_at": "2024-01-01",
            "projects": [],
        }

        assert validate_config(config) is True

    def test_validate_missing_fields(self):
        """Test validating config with missing fields."""
        config = {"version": "1.0"}

        with pytest.raises(ValueError, match="missing required fields"):
            validate_config(config)

    def test_migrate_config(self):
        """Test migrating an old config."""
        config = {"version": "0.9"}

        migrated = migrate_config(config)

        assert migrated["version"] == "1.0"
        assert "projects" in migrated
        assert "workspace_path" in migrated


class TestFoundIndicators:
    """The registration records the indicators that were FOUND.

    The declared indicator list of a type names every file that could
    have identified it.  A project with a ``requirements.txt`` and
    nothing else does not have a ``Pipfile``, a ``poetry.lock`` or a
    ``setup.cfg`` - and the configuration that shows those files claims
    a project layout that is not there.
    """

    def test_only_the_files_that_exist_are_reported(self, temp_workspace):
        project_dir = Path(temp_workspace) / "a-python-project"
        project_dir.mkdir()
        (project_dir / "requirements.txt").write_text("pytest\n")
        (project_dir / "main.py").write_text("print('hello')\n")

        scanner = ProjectScanner()
        found = scanner.get_found_indicators(str(project_dir), "Python")

        assert found == ["requirements.txt"]

    def test_a_file_that_is_not_there_is_not_reported(self, temp_workspace):
        project_dir = Path(temp_workspace) / "another-python-project"
        project_dir.mkdir()
        (project_dir / "requirements.txt").write_text("pytest\n")

        scanner = ProjectScanner()
        found = scanner.get_found_indicators(str(project_dir), "Python")

        for phantom in ("setup.py", "Pipfile", "poetry.lock", "setup.cfg",
                        "tox.ini", "pyrightconfig.json", ".python-version"):
            assert phantom not in found

    def test_an_indicator_in_a_subdirectory_is_found(self, temp_workspace):
        project_dir = Path(temp_workspace) / "a-nested-python-project"
        (project_dir / "toolkits" / "math-toolkit").mkdir(parents=True)
        (project_dir / "toolkits" / "math-toolkit" / "pyproject.toml").write_text("[x]\n")

        scanner = ProjectScanner()
        found = scanner.get_found_indicators(str(project_dir), "Python")

        assert "pyproject.toml" in found

    def test_the_registration_records_the_found_indicators(self, temp_workspace):
        """A registered project records the files that are really there.

        The fixture carries enough indicator files for the scanner to
        detect the type on its own.  That is a limitation of the
        scanner's confidence normalisation - a project with only a
        ``requirements.txt`` scores below the threshold - and it is a
        known failure of its own, recorded in the CI baseline.  This test
        is about the indicators that are recorded, not about the score.
        """
        project_dir = Path(temp_workspace) / "a-registered-python-project"
        project_dir.mkdir()
        for name in ("pyproject.toml", "setup.py", "requirements.txt",
                     "setup.cfg", "tox.ini", "pytest.ini"):
            (project_dir / name).write_text("[x]\n")
        (project_dir / "main.py").write_text("print('hello')\n")

        manager = ProjectManager(temp_workspace)
        project = manager.discover_and_register(
            str(project_dir), name="registered"
        )

        assert project is not None
        assert project["type"] == "Python"
        assert project["indicators_found"] == [
            "pyproject.toml",
            "setup.py",
            "requirements.txt",
            "setup.cfg",
            "tox.ini",
            "pytest.ini",
        ]

    def test_a_file_that_is_absent_is_not_recorded(self, temp_workspace):
        """The declared indicators that are absent stay out."""
        project_dir = Path(temp_workspace) / "a-partly-identified-project"
        project_dir.mkdir()
        for name in ("pyproject.toml", "setup.py", "requirements.txt",
                     "setup.cfg", "tox.ini", "pytest.ini"):
            (project_dir / name).write_text("[x]\n")
        (project_dir / "main.py").write_text("print('hello')\n")

        manager = ProjectManager(temp_workspace)
        project = manager.discover_and_register(
            str(project_dir), name="partly-identified"
        )

        assert project is not None
        for phantom in ("Pipfile", "poetry.lock", "pyrightconfig.json",
                        ".python-version"):
            assert phantom not in project["indicators_found"]

    def test_the_declared_list_is_still_available(self):
        """The declared list is what the scanner matches against."""
        scanner = ProjectScanner()
        declared = scanner.get_project_indicators("Python")

        assert ("requirements.txt", 0.7) in declared
        assert ("Pipfile", 0.6) in declared


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
