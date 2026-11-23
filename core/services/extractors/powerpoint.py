import math
import re
from dataclasses import dataclass
from io import BytesIO
from xml.etree import ElementTree

from PIL import Image as PILImage
from pptx import Presentation
from pptx.enum.shapes import MSO_SHAPE_TYPE
from pptx.enum.text import PP_ALIGN
from pptx.oxml.ns import qn

from core.services.symbols import MAX_SYMBOL_PATH_LENGTH, MIN_SYMBOL_PATH_LENGTH

MIN_POLYGON_POINTS = 4
ELLIPSE_CURVE_COUNT = 4

EMU_PER_PIXEL = 914400 / 96
POINTS_PER_INCH = 72
PIXELS_PER_INCH = 96

ALPHA_MODIFIER_SCALE = 100000
QUARTER_TURN_DEGREES = 90
HALF_TURN_DEGREES = 180
DEFAULT_TITLE_FONT_SIZE = 32
DEFAULT_BODY_FONT_SIZE = 16

TITLE_PLACEHOLDER_TYPES = {1, 3}

TEXT_ALIGNMENT = {
    PP_ALIGN.LEFT: 'left',
    PP_ALIGN.CENTER: 'center',
    PP_ALIGN.RIGHT: 'right',
    PP_ALIGN.JUSTIFY: 'justify',
}

EXTENSION_BY_CONTENT_TYPE = {
    'image/png': 'png',
    'image/jpeg': 'jpg',
    'image/jpg': 'jpg',
    'image/svg+xml': 'svg',
}


def _emu_to_px(value):
    """Converte EMUs do PowerPoint em pixels."""
    if value is None:
        return 0

    return round(value / EMU_PER_PIXEL)


# Matriz afim (a, b, c, d, tx, ty):
# (x, y) -> (a*x + c*y + tx, b*x + d*y + ty).
IDENTITY_TRANSFORM = (1., 0., 0., 1., 0., 0.)


def _compose(outer, inner):
    a, b, c, d, tx, ty = outer
    e, f, g, h, ux, uy = inner
    return (
        a * e + c * f, b * e + d * f,
        a * g + c * h, b * g + d * h,
        a * ux + c * uy + tx, b * ux + d * uy + ty,
    )


def _transform_point(matrix, x, y):
    a, b, c, d, tx, ty = matrix
    return a * x + c * y + tx, b * x + d * y + ty


def _shape_rotation(shape):
    try:
        return float(shape.rotation or 0) % 360
    except (TypeError, ValueError):
        return 0.


def _scaled_axes(shape, transform):
    """Calcula largura, altura e rotação após a transformação do grupo."""
    angle = math.radians(_shape_rotation(shape))
    a, b, c, d, _, _ = transform
    axis_x = (
        a * math.cos(angle) + c * math.sin(angle),
        b * math.cos(angle) + d * math.sin(angle),
    )
    axis_y = (
        -a * math.sin(angle) + c * math.cos(angle),
        -b * math.sin(angle) + d * math.cos(angle),
    )
    width = max(float(shape.width) * math.hypot(*axis_x), 1.)
    height = max(float(shape.height) * math.hypot(*axis_y), 1.)
    return width, height, math.atan2(axis_x[1], axis_x[0])


def _get_base(shape, transform=IDENTITY_TRANSFORM):
    """Converte centro e rotação do PPTX para a origem superior esquerda do Fabric."""
    center_x, center_y = _transform_point(
        transform,
        shape.left + float(shape.width) / 2,
        shape.top + float(shape.height) / 2,
    )
    width, height, rotation = _scaled_axes(shape, transform)
    left = center_x - (width * math.cos(rotation) - height * math.sin(rotation)) / 2
    top = center_y - (width * math.sin(rotation) + height * math.cos(rotation)) / 2
    return {
        'rotation': math.degrees(rotation) % 360,
        'posicao_x': _emu_to_px(left),
        'posicao_y': _emu_to_px(top),
        'width': max(_emu_to_px(width), 1),
        'heigth': max(_emu_to_px(height), 1),
    }


