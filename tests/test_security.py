
import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi import HTTPException

from app.security import TokenVerifier


class _Chave:
    def __init__(self, key):
        self.key = key


class _FakeJwks:
    def __init__(self, public_key):
        self.public_key = public_key

    def get_signing_key_from_jwt(self, token):
        return _Chave(self.public_key)


@pytest.fixture
def par():
    privada = ec.generate_private_key(ec.SECP256R1())
    return privada, privada.public_key()


def _verifier(public_key):
    v = TokenVerifier()
    v._jwks = _FakeJwks(public_key)
    return v


def _token(privada, **extra):
    claims = {"sub": "u-1", "aud": "authenticated",
              "exp": int(time.time()) + 3600, **extra}
    return jwt.encode(claims, privada, algorithm="ES256", headers={"kid": "k1"})


def test_token_valido(par):
    privada, publica = par
    assert _verifier(publica).verify(_token(privada))["sub"] == "u-1"


def test_token_expirado(par):
    privada, publica = par
    with pytest.raises(HTTPException) as e:
        _verifier(publica).verify(_token(privada, exp=int(time.time()) - 10))
    assert e.value.status_code == 401


def test_audiencia_errada(par):
    privada, publica = par
    with pytest.raises(HTTPException) as e:
        _verifier(publica).verify(_token(privada, aud="outra"))
    assert e.value.status_code == 401


def test_assinatura_de_outra_chave(par):
    privada, publica = par
    impostora = ec.generate_private_key(ec.SECP256R1())
    with pytest.raises(HTTPException) as e:
        _verifier(publica).verify(_token(impostora))
    assert e.value.status_code == 401
