from rest_framework import serializers

from core.models import AuditLog, Design, Element


class ElementSerializer(serializers.ModelSerializer):
    class Meta:
        model = Element
        fields = [
            "id", "type", "content", "posicao_x", "posicao_y", "width", "heigth",
            "color", "shape_type", "stroke_width", "layer_order",
        ]


class DesignSerializer(serializers.ModelSerializer):
    elements = ElementSerializer(many=True, read_only=True)

    class Meta:
        model = Design
        fields = [
            "id", "name", "created_by", "created_at", "template", "theme",
            "importante", "elements",
        ]
        read_only_fields = ["id", "created_by", "created_at"]


class HistoryEntrySerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source="user.name", read_only=True, default=None)

    class Meta:
        model = AuditLog
        fields = [
            "id", "action", "entity", "entity_id",
            "field_name", "old_value", "new_value",
            "user", "user_name", "created_at",
        ]
