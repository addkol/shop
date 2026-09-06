from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Avg, Count, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from payment.services import PaymentGatewayError, create_payment

from .cart import add_product, clear_cart, get_cart_rows, remove_product, set_product_quantity
from .forms import CancelOrderForm, CheckoutForm, ReviewForm
from .models import Category, Order, OrderItem, Product, Review
from .services import release_order_stock


def _parse_quantity(request, minimum=1, add_message=True):
    raw_quantity = request.POST.get("quantity", minimum)
    try:
        quantity = int(raw_quantity)
    except (TypeError, ValueError):
        if add_message:
            messages.error(request, "Количество должно быть целым числом.")
        return None
    if quantity < minimum:
        if add_message:
            messages.error(request, f"Минимальное количество: {minimum}.")
        return None
    return quantity


def product_list(request, slug=None):
    categories = (
        Category.objects.filter(parent__isnull=True)
        .annotate(product_count=Count("products", filter=Q(products__is_active=True, products__stock__gt=0)))
        .order_by("created_at", "id")
    )
    base_products = (
        Product.objects.filter(is_active=True, stock__gt=0)
        .select_related("category")
        .prefetch_related("images", "wholesale_prices")
    )
    products = base_products
    category = None
    if slug:
        category = get_object_or_404(Category, slug=slug)
        child_ids = category.children.values_list("id", flat=True)
        products = products.filter(category_id__in=[category.id, *child_ids])

    query = request.GET.get("q", "").strip()
    selected_brand = request.GET.get("brand", "").strip()
    min_price = request.GET.get("min_price", "").strip()
    max_price = request.GET.get("max_price", "").strip()
    sort = request.GET.get("sort", "newest")

    if query:
        products = products.filter(
            Q(name__icontains=query)
            | Q(description__icontains=query)
            | Q(additional_description__icontains=query)
            | Q(brand__icontains=query)
        )
    if selected_brand:
        products = products.filter(brand__iexact=selected_brand)
    try:
        if min_price:
            products = products.filter(price__gte=Decimal(min_price))
        if max_price:
            products = products.filter(price__lte=Decimal(max_price))
    except InvalidOperation:
        messages.warning(request, "Укажите цену числом.")

    ordering = {
        "price_asc": ("price", "name"),
        "price_desc": ("-price", "name"),
        "name": ("name",),
        "newest": ("-created_at",),
    }.get(sort, ("-created_at",))
    products = products.order_by(*ordering)

    paginator = Paginator(products, 12)
    page_obj = paginator.get_page(request.GET.get("page"))
    brands = list(
        base_products.exclude(brand="")
        .order_by("brand")
        .values_list("brand", flat=True)
        .distinct()
    )
    featured_products = list(base_products.order_by("-stock", "-created_at")[:4])
    new_products = list(base_products.order_by("-created_at")[:4])
    hero_product = next((product for product in featured_products if product.main_image_url), None)
    active_filters = any([query, selected_brand, min_price, max_price, sort != "newest"])
    return render(
        request,
        "index.html",
        {
            "page_obj": page_obj,
            "categories": categories,
            "current_category": category,
            "brands": brands,
            "selected_brand": selected_brand,
            "query": query,
            "min_price": min_price,
            "max_price": max_price,
            "sort": sort,
            "featured_products": featured_products,
            "new_products": new_products,
            "hero_product": hero_product,
            "show_home_sections": not category and not active_filters and page_obj.number == 1,
        },
    )


