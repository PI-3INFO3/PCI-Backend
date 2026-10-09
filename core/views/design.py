from django.db import transaction
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import (
    FormParser,
    JSONParser,
    MultiPartParser,
)
from rest_framework.response import Response

from core.models import Design, DesignPage, Element
from core.serializers.design import (
    DesignSerializer,
    HistoryEntrySerializer,
)
from core.services import history
from core.services.file_import import (
    UnsupportedFileType,
    import_file_into_design,
)


class DesignViewSet(viewsets.ModelViewSet):
    serializer_class = DesignSerializer

    parser_classes = [
        MultiPartParser,
        FormParser,
        JSONParser,
    ]

    def get_queryset(self):
        queryset = Design.objects.filter(
            created_by=self.request.user
        )

        importante = self.request.query_params.get(
            "importante"
        )

        if importante is not None:
            queryset = queryset.filter(
                importante=importante.lower() == "true"
            )

        return queryset

    def perform_create(self, serializer):
        design = serializer.save(
            created_by=self.request.user
        )

        DesignPage.objects.create(
            design=design,
            name="Página 1",
            page_order=0,
            width=1080,
            height=1080,
        )

    def perform_update(self, serializer):
        design = serializer.instance

        context = history.ChangeContext(
            user=self.request.user,
            design=design,
        )

        changed_fields = history.diff_and_log_instance(
            context,
            design,
            serializer.validated_data,
            ["name", "template", "theme"],
            "design",
        )

        serializer.save()

        if changed_fields:
            design.refresh_from_db()

    @action(
        detail=False,
        methods=["post"],
        url_path="upload",
    )
    def upload(self, request):
        uploaded_file = request.FILES.get("file")

        if not uploaded_file:
            return Response(
                {"error": "Nenhum arquivo enviado."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        design = Design.objects.create(
            name=uploaded_file.name.rsplit(".", 1)[0],
            created_by=request.user,
        )

        context = history.ChangeContext(
            user=request.user,
            design=design,
        )

        history.log_creation(
            context,
            history.TargetRef("design", design.id),
            description="Design criado via upload de arquivo",
        )

        try:
            import_file_into_design(
                uploaded_file,
                design,
                request.user,
            )
        except UnsupportedFileType as exc:
            design.delete()

            return Response(
                {"error": str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = self.get_serializer(design)

        return Response(
            serializer.data,
            status=status.HTTP_201_CREATED,
        )

    @action(
        detail=True,
        methods=["get"],
        url_path="history",
    )
    def history_log(self, request, pk=None):
        design = self.get_object()

        entries = design.history.select_related(
            "user"
        ).all()

        serializer = HistoryEntrySerializer(
            entries,
            many=True,
        )

        return Response(serializer.data)

    @action(
        detail=True,
        methods=["post"],
        url_path="create-page",
    )
    @transaction.atomic
    def create_page(self, request, pk=None):
        design = self.get_object()

        pages = design.pages.order_by(
            "page_order",
            "id",
        )

        source_page = None
        source_id = request.data.get(
            "duplicate_page_id"
        )

        if source_id not in {None, ""}:
            try:
                source_page = pages.get(
                    id=int(source_id)
                )
            except (
                ValueError,
                TypeError,
                DesignPage.DoesNotExist,
            ):
                return Response(
                    {
                        "error": (
                            "A página para duplicação "
                            "não pertence a este design."
                        )
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

        last_page = pages.last()

        page_order = (
            last_page.page_order + 1
            if last_page
            else 0
        )

        try:
            width = int(
                request.data.get("width")
                or (
                    source_page.width
                    if source_page
                    else (
                        last_page.width
                        if last_page
                        else 1080
                    )
                )
            )

            height = int(
                request.data.get("height")
                or (
                    source_page.height
                    if source_page
                    else (
                        last_page.height
                        if last_page
                        else 1080
                    )
                )
            )

        except (TypeError, ValueError):
            return Response(
                {
                    "error": (
                        "Largura e altura precisam "
                        "ser números inteiros."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if width < 1 or height < 1:
            return Response(
                {
                    "error": (
                        "Largura e altura precisam "
                        "ser maiores que zero."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        background_color = (
            request.data.get("background_color")
            or (
                source_page.background_color
                if source_page
                else (
                    last_page.background_color
                    if last_page
                    else "#FFFFFF"
                )
            )
        )

        page = DesignPage.objects.create(
            design=design,
            name=(
                request.data.get("name")
                or f"Página {page_order + 1}"
            ),
            page_order=page_order,
            width=width,
            height=height,
            background_color=background_color,
        )

        # Se duplicate_page_id foi informado,
        # copia os elementos da página de origem.
        if source_page is not None:
            for source in source_page.elements.order_by(
                "layer_order",
                "id",
            ):
                Element.objects.create(
                    design=design,
                    page=page,
                    type=source.type,
                    content=source.content,
                    posicao_x=source.posicao_x,
                    posicao_y=source.posicao_y,
                    width=source.width,
                    heigth=source.heigth,
                    color=source.color,
                    shape_type=source.shape_type,
                    stroke_width=source.stroke_width,
                    stroke_color=source.stroke_color,
                    font_size=source.font_size,
                    font_family=source.font_family,
                    font_weight=source.font_weight,
                    font_style=source.font_style,
                    text_align=source.text_align,
                    layer_order=source.layer_order,
                )

        serializer = self.get_serializer(design)

        return Response(
            serializer.data,
            status=status.HTTP_201_CREATED,
        )

    @action(
        detail=True,
        methods=["patch"],
        url_path="update-page",
    )
    def update_page(self, request, pk=None):
        design = self.get_object()

        try:
            page = design.pages.get(
                id=int(request.data.get("page_id"))
            )

        except (
            ValueError,
            TypeError,
            DesignPage.DoesNotExist,
        ):
            return Response(
                {
                    "error": (
                        "A página informada não "
                        "pertence a este design."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        for field in (
            "name",
            "background_color",
        ):
            if field in request.data:
                setattr(
                    page,
                    field,
                    request.data[field],
                )

        for field in ("width", "height"):
            if field not in request.data:
                continue

            try:
                value = int(request.data[field])

            except (TypeError, ValueError):
                return Response(
                    {
                        "error": (
                            f"O campo {field} "
                            "deve ser numérico."
                        )
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            if value < 1:
                return Response(
                    {
                        "error": (
                            f"O campo {field} "
                            "deve ser maior que zero."
                        )
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            setattr(page, field, value)

        page.save()

        return Response(
            self.get_serializer(design).data
        )

    @action(
        detail=True,
        methods=["delete"],
        url_path="delete-page",
    )
    @transaction.atomic
    def delete_page(self, request, pk=None):
        design = self.get_object()

        try:
            page = design.pages.get(
                id=int(request.data.get("page_id"))
            )

        except (
            ValueError,
            TypeError,
            DesignPage.DoesNotExist,
        ):
            return Response(
                {
                    "error": (
                        "A página informada não "
                        "pertence a este design."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if design.pages.count() <= 1:
            return Response(
                {
                    "error": (
                        "Um design precisa ter "
                        "pelo menos uma página."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        page.delete()

        # Reorganiza a ordem das páginas restantes.
        for order, remaining_page in enumerate(
            design.pages.order_by(
                "page_order",
                "id",
            )
        ):
            if remaining_page.page_order != order:
                remaining_page.page_order = order

                remaining_page.save(
                    update_fields=["page_order"]
                )

        return Response(
            self.get_serializer(design).data
        )

    @action(
        detail=True,
        methods=["patch"],
        url_path="reorder-elements",
    )
    def reorder_elements(self, request, pk=None):
        design = self.get_object()

        ordered_ids = request.data.get(
            "element_ids",
            [],
        )

        if not isinstance(ordered_ids, list):
            return Response(
                {
                    "error": (
                        "O campo 'element_ids' "
                        "deve ser uma lista."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            page = self._get_target_page(
                design,
                request.data.get("page_id"),
            )

        except ValueError as exc:
            return Response(
                {"error": str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        elements_by_id = {
            element.id: element
            for element in page.elements.all()
        }

        context = history.ChangeContext(
            user=request.user,
            design=design,
        )

        for new_order, element_id in enumerate(
            ordered_ids
        ):
            numeric_id = self._to_int_or_none(
                element_id
            )

            if numeric_id is None:
                continue

            element = elements_by_id.get(
                numeric_id
            )

            if element is None:
                continue

            if element.layer_order == new_order:
                continue

            history.log_field_change(
                context,
                history.TargetRef(
                    "element",
                    element.id,
                ),
                "layer_order",
                element.layer_order,
                new_order,
            )

            element.layer_order = new_order

            element.save(
                update_fields=["layer_order"]
            )

        serializer = self.get_serializer(design)

        return Response(serializer.data)

    @action(
        detail=True,
        methods=["patch"],
        url_path="save-elements",
    )
    @transaction.atomic
    def save_elements(self, request, pk=None):
        design = self.get_object()

        incoming_elements = request.data.get(
            "elements",
            [],
        )

        if not isinstance(incoming_elements, list):
            return Response(
                {
                    "error": (
                        "O campo 'elements' "
                        "deve ser uma lista."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            page = self._get_target_page(
                design,
                request.data.get("page_id"),
            )

        except ValueError as exc:
            return Response(
                {"error": str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        existing_elements = list(
            page.elements.all()
        )

        elements_by_id = {
            element.id: element
            for element in existing_elements
        }

        elements_by_client_id = {
            str(element.client_id): element
            for element in existing_elements
            if element.client_id
        }

        context = history.ChangeContext(
            user=request.user,
            design=design,
        )

        maintained_ids = set()

        for element_data in incoming_elements:
            if not isinstance(element_data, dict):
                continue

            element = self._find_existing_element(
                element_data,
                elements_by_id,
                elements_by_client_id,
            )

            if element is None:
                element = self._create_element(
                    design,
                    page,
                    element_data,
                    context,
                )

            else:
                self._update_element(
                    element,
                    element_data,
                    context,
                )

            maintained_ids.add(element.id)

        self._delete_removed_elements(
            existing_elements,
            maintained_ids,
            context,
        )

        design.refresh_from_db()

        serializer = self.get_serializer(design)

        return Response(serializer.data)

    @staticmethod
    def _get_target_page(design, page_id=None):
        pages = design.pages.order_by(
            "page_order",
            "id",
        )

        if page_id not in {None, ""}:
            try:
                return pages.get(
                    id=int(page_id)
                )

            except (
                ValueError,
                TypeError,
                DesignPage.DoesNotExist,
            ):
                raise ValueError(
                    "A página informada não "
                    "pertence a este design."
                )

        page = pages.first()

        if page is None:
            page = DesignPage.objects.create(
                design=design,
                name="Página 1",
                page_order=0,
                width=1080,
                height=1080,
            )

        return page

    def _find_existing_element(
        self,
        element_data,
        elements_by_id,
        elements_by_client_id,
    ):
        element_id = element_data.get("id")

        numeric_id = self._to_int_or_none(
            element_id
        )

        if numeric_id is not None:
            element = elements_by_id.get(
                numeric_id
            )

            if element is not None:
                return element

        client_id = element_data.get(
            "client_id"
        )

        if not client_id:
            return None

        return elements_by_client_id.get(
            str(client_id)
        )

    def _create_element(
        self,
        design,
        page,
        element_data,
        context,
    ):
        element = Element.objects.create(
            design=design,
            page=page,
            **self._element_fields(element_data),
        )

        history.log_creation(
            context,
            history.TargetRef(
                "element",
                element.id,
            ),
            description=(
                "Elemento criado pelo usuário no editor"
            ),
        )

        return element

    def _update_element(
        self,
        element,
        element_data,
        context,
    ):
        fields = self._element_fields(
            element_data
        )

        changed_fields = history.diff_and_log_instance(
            context,
            element,
            fields,
            Element.TRACKED_FIELDS,
            "element",
        )

        if changed_fields:
            element.save(
                update_fields=changed_fields
            )

    @staticmethod
    def _element_fields(element_data):
        return {
            "type": element_data.get(
                "type",
                "text",
            ),
            "content": element_data.get(
                "content",
                "",
            ),
            "posicao_x": DesignViewSet._to_int(
                element_data.get("posicao_x")
            ),
            "posicao_y": DesignViewSet._to_int(
                element_data.get("posicao_y")
            ),
            "width": DesignViewSet._to_int(
                element_data.get("width")
            ),
            "heigth": DesignViewSet._to_int(
                element_data.get("heigth")
            ),
            "color": element_data.get(
                "color",
                "",
            ),
            "shape_type": element_data.get(
                "shape_type"
            ),
            "stroke_width": DesignViewSet._to_int(
                element_data.get("stroke_width")
            ),
            "stroke_color": element_data.get(
                "stroke_color",
                "",
            ),
            "font_size": DesignViewSet._to_int_or_none(
                element_data.get("font_size")
            ),
            "font_family": element_data.get(
                "font_family",
                "Poppins",
            ),
            "font_weight": element_data.get(
                "font_weight",
                "normal",
            ),
            "font_style": element_data.get(
                "font_style",
                "normal",
            ),
            "text_align": element_data.get(
                "text_align",
                "left",
            ),
            "client_id": (
                element_data.get("client_id")
                or None
            ),
            "layer_order": DesignViewSet._to_int(
                element_data.get("layer_order")
            ),
        }

    @staticmethod
    def _to_int(value):
        try:
            return int(value or 0)

        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _to_int_or_none(value):
        if value in {None, ""}:
            return None

        try:
            return int(value)

        except (TypeError, ValueError):
            return None

    @staticmethod
    def _delete_removed_elements(
        existing_elements,
        maintained_ids,
        context,
    ):
        for element in existing_elements:
            if element.id in maintained_ids:
                continue

            history.log_deletion(
                context,
                history.TargetRef(
                    "element",
                    element.id,
                ),
                description=(
                    "Elemento removido do editor"
                ),
            )

            element.delete()
