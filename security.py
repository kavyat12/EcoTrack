import hashlib
import hmac
import secrets


PASSWORD_ITERATIONS = 310_000
PASSWORD_MIN_LENGTH = 10
PASSWORD_MAX_LENGTH = 128


def hash_password(password):
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, PASSWORD_ITERATIONS
    )
    return salt.hex(), digest.hex()


def verify_password(password, salt_hex, digest_hex):
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), PASSWORD_ITERATIONS
    )
    return hmac.compare_digest(digest.hex(), digest_hex)


def new_session_token():
    return secrets.token_urlsafe(32)


def session_token_digest(token):
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
