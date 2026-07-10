from django.urls import path

from . import views


app_name = "shop"

urlpatterns = [
    path("", views.product_list, name="index"),
    path("category/<slug:slug>/", views.product_list, name="category"),
    path("products/<slug:slug>/", views.product_detail, name="product-detail"),
    path("cart/", views.cart_view, name="cart"),
    path("cart/add/<int:product_id>/", views.add_to_cart, name="add-to-cart"),
    path("cart/update/<int:product_id>/", views.update_cart, name="update-cart"),
    path("cart/remove/<int:product_id>/", views.remove_from_cart, name="remove-from-cart"),
    path("checkout/", views.checkout, name="checkout"),
    path("order/<str:order_number>/", views.order_success, name="order-success"),
    path("order/<str:order_number>/cancel/", views.cancel_order, name="cancel-order"),
]
