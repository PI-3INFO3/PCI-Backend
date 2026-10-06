from django.db import models


class Element(models.Model):
    class ElementType(models.TextChoices):
        TEXT = "text", "Texto"
        TITLE = "title", "Título"
        IMAGE = "image", "Imagem"
        SHAPE = "shape", "Forma"

    class ShapeType(models.TextChoices):
        RECT = "rect", "Retângulo"
        CIRCLE = "circle", "Círculo"

    design = models.ForeignKey("Design", on_delete=models.CASCADE, related_name="elements")
    type = models.CharField(max_length=45, choices=ElementType.choices)
    content = models.CharField(max_length=250, blank=True)
    posicao_x = models.IntegerField()
    posicao_y = models.IntegerField()
    width = models.IntegerField()
    heigth = models.IntegerField()
    color = models.CharField(max_length=20, blank=True)

    shape_type = models.CharField(max_length=20, choices=ShapeType.choices, blank=True, null=True)
    stroke_width = models.IntegerField(default=3, blank=True, null=True)

    layer_order = models.IntegerField(default=0)

    upload_at = models.DateTimeField(auto_now_add=True)

    TRACKED_FIELDS = [
        "content", "posicao_x", "posicao_y", "width", "heigth",
        "color", "shape_type", "stroke_width", "layer_order",
    ]

    class Meta:
        verbose_name = "Elemento"
        verbose_name_plural = "Elementos"
        ordering = ["layer_order", "id"]

    def __str__(self):
        return f"{self.type} ({self.id}) - design {self.design_id}"
