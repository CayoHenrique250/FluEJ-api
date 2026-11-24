from fastapi import FastAPI

from .routes import router

from .profile_documents.router import router as profile_documents_router
app.include_router(profile_documents_router)

app = FastAPI(
    title="FluEJ API",
    version="1.0.0",
    description="API de consulta do app FluEJ (somente leitura). Autenticação: token do Supabase.",
)
app.include_router(router)


@app.get("/health", tags=["Sistema"])
def health():
    return {"status": "ok"}
