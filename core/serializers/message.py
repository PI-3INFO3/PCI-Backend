from rest_framework import serializers
from rest_framework.serializers import ModelSerializer

from core.models import Message, User


class MessageSerializer(ModelSerializer):
    remetente = serializers.PrimaryKeyRelatedField(read_only=True)
    destinatario_id = serializers.PrimaryKeyRelatedField(
        source='destinatario',
        queryset=User.objects.all(),
        write_only=True,
    )

    class Meta:
        model = Message
        fields = ['id', 'remetente', 'destinatario', 'destinatario_id', 'content', 'sent_at', 'status']
        read_only_fields = ['destinatario', 'sent_at', 'status']