def _get_text_alignment(paragraph):
    return TEXT_ALIGNMENT.get(paragraph.alignment, 'left')


def _is_title(shape):
    """Identifica títulos e subtítulos definidos como placeholders."""
    try:
        return (
            shape.is_placeholder
            and shape.placeholder_format.type in TITLE_PLACEHOLDER_TYPES
        )
    except (AttributeError, ValueError):
        return False


def _color_to_hex(color):
    """Converte uma cor RGB para hexadecimal."""
    try:
        rgb = color.rgb
    except (AttributeError, ValueError, TypeError):
        return ''

    if rgb is None:
        return ''

    return f'#{rgb}'


def _get_font_properties(shape):
    properties = {
        'fontSize': None,
        'font_family': 'Poppins',
        'font_weight': 'normal',
        'font_style': 'normal',
        'underline': False,
        'color': '',
    }

    try:
        paragraphs = shape.text_frame.paragraphs
    except (AttributeError, ValueError):
        return properties

    for paragraph in paragraphs:
        for run in paragraph.runs:
            font = run.font

            if font.size is not None:
                properties['fontSize'] = round(
                    font.size.pt * PIXELS_PER_INCH / POINTS_PER_INCH
                )

            if font.name:
                properties['font_family'] = font.name

            if font.bold:
                properties['font_weight'] = 'bold'

            if font.italic:
                properties['font_style'] = 'italic'
            if font.underline:
                properties['underline'] = True

            properties['color'] = _color_to_hex(font.color)

            return properties

    return properties


def _extract_text_element(shape, base):
    if not shape.has_text_frame:
        return None

    content = shape.text_frame.text.strip()

    if not content:
        return None

    paragraphs = shape.text_frame.paragraphs

    alignment = _get_text_alignment(paragraphs[0]) if paragraphs else 'left'

    is_title = _is_title(shape)
    properties = _get_font_properties(shape)

    return {
        **base,
        **properties,
        'type': 'title' if is_title else 'text',
        'content': content,
        'image_bytes': None,
        'image_ext': None,
        'text_align': alignment,
        'fontSize': properties['fontSize'] or (
            DEFAULT_TITLE_FONT_SIZE if is_title else DEFAULT_BODY_FONT_SIZE
        ),
    }


def _get_image_extension(image_part):
    content_type = (getattr(image_part, 'content_type', '') or '').lower()

    extension = EXTENSION_BY_CONTENT_TYPE.get(content_type)

    if extension:
        return extension

    filename = getattr(image_part, 'filename', '') or ''

    if '.' not in filename:
        return 'png'

    extension = filename.rsplit('.', 1)[-1].lower()

    if extension == 'jpeg':
        extension = 'jpg'

    if extension not in {'png', 'jpg', 'svg'}:
        return None

    return extension


def _svg_polygon_path(node, tag):
    points = node.attrib.get('points', '').strip()
    pairs = re.findall(r'[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?', points)
    if len(pairs) < MIN_POLYGON_POINTS or len(pairs) % 2:
        return ''
    commands = [f'M {pairs[0]} {pairs[1]}']
    commands.extend(
        f'L {pairs[index]} {pairs[index + 1]}'
        for index in range(2, len(pairs), 2)
    )
    if tag == 'polygon':
        commands.append('Z')
    return ' '.join(commands)


def _svg_geometry(root):
    paths = []
    for node in root.iter():
        tag = node.tag.rsplit('}', 1)[-1].lower()
        if tag == 'path':
            path = node.attrib.get('d', '').strip()
        elif tag in {'polygon', 'polyline'}:
            path = _svg_polygon_path(node, tag)
        else:
            continue
        if path:
            paths.append(path)
    return ' '.join(paths).strip()


