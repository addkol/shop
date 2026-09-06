from .cart import get_cart_rows
from .models import Category


def cart_summary(request):
    rows, total = get_cart_rows(request)
    return {
        "cart_quantity": sum(row["quantity"] for row in rows),
        "cart_preview_rows": rows[:4],
        "cart_preview_total": total,
        "navigation_categories": Category.objects.filter(parent__isnull=True).order_by("created_at", "id")[:12],
    }
