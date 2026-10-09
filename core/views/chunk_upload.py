import json
import logging
import shutil
import tempfile
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

from django.core.files import File
from django.db import transaction
from rest_framework import status
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.models import Design
from core.serializers.design import DesignSerializer
from core.services import history
from core.services.file_import import (
    UnsupportedFileType,
    import_file_into_design,
)

logger = logging.getLogger(__name__)

# O frontend envia partes de 64 KB.
# O limite interno permite até 128 KB por parte.
CHUNK_SIZE_LIMIT = 128 * 1024

MAX_CHUNKS = 10_000
MAX_FILE_SIZE = 500 * 1024 * 1024
UPLOAD_EXPIRY_SECONDS = 6 * 60 * 60

UPLOADS_ROOT = (
    Path(tempfile.gettempdir())
    / "pci-chunked-uploads"
)


class UploadRequestError(Exception):
    """Erro de validação de uma parte recebida."""

    def __init__(
        self,
        message,
        http_status=status.HTTP_400_BAD_REQUEST,
    ):
        super().__init__(message)
        self.http_status = http_status


@dataclass(frozen=True)
class ChunkMetadata:
    upload_id: str
    file_name: str
    chunk_index: int
    total_chunks: int
    total_size: int


def _upload_directory(user_id, upload_id):
    return UPLOADS_ROOT / str(user_id) / upload_id


def _cleanup_expired_uploads(user_id):
    user_root = UPLOADS_ROOT / str(user_id)

    if not user_root.exists():
        return

    now = time.time()

    for directory in user_root.iterdir():
        try:
            expired = (
                directory.is_dir()
                and now - directory.stat().st_mtime
                > UPLOAD_EXPIRY_SECONDS
            )
        except OSError:
            continue

        if expired:
            shutil.rmtree(
                directory,
                ignore_errors=True,
            )


def _safe_pptx_name(name):
    value = str(name or "").replace("\\", "/")
    safe_name = Path(value).name

    if not safe_name.lower().endswith(".pptx"):
        return None

    return safe_name[:255]


def _integer_field(data, key, default):
    try:
        return int(data.get(key, default))
    except (TypeError, ValueError, AttributeError) as exc:
        raise UploadRequestError(
            f"Metadado inválido: {key}."
        ) from exc


def _parse_request(request):
    data = request.data

    file_name = _safe_pptx_name(
        data.get("file_name")
    )

    chunk = request.FILES.get("chunk")

    try:
        upload_id = str(
            uuid.UUID(
                str(data.get("upload_id", ""))
            )
        )
    except (ValueError, AttributeError) as exc:
        raise UploadRequestError(
            "Identificador de upload inválido."
        ) from exc

    index = _integer_field(
        data,
        "chunk_index",
        -1,
    )

    count = _integer_field(
        data,
        "total_chunks",
        0,
    )

    total_size = _integer_field(
        data,
        "file_size",
        0,
    )

    if not file_name:
        raise UploadRequestError(
            "O arquivo precisa ter extensão .pptx."
        )

    if chunk is None:
        raise UploadRequestError(
            "Parte do arquivo não enviada."
        )

    if chunk.size <= 0 or chunk.size > CHUNK_SIZE_LIMIT:
        raise UploadRequestError(
            "A parte enviada excede o limite permitido."
        )

    if count < 1 or count > MAX_CHUNKS:
        raise UploadRequestError(
            "Quantidade de partes inválida."
        )

    if index < 0 or index >= count:
        raise UploadRequestError(
            "Índice da parte inválido."
        )

    if total_size <= 0 or total_size > MAX_FILE_SIZE:
        raise UploadRequestError(
            "Tamanho total do arquivo inválido."
        )

    metadata = ChunkMetadata(
        upload_id=upload_id,
        file_name=file_name,
        chunk_index=index,
        total_chunks=count,
        total_size=total_size,
    )

    return metadata, chunk


def _manifest(metadata):
    return {
        "file_name": metadata.file_name,
        "total_chunks": metadata.total_chunks,
        "file_size": metadata.total_size,
    }


def _validate_or_create_manifest(
    upload_dir,
    metadata,
):
    manifest_path = upload_dir / "metadata.json"
    expected = _manifest(metadata)

    if not manifest_path.exists():
        if metadata.chunk_index != 0:
            raise UploadRequestError(
                "Envie a primeira parte antes das demais."
            )

        manifest_path.write_text(
            json.dumps(expected),
            encoding="utf-8",
        )

        return

    try:
        stored = json.loads(
            manifest_path.read_text(
                encoding="utf-8"
            )
        )
    except (OSError, json.JSONDecodeError) as exc:
        raise UploadRequestError(
            "Metadados do upload inválidos."
        ) from exc

    if stored != expected:
        raise UploadRequestError(
            "As partes não pertencem ao mesmo upload."
        )


