"""
core/services/file_import.py

Ponto único chamado pela view de upload. Decide qual extrator usar,
grava Image (quando houver) e Element no banco, e loga a criação de
cada elemento no histórico -- tudo dentro de uma transação, pra não
deixar Elements órfãos se algo falhar no meio.
"""
import os
import tempfile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import transaction

from core.models import Element
from core.services import history
from core.services.extractors.ocr import extract_with_ocr
from core.services.extractors.pdf import extract_pdf, pdf_has_extractable_text
from core.services.extractors.pptx import extract_pptx
from uploader.models import Image

SUPPORTED_EXTENSIONS = {".pptx", ".pdf", ".jpg", ".jpeg", ".png"}

EXTENSION_TO_CONTENT_TYPE = {
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
}


class UnsupportedFileType(Exception):
    pass


def _extract_raw_elements(tmp_path, ext):
    if ext == ".pptx":
        return extract_pptx(tmp_path)

    if ext == ".pdf":
        if pdf_has_extractable_text(tmp_path):
            return extract_pdf(tmp_path)
        return extract_with_ocr(tmp_path, is_pdf=True)

    if ext in {".jpg", ".jpeg", ".png"}:
        return extract_with_ocr(tmp_path, is_pdf=False)

    raise UnsupportedFileType(f"Tipo de arquivo não suportado: {ext}")


def _salvar_imagem_extraida(raw, design):
    content_type = EXTENSION_TO_CONTENT_TYPE.get(raw["image_ext"], "image/png")
    arquivo_upload = SimpleUploadedFile(
        name=f"design_{design.id}_elemento.{raw['image_ext']}",
        content=raw["image_bytes"],
        content_type=content_type,
    )
    asset = Image(description=f"Elemento extraído do design {design.id}")
    asset.file = arquivo_upload
    asset.save()
    return asset.url


@transaction.atomic
def import_file_into_design(uploaded_file, design, user):
    ext = os.path.splitext(uploaded_file.name)[1].lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise UnsupportedFileType(f"Tipo de arquivo não suportado: {ext}")

    with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
        for chunk in uploaded_file.chunks():
            tmp.write(chunk)
        tmp_path = tmp.name

    try:
        raw_elements, canvas_width, canvas_height = _extract_raw_elements(tmp_path, ext)
    finally:
        os.remove(tmp_path)

    context = history.ChangeContext(user=user, design=design)

    for layer_order, raw in enumerate(raw_elements):
        image_url = ""
        if raw["type"] == "image" and raw["image_bytes"]:
            image_url = _salvar_imagem_extraida(raw, design)

        element = Element.objects.create(
            design=design,
            type=raw["type"],
            content=image_url if raw["type"] == "image" else raw["content"],
            posicao_x=raw["posicao_x"],
            posicao_y=raw["posicao_y"],
            width=raw["width"],
            heigth=raw["heigth"],
            color="",
            layer_order=layer_order,
        )

        history.log_creation(
            context,
            history.TargetRef("element", element.id),
            description=f"Elemento criado a partir do arquivo importado ({raw['type']})",
        )

    return canvas_width, canvas_height
