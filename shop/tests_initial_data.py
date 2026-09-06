import json
import tarfile
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import skipUnless

from django.core.files.base import ContentFile
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings
from django.db import connection

from payment.models import PaymentEvent

from .models import Category, Product


class InitialDataBundleTests(TestCase):
    def setUp(self):
        self.category = Category.objects.create(name="Перенос", slug="initial-data-transfer")

    @skipUnless(connection.vendor == "sqlite", "SQLite export test")
    def test_export_requires_explicit_acceptance_for_classified_stub_data(self):
        PaymentEvent.objects.create(
            provider_event_id="stub-classified-event",
            payment_id="stub-classified-payment",
            status="success",
            payload={"source": "local_stub"},
        )
        with TemporaryDirectory() as directory:
            output_dir = Path(directory) / "bundle"

            with self.assertRaises(CommandError):
                call_command("export_initial_data", output_dir=str(output_dir), stdout=StringIO())

            self.assertFalse(output_dir.exists())

    @skipUnless(connection.vendor == "sqlite", "SQLite export test")
    def test_export_contains_fixture_media_hashes_and_classification(self):
        with TemporaryDirectory() as media_directory, TemporaryDirectory() as output_parent:
            with override_settings(MEDIA_ROOT=media_directory):
                product = Product.objects.create(
                    name="Товар для переноса",
                    slug="initial-data-product",
                    description="Описание",
                    price="100.00",
                    stock=2,
                    category=self.category,
                )
                product.image.save("photo.jpg", ContentFile(b"image-content"), save=True)
                PaymentEvent.objects.create(
                    provider_event_id="stub-export-event",
                    payment_id="stub-export-payment",
                    status="success",
                    payload={"source": "local_stub"},
                )
                output_dir = Path(output_parent) / "bundle"

                call_command(
                    "export_initial_data",
                    output_dir=str(output_dir),
                    accept_classified_data=True,
                    stdout=StringIO(),
                )

                manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
                self.assertEqual(manifest["source_database"], "sqlite")
                self.assertEqual(manifest["model_counts"]["shop.product"], 1)
                self.assertTrue(
                    manifest["classification"]["requires_confirmation"]["stub_payment_events"]
                )
                self.assertEqual(manifest["media"]["files"][0]["name"], product.image.name)
                with tarfile.open(output_dir / "media.tar.gz", "r:gz") as archive:
                    self.assertEqual(archive.getnames(), [f"media/{product.image.name}"])

    def test_verify_media_references_fails_for_missing_file(self):
        Product.objects.create(
            name="Товар без файла",
            slug="missing-media-product",
            description="Описание",
            price="100.00",
            stock=2,
            category=self.category,
            image="products/missing.jpg",
        )

        with TemporaryDirectory() as media_directory, override_settings(MEDIA_ROOT=media_directory):
            with self.assertRaises(CommandError):
                call_command("verify_media_references", stdout=StringIO())

    @skipUnless(connection.vendor != "postgresql", "Non-PostgreSQL guard test")
    def test_import_refuses_non_postgresql_database(self):
        with TemporaryDirectory() as directory:
            with self.assertRaisesMessage(CommandError, "только в PostgreSQL"):
                call_command(
                    "import_initial_data",
                    directory,
                    confirm_import=True,
                    stdout=StringIO(),
                )
