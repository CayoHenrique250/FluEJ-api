# FluEJ API

API usada pelo aplicativo Android FluEJ para consultar informações do sistema. O backend reúne dados do Supabase, aplica as regras de acesso por perfil e devolve respostas JSON para o aplicativo.

A API é **somente leitura**: todas as rotas de negócio usam `GET`. Login, cadastro, edição, inativação de membros, registro de atividades e sincronização continuam sendo feitos pelo aplicativo diretamente no Supabase.

## 1. Para que serve

O aplicativo usa a API quando precisa apresentar informações que dependem de consultas combinadas ou de regras centralizadas no servidor. Atualmente, ela atende a estas funções:

- notificações: avisos cadastrados pela equipe e feriados nacionais próximos;
- documentos pendentes: quantidade de documentos por setor;
- painel: números do mês, membros ativos e projetos;
- ranking: pontuação dos membros ativos em um período;
- desempenho: histórico de pontos e projetos associados a um membro;
- feriados: consulta dos feriados nacionais de um ano ou dos próximos dias.

O backend consulta o Supabase. Para feriados nacionais, consulta também a BrasilAPI e mantém um cache em memória por até 24 horas.

## 2. Endereço e documentação interativa

A URL de produção configurada atualmente no aplicativo é:

```text
https://fluej-api.onrender.com/
```

Os endereços principais da documentação automática do FastAPI são:

| Endereço | Finalidade |
|---|---|
| `/health` | Verificar se o serviço está respondendo. |
| `/docs` | Abrir a documentação interativa (Swagger UI). |
| `/openapi.json` | Consultar a especificação OpenAPI gerada pelo FastAPI. |

Em desenvolvimento, substitua a URL de produção por `http://127.0.0.1:8000/`.

> A barra `/` no final da `BASE_URL` é necessária para o Retrofit.

## 3. Como autenticar uma chamada

Todas as rotas sob `/v1` exigem um access token válido emitido pelo Supabase. A única exceção é `GET /health`.

O aplicativo faz login pelo Supabase e envia o token recebido em cada chamada à API no cabeçalho:

```http
Authorization: Bearer ACCESS_TOKEN_DO_SUPABASE
```

Não use a `SUPABASE_SERVICE_KEY` como token do aplicativo. São credenciais diferentes:

- **Access token:** pertence ao usuário que fez login. É enviado pelo Android para identificar o usuário.
- **SUPABASE_SERVICE_KEY:** chave secreta usada exclusivamente pelo backend para consultar o banco. Nunca deve ser incluída no aplicativo, no Git ou em uma captura de tela.

Depois de validar o token, a API lê o perfil correspondente na tabela `perfis`. O perfil precisa ser um destes valores, escritos em minúsculas: `presidente`, `rh`, `projetos`, `comercial`, `financeiro` ou `orientador`.

### Exemplo rápido com PowerShell

```powershell
$base = "https://fluej-api.onrender.com"
$token = "COLE_AQUI_UM_ACCESS_TOKEN_VALIDO"
$headers = @{ Authorization = "Bearer $token" }

Invoke-RestMethod -Method Get `
  -Uri "$base/v1/notificacoes" `
  -Headers $headers
```

### Exemplo com curl

```bash
BASE_URL="https://fluej-api.onrender.com"
ACCESS_TOKEN="COLE_AQUI_UM_ACCESS_TOKEN_VALIDO"

curl -i "$BASE_URL/v1/notificacoes" \
  -H "Authorization: Bearer $ACCESS_TOKEN"
```

Use um token obtido por meio do login normal do aplicativo ou de um cliente de teste autorizado. Não coloque tokens reais em arquivos versionados.

## 4. Perfis e limites de acesso

A API aplica as permissões no backend. Não basta esconder um botão no Android: o servidor também verifica o perfil e, quando necessário, limita os dados ao setor do usuário.