def product_detail(request, slug):
    product = get_object_or_404(
        Product.objects.select_related("category").prefetch_related("images", "wholesale_prices"),
        slug=slug,
        is_active=True,
    )
    wholesale_rules = product.get_pricing_tiers()
    pricing_tiers = [
        {"min_quantity": rule["min_quantity"], "price": str(rule["price"])}
        for rule in wholesale_rules
    ]
    best_price = min([product.price, *[rule["price"] for rule in wholesale_rules]])
    initial_unit_price = product.get_price_for_quantity(1)
    first_wholesale_quantity = wholesale_rules[0]["min_quantity"] if wholesale_rules else None
    base_tier_label = (
        f"1–{first_wholesale_quantity - 1} шт."
        if first_wholesale_quantity and first_wholesale_quantity > 1
        else "от 1 шт."
    )
    related_products = (
        Product.objects.filter(category=product.category, is_active=True, stock__gt=0)
        .exclude(pk=product.pk)
        .prefetch_related("images", "wholesale_prices")[:4]
    )
    reviews = product.reviews.filter(is_approved=True).select_related("user")
    review_summary = reviews.aggregate(average=Avg("rating"))
    review_count = reviews.count()
    average_rating = review_summary["average"] or 0
    eligible_review_item = None
    if request.user.is_authenticated:
        eligible_review_item = (
            OrderItem.objects.filter(
                order__user=request.user,
                order__status=Order.Status.DELIVERED,
                product=product,
                review__isnull=True,
            )
            .select_related("order")
            .first()
        )
    return render(
        request,
        "product_detail.html",
        {
            "product": product,
            "media_items": product.media_items,
            "pricing_tiers": pricing_tiers,
            "best_price": best_price,
            "base_price": str(product.price),
            "initial_unit_price": initial_unit_price,
            "first_wholesale_quantity": first_wholesale_quantity,
            "base_tier_label": base_tier_label,
            "related_products": related_products,
            "reviews": reviews,
            "review_count": review_count,
            "average_rating": average_rating,
            "eligible_review_item": eligible_review_item,
            "review_form": ReviewForm() if eligible_review_item else None,
        },
    )


def brand_list(request):
    brands = (
        Product.objects.filter(is_active=True)
        .exclude(brand="")
        .values_list("brand", flat=True)
        .order_by("brand")
        .distinct()
    )
    return render(request, "brands.html", {"brands": brands})


def cart_view(request):
    rows, total = get_cart_rows(request)
    return render(request, "cart.html", {"cart_rows": rows, "cart_total": total})


