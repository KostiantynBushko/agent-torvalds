"""
SSH Toolkit - Configuration

This module defines the SSH connection configuration using Pydantic v2.
"""

from pydantic import BaseModel, ConfigDict, Field, SecretStr


class SSHConfig(BaseModel):
    """
    SSH connection configuration model.
    
    This model uses frozen=True and extra="forbid" to ensure configuration
    integrity. A misspelled configuration property will fail validation
    immediately rather than being silently ignored.
    
    Attributes:
        host: SSH server hostname or IP address
        username: SSH username
        password: SSH password (optional, uses SecretStr for security)
        port: SSH TCP port (default: 22)
        connect_timeout: Maximum connection establishment time in seconds (default: 10.0)
        command_timeout: Default command execution timeout in seconds (default: 30.0)
        known_hosts: Path to known_hosts file (optional)
        client_keys: Tuple of private key file paths (optional)
        keepalive_interval: Keepalive interval in seconds (default: 30.0, None to disable)
    
    Example:
        >>> config = SSHConfig(
        ...     host="10.0.0.10",
        ...     username="automation",
        ...     password="secret",
        ... )
        >>> config.host
        '10.0.0.10'
    """
    
    model_config = ConfigDict(
        frozen=True,      # Immutable configuration
        extra="forbid",   # Fail on unknown fields
    )
    
    host: str = Field(
        min_length=1,
        description="SSH server hostname or IP address",
    )
    
    username: str = Field(
        min_length=1,
        description="SSH username",
    )
    
    password: SecretStr | None = Field(
        default=None,
        description="SSH password (uses SecretStr for secure handling)",
    )
    
    port: int = Field(
        default=22,
        ge=1,
        le=65535,
        description="SSH TCP port",
    )
    
    connect_timeout: float = Field(
        default=10.0,
        gt=0,
        description="Maximum connection establishment time in seconds",
    )
    
    command_timeout: float = Field(
        default=30.0,
        gt=0,
        description="Default command execution timeout in seconds",
    )
    
    known_hosts: str | None = Field(
        default=None,
        description="Path to known_hosts file for host-key verification",
    )
    
    client_keys: tuple[str, ...] = Field(
        default_factory=tuple,
        description="Tuple of private key file paths for key-based authentication",
    )
    
    keepalive_interval: float | None = Field(
        default=30.0,
        gt=0,
        description="Keepalive interval in seconds (None to disable)",
    )
    
    def get_password(self) -> str | None:
        """
        Safely unwrap the password SecretStr.
        
        Returns:
            The password string or None if not set.
        """
        if self.password is None:
            return None
        return self.password.get_secret_value()
    
    def __repr__(self) -> str:
        # Hide password in repr
        return (
            f"SSHConfig(host={self.host!r}, username={self.username!r}, "
            f"port={self.port}, password={'***' if self.password else None}, "
            f"connect_timeout={self.connect_timeout}, "
            f"command_timeout={self.command_timeout})"
        )
