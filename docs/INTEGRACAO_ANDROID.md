# Integração da API FluEJ com o aplicativo Android

Este documento descreve como o aplicativo FluEJ consome a API desenvolvida em FastAPI. O foco é a implementação no Android: configuração do Retrofit, envio do token do Supabase, conversão das respostas JSON, persistência temporária com Room e apresentação dos dados nas telas.

A API é utilizada para **consultas**. O fluxo atual de login e as operações de cadastro, edição, inativação, registro de atividades e sincronização de dados continuam sob responsabilidade do aplicativo e do Supabase.

## 1. Visão geral

A integração está organizada em camadas. Cada uma tem uma responsabilidade específica:

```text
Tela / Composable
       |
       v
ViewModel
       |
       v
ApiRepository --------> ApiCacheDao (Room)
       |
       v
FluejApi (Retrofit)
       |
       v
ApiClient (OkHttp + token Supabase)
       |
       v
FluEJ API (FastAPI)
       |
       +----> Supabase (dados do sistema)
       |
       +----> BrasilAPI (feriados nacionais)
```

| Camada | Responsabilidade |
|---|---|
| `ApiConfig` | Define a URL-base da API. |
| `ApiModels` | Representa as respostas JSON em classes Kotlin. |
| `ApiClient` | Configura OkHttp, adiciona o token do usuário e cria o Retrofit. |
| `FluejApi` | Declara os endpoints disponíveis para chamadas Retrofit. |
| `ApiCache` / `ApiCacheDao` | Armazenam e recuperam respostas no Room. |
| `ApiRepository` | Centraliza as chamadas e a estratégia de cache. |
| `ViewModel` | Solicita os dados e disponibiliza estados para a interface. |
| Composables | Apresentam os dados ao usuário. |

A API não recebe a chave secreta do Supabase pelo Android. O aplicativo envia o access token do usuário autenticado. A chave de acesso privilegiado ao banco fica somente nas variáveis de ambiente do backend.

## 2. Endereço da API

A URL de produção configurada para o FluEJ é:

```text
https://fluej-api.onrender.com/
```

O endereço deve terminar com `/`, requisito do Retrofit ao combinar a URL-base com os caminhos declarados em `@GET`.

No arquivo `ApiConfig.kt`:

```kotlin
package com.example.fluej.data.api

object ApiConfig {
    const val BASE_URL = "https://fluej-api.onrender.com/"
}
```

### 2.1 Endereços para desenvolvimento local

Quando o backend estiver sendo executado na máquina de desenvolvimento, o endereço depende de onde o aplicativo está rodando:

| Ambiente | URL-base |
|---|---|
| Emulador Android | `http://10.0.2.2:8000/` |
| Celular físico com `adb reverse` | `http://127.0.0.1:8000/` |
| Celular físico na mesma rede Wi-Fi | `http://IP-DO-COMPUTADOR:8000/` |
| Produção no Render | `https://fluej-api.onrender.com/` |

Para usar o celular físico via USB, execute:

```powershell
adb reverse tcp:8000 tcp:8000
```

Para acesso pela rede Wi-Fi, inicie o FastAPI ouvindo em `0.0.0.0` e permita a porta 8000 no firewall do computador:

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

O endereço `10.0.2.2` é específico do emulador Android padrão e não deve ser usado em um aparelho físico.

### 2.2 Tráfego HTTP em desenvolvimento

A produção deve utilizar HTTPS. Caso seja necessário testar com `http://` em ambiente local, a configuração de tráfego sem criptografia deve ficar restrita ao build de desenvolvimento, por exemplo em `src/debug/AndroidManifest.xml`:

```xml
<?xml version="1.0" encoding="utf-8"?>
<manifest xmlns:android="http://schemas.android.com/apk/res/android"
    xmlns:tools="http://schemas.android.com/tools">
    <application
        android:usesCleartextTraffic="true"
        tools:targetApi="m" />
</manifest>
```

Não habilite tráfego HTTP sem criptografia no build de produção. Confirme também que o `AndroidManifest.xml` principal contém a permissão de internet:

```xml
<uses-permission android:name="android.permission.INTERNET" />
```

## 3. Dependências do projeto

