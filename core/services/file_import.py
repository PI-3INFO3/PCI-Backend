import os
import tempfile

import fitz
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import transaction

from core.models import DesignPage, Element
from core.services import history
from core.services.extractors.ocr import extract_with_ocr
from core.services.extractors.pdf import (
    extract_pdf,
    pdf_has_extractable_text,
)
from core.services.extractors.pptx import extract_pptx_pages
from uploader.models import Image

SUPPORTED_EXTENSIONS = {
    ".pptx",
    ".pdf",
    ".jpg",
    ".jpeg",
    ".png",
}

EXTENSION_TO_CONTENT_TYPE = {
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
}


class UnsupportedFileType(Exception):
    """Tipo de arquivo não suportado para importação."""


def _extract_pdf_pages(tmp_path):
    """Extrai as páginas de um PDF."""
    with fitz.open(tmp_path) as doc:
        page_count = len(doc)

    pages = []

    for page_number in range(page_count):
        if pdf_has_extractable_text(
            tmp_path,
            page_number=page_number,
        ):
            raw_elements, width, height = extract_pdf(
                tmp_path,
                page_number=page_number,
            )
        else:
            with fitz.open(tmp_path) as doc:
                has_images = bool(
                    doc[page_number].get_images(full=True)
                )

            if has_images:
                raw_elements, width, height = extract_pdf(
                    tmp_path,
                    page_number=page_number,
                )
            else:
                raw_elements, width, height = extract_with_ocr(
                    tmp_path,
                    is_pdf=True,
                    page_number=page_number,
                )

        pages.append({
            "name": f"Página {page_number + 1}",
            "page_order": page_number,
            "width": width,
            "height": height,
            "elements": raw_elements,
        })

    return pages


def _extract_image_page(tmp_path):
    """Extrai o conteúdo de uma imagem."""
    raw_elements, width, height = extract_with_ocr(
        tmp_path,
        is_pdf=False,
    )

    return [{
        "name": "Página 1",
        "page_order": 0,
        "width": width,
        "height": height,
        "elements": raw_elements,
    }]


def _extract_pages(tmp_path, ext):
    """Escolhe o extrator adequado ao arquivo."""
    if ext == ".pptx":
        return extract_pptx_pages(tmp_path)

    if ext == ".pdf":
        return _extract_pdf_pages(tmp_path)

    if ext in {".jpg", ".jpeg", ".png"}:
        return _extract_image_page(tmp_path)

    raise UnsupportedFileType(
        f"Tipo de arquivo não suportado: {ext}"
    )


def _salvar_imagem_extraida(raw, design):
    """Salva uma imagem extraída e devolve sua URL."""
    extension = raw.get("image_ext") or "png"
    content_type = EXTENSION_TO_CONTENT_TYPE.get(
        extension.lower(),
        "image/png",
    )

    arquivo_upload = SimpleUploadedFile(
        name=f"design_{design.id}_elemento.{extension}",
        content=raw["image_bytes"],
        content_type=content_type,
    )

    asset = Image(
        description=f"Elemento extraído do design {design.id}"
    )
    asset.file = arquivo_upload
    asset.save()

    return asset.url


def _normalizar_tipo_forma(raw):
    """Garante que o tipo da forma seja aceito pelo modelo."""
    valid_types = {
        Element.ShapeType.RECT,
        Element.ShapeType.CIRCLE,
        Element.ShapeType.TRIANGLE,
        Element.ShapeType.STAR,
    }

    shape_type = raw.get("shape_type") or Element.ShapeType.RECT

    if shape_type not in valid_types:
        return Element.ShapeType.RECT

    return shape_type


def _create_element(raw, design, page, layer_order):
    """Cria um elemento e persiste seus atributos editáveis."""
    element_type = raw.get("type", Element.ElementType.TEXT)
    content = raw.get("content", "")

    if element_type == Element.ElementType.IMAGE:
        image_bytes = raw.get("image_bytes")
        if image_bytes:
            content = _salvar_imagem_extraida(raw, design)

    shape_type = None
    if element_type == Element.ElementType.SHAPE:
        shape_type = _normalizar_tipo_forma(raw)

    font_size = raw.get("fontSize")
    if font_size is not None:
        font_size = round(font_size)

    return Element.objects.create(
        design=design,
        page=page,
        type=element_type,
        content=content,
        posicao_x=int(raw.get("posicao_x") or 0),
        posicao_y=int(raw.get("posicao_y") or 0),
        width=max(int(raw.get("width") or 1), 1),
        heigth=max(int(raw.get("heigth") or 1), 1),
        color=raw.get("color") or "",
        shape_type=shape_type,
        stroke_width=raw.get("stroke_width") or 0,
        stroke_color=raw.get("stroke_color") or "",
        font_size=font_size,
        font_family=raw.get("font_family") or "Poppins",
        font_weight=raw.get("font_weight") or "normal",
        font_style=raw.get("font_style") or "normal",
        text_align=raw.get("text_align") or "left",
        layer_order=layer_order,
    )


def _create_page(design, page_data):
    """Cria uma página do design importado."""
    return DesignPage.objects.create(
        design=design,
        name=page_data["name"],
        page_order=page_data["page_order"],
        width=max(int(page_data.get("width") or 1080), 1),
        height=max(int(page_data.get("height") or 1080), 1),
    )


def _log_element_creation(context, element, raw, page):
    """Registra a criação de um elemento no histórico."""
    history.log_creation(
        context,
        history.TargetRef("element", element.id),
        description=(
            "Elemento criado a partir do arquivo importado "
            f"({raw['type']}) na página {page.page_order + 1}"
        ),
    )


@transaction.atomic
def import_file_into_design(uploaded_file, design, user):
    """Importa um arquivo em um design, preservando páginas e elementos."""
    ext = os.path.splitext(uploaded_file.name)[1].lower()

    if ext not in SUPPORTED_EXTENSIONS:
        raise UnsupportedFileType(
            f"Tipo de arquivo não suportado: {ext}"
        )

    tmp_path = None

    try:
        with tempfile.NamedTemporaryFile(
            delete=False,
            suffix=ext,
        ) as tmp:
            for chunk in uploaded_file.chunks():
                tmp.write(chunk)
            tmp_path = tmp.name

        extracted_pages = _extract_pages(tmp_path, ext)
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)

    if not extracted_pages:
        extracted_pages = [{
            "name": "Página 1",
            "page_order": 0,
            "width": 1080,
            "height": 1080,
            "elements": [],
        }]

    context = history.ChangeContext(
        user=user,
        design=design,
    )

    for page_data in extracted_pages:
        page = _create_page(design, page_data)

        for layer_order, raw in enumerate(page_data["elements"]):
            element = _create_element(
                raw,
                design,
                page,
                layer_order,
            )

            _log_element_creation(
                context,
                element,
                raw,
                page,
            )

    return (
        extracted_pages[0]["width"],
        extracted_pages[0]["height"],
    )
