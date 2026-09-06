from django.contrib import admin
from django.core.exceptions import ValidationError
from django.db import transaction

from .models import (
    Address,
    Cart,
    CartItem,
    Category,
    Order,
    OrderItem,
    Product,
    ProductImage,
    Review,
    WholesalePrice,
)
from .order_lifecycle import transition_order


class CartItemInline(admin.TabularInline):
    model = CartItem
    extra = 0


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ("product", "product_name", "price", "quantity")
    can_delete = False


class ProductImageInline(admin.TabularInline):
    model = ProductImage
    extra = 1


class WholesalePriceInline(admin.TabularInline):
    model = WholesalePrice
    extra = 1


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "parent", "created_at")
    list_filter = ("parent",)
    search_fields = ("name", "slug")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("name", "brand", "category", "price", "stock", "is_active", "updated_at")
    list_filter = ("brand", "category", "is_active")
    search_fields = ("name", "brand", "description", "additional_description")
    prepopulated_fields = {"slug": ("name",)}
    inlines = (ProductImageInline, WholesalePriceInline)
    readonly_fields = ("stock",)

    @transaction.atomic
    def save_model(self, request, obj, form, change):
        obj.stock = Product.objects.select_for_update().get(pk=obj.pk).stock if change else 0
        super().save_model(request, obj, form, change)


@admin.register(Cart)
class CartAdmin(admin.ModelAdmin):
    list_display = ("user", "total_quantity", "total_price", "updated_at")
    search_fields = ("user__email", "user__phone_number")
    inlines = (CartItemInline,)


@admin.register(Address)
class AddressAdmin(admin.ModelAdmin):
    list_display = ("user", "country", "city", "street", "building", "is_saved", "is_default")
    list_filter = ("country", "city", "is_saved", "is_default")
    search_fields = ("user__email", "user__phone_number", "city", "street")


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = (
        "order_number",
        "user",
        "total_price",
        "status",
        "payment_method",
        "payment_status",
        "created_at",
        "cancelled_at",
    )
    list_filter = ("status", "payment_method", "payment_status", "created_at", "cancelled_at")
    search_fields = ("order_number", "payment_id", "user__email", "user__phone_number")
    readonly_fields = (
        "user",
        "shipping_address",
        "order_number",
        "total_price",
        "status",
        "payment_method",
        "payment_status",
        "payment_id",
        "payment_link",
        "qr_code",
        "payment_attempts",
        "payment_last_error",
        "payment_checked_at",
        "payment_reconciliation_failures",
        "payment_expires_at",
        "paid_at",
        "stock_released",
        "created_at",
        "updated_at",
        "cancelled_at",
    )
    inlines = (OrderItemInline,)
    actions = ("mark_as_shipped", "mark_as_delivered", "cancel_pending_orders")

    def has_add_permission(self, request):
        return False

    @admin.action(description="Отметить оплаченные заказы как отправленные")
    def mark_as_shipped(self, request, queryset):
        updated = self._transition_orders(queryset, "ship")
        self.message_user(request, f"Отправлено заказов: {updated}")

    @admin.action(description="Отметить отправленные заказы как доставленные")
    def mark_as_delivered(self, request, queryset):
        updated = self._transition_orders(queryset, "deliver")
        self.message_user(request, f"Доставлено заказов: {updated}")

    @admin.action(description="Отменить ожидающие заказы и вернуть резерв")
    def cancel_pending_orders(self, request, queryset):
        cancelled = self._transition_orders(queryset, "cancel", f"Отменено администратором {request.user}.")
        self.message_user(request, f"Отменено заказов: {cancelled}")

    def _transition_orders(self, queryset, action, reason=""):
        updated = 0
        for order_id in queryset.values_list("pk", flat=True):
            try:
                transition_order(order_id, action, reason)
                updated += 1
            except ValidationError:
                continue
        return updated


@admin.register(OrderItem)
class OrderItemAdmin(admin.ModelAdmin):
    list_display = ("order", "product_name", "price", "quantity", "subtotal")
    search_fields = ("order__order_number", "product_name")
    readonly_fields = ("order", "product", "product_name", "price", "quantity")

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ("product", "user", "rating", "is_approved", "created_at")
    list_filter = ("rating", "is_approved", "created_at")
    search_fields = ("product__name", "user__email", "user__phone_number", "text")
    readonly_fields = ("product", "user", "order_item", "rating", "text", "created_at", "updated_at")
    actions = ("approve_reviews", "hide_reviews")

    @admin.action(description="Опубликовать выбранные отзывы")
    def approve_reviews(self, request, queryset):
        queryset.update(is_approved=True)

    @admin.action(description="Скрыть выбранные отзывы")
    def hide_reviews(self, request, queryset):
        queryset.update(is_approved=False)
