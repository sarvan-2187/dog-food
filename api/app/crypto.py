"""Ed25519 signing for judge participation records (PLAN.md Phase 4 T4).

The keypair is generated once, on first use, and persisted to KEYS_DIR (a
mounted volume in docker-compose.yml) rather than held only in memory --
an in-memory-only key would silently invalidate every record issued before
the process restarts. Entirely offline: no external KMS or signing service.
"""
import base64
import json
import os
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    PublicFormat,
    load_pem_private_key,
)

KEYS_DIR = Path(os.getenv("KEYS_DIR", "keys"))
_PRIVATE_KEY_PATH = KEYS_DIR / "judger-ed25519.pem"


def _load_or_create_key() -> Ed25519PrivateKey:
    if _PRIVATE_KEY_PATH.exists():
        return load_pem_private_key(_PRIVATE_KEY_PATH.read_bytes(), password=None)
    KEYS_DIR.mkdir(parents=True, exist_ok=True)
    key = Ed25519PrivateKey.generate()
    _PRIVATE_KEY_PATH.write_bytes(key.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption()))
    return key


_private_key = _load_or_create_key()
_public_key: Ed25519PublicKey = _private_key.public_key()

public_key_b64 = base64.b64encode(
    _public_key.public_bytes(Encoding.Raw, PublicFormat.Raw)
).decode("ascii")


def canonical_json(payload: dict) -> bytes:
    """Sort keys and fix separators so the same payload always serialises
    identically -- a signature only verifies against one exact byte string."""
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sign_record(payload: dict) -> dict:
    """Returns the payload alongside its signature and the public key needed
    to verify it, so a verifier never has to trust this server again."""
    message = canonical_json(payload)
    signature = base64.b64encode(_private_key.sign(message)).decode("ascii")
    return {
        "record": payload,
        "signature": signature,
        "public_key": public_key_b64,
        "algorithm": "ed25519",
    }


def verify_record(record: dict, signature_b64: str, public_key_b64_: str) -> bool:
    """Pure verification against a caller-supplied public key -- used by the
    self-check below and by any external party who received a record."""
    public_key = Ed25519PublicKey.from_public_bytes(base64.b64decode(public_key_b64_))
    try:
        public_key.verify(base64.b64decode(signature_b64), canonical_json(record))
        return True
    except Exception:
        return False


if __name__ == "__main__":
    demo = {"judge_id": 1, "event_id": 1, "submissions_scored": 3}
    signed = sign_record(demo)
    assert verify_record(signed["record"], signed["signature"], signed["public_key"])
    tampered = dict(demo, submissions_scored=99)
    assert not verify_record(tampered, signed["signature"], signed["public_key"])
    print("crypto self-check passed")
