# FluEJ API

API de **consulta** (somente `GET`) do app Android FluEJ. Ela lê os dados do Supabase, aplica as regras de
negócio no servidor (ranking, horas, permissões por perfil) e entrega JSON pronto para o app consumir com Retrofit.

> **Regra do projeto:** nenhuma rota desta API cadastra ou atualiza dados. Cadastro, inativação, login e
> sincronização continuam no app, direto no Supabase. A API só **consulta**.

## Como ela se encaixa

```
App Android ── Retrofit (GET) ──────────► FluEJ API ──► Supabase (leitura)
     │                                       ▲
     └── supabase-kt (login, cadastro,       │ valida o token que o app já recebeu no login
         atualização, sincronização) ──► Supabase
```

- **Login:** continua sendo o do Supabase. O app envia o token em cada chamada (`Authorization: Bearer <token>`).
- **Permissões:** a API descobre o perfil do usuário na tabela `perfis` e decide o que ele pode ver.
- **Feriados:** vêm da [BrasilAPI](https://brasilapi.com.br) (`/api/feriados/v1/{ano}`), com cache de 24 h em memória.

## Estrutura

```
fluej-api/
├── app/
│   ├── main.py        # cria o app e registra as rotas (+ /health)
│   ├── routes.py      # todos os endpoints
│   ├── deps.py        # quem é o usuário e o que ele pode ver
│   ├── security.py    # validação do token (JWT) do Supabase
│   ├── services.py    # regras de negócio (ranking, 60 pontos = 1 hora)
│   ├── holidays.py    # feriados nacionais (BrasilAPI + cache)
│   ├── db.py          # leitura das tabelas do Supabase (somente GET)
│   └── config.py      # variáveis de ambiente
├── sql/001_tabelas_da_api.sql   # tabelas novas (avisos, documentos_pendentes)
├── tests/             # testes automatizados (pytest)
├── docs/INTEGRACAO_ANDROID.md   # como consumir no app (Retrofit)
├── Dockerfile
├── .env.example
└── requirements.txt / requirements-dev.txt
```

## Passo a passo para rodar

1. **Python 3.11 ou superior.** Crie o ambiente e instale:
   ```bash
   python -m venv .venv
   # Windows: .venv\Scripts\activate      Linux/macOS: source .venv/bin/activate
   pip install -r requirements-dev.txt
   ```
2. **Tabelas novas.** No Supabase → SQL Editor, rode `sql/001_tabelas_da_api.sql`.
   Ele cria `avisos` e `documentos_pendentes` (com RLS ligado e sem políticas: só a API lê).
3. **Variáveis de ambiente.** Copie `.env.example` para `.env` e preencha:
   | Variável | Para quê |
   |---|---|
   | `SUPABASE_URL` | `https://SEU-PROJETO.supabase.co` |
   | `SUPABASE_SERVICE_KEY` | chave **secret / service_role** (Project Settings → API Keys). **Só no servidor.** |
   | `SUPABASE_JWT_SECRET` | opcional: só se o seu projeto ainda assina tokens com HS256 |
   | `DIAS_AVISO_FERIADO` | janela, em dias, para avisar feriados nas notificações (padrão 14) |

   > Nunca coloque a chave `secret` no app Android nem no Git. O `.env` já está no `.gitignore`.
4. **Subir a API** (carregando o `.env`):
   ```bash
   # Linux/macOS
   export $(grep -v '^#' .env | xargs) && uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
   # Windows (PowerShell): defina cada variável com  $env:NOME="valor"  e depois:
   uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
   ```
5. **Conferir.** `http://localhost:8000/health` deve responder `{"status":"ok"}`, e a documentação
   interativa (Swagger) fica em `http://localhost:8000/docs`.
6. **Testar com um token real.** Faça login no Supabase com um dos usuários de teste e use o `access_token`:
   ```bash
   curl http://localhost:8000/v1/painel -H "Authorization: Bearer SEU_TOKEN"
   ```
   Use `curl`, Postman ou Insomnia com o cabeçalho acima.

### Qual algoritmo de token o seu projeto usa?

A API aceita os dois formatos do Supabase:
- **Chaves assimétricas (ES256/RS256), o padrão atual:** a API busca a chave pública em
  `{SUPABASE_URL}/auth/v1/.well-known/jwks.json`. Não precisa de segredo.
- **HS256 (projetos antigos):** preencha `SUPABASE_JWT_SECRET`.

Para saber qual é o seu, veja em Project Settings → JWT Keys no painel do Supabase.

## Autenticação e permissões

Toda rota (exceto `/health`) exige `Authorization: Bearer <access_token do Supabase>`.

| Situação | Resposta |
|---|---|
| Sem cabeçalho, token inválido ou expirado | `401` |
| Token válido, mas o usuário não tem linha em `perfis` | `403` |
| Perfil sem permissão para o recurso | `403` |

Regra de visibilidade por perfil:

| Perfil | Painel, ranking, documentos e avisos | Detalhe de um membro (`/desempenho`) |
|---|---|---|
| `rh` | só o setor **RH** | **qualquer** membro |
| `projetos`, `comercial`, `financeiro` | só o **próprio setor** | só membros do próprio setor |
| `presidente`, `orientador` | **todos** os setores (podem filtrar com `?setor=`) | qualquer membro |

Para gestores de setor, o parâmetro `?setor=` é **ignorado**: a API sempre devolve o setor do próprio usuário.
Isso vale no servidor, então não depende do app.

## Endpoints

Todas as rotas ficam sob `/v1`. Todas são `GET`. Respostas de erro seguem o formato `{"detail": "mensagem"}`.

| Rota | Quem usa no app | Situação no app |
|---|---|---|
| `GET /health` | teste de disponibilidade | — |
| `GET /v1/notificacoes` | sino do dashboard | **usado** (avisos + feriados próximos) |
| `GET /v1/documentos-pendentes` | card "Documentos pendentes" | **usado** (substitui o mock) |
| `GET /v1/feriados/proximos` | notificações / calendário | disponível |
| `GET /v1/feriados/{ano}` | calendário de feriados | tela futura |
| `GET /v1/painel` | dashboards de Presidente e Orientador | tela futura |
| `GET /v1/ranking` | ranking geral entre setores | tela futura |
| `GET /v1/membros/{id}/desempenho` | detalhe do membro (Membros / Pontos) | tela futura |

Regra de horas em todas as rotas: **60 pontos = 1 hora** (`horas = pontos / 60`, 2 casas).

### `GET /health`
Sem autenticação.
```json
{ "status": "ok" }
```

### `GET /v1/notificacoes`
Alimenta o sino. Junta **avisos** (tabela `avisos`, do setor do usuário ou gerais, ainda não expirados, do mais
novo para o mais antigo) e **feriados nacionais** que acontecem nos próximos `DIAS_AVISO_FERIADO` dias.
```json
{
  "total": 2,
  "itens": [
    { "id": "6f0c…", "tipo": "aviso", "titulo": "Reunião geral",
      "mensagem": "Sexta-feira, às 14h, na sala 3.", "data": "2026-11-02" },
    { "id": "feriado-2026-11-15", "tipo": "feriado", "titulo": "Proclamação da República",
      "mensagem": "Feriado nacional em 12 dia(s).", "data": "2026-11-15" }
  ]
}
```
`tipo` é `"aviso"` ou `"feriado"`. `data` está em `yyyy-MM-dd`.

### `GET /v1/documentos-pendentes`
Parâmetro opcional: `setor` (só vale para Presidente e Orientador).
```json
[
  { "id": "a1…", "setor": "RH", "titulo": "Termos de voluntariado", "quantidade": 2 },
  { "id": "b2…", "setor": "RH", "titulo": "Termos de encerramento", "quantidade": 5 }
]
```

### `GET /v1/feriados/proximos?dias=30`
`dias`: de 1 a 366 (padrão 30). Atravessa a virada do ano.
```json
[ { "data": "2026-11-15", "nome": "Proclamação da República", "tipo": "national", "faltam_dias": 12 } ]
```

### `GET /v1/feriados/{ano}`
Ano de 2000 a 2100 (`400` fora disso). `502` se a BrasilAPI estiver fora do ar e não houver cache.
```json
[ { "data": "2026-01-01", "nome": "Confraternização mundial", "tipo": "national" } ]
```

### `GET /v1/painel`
Números do **mês atual** apenas de membros **ativos**.
```json
{
  "setor": null,
  "membros_ativos": 42,
  "projetos": 7,
  "pontos_no_mes": 3180,
  "horas_no_mes": 53.0,
  "por_setor": [
    { "setor": "Projetos", "membros": 12, "pontos": 1210, "horas": 20.17 },
    { "setor": "RH",       "membros": 8,  "pontos": 940,  "horas": 15.67 }
  ]
}
```
`setor` vem preenchido quando o usuário é gestor de setor.

### `GET /v1/ranking`
Ranking de pontos de membros **ativos**.

| Parâmetro | Padrão | Descrição |
|---|---|---|
| `setor` | — | só Presidente/Orientador |
| `inicio`, `fim` | mês atual | `yyyy-MM-dd`, inclusivos. `400` se `fim < inicio` |
| `ordem` | `asc` | `asc` (menor → maior, como no dashboard do app) ou `desc` |

```json
{
  "setor": "RH", "inicio": "2026-11-01", "fim_exclusivo": "2026-12-01", "ordem": "asc",
  "itens": [
    { "membro_id": "…", "nome": "Bia", "cargo": "Gerente", "setor": "RH", "pontos": 30, "horas": 0.5 },
    { "membro_id": "…", "nome": "Ana", "cargo": "Assessor", "setor": "RH", "pontos": 120, "horas": 2.0 }
  ]
}
```

### `GET /v1/membros/{membro_id}/desempenho?meses=6`
`meses`: de 1 a 24 (padrão 6). `404` se o membro não existir, `403` se for de outro setor (só para
Projetos/Comercial/Financeiro). Traz o total, os pontos por mês (mais antigos primeiro) e os projetos do membro.
```json
{
  "membro": { "id": "…", "nome": "Ana", "cargo": "Assessor", "setor": "RH", "ativo": true },
  "total_pontos": 180, "total_horas": 3.0,
  "pontos_por_mes": [ { "mes": "2026-10", "pontos": 60, "horas": 1.0 },
                      { "mes": "2026-11", "pontos": 120, "horas": 2.0 } ],
  "projetos": [ { "id": "…", "nome": "Feira", "total_pontos": 100 } ]
}
```

## Tabelas que a API lê

| Tabela | Origem |
|---|---|
| `members`, `atividades`, `projetos`, `projeto_membros`, `perfis` | já existem (criadas para o app) |
| `avisos`, `documentos_pendentes` | novas, criadas por `sql/001_tabelas_da_api.sql` |

Como o app **não tem telas de cadastro** para `avisos` e `documentos_pendentes`, você preenche essas duas pelo
Table Editor do Supabase. Exemplo de aviso só para o RH: `setor = 'RH'`. Aviso geral: `setor` vazio.
`expira_em` vazio = não expira.

## Testes

```bash
pytest
```
- `tests/test_api.py`: rotas, permissões por perfil, avisos + feriados, ranking, painel, desempenho.
  Usa um banco de mentira e feriados de mentira (sem rede).
- `tests/test_security.py`: valida o token com uma chave ES256 gerada na hora (válido, expirado, audiência
  errada, assinatura de outra chave).

## Publicar (deploy)

1. Suba o repositório no GitHub.
2. Num serviço como Render, Railway ou Cloud Run, crie um serviço web a partir do repositório:
   - **Build:** `pip install -r requirements.txt` (ou use o `Dockerfile`).
   - **Start:** `uvicorn app.main:app --host 0.0.0.0 --port $PORT`.
3. Cadastre as variáveis do `.env` no painel do serviço (nunca no código).
4. Teste `https://SEU-SERVICO/health` e troque a `BASE_URL` do app para esse endereço (com `https`).

Planos gratuitos costumam "dormir" quando ficam sem uso; a primeira chamada depois disso pode levar
dezenas de segundos. O app já usa timeout longo e mostra o último dado salvo enquanto espera.

## Segurança

- A chave `service_role` ignora o RLS: ela fica **só** nas variáveis de ambiente do servidor. Se vazar,
  gere outra no painel do Supabase.
- Use sempre HTTPS em produção. O `http://` só serve para desenvolvimento.
- A API valida assinatura, validade e audiência do token a cada chamada.
- Ideias para depois: limite de requisições por usuário, logs sem dados pessoais, e migrar as políticas do
  Supabase (hoje abertas a qualquer usuário logado) para políticas por perfil e setor.

## Integração com o app

Veja `docs/INTEGRACAO_ANDROID.md` (Retrofit, cache no Room, sino de notificações e documentos pendentes).