def _svg_as_symbol(image_bytes, base, name='Símbolo SVG'):
    """Preserva somente caminhos SVG simples como vetores editáveis."""
    if not image_bytes or len(image_bytes) > 1024 * 1024:
        return None
    if b'<!DOCTYPE' in image_bytes.upper() or b'<!ENTITY' in image_bytes.upper():
        return None
    try:
        root = ElementTree.fromstring(image_bytes)
    except (ValueError, ElementTree.ParseError):
        return None
    tags = [node.tag.rsplit('}', 1)[-1].lower() for node in root.iter()]
    unsafe_tags = {'script', 'foreignobject', 'image', 'use', 'text', 'animate'}
    if any(tag in unsafe_tags for tag in tags):
        return None
    path_data = _svg_geometry(root)
    valid_size = MIN_SYMBOL_PATH_LENGTH <= len(path_data) <= MAX_SYMBOL_PATH_LENGTH
    valid_path = re.fullmatch(
        r'[MmLlHhVvCcSsQqTtAaZz0-9\s,\.\-+eE]+', path_data
    )
    if not valid_size or not valid_path:
        return None
    return {
        **base,
        'type': 'symbol',
        'symbol_name': name,
        'symbol_path_data': path_data,
        'content': '',
        'color': '#FF5700',
        'stroke_color': '',
        'stroke_width': 0,
    }


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
        'spPr',
        None,
    )

    if shape_properties is not None:
        blip_fill = shape_properties.find(qn('a:blipFill'))

        if blip_fill is not None:
            blip = blip_fill.find(qn('a:blip'))

            if blip is not None:
                relationship_id = blip.get(qn('r:embed'))

                if relationship_id:
                    image_part = _get_related_image_part(
                        shape,
                        relationship_id,
                    )

    return image_part


