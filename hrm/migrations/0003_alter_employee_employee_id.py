# Generated by Django 5.2.1 on 2025-06-23 16:09

import uuid
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('hrm', '0002_alter_notification_options_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='employee',
            name='employee_id',
            field=models.CharField(default=uuid.uuid4, editable=False, max_length=36, unique=True),
        ),
    ]
