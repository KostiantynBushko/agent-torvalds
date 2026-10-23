#!/usr/bin/env bash
# ============================================================================
# deploy-torvalds.sh
#
# Automated deployment script for Agent Torvalds.
#
# Installs and configures all system dependencies, PostgreSQL (optional),
# Python virtual environment, Ollama (optional), and bootstraps configuration
# files on a fresh Linux system.
#
# Usage:
#   ./deploy-torvalds.sh [OPTIONS]
#
# Options:
#   -h, --help              Show this help message
#   -v, --version           Show version
#   -n, --non-interactive   Run without prompts (use defaults)
#   -s, --skip-ollama       Skip Ollama installation
#   -p, --skip-pip          Skip Python pip installation
#   -w, --with-postgres     Install and configure PostgreSQL
#   -m, --model MODEL       Ollama chat model (default: richardyoung/qwen3.6-27b-abliterated:Q4_K_M)
#   -e, --embedding-model MODEL  Ollama embedding model (default: nomic-embed-text)
#   -l, --log-file PATH     Log file path (default: /var/log/torvalds-deploy.log)
#   -d, --deploy-dir PATH   Deployment directory (default: current directory)
#
# PostgreSQL Options (only with --with-postgres):
#   -u, --pg-user USER      PostgreSQL app user (default: llama)
#   -P, --pg-password PASS  PostgreSQL app password (default: llama)
#   -D, --pg-database DB    PostgreSQL database name (default: llama_index_db)
#   -H, --pg-host HOST      PostgreSQL host (default: 127.0.0.1)
#   -O, --pg-port PORT      PostgreSQL port (default: 5432)
#
# Examples:
#   ./deploy-torvalds.sh --with-postgres --non-interactive
#   ./deploy-torvalds.sh --skip-ollama --model llama3.2
# ============================================================================

set -euo pipefail

# ---------------------------------------------------------------------------
# Version
# ---------------------------------------------------------------------------
readonly SCRIPT_VERSION="1.0.0"
readonly SCRIPT_NAME="$(basename "$0")"

# ---------------------------------------------------------------------------
# Default Configuration
# ---------------------------------------------------------------------------
INTERACTIVE=true
SKIP_OLLAMA=false
SKIP_PIP=false
WITH_POSTGRES=false
DEPLOY_DIR="$(pwd)"
LOG_FILE="/var/log/torvalds-deploy.log"

# Ollama defaults
CHAT_MODEL="richardyoung/qwen3.6-27b-abliterated:Q4_K_M"
EMBEDDING_MODEL="nomic-embed-text"

# PostgreSQL defaults
PG_USER="llama"
PG_PASSWORD="llama"
PG_DATABASE="llama_index_db"
PG_HOST="127.0.0.1"
PG_PORT="5432"

# Internal state tracking
DEPLOY_TIMESTAMP="$(date +%s)"
DEPLOY_DATE="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
ERRORS=0
WARNINGS=0

# Detected system info (populated during detection)
OS_FAMILY=""
PACKAGE_MANAGER=""
PYTHON3_PATH=""

# ---------------------------------------------------------------------------
# Logging Framework
# ---------------------------------------------------------------------------

# log_info <message>
# Log an informational message.
log_info() {
    local msg="[$(date '+%Y-%m-%d %H:%M:%S')] [INFO] $*"
    echo "$msg" >&2
    echo "$msg" >> "$LOG_FILE" 2>/dev/null || true
}

# log_warn <message>
# Log a warning message and increment warning counter.
log_warn() {
    local msg="[$(date '+%Y-%m-%d %H:%M:%S')] [WARN] $*"
    echo "$msg" >&2
    echo "$msg" >> "$LOG_FILE" 2>/dev/null || true
    ((WARNINGS++)) || true
}

# log_error <message>
# Log an error message and increment error counter.
log_error() {
    local msg="[$(date '+%Y-%m-%d %H:%M:%S')] [ERROR] $*"
    echo "$msg" >&2
    echo "$msg" >> "$LOG_FILE" 2>/dev/null || true
    ((ERRORS++)) || true
}

# log_section <title>
# Print a section header with decorative borders.
log_section() {
    local title="$1"
    local border="============================================================================"
    echo "" >&2
    echo "$border" >&2
    echo "  $title" >&2
    echo "$border" >&2
    echo "" >> "$LOG_FILE" 2>/dev/null || true
    echo "$border" >> "$LOG_FILE" 2>/dev/null || true
    echo "  $title" >> "$LOG_FILE" 2>/dev/null || true
    echo "$border" >> "$LOG_FILE" 2>/dev/null || true
}

