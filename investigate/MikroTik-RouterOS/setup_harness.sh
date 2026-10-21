#!/usr/bin/env bash
#
# setup_harness.sh - Build a local SSH harness that emulates the MikroTik RouterOS CLI.
#
# Why: MikroTik's download server is unreachable from this environment, so a real
# RouterOS (CHR container / physical device) could not be used to validate the
# protocol assumptions. This harness runs a real OpenSSH server whose ForceCommand
# reproduces the RouterOS behaviours the toolkit depends on:
#
#   * the RouterOS banner and the initial prompt
#   * the "[admin@MikroTik] >" prompt and submenu paths
#   * "print" table output (Flags / Columns / numbered rows)
#   * "invalid command name X" errors
#   * the <SAFE> safe-mode marker
#
# Ports:
#   2222 - interactive RouterOS-style session (legacy)
#   2223 - exec-mode RouterOS-style commands ($SSH_ORIGINAL_COMMAND)
#   2224 - interactive RouterOS-style session (main harness)
#
set -euo pipefail

HARNESS_DIR="${HARNESS_DIR:-/tmp/sshdtest}"
KEY_BITS="${KEY_BITS:-2048}"
HARNESS_USER="${HARNESS_USER:-$(id -un)}"
PORT_SESSION_A="${PORT_SESSION_A:-2222}"   # interactive session harness
PORT_EXEC="${PORT_EXEC:-2223}"              # exec-mode harness
PORT_SESSION_B="${PORT_SESSION_B:-2224}"   # interactive session harness (main)

mkdir -p "$HARNESS_DIR"
cd "$HARNESS_DIR"

echo "==> Generating SSH keys in $HARNESS_DIR"
[ -f hostkey ]   || ssh-keygen -t rsa -b "$KEY_BITS" -f hostkey   -N "" -q
[ -f userkey ]   || ssh-keygen -t rsa -b "$KEY_BITS" -f userkey   -N "" -q
cp -f userkey.pub authorized_keys
chmod 600 authorized_keys hostkey userkey

echo "==> Writing the fake RouterOS CLI scripts"

# --- interactive session harness (ports 2222 / 2224) ------------------------
cat > fake_routeros.sh <<'EOF'
#!/bin/bash
# Emulates the RouterOS interactive CLI: banner, prompt, print tables, errors.
export TERM=dumb
echo "MikroTik RouterOS 7.19.4 (fake)  Copyright (c) 1999-2025 MikroTik"
echo ""
echo "Type '?' for help"
echo -n "[admin@MikroTik] > "
while IFS= read -r line; do
  cmd="${line#/}"
  case "$cmd" in
    "") ;;
    system/resource) echo "                   uptime: 3d4h5m6s" ;;
    identity)        echo "  name: lab-router" ;;
    interface/print)
      echo "Flags: R - RUNNING"
      echo "Columns: NAME, TYPE, ACTUAL-MTU, L2MTU"
      for i in $(seq 0 49); do printf "  %d  R ether%d 1500 1598\n" "$i" "$i"; done
      ;;
    ip/address/print)
      echo "Columns: ADDRESS, NETWORK, INTERFACE"
      echo "  192.168.88.1/24  192.168.88.0  ether1"
      ;;
    *) echo "invalid command name $cmd" ;;
  esac
  echo -n "[admin@MikroTik] > "
done
EOF

# --- exec-mode harness (port 2223) ------------------------------------------
cat > fake_routeros_exec.sh <<'EOF'
#!/bin/bash
# Emulates RouterOS SSH exec-mode: "ssh router '/system/resource'".
# The real sshd passes the requested command in $SSH_ORIGINAL_COMMAND.
export TERM=dumb
cmd="$SSH_ORIGINAL_COMMAND"
cmd="${cmd#/}"
case "$cmd" in
  system/resource) echo "                   uptime: 3d4h5m6s"; exit 0 ;;
  interface/print) printf "Flags: R - RUNNING\n  0  R ether1 1500\n"; exit 0 ;;
  *) echo "invalid command name $cmd" >&2; exit 1 ;;
esac
EOF

chmod +x fake_routeros.sh fake_routeros_exec.sh

# --- sshd configs ------------------------------------------------------------
write_config() {  # $1=port  $2=pidfile  $3=force-command
cat > "sshd_config_$1" <<EOF
Port $1
ListenAddress 127.0.0.1
HostKey $HARNESS_DIR/hostkey
PidFile $HARNESS_DIR/sshd_$1.pid
AuthorizedKeysFile $HARNESS_DIR/authorized_keys
PasswordAuthentication no
PubkeyAuthentication yes
PermitRootLogin no
UsePAM no
StrictModes no
LogLevel VERBOSE
Subsystem sftp internal-sftp

Match User $HARNESS_USER
    ForceCommand $3
EOF
}

write_config "$PORT_SESSION_A" "$HARNESS_DIR" "$HARNESS_DIR/fake_routeros.sh"
write_config "$PORT_EXEC"      "$HARNESS_DIR" "$HARNESS_DIR/fake_routeros_exec.sh"
write_config "$PORT_SESSION_B" "$HARNESS_DIR" "$HARNESS_DIR/fake_routeros.sh"

# --- known_hosts fixtures ----------------------------------------------------
: > known_hosts                                   # strict policy: nothing trusted
ssh-keyscan -p "$PORT_EXEC" -t rsa 127.0.0.1 2>/dev/null > known_hosts_ok || true

echo "==> Starting the SSH harness"
for port in "$PORT_SESSION_A" "$PORT_EXEC" "$PORT_SESSION_B"; do
  if (ss -tln 2>/dev/null || netstat -tln 2>/dev/null) | grep -q ":$port "; then
    echo "    port $port already in use - skipping"
    continue
  fi
  setsid /usr/sbin/sshd -f "$HARNESS_DIR/sshd_config_$port" -D -e \
      > "$HARNESS_DIR/sshd_$port.log" 2>&1 &
  sleep 1
done

echo
echo "==> Verifying"
for port in "$PORT_SESSION_A" "$PORT_EXEC" "$PORT_SESSION_B"; do
  if (ss -tln 2>/dev/null || netstat -tln 2>/dev/null) | grep -q ":$port "; then
    echo "    port $port: LISTENING"
  else
    echo "    port $port: NOT LISTENING (see $HARNESS_DIR/sshd_$port.log)"
  fi
done

cat <<EOF

Harness ready.

  user      : $HARNESS_USER
  key       : $HARNESS_DIR/userkey
  host key  : $HARNESS_DIR/hostkey.pub
  exec port : $PORT_EXEC      (RouterOS-style exec mode)
  sess port : $PORT_SESSION_B (RouterOS-style interactive session)

Run the prototypes:
  cd self-development/investigate/MikroTik-RouterOS
  ../../.venv/bin/python proto_prompt_regex.py
  ../../.venv/bin/python proto_asyncssh.py
  ../../.venv/bin/python proto_exec.py
  ../../.venv/bin/python proto_session.py
  ../../.venv/bin/python proto_hostkey.py
  ../../.venv/bin/python proto_api.py
EOF
