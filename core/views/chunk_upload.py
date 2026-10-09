import json
import logging
import shutil
import tempfile
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.files import File
from django.db import close_old_connections, transaction
from rest_framework import status
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.renderers import JSONRenderer
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

CHUNK_SIZE_LIMIT = 128 * 1024
MAX_CHUNKS = 10_000
MAX_FILE_SIZE = 500 * 1024 * 1024
UPLOAD_EXPIRY_SECONDS = 6 * 60 * 60
UPLOADS_ROOT = Path(tempfile.gettempdir()) / "pci-chunked-uploads"


class UploadRequestError(Exception):
    def __init__(self, message, http_status=status.HTTP_400_BAD_REQUEST):
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


def _status_path(upload_dir):
    return upload_dir / "status.json"


def _write_status(upload_dir, data):
    temporary = upload_dir / f"status-{uuid.uuid4().hex}.tmp"
    temporary.write_text(json.dumps(data), encoding="utf-8")
    temporary.replace(_status_path(upload_dir))


def _read_status(upload_dir):
    path = _status_path(upload_dir)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"state": "failed", "complete": True, "error": "Não foi possível ler o estado do processamento."}


def _cleanup_expired_uploads(user_id):
    user_root = UPLOADS_ROOT / str(user_id)
    if not user_root.exists():
        return

    now = time.time()
    for directory in user_root.iterdir():
        try:
            expired = directory.is_dir() and now - directory.stat().st_mtime > UPLOAD_EXPIRY_SECONDS
        except OSError:
            continue
        if expired:
            shutil.rmtree(directory, ignore_errors=True)


def _safe_pptx_name(name):
    safe_name = Path((name or "").replace("\\", "/")).name
    if not safe_name.lower().endswith(".pptx"):
        return None
    return safe_name[:255]


def _integer_field(data, key, default):
    try:
        return int(data.get(key, default))
    except (ValueError, TypeError, AttributeError) as exc:
        raise UploadRequestError(f"Metadado inválido: {key}.") from exc


def _parse_request(request):
    data = request.data
    file_name = _safe_pptx_name(data.get("file_name", ""))
    chunk = request.FILES.get("chunk")

    try:
        upload_id = str(uuid.UUID(str(data.get("upload_id", ""))))
    except (ValueError, AttributeError) as exc:
        raise UploadRequestError("Identificador de upload inválido.") from exc

    index = _integer_field(data, "chunk_index", -1)
    count = _integer_field(data, "total_chunks", 0)
    total_size = _integer_field(data, "file_size", 0)

    if not file_name:
        raise UploadRequestError("O arquivo precisa ter extensão .pptx.")
    if chunk is None or chunk.size <= 0:
        raise UploadRequestError("Parte do arquivo ausente ou vazia.")
    if chunk.size > CHUNK_SIZE_LIMIT:
        raise UploadRequestError("A parte enviada excede 128 KB.")
    if count < 1 or count > MAX_CHUNKS or index < 0 or index >= count:
        raise UploadRequestError("Índice ou quantidade de partes inválido.")
    if total_size <= 0 or total_size > MAX_FILE_SIZE:
        raise UploadRequestError("Tamanho total do arquivo inválido.")

    return ChunkMetadata(upload_id, file_name, index, count, total_size), chunk


def _manifest(metadata):
    return {
        "file_name": metadata.file_name,
        "total_chunks": metadata.total_chunks,
        "file_size": metadata.total_size,
    }


