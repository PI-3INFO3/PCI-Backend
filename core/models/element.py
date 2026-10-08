import uuid

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
        TRIANGLE = "triangle", "Triângulo"
        STAR = "star", "Estrela"

    design = models.ForeignKey(
        "Design",
        on_delete=models.CASCADE,
        related_name="elements",
    )

    type = models.CharField(
        max_length=45,
        choices=ElementType.choices,
    )

    # TextField porque imagens podem ser armazenadas
    # como Data URL e ultrapassar facilmente 250 caracteres.
    content = models.TextField(
        blank=True,
    )

    posicao_x = models.IntegerField()
    posicao_y = models.IntegerField()

    width = models.IntegerField()
    heigth = models.IntegerField()

    color = models.CharField(
        max_length=20,
        blank=True,
    )

    shape_type = models.CharField(
        max_length=20,
        choices=ShapeType.choices,
        blank=True,
        null=True,
    )

    stroke_width = models.IntegerField(
        default=0,
        blank=True,
        null=True,
    )

    stroke_color = models.CharField(
        max_length=20,
        blank=True,
        default="",
    )

    font_size = models.IntegerField(
        blank=True,
        null=True,
    )

    font_family = models.CharField(
        max_length=100,
        blank=True,
        default="Poppins",
    )

    font_weight = models.CharField(
        max_length=30,
        blank=True,
        default="normal",
    )

    font_style = models.CharField(
        max_length=30,
        blank=True,
        default="normal",
    )

    text_align = models.CharField(
        max_length=30,
        blank=True,
        default="left",
    )

    client_id = models.UUIDField(
        default=uuid.uuid4,
        editable=False,
        null=True,
        blank=True,
        db_index=True,
    )

    layer_order = models.IntegerField(
        default=0,
    )

    upload_at = models.DateTimeField(
        auto_now_add=True,
    )

    TRACKED_FIELDS = [
        "content",
        "posicao_x",
        "posicao_y",
        "width",
        "heigth",
        "color",
        "shape_type",
        "stroke_width",
        "stroke_color",
        "font_size",
        "font_family",
        "font_weight",
        "font_style",
        "text_align",
        "layer_order",
    ]

    class Meta:
        verbose_name = "Elemento"
        verbose_name_plural = "Elementos"
        ordering = [
            "layer_order",
            "id",
        ]

    def __str__(self):
        return f"{self.type} ({self.id}) - design {self.design_id}"