Adicione as dependências abaixo em `app/build.gradle.kts`, caso ainda não estejam declaradas. Se o projeto utiliza um catálogo de versões (`libs.versions.toml`), mantenha as versões centralizadas nele em vez de duplicá-las no arquivo do módulo.

```kotlin
implementation("com.squareup.retrofit2:retrofit:2.11.0")
implementation("com.squareup.retrofit2:converter-kotlinx-serialization:2.11.0")
implementation("com.squareup.okhttp3:okhttp:4.12.0")
implementation("com.squareup.okhttp3:logging-interceptor:4.12.0")
```

A integração também depende do `kotlinx-serialization-json` e do plugin Kotlin Serialization. O projeto já utiliza serialização Kotlin em seus modelos. Após alterar as dependências, sincronize o Gradle.

## 4. Configuração do Retrofit e do OkHttp

### 4.1 `ApiClient.kt`

O `ApiClient` cria uma instância compartilhada de OkHttp e Retrofit. O interceptor consulta a sessão Supabase e adiciona o access token do usuário ao cabeçalho `Authorization`.

O código abaixo mantém o log no nível `BASIC`, adequado para acompanhar método, URL e status HTTP sem registrar o corpo das respostas. O cabeçalho `Authorization` permanece protegido.

```kotlin
package com.example.fluej.data.api

import com.example.fluej.data.supabase
import io.github.jan.supabase.gotrue.auth
import kotlinx.serialization.json.Json
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.logging.HttpLoggingInterceptor
import retrofit2.Retrofit
import retrofit2.converter.kotlinx.serialization.asConverterFactory
import java.util.concurrent.TimeUnit

object ApiClient {

    val json = Json {
        ignoreUnknownKeys = true
        encodeDefaults = true
    }

    private val http: OkHttpClient by lazy {
        OkHttpClient.Builder()
            .connectTimeout(15, TimeUnit.SECONDS)
            .readTimeout(40, TimeUnit.SECONDS)
            .addInterceptor { chain ->
                val token = supabase.auth.currentAccessTokenOrNull()

                val request = chain.request().newBuilder().apply {
                    if (!token.isNullOrBlank()) {
                        header("Authorization", "Bearer $token")
                    }
                }.build()

                chain.proceed(request)
            }
            .addInterceptor(
                HttpLoggingInterceptor().apply {
                    level = HttpLoggingInterceptor.Level.BASIC
                    redactHeader("Authorization")
                }
            )
            .build()
    }

    val api: FluejApi by lazy {
        Retrofit.Builder()
            .baseUrl(ApiConfig.BASE_URL)
            .client(http)
            .addConverterFactory(
                json.asConverterFactory("application/json".toMediaType())
            )
            .build()
            .create(FluejApi::class.java)
    }
}
```

O interceptor não cria uma sessão. Ele utiliza a sessão já estabelecida pelo fluxo de autenticação do aplicativo. Portanto, as chamadas protegidas devem ocorrer depois do login e enquanto houver uma sessão válida.

**Não coloque `SUPABASE_SERVICE_KEY`, `sb_secret_` ou a antiga `service_role` no Android.** Essas credenciais pertencem exclusivamente ao backend. O token enviado pelo aplicativo representa o usuário que realizou o login.

Evite alterar o nível de log para `BODY` em builds distribuídos. O corpo das respostas pode conter dados de membros e informações internas. Se for necessário usá-lo temporariamente em desenvolvimento, remova-o depois do diagnóstico.

### 4.2 `FluejApi.kt`

A interface Retrofit declara os caminhos HTTP disponíveis. A versão atual do arquivo contém estas operações:

```kotlin
package com.example.fluej.data.api

import retrofit2.http.GET
import retrofit2.http.Path
import retrofit2.http.Query

interface FluejApi {

    @GET("v1/notificacoes")
    suspend fun notificacoes(): NotificacoesDto

    @GET("v1/documentos-pendentes")
    suspend fun documentosPendentes(): List<DocumentoPendenteDto>

    @GET("v1/feriados/proximos")
    suspend fun feriadosProximos(
        @Query("dias") dias: Int = 30
    ): List<FeriadoDto>

    @GET("v1/feriados/{ano}")
    suspend fun feriados(
        @Path("ano") ano: Int
    ): List<FeriadoDto>

    @GET("v1/painel")
    suspend fun painel(): PainelDto

    @GET("v1/ranking")
    suspend fun ranking(
        @Query("ordem") ordem: String = "asc"
    ): RankingDto
}
```

