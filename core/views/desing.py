from rest_framework.viewsets import ModelViewSet

from core.models import Desing
from core.serializers import DesingSerializer


class DesingViewSet(ModelViewSet):
    queryset = Desing.objects.all()
    serializer_class = DesingSerializer
