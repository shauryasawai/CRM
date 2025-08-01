# Generated by Django 5.2.1 on 2025-07-22 12:29

import django.core.validators
import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('base', '0014_executionplan_rejected_at_executionplan_rejected_by'),
    ]

    operations = [
        migrations.CreateModel(
            name='ClientUpload',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('upload_id', models.CharField(editable=False, max_length=20, unique=True)),
                ('file', models.FileField(upload_to='client_uploads/', validators=[django.core.validators.FileExtensionValidator(allowed_extensions=['xlsx', 'xls'])])),
                ('uploaded_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('processed_at', models.DateTimeField(blank=True, null=True)),
                ('status', models.CharField(choices=[('pending', 'Pending Processing'), ('processing', 'Processing'), ('completed', 'Completed'), ('failed', 'Failed'), ('partial', 'Partially Processed'), ('archived', 'Archived')], default='pending', max_length=15)),
                ('total_rows', models.PositiveIntegerField(default=0)),
                ('processed_rows', models.PositiveIntegerField(default=0)),
                ('successful_rows', models.PositiveIntegerField(default=0)),
                ('failed_rows', models.PositiveIntegerField(default=0)),
                ('updated_rows', models.PositiveIntegerField(default=0)),
                ('processing_log', models.TextField(blank=True)),
                ('error_details', models.JSONField(blank=True, default=dict)),
                ('processing_summary', models.JSONField(blank=True, default=dict)),
                ('update_existing', models.BooleanField(default=True, help_text='Update existing client profiles if found')),
                ('is_archived', models.BooleanField(default=False)),
                ('archived_at', models.DateTimeField(blank=True, null=True)),
                ('archived_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='archived_client_uploads', to=settings.AUTH_USER_MODEL)),
                ('uploaded_by', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='client_uploads', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'Client Upload',
                'verbose_name_plural': 'Client Uploads',
                'ordering': ['-uploaded_at'],
            },
        ),
        migrations.CreateModel(
            name='ClientUploadLog',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('row_number', models.PositiveIntegerField(help_text='Row number in the uploaded file (0 for system messages)')),
                ('client_name', models.CharField(blank=True, max_length=255)),
                ('pan_number', models.CharField(blank=True, max_length=10)),
                ('status', models.CharField(choices=[('success', 'Success'), ('error', 'Error'), ('warning', 'Warning')], max_length=10)),
                ('message', models.TextField()),
                ('created_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('client_profile', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='upload_logs', to='base.clientprofile')),
                ('upload', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='processing_logs', to='base.clientupload')),
            ],
            options={
                'verbose_name': 'Client Upload Log',
                'verbose_name_plural': 'Client Upload Logs',
                'ordering': ['upload', 'row_number', 'created_at'],
            },
        ),
    ]