@require_POST
def add_to_cart(request, product_id):
    product = get_object_or_404(Product, pk=product_id, is_active=True)
    quantity = _parse_quantity(request)
    if quantity is None:
        return redirect(product.get_absolute_url())
    if not product.available:
        messages.error(request, "Товара нет в наличии.")
        return redirect(product.get_absolute_url())
    add_product(request, product, quantity)
    messages.success(request, f"{product.name} добавлен в корзину.")
    next_url = request.POST.get("next", "")
    if next_url and url_has_allowed_host_and_scheme(
        next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return redirect(next_url)
    return redirect("shop:cart")


@require_POST
def update_cart(request, product_id):
    product = get_object_or_404(Product, pk=product_id, is_active=True)
    is_ajax = request.headers.get("X-Requested-With") == "XMLHttpRequest"
    quantity = _parse_quantity(request, minimum=0, add_message=not is_ajax)
    if quantity is None:
        if is_ajax:
            return JsonResponse({"detail": "Укажите корректное количество."}, status=400)
        return redirect("shop:cart")
    set_product_quantity(request, product, quantity)
    if is_ajax:
        rows, total = get_cart_rows(request)
        row = next((item for item in rows if item["product"].pk == product.pk), None)
        return JsonResponse(
            {
                "item": (
                    {
                        "quantity": row["quantity"],
                        "unit_price": str(row["unit_price"]),
                        "subtotal": str(row["subtotal"]),
                        "retail_subtotal": str(row["retail_subtotal"]),
                        "is_wholesale": row["is_wholesale"],
                        "items_until_wholesale": row["items_until_wholesale"],
                    }
                    if row
                    else None
                ),
                "cart_quantity": sum(item["quantity"] for item in rows),
                "cart_total": str(total),
            }
        )
    messages.success(request, "Корзина обновлена.")
    return redirect("shop:cart")


@require_POST
def remove_from_cart(request, product_id):
    product = get_object_or_404(Product, pk=product_id)
    remove_product(request, product)
    messages.success(request, "Товар удален из корзины.")
    return redirect("shop:cart")


@login_required
def checkout(request):
    rows, total = get_cart_rows(request)
    if not rows:
        messages.info(request, "Корзина пуста.")
        return redirect("shop:cart")

    form = CheckoutForm(request.POST or None, user=request.user)
    if request.method == "POST" and form.is_valid():
        try:
            with transaction.atomic():
                address = form.get_or_create_address()
                locked_products = {
                    product.pk: product
                    for product in Product.objects.select_for_update()
                    .filter(pk__in=[row["product"].pk for row in rows], is_active=True)
                    .prefetch_related("wholesale_prices")
                    .order_by("pk")
                }
                line_items = []
                order_total = Decimal("0.00")
                for row in rows:
                    product = locked_products.get(row["product"].pk)
                    if product is None or product.stock < row["quantity"]:
                        product_name = row["product"].name
                        raise ValueError(f"Недостаточно товара на складе: {product_name}.")
                    unit_price = product.get_price_for_quantity(row["quantity"])
                    order_total += unit_price * row["quantity"]
                    line_items.append((product, row["quantity"], unit_price))

                order = Order.objects.create(
                    user=request.user,
                    shipping_address=address,
                    total_price=order_total,
                    payment_method=form.cleaned_data["payment_method"],
                    payment_expires_at=timezone.now()
                    + timezone.timedelta(minutes=settings.ORDER_PAYMENT_TTL_MINUTES),
                )

                for product, quantity, unit_price in line_items:
                    product.stock -= quantity
                    product.save(update_fields=["stock", "updated_at"])
                    OrderItem.objects.create(
                        order=order,
                        product=product,
                        product_name=product.name,
                        price=unit_price,
                        quantity=quantity,
                    )

                clear_cart(request)
        except ValueError as exc:
            messages.error(request, str(exc))
            return redirect("shop:cart")

        if not settings.PAYMENT_ENABLED:
            messages.info(request, "Заказ создан. Онлайн-оплата временно недоступна. Заказ не оплачен.")
            return redirect(order.get_absolute_url())
        try:
            create_payment(order, request=request)
        except PaymentGatewayError as exc:
            messages.warning(request, str(exc))
        else:
            messages.success(request, "Заказ создан. Завершите оплату по QR-коду.")
        return redirect(order.get_absolute_url())

    return render(request, "checkout.html", {"form": form, "cart_rows": rows, "cart_total": total})


@login_required
def order_success(request, order_number):
    order = get_object_or_404(
        Order.objects.prefetch_related("items").select_related("shipping_address"),
        order_number=order_number,
        user=request.user,
    )
    return render(request, "order_success.html", {"order": order, "cancel_form": CancelOrderForm()})


@login_required
@require_POST
def retry_payment(request, order_number):
    order = get_object_or_404(Order, order_number=order_number, user=request.user)
    if not settings.PAYMENT_ENABLED:
        messages.info(request, "Онлайн-оплата временно недоступна.")
        return redirect(order.get_absolute_url())
    if not order.can_be_paid:
        messages.error(request, "Срок оплаты истёк или заказ уже обработан.")
        return redirect(order.get_absolute_url())
    try:
        create_payment(order, request=request)
    except PaymentGatewayError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, "Новая ссылка на оплату подготовлена.")
    return redirect(order.get_absolute_url())


@login_required
@require_POST
def cancel_order(request, order_number):
    form = CancelOrderForm(request.POST)

    if not form.is_valid():
        messages.error(request, "Укажите причину отмены заказа.")
        return redirect("accounts:profile")

    with transaction.atomic():
        order = get_object_or_404(
            Order.objects.select_for_update().prefetch_related("items__product"),
            order_number=order_number,
            user=request.user,
        )

        if not order.can_be_cancelled:
            messages.error(request, "Этот заказ уже нельзя отменить.")
            return redirect(order.get_absolute_url())

        release_order_stock(order, form.cleaned_data["reason"])

    messages.success(request, "Заказ отменен. Причина сохранена.")
    return redirect("accounts:profile")


@login_required
@require_POST
def add_review(request, slug):
    product = get_object_or_404(Product, slug=slug, is_active=True)
    order_item = (
        OrderItem.objects.filter(
            order__user=request.user,
            order__status=Order.Status.DELIVERED,
            product=product,
            review__isnull=True,
        )
        .select_related("order")
        .first()
    )
    if order_item is None:
        messages.error(request, "Отзыв можно оставить только после получения товара.")
        return redirect(product.get_absolute_url())

    form = ReviewForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Проверьте оценку и текст отзыва.")
        return redirect(f"{product.get_absolute_url()}#reviews")

    review = form.save(commit=False)
    review.product = product
    review.user = request.user
    review.order_item = order_item
    review.save()
    messages.success(request, "Спасибо! Отзыв отправлен на проверку.")
    return redirect(f"{product.get_absolute_url()}#reviews")