As funções são `suspend` e devem ser chamadas em uma coroutine, normalmente a partir de um `ViewModel` ou de um repositório utilizado por ele.

**Limitação atual da interface:** a API também aceita `setor`, `inicio` e `fim` em `/v1/ranking`, mas a função acima envia somente `ordem`. Para enviar filtros adicionais pelo Android, amplie a assinatura:

```kotlin
@GET("v1/ranking")
suspend fun ranking(
    @Query("setor") setor: String? = null,
    @Query("inicio") inicio: String? = null,
    @Query("fim") fim: String? = null,
    @Query("ordem") ordem: String = "asc"
): RankingDto
```

O backend aplica o período personalizado quando `inicio` e `fim` são enviados juntos. Recomenda-se informar ambos ou não informar nenhum.

## 5. Modelos de resposta (DTOs)

Os DTOs representam os objetos JSON enviados pela API. Os nomes dos campos seguem o contrato do backend. Quando o JSON utiliza `snake_case` e a propriedade Kotlin utiliza `camelCase`, use `@SerialName`.

Exemplo das classes utilizadas pelas rotas disponíveis:

```kotlin
package com.example.fluej.data.api

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

@Serializable
data class NotificacaoDto(
    val id: String,
    val tipo: String,
    val titulo: String,
    val mensagem: String = "",
    val data: String = ""
)

@Serializable
data class NotificacoesDto(
    val total: Int = 0,
    val itens: List<NotificacaoDto> = emptyList()
)

@Serializable
data class DocumentoPendenteDto(
    val id: String,
    val setor: String,
    val titulo: String,
    val quantidade: Int = 0
)

@Serializable
data class FeriadoDto(
    val data: String,
    val nome: String,
    val tipo: String = "national",
    @SerialName("faltam_dias") val faltamDias: Int? = null
)

@Serializable
data class RankingItemDto(
    @SerialName("membro_id") val membroId: String,
    val nome: String,
    val cargo: String,
    val setor: String,
    val pontos: Int,
    val horas: Double
)

@Serializable
data class RankingDto(
    val setor: String? = null,
    val inicio: String,
    @SerialName("fim_exclusivo") val fimExclusivo: String,
    val ordem: String,
    val itens: List<RankingItemDto> = emptyList()
)

@Serializable
data class PainelSetorDto(
    val setor: String,
    val membros: Int,
    val pontos: Int,
    val horas: Double
)

@Serializable
data class PainelDto(
    val setor: String? = null,
    @SerialName("membros_ativos") val membrosAtivos: Int,
    val projetos: Int,
    @SerialName("pontos_no_mes") val pontosNoMes: Int,
    @SerialName("horas_no_mes") val horasNoMes: Double,
    @SerialName("por_setor") val porSetor: List<PainelSetorDto> = emptyList()
)
```

O `ignoreUnknownKeys = true` configurado no `ApiClient` permite que o aplicativo ignore campos adicionais enviados pelo backend. Isso não elimina a necessidade de manter os DTOs alinhados aos campos obrigatórios das respostas.

## 6. Persistência local com Room

A camada de cache permite recuperar a última resposta salva quando uma chamada não pode ser concluída. O cache não substitui o Supabase nem representa a fonte oficial dos dados.

### 6.1 Entidade e DAO

No arquivo `ApiCache.kt`:

```kotlin
package com.example.fluej.data.api

import androidx.room.Dao
import androidx.room.Entity
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.PrimaryKey
import androidx.room.Query

@Entity(tableName = "api_cache")
data class ApiCache(
    @PrimaryKey val chave: String,
    val json: String,
    val atualizadoEm: Long
)

@Dao
interface ApiCacheDao {

    @Query("SELECT * FROM api_cache WHERE chave = :chave")
    suspend fun buscar(chave: String): ApiCache?

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun salvar(item: ApiCache)

    @Query("DELETE FROM api_cache")
    suspend fun limpar()
}
```

A coluna `chave` identifica o resultado armazenado; `json` guarda a resposta serializada; `atualizadoEm` registra o instante da gravação em milissegundos desde a época Unix.

### 6.2 Registrar no `AppDatabase.kt`

