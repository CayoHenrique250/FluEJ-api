from __future__ import annotations

import hashlib
import os
import re
import unicodedata
import uuid
from datetime import date, datetime
from zoneinfo import ZoneInfo
from io import BytesIO
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

from ..deps import Usuario, get_usuario
from .admin import SupabaseAdmin, get_admin
from .generator import generate_pdf
from .schemas import GenerateDocumentRequest

router = APIRouter(prefix="/v1", tags=["Perfil dos membros"])
BUCKET = os.getenv("SUPABASE_MEMBER_DOCUMENTS_BUCKET", "member-documents")
MAX_PDF_BYTES = 10 * 1024 * 1024
PROFILE_ROLES = {"presidente", "rh", "orientador"}
MANAGE_ROLES = {"presidente", "rh"}
DOCUMENT_FILE_ROLES = {"presidente", "rh"}


def _require_role(user: Usuario, roles: set[str]) -> None:
    if user.perfil not in roles:
        raise HTTPException(403, "Seu perfil não tem permissão para esta operação.")


def _get_member(admin: SupabaseAdmin, member_id: str, user: Usuario | None = None) -> dict:
    rows = admin.select("members", {
        "select": "id,nome,cargo,setor,ativo",
        "id": f"eq.{member_id}",
        "limit": "1",
    })
    if not rows:
        raise HTTPException(404, "Membro não encontrado.")
    member = rows[0]
    # Reaproveita a regra setorial já aplicada nas demais consultas da FluEJ API.
    if user is not None and user.restrito_ao_setor and member.get("setor") != user.setor:
        raise HTTPException(403, "Você só pode acessar membros do seu setor.")
    return member


def _get_private(admin: SupabaseAdmin, member_id: str) -> dict:
    rows = admin.select("member_private_data", {
        "select": "member_id,nome,email,telefone,data_nascimento,cpf,rg,nacionalidade,estado_civil,profissao,endereco,data_inicio_voluntariado",
        "member_id": f"eq.{member_id}",
        "limit": "1",
    })
    return rows[0] if rows else {}


def _get_document(admin: SupabaseAdmin, document_id: str) -> dict:
    rows = admin.select("member_documents", {
        "select": "id,member_id,tipo,status,storage_path,file_name,mime_type,sha256,version,created_at,uploaded_at,uploaded_by,data_encerramento",
        "id": f"eq.{document_id}",
        "limit": "1",
    })
    if not rows:
        raise HTTPException(404, "Documento não encontrado.")
    return rows[0]


def _document_path(member_id: str, tipo: str, filename: str) -> str:
    return f"{member_id}/{tipo}/{uuid.uuid4().hex}_{filename}"


@router.get("/membros/{member_id}/perfil")
def get_member_profile(
    member_id: str,
    user: Usuario = Depends(get_usuario),
    admin: SupabaseAdmin = Depends(get_admin),
):
    _require_role(user, PROFILE_ROLES)
    member = _get_member(admin, member_id, user)
    private = _get_private(admin, member_id)
    if user.perfil == "orientador":
        # O orientador visualiza o perfil, mas não recebe identificadores civis/endereço.
        private = {key: value for key, value in private.items() if key in {"member_id", "nome", "email", "telefone", "data_inicio_voluntariado"}}
    documents = admin.select("member_documents", {
        "select": "id,member_id,tipo,status,file_name,mime_type,version,created_at,uploaded_at,data_encerramento",
        "member_id": f"eq.{member_id}",
        "order": "created_at.desc",
    })
    # A API retorna somente os dados pessoais necessários à tela autorizada.
    return {
        "membro": member,
        "dados_pessoais": private,
        "documentos": documents,
        "permissoes": {
            "gerenciar_documentos": user.perfil in MANAGE_ROLES,
            "baixar_documentos": user.perfil in DOCUMENT_FILE_ROLES,
        },
    }


@router.get("/membros/{member_id}/documentos")
def list_member_documents(
    member_id: str,
    user: Usuario = Depends(get_usuario),
    admin: SupabaseAdmin = Depends(get_admin),
):
    _require_role(user, PROFILE_ROLES)
    _get_member(admin, member_id, user)
    docs = admin.select("member_documents", {
        "select": "id,member_id,tipo,status,file_name,mime_type,version,created_at,uploaded_at,data_encerramento",
        "member_id": f"eq.{member_id}",
        "order": "created_at.desc",
    })
    return {"total": len(docs), "itens": docs}


@router.post("/membros/{member_id}/documentos/{tipo}/gerar")
def generate_member_document(
    member_id: str,
    tipo: Literal["voluntariado", "encerramento"],
    payload: GenerateDocumentRequest,
    user: Usuario = Depends(get_usuario),
    admin: SupabaseAdmin = Depends(get_admin),
):
    _require_role(user, MANAGE_ROLES)
    member = _get_member(admin, member_id, user)
    if member.get("ativo") is not True:
        raise HTTPException(409, "Não é possível gerar um termo novo para um membro inativo.")
    private = _get_private(admin, member_id)
    private.setdefault("nome", member.get("nome"))
    content, file_name = generate_pdf(tipo, member, private, payload)
    sha256 = hashlib.sha256(content).hexdigest()
    path = _document_path(member_id, tipo, file_name)
    admin.upload_storage(BUCKET, path, content, "application/pdf")
    try:
        result = admin.rpc("register_generated_member_document", {
            "p_member_id": member_id,
            "p_tipo": tipo,
            "p_storage_path": path,
            "p_file_name": file_name,
            "p_sha256": sha256,
            "p_actor_user_id": user.user_id,
        })
        doc_id = str(result).strip('"')
    except Exception:
        admin.delete_storage(BUCKET, path)
        raise
    return {
        "id": doc_id,
        "member_id": member_id,
        "tipo": tipo,
        "status": "gerado",
        "file_name": file_name,
        "message": "Documento gerado. Baixe, confira, colete as assinaturas e anexe a versão final.",
    }


