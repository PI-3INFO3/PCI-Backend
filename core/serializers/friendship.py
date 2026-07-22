from rest_framework import serializers
from rest_framework.serializers import ModelSerializer

from core.models import Friendship, User
from core.serializers.user import UserSerializer


class FriendshipSerializer(ModelSerializer):
    remetente = UserSerializer(read_only=True)
    destinatario = UserSerializer(read_only=True)
    destinatario_id = serializers.PrimaryKeyRelatedField(
        source='destinatario',
        queryset=User.objects.all(),
        write_only=True,
    )

    class Meta:
        model = Friendship
        fields = ['id', 'remetente', 'destinatario', 'destinatario_id', 'status', 'created_at']
        read_only_fields = ['status', 'created_at']

    def validate_destinatario_id(self, value):
        request = self.context['request']
        if value == request.user:
            raise serializers.ValidationError('Você não pode adicionar você mesmo.')
        return value

    def validate(self, attrs):
        request = self.context['request']
        destinatario = attrs.get('destinatario')
        ja_existe = Friendship.objects.filter(
            remetente__in=[request.user, destinatario],
            destinatario__in=[request.user, destinatario],
        ).exists()
        if ja_existe:
            raise serializers.ValidationError('Já existe um pedido de amizade entre vocês.')
        return attrs

    def create(self, validated_data):
        validated_data['remetente'] = self.context['request'].user
        return super().create(validated_data)