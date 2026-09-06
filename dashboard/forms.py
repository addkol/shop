from decimal import Decimal

from django import forms
from django.forms import BaseInlineFormSet, inlineformset_factory

from shop.models import Category, Product, ProductImage, WholesalePrice, Order


class ProductForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = ["name", "slug", "description", "additional_description", "category",
                  "brand", "price", "image", "video", "is_active"]
        widgets = {"description": forms.Textarea(attrs={"rows": 5}),
                   "additional_description": forms.Textarea(attrs={"rows": 3})}

    def clean_price(self):
        price = self.cleaned_data["price"]
        if price < Decimal("0.01"):
            raise forms.ValidationError("Цена должна быть больше нуля.")
        return price


class GalleryFormSet(BaseInlineFormSet):
    def clean(self):
        super().clean()
        if any(self.errors):
            return
        main_count = sum(bool(form.cleaned_data.get("is_main")) for form in self.forms
                         if form.cleaned_data and not form.cleaned_data.get("DELETE"))
        if main_count > 1:
            raise forms.ValidationError("Выберите только одно основное фото.")


GalleryFormSetFactory = inlineformset_factory(
    Product, ProductImage, formset=GalleryFormSet,
    fields=["image", "alt_text", "is_main", "ordering"], extra=2,
    can_delete=True, max_num=30, validate_max=True,
)
WholesaleFormSetFactory = inlineformset_factory(
    Product, WholesalePrice, fields=["min_quantity", "price"],
    extra=2, can_delete=True, max_num=30, validate_max=True,
)


class CategoryForm(forms.ModelForm):
    class Meta:
        model = Category
        fields = ["name", "slug", "parent"]

    def clean_parent(self):
        parent = self.cleaned_data["parent"]
        visited = set()
        ancestor = parent
        while ancestor:
            if ancestor.pk == self.instance.pk or ancestor.pk in visited:
                raise forms.ValidationError("Категории не могут образовывать цикл.")
            visited.add(ancestor.pk)
            ancestor = ancestor.parent
        return parent


class OrderFilterForm(forms.Form):
    q = forms.CharField(label="Поиск", required=False, max_length=150)
    status = forms.ChoiceField(label="Заказ", required=False, choices=[("", "Все статусы"), *Order.Status.choices])
    payment = forms.ChoiceField(label="Оплата", required=False, choices=[("", "Все оплаты"), *Order.PaymentStatus.choices])
    date_from = forms.DateField(label="С даты", required=False, widget=forms.DateInput(attrs={"type": "date"}))
    date_to = forms.DateField(label="По дату", required=False, widget=forms.DateInput(attrs={"type": "date"}))

    def clean(self):
        data = super().clean()
        if data.get("date_from") and data.get("date_to") and data["date_from"] > data["date_to"]:
            raise forms.ValidationError("Начальная дата должна быть раньше конечной.")
        return data


class OrderActionForm(forms.Form):
    action = forms.ChoiceField(choices=[("ship", "Отправить"), ("deliver", "Доставлено"), ("cancel", "Отменить")])
    reason = forms.CharField(label="Причина отмены", required=False, max_length=2000,
                             widget=forms.Textarea(attrs={"rows": 3}))

    def clean(self):
        data = super().clean()
        if data.get("action") == "cancel" and not data.get("reason", "").strip():
            self.add_error("reason", "Укажите причину отмены.")
        return data


class StockForm(forms.Form):
    quantity = forms.IntegerField(label="Новый доступный остаток", min_value=0, max_value=2147483647)
    expected_stock = forms.IntegerField(min_value=0, widget=forms.HiddenInput)
    reason = forms.CharField(label="Причина корректировки", max_length=500)


class ReviewActionForm(forms.Form):
    action = forms.ChoiceField(choices=[("approve", "Опубликовать"), ("hide", "Скрыть")])