| Perfil | Painel, ranking e documentos | Avisos | Desempenho de membros |
|---|---|---|---|
| `rh` | Somente RH | RH e avisos gerais | Qualquer setor |
| `projetos` | Somente Projetos | Projetos e avisos gerais | Somente Projetos |
| `comercial` | Somente Comercial | Comercial e avisos gerais | Somente Comercial |
| `financeiro` | Somente Financeiro | Financeiro e avisos gerais | Somente Financeiro |
| `presidente` | Todos os setores; pode filtrar | Todos os setores e avisos gerais | Qualquer setor |
| `orientador` | Todos os setores; pode filtrar | Todos os setores e avisos gerais | Qualquer setor |

Para os perfis de gestor (`rh`, `projetos`, `comercial` e `financeiro`), a regra esperada é usar o setor cadastrado na tabela `perfis`. Quando esse campo está preenchido, o parâmetro `setor` não permite que o gestor consulte outro setor.

> **Atenção: ajuste de segurança pendente no código atual.** Se um perfil restrito estiver com `setor` vazio, `setor_efetivo()` retorna `None`. Como as rotas aplicam o filtro apenas quando `alvo` tem valor, esse cadastro pode acabar consultando dados de todos os setores. Antes de considerar essa regra concluída, valide em `get_usuario()` que os perfis `rh`, `projetos`, `comercial` e `financeiro` sempre tenham `setor` preenchido; caso contrário, retorne `403` e não execute a consulta.

## 5. Endpoints disponíveis

Todas as rotas abaixo usam o método `GET`. Exceto `/health`, exigem o cabeçalho `Authorization` descrito na seção 3.

### 5.1 `GET /health`

Verifica se o processo da API está no ar. Não testa a conexão com o Supabase nem a disponibilidade da BrasilAPI. Não exige token.

**Exemplo:**

```bash
curl -i https://fluej-api.onrender.com/health
```

**Resposta:**

```json
{
  "status": "ok"
}
```

### 5.2 `GET /v1/notificacoes`

**Para que serve:** alimentar o sino de notificações do aplicativo.

A resposta reúne:

1. avisos não expirados da tabela `avisos`;
2. feriados nacionais que ocorrerão dentro da janela configurada em `DIAS_AVISO_FERIADO`.

Um aviso com `setor = null` é geral. Um aviso com `setor = "RH"`, por exemplo, só aparece para quem pode visualizar o RH. Avisos expirados não são retornados. Os avisos são ordenados do mais recente para o mais antigo; os feriados são acrescentados à lista.

**Parâmetros:** nenhum.

**Exemplo de chamada:**

```bash
curl "https://fluej-api.onrender.com/v1/notificacoes" \
  -H "Authorization: Bearer $ACCESS_TOKEN"
```

**Exemplo de resposta:**

```json
{
  "total": 2,
  "itens": [
    {
      "id": "6f0c0000-0000-0000-0000-000000000001",
      "tipo": "aviso",
      "titulo": "Reunião geral",
      "mensagem": "Sexta-feira, às 14h, na sala 3.",
      "data": "2026-11-06"
    },
    {
      "id": "feriado-2026-11-15",
      "tipo": "feriado",
      "titulo": "Proclamação da República",
      "mensagem": "Feriado nacional em 11 dia(s).",
      "data": "2026-11-15"
    }
  ]
}
```

O campo `tipo` identifica se o item é `aviso` ou `feriado`. O campo `data` usa o formato `AAAA-MM-DD`.

### 5.3 `GET /v1/documentos-pendentes`

**Para que serve:** mostrar quantos documentos de cada tipo ainda estão pendentes em cada setor.

**Parâmetro opcional:**

| Parâmetro | Exemplo | Quem pode escolher o setor |
|---|---|---|
| `setor` | `?setor=RH` | `presidente` e `orientador` |

Gestores de setor recebem somente os documentos do próprio setor, mesmo que tentem enviar outro valor em `setor`. Presidente e Orientador podem consultar todos os setores ou filtrar um setor específico.

