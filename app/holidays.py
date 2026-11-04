
import time
from datetime import date, timedelta

import httpx
from fastapi import HTTPException

BRASIL_API = "https://brasilapi.com.br/api/feriados/v1"
CACHE_SEGUNDOS = 24 * 3600


class HolidayService:
    def __init__(self):
        self._cache: dict[int, tuple[float, list[dict]]] = {}

    def do_ano(self, ano: int) -> list[dict]:
        agora = time.time()
        hit = self._cache.get(ano)
        if hit and agora - hit[0] < CACHE_SEGUNDOS:
            return hit[1]
        try:
            r = httpx.get(f"{BRASIL_API}/{ano}", timeout=10)
            r.raise_for_status()
            itens = [
                {"data": f["date"], "nome": f["name"], "tipo": f.get("type", "national")}
                for f in r.json()
            ]
        except (httpx.HTTPError, KeyError, ValueError):
            if hit: 
                return hit[1]
            raise HTTPException(502, "Não foi possível obter os feriados agora.")
        self._cache[ano] = (agora, itens)
        return itens

    def proximos(self, hoje: date, dias: int) -> list[dict]:
        limite = hoje + timedelta(days=dias)
        candidatos = self.do_ano(hoje.year)
        if limite.year != hoje.year:
            candidatos = candidatos + self.do_ano(limite.year)
        saida = []
        for f in candidatos:
            d = date.fromisoformat(f["data"])
            if hoje <= d <= limite:
                saida.append({**f, "faltam_dias": (d - hoje).days})
        return sorted(saida, key=lambda f: f["data"])


_service = HolidayService()


def get_holidays() -> HolidayService:
    return _service