# log_step <step_number> <message>
# Log a numbered step.
log_step() {
    local step="$1"
    local msg="$2"
    log_info "Step ${step}: ${msg}"
}

# ---------------------------------------------------------------------------
# Trap Handlers
# ---------------------------------------------------------------------------

# trap_err
# Called on error to log the failing command and line number.
trap_err() {
    local line_number="$1"
    local exit_code="$2"
    log_error "Command failed at line ${line_number} with exit code ${exit_code}"
}

# trap_exit
# Called on script exit to print summary.
trap_exit() {
    if [[ "$ERRORS" -gt 0 ]]; then
        log_error "Deployment completed with ${ERRORS} error(s) and ${WARNINGS} warning(s)"
    elif [[ "$WARNINGS" -gt 0 ]]; then
        log_warn "Deployment completed with ${WARNINGS} warning(s)"
    else
        log_info "Deployment completed successfully"
    fi
}

trap 'trap_err ${LINENO} $?' ERR
trap 'trap_exit' EXIT

# ---------------------------------------------------------------------------
# Banner & Help
# ---------------------------------------------------------------------------

# print_banner
# Print the deployment banner.
print_banner() {
    cat >&2 <<'EOF'

  ╔══════════════════════════════════════════════════════════════════╗
  ║                                                                ║
  ║   Agent Torvalds Deployment Script                             ║
  ║   Automated setup for Linux systems                            ║
  ║                                                                ║
  ╚══════════════════════════════════════════════════════════════════╝

EOF
}

# print_help
# Print usage information and exit.
print_help() {
    cat >&2 <<EOF
${SCRIPT_NAME} v${SCRIPT_VERSION} — Agent Torvalds Deployment Script

USAGE:
    ${SCRIPT_NAME} [OPTIONS]

OPTIONS:
    -h, --help              Show this help message and exit
    -v, --version           Show version and exit
    -n, --non-interactive   Run without prompts (use all defaults)
    -s, --skip-ollama       Skip Ollama installation and model download
    -p, --skip-pip          Skip Python pip dependency installation
    -w, --with-postgres     Install and configure PostgreSQL database

    -m, --model MODEL       Ollama chat model
                            (default: ${CHAT_MODEL})
    -e, --embedding-model MODEL  Ollama embedding model
                            (default: ${EMBEDDING_MODEL})
    -l, --log-file PATH     Log file path
                            (default: ${LOG_FILE})
    -d, --deploy-dir PATH   Deployment directory
                            (default: current directory)

POSTGRESQL OPTIONS (only with --with-postgres):
    -u, --pg-user USER      PostgreSQL application user
                            (default: ${PG_USER})
    -P, --pg-password PASS  PostgreSQL application password
                            (default: ${PG_PASSWORD})
    -D, --pg-database DB    PostgreSQL database name
                            (default: ${PG_DATABASE})
    -H, --pg-host HOST      PostgreSQL host
                            (default: ${PG_HOST})
    -O, --pg-port PORT      PostgreSQL port
                            (default: ${PG_PORT})

EXAMPLES:
    # Full deployment with PostgreSQL, non-interactive
    ${SCRIPT_NAME} --with-postgres --non-interactive

    # Skip Ollama, use defaults for everything else
    ${SCRIPT_NAME} --skip-ollama

    # Custom model selection
    ${SCRIPT_NAME} --model llama3.2 --embedding-model all-minilm

ENVIRONMENT:
    TORVALDS_DEPLOY_DIR     Override deployment directory
    TORVALDS_NON_INTERACTIVE Set to '1' for non-interactive mode

EOF
    exit 0
}

# print_version
# Print version and exit.
print_version() {
    echo "${SCRIPT_NAME} v${SCRIPT_VERSION}" >&2
    exit 0
}

# ---------------------------------------------------------------------------
# CLI Argument Parsing
# ---------------------------------------------------------------------------

