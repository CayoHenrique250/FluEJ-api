from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
import unicodedata
from datetime import date
from pathlib import Path

from docx import Document
from fastapi import HTTPException


PACKAGE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = PACKAGE_DIR / "templates"


def _format_date(value: date | str | None) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        value = date.fromisoformat(value[:10])
    return value.strftime("%d/%m/%Y")


def _replace_once_in_paragraph(paragraph, marker: str, replacement: str) -> bool:
    """Substitui marcador mesmo quando o Word o dividiu em vários runs."""
    runs = paragraph.runs
    full_text = "".join(run.text for run in runs)
    start = full_text.find(marker)
    if start < 0:
        return False
    end = start + len(marker)
    positions = []
    cursor = 0
    for index, run in enumerate(runs):
        run_start = cursor
        run_end = cursor + len(run.text)
        positions.append((index, run_start, run_end))
        cursor = run_end
    start_run = next(i for i, a, b in positions if a <= start < b or (a == b == start))
    end_run = next(i for i, a, b in positions if a < end <= b or (a == b == end))
    start_offset = start - positions[start_run][1]
    end_offset = end - positions[end_run][1]
    if start_run == end_run:
        original = runs[start_run].text
        runs[start_run].text = original[:start_offset] + replacement + original[end_offset:]
    else:
        first_text = runs[start_run].text
        last_text = runs[end_run].text
        runs[start_run].text = first_text[:start_offset] + replacement
        for index in range(start_run + 1, end_run):
            runs[index].text = ""
        runs[end_run].text = last_text[end_offset:]
    return True


def _all_paragraphs(document):
    for paragraph in document.paragraphs:
        yield paragraph
    for table in document.tables:
        for row in table.rows:
            for cell in row.cells:
                for paragraph in cell.paragraphs:
                    yield paragraph
    for section in document.sections:
        for paragraph in section.header.paragraphs:
            yield paragraph
        for paragraph in section.footer.paragraphs:
            yield paragraph


def _replace_document_markers(document, replacements: dict[str, str], repeated: dict[str, list[str]] | None = None):
    for paragraph in _all_paragraphs(document):
        for marker, value in replacements.items():
            while _replace_once_in_paragraph(paragraph, marker, value):
                pass
        if repeated:
            for marker, values in repeated.items():
                for value in values:
                    _replace_once_in_paragraph(paragraph, marker, value)


def _volunteer_qualification(private: dict) -> str:
    required = ["nome", "nacionalidade", "estado_civil", "profissao", "cpf", "rg", "endereco", "email"]
    missing = [field for field in required if not private.get(field)]
    if missing:
        raise HTTPException(422, "Complete os dados pessoais do membro antes de gerar o termo.")
    return (
        f"{private['nome']}, {private['nacionalidade']}, {private['estado_civil']}, "
        f"{private['profissao']}, inscrito(a) no CPF sob o n.º {private['cpf']}, "
        f"RG n.º {private['rg']}, residente e domiciliado(a) em {private['endereco']}, "
        f"e-mail {private['email']}"
    )


def _company_from_env() -> dict[str, str]:
    keys = {
        "razao_social": "EMPRESA_RAZAO_SOCIAL",
        "nome_fantasia": "EMPRESA_NOME_FANTASIA",
        "cnpj": "EMPRESA_CNPJ",
        "endereco": "EMPRESA_ENDERECO",
        "email": "EMPRESA_EMAIL",
        "representante_nome": "EMPRESA_REPRESENTANTE_NOME",
        "representante_cpf": "EMPRESA_REPRESENTANTE_CPF",
        "cidade_uf": "EMPRESA_CIDADE_UF",
    }
    data = {field: os.getenv(env, "").strip() for field, env in keys.items()}
    missing = [env for field, env in keys.items() if not data[field]]
    if missing:
        raise HTTPException(503, "Configure os dados institucionais no ambiente do backend: " + ", ".join(missing))
    return data


def _slug(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    normalized = re.sub(r"[^a-zA-Z0-9_-]+", "_", normalized).strip("_")
    return (normalized or "membro")[:60]


def _convert_to_pdf(docx_path: Path, output_dir: Path) -> Path:
    executable = shutil.which("libreoffice") or shutil.which("soffice")
    if not executable:
        raise HTTPException(503, "LibreOffice não está instalado no servidor para converter DOCX em PDF.")
    profile_dir = output_dir / "lo-profile"
    command = [
        executable,
        f"-env:UserInstallation={profile_dir.as_uri()}",
        "--headless",
        "--convert-to", "pdf",
        "--outdir", str(output_dir),
        str(docx_path),
    ]
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=60, check=False)
    except subprocess.TimeoutExpired as exc:
        raise HTTPException(504, "A conversão do documento para PDF excedeu o tempo limite.") from exc
    pdf_path = output_dir / f"{docx_path.stem}.pdf"
    if result.returncode != 0 or not pdf_path.exists():
        raise HTTPException(500, "Não foi possível converter o modelo DOCX em PDF.")
    return pdf_path


