from io import BytesIO

from PIL import Image as PILImage
from pptx import Presentation
from pptx.enum.shapes import MSO_SHAPE_TYPE
from pptx.enum.text import PP_ALIGN
from pptx.oxml.ns import qn

EMU_PER_PIXEL = 914400 / 96
POINTS_PER_INCH = 72
PIXELS_PER_INCH = 96

ALPHA_MODIFIER_SCALE = 100000
DEFAULT_TITLE_FONT_SIZE = 32
DEFAULT_BODY_FONT_SIZE = 16

TITLE_PLACEHOLDER_TYPES = {1, 3}

TEXT_ALIGNMENT = {
    PP_ALIGN.LEFT: "left",
    PP_ALIGN.CENTER: "center",
    PP_ALIGN.RIGHT: "right",
    PP_ALIGN.JUSTIFY: "justify",
}

EXTENSION_BY_CONTENT_TYPE = {
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/jpg": "jpg",
}


def _emu_to_px(value):
    """Converte EMUs do PowerPoint em pixels."""
    if value is None:
        return 0

    return round(value / EMU_PER_PIXEL)


def _get_base(shape, transform=(0, 0, 1, 1)):
    """Calcula posição e dimensões, considerando grupos."""
    offset_x, offset_y, scale_x, scale_y = transform

    left = offset_x + shape.left * scale_x
    top = offset_y + shape.top * scale_y
    width = shape.width * scale_x
    height = shape.height * scale_y

    return {
        "posicao_x": _emu_to_px(left),
        "posicao_y": _emu_to_px(top),
        "width": max(_emu_to_px(width), 1),
        "heigth": max(_emu_to_px(height), 1),
    }


def _get_text_alignment(paragraph):
    return TEXT_ALIGNMENT.get(paragraph.alignment, "left")


def _is_title(shape):
    """Identifica títulos e subtítulos definidos como placeholders."""
    try:
        return (
            shape.is_placeholder
            and shape.placeholder_format.type
            in TITLE_PLACEHOLDER_TYPES
        )
    except (AttributeError, ValueError):
        return False


def _color_to_hex(color):
    """Converte uma cor RGB para hexadecimal."""
    try:
        rgb = color.rgb
    except (AttributeError, ValueError, TypeError):
        return ""

    if rgb is None:
        return ""

    return f"#{rgb}"


def _get_font_properties(shape):
    properties = {
        "fontSize": None,
        "font_family": "Poppins",
        "font_weight": "normal",
        "font_style": "normal",
        "color": "",
    }

    try:
        paragraphs = shape.text_frame.paragraphs
    except (AttributeError, ValueError):
        return properties

    for paragraph in paragraphs:
        for run in paragraph.runs:
            font = run.font

            if font.size is not None:
                properties["fontSize"] = round(
                    font.size.pt
                    * PIXELS_PER_INCH
                    / POINTS_PER_INCH
                )

            if font.name:
                properties["font_family"] = font.name

            if font.bold:
                properties["font_weight"] = "bold"

            if font.italic:
                properties["font_style"] = "italic"

            properties["color"] = _color_to_hex(font.color)

            return properties

    return properties


def _extract_text_element(shape, base):
    if not shape.has_text_frame:
        return None

    content = shape.text_frame.text.strip()

    if not content:
        return None

    paragraphs = shape.text_frame.paragraphs

    alignment = (
        _get_text_alignment(paragraphs[0])
        if paragraphs
        else "left"
    )

    is_title = _is_title(shape)
    properties = _get_font_properties(shape)

    return {
        **base,
        **properties,
        "type": "title" if is_title else "text",
        "content": content,
        "image_bytes": None,
        "image_ext": None,
        "text_align": alignment,
        "fontSize": properties["fontSize"] or (
            DEFAULT_TITLE_FONT_SIZE
            if is_title
            else DEFAULT_BODY_FONT_SIZE
        ),
    }


def _get_image_extension(image_part):
    content_type = (
        getattr(image_part, "content_type", "") or ""
    ).lower()

    extension = EXTENSION_BY_CONTENT_TYPE.get(
        content_type
    )

    if extension:
        return extension

    filename = (
        getattr(image_part, "filename", "") or ""
    )

    if "." not in filename:
        return "png"

    extension = filename.rsplit(".", 1)[-1].lower()

    if extension == "jpeg":
        extension = "jpg"

    if extension not in {"png", "jpg"}:
        return None

    return extension


