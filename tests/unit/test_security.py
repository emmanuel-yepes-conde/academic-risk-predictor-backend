"""
Unit tests for app/core/security.py

Validates: Requirements 4.1
- hash_password produces a hash different from the plain text
- hash_password produces a valid bcrypt hash (starts with $2b$)
- verify_password returns True for the correct plain/hash pair
- verify_password returns False for an incorrect plain text
"""

from app.core.security import hash_password, verify_password


def test_hash_password_differs_from_plain():
    plain = "mysecretpassword"
    hashed = hash_password(plain)
    assert hashed != plain


def test_hash_password_is_bcrypt_format():
    hashed = hash_password("anypassword")
    assert hashed.startswith("$2b$")


def test_verify_password_correct_pair():
    plain = "correctpassword"
    hashed = hash_password(plain)
    assert verify_password(plain, hashed) is True


def test_verify_password_wrong_plain():
    hashed = hash_password("originalpassword")
    assert verify_password("wrongpassword", hashed) is False
