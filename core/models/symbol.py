"""Biblioteca pública de símbolos vetoriais (somente geometria SVG Path)."""
from django.db import models


class Symbol(models.Model):
    key = models.SlugField(max_length=100, unique=True)
    name = models.CharField(max_length=120)
    # Apenas comandos de path, nunca markup SVG/HTML arbitrário.
    path_data = models.TextField(max_length=4000)
    content_hash = models.CharField(max_length=64, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name", "id"]

    def __str__(self):
        return self.name
