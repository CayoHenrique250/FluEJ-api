
import httpx
import logging
from urllib.parse import urlparse

from fastapi import HTTPException

from .config import get_settings


logger = logging.getLogger(__name__)


class SupabaseRepo:

    def select(
        self,
        tabela: str,
        params: dict | None = None
    ) -> list[dict]:

        s = get_settings()

        if not s.supabase_url or not s.supabase_service_key:
            raise HTTPException(
                500,
                "API sem SUPABASE_URL / SUPABASE_SERVICE_KEY configurados."
            )

        if s.supabase_service_key.startswith("sb_publishable_"):
            logger.error(
                "[SUPABASE] Foi configurada uma chave publishable "
                "no lugar da chave secreta."
            )
            raise HTTPException(
                500,
                "SUPABASE_SERVICE_KEY precisa utilizar uma chave secreta."
            )

        headers = {
            "apikey": s.supabase_service_key,
        }

        url = f"{s.supabase_url}/rest/v1/{tabela}"

        try:
            response = httpx.get(
                url,
                params=params or {},
                headers=headers,
                timeout=15,
            )

        except httpx.TimeoutException:
            logger.exception(
                "[SUPABASE] Tempo limite excedido na tabela %s.",
                tabela
            )
            raise HTTPException(
                502,
                "Tempo limite excedido ao consultar o banco."
            )

        except httpx.HTTPError:
            logger.exception(
                "[SUPABASE] Falha na comunicação com o banco."
            )
            raise HTTPException(
                502,
                "Não foi possível falar com o banco."
            )

        if response.status_code >= 400:
            logger.error(
                "[SUPABASE] Projeto=%s | Tabela=%s | HTTP=%s",
                urlparse(s.supabase_url).netloc,
                tabela,
                response.status_code
            )

            raise HTTPException(
                502,
                f"Erro do banco ao ler '{tabela}'."
            )

        try:
            dados = response.json()
        except ValueError:
            logger.error(
                "[SUPABASE] Resposta JSON inválida na tabela %s.",
                tabela
            )
            raise HTTPException(
                502,
                "O banco retornou uma resposta inválida."
            )

        logger.warning(
            "[SUPABASE] Projeto=%s | Tabela=%s | Registros=%s",
            urlparse(s.supabase_url).netloc,
            tabela,
            len(dados) if isinstance(dados, list) else "Formato inesperado"
        )

        return dados


_repo = SupabaseRepo()


def get_repo() -> SupabaseRepo:
    return _repo
