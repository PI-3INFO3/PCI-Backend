from django.db.models import Q
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet

from core.models import Friendship
from core.serializers import FriendshipSerializer


class FriendshipViewSet(ModelViewSet):
    serializer_class = FriendshipSerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ['get', 'post', 'patch', 'delete']

    def get_queryset(self):
        user = self.request.user
        return Friendship.objects.filter(
            Q(remetente=user) | Q(destinatario=user)
        ).order_by('-created_at')

    @action(detail=False, methods=['get'])
    def amigos(self, request):
        """Lista amizades já aceitas."""
        aceitos = self.get_queryset().filter(status=Friendship.STATUS_ACEITO)
        return Response(self.get_serializer(aceitos, many=True).data)

    @action(detail=False, methods=['get'])
    def pendentes(self, request):
        """Lista pedidos recebidos aguardando resposta."""
        pendentes = Friendship.objects.filter(
            destinatario=request.user,
            status=Friendship.STATUS_PENDENTE,
        )
        return Response(self.get_serializer(pendentes, many=True).data)

    @action(detail=True, methods=['patch'])
    def aceitar(self, request, pk=None):
        friendship = self.get_object()
        if friendship.destinatario != request.user:
            return Response({'detail': 'Você não pode responder este pedido.'}, status=status.HTTP_403_FORBIDDEN)
        friendship.status = Friendship.STATUS_ACEITO
        friendship.save()
        return Response(self.get_serializer(friendship).data)

    @action(detail=True, methods=['patch'])
    def recusar(self, request, pk=None):
        friendship = self.get_object()
        if friendship.destinatario != request.user:
            return Response({'detail': 'Você não pode responder este pedido.'}, status=status.HTTP_403_FORBIDDEN)
        friendship.status = Friendship.STATUS_RECUSADO
        friendship.save()
        return Response(self.get_serializer(friendship).data)