from decimal import Decimal

from .models import Cart, CartItem, Product


CART_SESSION_KEY = "cart"


def _session_cart(session):
    return session.setdefault(CART_SESSION_KEY, {})


def add_to_session_cart(session, product_id, quantity=1):
    cart = _session_cart(session)
    key = str(product_id)
    cart[key] = int(cart.get(key, 0)) + int(quantity)
    session.modified = True


def set_session_quantity(session, product_id, quantity):
    cart = _session_cart(session)
    key = str(product_id)
    quantity = int(quantity)
    if quantity <= 0:
        cart.pop(key, None)
    else:
        cart[key] = quantity
    session.modified = True


def remove_from_session_cart(session, product_id):
    cart = _session_cart(session)
    cart.pop(str(product_id), None)
    session.modified = True


def clear_session_cart(session):
    session.pop(CART_SESSION_KEY, None)
    session.modified = True


def get_or_create_cart(user):
    cart, _ = Cart.objects.get_or_create(user=user)
    return cart


def merge_session_cart_to_db(user, session):
    session_cart = session.get(CART_SESSION_KEY, {})
    if not session_cart:
        return

    cart = get_or_create_cart(user)
    for product_id, quantity in session_cart.items():
        try:
            product = Product.objects.get(pk=product_id, is_active=True)
        except Product.DoesNotExist:
            continue
        item, created = CartItem.objects.get_or_create(
            cart=cart,
            product=product,
            defaults={"quantity": 0},
        )
        item.quantity = min(product.stock, item.quantity + int(quantity))
        if item.quantity > 0:
            item.save(update_fields=["quantity"])
        elif not created:
            item.delete()

    clear_session_cart(session)


def add_product(request, product, quantity=1):
    quantity = max(1, int(quantity))
    if request.user.is_authenticated:
        cart = get_or_create_cart(request.user)
        item, _ = CartItem.objects.get_or_create(cart=cart, product=product, defaults={"quantity": 0})
        item.quantity = min(product.stock, item.quantity + quantity)
        item.save(update_fields=["quantity"])
    else:
        add_to_session_cart(request.session, product.pk, quantity)


def set_product_quantity(request, product, quantity):
    quantity = max(0, int(quantity))
    if request.user.is_authenticated:
        cart = get_or_create_cart(request.user)
        try:
            item = CartItem.objects.get(cart=cart, product=product)
        except CartItem.DoesNotExist:
            return
        if quantity <= 0:
            item.delete()
        else:
            item.quantity = min(product.stock, quantity)
            item.save(update_fields=["quantity"])
    else:
        set_session_quantity(request.session, product.pk, quantity)


def remove_product(request, product):
    if request.user.is_authenticated:
        cart = get_or_create_cart(request.user)
        CartItem.objects.filter(cart=cart, product=product).delete()
    else:
        remove_from_session_cart(request.session, product.pk)


def clear_cart(request):
    if request.user.is_authenticated:
        get_or_create_cart(request.user).items.all().delete()
    else:
        clear_session_cart(request.session)


def get_cart_rows(request):
    rows = []
    total = Decimal("0.00")

    if request.user.is_authenticated:
        cart = get_or_create_cart(request.user)
        items = (
            cart.items.select_related("product", "product__category")
            .prefetch_related("product__wholesale_prices")
            .filter(product__is_active=True)
        )
        for item in items:
            unit_price = item.product.get_price_for_quantity(item.quantity)
            subtotal = unit_price * item.quantity
            rows.append({"product": item.product, "quantity": item.quantity, "subtotal": subtotal, "unit_price": unit_price})
            total += subtotal
    else:
        session_cart = request.session.get(CART_SESSION_KEY, {})
        products = (
            Product.objects.filter(id__in=session_cart.keys(), is_active=True)
            .select_related("category")
            .prefetch_related("wholesale_prices")
        )
        products_by_id = {str(product.id): product for product in products}
        for product_id, quantity in session_cart.items():
            product = products_by_id.get(str(product_id))
            if not product:
                continue
            quantity = min(product.stock, int(quantity))
            unit_price = product.get_price_for_quantity(quantity)
            subtotal = unit_price * quantity
            rows.append({"product": product, "quantity": quantity, "subtotal": subtotal, "unit_price": unit_price})
            total += subtotal

    return rows, total


def get_cart_quantity(request):
    if request.user.is_authenticated:
        cart = getattr(request.user, "cart", None)
        return cart.total_quantity if cart else 0
    return sum(int(quantity) for quantity in request.session.get(CART_SESSION_KEY, {}).values())