# parse_args
# Parse command-line arguments using getopt.
parse_args() {
    local optstring="hvnspsw"
    local longopts="help,version,non-interactive,skip-ollama,skip-pip,with-postgres,model:,embedding-model:,log-file:,deploy-dir:,pg-user:,pg-password:,pg-database:,pg-host:,pg-port:"

    while [[ $# -gt 0 ]]; do
        case "$1" in
            -h|--help)       print_help ;;
            -v|--version)    print_version ;;
            -n|--non-interactive) INTERACTIVE=false; shift ;;
            -s|--skip-ollama)   SKIP_OLLAMA=true; shift ;;
            -p|--skip-pip)      SKIP_PIP=true; shift ;;
            -w|--with-postgres) WITH_POSTGRES=true; shift ;;
            -m|--model)         CHAT_MODEL="$2"; shift 2 ;;
            -e|--embedding-model) EMBEDDING_MODEL="$2"; shift 2 ;;
            -l|--log-file)      LOG_FILE="$2"; shift 2 ;;
            -d|--deploy-dir)    DEPLOY_DIR="$2"; shift 2 ;;
            -u|--pg-user)       PG_USER="$2"; shift 2 ;;
            -P|--pg-password)   PG_PASSWORD="$2"; shift 2 ;;
            -D|--pg-database)   PG_DATABASE="$2"; shift 2 ;;
            -H|--pg-host)       PG_HOST="$2"; shift 2 ;;
            -O|--pg-port)       PG_PORT="$2"; shift 2 ;;
            *)
                log_error "Unknown option: $1"
                print_help
                ;;
        esac
    done

    # Allow environment variable overrides
    if [[ -n "${TORVALDS_DEPLOY_DIR:-}" ]]; then
        DEPLOY_DIR="${TORVALDS_DEPLOY_DIR}"
    fi
    if [[ "${TORVALDS_NON_INTERACTIVE:-}" == "1" ]]; then
        INTERACTIVE=false
    fi
}

# ---------------------------------------------------------------------------
# Utility Functions
# ---------------------------------------------------------------------------

# prompt_user <question> <default_value>
# Prompt the user for input with a default value. Returns empty string in
# non-interactive mode.
prompt_user() {
    local question="$1"
    local default="${2:-}"

    if [[ "$INTERACTIVE" == "false" ]]; then
        echo "$default"
        return
    fi

    local prompt="${question}"
    if [[ -n "$default" ]]; then
        prompt="${prompt} (default: ${default})"
    fi
    prompt="${prompt}? "

    local answer
    read -r -p "$prompt" answer
    echo "${answer:-$default}"
}

# check_command <command_name>
# Check if a command exists in PATH. Returns 0 if found, 1 otherwise.
check_command() {
    command -v "$1" &>/dev/null
}

# run_sudo <command...>
# Run a command with sudo, caching the password first.
run_sudo() {
    sudo -v 2>/dev/null || true
    sudo "$@"
}

# wait_for_service <name> <url> <timeout_seconds>
# Wait for a service to become available by polling a URL.
wait_for_service() {
    local name="$1"
    local url="$2"
    local timeout="${3:-30}"
    local elapsed=0

    log_info "Waiting for ${name} to be ready..."

    while [[ $elapsed -lt $timeout ]]; do
        if curl -sf "$url" &>/dev/null; then
            log_info "${name} is ready after ${elapsed}s"
            return 0
        fi
        sleep 2
        ((elapsed += 2))
    done

    log_warn "${name} did not become ready within ${timeout}s"
    return 1
}

# ---------------------------------------------------------------------------
# Phase 1: Pre-flight Checks
# ---------------------------------------------------------------------------

# check_root_or_sudo
# Verify we have sudo privileges.
check_root_or_sudo() {
    log_step 1 "Checking sudo privileges"

    if [[ "$(id -u)" -eq 0 ]]; then
        log_info "Running as root"
        return 0
    fi

    if ! sudo -n true 2>/dev/null; then
        if [[ "$INTERACTIVE" == "false" ]]; then
            log_error "Not running as root and non-interactive mode requires cached sudo"
            return 1
        fi
        sudo -v
    fi
    log_info "Sudo privileges confirmed"
}

# check_deploy_directory
# Verify the deployment directory exists and is writable.
check_deploy_directory() {
    log_step 2 "Checking deployment directory: ${DEPLOY_DIR}"

    if [[ ! -d "$DEPLOY_DIR" ]]; then
        log_error "Deployment directory does not exist: ${DEPLOY_DIR}"
        return 1
    fi

    if [[ ! -w "$DEPLOY_DIR" ]]; then
        log_error "Deployment directory is not writable: ${DEPLOY_DIR}"
        return 1
    fi

    log_info "Deployment directory OK"
}

