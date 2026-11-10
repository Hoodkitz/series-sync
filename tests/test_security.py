import pytest
from apps.api.security.auth import get_password_hash, verify_password

def test_password_hashing():
    password = "secretpassword123"
    hashed = get_password_hash(password)

    assert hashed != password
    assert verify_password(password, hashed)
    assert not verify_password("wrongpassword", hashed)
