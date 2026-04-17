from django.db import models


class Message(models.Model):
    STATUS_ENVIADA = 'enviada'
    STATUS_LIDA = 'lida'

    STATUS_CHOICES = [
        (STATUS_ENVIADA, 'Enviada'),
        (STATUS_LIDA, 'Lida')
    ]

    content = models.TextField()
    sent_at = models.DateTimeField()
    status = models.CharField(
        max_length=10,
        choices=STATUS_CHOICES,
        default=STATUS_ENVIADA
    )

    def __str__(self):
        return f'({self.sent_at} - {self.status})'