# check_requirements_files
# Verify that required project files exist.
check_requirements_files() {
    log_step 3 "Checking required project files"

    local required_files=("requirements.txt" "setup_postgres_db.sql")
    local missing=()

    for f in "${required_files[@]}"; do
        if [[ ! -f "${DEPLOY_DIR}/${f}" ]]; then
            missing+=("$f")
            log_warn "Missing required file: ${f}"
        fi
    done

    if [[ ${#missing[@]} -gt 0 ]]; then
        log_error "Missing required files: ${missing[*]}"
        log_error "Ensure you are running from the Agent Torvalds project root"
        return 1
    fi

    log_info "All required files present"
}

# ---------------------------------------------------------------------------
# Phase 2: System Detection & Prerequisites
# ---------------------------------------------------------------------------

# detect_os
# Detect the OS family and package manager.
detect_os() {
    log_section "Phase 2: System Detection"
    log_step 1 "Detecting operating system"

    if [[ -f /etc/os-release ]]; then
        # shellcheck disable=SC1091
        . /etc/os-release
        local id="${ID,,}"  # lowercase
        local version="${VERSION_ID:-unknown}"

        case "$id" in
            ubuntu|debian|linuxmint|pop)
                OS_FAMILY="debian"
                PACKAGE_MANAGER="apt"
                ;;
            fedora|rhel|centos|rocky|almalinux)
                OS_FAMILY="rhel"
                PACKAGE_MANAGER="dnf"
                ;;
            arch|manjaro)
                OS_FAMILY="arch"
                PACKAGE_MANAGER="pacman"
                ;;
            suse|sles|opensuse*)
                OS_FAMILY="suse"
                PACKAGE_MANAGER="zypper"
                ;;
            *)
                OS_FAMILY="unknown"
                PACKAGE_MANAGER="unknown"
                log_warn "Unknown distribution: ${ID} ${VERSION}"
                ;;
        esac

        log_info "Detected: ${PRETTY_NAME:-$id $version}"
        log_info "OS Family: ${OS_FAMILY}, Package Manager: ${PACKAGE_MANAGER}"
    else
        OS_FAMILY="unknown"
        PACKAGE_MANAGER="unknown"
        log_warn "Could not detect OS (no /etc/os-release)"
    fi
}

# check_python3
# Verify Python 3.8+ is available.
check_python3() {
    log_step 2 "Checking Python 3"

    if check_command python3; then
        PYTHON3_PATH="$(command -v python3)"
        local version
        version="$(${PYTHON3_PATH} --version 2>&1)"
        log_info "Found: ${version} at ${PYTHON3_PATH}"

        # Check version >= 3.8
        local major minor
        major="$(${PYTHON3_PATH} -c 'import sys; print(sys.version_info.major)')"
        minor="$(${PYTHON3_PATH} -c 'import sys; print(sys.version_info.minor)')"

        if [[ "$major" -lt 3 ]] || { [[ "$major" -eq 3 ]] && [[ "$minor" -lt 8 ]]; }; then
            log_error "Python 3.8+ required, found ${major}.${minor}"
            return 1
        fi
    else
        log_error "Python 3 not found in PATH"
        return 1
    fi
}

# check_git
# Verify Git is available.
check_git() {
    log_step 3 "Checking Git"

    if check_command git; then
        local version
        version="$(git --version 2>&1)"
        log_info "Found: ${version}"
    else
        log_warn "Git not found (will be installed if possible)"
    fi
}

# check_network
# Verify network connectivity.
check_network() {
    log_step 4 "Checking network connectivity"

    if curl -sf --max-time 5 https://github.com &>/dev/null; then
        log_info "Network connectivity OK (github.com reachable)"
    elif ping -c 1 -W 5 github.com &>/dev/null; then
        log_info "Network connectivity OK (github.com pingable)"
    else
        log_warn "Cannot reach github.com — some installations may fail"
    fi
}

# check_disk_space
# Check available disk space. Ollama models can be large.
check_disk_space() {
    log_step 5 "Checking disk space"

    local available_gb
    available_gb="$(df -BG "${DEPLOY_DIR}" | awk 'NR==2 {gsub(/G/,"",$2); print $2}')"

    if [[ "$SKIP_OLLAMA" == "false" ]]; then
        # Ollama models need significant space
        if [[ "$available_gb" -lt 20 ]]; then
            log_warn "Less than 20GB available (${available_gb}GB) — Ollama models may not fit"
        else
            log_info "Disk space OK: ${available_gb}GB available"
        fi
    else
        if [[ "$available_gb" -lt 5 ]]; then
            log_warn "Less than 5GB available (${available_gb}GB)"
        else
            log_info "Disk space OK: ${available_gb}GB available"
        fi
    fi
}

