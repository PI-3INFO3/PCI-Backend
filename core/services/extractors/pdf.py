import fitz

TITLE_FONT_SIZE_THRESHOLD = 20


def pdf_has_extractable_text(file_path, page_number=0):
    doc = fitz.open(file_path)
    text = doc[page_number].get_text().strip()
    doc.close()
    return len(text) > 0


def _text_block_to_element(block):
    block_text = ""
    max_font_size = 0
    for line in block["lines"]:
        for span in line["spans"]:
            block_text += span["text"]
            max_font_size = max(max_font_size, span["size"])
        block_text += "\n"
    block_text = block_text.strip()

    if not block_text:
        return None

    x0, y0, x1, y1 = block["bbox"]
    is_title = max_font_size >= TITLE_FONT_SIZE_THRESHOLD

    return {
        "type": "title" if is_title else "text",
        "content": block_text,
        "image_bytes": None,
        "image_ext": None,
        "posicao_x": round(x0),
        "posicao_y": round(y0),
        "width": round(x1 - x0),
        "heigth": round(y1 - y0),
        "fontSize": round(max_font_size),
    }


def _extract_text_elements(page):
    elements = []
    for block in page.get_text("dict")["blocks"]:
        if block["type"] != 0:
            continue
        element = _text_block_to_element(block)
        if element is not None:
            elements.append(element)
    return elements


def _image_xref_to_element(doc, page, xref):
    base_image = doc.extract_image(xref)
    rects = page.get_image_rects(xref)
    rect = rects[0] if rects else fitz.Rect(0, 0, 100, 100)

    return {
        "type": "image",
        "content": "",
        "image_bytes": base_image["image"],
        "image_ext": base_image["ext"],
        "posicao_x": round(rect.x0),
        "posicao_y": round(rect.y0),
        "width": round(rect.width),
        "heigth": round(rect.height),
        "fontSize": None,
    }


def _extract_image_elements(doc, page):
    return [
        _image_xref_to_element(doc, page, xref)
        for xref, *_ in page.get_images(full=True)
    ]


def extract_pdf(file_path, page_number=0):
    doc = fitz.open(file_path)
    page = doc[page_number]
    canvas_width = round(page.rect.width)
    canvas_height = round(page.rect.height)

    raw_elements = _extract_text_elements(page) + _extract_image_elements(doc, page)

    doc.close()
    return raw_elements, canvas_width, canvas_height
