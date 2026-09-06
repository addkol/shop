import hashlib
import json
import os
import shutil
import tarfile
from importlib import import_module
from collections import Counter
from pathlib import Path

from django.apps import apps
from django.core.files.storage import FileSystemStorage, default_storage
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction

from shop.initial_data import (
    BUNDLE_FORMAT_VERSION,
    MIGRATION_MODEL_LABELS,
    MIGRATION_SEEDED_CATEGORY_SLUGS,
    classification_requires_confirmation,
    inspect_media_files,
    model_counts,
    sha256_file,
)


class Command(BaseCommand):
    help = "Однократно импортирует проверенный initial bundle в пустой PostgreSQL."

    def add_arguments(self, parser):
        parser.add_argument("bundle_dir", help="Каталог с manifest.json и артефактами bundle.")
        parser.add_argument("--confirm-import", action="store_true", help="Подтвердить первый import.")
        parser.add_argument(
            "--accept-classified-data",
            action="store_true",
            help="Подтвердить перенос перечисленных test/stub записей без удаления.",
        )
        parser.add_argument(
            "--restore-media",
            action="store_true",
            help="Восстановить media.tar.gz в MEDIA_ROOT перед импортом fixture.",
        )

    def handle(self, *args, **options):
        if connection.vendor != "postgresql":
            raise CommandError("Initial import разрешён только в PostgreSQL.")
        if not options["confirm_import"]:
            raise CommandError("Повторите команду с --confirm-import после проверки manifest.json.")

        bundle_dir = Path(options["bundle_dir"]).expanduser().resolve()
        manifest_path = bundle_dir / "manifest.json"
        fixture_path = bundle_dir / "initial-data.json"
        media_path = bundle_dir / "media.tar.gz"
        if not all(path.is_file() for path in (manifest_path, fixture_path, media_path)):
            raise CommandError("Bundle неполный: нужны manifest.json, initial-data.json и media.tar.gz.")

        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("format_version") != BUNDLE_FORMAT_VERSION:
            raise CommandError("Неподдерживаемая версия migration bundle.")
        if manifest.get("source_database") != "sqlite":
            raise CommandError("Источник bundle должен быть SQLite.")
        if (
            classification_requires_confirmation(manifest["classification"])
            and not options["accept_classified_data"]
        ):
            raise CommandError(
                "Manifest содержит test/stub кандидаты. Проверьте их и добавьте "
                "--accept-classified-data для переноса без удаления."
            )
        if set(manifest["artifacts"]) != {"initial-data.json", "media.tar.gz"}:
            raise CommandError("Некорректный список артефактов bundle.")
        for filename, expected_hash in manifest["artifacts"].items():
            artifact_path = bundle_dir / filename
            if not artifact_path.is_file() or sha256_file(artifact_path) != expected_hash:
                raise CommandError(f"Нарушена SHA-256 целостность {filename}.")

        fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
        if not isinstance(fixture, list) or any(
            not isinstance(record, dict) or record.get("model") not in MIGRATION_MODEL_LABELS
            for record in fixture
        ):
            raise CommandError("Fixture содержит недопустимые модели.")
        fixture_counts = Counter(record["model"] for record in fixture)
        if set(manifest["model_counts"]) != set(MIGRATION_MODEL_LABELS) or any(
            fixture_counts[label] != manifest["model_counts"][label] for label in MIGRATION_MODEL_LABELS
        ):
            raise CommandError("Manifest не соответствует количеству записей fixture.")
        self._assert_fresh_database()
        if options["restore_media"]:
            self._restore_media(media_path, manifest["media"]["files"])
        elif manifest["media"]["files"]:
            raise CommandError("Bundle содержит media. Для полного переноса нужен --restore-media.")

        expected_counts = manifest["model_counts"]
        with transaction.atomic():
            for label in MIGRATION_MODEL_LABELS:
                table = connection.ops.quote_name(apps.get_model(label)._meta.db_table)
                with connection.cursor() as cursor:
                    cursor.execute(f"LOCK TABLE {table} IN ACCESS EXCLUSIVE MODE")
            self._assert_fresh_database()
            apps.get_model("shop.category").objects.all().delete()
            call_command("loaddata", str(fixture_path), database="default", verbosity=0)
            actual_counts = model_counts()
            mismatches = {
                label: {"expected": expected_counts.get(label), "actual": actual_counts.get(label)}
                for label in MIGRATION_MODEL_LABELS
                if expected_counts.get(label) != actual_counts.get(label)
            }
            if mismatches:
                raise CommandError(
                    "Количество записей после import не совпало: "
                    + json.dumps(mismatches, ensure_ascii=False)
                )

            references, files, missing = inspect_media_files(include_hashes=True)
            expected_references = manifest["media"]["references"]
            expected_files = {item["name"]: item for item in manifest["media"]["files"]}
            actual_files = {item["name"]: item for item in files}
            reference_key = lambda item: (item["model"], item["pk"], item["field"], item["name"])
            if (
                sorted(references, key=reference_key) != sorted(expected_references, key=reference_key)
                or missing or actual_files != expected_files
            ):
                raise CommandError("Проверка media не пройдена; транзакция импорта БД отменена.")

        self.stdout.write(self.style.SUCCESS("SQLite bundle импортирован в PostgreSQL и проверен."))

    def _assert_fresh_database(self):
        nonempty = {
            label: count
            for label, count in model_counts().items()
            if count and label != "shop.category"
        }
        if nonempty:
            raise CommandError(
                "Целевая PostgreSQL уже содержит данные: "
                + json.dumps(nonempty, ensure_ascii=False)
            )
        Category = apps.get_model("shop.category")
        category_slugs = set(Category.objects.values_list("slug", flat=True))
        unexpected = category_slugs - MIGRATION_SEEDED_CATEGORY_SLUGS
        if unexpected:
            raise CommandError(
                "В PostgreSQL есть категории не из миграционного seed: " + ", ".join(sorted(unexpected))
            )
        seed = dict((slug, name) for name, slug in import_module("shop.migrations.0005_product_brand_and_catalog").CATALOG_CATEGORIES)
        for category in Category.objects.all():
            if seed.get(category.slug) != category.name or category.parent_id is not None:
                raise CommandError("Категории изменены после migrations; initial import запрещён.")

    def _restore_media(self, media_path, expected_file_list):
        if not isinstance(default_storage, FileSystemStorage):
            raise CommandError("Восстановление media.tar.gz поддерживает только локальный MEDIA_ROOT.")
        expected_files = {item["name"]: item for item in expected_file_list}
        media_root = Path(default_storage.location).resolve()
        media_root.mkdir(parents=True, exist_ok=True)

        with tarfile.open(media_path, "r:gz") as archive:
            members = archive.getmembers()
            actual_names = set()
            for member in members:
                if not member.isfile() or not member.name.startswith("media/"):
                    raise CommandError(f"Недопустимый объект в media archive: {member.name}")
                relative_name = member.name.removeprefix("media/")
                target = (media_root / relative_name).resolve()
                if media_root not in target.parents:
                    raise CommandError(f"Небезопасный путь в media archive: {member.name}")
                expected = expected_files.get(relative_name)
                if relative_name in actual_names:
                    raise CommandError(f"Повторный файл в media archive: {relative_name}")
                if expected is None:
                    raise CommandError(f"Лишний файл в media archive: {relative_name}")
                source = archive.extractfile(member)
                if source is None:
                    raise CommandError(f"Не удалось прочитать media: {relative_name}")
                digest = hashlib.sha256()
                for chunk in iter(lambda: source.read(1024 * 1024), b""):
                    digest.update(chunk)
                if member.size != expected["size"] or digest.hexdigest() != expected["sha256"]:
                    raise CommandError(f"Нарушена целостность media: {relative_name}")
                actual_names.add(relative_name)
            missing_from_archive = set(expected_files) - actual_names
            if missing_from_archive:
                raise CommandError(
                    "В media archive отсутствуют: " + ", ".join(sorted(missing_from_archive))
                )

        with tarfile.open(media_path, "r:gz") as archive:
            for member in archive.getmembers():
                relative_name = member.name.removeprefix("media/")
                target = (media_root / relative_name).resolve()
                target.parent.mkdir(parents=True, exist_ok=True)
                expected = expected_files[relative_name]
                if target.exists():
                    if sha256_file(target) != expected["sha256"]:
                        raise CommandError(f"Существующий media-файл отличается: {relative_name}")
                    continue
                source = archive.extractfile(member)
                temporary = target.with_name(f".{target.name}.initial-import")
                try:
                    with temporary.open("wb") as destination:
                        shutil.copyfileobj(source, destination, length=1024 * 1024)
                    os.chmod(temporary, 0o640)
                    os.replace(temporary, target)
                finally:
                    temporary.unlink(missing_ok=True)
