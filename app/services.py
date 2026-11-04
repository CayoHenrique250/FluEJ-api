
from collections import defaultdict
from datetime import date

from .db import SupabaseRepo

PONTOS_POR_HORA = 60


def horas(pontos: int) -> float:
    return round(pontos / PONTOS_POR_HORA, 2)


def periodo_do_mes(hoje: date) -> tuple[str, str]:
    inicio = hoje.replace(day=1)
    fim = (inicio.replace(year=inicio.year + 1, month=1) if inicio.month == 12
           else inicio.replace(month=inicio.month + 1))
    return inicio.isoformat(), fim.isoformat() 


def membros_ativos(repo: SupabaseRepo, setor: str | None) -> list[dict]:
    params = {"select": "id,nome,cargo,setor", "ativo": "eq.true"}
    if setor:
        params["setor"] = f"eq.{setor}"
    return repo.select("members", params)


def pontos_por_membro(repo: SupabaseRepo, inicio: str, fim_exclusivo: str) -> dict[str, int]:
    linhas = repo.select("atividades", [
        ("select", "member_id,pontos"),
        ("data", f"gte.{inicio}"),
        ("data", f"lt.{fim_exclusivo}"),
    ])
    soma: dict[str, int] = defaultdict(int)
    for a in linhas:
        soma[a["member_id"]] += a["pontos"]
    return soma


def ranking(repo: SupabaseRepo, setor: str | None, inicio: str, fim_exclusivo: str, ordem: str) -> list[dict]:
    membros = membros_ativos(repo, setor)
    soma = pontos_por_membro(repo, inicio, fim_exclusivo)
    itens = [
        {"membro_id": m["id"], "nome": m["nome"], "cargo": m["cargo"], "setor": m["setor"],
         "pontos": soma.get(m["id"], 0), "horas": horas(soma.get(m["id"], 0))}
        for m in membros
    ]
    itens.sort(key=lambda i: (i["pontos"], i["nome"].lower()), reverse=(ordem == "desc"))
    return itens
