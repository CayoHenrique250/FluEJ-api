
from dataclasses import dataclass

from fastapi import Depends, Header, HTTPException

from .db import SupabaseRepo, get_repo
from .security import TokenVerifier, get_verifier

PERFIS = {"presidente", "rh", "projetos",
          "comercial", "financeiro", "orientador"}

PERFIS_DE_SETOR = {"rh", "projetos", "comercial", "financeiro"}


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
            401, "Envie o cabeçalho Authorization: Bearer <token>.")
    claims = verifier.verify(authorization.split(" ", 1)[1].strip())
    user_id = claims.get("sub")
    linhas = repo.select(
        "perfis", {"user_id": f"eq.{user_id}", "select": "perfil,setor,nome"})
    if not linhas or linhas[0].get("perfil") not in PERFIS:
        raise HTTPException(403, "Usuário sem perfil de acesso configurado.")
    p = linhas[0]
    return Usuario(user_id=user_id, perfil=p["perfil"], setor=p.get("setor"), nome=p.get("nome"))


def exigir_perfis(usuario: Usuario, permitidos: set[str]) -> None:
    if usuario.perfil not in permitidos:
        raise HTTPException(403, "Seu perfil não tem acesso a este recurso.")


def setor_efetivo(usuario: Usuario, pedido: str | None) -> str | None:
    if usuario.restrito_ao_setor:
        return usuario.setor
    return pedido
