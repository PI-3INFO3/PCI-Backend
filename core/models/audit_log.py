from django.db import models


class AuditLog(models.Model):
    class Action(models.TextChoices):
        CREATE = "create", "Criação"
        UPDATE = "update", "Atualização"
        DELETE = "delete", "Exclusão"
        LOGIN = "login", "Login"

    class Entity(models.TextChoices):
        DESIGN = "design", "Design"
        ELEMENT = "element", "Elemento"
        TEMPLATE = "template", "Template"
        USER = "user", "Usuário"
        COMPANY = "company", "Empresa"

    action = models.CharField(max_length=20, choices=Action.choices)
    entity = models.CharField(max_length=20, choices=Entity.choices)
    entity_id = models.BigIntegerField()
    description = models.TextField(blank=True)

    field_name = models.CharField(max_length=80, blank=True, null=True)
    old_value = models.TextField(blank=True, null=True)
    new_value = models.TextField(blank=True, null=True)

    design = models.ForeignKey(
        "core.Design", on_delete=models.CASCADE, null=True, blank=True, related_name="history"
    )

    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    user = models.ForeignKey(
        "core.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="audit_logs"
    )
    # company = models.ForeignKey(
    #     "core.Company", on_delete=models.SET_NULL, null=True, blank=True, related_name="audit_logs"
    # )

    class Meta:
        verbose_name = "Log de auditoria"
        verbose_name_plural = "Logs de auditoria"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["design", "-created_at"]),
            models.Index(fields=["entity", "entity_id"]),
        ]

    def __str__(self):
        if self.field_name:
            return f"{self.entity}#{self.entity_id}.{self.field_name}: {self.old_value} -> {self.new_value}"
        return f"{self.action} em {self.entity}#{self.entity_id}"
