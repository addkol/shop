from pathlib import Path
from tempfile import TemporaryDirectory

from django.test import RequestFactory, SimpleTestCase, TestCase, override_settings

from .media_views import serve_media


class HealthCheckTests(TestCase):
    def test_health_check_reports_database_status(self):
        response = self.client.get("/health/")

        self.assertEqual(response.status_code, 200)
        self.assertJSONEqual(
            response.content,
            {"status": "ok", "checks": {"database": "ok", "cache": "ok"}},
        )

    def test_liveness_check(self):
        response = self.client.get("/health/live/")

        self.assertEqual(response.status_code, 200)
        self.assertJSONEqual(response.content, {"status": "ok"})

    @override_settings(SECURE_SSL_REDIRECT=True)
    def test_internal_health_check_is_exempt_from_https_redirect(self):
        response = self.client.get("/health/live/")

        self.assertEqual(response.status_code, 200)


class MediaServingTests(SimpleTestCase):
    def test_local_media_view_serves_existing_file(self):
        with TemporaryDirectory() as directory:
            file_path = Path(directory) / "products" / "photo.jpg"
            file_path.parent.mkdir()
            file_path.write_bytes(b"test-image")
            request = RequestFactory().get("/media/products/photo.jpg")

            with override_settings(MEDIA_ROOT=directory):
                response = serve_media(request, "products/photo.jpg")
                try:
                    self.assertEqual(response.status_code, 200)
                    self.assertEqual(response.headers["Cache-Control"], "public, max-age=86400")
                    self.assertEqual(response.headers["Accept-Ranges"], "bytes")
                finally:
                    response.close()

    def test_local_media_view_serves_byte_range(self):
        with TemporaryDirectory() as directory:
            file_path = Path(directory) / "products" / "video.mp4"
            file_path.parent.mkdir()
            file_path.write_bytes(b"0123456789")
            request = RequestFactory().get("/media/products/video.mp4", HTTP_RANGE="bytes=2-5")

            with override_settings(MEDIA_ROOT=directory):
                response = serve_media(request, "products/video.mp4")
                try:
                    self.assertEqual(response.status_code, 206)
                    self.assertEqual(response.headers["Content-Range"], "bytes 2-5/10")
                    self.assertEqual(b"".join(response.streaming_content), b"2345")
                finally:
                    response.close()

    def test_local_media_view_rejects_invalid_range(self):
        with TemporaryDirectory() as directory:
            file_path = Path(directory) / "products" / "video.mp4"
            file_path.parent.mkdir()
            file_path.write_bytes(b"0123456789")
            request = RequestFactory().get("/media/products/video.mp4", HTTP_RANGE="bytes=20-30")

            with override_settings(MEDIA_ROOT=directory):
                response = serve_media(request, "products/video.mp4")

            self.assertEqual(response.status_code, 416)
            self.assertEqual(response.headers["Content-Range"], "bytes */10")
