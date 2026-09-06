import json

from django.core.management.base import BaseCommand, CommandError

from shop.initial_data import inspect_media_files


class Command(BaseCommand):
    help = "Проверяет существование всех файлов, на которые ссылаются Product и ProductImage."

    def add_arguments(self, parser):
        parser.add_argument("--json", action="store_true", help="Вывести результат в JSON.")

    def handle(self, *args, **options):
        references, files, missing = inspect_media_files(include_hashes=False)
        result = {
            "references": len(references),
            "unique_files": len(files),
            "missing": missing,
        }
        if options["json"]:
            self.stdout.write(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            self.stdout.write(
                f"Ссылок: {result['references']}; файлов: {result['unique_files']}; "
                f"отсутствует: {len(missing)}"
            )
        if missing:
            raise CommandError("Не найдены media-файлы: " + ", ".join(missing))
        self.stdout.write(self.style.SUCCESS("Все ссылки FileField/ImageField существуют."))