**Exemplo para consultar o RH:**

```bash
curl "https://fluej-api.onrender.com/v1/documentos-pendentes?setor=RH" \
  -H "Authorization: Bearer $ACCESS_TOKEN"
```

**Exemplo de resposta:**

```json
[
  {
    "id": "a1",
    "setor": "RH",
    "titulo": "Termos de voluntariado",
    "quantidade": 2
  },
  {
    "id": "a2",
    "setor": "RH",
    "titulo": "Termos de encerramento",
    "quantidade": 5
  }
]
```

A lista vem ordenada pelo título. Os dados são mantidos na tabela `documentos_pendentes` do Supabase.

### 5.4 `GET /v1/feriados/proximos`

**Para que serve:** consultar feriados nacionais a partir da data atual, para exibição no calendário ou em outra área do aplicativo.

**Parâmetro:**

| Parâmetro | Padrão | Limites | Descrição |
|---|---:|---:|---|
| `dias` | `30` | 1 a 366 | Quantos dias à frente devem ser consultados. |

A consulta considera a virada do ano quando o período solicitado alcança janeiro do ano seguinte.

**Exemplo:**

```bash
curl "https://fluej-api.onrender.com/v1/feriados/proximos?dias=45" \
  -H "Authorization: Bearer $ACCESS_TOKEN"
```

**Exemplo de resposta:**

```json
[
  {
    "data": "2026-11-15",
    "nome": "Proclamação da República",
    "tipo": "national",
    "faltam_dias": 11
  }
]
```

### 5.5 `GET /v1/feriados/{ano}`

**Para que serve:** retornar os feriados nacionais de um ano específico.

**Parâmetro de caminho:** `ano`, entre 2000 e 2100.

**Exemplo:**

```bash
curl "https://fluej-api.onrender.com/v1/feriados/2027" \
  -H "Authorization: Bearer $ACCESS_TOKEN"
```

**Exemplo de resposta:**

```json
[
  {
    "data": "2027-01-01",
    "nome": "Confraternização Universal",
    "tipo": "national"
  }
]
```

Os dados vêm da BrasilAPI. A API mantém os resultados em cache na memória por até 24 horas. Se a consulta externa falhar e houver uma cópia anterior em cache, essa cópia pode ser usada. Sem resposta externa e sem cache disponível, a rota retorna `502`.

### 5.6 `GET /v1/painel`

**Para que serve:** fornecer os indicadores usados em um dashboard: quantidade de membros ativos, quantidade de projetos e pontuação acumulada no mês.

O período é o mês atual. A contagem de membros considera somente membros ativos. A pontuação é convertida em horas pela regra do projeto: **60 pontos equivalem a 1 hora**.

**Parâmetros:** nenhum.

**Exemplo:**

```bash
curl "https://fluej-api.onrender.com/v1/painel" \
  -H "Authorization: Bearer $ACCESS_TOKEN"
```

**Exemplo de resposta:**

```json
{
  "setor": "RH",
  "membros_ativos": 8,
  "projetos": 2,
  "pontos_no_mes": 940,
  "horas_no_mes": 15.67,
  "por_setor": [
    {
      "setor": "RH",
      "membros": 8,
      "pontos": 940,
      "horas": 15.67
    }
  ]
}
```

Para Presidente e Orientador, `setor` pode ser `null` e `por_setor` pode conter vários setores. Para gestores com o campo `setor` preenchido, os números ficam limitados ao setor cadastrado. Consulte o alerta de segurança da seção 4 sobre perfis sem setor.

### 5.7 `GET /v1/ranking`

**Para que serve:** listar os membros ativos em ordem de pontuação dentro de um período.

**Parâmetros:**

