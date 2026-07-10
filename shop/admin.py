from django.contrib import admin

from .models import Address, Cart, CartItem, Category, Order, OrderItem, Product, ProductImage, WholesalePrice


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
    list_display = ("name", "category", "price", "stock", "is_active", "updated_at")
    list_filter = ("category", "is_active")
    search_fields = ("name", "description", "additional_description")
    prepopulated_fields = {"slug": ("name",)}
    inlines = (ProductImageInline, WholesalePriceInline)


@admin.register(Cart)
class CartAdmin(admin.ModelAdmin):
    list_display = ("user", "total_quantity", "total_price", "updated_at")
    search_fields = ("user__email", "user__phone_number")
    inlines = (CartItemInline,)


@admin.register(Address)
class AddressAdmin(admin.ModelAdmin):
    list_display = ("user", "country", "city", "street", "building", "is_default")
    list_filter = ("country", "city", "is_default")
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
    readonly_fields = ("order_number", "payment_id", "payment_link", "qr_code", "created_at", "updated_at", "cancelled_at")
    inlines = (OrderItemInline,)


@admin.register(OrderItem)
class OrderItemAdmin(admin.ModelAdmin):
    list_display = ("order", "product_name", "price", "quantity", "subtotal")
    search_fields = ("order__order_number", "product_name")
