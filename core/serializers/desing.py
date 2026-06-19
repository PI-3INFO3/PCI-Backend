from rest_framework.serializers import ModelSerializer

from core.models import Desing


class DesingSerializer(ModelSerializer):
    class Meta:
        model = Desing
        fields = '__all__'
