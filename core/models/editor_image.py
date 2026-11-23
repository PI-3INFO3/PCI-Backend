"""Imagens privadas do editor, distintas das imagens do app `uploader`."""
from django.conf import settings
from django.db import models

from core.storage import PrivateEditorImageStorage


def editor_image_path(image, filename):
    """Localização não exposta publicamente; o conteúdo só sai via API."""
    extension = filename.rsplit('.', 1)[-1].lower() if '.' in filename else 'png'
    if extension not in {'png', 'jpg', 'webp'}:
        extension = 'png'
    return f'editor-images/{image.owner_id}/{image.sha256}.{extension}'


class EditorImage(models.Model):
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name='editor_images',
    )
    sha256 = models.CharField(max_length=64, db_index=True)
    file = models.ImageField(
        storage=PrivateEditorImageStorage(), upload_to=editor_image_path,
        max_length=255,
    )
    description = models.CharField(max_length=255, blank=True)
    uploaded_on = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-uploaded_on', '-id']
        constraints = [models.UniqueConstraint(
            fields=['owner', 'sha256'], name='unique_editor_image_per_owner',
        )]

    def __str__(self):
        return f'EditorImage {self.pk}: {self.description}'

    @property
    def url(self):
        return f'/api/editor-images/{self.pk}/content/' if self.pk else ''
