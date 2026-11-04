# Integração com o app Android (Retrofit)

Este guia liga o app FluEJ à API **sem mudar o que já funciona**: login, cadastro, inativação e sincronização
continuam no Supabase (supabase-kt + Room). A API entra só para **consulta**, e o Room guarda o último resultado
para o app continuar mostrando dados sem internet.

## O que muda no app

| Onde | O quê | Arquivo |
|---|---|---|
| Gradle | 4 dependências | `app/build.gradle.kts` |
| Debug | liberar `http://` só em debug | `app/src/debug/AndroidManifest.xml` (novo) |
| `data/api/` | Retrofit, DTOs, cliente, cache, repositório | 6 arquivos novos |
| Room | tabela `api_cache` | `AppDatabase.kt` (3 linhas) |
| Sino de notificações (feriados + avisos) | ViewModel + componente reutilizável | 2 arquivos novos |
| Dashboard do RH | sino real e "Documentos pendentes" reais | `DashboardViewModel.kt` e `DashboardRHScreen.kt` |

Nada disso cadastra ou atualiza dados: são só telas de consulta.

---

## Passo 1 — Dependências

Em `app/build.gradle.kts`, dentro de `dependencies { }`:

```kotlin
implementation("com.squareup.retrofit2:retrofit:2.11.0")
implementation("com.squareup.retrofit2:converter-kotlinx-serialization:2.11.0")
implementation("com.squareup.okhttp3:okhttp:4.12.0")
implementation("com.squareup.okhttp3:logging-interceptor:4.12.0")
```

Você já tem `kotlinx-serialization-json` e o plugin de serialização. Faça **Sync Project**.
Se o Gradle sugerir versões mais novas dessas bibliotecas, pode usá-las.

## Passo 2 — Endereço da API em desenvolvimento

Crie `app/src/debug/AndroidManifest.xml` (a pasta `debug` fica ao lado de `main`):

```xml
<?xml version="1.0" encoding="utf-8"?>
<manifest xmlns:android="http://schemas.android.com/apk/res/android"
    xmlns:tools="http://schemas.android.com/tools">
    <application
        android:usesCleartextTraffic="true"
        tools:targetApi="m" />
</manifest>
```

Isso libera `http://` **apenas** em builds de debug. Em produção use `https://`.

Qual endereço usar (o `localhost` do celular não é o seu computador):

| Onde o app roda | `BASE_URL` |
|---|---|
| Emulador do Android Studio | `http://10.0.2.2:8000/` |
| Celular real, via cabo | rode `adb reverse tcp:8000 tcp:8000` e use `http://127.0.0.1:8000/` |
| Celular real, mesma rede Wi-Fi | `http://IP-DO-SEU-PC:8000/` (a API precisa estar com `--host 0.0.0.0` e o firewall liberado) |
| Produção | `https://seu-servico.exemplo.com/` |

A `BASE_URL` **precisa terminar com `/`**.

## Passo 3 — Arquivos novos em `data/api/`

Crie a pasta `app/src/main/java/com/example/fluej/data/api/`.

### `ApiConfig.kt`
```kotlin
package com.example.fluej.data.api

object ApiConfig {
    // Emulador: 10.0.2.2. Veja a tabela do Passo 2 para celular real e produção.
    const val BASE_URL = "http://10.0.2.2:8000/"
}
```

### `ApiModels.kt`
Os nomes em `snake_case` do JSON são mapeados com `@SerialName`, como você já faz no `Member`.

```kotlin
package com.example.fluej.data.api

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

@Serializable
data class NotificacaoDto(
    val id: String,
    val tipo: String,            // "aviso" ou "feriado"
    val titulo: String,
    val mensagem: String = "",
    val data: String = ""        // yyyy-MM-dd
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

// Os DTOs abaixo ainda não têm tela; já ficam prontos para os próximos dashboards.

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

### `FluejApi.kt`
A interface do Retrofit: só `GET`, com funções `suspend`.

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
    suspend fun feriadosProximos(@Query("dias") dias: Int = 30): List<FeriadoDto>

    @GET("v1/feriados/{ano}")
    suspend fun feriados(@Path("ano") ano: Int): List<FeriadoDto>

    @GET("v1/painel")
    suspend fun painel(): PainelDto

    @GET("v1/ranking")
    suspend fun ranking(@Query("ordem") ordem: String = "asc"): RankingDto
}
```