def _store_chunk(
    upload_dir,
    metadata,
    chunk,
):
    _validate_or_create_manifest(
        upload_dir,
        metadata,
    )

    chunk_path = (
        upload_dir
        / f"chunk_{metadata.chunk_index:06d}.part"
    )

    try:
        with chunk_path.open("wb") as target:
            for block in chunk.chunks():
                target.write(block)

    except OSError as exc:
        raise UploadRequestError(
            "Não foi possível salvar a parte recebida.",
            status.HTTP_500_INTERNAL_SERVER_ERROR,
        ) from exc


def _all_chunks_present(
    upload_dir,
    total_chunks,
):
    for index in range(total_chunks):
        part = (
            upload_dir
            / f"chunk_{index:06d}.part"
        )

        if not part.is_file():
            return False

    return True


def _assemble_file(
    upload_dir,
    metadata,
):
    target_path = upload_dir / "complete.pptx"
    assembled_size = 0

    try:
        with target_path.open("wb") as target:
            for index in range(metadata.total_chunks):
                part = (
                    upload_dir
                    / f"chunk_{index:06d}.part"
                )

                with part.open("rb") as source:
                    shutil.copyfileobj(
                        source,
                        target,
                        length=64 * 1024,
                    )

                assembled_size += part.stat().st_size

    except OSError as exc:
        raise UploadRequestError(
            "Não foi possível reconstruir a apresentação.",
            status.HTTP_500_INTERNAL_SERVER_ERROR,
        ) from exc

    if assembled_size != metadata.total_size:
        raise UploadRequestError(
            "O tamanho reconstruído difere do arquivo original."
        )

    return target_path


def _import_design(
    request,
    file_path,
    file_name,
):
    # Usa o mesmo importador do upload original.
    # O PPTX é reconstruído no backend antes da importação.
    with transaction.atomic():
        design = Design.objects.create(
            name=file_name.rsplit(".", 1)[0],
            created_by=request.user,
        )

        context = history.ChangeContext(
            user=request.user,
            design=design,
        )

        history.log_creation(
            context,
            history.TargetRef(
                "design",
                design.id,
            ),
            description="Design criado via upload segmentado",
        )

        with file_path.open("rb") as source:
            import_file_into_design(
                File(source, name=file_name),
                design,
                request.user,
            )

        return DesignSerializer(
            design,
            context={"request": request},
        ).data


def _receive_chunk(request):
    metadata, chunk = _parse_request(request)

    _cleanup_expired_uploads(request.user.pk)

    upload_dir = _upload_directory(
        request.user.pk,
        metadata.upload_id,
    )

    upload_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    _store_chunk(
        upload_dir,
        metadata,
        chunk,
    )

    if not _all_chunks_present(
        upload_dir,
        metadata.total_chunks,
    ):
        return (
            {
                "received": True,
                "complete": False,
                "chunk_index": metadata.chunk_index,
                "total_chunks": metadata.total_chunks,
            },
            status.HTTP_200_OK,
        )

    try:
        assembled_path = _assemble_file(
            upload_dir,
            metadata,
        )

        result = _import_design(
            request,
            assembled_path,
            metadata.file_name,
        )

        return result, status.HTTP_201_CREATED

    finally:
        shutil.rmtree(
            upload_dir,
            ignore_errors=True,
        )


class ChunkedDesignUploadView(APIView):
    """Recebe PPTX em partes pequenas e importa no backend."""

    permission_classes = [IsAuthenticated]

    parser_classes = [
        MultiPartParser,
        FormParser,
    ]

    def post(self, request):
        try:
            data, response_status = _receive_chunk(
                request
            )

        except UploadRequestError as exc:
            return Response(
                {"error": str(exc)},
                status=exc.http_status,
            )

        except UnsupportedFileType as exc:
            return Response(
                {"error": str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        except Exception:
            logger.exception(
                "Falha ao importar PPTX segmentado"
            )

            return Response(
                {
                    "error": (
                        "Não foi possível importar "
                        "a apresentação."
                    )
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        return Response(
            data,
            status=response_status,
        )
