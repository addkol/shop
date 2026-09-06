from decimal import Decimal
from django import forms

from django.contrib import messages
from django.contrib.admin.models import CHANGE, LogEntry
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db import IntegrityError, transaction
from django.db.models import Count, Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from accounts.models import User
from shop.models import Category, Order, Product, ProductImage, Review
from shop.order_lifecycle import transition_order
from shop.services import adjust_product_stock

from .forms import (
    CategoryForm, GalleryFormSetFactory, OrderActionForm, OrderFilterForm,
    ProductForm, ReviewActionForm, StockForm, WholesaleFormSetFactory,
)
from .security import staff_permission


def audit(request, instance, message):
    LogEntry.objects.create(
        user_id=request.user.pk, content_type=ContentType.objects.get_for_model(instance),
        object_id=str(instance.pk), object_repr=str(instance)[:200],
        action_flag=CHANGE, change_message=message,
    )


def page_context(request, queryset, title, **extra):
    query = request.GET.copy()
    query.pop("page", None)
    return {"page": Paginator(queryset, 25).get_page(request.GET.get("page")),
            "querystring": query.urlencode(), "title": title, **extra}


@staff_permission()
def home(request):
    context = {"title": "Обзор магазина"}
    if request.user.has_perm("shop.view_order"):
        today = timezone.localdate()
        orders = Order.objects.select_related("user")
        counts = {item["status"]: item["total"] for item in orders.values("status").annotate(total=Count("pk"))}
        context.update(
            metrics=[
                ("Заказы сегодня", orders.filter(created_at__date=today).count()),
                ("Новые / ожидают оплаты", counts.get("pending", 0)),
                ("Оплачены / к обработке", counts.get("paid", 0)),
                ("Отправлены", counts.get("shipped", 0)),
                ("Доставлены / завершены", counts.get("delivered", 0)),
                ("Отменены", counts.get("cancelled", 0)),
                ("Требуется возврат", orders.filter(payment_status="refund_required").count()),
                ("Продажи сегодня, сом", orders.filter(payment_status="success", paid_at__date=today)
                 .aggregate(total=Sum("total_price"))["total"] or Decimal("0")),
            ],
            latest_orders=orders[:8],
            attention_orders=orders.filter(Q(payment_status="refund_required") | Q(payment_reconciliation_failures__gt=0) | ~Q(payment_last_error=""))[:8],
        )
    if request.user.has_perm("accounts.view_user"):
        context["customer_count"] = User.objects.filter(is_client=True).count()
    if request.user.has_perm("shop.view_product"):
        context["low_stock_count"] = Product.objects.filter(is_active=True, stock__lte=5).count()
        context["low_stock"] = Product.objects.filter(is_active=True, stock__lte=5).order_by("stock", "pk")[:10]
    return render(request, "dashboard/home.html", context)


def filtered_orders(request):
    queryset = Order.objects.select_related("user", "shipping_address")
    form = OrderFilterForm(request.GET)
    if not form.is_valid():
        return queryset.none(), form
    data = form.cleaned_data
    if data["q"]:
        queryset = queryset.filter(Q(order_number__icontains=data["q"]) | Q(user__phone_number__icontains=data["q"]) |
                                   Q(user__first_name__icontains=data["q"]) | Q(payment_id__icontains=data["q"]))
    for field, lookup in [("status", "status"), ("payment", "payment_status"),
                          ("date_from", "created_at__date__gte"), ("date_to", "created_at__date__lte")]:
        if data[field]:
            queryset = queryset.filter(**{lookup: data[field]})
    return queryset, form


@staff_permission("shop.view_order")
def orders(request):
    queryset, form = filtered_orders(request)
    return render(request, "dashboard/orders.html", page_context(request, queryset, "Заказы", filter_form=form))


@staff_permission("shop.view_order")
def order_detail(request, pk):
    order = get_object_or_404(Order.objects.select_related("user", "shipping_address").prefetch_related("items"), pk=pk)
    events = order.payment_events.all()[:100] if request.user.has_perm("payment.view_paymentevent") else []
    return render(request, "dashboard/order_detail.html", {
        "title": str(order), "order": order, "events": events,
        "show_payments": request.user.has_perm("payment.view_paymentevent"),
    })


