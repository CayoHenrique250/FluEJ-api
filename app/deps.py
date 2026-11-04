
import logging
from dataclasses import dataclass

from fastapi import Depends, Header, HTTPException

from .db import SupabaseRepo, get_repo
from .security import TokenVerifier, get_verifier


logger = logging.getLogger(__name__)


PERFIS = {
    "presidente",
    "rh",
    "projetos",
    "comercial",
    "financeiro",
    "orientador",
}

PERFIS_DE_SETOR = {
    "rh",
    "projetos",
    "comercial",
    "financeiro",
}


@dataclass
class Usuario:
    user_id: str
    perfil: str
    setor: str | None
    nome: str | None

    @property
    def restrito_ao_setor(self) -> bool:
        return self.perfil in PERFIS_DE_SETOR

    @property
    def restrito_em_membros(self) -> bool:
        return self.perfil in {"projetos", "comercial", "financeiro"}


def get_usuario(
    authorization: str | None = Header(default=None),
    verifier: TokenVerifier = Depends(get_verifier),
    repo: SupabaseRepo = Depends(get_repo),
) -> Usuario:

    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=401,
            detail="Envie o cabeçalho Authorization: Bearer <token>."
        )

    token = authorization.split(" ", 1)[1].strip()
    claims = verifier.verify(token)

    user_id = claims.get("sub")

    if not user_id:
        raise HTTPException(
            status_code=401,
            detail="Token sem identificação de usuário."
        )

    linhas = repo.select(
        "perfis",
        {
            "user_id": f"eq.{user_id}",
            "select": "perfil,setor,nome"
        }
    )

    perfil_encontrado = (
        linhas[0].get("perfil") if linhas else None
    )

    logger.warning(
        "[AUTENTICACAO] sub=%s | perfil=%s | registro_encontrado=%s",
        user_id,
        perfil_encontrado,
        bool(linhas)
    )

    if not linhas or perfil_encontrado not in PERFIS:
        raise HTTPException(
            status_code=403,
            detail="Usuário sem perfil de acesso configurado."
        )

    p = linhas[0]

    return Usuario(
        user_id=user_id,
        perfil=p["perfil"],
        setor=p.get("setor"),
        nome=p.get("nome")
    )


def exigir_perfis(
    usuario: Usuario,
    permitidos: set[str]
) -> None:

    if usuario.perfil not in permitidos:
        raise HTTPException(
            status_code=403,
            detail="Seu perfil não tem acesso a este recurso."
        )


def setor_efetivo(
    usuario: Usuario,
    pedido: str | None
) -> str | None:

    if usuario.restrito_ao_setor:
        return usuario.setor

    return pedido
