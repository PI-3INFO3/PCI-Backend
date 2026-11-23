from rest_framework import mixins, viewsets

from core.models import Symbol
from core.serializers.symbol import SymbolSerializer


class SymbolViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    viewsets.GenericViewSet,
):
    queryset = Symbol.objects.all().order_by("name", "id")
    serializer_class = SymbolSerializer
    pagination_class = None  # Catálogo curto; novos símbolos ficam disponíveis a todos.
