from rest_framework.serializers import ModelSerializer

from core.models import Template


class TemplateSerializer(ModelSerializer):
    class Meta:
        model = Template
        fields = '__all__'
