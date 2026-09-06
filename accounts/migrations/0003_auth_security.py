from django.contrib.auth.hashers import make_password
from django.db import migrations, models
from django.db.models import Q


def clear_legacy_secrets(apps, schema_editor):
    ClientProfile = apps.get_model("accounts", "ClientProfile")
    AdminProfile = apps.get_model("accounts", "AdminProfile")
    User = apps.get_model("accounts", "User")

    ClientProfile.objects.exclude(verification_code_hash="").update(
        verification_code_hash="",
        verification_code_sent_at=None,
        verification_attempts=0,
    )
    AdminProfile.objects.exclude(email_verification_token="").update(
        email_verification_token="",
        email_verification_sent_at=None,
    )
    User.objects.filter(Q(password="") | Q(password__isnull=True)).update(
        password=make_password(None)
    )


class Migration(migrations.Migration):
    dependencies = [("accounts", "0002_alter_adminprofile_options_and_more")]

    operations = [
        migrations.RenameField(
            model_name="clientprofile",
            old_name="verification_code",
            new_name="verification_code_hash",
        ),
        migrations.AlterField(
            model_name="clientprofile",
            name="verification_code_hash",
            field=models.CharField(blank=True, max_length=256, verbose_name="Хеш кода подтверждения"),
        ),
        migrations.AddField(
            model_name="clientprofile",
            name="verification_requests_count",
            field=models.PositiveSmallIntegerField(default=0, verbose_name="Запросы кода"),
        ),
        migrations.AddField(
            model_name="clientprofile",
            name="verification_requests_started_at",
            field=models.DateTimeField(blank=True, null=True, verbose_name="Начало окна запросов"),
        ),
        migrations.AddField(
            model_name="adminprofile",
            name="email_verification_sent_at",
            field=models.DateTimeField(blank=True, null=True, verbose_name="Подтверждение отправлено"),
        ),
        migrations.AlterField(
            model_name="user",
            name="first_name",
            field=models.CharField(blank=True, max_length=150, verbose_name="Имя"),
        ),
        migrations.RunPython(clear_legacy_secrets, migrations.RunPython.noop),
    ]
