from django.conf import settings
from django.db import models


class Friendship(models.Model):
    STATUS_PENDENTE = 'pendente'
    STATUS_ACEITO = 'aceito'
    STATUS_RECUSADO = 'recusado'

    STATUS_CHOICES = [
        (STATUS_PENDENTE, 'Pendente'),
        (STATUS_ACEITO, 'Aceito'),
        (STATUS_RECUSADO, 'Recusado'),
    ]

    remetente = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name='pedidos_enviados',
        on_delete=models.CASCADE,
    )
    destinatario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name='pedidos_recebidos',
        on_delete=models.CASCADE,
    )
    status = models.CharField(
        max_length=10,
        choices=STATUS_CHOICES,
        default=STATUS_PENDENTE,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('remetente', 'destinatario')

    def __str__(self):
        return f'{self.remetente} -> {self.destinatario} ({self.status})'