def _store_chunk(upload_dir, metadata, chunk):
    metadata_path = upload_dir / "metadata.json"
    expected = _manifest(metadata)

    if metadata_path.exists():
        try:
            saved = json.loads(metadata_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise UploadRequestError("Metadados de upload inválidos.") from exc
        if saved != expected:
            raise UploadRequestError("As partes não pertencem ao mesmo upload.")
    else:
        if metadata.chunk_index != 0:
            raise UploadRequestError("Envie a primeira parte antes das demais.")
        metadata_path.write_text(json.dumps(expected), encoding="utf-8")

    path = upload_dir / f"chunk_{metadata.chunk_index:06d}.part"
    try:
        with path.open("wb") as destination:
            for block in chunk.chunks():
                destination.write(block)
    except OSError as exc:
        raise UploadRequestError(
            "Não foi possível salvar a parte recebida.",
            status.HTTP_500_INTERNAL_SERVER_ERROR,
        ) from exc


def _all_chunks_present(upload_dir, total_chunks):
    return all(
        (upload_dir / f"chunk_{index:06d}.part").is_file()
        for index in range(total_chunks)
    )


def _assemble_file(upload_dir, metadata):
    target = upload_dir / "complete.pptx"
    size = 0

    with target.open("wb") as destination:
        for index in range(metadata.total_chunks):
            part = upload_dir / f"chunk_{index:06d}.part"
            if not part.is_file():
                raise UploadRequestError("Uma parte do arquivo está faltando.")
            with part.open("rb") as source:
                shutil.copyfileobj(source, destination, length=64 * 1024)
            size += part.stat().st_size

    if size != metadata.total_size:
        raise UploadRequestError(
            f"Tamanho reconstruído incorreto: esperado {metadata.total_size}, recebido {size}."
        )
    return target


def _import_design(file_path, file_name, user_id):
    user_model = get_user_model()
    user = user_model.objects.get(pk=user_id)

    with transaction.atomic():
        design = Design.objects.create(
            name=file_name.rsplit(".", 1)[0],
            created_by=user,
        )
        context = history.ChangeContext(user=user, design=design)
        history.log_creation(
            context,
            history.TargetRef("design", design.id),
            description="Design criado via upload segmentado",
        )

        with file_path.open("rb") as source:
            import_file_into_design(File(source, name=file_name), design, user)

        serialized = DesignSerializer(design).data
        return json.loads(JSONRenderer().render(serialized))


def _remove_payload_files(upload_dir):
    for path in upload_dir.iterdir():
        if path.name not in {"metadata.json", "status.json"}:
            if path.is_dir():
                shutil.rmtree(path, ignore_errors=True)
            else:
                try:
                    path.unlink(missing_ok=True)
                except OSError:
                    logger.warning("Não foi possível remover %s", path)


def _finish_successful_upload(upload_dir, metadata, user_id):
    """Reconstrói, importa e registra o resultado bem-sucedido."""
    assembled = _assemble_file(upload_dir, metadata)
    design_data = _import_design(
        assembled,
        metadata.file_name,
        user_id,
    )

    _remove_payload_files(upload_dir)
    _write_status(
        upload_dir,
        {
            "state": "complete",
            "complete": True,
            "design": design_data,
        },
    )


def _finish_failed_upload(upload_dir, error):
    """Registra o erro sem substituir o traceback original."""
    _remove_payload_files(upload_dir)
    _write_status(
        upload_dir,
        {
            "state": "failed",
            "complete": True,
            "error": f"{type(error).__name__}: {error}",
        },
    )


def _process_upload(upload_dir, metadata, user_id):
    # A importação ocorre fora da requisição HTTP para evitar que o proxy
    # interrompa a última requisição enquanto extrai slides e imagens.
    close_old_connections()
    try:
        _finish_successful_upload(
            upload_dir,
            metadata,
            user_id,
        )
    except UnsupportedFileType as exc:
        logger.exception(
            "Tipo de arquivo não suportado no upload segmentado"
        )
        try:
            _finish_failed_upload(upload_dir, exc)
        except OSError:
            logger.exception(
                "Não foi possível salvar o estado de erro do upload"
            )
    except Exception as exc:
        logger.exception("Falha ao importar PPTX segmentado")
        try:
            _finish_failed_upload(upload_dir, exc)
        except OSError:
            logger.exception(
                "Não foi possível salvar o estado de erro do upload"
            )
    finally:
        close_old_connections()


def _handle_chunk(request):
    metadata, chunk = _parse_request(request)
    _cleanup_expired_uploads(request.user.pk)
    upload_dir = _upload_directory(request.user.pk, metadata.upload_id)
    upload_dir.mkdir(parents=True, exist_ok=True)

    # Se já está processando ou terminou, não reinicie o trabalho.
    existing_status = _read_status(upload_dir)
    if existing_status and existing_status.get("state") in {"processing", "complete", "failed"}:
        return existing_status, status.HTTP_200_OK

    _store_chunk(upload_dir, metadata, chunk)

    if not _all_chunks_present(upload_dir, metadata.total_chunks):
        return {
            "received": True,
            "complete": False,
            "chunk_index": metadata.chunk_index,
            "total_chunks": metadata.total_chunks,
        }, status.HTTP_200_OK

    _write_status(upload_dir, {
        "state": "processing",
        "complete": False,
        "message": "Arquivo recebido; importação em andamento.",
    })

    worker = threading.Thread(
        target=_process_upload,
        args=(upload_dir, metadata, request.user.pk),
        daemon=True,
        name=f"pptx-import-{metadata.upload_id}",
    )
    worker.start()

    return {
        "state": "processing",
        "received": True,
        "complete": False,
        "message": "Arquivo recebido; importação iniciada.",
    }, status.HTTP_202_ACCEPTED


class ChunkedDesignUploadView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        try:
            data, response_status = _handle_chunk(request)
        except UploadRequestError as exc:
            return Response({"error": str(exc)}, status=exc.http_status)
        except Exception:
            logger.exception("Falha ao receber parte do PPTX")
            return Response(
                {"error": "Não foi possível receber a parte do PPTX."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        return Response(data, status=response_status)

    def get(self, request):
        try:
            upload_id = str(uuid.UUID(str(request.query_params.get("upload_id", ""))))
        except (ValueError, AttributeError):
            return Response(
                {"error": "Identificador de upload inválido."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        upload_dir = _upload_directory(request.user.pk, upload_id)
        result = _read_status(upload_dir)

        if result is None:
            return Response({
                "state": "uploading",
                "complete": False,
            })

        return Response(result)
