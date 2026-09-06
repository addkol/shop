import json
import os
import shutil
import tarfile
import time
from pathlib import Path
from io import StringIO

import django
from django.contrib.auth.models import Permission
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction
from django.utils import timezone

from shop.initial_data import (
    BUNDLE_FORMAT_VERSION,
    MIGRATION_MODEL_LABELS,
    classification_requires_confirmation,
    classify_existing_data,
    collect_media_references,
    inspect_media_files,
    model_counts,
    sha256_file,
)


class Command(BaseCommand):
    help = "Классифицирует SQLite-данные и создаёт проверяемый bundle для первого PostgreSQL import."

    def add_arguments(self, parser):
        parser.add_argument("--output-dir", help="Новый каталог для migration bundle.")
        parser.add_argument(
            "--audit-only",
            action="store_true",
            help="Только показать классификацию, не создавать bundle.",
        )
        parser.add_argument(
            "--accept-classified-data",
            action="store_true",
            help="Явно включить найденные test/stub записи без удаления.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        if connection.vendor != "sqlite":
            raise CommandError("Экспорт первого bundle разрешён только из SQLite.")

        classification = classify_existing_data()
        self.stdout.write("Классификация данных перед экспортом:")
        self.stdout.write(json.dumps(classification, ensure_ascii=False, indent=2, default=str))
        if options["audit_only"]:
            return
        if not options["output_dir"]:
            raise CommandError("Для экспорта укажите --output-dir.")
        if classification_requires_confirmation(classification) and not options["accept_classified_data"]:
            raise CommandError(
                "Найдены test/stub кандидаты. Проверьте список и повторите команду с "
                "--accept-classified-data, чтобы перенести их без удаления."
            )

        output_dir = Path(options["output_dir"]).expanduser().resolve()
        if output_dir.exists():
            raise CommandError(f"Каталог bundle уже существует: {output_dir}")

        references, media_files, missing = inspect_media_files(include_hashes=True)
        if missing:
            raise CommandError(
                "Экспорт остановлен: отсутствуют media-файлы: " + ", ".join(missing)
            )
        _, field_files = collect_media_references()

        fixture_path = output_dir / "initial-data.json"
        media_path = output_dir / "media.tar.gz"
        manifest_path = output_dir / "manifest.json"
        checksum_path = output_dir / "SHA256SUMS"
        try:
            output_dir.mkdir(parents=True, mode=0o700)
            fixture_stream = StringIO()
            call_command(
                "dumpdata",
                *MIGRATION_MODEL_LABELS,
                database="default",
                natural_foreign=False,
                natural_primary=False,
                indent=2,
                stdout=fixture_stream,
                verbosity=0,
            )
            fixture = json.loads(fixture_stream.getvalue())
            permissions = {permission.pk: permission.natural_key() for permission in Permission.objects.select_related("content_type")}
            for record in fixture:
                permission_field = {"accounts.user": "user_permissions", "auth.group": "permissions"}.get(record["model"])
                if permission_field:
                    record["fields"][permission_field] = [permissions[pk] for pk in record["fields"][permission_field]]
            fixture_path.write_text(json.dumps(fixture, ensure_ascii=False, indent=2), encoding="utf-8")
            with tarfile.open(media_path, "w:gz") as archive:
                for item in media_files:
                    field_file = field_files[item["name"]]
                    info = tarfile.TarInfo(name=f"media/{item['name']}")
                    info.size = item["size"]
                    info.mode = 0o640
                    info.mtime = int(time.time())
                    with field_file.open("rb") as source:
                        archive.addfile(info, source)

            manifest = {
                "format_version": BUNDLE_FORMAT_VERSION,
                "created_at": timezone.now().isoformat(),
                "source_database": "sqlite",
                "django_version": django.get_version(),
                "model_counts": model_counts(),
                "classification": classification,
                "media": {
                    "references": references,
                    "files": media_files,
                    "missing": [],
                },
                "artifacts": {
                    fixture_path.name: sha256_file(fixture_path),
                    media_path.name: sha256_file(media_path),
                },
            }
            manifest_path.write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2, default=str) + "\n",
                encoding="utf-8",
            )
            checksum_path.write_text(
                "\n".join(
                    [
                        f"{manifest['artifacts'][fixture_path.name]}  {fixture_path.name}",
                        f"{manifest['artifacts'][media_path.name]}  {media_path.name}",
                        f"{sha256_file(manifest_path)}  {manifest_path.name}",
                    ]
                )
                + "\n",
                encoding="ascii",
            )
            for path in (fixture_path, media_path, manifest_path, checksum_path):
                os.chmod(path, 0o600)
            os.chmod(output_dir, 0o700)
        except Exception:
            shutil.rmtree(output_dir, ignore_errors=True)
            raise

        self.stdout.write(self.style.SUCCESS(f"Migration bundle создан: {output_dir}"))
        self.stdout.write(f"SHA256SUMS: {sha256_file(checksum_path)}")