Inclua `ApiCache` na lista de entidades, exponha o DAO e incremente a versão do banco Room. O número deve ser a versão atual do seu projeto acrescida de uma unidade.

No `@Database`, inclua `ApiCache::class` na lista de entidades e incremente a versão atual do banco em uma unidade. Preserve todas as entidades e declarações de DAO que já existem.

Exemplo das linhas que precisam estar presentes:

```kotlin
entities = [
    Member::class,
    Activity::class,
    Project::class,
    ProjectMember::class,
    ApiCache::class
]

abstract fun apiCacheDao(): ApiCacheDao
```

Não substitua os outros DAOs nem a configuração atual do banco. A inclusão de uma entidade exige uma migração compatível com a estratégia adotada pelo projeto. Se o banco utiliza `fallbackToDestructiveMigration()`, uma migração destrutiva pode apagar dados locais ainda não sincronizados. Como o FluEJ mantém dados operacionais localmente, prefira uma migração Room explícita e faça backup/teste antes de atualizar a versão em produção.

### 6.3 Repositório e estratégia de cache

O `ApiRepository` centraliza as consultas utilizadas pelas telas e grava a resposta após uma chamada bem-sucedida.

A implementação atual é:

```kotlin
package com.example.fluej.data.api

import com.example.fluej.data.supabase
import io.github.jan.supabase.gotrue.auth
import kotlinx.coroutines.CancellationException
import kotlinx.serialization.serializer

data class ApiResultado<T>(
    val dados: T,
    val deCache: Boolean,
    val atualizadoEm: Long? = null
)

class ApiRepository(
    private val cacheDao: ApiCacheDao,
    private val api: FluejApi = ApiClient.api
) {
    private val json = ApiClient.json

    suspend fun notificacoes() =
        comCache("notificacoes") { api.notificacoes() }

    suspend fun documentosPendentes() =
        comCache("documentos") { api.documentosPendentes() }

    suspend fun painel() =
        comCache("painel") { api.painel() }

    suspend fun ranking(ordem: String = "asc") =
        comCache("ranking_$ordem") { api.ranking(ordem) }

    private suspend inline fun <reified T> comCache(
        chave: String,
        buscar: suspend () -> T
    ): ApiResultado<T> {
        val usuario = supabase.auth.currentUserOrNull()?.id.orEmpty()
        val chaveFinal = "$usuario:$chave"

        return try {
            val dados = buscar()
            cacheDao.salvar(
                ApiCache(
                    chave = chaveFinal,
                    json = json.encodeToString(serializer<T>(), dados),
                    atualizadoEm = System.currentTimeMillis()
                )
            )
            ApiResultado(dados = dados, deCache = false)
        } catch (e: CancellationException) {
            throw e
        } catch (e: Exception) {
            val salvo = cacheDao.buscar(chaveFinal) ?: throw e
            ApiResultado(
                dados = json.decodeFromString(serializer<T>(), salvo.json),
                deCache = true,
                atualizadoEm = salvo.atualizadoEm
            )
        }
    }
}
```

A chave do cache inclui o ID do usuário autenticado (`usuario:chave`). Isso separa os resultados de usuários diferentes no mesmo aparelho.

**Comportamento que deve ser considerado na manutenção:** a implementação acima tenta utilizar o cache para qualquer `Exception`, não apenas para falhas de conexão. Portanto, ela também pode apresentar dados antigos se a chamada retornar HTTP 401 ou 403. Para uma versão mais rigorosa, trate `HttpException` de autenticação/autorização separadamente e permita o fallback somente para falhas de rede e, conforme a regra do produto, erros temporários do servidor. Ao encerrar a sessão, avalie também limpar os dados locais do usuário ou manter a separação por ID, conforme a política de privacidade do aplicativo.

Atualmente, o repositório expõe métodos para notificações, documentos pendentes, painel e ranking. A interface `FluejApi` já declara as consultas de feriados, mas elas ainda não possuem métodos correspondentes no `ApiRepository`. A rota de desempenho de membro também ainda não está declarada na interface Retrofit apresentada neste guia.

## 7. Consumo dos dados nas telas

As chamadas devem ser feitas fora da thread principal. O fluxo recomendado é: o `ViewModel` chama o repositório em `viewModelScope`, atualiza o estado e a interface observa esse estado.

### 7.1 Notificações

