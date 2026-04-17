from django.db import models


class Template(models.Model):
    name = models.CharField(max_length=255, blank=True, default='Novo Template')
    created_at = models.DateTimeField(auto_now_add=True)
