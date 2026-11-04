from .conftest import auth


def test_health_sem_login(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_sem_token_401(client):
    assert client.get("/v1/painel").status_code == 401


def test_token_invalido_401(client):
    r = client.get("/v1/painel", headers={"Authorization": "Bearer lixo"})
    assert r.status_code == 401


def test_usuario_sem_perfil_403(client):
    assert client.get("/v1/painel", headers=auth("semperfil")).status_code == 403


def test_ranking_rh_ordem_crescente_e_so_ativos(client):
    r = client.get("/v1/ranking", headers=auth("rh")).json()
    nomes = [i["nome"] for i in r["itens"]]
    assert nomes == ["Bia", "Ana"]       
    assert r["itens"][1]["pontos"] == 120    
    assert r["itens"][1]["horas"] == 2.0    


def test_ranking_gestor_nao_escapa_do_proprio_setor(client):
    r = client.get("/v1/ranking?setor=Projetos", headers=auth("rh")).json()
    assert r["setor"] == "RH"
    assert all(i["setor"] == "RH" for i in r["itens"])


def test_ranking_presidente_filtra_setor_e_ordem_desc(client):
    r = client.get("/v1/ranking?setor=RH&ordem=desc", headers=auth("pres")).json()
    assert [i["nome"] for i in r["itens"]] == ["Ana", "Bia"]
    todos = client.get("/v1/ranking", headers=auth("pres")).json()
    assert {i["setor"] for i in todos["itens"]} == {"RH", "Projetos"}


def test_ranking_intervalo_personalizado(client):
    r = client.get("/v1/ranking?inicio=2026-10-01&fim=2026-10-31", headers=auth("pres")).json()
    pontos = {i["nome"]: i["pontos"] for i in r["itens"]}
    assert pontos["Ana"] == 60


def test_ranking_intervalo_invalido(client):
    r = client.get("/v1/ranking?inicio=2026-11-10&fim=2026-11-01", headers=auth("pres"))
    assert r.status_code == 400


def test_painel_presidente_ve_tudo(client):
    p = client.get("/v1/painel", headers=auth("pres")).json()
    assert p["membros_ativos"] == 3
    assert p["projetos"] == 2
    assert p["pontos_no_mes"] == 120 + 30 + 90
    assert {s["setor"] for s in p["por_setor"]} == {"RH", "Projetos"}


def test_painel_gestor_so_o_setor(client):
    p = client.get("/v1/painel", headers=auth("rh")).json()
    assert p["setor"] == "RH" and p["membros_ativos"] == 2 and p["projetos"] == 1


def test_documentos_pendentes_por_setor(client):
    r = client.get("/v1/documentos-pendentes", headers=auth("proj")).json()
    assert [d["titulo"] for d in r] == ["Termos de encerramento"]
    todos = client.get("/v1/documentos-pendentes", headers=auth("ori")).json()
    assert len(todos) == 2


def test_notificacoes_inclui_feriado_proximo_e_avisos_do_setor(client):
    r = client.get("/v1/notificacoes", headers=auth("rh")).json()
    titulos = [i["titulo"] for i in r["itens"]]
    assert "Proclamação da República" in titulos      # 15/11 está a 5 dias de 10/11
    assert "Natal" not in titulos                     # fora da janela de 14 dias
    assert "Só RH" in titulos and "Geral" in titulos
    assert "Só Projetos" not in titulos
    feriado = next(i for i in r["itens"] if i["tipo"] == "feriado")
    assert "5 dia" in feriado["mensagem"]


def test_notificacoes_presidente_ve_todos_os_avisos(client):
    titulos = [i["titulo"] for i in client.get("/v1/notificacoes", headers=auth("pres")).json()["itens"]]
    assert {"Só RH", "Só Projetos", "Geral"} <= set(titulos)


def test_feriados_proximos_atravessa_o_ano(client, monkeypatch):
    from datetime import date
    from app import routes
    monkeypatch.setattr(routes, "hoje", lambda: date(2026, 12, 20))
    r = client.get("/v1/feriados/proximos?dias=20", headers=auth("rh")).json()
    assert [f["nome"] for f in r] == ["Natal", "Confraternização Universal"]


def test_feriados_ano_invalido(client):
    assert client.get("/v1/feriados/1800", headers=auth("rh")).status_code == 400
    assert len(client.get("/v1/feriados/2026", headers=auth("rh")).json()) == 3


def test_desempenho_membro(client):
    r = client.get("/v1/membros/m1/desempenho", headers=auth("rh")).json()
    assert r["total_pontos"] == 180 and r["total_horas"] == 3.0
    assert [m["mes"] for m in r["pontos_por_mes"]] == ["2026-10", "2026-11"]
    assert r["projetos"][0]["nome"] == "Feira"


def test_desempenho_gestor_de_projetos_so_ve_o_proprio_setor(client):
    assert client.get("/v1/membros/m1/desempenho", headers=auth("proj")).status_code == 403  # membro de RH
    assert client.get("/v1/membros/m4/desempenho", headers=auth("proj")).status_code == 200


def test_desempenho_rh_e_presidente_veem_qualquer_membro(client):
    assert client.get("/v1/membros/m4/desempenho", headers=auth("rh")).status_code == 200
    assert client.get("/v1/membros/m4/desempenho", headers=auth("pres")).status_code == 200
    assert client.get("/v1/membros/zzz/desempenho", headers=auth("pres")).status_code == 404
