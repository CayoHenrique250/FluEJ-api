from datetime import date
from typing import Literal

from pydantic import BaseModel, Field


DocumentType = Literal["voluntariado", "encerramento"]


class GenerateDocumentRequest(BaseModel):
    data_assinatura: date | None = None
    # O modelo de adesão anexado possui um campo chamado [data de encerramento].
    # Exigimos a data para não gerar um documento com esse marcador em aberto.
    data_termino_prevista: date | None = None
    # Pode ser informada aqui quando ainda não estiver cadastrada no Supabase.
    data_inicio_voluntariado: date | None = None
    data_encerramento: date | None = None


class GeneratedDocumentResponse(BaseModel):
    id: str
    member_id: str
    tipo: DocumentType
    status: str
    file_name: str
    created_at: str | None = None
    message: str


class EmailDraftResponse(BaseModel):
    to: str
    subject: str
    body: str
    file_name: str
    document_id: str
    prepared_at: str
