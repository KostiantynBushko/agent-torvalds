"""
Shared configuration for the MikroTik RouterOS investigation prototypes.

The prototypes run against a local SSH harness that emulates the RouterOS CLI.
Build it with ``setup_harness.sh`` (it starts a real sshd with a ForceCommand
script that reproduces the RouterOS banner, prompt, print tables and errors).

Every value can be overridden with an environment variable, so the prototypes
can also be pointed at a real router:

    export HARNESS_HOST=10.0.0.1
    export HARNESS_PORT_SESSION=22
    export HARNESS_PORT_EXEC=22
    export HARNESS_USER=admin
    export HARNESS_KEY=~/.ssh/id_ed25519
"""
import getpass
import os

# --- Local SSH harness (emulates a MikroTik RouterOS CLI) ---------------------
HARNESS_DIR = os.environ.get("HARNESS_DIR", "/tmp/sshdtest")

HARNESS_HOST = os.environ.get("HARNESS_HOST", "127.0.0.1")
HARNESS_PORT_SESSION = int(os.environ.get("HARNESS_PORT_SESSION", "2224"))  # interactive
HARNESS_PORT_EXEC = int(os.environ.get("HARNESS_PORT_EXEC", "2223"))       # exec mode
# The account of the operator, taken from the environment — the Python
# equivalent of $USER, and it is never written down.
HARNESS_USER = os.environ.get(
    "HARNESS_USER", os.environ.get("USER") or getpass.getuser()
)
HARNESS_KEY = os.environ.get("HARNESS_KEY", f"{HARNESS_DIR}/userkey")

HARNESS_HOSTKEY_PUB = os.environ.get("HARNESS_HOSTKEY_PUB", f"{HARNESS_DIR}/hostkey.pub")
HARNESS_KNOWN_HOSTS = os.environ.get("HARNESS_KNOWN_HOSTS", f"{HARNESS_DIR}/known_hosts")
HARNESS_KNOWN_HOSTS_OK = os.environ.get("HARNESS_KNOWN_HOSTS_OK", f"{HARNESS_DIR}/known_hosts_ok")

# --- Real router (opt-in, for integration testing) -----------------------------
# export MIKROTIK_TEST_HOST=10.0.0.1
# export MIKROTIK_TEST_USER=admin
# export MIKROTIK_TEST_PASSWORD=...
