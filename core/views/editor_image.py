"""Biblioteca de imagens privada usada exclusivamente pelo editor."""
import mimetypes

from django.http import FileResponse
from rest_framework import mixins, parsers, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.models.editor_image import EditorImage
from core.serializers.editor_image import EditorImageSerializer
from core.services.editor_images import save_editor_image_once


class EditorImageViewSet(
    mixins.ListModelMixin, mixins.CreateModelMixin,
    mixins.RetrieveModelMixin, viewsets.GenericViewSet,
):
    serializer_class = EditorImageSerializer
    permission_classes = [IsAuthenticated]
    parser_classes = [parsers.MultiPartParser, parsers.FormParser]

    def get_queryset(self):
        return EditorImage.objects.filter(owner=self.request.user)

    def create(self, request, *args, **kwargs):
        uploaded = request.FILES.get('file')
        if uploaded is None:
            return Response(
                {'error': 'Envie um arquivo no campo file.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            image, created = save_editor_image_once(
                uploaded, request.user, request.data.get('description', ''),
            )
        except ValueError as exc:
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        image.was_reused = not created
        return Response(
            self.get_serializer(image).data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )

    @action(detail=True, methods=['get'], url_path='content')
    def content(self, request, pk=None):
        image = self.get_object()  # 404 se outra pessoa tentar acessar.
        handle = image.file.open('rb')
        mime, _ = mimetypes.guess_type(image.file.name)
        response = FileResponse(handle, content_type=mime or 'application/octet-stream')
        response['Cache-Control'] = 'private, no-store'
        response['X-Content-Type-Options'] = 'nosniff'
        return response
