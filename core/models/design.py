from django.db import models


class Design(models.Model):
    name = models.CharField(max_length=255, blank=True, default="Novo Design")
    created_by = models.ForeignKey(
        "core.User", on_delete=models.SET_NULL, null=True, related_name="designs_created"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    template = models.ForeignKey(
        "Template", on_delete=models.SET_NULL, null=True, blank=True, related_name="designs"
    )
    theme = models.ForeignKey(
        "Theme", on_delete=models.SET_NULL, null=True, blank=True, related_name="designs"
    )
    importante = models.BooleanField(default=False)

    class Meta:
        verbose_name = "Design"
        verbose_name_plural = "Designs"

    def __str__(self):
        return self.name
