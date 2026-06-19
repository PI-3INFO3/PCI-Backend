from rest_framework.viewsets import ModelViewSet

from core.models import Template
from core.serializers import TemplateSerializer


class TemplateViewSet(ModelViewSet):
    queryset = Template.objects.all()
    serializer_class = TemplateSerializer
