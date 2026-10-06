from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response

from core.models import Design, Element
from core.serializers.design import DesignSerializer, HistoryEntrySerializer
from core.services import history
from core.services.file_import import UnsupportedFileType, import_file_into_design


class DesignViewSet(viewsets.ModelViewSet):
    serializer_class = DesignSerializer
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get_queryset(self):
        queryset = Design.objects.filter(created_by=self.request.user)
        importante = self.request.query_params.get("importante")
        if importante is not None:
            queryset = queryset.filter(importante=importante.lower() == "true")
        return queryset

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    def perform_update(self, serializer):
        design = serializer.instance
        context = history.ChangeContext(user=self.request.user, design=design)
        changed_fields = history.diff_and_log_instance(
            context, design, serializer.validated_data, ["name", "template", "theme"], "design",
        )
        serializer.save()
        if changed_fields:
            design.refresh_from_db()

    @action(detail=False, methods=["post"], url_path="upload")
    def upload(self, request):
        uploaded_file = request.FILES.get("file")
        if not uploaded_file:
            return Response({"error": "Nenhum arquivo enviado."}, status=status.HTTP_400_BAD_REQUEST)

        design = Design.objects.create(
            name=uploaded_file.name.rsplit(".", 1)[0],
            created_by=request.user,
        )
        context = history.ChangeContext(user=request.user, design=design)
        history.log_creation(
            context, history.TargetRef("design", design.id),
            description="Design criado via upload de arquivo",
        )

        try:
            import_file_into_design(uploaded_file, design, request.user)
        except UnsupportedFileType as exc:
            design.delete()
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        serializer = self.get_serializer(design)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["get"], url_path="history")
    def history_log(self, request, pk=None):
        design = self.get_object()
        entries = design.history.select_related("user").all()
        serializer = HistoryEntrySerializer(entries, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=["patch"], url_path="reorder-elements")
    def reorder_elements(self, request, pk=None):
        design = self.get_object()
        ordered_ids = request.data.get("element_ids", [])
        elements_by_id = {el.id: el for el in design.elements.all()}
        context = history.ChangeContext(user=request.user, design=design)

        for new_order, element_id in enumerate(ordered_ids):
            element = elements_by_id.get(element_id)
            if element is None or element.layer_order == new_order:
                continue
            history.log_field_change(
                context, history.TargetRef("element", element.id),
                "layer_order", element.layer_order, new_order,
            )
            element.layer_order = new_order
            element.save(update_fields=["layer_order"])

        serializer = self.get_serializer(design)
        return Response(serializer.data)

    @action(detail=True, methods=["patch"], url_path="save-elements")
    def save_elements(self, request, pk=None):
        design = self.get_object()
        incoming_elements = request.data.get("elements", [])
        incoming_ids = {el["id"] for el in incoming_elements if el.get("id")}

        existing_elements = {el.id: el for el in design.elements.all()}
        context = history.ChangeContext(user=request.user, design=design)

        for element_id, element in existing_elements.items():
            if element_id not in incoming_ids:
                history.log_deletion(context, history.TargetRef("element", element_id))
                element.delete()

        for el_data in incoming_elements:
            element_id = el_data.get("id")

            if element_id and element_id in existing_elements:
                element = existing_elements[element_id]
                changed_fields = history.diff_and_log_instance(
                    context, element, el_data, Element.TRACKED_FIELDS, "element",
                )
                if changed_fields:
                    element.save(update_fields=changed_fields)
            else:

                new_element = Element.objects.create(
                    design=design,
                    type=el_data["type"],
                    content=el_data.get("content", ""),
                    posicao_x=el_data["posicao_x"],
                    posicao_y=el_data["posicao_y"],
                    width=el_data["width"],
                    heigth=el_data["heigth"],
                    color=el_data.get("color", ""),
                    shape_type=el_data.get("shape_type"),
                    stroke_width=el_data.get("stroke_width"),
                    layer_order=el_data.get("layer_order", 0),
                )
                history.log_creation(
                    context, history.TargetRef("element", new_element.id),
                    description="Elemento criado pelo usuário no editor",
                )

        serializer = self.get_serializer(design)
        return Response(serializer.data)
