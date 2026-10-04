from django.db.models import Q
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.viewsets import ModelViewSet

from core.models import Desing
from core.serializers import DesingSerializer, DesingListSerializer


class DesingViewSet(ModelViewSet):
    queryset = Desing.objects.all()
    serializer_class = DesingSerializer

    filter_backends = [DjangoFilterBackend]
    filterset_fields = [
        'usuario', 'importante', 'meu_projeto', 'em_andamento', 'publico'
    ]

    def get_queryset(self):
        qs = Desing.objects.select_related('usuario').order_by('-id')
        user = self.request.user

        if not user.is_authenticated:
            return qs.none()

        if self.action in ('update', 'partial_update', 'destroy'):
            return qs.filter(usuario=user)

        return qs.filter(Q(usuario=user) | Q(publico=True))

    def get_serializer_class(self):
        if self.action == 'list':
            return DesingListSerializer
        return DesingSerializer

    def perform_create(self, serializer):
        serializer.save(usuario=self.request.user)