from rest_framework.serializers import ModelSerializer, SerializerMethodField
from core.models import Desing


class DesingSerializer(ModelSerializer):
    autor_nome = SerializerMethodField()

    class Meta:
        model = Desing
        fields = '__all__'

    def get_autor_nome(self, obj):
        usuario = obj.usuario
        if not usuario:
            return ''
        return (getattr(usuario, 'name', '') 
                or getattr(usuario, 'emial', '')
                or str(usuario)
)

class DesingListSerializer(DesingSerializer):
    class Meta:
        model = Desing
        exclude = ['canvas', 'foto_original']