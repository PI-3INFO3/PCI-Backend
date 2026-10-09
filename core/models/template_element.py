from django.db import models


class TemplateElement(models.Model):
    class ElementType(models.TextChoices):
        TEXT = "text", "Texto"
        TITLE = "title", "Título"
        IMAGE = "image", "Imagem"
        SHAPE = "shape", "Forma"

    template = models.ForeignKey("Template", on_delete=models.CASCADE, related_name="template_elements")
    type = models.CharField(max_length=45, choices=ElementType.choices)
    content = models.CharField(max_length=250, blank=True)
    posicao_x = models.IntegerField()
    posicao_y = models.IntegerField()
    width = models.IntegerField()
    heigth = models.IntegerField()
    color = models.CharField(max_length=20, blank=True)

    class Meta:
        verbose_name = "Elemento de template"
        verbose_name_plural = "Elementos de template"

    def to_element_kwargs(self):
        return {
            "type": self.type,
            "content": self.content,
            "posicao_x": self.posicao_x,
            "posicao_y": self.posicao_y,
            "width": self.width,
            "heigth": self.heigth,
            "color": self.color,
        }
