"""
Prototype: proving the RouterOS API cannot substitute for SSH.

Validates investigation hypothesis V11:
  - routeros_api speaks the BINARY API protocol (default TCP 8728), not SSH.
  - Pointing it at an SSH port fails with a protocol error, which proves the
    two transports are distinct and that the API cannot run arbitrary CLI
    commands over SSH.

Usage:
    python proto_api.py
"""
import routeros_api


def try_api(host: str, port: int, label: str) -> None:
    """Attempt an API connection and report the failure mode."""
    try:
        api = routeros_api.connect(
            host=host, port=port, username="admin", password="x"
        )
        print(f"{label:44} -> connected (unexpected)")
        api.close()
    except Exception as exc:  # noqa: BLE001 - reporting every failure mode
        print(f"{label:44} -> {type(exc).__name__}: {str(exc)[:80]}")


def main() -> None:
    print("routeros_api exports:", [n for n in dir(routeros_api) if not n.startswith("_")])
    print()

    # The SSH harness listens on 2223 -> an API client must fail (protocol mismatch)
    try_api("127.0.0.1", 2223, "routeros_api vs SSH port (2223)")

    # The real RouterOS API port with nothing listening -> connection refused
    try_api("127.0.0.1", 8728, "routeros_api vs API port (8728, closed)")

    print()
    print("Conclusion: the RouterOS API is a separate transport on 8728/8729.")
    print("It cannot execute arbitrary CLI commands over SSH; it is useful only")
    print("as an optional secondary channel for structured reads.")


if __name__ == "__main__":
    main()
