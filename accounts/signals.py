from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import AdminProfile, ClientProfile, User


@receiver(post_save, sender=User)
def create_user_profiles(sender, instance, created, **kwargs):
    if not created or kwargs.get("raw", False):
        return
    if instance.is_client:
        ClientProfile.objects.get_or_create(user=instance)
    if instance.is_admin or instance.is_staff:
        AdminProfile.objects.get_or_create(user=instance)