def generate_pdf(
    tipo: str,
    member: dict,
    private: dict,
    request_data,
) -> tuple[bytes, str]:
    company = _company_from_env()
    today = request_data.data_assinatura or date.today()
    member_name = private.get("nome") or member.get("nome") or "membro"
    safe_name = _slug(member_name)

    with tempfile.TemporaryDirectory(prefix="fluej-doc-") as temp:
        temp_dir = Path(temp)
        if tipo == "voluntariado":
            if not request_data.data_termino_prevista:
                raise HTTPException(422, "Informe data_termino_prevista: o modelo anexado possui essa data na cláusula 5ª.")
            source = TEMPLATES_DIR / "termo_voluntariado.docx"
            doc = Document(source)
            replacements = {
                "[Razão social da Empresa júnior]": company["razao_social"],
                "[XXX]": company["nome_fantasia"],
                "[nº do CNPJ]": company["cnpj"],
                "[endereço completo da Empresa Júnior]": company["endereco"],
                "<XXX>": company["email"],
                "[nome da Empresa Júnior]": company["nome_fantasia"],
                "[qualificação completa do voluntário, contendo nome completo, nacionalidade, estado civil, profissão, CPF, RG, endereço completo e e-mail]": _volunteer_qualification(private),
                "202X": os.getenv("PROCESSO_SELETIVO_ANO", str(today.year)),
                "[data de encerramento]": _format_date(request_data.data_termino_prevista),
                "[cidade e estado]": company["cidade_uf"],
                "[data de assinatura]": _format_date(today),
                "[Empresa Junior]": company["nome_fantasia"],
                "[representante legal]": company["representante_nome"],
            }
            _replace_document_markers(doc, replacements)
            repeated = {"XXX": [company["representante_nome"], company["representante_cpf"]]}
            _replace_document_markers(doc, {}, repeated)
            output_name = f"termo_voluntariado_{safe_name}_{today.isoformat()}"
        elif tipo == "encerramento":
            data_inicio = request_data.data_inicio_voluntariado or private.get("data_inicio_voluntariado")
            if not data_inicio:
                raise HTTPException(422, "Informe ou cadastre data_inicio_voluntariado antes de gerar o encerramento.")
            data_encerramento = request_data.data_encerramento or today
            source = TEMPLATES_DIR / "termo_encerramento.docx"
            doc = Document(source)
            replacements = {
                "[[RAZAO_SOCIAL]]": company["razao_social"],
                "[[NOME_FANTASIA]]": company["nome_fantasia"],
                "[[CNPJ]]": company["cnpj"],
                "[[ENDERECO_EMPRESA]]": company["endereco"],
                "[[EMAIL_EMPRESA]]": company["email"],
                "[[REPRESENTANTE_NOME]]": company["representante_nome"],
                "[[REPRESENTANTE_CPF]]": company["representante_cpf"],
                "[[QUALIFICACAO_VOLUNTARIO]]": _volunteer_qualification(private),
                "[[DATA_ADESAO]]": _format_date(data_inicio),
                "[[NOME_VOLUNTARIO]]": member_name,
                "[[DATA_INICIO]]": _format_date(data_inicio),
                "[[DATA_ENCERRAMENTO]]": _format_date(data_encerramento),
                "[[DATA_ASSINATURA]]": _format_date(today),
                "[[CIDADE_UF]]": company["cidade_uf"],
            }
            _replace_document_markers(doc, replacements)
            output_name = f"termo_encerramento_{safe_name}_{today.isoformat()}"
        else:
            raise HTTPException(400, "Tipo de documento inválido.")

        unresolved = []
        for paragraph in _all_paragraphs(doc):
            if re.search(r"\[[^\]]+\]|\[\[[^\]]+\]\]|\bXXX\b|<XXX>", paragraph.text):
                unresolved.append(paragraph.text)
        if unresolved:
            raise HTTPException(422, "O modelo contém campos não preenchidos. Confira os dados e o mapeamento do documento.")

        docx_path = temp_dir / f"{output_name}.docx"
        doc.save(docx_path)
        pdf_path = _convert_to_pdf(docx_path, temp_dir)
        content = pdf_path.read_bytes()
        if not content.startswith(b"%PDF-"):
            raise HTTPException(500, "O arquivo gerado não é um PDF válido.")
        return content, f"{output_name}.pdf"
