"""
Shared types and constants for project management.

Category: Project Management
"""

from typing import Any, Dict, List, Optional, Tuple

# ============================================================================
# Type Aliases
# ============================================================================

IndicatorTuple = Tuple[str, float]
CandidateTuple = Tuple[str, float]
ProjectDict = Dict[str, Any]
ConfigDict = Dict[str, Any]
ActionsDict = Dict[str, str]
MetadataDict = Dict[str, Any]


# ============================================================================
# Project Type Indicator Database
# ============================================================================
# Each project type maps to a list of (indicator, weight) tuples.
# Primary indicators have higher weights than secondary ones.

PROJECT_INDICATORS: Dict[str, List[IndicatorTuple]] = {
    "Python": [
        ("pyproject.toml", 0.9),
        ("setup.py", 0.8),
        ("requirements.txt", 0.7),
        ("Pipfile", 0.6),
        ("poetry.lock", 0.7),
        ("setup.cfg", 0.6),
        ("tox.ini", 0.5),
        ("pytest.ini", 0.5),
        ("pyrightconfig.json", 0.4),
        (".python-version", 0.5),
        ("__init__.py", 0.3),
    ],
    "Node.js": [
        ("package.json", 0.9),
        ("package-lock.json", 0.8),
        ("yarn.lock", 0.8),
        ("pnpm-lock.yaml", 0.7),
        (".npmrc", 0.5),
        ("tsconfig.json", 0.6),
        ("next.config.js", 0.5),
        ("next.config.mjs", 0.5),
        ("nuxt.config.js", 0.5),
        ("vue.config.js", 0.5),
        ("angular.json", 0.6),
    ],
    "Java": [
        ("pom.xml", 0.9),
        ("build.gradle", 0.9),
        ("build.gradle.kts", 0.9),
        ("settings.gradle", 0.7),
        ("settings.gradle.kts", 0.7),
        ("gradlew", 0.6),
        ("gradlew.bat", 0.5),
        ("mvnw", 0.6),
        ("mvnw.cmd", 0.5),
        ("gradle/wrapper/gradle-wrapper.properties", 0.4),
        (".mvn/wrapper/maven-wrapper.properties", 0.4),
    ],
    "C/C++": [
        ("CMakeLists.txt", 0.9),
        ("Makefile", 0.8),
        ("configure.ac", 0.7),
        ("autogen.sh", 0.5),
        ("meson.build", 0.8),
        ("SConstruct", 0.6),
        (".clang-format", 0.4),
        (".clang-tidy", 0.4),
        ("compile_commands.json", 0.5),
        ("meson_options.txt", 0.4),
    ],
    "Rust": [
        ("Cargo.toml", 0.9),
        ("Cargo.lock", 0.7),
        (".cargo/config.toml", 0.5),
        ("rust-toolchain", 0.5),
        ("rustfmt.toml", 0.4),
        ("clippy.toml", 0.4),
    ],
    "Go": [
        ("go.mod", 0.9),
        ("go.sum", 0.8),
        ("Gopkg.toml", 0.6),
        ("Gopkg.lock", 0.6),
        ("glide.yaml", 0.5),
        (".go-version", 0.5),
        ("golangci-lint.yaml", 0.4),
    ],
    "ESP32/FreeRTOS": [
        ("sdkconfig", 0.9),
        ("partitions.csv", 0.7),
        ("sdkconfig.defaults", 0.6),
        ("CMakeLists.txt", 0.5),
        ("main.c", 0.3),
        ("Kconfig", 0.5),
        ("Kconfig.projbuild", 0.4),
    ],
    "PX4/UAV": [
        ("ROMFS", 0.8),
        ("px4fmu_common", 0.7),
        ("CMakeLists.txt", 0.5),
        ("platforms/", 0.4),
        ("src/modules/", 0.4),
    ],
    "Motorola TRBO": [
        (".rdt", 0.9),
        ("config.json", 0.4),
        (".bin", 0.3),
    ],
    "FPGA": [
        (".vhd", 0.8),
        (".sv", 0.8),
        (".v", 0.8),
        (".xdc", 0.7),
        (".qsf", 0.7),
        ("constraints.xdc", 0.6),
        ("system_top.vhd", 0.5),
        ("system_top.sv", 0.5),
    ],
    "Yocto": [
        ("conf/local.conf", 0.9),
        ("conf/bblayers.conf", 0.9),
        ("meta-", 0.5),
        ("bitbake", 0.6),
        ("oe-init-build-env", 0.6),
        ("layers/meta-", 0.5),
    ],
    "System Software": [
        ("Makefile", 0.6),
        ("Kconfig", 0.8),
        ("arch/", 0.4),
        ("drivers/", 0.4),
        ("include/", 0.3),
        (".gitignore", 0.1),
    ],
    "Documentation": [
        ("mkdocs.yml", 0.8),
        ("docs/", 0.5),
        ("README.md", 0.3),
        ("CONTRIBUTING.md", 0.3),
        (".rst", 0.4),
        ("sphinx/", 0.5),
        ("conf.py", 0.5),
    ],
    "Data Science": [
        (".ipynb", 0.8),
        ("notebooks/", 0.6),
        ("requirements.txt", 0.5),
        ("JupyterNotebook", 0.7),
        ("environment.yml", 0.5),
        ("Pipfile", 0.3),
    ],
    "Configuration": [
        (".json", 0.3),
        (".yaml", 0.3),
        (".ini", 0.3),
        (".conf", 0.3),
        (".cfg", 0.3),
        (".toml", 0.3),
    ],
}

# File extension-based indicators
EXTENSION_INDICATORS: Dict[str, Dict[str, float]] = {
    "FPGA": {".vhd": 0.8, ".sv": 0.8, ".v": 0.8, ".xdc": 0.7, ".qsf": 0.7},
    "Data Science": {".ipynb": 0.8},
    "Python": {".py": 0.3, ".pyi": 0.3},
    "Rust": {".rs": 0.4},
    "Go": {".go": 0.4},
    "Java": {".java": 0.5},
    "C/C++": {".c": 0.3, ".cpp": 0.3, ".h": 0.2, ".hpp": 0.2, ".cc": 0.3},
    "Node.js": {".js": 0.2, ".ts": 0.3, ".tsx": 0.3, ".jsx": 0.2},
}


# ============================================================================
# Workspace Config Schema
# ============================================================================

DEFAULT_SCHEMA_VERSION = "1.0"

DEFAULT_CONFIG: ConfigDict = {
    "version": DEFAULT_SCHEMA_VERSION,
    "workspace_path": "",
    "created_at": "",
    "updated_at": "",
    "projects": [],
}

DEFAULT_PROJECT: ProjectDict = {
    "name": "",
    "path": "",
    "type": "Unknown",
    "git_repo": False,
    "git_branch": "",
    "indicators_found": [],
    "confidence": 0.0,
    "actions": {},
    "metadata": {},
}

REQUIRED_CONFIG_FIELDS = ["version", "workspace_path", "created_at", "updated_at", "projects"]
REQUIRED_PROJECT_FIELDS = [
    "name", "path", "type", "git_repo", "indicators_found",
    "confidence", "actions", "metadata",
]