A rota `GET /v1/notificacoes` retorna uma estrutura com `total` e `itens`. Cada item possui `id`, `tipo`, `titulo`, `mensagem` e `data`. O campo `tipo` assume os valores `aviso` ou `feriado`.

Um `ViewModel` pode manter os dados e os estados de carregamento, erro e origem do resultado:

```kotlin
import android.app.Application
import android.util.Log
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.example.fluej.data.AppDatabase
import com.example.fluej.data.api.ApiRepository
import com.example.fluej.data.api.NotificacaoDto
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.launch

class NotificacoesViewModel(
    application: Application
) : AndroidViewModel(application) {

    private val repository = ApiRepository(
        AppDatabase.getDatabase(application).apiCacheDao()
    )

    var itens by mutableStateOf<List<NotificacaoDto>>(emptyList())
        private set

    var carregando by mutableStateOf(false)
        private set

    var offline by mutableStateOf(false)
        private set

    var erro by mutableStateOf<String?>(null)
        private set

    fun atualizar() {
        viewModelScope.launch {
            carregando = true
            try {
                val resultado = repository.notificacoes()
                itens = resultado.dados.itens
                offline = resultado.deCache
                erro = null
            } catch (e: CancellationException) {
                throw e
            } catch (e: Exception) {
                Log.e("ApiErro", "Falha ao carregar notificações", e)
                erro = "Não foi possível carregar as notificações."
            } finally {
                carregando = false
            }
        }
    }
}
```

O `SinoNotificacoes.kt` pode observar `itens`, `carregando`, `offline` e `erro` para montar o badge e a lista. Se o ViewModel já existir no projeto, mantenha sua implementação e adapte somente os estados e a chamada ao repositório necessários.

A data recebida está no formato `AAAA-MM-DD`. A formatação para exibição deve ser feita na interface, sem alterar o valor original utilizado como dado.

### 7.2 Documentos pendentes

A rota `GET /v1/documentos-pendentes` retorna uma lista. Cada elemento contém:

- `id`: identificador do registro;
- `setor`: setor ao qual o documento pertence;
- `titulo`: nome do documento;
- `quantidade`: quantidade pendente.

O backend já aplica o filtro de setor de acordo com o perfil. A tela não deve tentar substituir essa autorização por um filtro exclusivamente local. O `DashboardViewModel` pode chamar `repository.documentosPendentes()` e disponibilizar a lista para o dashboard do RH.

Exemplo de apresentação dos dados:

```kotlin
if (viewModel.documentos.isEmpty()) {
    Text("Nenhum documento pendente.")
} else {
    viewModel.documentos.forEach { documento ->
        DocumentoPendenteRow(
            documento.titulo,
            documento.quantidade
        )
    }
}
```

O trecho pressupõe que `documentos` seja uma propriedade de estado do ViewModel e que `DocumentoPendenteRow` seja o componente visual utilizado pelo dashboard.

### 7.3 Painel e ranking

O `ApiRepository` já disponibiliza `painel()` e `ranking(ordem)`. As respostas podem ser utilizadas nas telas de dashboard quando essas funcionalidades forem integradas.

O painel contém os indicadores do mês atual, enquanto o ranking contém os membros ativos ordenados pela pontuação. A regra de conversão definida no backend é:

```text
60 pontos = 1 hora
horas = pontos / 60
```

O Android deve apresentar o valor `horas` recebido do backend, sem recalcular de maneira diferente. Se a tela precisar filtrar o ranking por setor ou período, atualize a assinatura Retrofit e o método correspondente no repositório para encaminhar os parâmetros suportados pela API.

### 7.4 Consulta de feriados

A interface `FluejApi` já possui `feriadosProximos(dias)` e `feriados(ano)`. No código atual apresentado, essas funções ainda são chamadas diretamente pela interface Retrofit; o `ApiRepository` não possui métodos com cache para elas.

Para centralizar as chamadas e aplicar a mesma estratégia de cache, podem ser incluídos no repositório:

```kotlin
suspend fun feriadosProximos(dias: Int = 30) =
    comCache("feriados_proximos_$dias") {
        api.feriadosProximos(dias)
    }

suspend fun feriados(ano: Int) =
    comCache("feriados_$ano") {
        api.feriados(ano)
    }
```

Esses métodos são uma extensão sugerida; só devem ser documentados como disponíveis depois de adicionados ao `ApiRepository` do projeto.

