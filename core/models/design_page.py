from django.db import models


class DesignPage(models.Model):
    design = models.ForeignKey(
        "Design",
        on_delete=models.CASCADE,
        related_name="pages",
    )

    name = models.CharField(
        max_length=255,
        default="Página 1",
    )

    page_order = models.PositiveIntegerField(default=0)

    width = models.PositiveIntegerField(default=1080)

    height = models.PositiveIntegerField(default=1080)

    background_color = models.CharField(
        max_length=20,
        default="#FFFFFF",
        blank=True,
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["page_order", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["design", "page_order"],
                name="unique_page_order_per_design",
            ),
        ]

    def __str__(self):
        return f"{self.name} - design {self.design_id}"
