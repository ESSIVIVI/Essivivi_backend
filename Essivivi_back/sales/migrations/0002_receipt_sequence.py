"""Séquence PostgreSQL des numéros de reçu (RC-AAAA-000001), sans doublon même en concurrence."""
from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("sales", "0001_initial")]
    operations = [
        migrations.RunSQL(
            "CREATE SEQUENCE IF NOT EXISTS receipt_number_seq;",
            "DROP SEQUENCE IF EXISTS receipt_number_seq;",
        )
    ]
