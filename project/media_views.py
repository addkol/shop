import mimetypes
import re
from pathlib import Path

from django.conf import settings
from django.http import FileResponse, Http404, HttpResponse, StreamingHttpResponse
from django.utils._os import safe_join
from django.utils.http import content_disposition_header, http_date


RANGE_HEADER_PATTERN = re.compile(r"bytes=(\d*)-(\d*)")


def _file_iterator(file_path, start, length, chunk_size=64 * 1024):
    with file_path.open("rb") as file_handle:
        file_handle.seek(start)
        remaining = length
        while remaining > 0:
            chunk = file_handle.read(min(chunk_size, remaining))
            if not chunk:
                break
            remaining -= len(chunk)
            yield chunk


def _range_response(file_path, content_type, range_header):
    file_size = file_path.stat().st_size
    match = RANGE_HEADER_PATTERN.fullmatch(range_header.strip())
    if not match or file_size == 0:
        response = HttpResponse(status=416)
        response.headers["Content-Range"] = f"bytes */{file_size}"
        return response

    start_text, end_text = match.groups()
    if start_text:
        start = int(start_text)
        end = int(end_text) if end_text else file_size - 1
        if start >= file_size or end < start:
            response = HttpResponse(status=416)
            response.headers["Content-Range"] = f"bytes */{file_size}"
            return response
        end = min(end, file_size - 1)
    else:
        suffix_length = int(end_text or 0)
        if suffix_length <= 0:
            response = HttpResponse(status=416)
            response.headers["Content-Range"] = f"bytes */{file_size}"
            return response
        start = max(file_size - suffix_length, 0)
        end = file_size - 1

    length = end - start + 1
    response = StreamingHttpResponse(
        _file_iterator(file_path, start, length),
        status=206,
        content_type=content_type,
    )
    response.headers["Content-Length"] = str(length)
    response.headers["Content-Range"] = f"bytes {start}-{end}/{file_size}"
    return response


def serve_media(request, path):
    try:
        file_path = Path(safe_join(settings.MEDIA_ROOT, path))
    except ValueError as exc:
        raise Http404 from exc
    if not file_path.is_file():
        raise Http404

    content_type, encoding = mimetypes.guess_type(file_path.name)
    range_header = request.headers.get("Range", "")
    if range_header:
        response = _range_response(file_path, content_type, range_header)
    else:
        response = FileResponse(file_path.open("rb"), content_type=content_type)
    if encoding:
        response.headers["Content-Encoding"] = encoding
    response.headers["Accept-Ranges"] = "bytes"
    response.headers["Last-Modified"] = http_date(file_path.stat().st_mtime)
    response.headers["Content-Disposition"] = content_disposition_header(False, file_path.name)
    response.headers["Cache-Control"] = "public, max-age=86400"
    return response