# ---------------------------------------------------------------------------
# Phase 3: System Package Installation
# ---------------------------------------------------------------------------

# install_system_packages
# Install required system packages using the detected package manager.
install_system_packages() {
    log_section "Phase 3: System Package Installation"

    local packages=()

    case "$PACKAGE_MANAGER" in
        apt)
            log_info "Using apt package manager"
            packages=(
                "python3-venv"
                "python3-pip"
                "git"
                "build-essential"
                "cmake"
                "libpq-dev"
                "curl"
                "wget"
                "unzip"
                "whiptail"
            )
            ;;
        dnf)
            log_info "Using dnf package manager"
            packages=(
                "python3"
                "python3-pip"
                "python3-devel"
                "git"
                "gcc"
                "gcc-c++"
                "make"
                "cmake"
                "libpq-devel"
                "curl"
                "wget"
                "unzip"
                "newt"
            )
            ;;
        pacman)
            log_info "Using pacman package manager"
            packages=(
                "python"
                "python-pip"
                "git"
                "base-devel"
                "cmake"
                "postgresql-libs"
                "curl"
                "wget"
                "unzip"
                "util-linux"
            )
            ;;
        *)
            log_warn "Unsupported package manager: ${PACKAGE_MANAGER}"
            log_warn "Please install dependencies manually"
            return 0
            ;;
    esac

    # Check which packages are already installed
    local to_install=()
    for pkg in "${packages[@]}"; do
        case "$PACKAGE_MANAGER" in
            apt)
                if ! dpkg -l "$pkg" &>/dev/null; then
                    to_install+=("$pkg")
                fi
                ;;
            dnf)
                if ! rpm -q "$pkg" &>/dev/null; then
                    to_install+=("$pkg")
                fi
                ;;
            pacman)
                if ! pacman -Q "$pkg" &>/dev/null; then
                    to_install+=("$pkg")
                fi
                ;;
        esac
    done

    if [[ ${#to_install[@]} -eq 0 ]]; then
        log_info "All required packages already installed"
        return 0
    fi

    log_info "Installing ${#to_install[@]} packages: ${to_install[*]}"

    case "$PACKAGE_MANAGER" in
        apt)
            run_sudo apt-get update -qq
            run_sudo DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends "${to_install[@]}"
            ;;
        dnf)
            run_sudo dnf install -y "${to_install[@]}"
            ;;
        pacman)
            run_sudo pacman -Syu --noconfirm --needed "${to_install[@]}"
            ;;
    esac

    log_info "System packages installed successfully"
}

# ---------------------------------------------------------------------------
# Phase 4: PostgreSQL Setup
# ---------------------------------------------------------------------------

