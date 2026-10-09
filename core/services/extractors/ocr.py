import io

import fitz
import pytesseract
from PIL import Image

MIN_OCR_CONFIDENCE = 40
TITLE_FONT_SIZE_RATIO = 1.5


def _page_to_image(file_path, page_number=0, zoom=2):
    doc = fitz.open(file_path)
    page = doc[page_number]
    pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom))
    img_bytes = pix.tobytes("png")
    doc.close()
    return Image.open(io.BytesIO(img_bytes)), zoom


def _word_box(ocr_data, index, zoom):
    return (
        ocr_data["left"][index] / zoom,
        ocr_data["top"][index] / zoom,
        ocr_data["width"][index] / zoom,
        ocr_data["height"][index] / zoom,
    )


def _new_block(word, box):
    x, y, w, h = box
    return {
        "type": "text", "content": word, "image_bytes": None, "image_ext": None,
        "posicao_x": round(x), "posicao_y": round(y),
        "width": round(w), "heigth": round(h), "fontSize": round(h),
    }


def _extend_block(block, word, box):
    x, y, w, h = box
    block["content"] += " " + word
    x1 = max(block["posicao_x"] + block["width"], x + w)
    y1 = max(block["posicao_y"] + block["heigth"], y + h)
    block["width"] = round(x1 - block["posicao_x"])
    block["heigth"] = round(y1 - block["posicao_y"])


def _ocr_data_to_elements(ocr_data, zoom):
    elements = []
    current_block = None
    current_block_id = None

    for index in range(len(ocr_data["text"])):
        word = ocr_data["text"][index].strip()
        conf = int(ocr_data["conf"][index]) if ocr_data["conf"][index] != "-1" else -1
        if not word or conf < MIN_OCR_CONFIDENCE:
            continue

        block_id = ocr_data["block_num"][index]
        box = _word_box(ocr_data, index, zoom)

        if block_id != current_block_id:
            if current_block is not None:
                elements.append(current_block)
            current_block_id = block_id
            current_block = _new_block(word, box)
        else:
            _extend_block(current_block, word, box)

    if current_block is not None:
        elements.append(current_block)

    return elements


def _mark_titles(elements):
    if not elements:
        return elements
    avg_font = sum(e["fontSize"] for e in elements) / len(elements)
    for element in elements:
        if element["fontSize"] > avg_font * TITLE_FONT_SIZE_RATIO:
            element["type"] = "title"
    return elements


def extract_with_ocr(file_path, is_pdf, page_number=0, lang="por"):
    if is_pdf:
        image, zoom = _page_to_image(file_path, page_number)
    else:
        image, zoom = Image.open(file_path), 1

    canvas_width = round(image.width / zoom)
    canvas_height = round(image.height / zoom)

    ocr_data = pytesseract.image_to_data(image, lang=lang, output_type=pytesseract.Output.DICT)
    raw_elements = _mark_titles(_ocr_data_to_elements(ocr_data, zoom))

    return raw_elements, canvas_width, canvas_height
