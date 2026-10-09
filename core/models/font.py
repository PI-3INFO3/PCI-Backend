from django.db import models


class Font(models.Model):
    name = models.CharField(max_length=80)
    family = models.CharField(max_length=80)
    styles = models.CharField(max_length=80, blank=True)

    class Meta:
        verbose_name = "Fonte"
        verbose_name_plural = "Fontes"

    def __str__(self):
        return self.name
