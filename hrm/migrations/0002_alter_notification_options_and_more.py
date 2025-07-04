# Generated by Django 5.2.1 on 2025-06-30 17:31

import django.core.validators
import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('base', '0004_mutualfundscheme_executionplan_executionmetrics_and_more'),
        ('hrm', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
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
            model_name='department',
            name='created_at',
            field=models.DateTimeField(auto_now_add=True, default=django.utils.timezone.now),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='department',
            name='head',
            field=models.ForeignKey(blank=True, limit_choices_to={'role__in': ['business_head', 'business_head_ops', 'rm_head', 'ops_team_lead']}, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='headed_departments', to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name='department',
            name='team',
            field=models.OneToOneField(blank=True, help_text='Link to CRM team structure', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='hr_department', to='base.team'),
        ),
        migrations.AddField(
            model_name='employee',
            name='created_at',
            field=models.DateTimeField(auto_now_add=True, default=django.utils.timezone.now),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='employee',
            name='emergency_contact',
            field=models.CharField(blank=True, max_length=15),
        ),
        migrations.AddField(
            model_name='employee',
            name='employee_id',
            field=models.CharField(default=1, editable=False, help_text='Auto-generated employee ID', max_length=20, unique=True),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='employee',
            name='office_location',
            field=models.CharField(blank=True, help_text='Office address or coordinates (Latitude,Longitude format)', max_length=100),
        ),
        migrations.AddField(
            model_name='employee',
            name='updated_at',
            field=models.DateTimeField(auto_now=True),
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
        migrations.AddField(
            model_name='notification',
            name='notification_type',
            field=models.CharField(choices=[('leave_request', 'Leave Request'), ('leave_approval', 'Leave Approval'), ('reimbursement', 'Reimbursement'), ('general', 'General')], default='general', max_length=20),
        ),
        migrations.AddField(
            model_name='notification',
            name='reference_id',
            field=models.CharField(blank=True, max_length=50),
        ),
        migrations.AddField(
            model_name='notification',
            name='reference_model',
            field=models.CharField(blank=True, max_length=50),
        ),
        migrations.AddField(
            model_name='notification',
            name='sender',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='sent_notifications', to='hrm.employee'),
        ),
        migrations.AlterField(
            model_name='attendance',
            name='employee',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='attendance_records', to='hrm.employee'),
        ),
        migrations.AlterField(
            model_name='attendance',
            name='login_time',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name='employee',
            name='department',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='employees', to='hrm.department'),
        ),
        migrations.AlterField(
            model_name='employee',
            name='hierarchy_level',
            field=models.CharField(choices=[('top_management', 'Top Management'), ('business_head', 'Business Head'), ('business_head_ops', 'Business Head - Ops'), ('rm_head', 'RM Head'), ('rm', 'Relationship Manager'), ('ops_team_lead', 'Operations Team Lead'), ('ops_exec', 'Operations Executive')], help_text="This should match the user's role in CRM", max_length=20),
        ),
        migrations.AlterField(
            model_name='employee',
            name='reporting_manager',
            field=models.ForeignKey(blank=True, help_text='This will sync with CRM User.manager relationship', null=True, on_delete=django.db.models.deletion.SET_NULL, to='hrm.employee'),
        ),
        migrations.AlterField(
            model_name='employee',
            name='user',
            field=models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='employee_profile', to=settings.AUTH_USER_MODEL),
        ),
        migrations.AlterField(
            model_name='leaverequest',
            name='employee',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='leave_requests', to='hrm.employee'),
        ),
        migrations.AlterField(
            model_name='leaverequest',
            name='status',
            field=models.CharField(choices=[('P', 'Pending'), ('A', 'Approved'), ('R', 'Rejected'), ('C', 'Cancelled'), ('CR', 'Cancellation Requested')], default='P', max_length=2),
        ),
        migrations.AlterField(
            model_name='notification',
            name='recipient',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='notifications', to='hrm.employee'),
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
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('employee', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='reimbursement_claims', to='hrm.employee')),
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
                ('hierarchy_level', models.CharField(choices=[('top_management', 'Top Management'), ('business_head', 'Business Head'), ('business_head_ops', 'Business Head - Ops'), ('rm_head', 'RM Head'), ('rm', 'Relationship Manager'), ('ops_team_lead', 'Operations Team Lead'), ('ops_exec', 'Operations Executive')], max_length=20)),
                ('quota', models.PositiveIntegerField()),
                ('leave_type', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='hrm.leavetype')),
            ],
            options={
                'unique_together': {('hierarchy_level', 'leave_type')},
            },
        ),
    ]
