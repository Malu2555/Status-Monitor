# Polar.sh migration: rename Stripe ids, add product id, generalize the
# webhook ledger (StripeEvent -> WebhookEvent with a provider column).
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("billing", "0002_stripeevent"),
    ]

    operations = [
        migrations.RenameField(
            model_name="subscription",
            old_name="stripe_subscription_id",
            new_name="polar_subscription_id",
        ),
        migrations.RenameField(
            model_name="subscription",
            old_name="stripe_customer_id",
            new_name="polar_customer_id",
        ),
        migrations.AlterField(
            model_name="subscription",
            name="polar_subscription_id",
            field=models.CharField(blank=True, default="", max_length=64),
        ),
        migrations.AlterField(
            model_name="subscription",
            name="polar_customer_id",
            field=models.CharField(blank=True, default="", max_length=64),
        ),
        migrations.AddField(
            model_name="subscription",
            name="polar_product_id",
            field=models.CharField(blank=True, default="", max_length=64),
        ),
        migrations.RenameModel(old_name="StripeEvent", new_name="WebhookEvent"),
        migrations.AddField(
            model_name="webhookevent",
            name="provider",
            field=models.CharField(default="polar", max_length=24),
        ),
    ]
