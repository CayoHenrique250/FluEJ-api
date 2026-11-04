
from collections import defaultdict
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query

from . import services
from .config import get_settings
from .db import SupabaseRepo, get_repo
from .deps import Usuario, exigir_perfis, get_usuario, setor_efetivo
from .holidays import HolidayService, get_holidays

router = APIRouter(prefix="/v1")

TODOS = {"presidente", "rh", "projetos",
         "comercial", "financeiro", "orientador"}


def hoje() -> date:
    return date.today()


@router.get("/feriados/proximos", tags=["Feriados"])
def feriados_proximos(
    dias: int = Query(30, ge=1, le=366),
    _: Usuario = Depends(get_usuario),
    feriados: HolidayService = Depends(get_holidays),
):

    return feriados.proximos(hoje(), dias)


@router.get("/feriados/{ano}", tags=["Feriados"])
def feriados_do_ano(
    ano: int,
    _: Usuario = Depends(get_usuario),
    feriados: HolidayService = Depends(get_holidays),
):
    if not 2000 <= ano <= 2100:
        raise HTTPException(400, "Ano fora do intervalo 2000-2100.")
    return feriados.do_ano(ano)


@router.get("/notificacoes", tags=["Notificações"])
def notificacoes(
    usuario: Usuario = Depends(get_usuario),
    repo: SupabaseRepo = Depends(get_repo),
    feriados: HolidayService = Depends(get_holidays),
):
    agora = datetime.now(timezone.utc).isoformat()
    avisos = repo.select("avisos", {
        "select": "id,titulo,mensagem,setor,criado_em",
        "or": f"(expira_em.is.null,expira_em.gt.{agora})",
        "order": "criado_em.desc",
    })
    itens = []
    for a in avisos:
        if a["setor"] is None or not usuario.restrito_ao_setor or a["setor"] == usuario.setor:
            itens.append({"id": a["id"], "tipo": "aviso", "titulo": a["titulo"],
                          "mensagem": a["mensagem"], "data": a["criado_em"][:10]})
    for f in feriados.proximos(hoje(), get_settings().dias_aviso_feriado):
        quando = "hoje" if f["faltam_dias"] == 0 else f"em {f['faltam_dias']} dia(s)"
        itens.append({"id": f"feriado-{f['data']}", "tipo": "feriado",
                      "titulo": f["nome"], "mensagem": f"Feriado nacional {quando}.",
                      "data": f["data"]})
    return {"total": len(itens), "itens": itens}


@router.get("/documentos-pendentes", tags=["Dashboard"])
def documentos_pendentes(
    setor: str | None = None,
    usuario: Usuario = Depends(get_usuario),
    repo: SupabaseRepo = Depends(get_repo),
):
    alvo = setor_efetivo(usuario, setor)
    params = {"select": "id,setor,titulo,quantidade", "order": "titulo.asc"}
    if alvo:
        params["setor"] = f"eq.{alvo}"
    return repo.select("documentos_pendentes", params)


@router.get("/ranking", tags=["Dashboard"])
def ranking(
    setor: str | None = None,
    inicio: date | None = None,
    fim: date | None = None,
    ordem: str = Query("asc", pattern="^(asc|desc)$"),
    usuario: Usuario = Depends(get_usuario),
    repo: SupabaseRepo = Depends(get_repo),
):
    ini, fim_excl = services.periodo_do_mes(hoje())
    if inicio and fim:
        if fim < inicio:
            raise HTTPException(400, "'fim' não pode ser anterior a 'inicio'.")
        ini = inicio.isoformat()
        fim_excl = date.fromordinal(fim.toordinal() + 1).isoformat()
    alvo = setor_efetivo(usuario, setor)
    return {"setor": alvo, "inicio": ini, "fim_exclusivo": fim_excl, "ordem": ordem,
            "itens": services.ranking(repo, alvo, ini, fim_excl, ordem)}


@router.get("/painel", tags=["Dashboard"])
def painel(
    usuario: Usuario = Depends(get_usuario),
    repo: SupabaseRepo = Depends(get_repo),
):
    exigir_perfis(usuario, TODOS)
    alvo = setor_efetivo(usuario, None)
    ini, fim = services.periodo_do_mes(hoje())
    membros = services.membros_ativos(repo, alvo)
    soma = services.pontos_por_membro(repo, ini, fim)
    por_setor: dict[str, dict] = defaultdict(
        lambda: {"membros": 0, "pontos": 0})
    for m in membros:
        por_setor[m["setor"]]["membros"] += 1
        por_setor[m["setor"]]["pontos"] += soma.get(m["id"], 0)
    total = sum(v["pontos"] for v in por_setor.values())
    params = {"select": "id"}
    if alvo:
        params["setor"] = f"eq.{alvo}"
    projetos = repo.select("projetos", params)
    return {
        "setor": alvo,
        "membros_ativos": len(membros),
        "projetos": len(projetos),
        "pontos_no_mes": total,
        "horas_no_mes": services.horas(total),
        "por_setor": [{"setor": s, **v, "horas": services.horas(v["pontos"])}
                      for s, v in sorted(por_setor.items())],
    }


@router.get("/membros/{membro_id}/desempenho", tags=["Membros"])
def desempenho(
    membro_id: str,
    meses: int = Query(6, ge=1, le=24),
    usuario: Usuario = Depends(get_usuario),
    repo: SupabaseRepo = Depends(get_repo),
):
    """Pontos por mês e projetos de um membro (tela de detalhe, só leitura)."""
    achados = repo.select(
        "members", {"select": "id,nome,cargo,setor,ativo", "id": f"eq.{membro_id}"})
    if not achados:
        raise HTTPException(404, "Membro não encontrado.")
    m = achados[0]
    if usuario.restrito_em_membros and m["setor"] != usuario.setor:
        raise HTTPException(403, "Este membro é de outro setor.")
    atividades = repo.select(
        "atividades", {"select": "data,pontos", "member_id": f"eq.{membro_id}"})
    por_mes: dict[str, int] = defaultdict(int)
    for a in atividades:
        por_mes[a["data"][:7]] += a["pontos"]
    ultimos = sorted(por_mes.items(), reverse=True)[:meses]
    vinculos = repo.select("projeto_membros", {
                           "select": "project_id", "member_id": f"eq.{membro_id}"})
    projetos = []
    if vinculos:
        ids = ",".join(v["project_id"] for v in vinculos)
        projetos = repo.select(
            "projetos", {"select": "id,nome,total_pontos", "id": f"in.({ids})"})
    total = sum(por_mes.values())
    return {
        "membro": m,
        "total_pontos": total,
        "total_horas": services.horas(total),
        "pontos_por_mes": [{"mes": k, "pontos": v, "horas": services.horas(v)}
                           for k, v in sorted(ultimos)],
        "projetos": projetos,
    }
