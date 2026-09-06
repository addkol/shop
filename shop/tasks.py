from celery import shared_task

from .order_lifecycle import cancel_expired_orders


@shared_task
def cancel_expired_orders_task():
    return cancel_expired_orders()