| Parâmetro | Padrão | Descrição |
|---|---|---|
| `setor` | sem filtro | Presidente e Orientador podem escolher um setor. Gestores ficam limitados ao próprio setor. |
| `inicio` | primeiro dia do mês atual | Data inicial no formato `AAAA-MM-DD`. |
| `fim` | último dia do mês atual | Data final no formato `AAAA-MM-DD`; é inclusiva. |
| `ordem` | `asc` | `asc` ordena da menor para a maior pontuação; `desc`, da maior para a menor. |

Para consultar um período personalizado, informe **`inicio` e `fim` juntos**. O código atual só aplica o período personalizado quando os dois são enviados. Se apenas um for informado, a implementação atual usa o mês corrente; esse comportamento deve ser ajustado para retornar `400` em vez de ignorar silenciosamente o parâmetro.

**Exemplo:**

```bash
curl "https://fluej-api.onrender.com/v1/ranking?inicio=2026-10-01&fim=2026-10-31&ordem=desc" \
  -H "Authorization: Bearer $ACCESS_TOKEN"
```

**Exemplo de resposta:**

```json
{
  "setor": "RH",
  "inicio": "2026-10-01",
  "fim_exclusivo": "2026-11-01",
  "ordem": "desc",
  "itens": [
    {
      "membro_id": "m1",
      "nome": "Ana",
      "cargo": "Assessora",
      "setor": "RH",
      "pontos": 120,
      "horas": 2.0
    },
    {
      "membro_id": "m2",
      "nome": "Bia",
      "cargo": "Gerente",
      "setor": "RH",
      "pontos": 60,
      "horas": 1.0
    }
  ]
}
```

A resposta informa `fim_exclusivo`, que é o dia seguinte ao `fim` recebido. Isso permite que a consulta ao banco use o intervalo `data >= inicio` e `data < fim_exclusivo`, incluindo todo o último dia solicitado.

Membros ativos sem atividades no período também aparecem, com `pontos` e `horas` iguais a zero.

### 5.8 `GET /v1/membros/{membro_id}/desempenho`

**Para que serve:** abrir o histórico de um membro, com total de pontos, conversão em horas, pontos agrupados por mês e projetos aos quais ele está vinculado.

**Parâmetros:**

| Parâmetro | Tipo | Padrão | Limites |
|---|---|---:|---|
| `membro_id` | caminho | — | ID do membro na tabela `members`. |
| `meses` | consulta | `6` | 1 a 24 meses com registros. |

O campo `pontos_por_mes` retorna os meses mais recentes que possuem atividades, em ordem cronológica. Já `total_pontos` e `total_horas` representam a soma de todo o histórico de atividades encontrado para o membro, não apenas dos meses exibidos na lista.

RH, Presidente e Orientador podem consultar membros de qualquer setor. Gestores de Projetos, Comercial e Financeiro só podem consultar membros do próprio setor.

**Exemplo:**

```bash
curl "https://fluej-api.onrender.com/v1/membros/ID_DO_MEMBRO/desempenho?meses=6" \
  -H "Authorization: Bearer $ACCESS_TOKEN"
```

**Exemplo de resposta:**

```json
{
  "membro": {
    "id": "m1",
    "nome": "Ana",
    "cargo": "Assessora",
    "setor": "RH",
    "ativo": true
  },
  "total_pontos": 180,
  "total_horas": 3.0,
  "pontos_por_mes": [
    {
      "mes": "2026-10",
      "pontos": 60,
      "horas": 1.0
    },
    {
      "mes": "2026-11",
      "pontos": 120,
      "horas": 2.0
    }
  ],
  "projetos": [
    {
      "id": "p1",
      "nome": "Feira",
      "total_pontos": 100
    }
  ]
}
```

A rota retorna `404` quando o membro não existe e `403` quando um gestor restrito tenta consultar alguém de outro setor.

## 6. Códigos de resposta e erros