def _get_alpha_modifier(blip):
    alpha_fix = blip.find(qn('a:alphaModFix'))

    if alpha_fix is None:
        return None

    try:
        return int(
            alpha_fix.get(
                'amt',
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
        image = source.convert('RGBA')

    alpha = image.getchannel('A')

    alpha = alpha.point(lambda value: round(value * factor))

    image.putalpha(alpha)

    output = BytesIO()

    image.save(output, format='PNG')

    return output.getvalue()


def _xml_flag(element, key):
    if element is None:
        return False
    return str(element.get(key, '')).lower() in {'1', 'true'}


def _image_fill(shape):
    """Obtém <a:blipFill> de imagens e de preenchimentos."""
    element = shape._element
    picture_fill = getattr(element, 'blipFill', None)
    if picture_fill is not None:
        return picture_fill
    props = getattr(element, 'spPr', None)
    if props is not None:
        return props.find(qn('a:blipFill'))
    return None


def _image_crop(shape, fill):
    # Picture expõe crop_left/top/right/bottom pela python-pptx.
    if shape.shape_type == MSO_SHAPE_TYPE.PICTURE:
        try:
            return tuple(float(getattr(shape, f'crop_{edge}'))
                         for edge in ('left', 'top', 'right', 'bottom'))
        except (AttributeError, ValueError, TypeError):
            pass
    src = fill.find(qn('a:srcRect')) if fill is not None else None
    if src is None:
        return (0., 0., 0., 0.)
    return tuple(float(src.get(edge, 0)) / ALPHA_MODIFIER_SCALE
                 for edge in ('l', 't', 'r', 'b'))


def _image_fill_rect(fill):
    """Lê a área de esticamento da imagem dentro da forma PPTX.

    Valores negativos em <a:fillRect> expandem a imagem para fora da forma.
    A parte excedente não deve ser mostrada (ex.: rolos do pergaminho).
    """
    if fill is None:
        return (0., 0., 0., 0.)
    stretch = fill.find(qn('a:stretch'))
    rect = stretch.find(qn('a:fillRect')) if stretch is not None else None
    if rect is None:
        return (0., 0., 0., 0.)
    try:
        return tuple(
            float(rect.get(edge, 0)) / ALPHA_MODIFIER_SCALE
            for edge in ('l', 't', 'r', 'b')
        )
    except (TypeError, ValueError):
        return (0., 0., 0., 0.)


def _apply_fill_rect(image, fill_rect):
    """Estica e recorta o bitmap exatamente na caixa da forma PPTX."""
    if not any(fill_rect):
        return image
    left, top, right, bottom = fill_rect
    width = image.width
    height = image.height
    target_width = max(round(width * (1 - left - right)), 1)
    target_height = max(round(height * (1 - top - bottom)), 1)
    scaled = image.resize(
        (target_width, target_height),
        PILImage.Resampling.LANCZOS,
    )
    result = PILImage.new('RGBA', (width, height), (0, 0, 0, 0))
    result.paste(scaled, (round(width * left), round(height * top)))
    return result


def _image_flip(shape, transform):
    props = getattr(shape._element, 'spPr', None)
    xfrm = getattr(props, 'xfrm', None)
    flip_h = _xml_flag(xfrm, 'flipH')
    flip_v = _xml_flag(xfrm, 'flipV')
    a, b, c, d, _, _ = transform
    # Uma reflexão do grupo inverte a orientação do eixo Y em coordenadas
    # locais (o ângulo de _get_base já acompanha o eixo X).
    if a * d - b * c < 0:
        flip_v = not flip_v
    return flip_h, flip_v


@dataclass(frozen=True)
class ImageAdjustments:
    """Configurações visuais de uma imagem incorporada no PowerPoint."""
    crop: tuple[float, float, float, float]
    flip_h: bool
    flip_v: bool
    opacity: int | None = None
    fill_rect: tuple[float, float, float, float] = (0., 0., 0., 0.)


def _crop_image(image, crop):
    """Aplica o retângulo de origem da imagem sem cortar fora da área válida."""
    left, top, right, bottom = (
        max(0., min(float(value), .999)) for value in crop
    )
    x0 = round(image.width * left)
    y0 = round(image.height * top)
    x1 = round(image.width * (1 - right))
    y1 = round(image.height * (1 - bottom))
    if x1 <= x0 or y1 <= y0:
        return image
    return image.crop((x0, y0, x1, y1))


def _apply_raster_adjustments(image, adjustments):
    if any(adjustments.crop):
        image = _crop_image(image, adjustments.crop)
    image = _apply_fill_rect(image, adjustments.fill_rect)
    if adjustments.flip_h:
        image = image.transpose(PILImage.Transpose.FLIP_LEFT_RIGHT)
    if adjustments.flip_v:
        image = image.transpose(PILImage.Transpose.FLIP_TOP_BOTTOM)
    if adjustments.opacity is not None and adjustments.opacity < ALPHA_MODIFIER_SCALE:
        factor = max(adjustments.opacity, 0) / ALPHA_MODIFIER_SCALE
        image.putalpha(image.getchannel('A').point(lambda value: round(value * factor)))
    return image


def _prepare_image(image_bytes, extension, adjustments):
    """Aplica apenas alterações visuais, preservando arquivos idênticos."""
    changed = (
        any(adjustments.crop)
        or any(adjustments.fill_rect)
        or adjustments.flip_h
        or adjustments.flip_v
        or (
            adjustments.opacity is not None
            and adjustments.opacity < ALPHA_MODIFIER_SCALE
        )
    )
    if not changed and extension.lower() in {'png', 'jpg', 'jpeg', 'webp'}:
        return image_bytes, 'jpg' if extension.lower() == 'jpeg' else extension.lower()

    with PILImage.open(BytesIO(image_bytes)) as source:
        image = source.convert('RGBA')
    image = _apply_raster_adjustments(image, adjustments)
    result = BytesIO()
    image.save(result, format='PNG')
    return result.getvalue(), 'png'


def _svg_fallback_rotated_fill(shape):
    """Identifica bitmap de apoio de SVG em forma livre girada a 90/270°."""
    if shape.shape_type != MSO_SHAPE_TYPE.FREEFORM:
        return False
    if round(_shape_rotation(shape)) % HALF_TURN_DEGREES != QUARTER_TURN_DEGREES:
        return False
    fill = _image_fill(shape)
    return fill is not None and any(
        child.tag.endswith('svgBlip') for child in fill.iter()
    )


def _upright_fill_box(base):
    """Transforma a caixa girada na caixa visual do preenchimento SVG."""
    width = base['width']
    height = base['heigth']
    rotation = math.radians(base['rotation'])
    cosine = math.cos(rotation)
    sine = math.sin(rotation)
    x0 = base['posicao_x']
    y0 = base['posicao_y']
    corners = (
        (x0, y0),
        (x0 + width * cosine, y0 + width * sine),
        (x0 - height * sine, y0 + height * cosine),
        (x0 + width * cosine - height * sine,
         y0 + width * sine + height * cosine),
    )
    xs = [point[0] for point in corners]
    ys = [point[1] for point in corners]
    return {
        **base,
        'posicao_x': round(min(xs)),
        'posicao_y': round(min(ys)),
        'width': max(round(max(xs) - min(xs)), 1),
        'heigth': max(round(max(ys) - min(ys)), 1),
        'rotation': 0,
    }


def _rotate_svg_fallback(shape, image_bytes):
    """Gira o conteúdo do preenchimento sem girar novamente sua caixa visual."""
    angle = round(_shape_rotation(shape)) % 360
    direction = (
        PILImage.Transpose.ROTATE_90
        if angle == 3 * QUARTER_TURN_DEGREES
        else PILImage.Transpose.ROTATE_270
    )
    with PILImage.open(BytesIO(image_bytes)) as source:
        rotated = source.convert('RGBA').transpose(direction)
    output = BytesIO()
    rotated.save(output, format='PNG')
    return output.getvalue(), 'png'


def _extract_raster(shape, base, image_bytes, extension, transform):
    if extension.lower() == 'svg':
        return _svg_as_symbol(image_bytes, base, getattr(shape, 'name', 'Símbolo SVG'))
    # O PNG de fallback de SVG é preenchimento de forma livre rotacionada.
    # Girar o bitmap e preservar flipV evita uma emenda vertical no pergaminho.
    # Imagens comuns não passam por este tratamento.
    is_upright_fallback = _svg_fallback_rotated_fill(shape)
    if is_upright_fallback:
        base = _upright_fill_box(base)
    fill = _image_fill(shape)
    blip = fill.find(qn('a:blip')) if fill is not None else None
    opacity = _get_alpha_modifier(blip) if blip is not None else None
    crop = _image_crop(shape, fill)
    fill_rect = _image_fill_rect(fill)
    flip_h, flip_v = _image_flip(shape, transform)
    try:
        adjustments = ImageAdjustments(
            crop=crop,
            flip_h=flip_h,
            flip_v=flip_v,
            opacity=opacity,
            fill_rect=fill_rect,
        )
        image_bytes, extension = _prepare_image(image_bytes, extension, adjustments)
        if is_upright_fallback:
            image_bytes, extension = _rotate_svg_fallback(shape, image_bytes)
    except (OSError, ValueError, TypeError) as exc:
        print(f'[PPTX] Imagem não pôde ser ajustada: {exc}')
        return None
    return {
        **base, 'type': 'image', 'content': '',
        'image_bytes': image_bytes, 'image_ext': extension,
        'fontSize': None, 'color': '',
    }


def _extract_embedded_image(shape, base, transform=IDENTITY_TRANSFORM):
    """Extrai imagens de preenchimento, preservando recorte e inversões."""
    image_part = _get_embedded_image_part(shape)
    if image_part is None:
        return None
    extension = _get_image_extension(image_part)
    if extension is None:
        return None
    return _extract_raster(shape, base, image_part.blob, extension, transform)


def _extract_picture(shape, base, transform=IDENTITY_TRANSFORM):
    try:
        image = shape.image
    except (AttributeError, ValueError, TypeError):
        return _extract_embedded_image(shape, base, transform)
    return _extract_raster(shape, base, image.blob, image.ext or 'png', transform)


def _get_fill_color(shape):
    try:
        fill = shape.fill

        if fill.type is None:
            return ''

        return _color_to_hex(fill.fore_color)

    except (AttributeError, ValueError, TypeError):
        return ''


def _get_line_color(shape):
    try:
        line = shape.line

        if line.fill.type is None:
            return ''

        return _color_to_hex(line.color)

    except (AttributeError, ValueError, TypeError):
        return ''


def _get_line_width(shape):
    try:
        width = shape.line.width
    except (AttributeError, ValueError, TypeError):
        return 0

    if width is None:
        return 0

    return max(round(width / EMU_PER_PIXEL), 0)


def _ellipse_path_geometry(path):
    """Lê as curvas da forma livre, mantendo o try com até cinco instruções."""
    curves = path.findall(qn('a:cubicBezTo'))
    starts = path.findall(qn('a:moveTo'))
    if len(starts) != 1 or len(curves) != ELLIPSE_CURVE_COUNT:
        return None
    try:
        width = int(path.get('w'))
        height = int(path.get('h'))
        start = starts[0].find(qn('a:pt'))
        ends = [curve.findall(qn('a:pt'))[-1] for curve in curves]
        actual = [
            (int(point.get('x')), int(point.get('y')))
            for point in (start, *ends)
        ]
    except (AttributeError, ValueError, TypeError, IndexError):
        return None
    return width, height, actual


def _is_ellipse_freeform(shape):
    """Reconhece elipses em forma livre representadas por quatro curvas Bézier."""
    if shape.shape_type != MSO_SHAPE_TYPE.FREEFORM:
        return False
    paths = shape._element.xpath('.//a:pathLst/a:path')
    if len(paths) != 1:
        return False
    geometry = _ellipse_path_geometry(paths[0])
    if geometry is None:
        return False
    width, height, actual = geometry
    if not width or not height:
        return False
    expected = [
        (width / 2, 0), (0, height / 2),
        (width / 2, height), (width, height / 2), (width / 2, 0),
    ]
    tolerance = max(width, height) * .05
    return all(
        abs(x - tx) <= tolerance and abs(y - ty) <= tolerance
        for (x, y), (tx, ty) in zip(actual, expected, strict=True)
    )


def _get_shape_type(shape):
    if _is_ellipse_freeform(shape):
        return 'circle'
    try:
        shape_name = str(shape.auto_shape_type).lower()
    except (AttributeError, ValueError, TypeError):
        shape_name = ''

    if 'oval' in shape_name or 'ellipse' in shape_name:
        return 'circle'

    if 'triangle' in shape_name:
        return 'triangle'

    if 'star' in shape_name:
        return 'star'

    return 'rect'


SYMBOL_PRESET_MATCHES = (
    ('balao', ('callout', 'balloon')),
    ('nuvem', ('cloud',)),
    ('coracao', ('heart',)),
    ('raio', ('lightning', 'bolt')),
    ('hexagono', ('hexagon',)),
    ('losango', ('diamond',)),
    ('seta', ('arrow',)),
)


def _symbol_for_shape(shape):
    """Relaciona presets de formas do PowerPoint a símbolos vetoriais."""
    try:
        preset = str(shape.auto_shape_type).lower().replace('_', ' ')
    except (AttributeError, ValueError, TypeError):
        return None

    for symbol_key, keywords in SYMBOL_PRESET_MATCHES:
        if any(keyword in preset for keyword in keywords):
            return symbol_key

    return None


def _extract_shape_element(shape, base):
    """Extrai as propriedades básicas de uma forma vetorial."""
    fill_color = _get_fill_color(shape)
    stroke_color = _get_line_color(shape)

    is_line = shape.shape_type == MSO_SHAPE_TYPE.LINE

    symbol_key = _symbol_for_shape(shape)
    if not fill_color and not stroke_color and not is_line and not symbol_key:
        return None
    if symbol_key and not fill_color:
        fill_color = '#FF5700'

    return {
        **base,
        'type': 'symbol' if symbol_key else 'shape',
        'symbol_key': symbol_key,
        'content': '',
        'image_bytes': None,
        'image_ext': None,
        'color': fill_color,
        'shape_type': ('rect' if is_line else _get_shape_type(shape)),
        'stroke_color': stroke_color,
        'stroke_width': _get_line_width(shape),
        'fontSize': None,
    }


def _group_basis(shape, xfrm):
    """Converte a caixa interna do grupo em dimensões no slide."""
    child_width = xfrm.chExt.cx
    child_height = xfrm.chExt.cy
    if not child_width or not child_height:
        return None
    scale_x = shape.width / child_width
    scale_y = shape.height / child_height
    return (
        scale_x, 0., 0., scale_y,
        shape.left - xfrm.chOff.x * scale_x,
        shape.top - xfrm.chOff.y * scale_y,
    )


def _group_orientation(shape, xfrm):
    """Aplica rotação e espelhamentos ao redor do centro do grupo."""
    rotation = math.radians(_shape_rotation(shape))
    cosine = math.cos(rotation)
    sine = math.sin(rotation)
    flip_h = -1 if _xml_flag(xfrm, 'flipH') else 1
    flip_v = -1 if _xml_flag(xfrm, 'flipV') else 1
    center_x = shape.left + shape.width / 2
    center_y = shape.top + shape.height / 2
    a, b, c, d = cosine * flip_h, sine * flip_h, -sine * flip_v, cosine * flip_v
    return (
        a, b, c, d,
        center_x - a * center_x - c * center_y,
        center_y - b * center_x - d * center_y,
    )


def _transform_for_group(shape, parent_transform):
    """Aplica escala, posição, espelhamento e rotação de grupos PPTX."""
    try:
        xfrm = shape._element.grpSpPr.xfrm
        basis = _group_basis(shape, xfrm)
    except (AttributeError, TypeError):
        # Mantém a posição do grupo mesmo em documentos incompletos.
        return _compose(parent_transform, (1, 0, 0, 1, shape.left, shape.top))

    if basis is None:
        return parent_transform
    return _compose(parent_transform, _compose(_group_orientation(shape, xfrm), basis))


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


def _table_cell_text(cell, base):
    """Converte uma célula em texto editável, preservando estilo da primeira run."""
    if not cell.text.strip():
        return None
    paragraphs = cell.text_frame.paragraphs
    run = next((run for paragraph in paragraphs for run in paragraph.runs), None)
    font = run.font if run is not None else None
    font_size = round(font.size.pt * PIXELS_PER_INCH / POINTS_PER_INCH) if (
        font is not None and font.size is not None
    ) else DEFAULT_BODY_FONT_SIZE
    return {
        **base,
        'type': 'text',
        'content': cell.text,
        'fontSize': font_size,
        'font_family': font.name if font is not None and font.name else 'Poppins',
        'font_weight': 'bold' if font is not None and font.bold else 'normal',
        'font_style': 'italic' if font is not None and font.italic else 'normal',
        'underline': bool(font.underline) if font is not None else False,
        'color': _color_to_hex(font.color) if font is not None else '#333333',
        'text_align': _get_text_alignment(paragraphs[0]),
        'image_bytes': None,
        'image_ext': None,
    }


def _table_cell_background(cell, base):
    """Reproduz células com preenchimento, preservando-as como formas."""
    if cell.fill.type is None:
        return None
    color = _color_to_hex(cell.fill.fore_color)
    if not color:
        return None
    return {
        **base,
        'type': 'shape',
        'content': '',
        'shape_type': 'rect',
        'color': color,
        'stroke_color': '',
        'stroke_width': 0,
        'fontSize': None,
        'image_bytes': None,
        'image_ext': None,
    }


def _table_text_box(cell, base):
    """Respeita margens da célula e alinhamento vertical básico."""
    left = _emu_to_px(cell.margin_left)
    right = _emu_to_px(cell.margin_right)
    top = _emu_to_px(cell.margin_top)
    bottom = _emu_to_px(cell.margin_bottom)
    width = max(base['width'] - left - right, 1)
    height = max(base['heigth'] - top - bottom, 1)
    return {
        **base,
        'posicao_x': base['posicao_x'] + left,
        'posicao_y': base['posicao_y'] + top,
        'width': width,
        'heigth': height,
    }


def _extract_table(shape, output):
    """Extrai as células de tabelas PPTX como retângulos e textos editáveis."""
    table = shape.table
    columns = [column.width for column in table.columns]
    rows = [row.height for row in table.rows]
    scale_x = shape.width / max(sum(columns), 1)
    scale_y = shape.height / max(sum(rows), 1)
    y_emu = shape.top
    for row, row_height in zip(table.rows, rows, strict=True):
        x_emu = shape.left
        for cell, column_width in zip(row.cells, columns, strict=True):
            box = {
                'posicao_x': _emu_to_px(x_emu),
                'posicao_y': _emu_to_px(y_emu),
                'width': max(_emu_to_px(column_width * scale_x), 1),
                'heigth': max(_emu_to_px(row_height * scale_y), 1),
                'rotation': 0,
            }
            background = _table_cell_background(cell, box)
            if background is not None:
                output.append(background)
            text_element = _table_cell_text(cell, _table_text_box(cell, box))
            if text_element is not None:
                output.append(text_element)
            x_emu += column_width * scale_x
        y_emu += row_height * scale_y


def _process_shape(shape, output, transform):
    base = _get_base(shape, transform)

    if shape.shape_type == MSO_SHAPE_TYPE.GROUP:
        _extract_group(shape, output, transform)
        return

    if shape.has_table:
        _extract_table(shape, output)
        return

    if shape.shape_type == MSO_SHAPE_TYPE.PICTURE:
        element = _extract_picture(shape, base, transform)

        if element is not None:
            output.append(element)

        return

    # Formas preenchidas com imagem podem conter texto próprio.
    # Importar ambos, na ordem (imagem atrás, texto à frente).
    element = _extract_embedded_image(shape, base, transform)
    if element is not None:
        output.append(element)
    elif shape.shape_type in {
        MSO_SHAPE_TYPE.AUTO_SHAPE,
        MSO_SHAPE_TYPE.LINE,
        MSO_SHAPE_TYPE.FREEFORM,
    }:
        shape_element = _extract_shape_element(shape, base)
        if shape_element is not None:
            output.append(shape_element)

    text_element = _extract_text_element(shape, base)
    if text_element is not None:
        output.append(text_element)


def _extract_one(
    shape,
    output,
    transform=IDENTITY_TRANSFORM,
):
    try:
        _process_shape(
            shape,
            output,
            transform,
        )
    except Exception as exc:
        print(f'[PPTX] Falha ao extrair objeto: {exc}')


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

    canvas_width = _emu_to_px(presentation.slide_width)

    canvas_height = _emu_to_px(presentation.slide_height)

    if not presentation.slides:
        return [], canvas_width, canvas_height

    if not 0 <= slide_index < len(presentation.slides):
        raise IndexError('O índice do slide está fora dos limites.')

    return _extract_slide(
        presentation.slides[slide_index],
        canvas_width,
        canvas_height,
    )


def extract_pptx_pages(file_path):
    """Extrai todos os slides em formato de páginas."""
    presentation = Presentation(file_path)

    canvas_width = _emu_to_px(presentation.slide_width)

    canvas_height = _emu_to_px(presentation.slide_height)

    pages = []

    for index, slide in enumerate(presentation.slides):
        elements, width, height = _extract_slide(
            slide,
            canvas_width,
            canvas_height,
        )

        pages.append({
            'name': f'Slide {index + 1}',
            'page_order': index,
            'width': width,
            'height': height,
            'elements': elements,
        })

    return pages