def _get_related_image_part(shape, relationship_id):
    try:
        image_part = shape.part.related_part(relationship_id)
    except (KeyError, AttributeError, ValueError, TypeError):
        image_part = None

    return image_part


def _get_embedded_image_part(shape):
    image_part = None

    shape_properties = getattr(
        shape._element,
        "spPr",
        None,
    )

    if shape_properties is not None:
        blip_fill = shape_properties.find(
            qn("a:blipFill")
        )

        if blip_fill is not None:
            blip = blip_fill.find(
                qn("a:blip")
            )

            if blip is not None:
                relationship_id = blip.get(
                    qn("r:embed")
                )

                if relationship_id:
                    image_part = _get_related_image_part(
                        shape,
                        relationship_id,
                    )

    return image_part


def _get_alpha_modifier(blip):
    alpha_fix = blip.find(qn("a:alphaModFix"))

    if alpha_fix is None:
        return None

    try:
        return int(
            alpha_fix.get(
                "amt",
                str(ALPHA_MODIFIER_SCALE),
            )
        )
    except (TypeError, ValueError):
        return None


def _apply_image_opacity(image_bytes, amount):
    """Aplica o modificador de transparência usando Pillow."""
    if amount is None or amount >= ALPHA_MODIFIER_SCALE:
        return image_bytes

    if amount <= 0:
        factor = 0
    else:
        factor = amount / ALPHA_MODIFIER_SCALE

    with PILImage.open(BytesIO(image_bytes)) as source:
        image = source.convert("RGBA")

    alpha = image.getchannel("A")

    alpha = alpha.point(
        lambda value: round(value * factor)
    )

    image.putalpha(alpha)

    output = BytesIO()

    image.save(output, format="PNG")

    return output.getvalue()


def _extract_embedded_image(shape, base):
    """
    Extrai uma imagem usada como preenchimento de uma forma livre,
    forma automática ou outro objeto compatível do PowerPoint.
    """
    image_part = _get_embedded_image_part(shape)

    if image_part is None:
        return None

    image_bytes = image_part.blob
    extension = _get_image_extension(image_part)

    if extension is None:
        return None

    try:
        blip = shape._element.spPr.find(
            qn("a:blipFill")
        ).find(qn("a:blip"))

        amount = _get_alpha_modifier(blip)

        if amount is not None and extension == "png":
            image_bytes = _apply_image_opacity(
                image_bytes,
                amount,
            )

    except (
        AttributeError,
        TypeError,
        ValueError,
        OSError,
    ) as exc:
        print(
            "[PPTX] Não foi possível ajustar a transparência "
            f"da imagem: {exc}"
        )

    return {
        **base,
        "type": "image",
        "content": "",
        "image_bytes": image_bytes,
        "image_ext": extension,
        "fontSize": None,
        "color": "",
    }


def _extract_picture(shape, base):
    """Extrai uma imagem do tipo PICTURE."""
    try:
        image = shape.image
    except (AttributeError, ValueError, TypeError):
        return _extract_embedded_image(shape, base)

    extension = image.ext or "png"

    if extension.lower() == "jpeg":
        extension = "jpg"

    return {
        **base,
        "type": "image",
        "content": "",
        "image_bytes": image.blob,
        "image_ext": extension,
        "fontSize": None,
        "color": "",
    }


def _get_fill_color(shape):
    try:
        fill = shape.fill

        if fill.type is None:
            return ""

        return _color_to_hex(fill.fore_color)

    except (AttributeError, ValueError, TypeError):
        return ""


def _get_line_color(shape):
    try:
        line = shape.line

        if line.fill.type is None:
            return ""

        return _color_to_hex(line.color)

    except (AttributeError, ValueError, TypeError):
        return ""


def _get_line_width(shape):
    try:
        width = shape.line.width
    except (AttributeError, ValueError, TypeError):
        return 0

    if width is None:
        return 0

    return max(round(width / EMU_PER_PIXEL), 0)


def _get_shape_type(shape):
    try:
        shape_name = str(shape.auto_shape_type).lower()
    except (AttributeError, ValueError, TypeError):
        shape_name = ""

    if "oval" in shape_name or "ellipse" in shape_name:
        return "circle"

    if "triangle" in shape_name:
        return "triangle"

    if "star" in shape_name:
        return "star"

    return "rect"


