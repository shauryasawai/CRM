# Generated by Django 5.2.1 on 2025-07-06 06:30

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('base', '0008_servicerequestidcounter_and_more'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='client',
            options={'ordering': ['name'], 'verbose_name': 'Client', 'verbose_name_plural': 'Clients'},
        ),
        migrations.AddField(
            model_name='client',
            name='is_active',
            field=models.BooleanField(default=True),
        ),
    ]
