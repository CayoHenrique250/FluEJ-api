import httpx
from fastapi import HTTPException

from .config import get_settings


class SupabaseRepo:
    def select(self, tabela: str, params: dict | None = None) -> list[dict]:
        s = get_settings()
        if not s.supabase_url or not s.supabase_service_key:
            raise HTTPException(
                500, "API sem SUPABASE_URL / SUPABASE_SERVICE_KEY configurados.")
        headers = {
            "apikey": s.supabase_service_key,
            "Authorization": f"Bearer {s.supabase_service_key}",
        }
        try:
            r = httpx.get(
                f"{s.supabase_url}/rest/v1/{tabela}",
                params=params or {},
                headers=headers,
                timeout=15,
            )
        except httpx.HTTPError:
            raise HTTPException(502, "Não foi possível falar com o banco.")
        if r.status_code >= 400:
            raise HTTPException(502, f"Erro do banco ao ler '{tabela}'.")
        return r.json()


_repo = SupabaseRepo()


def get_repo() -> SupabaseRepo:
    return _repo
