import hashlib
from pathlib import PurePosixPath

from django.apps import apps
from django.db.models import Q

from payment.models import PaymentEvent

from .models import Product, ProductImage


BUNDLE_FORMAT_VERSION = 1
MIGRATION_MODEL_LABELS = (
    "auth.group",
    "accounts.user",
    "accounts.clientprofile",
    "accounts.adminprofile",
    "shop.category",
    "shop.product",
    "shop.productimage",
    "shop.wholesaleprice",
    "shop.cart",
    "shop.cartitem",
    "shop.address",
    "shop.order",
    "shop.orderitem",
    "shop.review",
    "payment.paymentevent",
)
MIGRATION_SEEDED_CATEGORY_SLUGS = {
    "mobile-accessories",
    "phone-accessories",
    "home-appliances",
    "cosmetics",
    "clothing",
    "shoes",
    "sport",
    "computers",
    "phones",
    "tablets",
    "beauty-care",
    "bags",
    "cookware",
    "household",
    "toys",
    "stationery",
    "headwear",
    "lighting",
    "decor",
    "home-textile",
    "bathroom",
    "home-accessories",
    "furniture",
}
TEST_MARKERS = ("test", "demo", "sample", "stub", "тест", "пример", "демо")


def sha256_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def model_counts():
    return {
        label: apps.get_model(label).objects.count()
        for label in MIGRATION_MODEL_LABELS
    }


def classify_existing_data():
    catalog_filter = Q()
    for marker in TEST_MARKERS:
        catalog_filter |= Q(name__icontains=marker) | Q(slug__icontains=marker)

    stub_events = PaymentEvent.objects.filter(
        Q(provider_event_id__startswith="stub-") | Q(payload__source="local_stub")
    ).values("pk", "provider_event_id", "payment_id")
    stub_orders = apps.get_model("shop.order").objects.filter(
        Q(payment_id__startswith="stub-") | Q(payment_link__contains="/pay/test/")
    ).values("pk", "order_number", "payment_id")
    catalog_candidates = Product.objects.filter(catalog_filter).values("pk", "name", "slug")
    User = apps.get_model("accounts.user")
    return {
        "requires_confirmation": {
            "stub_payment_events": list(stub_events),
            "stub_payment_orders": list(stub_orders),
            "test_named_products": list(catalog_candidates),
        },
        "informational_counts": {
            "unverified_clients": User.objects.filter(
                is_client=True,
                client_profile__phone_verified=False,
            ).count(),
            "inactive_administrators": User.objects.filter(
                Q(is_admin=True) | Q(is_staff=True),
                is_active=False,
            ).count(),
            "waiting_orders": apps.get_model("shop.order").objects.filter(
                payment_status="waiting"
            ).count(),
        },
    }


def classification_requires_confirmation(classification):
    return any(classification["requires_confirmation"].values())


def _normalize_media_name(name):
    normalized = str(name or "").replace("\\", "/")
    path = PurePosixPath(normalized)
    if not normalized or path.is_absolute() or ".." in path.parts or ":" in normalized:
        raise ValueError(f"Недопустимый путь media: {name}")
    return str(path)


def collect_media_references():
    references = []
    file_fields = {}
    sources = (
        (Product.objects.exclude(image="").only("pk", "image"), "image"),
        (Product.objects.exclude(video="").only("pk", "video"), "video"),
        (ProductImage.objects.exclude(image="").only("pk", "image"), "image"),
    )
    for queryset, field_name in sources:
        for instance in queryset.iterator():
            field_file = getattr(instance, field_name)
            if not field_file.name:
                continue
            name = _normalize_media_name(field_file.name)
            references.append(
                {
                    "model": instance._meta.label_lower,
                    "pk": instance.pk,
                    "field": field_name,
                    "name": name,
                }
            )
            file_fields.setdefault(name, field_file)
    return references, file_fields


def inspect_media_files(include_hashes=False):
    references, file_fields = collect_media_references()
    missing = []
    files = []
    for name, field_file in sorted(file_fields.items()):
        try:
            exists = field_file.storage.exists(field_file.name)
        except (OSError, ValueError):
            exists = False
        if not exists:
            missing.append(name)
            continue

        item = {"name": name, "size": field_file.size}
        if include_hashes:
            digest = hashlib.sha256()
            with field_file.open("rb") as source:
                for chunk in iter(lambda: source.read(1024 * 1024), b""):
                    digest.update(chunk)
            item["sha256"] = digest.hexdigest()
        files.append(item)
    return references, files, missing
