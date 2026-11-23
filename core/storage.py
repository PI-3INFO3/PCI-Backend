"""Armazenamento privado para imagens utilizadas pelo editor.

Independente do app de terceiros `uploader` e do storage público do site.
"""
from django.conf import settings
from django.core.files.storage import FileSystemStorage
from django.utils.deconstruct import deconstructible


@deconstructible
class PrivateEditorImageStorage(FileSystemStorage):
    def __init__(self):
        super().__init__(location=settings.PRIVATE_EDITOR_MEDIA_ROOT, base_url=None)
