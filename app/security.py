
import jwt
from fastapi import HTTPException
from jwt import PyJWKClient

from .config import get_settings


class TokenVerifier:
    def __init__(self):
        self._jwks: PyJWKClient | None = None

    def _client(self) -> PyJWKClient:
        if self._jwks is None:
            url = get_settings().supabase_url + "/auth/v1/.well-known/jwks.json"
            self._jwks = PyJWKClient(url, cache_keys=True)
        return self._jwks

    def verify(self, token: str) -> dict:
        try:
            alg = jwt.get_unverified_header(token).get("alg")
            if alg == "HS256":
                secret = get_settings().supabase_jwt_secret
                if not secret:
                    raise HTTPException(401, "Token HS256 recusado: JWT secret não configurado.")
                key, algs = secret, ["HS256"]
            else:
                key = self._client().get_signing_key_from_jwt(token).key
                algs = ["ES256", "RS256"]
            return jwt.decode(token, key, algorithms=algs, audience="authenticated")
        except HTTPException:
            raise
        except jwt.PyJWTError:
            raise HTTPException(401, "Token inválido ou expirado.")


_verifier = TokenVerifier()


def get_verifier() -> TokenVerifier:
    return _verifier
