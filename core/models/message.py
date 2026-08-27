from django.conf import settings
from django.db import models


class Message(models.Model):
    STATUS_ENVIADA = 'enviada'
    STATUS_LIDA = 'lida'

    STATUS_CHOICES = [
        (STATUS_ENVIADA, 'Enviada'),
        (STATUS_LIDA, 'Lida'),
    ]

    remetente = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name='mensagens_enviadas',
        on_delete=models.CASCADE,
    )
    destinatario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name='mensagens_recebidas',
        on_delete=models.CASCADE,
    )
    content = models.TextField()
    sent_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(
        max_length=10,
        choices=STATUS_CHOICES,
        default=STATUS_ENVIADA,
    )

    class Meta:
        ordering = ['sent_at']

    def __str__(self):
        return f'({self.sent_at} - {self.status})'