from rest_framework.serializers import ModelSerializer

from core.models import Model


class ModelSerializer(ModelSerializer):
    class Meta:
        model = Model
        fields = '__all__'
