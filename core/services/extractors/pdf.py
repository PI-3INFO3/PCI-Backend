import fitz

TITLE_FONT_SIZE_THRESHOLD = 20
POINTS_PER_INCH = 72
PIXELS_PER_INCH = 96
POINTS_TO_PIXELS = PIXELS_PER_INCH / POINTS_PER_INCH
MIN_ELEMENT_SIZE = 1


def _points_to_pixels(value):
    """Converte pontos PDF em pixels."""
    return round(value * POINTS_TO_PIXELS)


def pdf_has_extractable_text(file_path, page_number=0):
    """Verifica se a página do PDF contém texto extraível."""
    with fitz.open(file_path) as document:
        if page_number < 0 or page_number >= len(document):
            return False

        return bool(document[page_number].get_text().strip())


def _text_block_to_element(block):
    """Converte um bloco de texto do PDF em um elemento do editor."""
    text_parts = []
    max_font_size = 0

    for line in block.get("lines", []):
        line_parts = []

        for span in line.get("spans", []):
            text = span.get("text", "")

            if text:
                line_parts.append(text)

            max_font_size = max(
                max_font_size,
                span.get("size", 0),
            )

        line_text = "".join(line_parts)

        if line_text:
            text_parts.append(line_text)

    content = "\n".join(text_parts).strip()

    if not content:
        return None

    x0, y0, x1, y1 = block["bbox"]
    is_title = max_font_size >= TITLE_FONT_SIZE_THRESHOLD

    return {
        "type": "title" if is_title else "text",
        "content": content,
        "image_bytes": None,
        "image_ext": None,
        "posicao_x": _points_to_pixels(x0),
        "posicao_y": _points_to_pixels(y0),
        "width": max(
            _points_to_pixels(x1 - x0),
            MIN_ELEMENT_SIZE,
        ),
        "heigth": max(
            _points_to_pixels(y1 - y0),
            MIN_ELEMENT_SIZE,
        ),
        "fontSize": round(max_font_size * POINTS_TO_PIXELS),
    }


def _extract_text_elements(page):
    """Extrai os blocos de texto de uma página."""
    elements = []

    for block in page.get_text("dict").get("blocks", []):
        if block.get("type") != 0:
            continue

        element = _text_block_to_element(block)

        if element is not None:
            elements.append(element)

    return elements


def _image_xref_to_element(document, rect, xref):
    """Converte uma ocorrência de imagem do PDF em elemento."""
    image_data = document.extract_image(xref)

    return {
        "type": "image",
        "content": "",
        "image_bytes": image_data["image"],
        "image_ext": image_data["ext"],
        "posicao_x": _points_to_pixels(rect.x0),
        "posicao_y": _points_to_pixels(rect.y0),
        "width": max(
            _points_to_pixels(rect.width),
            MIN_ELEMENT_SIZE,
        ),
        "heigth": max(
            _points_to_pixels(rect.height),
            MIN_ELEMENT_SIZE,
        ),
        "fontSize": None,
    }


def _extract_image_elements(document, page):
    """
    Extrai as ocorrências visuais das imagens.

    Remove xrefs repetidos da lista inicial, mas preserva posições diferentes
    quando a mesma imagem aparece legitimamente mais de uma vez na página.
    """
    elements = []

    image_xrefs = dict.fromkeys(
        xref
        for xref, *_ in page.get_images(full=True)
    )

    for xref in image_xrefs:
        for rect in page.get_image_rects(xref):
            if rect.is_empty or rect.is_infinite:
                continue

            elements.append(
                _image_xref_to_element(document, rect, xref)
            )

    return elements


def extract_pdf(file_path, page_number=0):
    """Extrai texto e imagens de uma página específica do PDF."""
    with fitz.open(file_path) as document:
        if page_number < 0 or page_number >= len(document):
            raise IndexError("O índice da página está fora dos limites.")

        page = document[page_number]

        canvas_width = _points_to_pixels(page.rect.width)
        canvas_height = _points_to_pixels(page.rect.height)

        text_elements = _extract_text_elements(page)
        image_elements = _extract_image_elements(document, page)

        raw_elements = text_elements + image_elements

    return raw_elements, canvas_width, canvas_height
