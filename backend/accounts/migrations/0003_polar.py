# Polar.sh migration: rename the Stripe customer id column.
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0002_user_email_verified_accountactiontoken"),
    ]

    operations = [
        migrations.RenameField(
            model_name="user",
            old_name="stripe_customer_id",
            new_name="polar_customer_id",
        ),
        migrations.AlterField(
            model_name="user",
            name="polar_customer_id",
            field=models.CharField(blank=True, default="", max_length=64),
        ),
    ]