@staff_permission("shop.view_order")
@require_http_methods(["GET", "POST"])
def order_action(request, pk):
    action = request.POST.get("action") if request.method == "POST" else request.GET.get("action")
    permission = {"ship": "shop.fulfill_order", "deliver": "shop.fulfill_order", "cancel": "shop.cancel_order"}.get(action)
    if not permission or not request.user.has_perm(permission):
        raise PermissionDenied
    order = get_object_or_404(Order, pk=pk)
    form = OrderActionForm(request.POST if request.method == "POST" else None, initial={"action": action})
    form.fields["action"].widget = forms.HiddenInput()
    if request.method == "POST" and form.is_valid():
        try:
            with transaction.atomic():
                transition_order(order.pk, form.cleaned_data["action"], form.cleaned_data["reason"])
                audit(request, order, "Действие с заказом: " + form.cleaned_data["action"] + ". " + form.cleaned_data["reason"])
            messages.success(request, "Состояние заказа обновлено.")
            return redirect("dashboard:order-detail", pk=pk)
        except ValidationError as exc:
            form.add_error(None, exc)
    return render(request, "dashboard/form.html", {"title": "Подтвердите действие: " + str(order), "form": form, "confirmation": True})


@staff_permission("shop.view_product")
def products(request):
    queryset = Product.objects.select_related("category")
    query = request.GET.get("q", "")[:150]
    if query:
        queryset = queryset.filter(Q(name__icontains=query) | Q(brand__icontains=query))
    return render(request, "dashboard/products.html", page_context(request, queryset, "Товары", search=True))


@staff_permission("shop.view_product")
@require_http_methods(["GET", "POST"])
def product_edit(request, pk=None):
    permission = "shop.change_product" if pk else "shop.add_product"
    if not request.user.has_perm(permission):
        raise PermissionDenied
    instance = get_object_or_404(Product, pk=pk) if pk else Product(stock=0)
    data = request.POST if request.method == "POST" else None
    form = ProductForm(data, request.FILES or None, instance=instance)
    can_gallery = request.user.has_perms(["shop.add_productimage", "shop.change_productimage", "shop.delete_productimage"])
    can_wholesale = request.user.has_perms(["shop.add_wholesaleprice", "shop.change_wholesaleprice", "shop.delete_wholesaleprice"])
    gallery = GalleryFormSetFactory(data if can_gallery else None, request.FILES or None, instance=instance, prefix="gallery") if can_gallery else None
    wholesale = WholesaleFormSetFactory(data if can_wholesale else None, instance=instance, prefix="wholesale") if can_wholesale else None
    if request.method == "POST":
        valid = form.is_valid()
        for formset in [gallery, wholesale]:
            if formset is not None:
                valid = formset.is_valid() and valid
        if valid:
            try:
                with transaction.atomic():
                    if pk:
                        locked = Product.objects.select_for_update().get(pk=pk)
                        form.instance.stock = locked.stock
                    product = form.save()
                    if gallery is not None:
                        ProductImage.objects.filter(product=product, is_main=True).update(is_main=False)
                        gallery.instance = product
                        gallery.save()
                        for child in gallery.forms:
                            if child.cleaned_data and not child.cleaned_data.get("DELETE") and child.cleaned_data.get("is_main"):
                                ProductImage.objects.filter(pk=child.instance.pk).update(is_main=True)
                    if wholesale is not None:
                        wholesale.instance = product
                        wholesale.save()
                    audit(request, product, "Сохранена карточка товара.")
                messages.success(request, "Товар сохранён. Остаток корректируется отдельно в разделе «Склад».")
                return redirect("dashboard:product-edit", pk=product.pk)
            except IntegrityError:
                form.add_error(None, "Данные изменились или содержат дубликаты. Проверьте значения и повторите.")
    return render(request, "dashboard/form.html", {"title": "Редактирование товара" if pk else "Новый товар",
                                                   "form": form, "gallery": gallery, "wholesale": wholesale})


@staff_permission("shop.view_category")
def categories(request):
    return render(request, "dashboard/categories.html", page_context(request, Category.objects.select_related("parent"), "Категории"))


