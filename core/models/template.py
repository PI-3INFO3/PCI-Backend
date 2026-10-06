from django.db import models


class Template(models.Model):
    name = models.CharField(max_length=45)
    created_at = models.DateTimeField(auto_now_add=True)
    fonts = models.ManyToManyField("Font", blank=True, related_name="templates")
    images = models.ManyToManyField("uploader.Image", blank=True, related_name="templates")

    class Meta:
        verbose_name = "Template"
        verbose_name_plural = "Templates"

    def __str__(self):
        return self.name
