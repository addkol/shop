from django.urls import path

from . import views


app_name = "payment"

urlpatterns = [
    path("webhook/finik/", views.finik_webhook, name="finik-webhook"),
    path("pay/test/<str:payment_id>/", views.stub_payment, name="stub-payment"),
]
