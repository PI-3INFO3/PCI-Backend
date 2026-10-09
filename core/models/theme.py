from django.db import models


class Theme(models.Model):
    description = models.TextField(blank=True)
    colors = models.CharField(max_length=20, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Tema"
        verbose_name_plural = "Temas"

    def __str__(self):
        return f"Tema {self.id}"