| Código | Significado nesta API | O que conferir |
|---|---|---|
| `200` | Consulta concluída. | Ler o JSON retornado. |
| `400` | Parâmetro inválido, como ano fora do intervalo ou período com `fim` anterior a `inicio`. | Corrigir os parâmetros da URL. |
| `401` | Cabeçalho ausente, token inválido/expirado ou token sem `sub`. | Fazer login novamente e enviar o access token do usuário. |
| `403` | Usuário autenticado sem perfil cadastrado/autorizado ou sem permissão para aquele membro. | Conferir `auth.users`, tabela `perfis`, perfil e setor. |
| `404` | Membro solicitado não encontrado. | Conferir o ID enviado no caminho. |
| `500` | Configuração interna ausente ou inválida. | Conferir variáveis de ambiente do serviço. |
| `502` | Falha ao consultar o Supabase ou a BrasilAPI, conforme a rota. | Conferir logs do Render, credenciais e disponibilidade do serviço externo. |

As respostas de erro do FastAPI normalmente vêm neste formato:

```json
{
  "detail": "Descrição do erro"
}
```

No caso de `403`, diferencie a mensagem de usuário sem perfil da mensagem de usuário sem acesso ao membro. Ambas significam acesso negado, mas têm causas diferentes.

## 7. Tabelas consultadas no Supabase

A API lê as seguintes tabelas:

| Tabela | Uso |
|---|---|
| `perfis` | Relacionar o usuário autenticado ao perfil, setor e nome. |
| `members` | Consultar membros, setor, cargo e situação de atividade. |
| `atividades` | Somar pontos por membro e período. |
| `projetos` | Contar projetos e apresentar os projetos vinculados a um membro. |
| `projeto_membros` | Localizar os projetos associados ao membro. |
| `avisos` | Montar as notificações gerais e por setor. |
| `documentos_pendentes` | Mostrar a quantidade pendente por tipo de documento e setor. |

As tabelas `avisos` e `documentos_pendentes` são criadas pelo script `sql/001_tabelas_da_api.sql`. O aplicativo não cadastra esses registros pela API; o gerenciamento é feito pelo painel do Supabase.

### Como cadastrar um aviso

No Table Editor do Supabase, crie uma linha na tabela `avisos`:

| Campo | Exemplo | Significado |
|---|---|---|
| `titulo` | `Reunião de equipe` | Texto do título. |
| `mensagem` | `Reunião na sexta-feira, às 14h.` | Texto exibido ao abrir a notificação. |
| `setor` | `RH` | Setor que recebe o aviso. Deixe `NULL` para todos. |
| `expira_em` | `2026-12-01 23:59:00+00` | Data/hora em que deixa de aparecer. Deixe `NULL` para não expirar. |

`criado_em` é preenchido automaticamente pelo banco.

### Como atualizar documentos pendentes

Na tabela `documentos_pendentes`, mantenha uma linha por combinação de setor e tipo de documento. Por exemplo:

| setor | titulo | quantidade |
|---|---|---:|
| RH | Termos de voluntariado | 2 |
| RH | Termos de encerramento | 5 |
| Projetos | Termos de encerramento | 1 |

A API consulta esses valores e os devolve para o aplicativo. A coluna `atualizado_em` recebe valor padrão na criação; o script apresentado não cria, por si só, uma rotina automática para atualizá-la a cada edição.

## 8. Configuração do ambiente

O backend lê as variáveis abaixo do ambiente em que está sendo executado:

| Variável | Obrigatória? | Uso |
|---|---|---|
| `SUPABASE_URL` | Sim | URL do projeto Supabase, por exemplo `https://seu-projeto.supabase.co`. |
| `SUPABASE_SERVICE_KEY` | Sim | Chave secreta do projeto usada somente no servidor. Na configuração atual, use a chave `sb_secret_...`, não `sb_publishable_...`. |
| `SUPABASE_JWT_SECRET` | Condicional | Segredo JWT legado, necessário apenas para projetos que ainda assinam tokens com `HS256`. |
| `DIAS_AVISO_FERIADO` | Não | Quantos dias à frente a rota de notificações procura feriados. Padrão: `14`. |

