from django import forms

from .models import Address, Order


class BootstrapFormMixin:
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            css_class = field.widget.attrs.get("class", "")
            if isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs["class"] = f"{css_class} form-check-input".strip()
            elif isinstance(field.widget, forms.RadioSelect):
                field.widget.attrs["class"] = css_class
            else:
                field.widget.attrs["class"] = f"{css_class} form-control".strip()


class CheckoutForm(BootstrapFormMixin, forms.Form):
    existing_address = forms.ModelChoiceField(
        label="Сохраненный адрес",
        queryset=Address.objects.none(),
        required=False,
        empty_label="Открыть новый адрес",
    )
    country = forms.CharField(max_length=100, initial="Киргизия", required=False, label="Страна")
    city = forms.CharField(max_length=100, required=False, label="Город")
    street = forms.CharField(max_length=150, required=False, label="Улица")
    building = forms.CharField(max_length=50, required=False, label="Дом")
    apartment = forms.CharField(max_length=50, required=False, label="Квартира")
    postal_code = forms.CharField(max_length=20, required=False, label="Почтовый код")
    save_address = forms.BooleanField(label="Сохранить адрес", required=False, initial=True)
    payment_method = forms.ChoiceField(
        choices=Order.PaymentMethod.choices,
        widget=forms.RadioSelect,
        initial=Order.PaymentMethod.QR,
        label="Способ оплаты",
    )

    def __init__(self, *args, user=None, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)
        if user and user.is_authenticated:
            self.fields["existing_address"].queryset = user.addresses.all()

    def clean(self):
        cleaned_data = super().clean()
        if cleaned_data.get("existing_address"):
            return cleaned_data

        required = ["country", "city", "street", "building"]
        missing = [field for field in required if not cleaned_data.get(field)]
        for field in missing:
            self.add_error(field, "Это поле обязательно для нового адреса.")
        return cleaned_data

    def get_or_create_address(self):
        existing_address = self.cleaned_data.get("existing_address")
        if existing_address:
            return existing_address

        return Address.objects.create(
            user=self.user,
            country=self.cleaned_data["country"],
            city=self.cleaned_data["city"],
            street=self.cleaned_data["street"],
            building=self.cleaned_data["building"],
            apartment=self.cleaned_data.get("apartment", ""),
            postal_code=self.cleaned_data.get("postal_code", ""),
            is_default=not self.user.addresses.exists(),
        )


class CancelOrderForm(BootstrapFormMixin, forms.Form):
    reason = forms.CharField(
        label="Причина отказа",
        min_length=5,
        max_length=500,
        widget=forms.Textarea(
            attrs={
                "rows": 3,
                "placeholder": "Например: передумал, ошибся с товаром, хочу изменить адрес...",
            }
        ),
    )
