from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('members', '0020_member_photo'),
    ]

    operations = [
        migrations.AddField(
            model_name='memberpayment',
            name='registration_fee',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=10),
        ),
    ]