# install_postgres
# Install and configure PostgreSQL if --with-postgres is specified.
install_postgres() {
    log_section "Phase 4: PostgreSQL Setup"

    if [[ "$WITH_POSTGRES" == "false" ]]; then
        log_info "PostgreSQL setup skipped (--with-postgres not specified)"
        return 0
    fi

    log_info "Installing PostgreSQL..."

    # Install PostgreSQL packages
    case "$PACKAGE_MANAGER" in
        apt)
            run_sudo DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends postgresql postgresql-contrib
            ;;
        dnf)
            run_sudo dnf install -y postgresql-server postgresql-contrib
            ;;
        pacman)
            run_sudo pacman -Syu --noconfirm --needed postgresql
            ;;
        *)
            log_warn "Cannot auto-install PostgreSQL for ${PACKAGE_MANAGER}"
            return 0
            ;;
    esac

    # Start and enable PostgreSQL service
    log_info "Starting PostgreSQL service..."
    if run_sudo systemctl enable --now postgresql 2>/dev/null; then
        log_info "PostgreSQL service enabled and started"
    elif run_sudo systemctl enable --now postgresql.service 2>/dev/null; then
        log_info "PostgreSQL service enabled and started"
    else
        log_warn "Could not start PostgreSQL via systemctl — may need manual start"
    fi

    # Wait for PostgreSQL to be ready
    local retries=10
    while [[ $retries -gt 0 ]]; do
        if run_sudo -u postgres pg_isready -h "$PG_HOST" -p "$PG_PORT" &>/dev/null; then
            break
        fi
        sleep 2
        ((retries--))
    done

    if [[ $retries -eq 0 ]]; then
        log_error "PostgreSQL did not become ready"
        return 1
    fi

    # Prompt for password in interactive mode
    if [[ "$INTERACTIVE" == "true" ]]; then
        local pg_pass
        pg_pass="$(prompt_user "PostgreSQL password for user '${PG_USER}'" "$PG_PASSWORD")"
        if [[ -n "$pg_pass" ]]; then
            PG_PASSWORD="$pg_pass"
        fi
    fi

    # Execute setup SQL
    log_info "Running PostgreSQL setup script..."
    local sql_file="${DEPLOY_DIR}/setup_postgres_db.sql"

    if [[ ! -f "$sql_file" ]]; then
        log_error "PostgreSQL setup script not found: ${sql_file}"
        return 1
    fi

    # Run the SQL script with custom parameters
    if run_sudo -u postgres psql \
        -h "$PG_HOST" \
        -p "$PG_PORT" \
        -d postgres \
        -v ON_ERROR_STOP=1 \
        -v "app_user=${PG_USER}" \
        -v "app_password=${PG_PASSWORD}" \
        -v "app_database=${PG_DATABASE}" \
        -f "$sql_file" 2>>"$LOG_FILE"; then
        log_info "PostgreSQL setup completed successfully"
    else
        log_warn "PostgreSQL setup script had errors — check log for details"
    fi

    # Verify connectivity
    log_info "Verifying PostgreSQL connectivity..."
    if run_sudo -u postgres psql \
        -h "$PG_HOST" \
        -p "$PG_PORT" \
        -d "$PG_DATABASE" \
        -U "$PG_USER" \
        -c "SELECT 1" &>/dev/null; then
        log_info "PostgreSQL connectivity verified"
    else
        log_warn "PostgreSQL connectivity test failed — may need password authentication setup"
    fi
}

# ---------------------------------------------------------------------------
# Phase 5: Python Virtual Environment
# ---------------------------------------------------------------------------

# setup_python_env
# Create and populate the Python virtual environment.
setup_python_env() {
    log_section "Phase 5: Python Virtual Environment"

    if [[ "$SKIP_PIP" == "true" ]]; then
        log_info "Python pip installation skipped (--skip-pip specified)"
        return 0
    fi

    local venv_dir="${DEPLOY_DIR}/.venv"

    # Create venv if it doesn't exist
    if [[ ! -d "$venv_dir" ]]; then
        log_info "Creating Python virtual environment at ${venv_dir}"
        ${PYTHON3_PATH} -m venv "$venv_dir"
    else
        log_info "Virtual environment already exists at ${venv_dir}"
    fi

    # Activate and upgrade pip
    log_info "Upgrading pip, setuptools, wheel..."
    source "${venv_dir}/bin/activate"

    pip install --upgrade pip setuptools wheel 2>>"$LOG_FILE" || {
        log_warn "pip upgrade had warnings — continuing"
    }

    # Install requirements
    local req_file="${DEPLOY_DIR}/requirements.txt"
    if [[ -f "$req_file" ]]; then
        log_info "Installing Python dependencies from requirements.txt..."
        pip install -r "$req_file" 2>>"$LOG_FILE" || {
            log_warn "Some pip packages may have failed to install — check log"
        }
    else
        log_warn "requirements.txt not found at ${req_file}"
    fi

    # Deactivate
    deactivate 2>/dev/null || true
    log_info "Python virtual environment setup complete"
}

# ---------------------------------------------------------------------------
# Phase 6: Ollama Setup
# ---------------------------------------------------------------------------

