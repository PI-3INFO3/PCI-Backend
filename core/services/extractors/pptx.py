from pptx import Presentation
from pptx.enum.shapes import MSO_SHAPE_TYPE

EMU_PER_PIXEL = 914400 / 96


def _emu_to_px(value):
    return round(value / EMU_PER_PIXEL) if value is not None else 0


def extract_pptx(file_path, slide_index=0):
    prs = Presentation(file_path)
    canvas_width = _emu_to_px(prs.slide_width)
    canvas_height = _emu_to_px(prs.slide_height)
    slide = prs.slides[slide_index]

    raw_elements = []

    for shape in slide.shapes:
        base = {
            "posicao_x": _emu_to_px(shape.left),
            "posicao_y": _emu_to_px(shape.top),
            "width": _emu_to_px(shape.width),
            "heigth": _emu_to_px(shape.height),
        }

        if shape.has_text_frame and shape.text_frame.text.strip():
            font_size = None
            try:
                first_run = shape.text_frame.paragraphs[0].runs[0]
                if first_run.font.size is not None:
                    font_size = first_run.font.size.pt
            except (IndexError, AttributeError):
                pass

            is_title = shape.is_placeholder and shape.placeholder_format.type in {13, 1}

            raw_elements.append({
                **base,
                "type": "title" if is_title else "text",
                "content": shape.text_frame.text,
                "image_bytes": None,
                "image_ext": None,
                "fontSize": font_size or (32 if is_title else 16),
            })

        elif shape.shape_type == MSO_SHAPE_TYPE.PICTURE:
            raw_elements.append({
                **base,
                "type": "image",
                "content": "",
                "image_bytes": shape.image.blob,
                "image_ext": shape.image.ext,
                "fontSize": None,
            })

    return raw_elements, canvas_width, canvas_height
