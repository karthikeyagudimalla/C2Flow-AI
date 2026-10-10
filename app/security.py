
from pwdlib import PasswordHash

# Use Argon2 through pwdlib's recommended password-hashing configuration.
password_hasher = PasswordHash.recommended()


def hash_password(password: str) -> str:
    """Convert a plain-text password into a secure password hash."""
    return password_hasher.hash(password)


def verify_password(password: str, hashed_password: str) -> bool:
    """Check a password against its stored hash."""
    return password_hasher.verify(password, hashed_password)