# setup_ollama
# Install Ollama and pull required models.
setup_ollama() {
    log_section "Phase 6: Ollama Setup"

    if [[ "$SKIP_OLLAMA" == "true" ]]; then
        log_info "Ollama setup skipped (--skip-ollama specified)"
        return 0
    fi

    # Check if Ollama is already installed
    if check_command ollama; then
        log_info "Ollama already installed: $(ollama --version 2>&1 || echo 'version unknown')"
    else
        log_info "Installing Ollama..."
        if curl -fsSL https://ollama.com/install.sh | run_sudo sh 2>>"$LOG_FILE"; then
            log_info "Ollama installed successfully"
        else
            log_error "Ollama installation failed"
            return 1
        fi
    fi

    # Start and enable Ollama service
    log_info "Starting Ollama service..."
    if run_sudo systemctl enable --now ollama 2>/dev/null; then
        log_info "Ollama service enabled and started"
    else
        log_warn "Could not enable Ollama via systemctl — trying to start manually"
        # Ollama might already be running
        if pgrep -x ollama &>/dev/null; then
            log_info "Ollama process already running"
        else
            log_warn "Ollama service not started — may need manual intervention"
        fi
    fi

    # Wait for Ollama server
    if ! wait_for_service "Ollama" "http://localhost:11434/api/version" 60; then
        log_warn "Ollama server not responding — models may not be pulled"
        return 0
    fi

    # Pull chat model
    log_info "Pulling chat model: ${CHAT_MODEL}"
    if ollama pull "$CHAT_MODEL" 2>>"$LOG_FILE"; then
        log_info "Chat model pulled successfully"
    else
        log_warn "Failed to pull chat model: ${CHAT_MODEL}"
    fi

    # Pull embedding model
    log_info "Pulling embedding model: ${EMBEDDING_MODEL}"
    if ollama pull "$EMBEDDING_MODEL" 2>>"$LOG_FILE"; then
        log_info "Embedding model pulled successfully"
    else
        log_warn "Failed to pull embedding model: ${EMBEDDING_MODEL}"
    fi

    # Verify models
    log_info "Verifying installed models..."
    ollama list 2>>"$LOG_FILE" || true
    log_info "Ollama setup complete"
}

# ---------------------------------------------------------------------------
# Phase 7: Configuration Bootstrap
# ---------------------------------------------------------------------------

# bootstrap_config
# Generate initial configuration files.
bootstrap_config() {
    log_section "Phase 7: Configuration Bootstrap"

    # Generate .env file
    local env_file="${DEPLOY_DIR}/.env"
    if [[ ! -f "$env_file" ]]; then
        log_info "Generating .env file..."
        cat > "$env_file" <<EOF
# Agent Torvalds Environment Configuration
# Generated by deploy-torvalds.sh on ${DEPLOY_DATE}

# ---------------------------------------------------------------------------
# Ollama Configuration
# ---------------------------------------------------------------------------
TORVALDS_OLLAMA_BASE_URL=http://localhost:11434
TORVALDS_CHAT_MODEL=${CHAT_MODEL}
TORVALDS_EMBEDDING_MODEL=${EMBEDDING_MODEL}

# ---------------------------------------------------------------------------
# PostgreSQL Configuration
# ---------------------------------------------------------------------------
TORVALDS_PG_HOST=${PG_HOST}
TORVALDS_PG_PORT=${PG_PORT}
TORVALDS_PG_USER=${PG_USER}
TORVALDS_PG_PASSWORD=${PG_PASSWORD}
TORVALDS_PG_DATABASE=${PG_DATABASE}

# ---------------------------------------------------------------------------
# Application Configuration
# ---------------------------------------------------------------------------
TORVALDS_DEPLOY_DIR=${DEPLOY_DIR}
EOF
        chmod 0600 "$env_file"
        log_info ".env file created with restrictive permissions (0600)"
    else
        log_info ".env file already exists — not overwriting"
    fi

    # Copy example config files
    local examples=("db_toolkit_config.yaml" "mikrotik_targets.yaml")
    for example in "${examples[@]}"; do
        local src="${DEPLOY_DIR}/${example}.example"
        local dst="${DEPLOY_DIR}/${example}"
        if [[ -f "$src" ]] && [[ ! -f "$dst" ]]; then
            cp "$src" "$dst"
            log_info "Copied ${example}.example -> ${example}"
        fi
    done

    log_info "Configuration bootstrap complete"
}

# ---------------------------------------------------------------------------
# Phase 8: Verification & Summary
# ---------------------------------------------------------------------------

