from django.conf import settings
from django.db import models


class Desing(models.Model):
    name = models.CharField(max_length=255, blank=True, default='Novo Desing')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='desings',
        null=True, blank=True,
    )

    # categorias
    importante = models.BooleanField(default=False)
    meu_projeto = models.BooleanField(default=False)
    em_andamento = models.BooleanField(default=False)

    # conteúdo do editor
    canvas = models.JSONField(null=True, blank=True)
    miniatura = models.TextField(blank=True, default='')
    foto_original = models.TextField(blank=True, default='')

    publico = models.BooleanField(default=False)