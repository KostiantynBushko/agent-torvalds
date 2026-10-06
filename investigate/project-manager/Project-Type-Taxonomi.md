# Project Types Taxonomy

This document defines the types of projects the AI agent should recognize and manage.  
Each project type includes **indicators**, **tools**, and **configuration fields**.

---

## 🛠️ Software Development Projects

### Python Project
- **Indicators**: `requirements.txt`, `setup.py`, `pyproject.toml`
- **Tools**: `pip`, `pytest`, `uvicorn`
- **Config Fields**: entry points, virtualenv, dependencies

### Node.js Project
- **Indicators**: `package.json`, `yarn.lock`
- **Tools**: `npm`, `yarn`
- **Config Fields**: build/test scripts, runtime commands

### Java Project
- **Indicators**: `pom.xml`, `build.gradle`
- **Tools**: Maven, Gradle
- **Config Fields**: JDK version, main class, build profiles

### C/C++ Project
- **Indicators**: `CMakeLists.txt`, `Makefile`
- **Tools**: `gcc`, `clang`, `cmake`, `make`
- **Config Fields**: compiler flags, target binaries

### Rust Project
- **Indicators**: `Cargo.toml`
- **Tools**: Cargo
- **Config Fields**: crate type, dependencies

### Go Project
- **Indicators**: `go.mod`
- **Tools**: `go build`, `go test`
- **Config Fields**: module path, build targets

---

## ⚙️ Embedded & Hardware Projects

### ESP32 / FreeRTOS Project
- **Indicators**: `sdkconfig`, `main.c`, `CMakeLists.txt`
- **Tools**: `idf.py`, `esptool.py`
- **Config Fields**: flash commands, serial port, board type

### PX4 / UAV Project
- **Indicators**: `ROMFS/px4fmu_common`, `CMakeLists.txt`
- **Tools**: `make px4_sitl`, `mavlink`
- **Config Fields**: SITL vs hardware build, target board

### Motorola TRBO Project
- **Indicators**: `.rdt`, `config.json`, firmware `.bin`
- **Tools**: TRBO config tool, TRBO keygen, TRBO flash
- **Config Fields**: device model (DP4400, DP4800), key management, firmware path

### FPGA Project
- **Indicators**: `.vhd`, `.sv`, `.xdc`
- **Tools**: Vivado, Quartus
- **Config Fields**: synthesis scripts, bitstream flashing

### Yocto Project
- **Indicators**: `conf/local.conf`, `conf/bblayers.conf`, `meta-*` directories
- **Tools**: `bitbake`, `devtool`, `yocto-build`
- **Config Fields**: target machine, layers, recipes, SDK generation

### System Software Project
*(covers Linux kernel, U‑Boot, and similar low‑level system software)*  
- **Indicators**: `Makefile`, `Kconfig`, `arch/` directories
- **Tools**: `make`, `gcc`, cross‑compiler toolchains
- **Config Fields**: kernel config options, board support packages, bootloader targets

---

## 📂 Configuration / Non‑Code Projects

### Documentation Project
- **Indicators**: `.md`, `.rst`, `mkdocs.yml`
- **Tools**: MkDocs, Sphinx
- **Config Fields**: site build commands, theme settings

### Configuration Project
- **Indicators**: `.json`, `.yaml`, `.ini`
- **Tools**: custom CLI tools
- **Config Fields**: schema validation, deployment scripts

### Data Science Project
- **Indicators**: `.ipynb`, `requirements.txt`
- **Tools**: Jupyter, pandas, scikit‑learn
- **Config Fields**: environment setup, dataset paths

---

## 🚀 Notes
- Every project must be placed under **Git version control**.  
- If a folder is not a Git repo, the agent initializes one automatically.  
- Workspaces may contain **multiple projects**; each project is tracked separately in `.agentworkspace.json`.  
- Ambiguities are resolved via **human‑in‑the‑loop** (console or whiptail).

