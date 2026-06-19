from django.db import models


class Desing(models.Model):
    name = models.CharField(max_length=255, blank=True, default='Novo Desing')
    created_at = models.DateTimeField(auto_now_add=True)
