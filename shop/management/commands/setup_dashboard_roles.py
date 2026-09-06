from django.contrib.auth.models import Group, Permission
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction


READ_ORDERS = {"shop.view_order", "shop.view_orderitem"}
READ_CLIENTS = {"accounts.view_user", "shop.view_address", "accounts.view_clientprofile"}
READ_CATALOG = {"shop.view_product", "shop.view_category", "shop.view_productimage", "shop.view_wholesaleprice"}
CATALOG_EDIT = {
    "shop." + action + "_" + model
    for action in ("add", "change", "delete")
    for model in ("productimage", "wholesaleprice")
} | {"shop.add_product", "shop.change_product", "shop.add_category", "shop.change_category", "shop.adjust_stock"}
OPERATIONS = READ_ORDERS | READ_CLIENTS | READ_CATALOG | {"payment.view_paymentevent", "shop.view_review"}
ROLES = {
    "Owner": OPERATIONS | CATALOG_EDIT | {"shop.fulfill_order", "shop.cancel_order", "shop.change_order", "shop.change_review",
                                        "accounts.add_user", "accounts.change_user", "auth.view_group", "auth.add_group", "auth.change_group"},
    "Administrator": OPERATIONS | CATALOG_EDIT | {"shop.fulfill_order", "shop.cancel_order", "shop.change_order", "shop.change_review"},
    "Manager": OPERATIONS | CATALOG_EDIT | {"shop.fulfill_order", "shop.cancel_order", "shop.change_review"},
    "Warehouse": READ_ORDERS | READ_CATALOG | {"shop.fulfill_order", "shop.adjust_stock"},
    "Support": OPERATIONS | {"shop.cancel_order", "shop.change_review"},
}


class Command(BaseCommand):
    help = "Создать/синхронизировать стандартные группы dashboard. Не создаёт пользователей и пароли."

    @transaction.atomic
    def handle(self, *args, **options):
        permissions = {permission.content_type.app_label + "." + permission.codename: permission
                       for permission in Permission.objects.select_related("content_type")}
        for name, codes in ROLES.items():
            missing = codes - permissions.keys()
            if missing:
                raise CommandError("Сначала выполните migrate. Нет permissions: " + ", ".join(sorted(missing)))
            group, _ = Group.objects.get_or_create(name=name)
            group.permissions.set([permissions[code] for code in sorted(codes)])
            self.stdout.write(name + ": " + str(len(codes)) + " permissions")
