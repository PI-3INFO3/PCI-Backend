from django.db import models


class TemplateAccessGrant(models.Model):
    template = models.ForeignKey("Template", on_delete=models.CASCADE, related_name="access_grants")
    user = models.ForeignKey("core.User", on_delete=models.CASCADE, related_name="template_access_grants")
    granted_at = models.DateField(auto_now_add=True)

    class Meta:
        verbose_name = "Acesso ao template"
        verbose_name_plural = "Acessos aos templates"
        unique_together = ("template", "user")