### `ApiClient.kt`
Cria o Retrofit uma única vez e coloca **o token do Supabase** em toda chamada. O token vem de
`supabase.auth.currentAccessTokenOrNull()`, e o supabase-kt renova sozinho quando ele expira.

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
            // Timeout longo: serviços gratuitos "dormem" e a 1ª chamada pode demorar.
            .readTimeout(40, TimeUnit.SECONDS)
            .addInterceptor { chain ->
                val token = supabase.auth.currentAccessTokenOrNull()
                val request = chain.request().newBuilder().apply {
                    if (token != null) header("Authorization", "Bearer $token")
                }.build()
                chain.proceed(request)
            }
            .addInterceptor(
                // BASIC mostra só método, URL e status; nunca o token.
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
            .addConverterFactory(json.asConverterFactory("application/json".toMediaType()))
            .build()
            .create(FluejApi::class.java)
    }
}
```

> O conversor `converter-kotlinx-serialization` é o oficial do Retrofit, por isso o import é
> `retrofit2.converter.kotlinx.serialization.asConverterFactory`. Tutoriais antigos usam o pacote
> `com.jakewharton...`, que não funciona com essa dependência.

### `ApiCache.kt` (entidade e DAO do Room)
Guarda a última resposta de cada chamada em texto JSON. A chave inclui o id do usuário, então dois usuários
no mesmo aparelho nunca veem o cache um do outro.

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

### `ApiRepository.kt`
Mesma ideia do resto do app: tenta a rede; se der certo, guarda no Room; se falhar, devolve o último dado salvo.
Só dá erro se não houver rede **e** nada salvo.

```kotlin
package com.example.fluej.data.api

import com.example.fluej.data.supabase
import io.github.jan.supabase.gotrue.auth
import kotlinx.coroutines.CancellationException
import kotlinx.serialization.serializer

data class ApiResultado<T>(
    val dados: T,
    val deCache: Boolean,            // true = veio do aparelho (sem rede ou API fora do ar)
    val atualizadoEm: Long? = null   // quando o cache foi salvo
)

