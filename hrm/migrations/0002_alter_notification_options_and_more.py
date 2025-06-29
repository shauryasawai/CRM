# Generated by Django 5.2.1 on 2025-06-23 16:08

import django.core.validators
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('hrm', '0001_initial'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='notification',
            options={'ordering': ['-created_at']},
        ),
        migrations.AddField(
            model_name='attendance',
            name='logout_location',
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AddField(
            model_name='attendance',
            name='notes',
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name='employee',
            name='emergency_contact',
            field=models.CharField(blank=True, max_length=15),
        ),
        migrations.AddField(
            model_name='employee',
            name='employee_id',
            field=models.CharField(default='EMP001', max_length=20),
        ),
        migrations.AddField(
            model_name='employee',
            name='office_location',
            field=models.CharField(blank=True, help_text='Latitude,Longitude format', max_length=100),
        ),
        migrations.AddField(
            model_name='leaverequest',
            name='cancellation_reason',
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name='leaverequest',
            name='manager_comments',
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name='leaverequest',
            name='total_days',
            field=models.PositiveIntegerField(default=1),
        ),
        migrations.AlterField(
            model_name='attendance',
            name='login_time',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name='leaverequest',
            name='status',
            field=models.CharField(choices=[('P', 'Pending'), ('A', 'Approved'), ('R', 'Rejected'), ('C', 'Cancelled'), ('CR', 'Cancellation Requested')], default='P', max_length=2),
        ),
        migrations.AlterUniqueTogether(
            name='attendance',
            unique_together={('employee', 'date')},
        ),
        migrations.CreateModel(
            name='Holiday',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=100)),
                ('date', models.DateField()),
                ('description', models.TextField(blank=True)),
            ],
            options={
                'unique_together': {('name', 'date')},
            },
        ),
        migrations.CreateModel(
            name='ReimbursementClaim',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('month', models.PositiveIntegerField(validators=[django.core.validators.MinValueValidator(1), django.core.validators.MaxValueValidator(12)])),
                ('year', models.PositiveIntegerField()),
                ('total_amount', models.DecimalField(decimal_places=2, default=0, max_digits=10)),
                ('status', models.CharField(choices=[('D', 'Draft'), ('P', 'Pending'), ('MA', 'Manager Approved'), ('A', 'Approved'), ('R', 'Rejected')], default='D', max_length=2)),
                ('submitted_on', models.DateTimeField(blank=True, null=True)),
                ('manager_approved_on', models.DateTimeField(blank=True, null=True)),
                ('manager_comments', models.TextField(blank=True)),
                ('final_approved_on', models.DateTimeField(blank=True, null=True)),
                ('final_comments', models.TextField(blank=True)),
                ('employee', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='hrm.employee')),
                ('final_approved_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='final_approved_claims', to='hrm.employee')),
                ('manager_approved_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='manager_approved_claims', to='hrm.employee')),
            ],
            options={
                'unique_together': {('employee', 'month', 'year')},
            },
        ),
        migrations.CreateModel(
            name='ReimbursementExpense',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('expense_type', models.CharField(choices=[('TRAVEL', 'Travel'), ('FOOD', 'Food'), ('ACCOMMODATION', 'Accommodation'), ('FUEL', 'Fuel'), ('COMMUNICATION', 'Communication'), ('OFFICE_SUPPLIES', 'Office Supplies'), ('TRAINING', 'Training'), ('OTHER', 'Other')], max_length=20)),
                ('description', models.CharField(max_length=255)),
                ('amount', models.DecimalField(decimal_places=2, max_digits=10)),
                ('expense_date', models.DateField()),
                ('receipt', models.FileField(blank=True, upload_to='receipts/')),
                ('claim', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='expenses', to='hrm.reimbursementclaim')),
            ],
        ),
        migrations.CreateModel(
            name='LeaveQuota',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('hierarchy_level', models.CharField(choices=[('TM', 'Top Management'), ('BH', 'Business Head'), ('RMH', 'RM Head'), ('RM', 'RM')], max_length=3)),
                ('quota', models.PositiveIntegerField()),
                ('leave_type', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='hrm.leavetype')),
            ],
            options={
                'unique_together': {('hierarchy_level', 'leave_type')},
            },
        ),
    ]
