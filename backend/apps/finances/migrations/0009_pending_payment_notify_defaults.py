from django.db import migrations

NEW_SETTINGS = [
    ("NOTIFY_PENDING_PAYMENT_MEMBER", "true"),
    ("NOTIFY_PENDING_PAYMENT_ADMIN",  "true"),
    ("ADMIN_WHATSAPP_NUMBER",         ""),
]


def seed_defaults(apps, schema_editor):
    GymSetting = apps.get_model("finances", "GymSetting")
    for key, value in NEW_SETTINGS:
        GymSetting.objects.get_or_create(key=key, defaults={"value": value})


def remove_defaults(apps, schema_editor):
    GymSetting = apps.get_model("finances", "GymSetting")
    GymSetting.objects.filter(key__in=[k for k, _ in NEW_SETTINGS]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("finances", "0008_notification_settings_defaults"),
    ]

    operations = [
        migrations.RunPython(seed_defaults, remove_defaults),
    ]