class ApiRepository(
    private val cacheDao: ApiCacheDao,
    private val api: FluejApi = ApiClient.api
) {
    private val json = ApiClient.json

    suspend fun notificacoes() = comCache("notificacoes") { api.notificacoes() }

    suspend fun documentosPendentes() = comCache("documentos") { api.documentosPendentes() }

    suspend fun painel() = comCache("painel") { api.painel() }

    suspend fun ranking(ordem: String = "asc") = comCache("ranking_$ordem") { api.ranking(ordem) }

    private suspend inline fun <reified T> comCache(
        chave: String,
        buscar: suspend () -> T
    ): ApiResultado<T> {
        val usuario = supabase.auth.currentUserOrNull()?.id.orEmpty()
        val chaveFinal = "$usuario:$chave"
        return try {
            val dados = buscar()
            cacheDao.salvar(
                ApiCache(chaveFinal, json.encodeToString(serializer<T>(), dados), System.currentTimeMillis())
            )
            ApiResultado(dados, deCache = false)
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

## Passo 4 — Room: registrar a tabela de cache

Em `AppDatabase.kt`, três mudanças:

```kotlin
import com.example.fluej.data.api.ApiCache
import com.example.fluej.data.api.ApiCacheDao

@Database(
    entities = [Member::class, Activity::class, Project::class, ProjectMember::class, ApiCache::class],
    version = /* a versão atual + 1 */,
    exportSchema = false
)
abstract class AppDatabase : RoomDatabase() {
    // ... os DAOs que você já tem
    abstract fun apiCacheDao(): ApiCacheDao
    // ... companion object igual
}
```

Como o banco usa `fallbackToDestructiveMigration()`, ele é recriado e os dados voltam na sincronização
(pendentes não enviados ainda seriam perdidos: abra o app online antes de atualizar).

## Passo 5 — O sino com feriados e avisos

A API já entrega, em `/v1/notificacoes`, os avisos do seu setor **e** os feriados nacionais que estão chegando.
O sino fica como um componente que qualquer dashboard pode reaproveitar.

### `NotificacoesViewModel.kt` (em `ui/viewmodels`)
```kotlin
package com.example.fluej.ui.viewmodels

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

class NotificacoesViewModel(application: Application) : AndroidViewModel(application) {

    private val repository = ApiRepository(AppDatabase.getDatabase(application).apiCacheDao())

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
                Log.e("ApiErro", "Notificações: ${e.message}", e)
                erro = "Não foi possível carregar as notificações."
            } finally {
                carregando = false
            }
        }
    }
}
```

### `SinoNotificacoes.kt` (em `ui/components`)
O sino mostra um selo com a quantidade e, ao tocar, abre uma guia (bottom sheet) com a lista. Os feriados
aparecem com ícone de calendário e os avisos com ícone de informação.

```kotlin
package com.example.fluej.ui.components

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.DateRange
import androidx.compose.material.icons.filled.Info
import androidx.compose.material.icons.filled.Notifications
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.viewmodel.compose.viewModel
import com.example.fluej.data.api.NotificacaoDto
import com.example.fluej.ui.theme.*
import com.example.fluej.ui.viewmodels.NotificacoesViewModel

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun SinoNotificacoes(viewModel: NotificacoesViewModel = viewModel()) {
    var aberto by remember { mutableStateOf(false) }

    LaunchedEffect(Unit) { viewModel.atualizar() }

    IconButton(onClick = { aberto = true }) {
        BadgedBox(
            badge = {
                if (viewModel.itens.isNotEmpty()) {
                    Badge { Text(viewModel.itens.size.toString()) }
                }
            }
        ) {
            Icon(Icons.Default.Notifications, contentDescription = "Notificações", tint = TextPrimary)
        }
    }

    if (aberto) {
        ModalBottomSheet(
            onDismissRequest = { aberto = false },
            sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true),
            containerColor = SurfaceLight
        ) {
            Column(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(horizontal = 20.dp)
                    .padding(bottom = 24.dp)
            ) {
                Text("Notificações", fontWeight = FontWeight.Bold, fontSize = 16.sp, color = TextPrimary)
                if (viewModel.offline) {
                    Text("Mostrando dados salvos no aparelho.", fontSize = 11.sp, color = TextSecondary)
                }
                Spacer(modifier = Modifier.height(12.dp))

                when {
                    viewModel.carregando && viewModel.itens.isEmpty() ->
                        LinearProgressIndicator(modifier = Modifier.fillMaxWidth())

                    viewModel.erro != null && viewModel.itens.isEmpty() -> {
                        Text(viewModel.erro.orEmpty(), color = MaterialTheme.colorScheme.error, fontSize = 13.sp)
                        TextButton(onClick = { viewModel.atualizar() }) { Text("Tentar novamente") }
                    }

                    viewModel.itens.isEmpty() ->
                        Text("Nenhuma notificação por enquanto.", fontSize = 13.sp, color = TextSecondary)

                    else -> LazyColumn(
                        modifier = Modifier.heightIn(max = 420.dp),
                        verticalArrangement = Arrangement.spacedBy(8.dp)
                    ) {
                        items(viewModel.itens, key = { it.id }) { NotificacaoItem(it) }
                    }
                }
            }
        }
    }
}

@Composable
private fun NotificacaoItem(item: NotificacaoDto) {
    Card(
        shape = RoundedCornerShape(12.dp),
        colors = CardDefaults.cardColors(containerColor = CardBackground),
        border = BorderStroke(1.dp, GrayBorder)
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(12.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            Icon(
                imageVector = if (item.tipo == "feriado") Icons.Default.DateRange else Icons.Default.Info,
                contentDescription = null,
                tint = TextPrimary,
                modifier = Modifier.size(22.dp)
            )
            Spacer(modifier = Modifier.width(12.dp))
            Column(modifier = Modifier.weight(1f)) {
                Text(item.titulo, fontWeight = FontWeight.Bold, fontSize = 13.sp, color = TextPrimary)
                if (item.mensagem.isNotBlank()) {
                    Text(item.mensagem, fontSize = 11.sp, color = TextSecondary)
                }
            }
            Text(dataCurta(item.data), fontSize = 11.sp, color = TextSecondary)
        }
    }
}

/** "2026-11-15" -> "15/11" */
private fun dataCurta(iso: String): String {
    val p = iso.split("-")
    return if (p.size == 3) "${p[2]}/${p[1]}" else iso
}
```

## Passo 6 — Dashboard do RH

### `DashboardViewModel.kt`
Adicione o repositório e a lista de documentos. A busca na API roda **separada** da sincronização do Supabase,
para uma API lenta ou fora do ar nunca travar o resto do dashboard.

```kotlin
// imports novos
import android.util.Log
import com.example.fluej.data.api.ApiRepository
import com.example.fluej.data.api.DocumentoPendenteDto
import kotlinx.coroutines.CancellationException

// junto dos outros repositórios
private val apiRepository = ApiRepository(db.apiCacheDao())

// junto das outras variáveis de estado
var documentos by mutableStateOf<List<DocumentoPendenteDto>>(emptyList())
    private set

// dentro de atualizar(): chame no começo da função, antes do viewModelScope.launch existente
fun atualizar() {
    carregarDocumentos()
    // ... o restante do atualizar() continua igual
}

private fun carregarDocumentos() {
    viewModelScope.launch {
        try {
            documentos = apiRepository.documentosPendentes().dados
        } catch (e: CancellationException) {
            throw e
        } catch (e: Exception) {
            Log.e("ApiErro", "Documentos pendentes: ${e.message}", e)
        }
    }
}
```

### `DashboardRHScreen.kt`
Duas trocas.

**a) O sino**, no `actions` da barra superior. Troque o `IconButton` do sino (o que chamava `emBreve`) por
`SinoNotificacoes()` e mantenha o botão **Sair**:

```kotlin
actions = {
    SinoNotificacoes()
    TextButton(onClick = onLogout) {
        Text("Sair", color = TextPrimary)
    }
}
```
Adicione o import `com.example.fluej.ui.components.SinoNotificacoes`.

**b) Os documentos pendentes.** Troque as duas linhas mockadas
(`DocumentoPendenteRow("Termos de voluntariado", 2)` e `DocumentoPendenteRow("Termos de encerramento", 5)`) por:

```kotlin
if (viewModel.documentos.isEmpty()) {
    Text("Nenhum documento pendente.", fontSize = 13.sp, color = TextSecondary)
} else {
    viewModel.documentos.forEach { DocumentoPendenteRow(it.titulo, it.quantidade) }
}
```

A API já devolve só os documentos do setor do usuário, então não precisa filtrar no app.

## Passo 7 — Reaproveitar nos outros dashboards

Em cada dashboard novo (Presidente, Orientador, gestores), o sino é **uma linha** na barra superior:

```kotlin
actions = {
    SinoNotificacoes()
    TextButton(onClick = onLogout) { Text("Sair", color = TextPrimary) }
}
```

Isso vale também para o `DashboardEmBreveScreen` que já existe.

## Passo 8 — Testar

1. Suba a API (veja o README) e confirme `http://localhost:8000/health`.
2. No Supabase, rode `sql/001_tabelas_da_api.sql` (já traz um aviso e documentos de exemplo para o RH).
3. Rode o app (emulador: `BASE_URL = "http://10.0.2.2:8000/"`) e entre com o usuário do RH.
4. **Sino:** deve aparecer o selo com a quantidade. Ao tocar, aparecem o aviso "Reunião geral" e, se algum
   feriado nacional estiver dentro da janela de `DIAS_AVISO_FERIADO` dias, ele também.
5. **Documentos pendentes:** deve mostrar os números que estão na tabela `documentos_pendentes`. Edite no
   Table Editor do Supabase, volte ao dashboard e confira que mudou.
6. **Offline:** com tudo já carregado uma vez, ative o modo avião e reabra o dashboard. O sino deve mostrar
   "Mostrando dados salvos no aparelho." e os documentos devem continuar aparecendo.
7. **Permissão:** entre com o usuário de Projetos. Ele não deve ver os documentos nem os avisos do RH.

## Problemas comuns

| Sintoma | Causa provável |
|---|---|
| `Cleartext HTTP traffic not permitted` | faltou o `AndroidManifest.xml` da pasta `debug` (Passo 2), ou está em build release |
| `Failed to connect to /10.0.2.2:8000` | API fora do ar, ou subiu sem `--host 0.0.0.0` (celular real) |
| `java.lang.IllegalArgumentException: baseUrl must end in /` | faltou a barra final na `BASE_URL` |
| `HTTP 401` | token ausente ou expirado: confira se o login foi feito e veja o Logcat com `ApiErro` |
| `HTTP 403` "sem perfil de acesso" | o usuário não tem linha na tabela `perfis` |
| `HTTP 502` | a API não conseguiu falar com o Supabase: confira `SUPABASE_URL` e `SUPABASE_SERVICE_KEY` |
| Primeira chamada demora muito | serviço gratuito "dormindo"; as seguintes são rápidas |
| `Unresolved reference: asConverterFactory` | import errado: use `retrofit2.converter.kotlinx.serialization.asConverterFactory` |

## Próximos passos (a API já tem as rotas)

- **Dashboard do Presidente e do Orientador:** `ApiRepository.painel()` e `ranking()` já estão prontos.
  Falta só a tela e um `PainelViewModel`, seguindo o mesmo molde do `NotificacoesViewModel`.
- **Detalhe do membro** (ao tocar num membro): `GET /v1/membros/{id}/desempenho`.
- **Calendário de feriados:** `GET /v1/feriados/{ano}`.
- **Registro de pontos** é uma tela de cadastro; por isso continua no Supabase, e não na API.
