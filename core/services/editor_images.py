"""Upload seguro e deduplicado para a biblioteca privada do editor.

Não usa nem modifica o modelo ou as rotas do app de terceiros `uploader`.
"""
import hashlib
from pathlib import Path

from django.db import IntegrityError, transaction
from PIL import Image as PILImage
from PIL import UnidentifiedImageError

from core.models.editor_image import EditorImage

MAX_IMAGE_SIZE = 15 * 1024 * 1024
ALLOWED_FORMATS = {'PNG': 'png', 'JPEG': 'jpg', 'WEBP': 'webp'}


def save_editor_image_once(uploaded, owner, description=''):
    """Retorna (registro, criado). Reutiliza bytes idênticos por proprietário."""
    if not owner or not owner.is_authenticated:
        raise ValueError('É necessário fazer login para enviar imagens.')
    if not uploaded or uploaded.size <= 0 or uploaded.size > MAX_IMAGE_SIZE:
        raise ValueError('A imagem deve ter entre 1 byte e 15 MB.')

    digest = hashlib.sha256()
    for chunk in uploaded.chunks():
        digest.update(chunk)
    uploaded.seek(0)
    digest = digest.hexdigest()
    existing = EditorImage.objects.filter(owner=owner, sha256=digest).first()
    if existing:
        return existing, False

    detected_format = None
    try:
        with PILImage.open(uploaded) as image:
            detected_format = image.format
            if detected_format not in ALLOWED_FORMATS:
                raise ValueError('Formato inválido. Use PNG, JPG ou WEBP.')
            image.verify()
    except (
        UnidentifiedImageError, OSError, SyntaxError,
        PILImage.DecompressionBombError,
    ) as exc:
        raise ValueError('Imagem inválida ou corrompida.') from exc
    finally:
        uploaded.seek(0)

    name = f'{Path(uploaded.name).stem[:80]}.{ALLOWED_FORMATS[detected_format]}'
    asset = EditorImage(
        owner=owner,
        sha256=digest,
        description=description[:255],
    )
    stored = None
    try:
        with transaction.atomic():
            asset.file.save(name, uploaded, save=False)
            stored = asset.file
            asset.save()
    except IntegrityError:
        if stored:
            # FileSystemStorage garante sufixo exclusivo quando outro upload
            # com o mesmo conteúdo já criou o caminho determinístico.
            surviving = EditorImage.objects.get(owner=owner, sha256=digest)
            if stored.name != surviving.file.name:
                stored.delete(save=False)
            return surviving, False
        return EditorImage.objects.get(owner=owner, sha256=digest), False

    return asset, True


def editor_image_url(image):
    return image.url