@router.post("/membros/{member_id}/documentos/{tipo}/anexar")
async def upload_signed_member_document(
    member_id: str,
    tipo: Literal["voluntariado", "encerramento"],
    file: UploadFile = File(...),
    data_encerramento: date | None = Form(default=None),
    user: Usuario = Depends(get_usuario),
    admin: SupabaseAdmin = Depends(get_admin),
):
    _require_role(user, MANAGE_ROLES)
    member = _get_member(admin, member_id, user)
    if tipo == "encerramento" and not data_encerramento:
        raise HTTPException(422, "Informe data_encerramento ao anexar o termo de encerramento.")
    if file.content_type not in ("application/pdf", "application/octet-stream"):
        raise HTTPException(415, "Envie o documento em formato PDF.")
    content = await file.read(MAX_PDF_BYTES + 1)
    if len(content) > MAX_PDF_BYTES:
        raise HTTPException(413, "O PDF ultrapassa o limite de 10 MB.")
    if not content.startswith(b"%PDF-"):
        raise HTTPException(415, "O arquivo enviado não possui assinatura de PDF válida.")

    raw_name = os.path.basename(file.filename or f"termo_{tipo}.pdf")
    raw_name = unicodedata.normalize("NFKD", raw_name).encode("ascii", "ignore").decode("ascii")
    original_name = re.sub(r"[^A-Za-z0-9._-]+", "_", raw_name).strip("._") or f"termo_{tipo}.pdf"
    if not original_name.lower().endswith(".pdf"):
        original_name += ".pdf"
    path = _document_path(member_id, tipo, original_name)
    digest = hashlib.sha256(content).hexdigest()
    admin.upload_storage(BUCKET, path, content, "application/pdf")
    try:
        result = admin.rpc("register_uploaded_member_document", {
            "p_member_id": member_id,
            "p_tipo": tipo,
            "p_storage_path": path,
            "p_file_name": original_name,
            "p_sha256": digest,
            "p_actor_user_id": user.user_id,
            "p_data_encerramento": data_encerramento.isoformat() if data_encerramento else None,
        })
        doc_id = str(result).strip('"')
    except Exception:
        admin.delete_storage(BUCKET, path)
        raise

    message = "Documento assinado anexado com sucesso."
    if tipo == "encerramento":
        message += " O membro foi marcado como inativo."
    return {"id": doc_id, "member_id": member_id, "tipo": tipo, "status": "anexado", "message": message}


@router.get("/documentos/{document_id}/download")
def download_member_document(
    document_id: str,
    user: Usuario = Depends(get_usuario),
    admin: SupabaseAdmin = Depends(get_admin),
):
    _require_role(user, DOCUMENT_FILE_ROLES)
    document = _get_document(admin, document_id)
    _get_member(admin, document["member_id"], user)
    content = admin.download_storage(BUCKET, document["storage_path"])
    filename = document["file_name"].replace('"', "")
    return StreamingResponse(
        BytesIO(content),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/documentos/{document_id}/email-draft")
def get_document_email_draft(
    document_id: str,
    user: Usuario = Depends(get_usuario),
    admin: SupabaseAdmin = Depends(get_admin),
):
    _require_role(user, MANAGE_ROLES)
    document = _get_document(admin, document_id)
    member = _get_member(admin, document["member_id"], user)
    private = _get_private(admin, document["member_id"])
    recipient = private.get("email")
    if not recipient:
        raise HTTPException(422, "O membro não possui e-mail cadastrado.")
    name = private.get("nome") or member.get("nome") or "membro"
    app_timezone = ZoneInfo(os.getenv("APP_TIMEZONE", "America/Maceio"))
    prepared_at = datetime.now(app_timezone).strftime("%d/%m/%Y")
    if document["tipo"] == "voluntariado":
        subject = f"Termo de Adesão ao Voluntariado – {name}"
        body = (
            f"Olá, {name}!\n\n"
            "Encaminhamos o Termo de Adesão ao Voluntariado para conferência e assinatura. "
            "Após a assinatura, solicitamos que devolva o documento ao setor responsável.\n\n"
            f"Data de preparação da mensagem: {prepared_at}.\n\n"
            "Atenciosamente,\nRecursos Humanos – Empresa Júnior."
        )
    else:
        subject = f"Termo de Encerramento ao Voluntariado – {name}"
        body = (
            f"Olá, {name}!\n\n"
            "Encaminhamos o Termo de Encerramento ao Voluntariado para sua conferência e assinatura. "
            "Guarde uma cópia do documento assinado.\n\n"
            f"Data de preparação da mensagem: {prepared_at}.\n\n"
            "Atenciosamente,\nRecursos Humanos – Empresa Júnior."
        )
    return {
        "to": recipient,
        "subject": subject,
        "body": body,
        "file_name": document["file_name"],
        "document_id": document_id,
        "prepared_at": prepared_at,
    }
