"""Acesso administrativo ao PostgREST e ao Supabase Storage.

Este módulo usa SUPABASE_SERVICE_KEY apenas no backend. Nunca envie essa chave
para o aplicativo Android.
"""
from __future__ import annotations

from urllib.parse import quote

import httpx
from fastapi import HTTPException

from ..config import get_settings


TIMEOUT = 30.0


class SupabaseAdmin:
    def __init__(self) -> None:
        settings = get_settings()
        if not settings.supabase_url or not settings.supabase_service_key:
            raise HTTPException(503, "Supabase não configurado no servidor.")
        if settings.supabase_service_key.startswith("sb_publishable_"):
            raise HTTPException(503, "SUPABASE_SERVICE_KEY deve ser uma chave secreta de servidor.")
        self.base_url = settings.supabase_url.rstrip("/")
        self.key = settings.supabase_service_key

    def _headers(self, extra: dict[str, str] | None = None) -> dict[str, str]:
        headers = {
            "apikey": self.key,
            "Authorization": f"Bearer {self.key}",
        }
        if extra:
            headers.update(extra)
        return headers

    def select(self, table: str, params: dict | list[tuple[str, str]]) -> list[dict]:
        try:
            response = httpx.get(
                f"{self.base_url}/rest/v1/{table}",
                params=params,
                headers=self._headers(),
                timeout=TIMEOUT,
            )
            response.raise_for_status()
            data = response.json()
            if not isinstance(data, list):
                raise HTTPException(502, "Resposta inesperada do Supabase.")
            return data
        except HTTPException:
            raise
        except (httpx.HTTPError, ValueError) as exc:
            raise HTTPException(502, "Falha ao consultar o Supabase.") from exc

    def rpc(self, function_name: str, payload: dict):
        try:
            response = httpx.post(
                f"{self.base_url}/rest/v1/rpc/{function_name}",
                json=payload,
                headers=self._headers({"Content-Type": "application/json"}),
                timeout=TIMEOUT,
            )
            if response.is_error:
                # Não repassamos detalhes internos do banco ao aplicativo.
                raise HTTPException(409, "Não foi possível concluir a operação no banco de dados.")
            if not response.content:
                return None
            return response.json()
        except HTTPException:
            raise
        except (httpx.HTTPError, ValueError) as exc:
            raise HTTPException(502, "Falha ao executar operação no Supabase.") from exc

    def upload_storage(self, bucket: str, path: str, content: bytes, content_type: str) -> None:
        encoded_path = quote(path, safe="/")
        try:
            response = httpx.post(
                f"{self.base_url}/storage/v1/object/{bucket}/{encoded_path}",
                content=content,
                headers=self._headers({
                    "Content-Type": content_type,
                    "x-upsert": "false",
                }),
                timeout=TIMEOUT,
            )
            if response.is_error:
                raise HTTPException(502, "Não foi possível armazenar o documento.")
        except HTTPException:
            raise
        except httpx.HTTPError as exc:
            raise HTTPException(502, "Falha ao enviar o documento ao Storage.") from exc

    def download_storage(self, bucket: str, path: str) -> bytes:
        encoded_path = quote(path, safe="/")
        try:
            response = httpx.get(
                f"{self.base_url}/storage/v1/object/{bucket}/{encoded_path}",
                headers=self._headers(),
                timeout=TIMEOUT,
            )
            if response.status_code == 404:
                raise HTTPException(404, "Arquivo não encontrado no armazenamento.")
            response.raise_for_status()
            return response.content
        except HTTPException:
            raise
        except httpx.HTTPError as exc:
            raise HTTPException(502, "Falha ao baixar o documento do Storage.") from exc

    def delete_storage(self, bucket: str, path: str) -> None:
        encoded_path = quote(path, safe="/")
        try:
            response = httpx.delete(
                f"{self.base_url}/storage/v1/object/{bucket}/{encoded_path}",
                headers=self._headers(),
                timeout=TIMEOUT,
            )
            if response.is_error:
                # O erro de limpeza não deve esconder o erro principal.
                return
        except httpx.HTTPError:
            return


def get_admin() -> SupabaseAdmin:
    return SupabaseAdmin()
