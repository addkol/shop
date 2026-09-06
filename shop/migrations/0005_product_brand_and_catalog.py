from django.db import migrations, models


CATALOG_CATEGORIES = [
    ("Мобильные аксессуары", "mobile-accessories"),
    ("Техника для дома и кухни", "home-appliances"),
    ("Косметика", "cosmetics"),
    ("Одежда", "clothing"),
    ("Обувь", "shoes"),
    ("Спорт и отдых", "sport"),
    ("Компьютеры и ноутбуки", "computers"),
    ("Телефоны", "phones"),
    ("Планшеты", "tablets"),
    ("Красота и уход", "beauty-care"),
    ("Сумки и рюкзаки", "bags"),
    ("Посуда", "cookware"),
    ("Хозтовары", "household"),
    ("Игрушки", "toys"),
    ("Канцелярские товары", "stationery"),
    ("Головные уборы", "headwear"),
    ("Освещение и люстры", "lighting"),
    ("Для декора", "decor"),
    ("Текстиль для дома", "home-textile"),
    ("Для ванны", "bathroom"),
    ("Аксессуары для дома", "home-accessories"),
    ("Мебель для дома", "furniture"),
]


def seed_catalog(apps, schema_editor):
    Category = apps.get_model("shop", "Category")
    Product = apps.get_model("shop", "Product")

    electronics = Category.objects.filter(slug="electronics").first()
    if electronics:
        electronics.name = "Мобильные аксессуары"
        electronics.slug = "mobile-accessories"
        electronics.save(update_fields=["name", "slug"])

    home = Category.objects.filter(slug="home").first()
    if home:
        home.name = "Техника для дома и кухни"
        home.slug = "home-appliances"
        home.save(update_fields=["name", "slug"])

    accessories = Category.objects.filter(slug="accessories").first()
    if accessories:
        accessories.name = "Аксессуары для телефонов"
        accessories.slug = "phone-accessories"
        if electronics:
            accessories.parent = electronics
        accessories.save(update_fields=["name", "slug", "parent"])

    for name, slug in CATALOG_CATEGORIES:
        Category.objects.get_or_create(slug=slug, defaults={"name": name})

    Product.objects.filter(name__icontains="Xiaomi").update(brand="Xiaomi")
    Product.objects.filter(name__icontains="Wireless Headphones").update(brand="Elite Sound")
    Product.objects.filter(name__icontains="Smart Desk Lamp").update(brand="Elite Home")
    Product.objects.filter(name__icontains="USB-C").update(brand="Elite Tech")
    Product.objects.filter(name__icontains="Kitchen Scale").update(brand="Elite Home")


class Migration(migrations.Migration):
    dependencies = [("shop", "0004_order_cancellation")]

    operations = [
        migrations.AddField(
            model_name="product",
            name="brand",
            field=models.CharField(blank=True, db_index=True, max_length=100, verbose_name="Бренд"),
        ),
        migrations.RunPython(seed_catalog, migrations.RunPython.noop),
    ]
