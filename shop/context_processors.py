from .cart import get_cart_quantity


def cart_summary(request):
    return {"cart_quantity": get_cart_quantity(request)}
