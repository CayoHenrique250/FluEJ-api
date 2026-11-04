from datetime import date

import pytest
from fastapi.testclient import TestClient

from app import routes
from app.db import get_repo
from app.holidays import HolidayService, get_holidays
from app.main import app
from app.security import get_verifier

PERFIS = [
    {"user_id": "u-rh", "perfil": "rh", "setor": "RH", "nome": "Gestor de RH"},
    {"user_id": "u-proj", "perfil": "projetos", "setor": "Projetos", "nome": "Gestor de Projetos"},
    {"user_id": "u-pres", "perfil": "presidente", "setor": None, "nome": "Presidente"},
    {"user_id": "u-ori", "perfil": "orientador", "setor": None, "nome": "Orientador"},
]
MEMBERS = [
    {"id": "m1", "nome": "Ana", "cargo": "Assessor", "setor": "RH", "ativo": True},
    {"id": "m2", "nome": "Bia", "cargo": "Gerente", "setor": "RH", "ativo": True},
    {"id": "m3", "nome": "Caio", "cargo": "Diretor", "setor": "RH", "ativo": False},
    {"id": "m4", "nome": "Davi", "cargo": "Trainee", "setor": "Projetos", "ativo": True},
]
ATIVIDADES = [
    {"member_id": "m1", "data": "2026-11-02", "pontos": 120},
    {"member_id": "m1", "data": "2026-10-20", "pontos": 60},
    {"member_id": "m2", "data": "2026-11-03", "pontos": 30},
    {"member_id": "m3", "data": "2026-11-03", "pontos": 999},
    {"member_id": "m4", "data": "2026-11-04", "pontos": 90},
]
AVISOS = [
    {"id": "a1", "titulo": "Geral", "mensagem": "p/ todos", "setor": None, "criado_em": "2026-11-01T10:00:00+00:00"},
    {"id": "a2", "titulo": "Só RH", "mensagem": "rh", "setor": "RH", "criado_em": "2026-11-02T10:00:00+00:00"},
    {"id": "a3", "titulo": "Só Projetos", "mensagem": "proj", "setor": "Projetos", "criado_em": "2026-11-02T11:00:00+00:00"},
]
DOCS = [
    {"id": "d1", "setor": "RH", "titulo": "Termos de voluntariado", "quantidade": 2},
    {"id": "d2", "setor": "Projetos", "titulo": "Termos de encerramento", "quantidade": 1},
]
PROJETOS = [
    {"id": "p1", "nome": "Feira", "total_pontos": 100, "setor": "RH"},
    {"id": "p2", "nome": "Site", "total_pontos": 50, "setor": "Projetos"},
]
VINCULOS = [{"project_id": "p1", "member_id": "m1"}]


class FakeRepo:

    TABELAS = {
        "perfis": PERFIS, "members": MEMBERS, "atividades": ATIVIDADES, "avisos": AVISOS,
        "documentos_pendentes": DOCS, "projetos": PROJETOS, "projeto_membros": VINCULOS,
    }

    def select(self, tabela, params=None):
        itens = params.items() if isinstance(params, dict) else (params or [])
        linhas = list(self.TABELAS[tabela])
        for chave, valor in itens:
            if chave in ("select", "order", "or") or not isinstance(valor, str):
                continue
            op, _, v = valor.partition(".")
            if op == "eq":
                alvo = {"true": True, "false": False}.get(v, v)
                linhas = [l for l in linhas if l.get(chave) == alvo]
            elif op == "gte":
                linhas = [l for l in linhas if l[chave] >= v]
            elif op == "lt":
                linhas = [l for l in linhas if l[chave] < v]
            elif op == "in":
                ids = v.strip("()").split(",")
                linhas = [l for l in linhas if l[chave] in ids]
        return linhas


class FakeVerifier:
    def verify(self, token):
        if not token.startswith("tok-"):
            from fastapi import HTTPException
            raise HTTPException(401, "Token inválido ou expirado.")
        return {"sub": token.replace("tok-", "u-", 1)}


class FakeHolidays(HolidayService):
    def do_ano(self, ano):
        return [
            {"data": f"{ano}-11-15", "nome": "Proclamação da República", "tipo": "national"},
            {"data": f"{ano}-12-25", "nome": "Natal", "tipo": "national"},
            {"data": f"{ano}-01-01", "nome": "Confraternização Universal", "tipo": "national"},
        ]


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(routes, "hoje", lambda: date(2026, 11, 10))
    app.dependency_overrides[get_repo] = lambda: FakeRepo()
    app.dependency_overrides[get_verifier] = lambda: FakeVerifier()
    app.dependency_overrides[get_holidays] = lambda: FakeHolidays()
    yield TestClient(app)
    app.dependency_overrides.clear()


def auth(quem):
    return {"Authorization": f"Bearer tok-{quem}"}
