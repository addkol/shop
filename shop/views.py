from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from payment.services import PaymentGatewayError, create_payment

from .cart import add_product, clear_cart, get_cart_rows, remove_product, set_product_quantity
from .forms import CancelOrderForm, CheckoutForm
from .models import Category, Order, OrderItem, Product


def product_list(request, slug=None):
    categories = Category.objects.filter(parent__isnull=True)
    products = (
        Product.objects.filter(is_active=True, stock__gt=0)
        .select_related("category")
        .prefetch_related("images", "wholesale_prices")
    )
    category = None
    if slug:
        category = get_object_or_404(Category, slug=slug)
        child_ids = category.children.values_list("id", flat=True)
        products = products.filter(category_id__in=[category.id, *child_ids])

    paginator = Paginator(products, 12)
    page_obj = paginator.get_page(request.GET.get("page"))
    return render(
        request,
        "index.html",
        {
            "page_obj": page_obj,
            "categories": categories,
            "current_category": category,
        },
    )


def product_detail(request, slug):
    product = get_object_or_404(
        Product.objects.select_related("category").prefetch_related("images", "wholesale_prices"),
        slug=slug,
        is_active=True,
    )
    wholesale_rules = list(product.wholesale_prices.all())
    pricing_tiers = [
        {"min_quantity": rule.min_quantity, "price": str(rule.price)}
        for rule in wholesale_rules
    ]
    best_price = min([product.price, *[rule.price for rule in wholesale_rules]])
    initial_unit_price = product.get_price_for_quantity(1)
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
        },
    )


def cart_view(request):
    rows, total = get_cart_rows(request)
    return render(request, "cart.html", {"cart_rows": rows, "cart_total": total})


@require_POST
def add_to_cart(request, product_id):
    product = get_object_or_404(Product, pk=product_id, is_active=True)
    quantity = request.POST.get("quantity", 1)
    if not product.available:
        messages.error(request, "Товара нет в наличии.")
        return redirect(product.get_absolute_url())
    add_product(request, product, quantity)
    messages.success(request, f"{product.name} добавлен в корзину.")
    return redirect(request.POST.get("next") or "shop:cart")


@require_POST
def update_cart(request, product_id):
    product = get_object_or_404(Product, pk=product_id, is_active=True)
    quantity = request.POST.get("quantity", 1)
    set_product_quantity(request, product, quantity)
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
                order = Order.objects.create(
                    user=request.user,
                    shipping_address=address,
                    total_price=total,
                    payment_method=form.cleaned_data["payment_method"],
                )

                for row in rows:
                    product = Product.objects.select_for_update().get(pk=row["product"].pk)
                    if product.stock < row["quantity"]:
                        raise ValueError(f"Недостаточно товара на складе: {product.name}.")
                    product.stock -= row["quantity"]
                    product.save(update_fields=["stock", "updated_at"])
                    unit_price = product.get_price_for_quantity(row["quantity"])
                    OrderItem.objects.create(
                        order=order,
                        product=product,
                        product_name=product.name,
                        price=unit_price,
                        quantity=row["quantity"],
                    )

                clear_cart(request)
        except ValueError as exc:
            messages.error(request, str(exc))
            return redirect("shop:cart")

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

        for item in order.items.all():
            if item.product:
                item.product.stock += item.quantity
                item.product.save(update_fields=["stock", "updated_at"])

        order.status = Order.Status.CANCELLED
        order.payment_status = Order.PaymentStatus.FAILED
        order.cancellation_reason = form.cleaned_data["reason"]
        order.cancelled_at = timezone.now()
        order.save(update_fields=["status", "payment_status", "cancellation_reason", "cancelled_at", "updated_at"])

    messages.success(request, "Заказ отменен. Причина сохранена.")
    return redirect("accounts:profile")