def _extract_shape_element(shape, base):
    """Extrai as propriedades básicas de uma forma vetorial."""
    fill_color = _get_fill_color(shape)
    stroke_color = _get_line_color(shape)

    is_line = shape.shape_type == MSO_SHAPE_TYPE.LINE

    if not fill_color and not stroke_color and not is_line:
        return None

    return {
        **base,
        "type": "shape",
        "content": "",
        "image_bytes": None,
        "image_ext": None,
        "color": fill_color,
        "shape_type": (
            "rect"
            if is_line
            else _get_shape_type(shape)
        ),
        "stroke_color": stroke_color,
        "stroke_width": _get_line_width(shape),
        "fontSize": None,
    }


def _transform_for_group(shape, transform):
    """Converte as coordenadas dos filhos de um grupo para o slide."""
    offset_x, offset_y, scale_x, scale_y = transform

    group_left = (
        offset_x + shape.left * scale_x
    )

    group_top = (
        offset_y + shape.top * scale_y
    )

    group_width = shape.width * scale_x
    group_height = shape.height * scale_y

    try:
        xfrm = shape._element.grpSpPr.xfrm

        child_offset_x = xfrm.chOff.x
        child_offset_y = xfrm.chOff.y

        child_width = xfrm.chExt.cx
        child_height = xfrm.chExt.cy

    except AttributeError:
        return (
            group_left,
            group_top,
            1,
            1,
        )

    if not child_width or not child_height:
        return (
            group_left,
            group_top,
            1,
            1,
        )

    child_scale_x = group_width / child_width
    child_scale_y = group_height / child_height

    return (
        group_left - child_offset_x * child_scale_x,
        group_top - child_offset_y * child_scale_y,
        child_scale_x,
        child_scale_y,
    )


def _extract_group(shape, output, transform):
    """Percorre recursivamente as formas de um grupo."""
    child_transform = _transform_for_group(
        shape,
        transform,
    )

    for child in shape.shapes:
        _extract_one(
            child,
            output,
            child_transform,
        )


def _process_shape(shape, output, transform):
    base = _get_base(shape, transform)

    if shape.shape_type == MSO_SHAPE_TYPE.GROUP:
        _extract_group(shape, output, transform)
        return

    if shape.shape_type == MSO_SHAPE_TYPE.PICTURE:
        element = _extract_picture(shape, base)

        if element is not None:
            output.append(element)

        return

    # Algumas ilustrações são imagens usadas como preenchimento
    # de formas livres, e não objetos PICTURE.
    element = _extract_embedded_image(shape, base)

    if element is not None:
        output.append(element)
        return

    if shape.shape_type in {
        MSO_SHAPE_TYPE.AUTO_SHAPE,
        MSO_SHAPE_TYPE.LINE,
        MSO_SHAPE_TYPE.FREEFORM,
    }:
        shape_element = _extract_shape_element(
            shape,
            base,
        )

        if shape_element is not None:
            output.append(shape_element)

    text_element = _extract_text_element(
        shape,
        base,
    )

    if text_element is not None:
        output.append(text_element)


def _extract_one(
    shape,
    output,
    transform=(0, 0, 1, 1),
):
    try:
        _process_shape(
            shape,
            output,
            transform,
        )
    except Exception as exc:
        print(
            "[PPTX] Falha ao extrair objeto: "
            f"{exc}"
        )


def _extract_slide(
    slide,
    canvas_width,
    canvas_height,
):
    elements = []

    for shape in slide.shapes:
        _extract_one(shape, elements)

    return (
        elements,
        canvas_width,
        canvas_height,
    )


def extract_pptx(file_path, slide_index=0):
    """Extrai os elementos de um slide específico."""
    presentation = Presentation(file_path)

    canvas_width = _emu_to_px(
        presentation.slide_width
    )

    canvas_height = _emu_to_px(
        presentation.slide_height
    )

    if not presentation.slides:
        return [], canvas_width, canvas_height

    if not 0 <= slide_index < len(presentation.slides):
        raise IndexError(
            "O índice do slide está fora dos limites."
        )

    return _extract_slide(
        presentation.slides[slide_index],
        canvas_width,
        canvas_height,
    )


def extract_pptx_pages(file_path):
    """Extrai todos os slides em formato de páginas."""
    presentation = Presentation(file_path)

    canvas_width = _emu_to_px(
        presentation.slide_width
    )

    canvas_height = _emu_to_px(
        presentation.slide_height
    )

    pages = []

    for index, slide in enumerate(presentation.slides):
        elements, width, height = _extract_slide(
            slide,
            canvas_width,
            canvas_height,
        )

        pages.append({
            "name": f"Slide {index + 1}",
            "page_order": index,
            "width": width,
            "height": height,
            "elements": elements,
        })

    return pages
