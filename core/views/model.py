from rest_framework.viewsets import ModelViewSet

from core.models import Model
from core.serializers import ModelSerializer


class ModelViewSet(ModelViewSet):
    queryset = Model.objects.all()
    serializer_class = ModelSerializer
