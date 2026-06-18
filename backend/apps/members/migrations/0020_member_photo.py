from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('members', '0019_member_notifications_enabled'),
    ]

    operations = [
        migrations.AddField(
            model_name='member',
            name='photo',
            field=models.ImageField(blank=True, null=True, upload_to='members/'),
        ),
    ]