Não versione o arquivo `.env` e não compartilhe a chave secreta. No Render, configure os valores em **Environment**. Depois de alterar uma variável, reinicie ou faça novo deploy do serviço.

### Rodar localmente no Windows (PowerShell)

Na pasta `fluej-api`:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt

$env:SUPABASE_URL = "https://SEU-PROJETO.supabase.co"
$env:SUPABASE_SERVICE_KEY = "sb_secret_SUA_CHAVE"
$env:SUPABASE_JWT_SECRET = ""
$env:DIAS_AVISO_FERIADO = "14"

uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Rodar localmente no Linux/macOS

Na pasta `fluej-api`, depois de preencher o `.env`:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
set -a
. ./.env
set +a
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

O arquivo `.env` não é lido automaticamente por `os.getenv()`. Os comandos acima exportam suas variáveis para o processo. Outra opção é configurar as variáveis diretamente no terminal.

## 9. Executar os testes

Com o ambiente virtual ativado e as dependências de desenvolvimento instaladas:

```bash
pytest
```

Os testes em `tests/` usam repositório, verificador de token e serviço de feriados falsos. Portanto, testam as regras da API sem consultar o Supabase real ou a BrasilAPI.

- `tests/test_api.py`: rotas, respostas, filtros por setor, ranking, painel, notificações, feriados e desempenho.
- `tests/test_security.py`: assinatura ES256, token expirado, audiência incorreta e assinatura com outra chave.

Antes de publicar uma mudança de segurança, acrescente um teste que reproduza o cenário corrigido.

## 10. Publicação no Render

1. Envie o código para o repositório GitHub conectado ao serviço.
2. No Render, configure as variáveis de ambiente listadas na seção 8.
3. Use o comando de inicialização:

   ```bash
   uvicorn app.main:app --host 0.0.0.0 --port $PORT
   ```

4. Aguarde o deploy terminar.
5. Acesse `https://fluej-api.onrender.com/health` e confirme a resposta `{"status":"ok"}`.
6. Teste uma rota autenticada com um access token válido.

O endpoint `/health` confirma que o processo está respondendo, mas não garante sozinho que o Supabase esteja acessível. Para verificar a integração, faça também uma consulta autenticada, como `/v1/notificacoes`.

## 11. Organização do projeto

```text
fluej-api/
├── app/
│   ├── main.py       # Criação da aplicação FastAPI e health check
│   ├── routes.py     # Endpoints HTTP
│   ├── deps.py       # Identificação do usuário e regras de acesso
│   ├── security.py   # Validação dos tokens JWT do Supabase
│   ├── db.py         # Consultas de leitura ao Supabase
│   ├── services.py   # Ranking, pontos, horas e períodos
│   ├── holidays.py   # Consulta e cache de feriados
│   └── config.py     # Leitura das variáveis de ambiente
├── docs/
│   └── INTEGRACAO_ANDROID.md
├── sql/
│   └── 001_tabelas_da_api.sql
├── tests/
├── .env.example
├── .gitignore
├── Dockerfile
├── requirements.txt
└── requirements-dev.txt
```

## 12. Decisões e limites atuais

- A API não cria, edita nem remove membros, atividades, projetos, avisos ou documentos.
- As consultas ao Supabase são feitas pelo backend com uma chave secreta. Essa chave tem acesso privilegiado e não deve ser enviada ao Android.
- O cache de feriados é mantido na memória do processo. Um novo deploy ou reinício limpa esse cache; em ambientes com mais de um worker, cada worker pode ter seu próprio cache.
- A API não implementa paginação nas listas atuais. Se o volume de membros ou atividades crescer, será necessário revisar o tamanho das consultas.
- A documentação descreve o comportamento dos endpoints implementados em `app/routes.py`. Se uma rota for alterada, atualize também este README e os testes correspondentes.
