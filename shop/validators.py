from pathlib import Path

from django.core.exceptions import ValidationError


IMAGE_EXTENSIONS = {"jpg", "jpeg", "png", "webp"}
IMAGE_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}
VIDEO_EXTENSIONS = {"mp4", "webm", "mov"}
VIDEO_CONTENT_TYPES = {"video/mp4", "video/webm", "video/quicktime"}
MAX_IMAGE_SIZE = 10 * 1024 * 1024
MAX_VIDEO_SIZE = 100 * 1024 * 1024


def _read_header(upload, size=16):
    position = upload.tell() if hasattr(upload, "tell") else None
    try:
        upload.seek(0)
        return upload.read(size)
    finally:
        if position is not None:
            upload.seek(position)


def _signature_matches(extension, header):
    signatures = {
        "jpg": header.startswith(b"\xff\xd8\xff"),
        "jpeg": header.startswith(b"\xff\xd8\xff"),
        "png": header.startswith(b"\x89PNG\r\n\x1a\n"),
        "webp": header.startswith(b"RIFF") and header[8:12] == b"WEBP",
        "mp4": header[4:8] == b"ftyp",
        "mov": header[4:8] == b"ftyp",
        "webm": header.startswith(b"\x1aE\xdf\xa3"),
    }
    return signatures.get(extension, False)


def _validate_upload(upload, extensions, content_types, max_size, file_label):
    extension = Path(upload.name).suffix.lower().lstrip(".")
    if extension not in extensions:
        raise ValidationError(f"Недопустимый формат файла «{file_label}».")
    if upload.size > max_size:
        size_mb = max_size // (1024 * 1024)
        raise ValidationError(f"Размер файла «{file_label}» не должен превышать {size_mb} МБ.")
    content_type = getattr(upload, "content_type", "")
    if content_type and content_type not in content_types:
        raise ValidationError(f"Содержимое файла «{file_label}» не соответствует его формату.")
    if not _signature_matches(extension, _read_header(upload)):
        raise ValidationError(f"Фактическое содержимое файла «{file_label}» не соответствует расширению.")


def validate_product_image(upload):
    _validate_upload(upload, IMAGE_EXTENSIONS, IMAGE_CONTENT_TYPES, MAX_IMAGE_SIZE, "изображение")


def validate_product_video(upload):
    _validate_upload(upload, VIDEO_EXTENSIONS, VIDEO_CONTENT_TYPES, MAX_VIDEO_SIZE, "видео")