### 7.5 Desempenho de um membro

O backend disponibiliza `GET /v1/membros/{membro_id}/desempenho?meses=6`, mas a interface Retrofit e os DTOs apresentados ainda não incluem essa operação. Para integrá-la, será necessário:

1. criar DTOs que representem `membro`, `total_pontos`, `total_horas`, `pontos_por_mes` e `projetos`;
2. declarar a função Retrofit com `@Path("membro_id")` e `@Query("meses")`;
3. criar o método correspondente no `ApiRepository`;
4. consumir o resultado em um ViewModel da tela de detalhes do membro.

O parâmetro `meses` aceita valores de 1 a 24 e, no backend atual, limita a quantidade de meses com registros apresentada em `pontos_por_mes`. O total de pontos retornado considera o histórico consultado pelo serviço, não apenas os meses exibidos.

## 8. Endpoints e integração no Android

A tabela diferencia o que o backend oferece do que está declarado nas classes Kotlin apresentadas neste documento.

| Endpoint | Finalidade | Situação no Android descrito aqui |
|---|---|---|
| `GET /health` | Verificar disponibilidade da API | Verificação externa; não exige Retrofit autenticado |
| `GET /v1/notificacoes` | Avisos e feriados próximos | Declarado no Retrofit e no Repository |
| `GET /v1/documentos-pendentes` | Pendências por setor | Declarado no Retrofit e no Repository |
| `GET /v1/feriados/proximos` | Feriados nos próximos dias | Declarado no Retrofit; falta método no Repository |
| `GET /v1/feriados/{ano}` | Feriados de um ano | Declarado no Retrofit; falta método no Repository |
| `GET /v1/painel` | Indicadores do mês | Declarado no Retrofit e no Repository |
| `GET /v1/ranking` | Ranking de membros ativos | Declarado no Retrofit e no Repository; filtros adicionais não estão mapeados na assinatura atual |
| `GET /v1/membros/{membro_id}/desempenho` | Histórico de um membro | Ainda precisa ser declarado no Retrofit, nos DTOs e no Repository |

A presença de uma função na interface Retrofit não significa, por si só, que a tela correspondente já esteja implementada ou que a consulta esteja sendo chamada pelo aplicativo.

## 9. Autenticação e permissões

Todas as rotas sob `/v1` exigem um access token válido do Supabase. A rota `/health` é a exceção.

O cabeçalho enviado pelo Android deve ter este formato:

```http
Authorization: Bearer ACCESS_TOKEN_DO_USUARIO
```

O token deve ser obtido da sessão do usuário autenticado. Não reutilize a chave secreta do backend e não grave tokens em logs, arquivos de configuração ou no repositório Git.

O backend consulta a tabela `perfis` para identificar o perfil e o setor do usuário. Os valores aceitos são `presidente`, `rh`, `projetos`, `comercial`, `financeiro` e `orientador`.

A interface pode ocultar recursos que o perfil não utiliza, mas a autorização efetiva sempre é feita pelo backend. Não considere uma validação visual no Android como controle de segurança.

## 10. Testar a integração

### 10.1 Verificar se o backend está no ar

Abra no navegador:

```text
https://fluej-api.onrender.com/health
```

A resposta esperada é:

```json
{"status":"ok"}
```

Esse endpoint confirma que o serviço está respondendo. Ele não comprova, sozinho, que a conexão com o Supabase ou com a BrasilAPI está funcionando.

### 10.2 Testar uma rota autenticada pelo PowerShell

Obtenha um access token por meio do fluxo de login de um usuário de teste. Em seguida, execute:

```powershell
$base = "https://fluej-api.onrender.com"
$token = "ACCESS_TOKEN_DO_USUARIO"
$headers = @{ Authorization = "Bearer $token" }

Invoke-RestMethod -Method Get `
  -Uri "$base/v1/notificacoes" `
  -Headers $headers
```

Não salve um token real em um arquivo versionado nem o compartilhe em capturas de tela.

### 10.3 Conferir no aplicativo

1. Configure a URL-base correta em `ApiConfig.kt`.
2. Inicie o aplicativo e faça login com um usuário cadastrado na tabela `perfis`.
3. Abra a tela que utiliza notificações ou documentos pendentes.
4. Verifique o Logcat para confirmar o status HTTP e identificar falhas.
5. Compare a resposta com os DTOs e com os dados cadastrados no Supabase.

