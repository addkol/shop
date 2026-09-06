from django.urls import path

from . import views

app_name = "dashboard"
urlpatterns = [
    path("", views.home, name="home"),
    path("orders/", views.orders, name="orders"),
    path("orders/<int:pk>/", views.order_detail, name="order-detail"),
    path("orders/<int:pk>/action/", views.order_action, name="order-action"),
    path("products/", views.products, name="products"),
    path("products/new/", views.product_edit, name="product-new"),
    path("products/<int:pk>/edit/", views.product_edit, name="product-edit"),
    path("categories/", views.categories, name="categories"),
    path("categories/new/", views.category_edit, name="category-new"),
    path("categories/<int:pk>/edit/", views.category_edit, name="category-edit"),
    path("customers/", views.customers, name="customers"),
    path("customers/<int:pk>/", views.customer_detail, name="customer-detail"),
    path("payments/", views.payments, name="payments"),
    path("stock/", views.stock, name="stock"),
    path("stock/<int:pk>/", views.stock_edit, name="stock-edit"),
    path("reviews/", views.reviews, name="reviews"),
    path("reviews/<int:pk>/", views.review_detail, name="review-detail"),
]
