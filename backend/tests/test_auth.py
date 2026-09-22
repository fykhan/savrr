import pytest

from backend.auth import verify_jwt


async def test_verify_jwt_accepts_a_real_token(test_user):
    _, token = test_user
    claims = verify_jwt(token)
    assert claims["sub"] == test_user[0]
    assert claims["aud"] == "authenticated"


async def test_verify_jwt_rejects_tampered_signature(test_user):
    _, token = test_user
    header, payload, signature = token.split(".")
    tampered = f"{header}.{payload}.{signature[:-4]}abcd"
    with pytest.raises(Exception):
        verify_jwt(tampered)


async def test_verify_jwt_rejects_garbage():
    with pytest.raises(Exception):
        verify_jwt("not.a.jwt")