# verify_deployment
# Run verification checks and print deployment summary.
verify_deployment() {
    log_section "Phase 8: Verification & Summary"

    local checks_passed=0
    local checks_failed=0

    # Check 1: Python venv
    log_step 1 "Verifying Python virtual environment"
    if [[ -x "${DEPLOY_DIR}/.venv/bin/python" ]]; then
        log_info "✓ Python virtual environment OK"
        ((checks_passed++))
    else
        log_error "✗ Python virtual environment missing or broken"
        ((checks_failed++))
    fi

    # Check 2: Python imports
    log_step 2 "Verifying Python module imports"
    if [[ -x "${DEPLOY_DIR}/.venv/bin/python" ]]; then
        if "${DEPLOY_DIR}/.venv/bin/python" -c "import llama_index" 2>/dev/null; then
            log_info "✓ llama_index import OK"
            ((checks_passed++))
        else
            log_warn "✗ llama_index import failed"
            ((checks_failed++))
        fi
    fi

    # Check 3: Ollama
    if [[ "$SKIP_OLLAMA" == "false" ]]; then
        log_step 3 "Verifying Ollama connectivity"
        if curl -sf http://localhost:11434/api/version &>/dev/null; then
            log_info "✓ Ollama server responding"
            ((checks_passed++))
        else
            log_warn "✗ Ollama server not responding"
            ((checks_failed++))
        fi
    else
        log_info "Ollama verification skipped (--skip-ollama)"
    fi

    # Check 4: PostgreSQL
    if [[ "$WITH_POSTGRES" == "true" ]]; then
        log_step 4 "Verifying PostgreSQL connectivity"
        if run_sudo -u postgres psql \
            -h "$PG_HOST" -p "$PG_PORT" \
            -d "$PG_DATABASE" -U "$PG_USER" \
            -c "SELECT 1" &>/dev/null; then
            log_info "✓ PostgreSQL connectivity OK"
            ((checks_passed++))
        else
            log_warn "✗ PostgreSQL connectivity test failed"
            ((checks_failed++))
        fi
    else
        log_info "PostgreSQL verification skipped (--with-postgres not specified)"
    fi

    # -----------------------------------------------------------------------
    # Deployment Summary
    # -----------------------------------------------------------------------
    log_section "Deployment Summary"

    cat >&2 <<EOF

  ┌──────────────────────────────────────────────────────────────┐
  │  DEPLOYMENT SUMMARY                                         │
  ├──────────────────────────────────────────────────────────────┤
  │  Date:              ${DEPLOY_DATE}                           │
  │  Directory:         ${DEPLOY_DIR}                            │
  │  OS:                ${OS_FAMILY:-unknown} (${PACKAGE_MANAGER:-unknown})│
  │                                                              │
  │  PostgreSQL:        $([ "$WITH_POSTGRES" = "true" ] && echo "Installed" || echo "Skipped")│
  │  Ollama:            $([ "$SKIP_OLLAMA" = "false" ] && echo "Installed" || echo "Skipped")│
  │  Python venv:       $([ "$SKIP_PIP" = "false" ] && echo "Installed" || echo "Skipped") │
  │                                                              │
  │  Checks Passed:     ${checks_passed}                          │
  │  Checks Failed:     ${checks_failed}                          │
  │  Warnings:          ${WARNINGS}                               │
  │  Errors:            ${ERRORS}                                 │
  ├──────────────────────────────────────────────────────────────┤
  │                                                              │
  │  Next Steps:                                                │
  │  1. Source the virtual environment:                          │
  │     source .venv/bin/activate                                │
  │  2. Load environment variables:                              │
  │     export \$(cat .env | xargs)                               │
  │  3. Run the agent:                                          │
  │     python agent-torvalds.py                                 │
  │                                                              │
  └──────────────────────────────────────────────────────────────┘

EOF

    log_info "Deployment summary printed"

    if [[ "$checks_failed" -gt 0 ]]; then
        log_warn "Some verification checks failed — review the log"
        return 1
    fi

    return 0
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

main() {
    parse_args "$@"

    print_banner
    log_section "Agent Torvalds Deployment — ${DEPLOY_DATE}"
    log_info "Version: ${SCRIPT_VERSION}"
    log_info "Deploy directory: ${DEPLOY_DIR}"
    log_info "Interactive: ${INTERACTIVE}"
    log_info "Log file: ${LOG_FILE}"

    # Phase 1: Pre-flight
    log_section "Phase 1: Pre-flight Checks"
    check_root_or_sudo
    check_deploy_directory
    check_requirements_files

    # Phase 2: System Detection
    detect_os
    check_python3
    check_git
    check_network
    check_disk_space

    # Phase 3: System Packages
    install_system_packages

    # Phase 4: PostgreSQL
    install_postgres

    # Phase 5: Python Virtual Environment
    setup_python_env

    # Phase 6: Ollama
    setup_ollama

    # Phase 7: Configuration
    bootstrap_config

    # Phase 8: Verification
    verify_deployment

    log_info "Deployment complete!"
}

# Run main if script is executed (not sourced)
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi
