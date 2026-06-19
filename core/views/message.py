from rest_framework.viewsets import ModelViewSet

from core.models import Message
from core.serializers import MessageSerializer


class MessageViewSet(ModelViewSet):
    queryset = Message.objects.all()
    serializer_class = MessageSerializer
