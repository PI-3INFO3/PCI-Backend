from rest_framework import serializers

from core.models import AuditLog, Design, DesignPage, Element


class ElementSerializer(serializers.ModelSerializer):
    class Meta:
        model = Element

        fields = [
            "id",
            "client_id",
            "type",
            "content",
            "posicao_x",
            "posicao_y",
            "width",
            "heigth",
            "color",
            "shape_type",
            "stroke_width",
            "stroke_color",
            "font_size",
            "font_family",
            "font_weight",
            "font_style",
            "text_align",
            "layer_order",
        ]

        read_only_fields = [
            "id",
        ]


class DesignPageSerializer(serializers.ModelSerializer):
    elements = ElementSerializer(many=True, read_only=True)

    class Meta:
        model = DesignPage

        fields = [
            "id",
            "name",
            "page_order",
            "width",
            "height",
            "background_color",
            "elements",
        ]

        read_only_fields = ["id"]


class DesignSerializer(serializers.ModelSerializer):
    # Compatibilidade com o editor atual.
    # O campo "elements" contém os elementos da primeira página.
    elements = serializers.SerializerMethodField()

    # O editor multipágina utilizará "pages".
    pages = DesignPageSerializer(many=True, read_only=True)

    def get_elements(self, obj):
        first_page = obj.pages.order_by(
            "page_order",
            "id",
        ).first()

        if first_page is not None:
            elements = first_page.elements.order_by(
                "layer_order",
                "id",
            )

            return ElementSerializer(
                elements,
                many=True,
            ).data

        # Compatibilidade com designs antigos que ainda não tenham páginas.
        elements = obj.elements.order_by(
            "layer_order",
            "id",
        )

        return ElementSerializer(
            elements,
            many=True,
        ).data

    class Meta:
        model = Design

        fields = [
            "id",
            "name",
            "created_by",
            "created_at",
            "template",
            "theme",
            "importante",
            "elements",
            "pages",
        ]

        read_only_fields = [
            "id",
            "created_by",
            "created_at",
        ]


class HistoryEntrySerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(
        source="user.name",
        read_only=True,
        default=None,
    )

    class Meta:
        model = AuditLog

        fields = [
            "id",
            "action",
            "entity",
            "entity_id",
            "field_name",
            "old_value",
            "new_value",
            "user",
            "user_name",
            "created_at",
        ]