@staff_permission("shop.view_category")
@require_http_methods(["GET", "POST"])
def category_edit(request, pk=None):
    if not request.user.has_perm("shop.change_category" if pk else "shop.add_category"):
        raise PermissionDenied
    instance = get_object_or_404(Category, pk=pk) if pk else Category()
    form = CategoryForm(request.POST if request.method == "POST" else None, instance=instance)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            instance = form.save()
            audit(request, instance, "Сохранена категория.")
        messages.success(request, "Категория сохранена.")
        return redirect("dashboard:categories")
    return render(request, "dashboard/form.html", {"title": "Категория", "form": form})


@staff_permission("accounts.view_user")
def customers(request):
    queryset = User.objects.filter(is_client=True).select_related("client_profile").annotate(order_count=Count("orders")).order_by("-date_joined", "-pk")
    query = request.GET.get("q", "")[:150]
    if query:
        queryset = queryset.filter(Q(phone_number__icontains=query) | Q(first_name__icontains=query) | Q(last_name__icontains=query))
    return render(request, "dashboard/customers.html", page_context(request, queryset, "Клиенты", search=True))


@staff_permission("accounts.view_user", "shop.view_address", "shop.view_order")
def customer_detail(request, pk):
    customer = get_object_or_404(User.objects.select_related("client_profile"), pk=pk, is_client=True)
    return render(request, "dashboard/customer_detail.html", {
        "title": customer.get_full_name() or customer.phone_number,
        "customer": customer, "addresses": customer.addresses.all(),
        "latest_orders": customer.orders.all()[:20], "order_count": customer.orders.count(),
    })


@staff_permission("shop.view_order", "payment.view_paymentevent")
def payments(request):
    queryset, form = filtered_orders(request)
    return render(request, "dashboard/payments.html", page_context(request, queryset, "Платежи", filter_form=form))


@staff_permission("shop.view_product")
def stock(request):
    queryset = Product.objects.annotate(reserved=Sum(
        "orderitem__quantity", filter=Q(orderitem__order__stock_released=False,
                                       orderitem__order__status__in=["pending", "paid"]), default=0,
    )).order_by("stock", "pk")
    query = request.GET.get("q", "")[:150]
    if query:
        queryset = queryset.filter(name__icontains=query)
    return render(request, "dashboard/stock.html", page_context(request, queryset, "Склад", search=True))


@staff_permission("shop.view_product", "shop.adjust_stock")
@require_http_methods(["GET", "POST"])
def stock_edit(request, pk):
    product = get_object_or_404(Product, pk=pk)
    form = StockForm(request.POST if request.method == "POST" else None,
                     initial={"quantity": product.stock, "expected_stock": product.stock})
    if request.method == "POST" and form.is_valid():
        try:
            with transaction.atomic():
                adjust_product_stock(pk, form.cleaned_data["quantity"], form.cleaned_data["expected_stock"])
                audit(request, product, "Остаток: " + str(form.cleaned_data["expected_stock"]) + " → " +
                      str(form.cleaned_data["quantity"]) + ". " + form.cleaned_data["reason"])
            messages.success(request, "Остаток изменён.")
            return redirect("dashboard:stock")
        except ValidationError as exc:
            form.add_error(None, exc)
    return render(request, "dashboard/form.html", {"title": "Корректировка: " + product.name, "form": form, "confirmation": True})


@staff_permission("shop.view_review")
def reviews(request):
    return render(request, "dashboard/reviews.html", page_context(
        request, Review.objects.select_related("product", "user"), "Отзывы"))


@staff_permission("shop.view_review")
@require_http_methods(["GET", "POST"])
def review_detail(request, pk):
    review = get_object_or_404(Review.objects.select_related("product", "user"), pk=pk)
    if request.method == "POST":
        if not request.user.has_perm("shop.change_review"):
            raise PermissionDenied
        form = ReviewActionForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                Review.objects.filter(pk=pk).update(is_approved=form.cleaned_data["action"] == "approve", updated_at=timezone.now())
                audit(request, review, "Модерация: " + form.cleaned_data["action"])
            messages.success(request, "Публикация отзыва обновлена.")
            return redirect("dashboard:review-detail", pk=pk)
    else:
        form = ReviewActionForm()
    return render(request, "dashboard/review_detail.html", {"title": "Отзыв", "review": review, "form": form})
