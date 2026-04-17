from django.db import models


class Model(models.Model):
    name = models.CharField(max_length=255, blank=True, default='Novo Modelo')
    description = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
