from django.db.models import Q
from rest_framework.permissions import IsAuthenticated
from rest_framework.viewsets import ModelViewSet

from core.models import Message
from core.serializers import MessageSerializer


class MessageViewSet(ModelViewSet):
    serializer_class = MessageSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None

    def get_queryset(self):
        user = self.request.user
        queryset = Message.objects.filter(Q(remetente=user) | Q(destinatario=user))

        outro_usuario_id = self.request.query_params.get('com')
        if outro_usuario_id:
            queryset = queryset.filter(
                Q(remetente=user, destinatario_id=outro_usuario_id) |
                Q(remetente_id=outro_usuario_id, destinatario=user)
            )
        return queryset.order_by('sent_at')

    def perform_create(self, serializer):
        serializer.save(remetente=self.request.user)