O `HttpLoggingInterceptor` em nível `BASIC` exibe informações básicas da requisição. Para investigar o corpo de um erro, prefira registrar temporariamente a mensagem controlada pelo backend, sem expor token, chave ou dados pessoais.

## 11. Códigos HTTP e diagnóstico

| Código | Significado no contexto da integração | Verificação inicial |
|---|---|---|
| `200` | Consulta concluída | Conferir se os campos foram convertidos corretamente nos DTOs. |
| `400` | Parâmetro ou intervalo inválido | Verificar ano, datas e demais valores enviados. |
| `401` | Token ausente, inválido ou expirado | Confirmar login e presença do cabeçalho `Authorization`. |
| `403` | Usuário sem perfil ou sem permissão para o recurso | Conferir o registro em `perfis`, o perfil e o setor. |
| `404` | Recurso ou membro não encontrado | Conferir o identificador enviado. |
| `422` | Parâmetro não passou pela validação do FastAPI | Conferir tipo, formato e limites dos parâmetros. |
| `502` | Falha do backend ao consultar um serviço externo ou o banco | Conferir logs do Render, Supabase e BrasilAPI. |
| `500` | Erro interno ou configuração inválida do servidor | Conferir variáveis de ambiente e logs do backend. |

### 11.1 Erro HTTP 401

Confirme que o usuário realizou login, que há uma sessão ativa e que o interceptor consegue obter o access token. Não tente resolver um `401` substituindo o token do usuário pela chave secreta do Supabase.

### 11.2 Erro HTTP 403

Um token válido não garante que o usuário tenha autorização. Confira se o `sub` do token corresponde ao `user_id` de um registro na tabela `perfis` e se o perfil está entre os valores permitidos pelo backend. Para endpoints restritos por setor, confira também o setor cadastrado.

### 11.3 Erro HTTP 502

Verifique os logs do Render e a configuração do backend. Uma resposta `502` pode ocorrer quando o backend não consegue consultar o Supabase ou quando a BrasilAPI está indisponível e não existe resultado em cache para o ano solicitado.

### 11.4 Falha de conexão

Confirme a URL-base, a conectividade do aparelho, o estado do serviço no Render e os timeouts do OkHttp. Em ambiente local, confirme também o endereço de rede e o firewall.

## 12. Boas práticas de manutenção

- Mantenha a URL de produção em HTTPS.
- Não inclua chaves secretas do Supabase no aplicativo Android.
- Não registre access tokens, dados pessoais ou corpos completos de respostas em logs de produção.
- Mantenha os DTOs sincronizados com os contratos JSON do backend.
- Faça chamadas de rede em coroutines, fora da thread principal.
- Trate erros de autenticação e autorização de forma diferente de falhas de conectividade.
- Atualize a versão do Room e crie migrações compatíveis ao alterar entidades.
- Separe os dados em cache por usuário e avalie a limpeza no encerramento da sessão.
- Teste os perfis e os limites de setor no backend; esconder componentes na interface não substitui autorização no servidor.
- Ao adicionar um endpoint, atualize a interface Retrofit, os DTOs, o Repository, o ViewModel, a tela e os testes correspondentes.

## 13. Referências do projeto

- `ApiConfig.kt`: endereço-base da API.
- `ApiClient.kt`: configuração de OkHttp, Retrofit e autenticação.
- `FluejApi.kt`: declaração dos endpoints Retrofit.
- `ApiModels.kt`: modelos Kotlin das respostas JSON.
- `ApiCache.kt`: entidade e DAO de cache do Room.
- `ApiRepository.kt`: consultas e persistência das respostas.
- `AppDatabase.kt`: configuração do banco local.
- `SinoNotificacoes.kt`: componente visual do sino de notificações.
- `NotificacoesViewModel.kt`: estado e carregamento das notificações, conforme a organização adotada no aplicativo.
- `DashboardViewModel.kt` e `DashboardRHScreen.kt`: integração dos documentos pendentes no dashboard do RH.

Para conhecer as rotas, parâmetros, permissões e respostas do backend, consulte também o `README.md` da pasta `fluej-api` e a documentação interativa do FastAPI em `/docs`.
