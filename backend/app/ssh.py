"""SSH connections to managed servers.

Security rules:
- The server's host key is pinned. The first "Test connection" (done by an admin) records it; every
  later connection must present the same key, or it is refused (protects against impostor servers).
- Runs refuse servers whose host key hasn't been verified yet.
- Credentials are decrypted only here, only for the duration of the connection.
"""
import base64
import hashlib
import io
from dataclasses import dataclass

import paramiko

from . import secrets_store

CONNECT_TIMEOUT = 15


class SSHError(RuntimeError):
    pass


@dataclass
class Target:
    hostname: str
    port: int
    username: str
    kind: str  # ssh_key | password
    secret: str  # decrypted
    passphrase: str | None
    host_key: str | None  # "<type> <base64>" or None when not verified yet


def fingerprint(key: paramiko.PKey) -> str:
    digest = hashlib.sha256(key.asbytes()).digest()
    return "SHA256:" + base64.b64encode(digest).decode().rstrip("=")


def load_private_key(text: str, passphrase: str | None = None) -> paramiko.PKey:
    """Parse an OpenSSH/PEM private key of any common type."""
    errors = []
    for cls in (paramiko.Ed25519Key, paramiko.ECDSAKey, paramiko.RSAKey):
        try:
            return cls.from_private_key(io.StringIO(text.strip() + "\n"), password=passphrase or None)
        except paramiko.PasswordRequiredException:
            raise SSHError("This private key is encrypted: enter its passphrase.")
        except (paramiko.SSHException, ValueError) as e:
            errors.append(str(e))
    raise SSHError("Not a valid private key (supported: Ed25519, ECDSA, RSA).")


def target_for(server, credential) -> Target:
    if credential is None:
        raise SSHError(f"Server {server.name} has no credential assigned.")
    return Target(
        hostname=server.hostname, port=server.port, username=credential.username, kind=credential.kind,
        secret=secrets_store.decrypt(credential.encrypted_secret),
        passphrase=secrets_store.decrypt(credential.encrypted_passphrase) if credential.encrypted_passphrase else None,
        host_key=server.host_key,
    )


def _known_hosts_name(t: Target) -> str:
    return t.hostname if t.port == 22 else f"[{t.hostname}]:{t.port}"


def connect(t: Target, trust_new_host_key: bool = False) -> paramiko.SSHClient:
    """Open a connection. With a pinned host key, a different key is refused. Without one, the
    connection is only allowed when trust_new_host_key=True (the admin's first test)."""
    client = paramiko.SSHClient()
    if t.host_key:
        key_type, key_b64 = t.host_key.split(" ", 1)
        client.get_host_keys().add(_known_hosts_name(t), key_type, paramiko.PKey.from_type_string(key_type, base64.b64decode(key_b64)))
        client.set_missing_host_key_policy(paramiko.RejectPolicy())
    elif trust_new_host_key:
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    else:
        raise SSHError("This server's identity hasn't been verified yet. An admin must run 'Test connection' first.")

    kwargs = {"hostname": t.hostname, "port": t.port, "username": t.username, "timeout": CONNECT_TIMEOUT,
              "banner_timeout": CONNECT_TIMEOUT, "auth_timeout": CONNECT_TIMEOUT,
              "allow_agent": False, "look_for_keys": False}
    if t.kind == "ssh_key":
        kwargs["pkey"] = load_private_key(t.secret, t.passphrase)
    else:
        kwargs["password"] = t.secret
    try:
        client.connect(**kwargs)
    except paramiko.BadHostKeyException:
        raise SSHError("HOST KEY MISMATCH: the server presented a different identity than the one pinned. "
                       "Refusing to connect. If the server was rebuilt, an admin must reset its host key.")
    except paramiko.AuthenticationException:
        raise SSHError("Authentication failed: check the credential's username and key/password.")
    except (paramiko.SSHException, OSError) as e:
        raise SSHError(f"Could not connect to {t.hostname}:{t.port}: {e}")
    return client


def host_key_of(client: paramiko.SSHClient) -> tuple[str, str]:
    key = client.get_transport().get_remote_server_key()
    return f"{key.get_name()} {key.get_base64()}", fingerprint(key)
