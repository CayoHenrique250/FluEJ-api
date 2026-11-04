from fastapi import FastAPI

from .routes import router

app = FastAPI(
    title="FluEJ API",
    version="1.0.0",
    description="API de consulta do app FluEJ (somente leitura). Autenticação: token do Supabase.",
)
app.include_router(router)


@app.get("/health", tags=["Sistema"])
def health():
    return {"status": "ok"}
