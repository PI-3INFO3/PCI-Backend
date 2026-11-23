from rest_framework import serializers

from core.models.editor_image import EditorImage


class EditorImageSerializer(serializers.ModelSerializer):
    url = serializers.ReadOnlyField()
    reused = serializers.SerializerMethodField()

    class Meta:
        model = EditorImage
        fields = ('id', 'description', 'uploaded_on', 'url', 'reused')
        read_only_fields = fields

    def get_reused(self, obj):
        return bool(getattr(obj, 'was_reused', False))
