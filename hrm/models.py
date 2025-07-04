from django.db import models
from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.db.models import Sum
from decimal import Decimal
import uuid
from datetime import datetime

# Import from your CRM module
from base.models import User, Team

class Department(models.Model):
    """Department structure aligned with CRM teams"""
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    team = models.OneToOneField(
        Team,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='hr_department',
        help_text="Link to CRM team structure"
    )
    head = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        limit_choices_to={'role__in': ['business_head', 'business_head_ops', 'rm_head', 'ops_team_lead']},
        related_name='headed_departments'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

class Employee(models.Model):
    """Enhanced Employee model aligned with CRM User model"""
    user = models.OneToOneField(
        User, 
        on_delete=models.CASCADE, 
        related_name='employee_profile'
    )
    employee_id = models.CharField(
        max_length=20,
        unique=True,
        editable=False,
        help_text="Auto-generated employee ID"
    )
    
    # Employment Details
    designation = models.CharField(max_length=100)
    department = models.ForeignKey(
        Department, 
        on_delete=models.SET_NULL, 
        null=True,
        related_name='employees'
    )
    date_of_joining = models.DateField()
    
    # Contact Information
    phone_number = models.CharField(max_length=15, blank=True)
    emergency_contact = models.CharField(max_length=15, blank=True)
    address = models.TextField(blank=True)
    
    # Office Details
    office_location = models.CharField(
        max_length=100, 
        blank=True, 
        help_text="Office address or coordinates (Latitude,Longitude format)"
    )
    
    # Leave Management - balances aligned with CRM role hierarchy
    leave_balance = models.PositiveIntegerField(default=0)
    
    # Reporting using CRM hierarchy
    reporting_manager = models.ForeignKey(
        'self', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        help_text="This will sync with CRM User.manager relationship"
    )
    
    # Hierarchy levels matching CRM roles
    HIERARCHY_CHOICES = [
        ('top_management', 'Top Management'),
        ('business_head', 'Business Head'),
        ('business_head_ops', 'Business Head - Ops'),
        ('rm_head', 'RM Head'),
        ('rm', 'Relationship Manager'),
        ('ops_team_lead', 'Operations Team Lead'),
        ('ops_exec', 'Operations Executive'),
    ]
    hierarchy_level = models.CharField(
        max_length=20, 
        choices=HIERARCHY_CHOICES,
        help_text="This should match the user's role in CRM"
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.get_full_name()} - {self.get_hierarchy_level_display()}"
    
    def save(self, *args, **kwargs):
        if not self.employee_id:
            self.employee_id = self.generate_employee_id()
        
        # Sync hierarchy level with CRM role
        if self.user_id:
            self.hierarchy_level = self.user.role
            
        # Sync reporting manager with CRM manager
        if self.user.manager:
            try:
                manager_employee = Employee.objects.get(user=self.user.manager)
                self.reporting_manager = manager_employee
            except Employee.DoesNotExist:
                pass
                
        super().save(*args, **kwargs)
    
    def generate_employee_id(self):
        """Generate unique employee ID"""
        year = datetime.now().year
        last_employee = Employee.objects.filter(
            employee_id__startswith=f"EMP{year}"
        ).order_by('-employee_id').first()
        
        if last_employee:
            last_num = int(last_employee.employee_id[-4:])
            new_num = last_num + 1
        else:
            new_num = 1
            
        return f"EMP{year}{new_num:04d}"
    
    def is_on_leave(self):
        """Check if employee is currently on approved leave"""
        today = timezone.now().date()
        return LeaveRequest.objects.filter(
            employee=self,
            status='A',
            start_date__lte=today,
            end_date__gte=today
        ).exists()
    
    def get_team_members(self):
        """Get team members using CRM hierarchy"""
        return self.user.get_team_members()
    
    def can_approve_leave(self, requester_employee):
        """Check if this employee can approve leave for requester using CRM hierarchy"""
        # Use CRM's approval hierarchy
        return self.user.can_approve_conversion(requester_employee.user)

class LeaveType(models.Model):
    name = models.CharField(max_length=50)
    description = models.TextField(blank=True)
    max_days = models.PositiveIntegerField()

    def __str__(self):
        return self.name

class LeaveQuota(models.Model):
    """Leave quota per hierarchy level matching CRM roles"""
    hierarchy_level = models.CharField(
        max_length=20, 
        choices=Employee.HIERARCHY_CHOICES
    )
    leave_type = models.ForeignKey(LeaveType, on_delete=models.CASCADE)
    quota = models.PositiveIntegerField()
    
    class Meta:
        unique_together = ['hierarchy_level', 'leave_type']
    
    def __str__(self):
        return f"{self.get_hierarchy_level_display()} - {self.leave_type.name}: {self.quota} days"

class LeaveRequest(models.Model):
    STATUS_CHOICES = [
        ('P', 'Pending'),
        ('A', 'Approved'),
        ('R', 'Rejected'),
        ('C', 'Cancelled'),
        ('CR', 'Cancellation Requested'),
    ]
    
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='leave_requests')
    leave_type = models.ForeignKey(LeaveType, on_delete=models.CASCADE)
    start_date = models.DateField()
    end_date = models.DateField()
    total_days = models.PositiveIntegerField(default=1)
    reason = models.TextField()
    status = models.CharField(max_length=2, choices=STATUS_CHOICES, default='P')
    applied_on = models.DateTimeField(auto_now_add=True)
    
    # Enhanced approval workflow using CRM hierarchy
    processed_by = models.ForeignKey(
        Employee, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='processed_leaves'
    )
    processed_on = models.DateTimeField(null=True, blank=True)
    manager_comments = models.TextField(blank=True)
    
    # Cancellation fields
    cancellation_reason = models.TextField(blank=True)
    
    def __str__(self):
        return f"{self.employee} - {self.leave_type} ({self.get_status_display()})"
    
    def save(self, *args, **kwargs):
        if not self.total_days:
            delta = self.end_date - self.start_date
            self.total_days = delta.days + 1
        super().save(*args, **kwargs)
    
    def get_approver(self):
        """Get the appropriate approver using CRM hierarchy"""
        return self.employee.user.get_approval_manager()
    
    def approve(self, approved_by_employee, comments=""):
        """Approve leave request"""
        if self.status == 'P' and approved_by_employee.can_approve_leave(self.employee):
            self.status = 'A'
            self.processed_by = approved_by_employee
            self.processed_on = timezone.now()
            self.manager_comments = comments
            self.save()
            return True
        return False
    
    def reject(self, rejected_by_employee, comments):
        """Reject leave request"""
        if self.status == 'P' and rejected_by_employee.can_approve_leave(self.employee):
            self.status = 'R'
            self.processed_by = rejected_by_employee
            self.processed_on = timezone.now()
            self.manager_comments = comments
            self.save()
            return True
        return False

class Holiday(models.Model):
    """Company holidays"""
    name = models.CharField(max_length=100)
    date = models.DateField()
    description = models.TextField(blank=True)
    
    class Meta:
        unique_together = ['name', 'date']
    
    def __str__(self):
        return f"{self.name} - {self.date}"

class Attendance(models.Model):
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='attendance_records')
    date = models.DateField(default=timezone.now)
    login_time = models.DateTimeField(null=True, blank=True)
    logout_time = models.DateTimeField(null=True, blank=True)
    login_location = models.CharField(max_length=255, blank=True)
    logout_location = models.CharField(max_length=255, blank=True)
    is_late = models.BooleanField(default=False)
    is_remote = models.BooleanField(default=False)
    notes = models.TextField(blank=True)
    
    class Meta:
        unique_together = ['employee', 'date']
    
    def __str__(self):
        return f"{self.employee} - {self.date}"
    
    @property
    def total_hours(self):
        """Calculate total hours worked"""
        if self.login_time and self.logout_time:
            duration = self.logout_time - self.login_time
            return duration.total_seconds() / 3600
        return 0

class ReimbursementClaim(models.Model):
    """Enhanced reimbursement claims with CRM-aligned approval workflow"""
    STATUS_CHOICES = [
        ('D', 'Draft'),
        ('P', 'Pending'),
        ('MA', 'Manager Approved'),
        ('A', 'Approved'),
        ('R', 'Rejected'),
    ]
    
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='reimbursement_claims')
    month = models.PositiveIntegerField(validators=[MinValueValidator(1), MaxValueValidator(12)])
    year = models.PositiveIntegerField()
    total_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    status = models.CharField(max_length=2, choices=STATUS_CHOICES, default='D')
    
    # Submission details
    submitted_on = models.DateTimeField(null=True, blank=True)
    
    # Manager approval using CRM hierarchy
    manager_approved_by = models.ForeignKey(
        Employee, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='manager_approved_claims'
    )
    manager_approved_on = models.DateTimeField(null=True, blank=True)
    manager_comments = models.TextField(blank=True)
    
    # Final approval (Top Management)
    final_approved_by = models.ForeignKey(
        Employee, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='final_approved_claims'
    )
    final_approved_on = models.DateTimeField(null=True, blank=True)
    final_comments = models.TextField(blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ['employee', 'month', 'year']
    
    def __str__(self):
        return f"{self.employee} - {self.month}/{self.year} - {self.get_status_display()}"
    
    def save(self, *args, **kwargs):
        # Update total amount from expenses
        if self.pk:
            self.total_amount = self.expenses.aggregate(
                total=Sum('amount')
            )['total'] or Decimal('0.00')
        super().save(*args, **kwargs)
    
    def get_approver(self):
        """Get the appropriate approver using CRM hierarchy"""
        return self.employee.user.get_approval_manager()
    
    def submit_for_approval(self):
        """Submit claim for approval"""
        if self.status == 'D':
            self.status = 'P'
            self.submitted_on = timezone.now()
            self.save()
            return True
        return False
    
    def approve_by_manager(self, manager_employee, comments=""):
        """Manager approval using CRM hierarchy"""
        if self.status == 'P' and manager_employee.user.can_approve_conversion(self.employee.user):
            # Check if this needs top management approval
            if manager_employee.hierarchy_level in ['top_management', 'business_head']:
                self.status = 'A'  # Final approval
                self.final_approved_by = manager_employee
                self.final_approved_on = timezone.now()
                self.final_comments = comments
            else:
                self.status = 'MA'  # Manager approved, needs final approval
                self.manager_approved_by = manager_employee
                self.manager_approved_on = timezone.now()
                self.manager_comments = comments
            
            self.save()
            return True
        return False
    
    def final_approve(self, approver_employee, comments=""):
        """Final approval by top management"""
        if (self.status == 'MA' and 
            approver_employee.hierarchy_level in ['top_management', 'business_head']):
            self.status = 'A'
            self.final_approved_by = approver_employee
            self.final_approved_on = timezone.now()
            self.final_comments = comments
            self.save()
            return True
        return False

class ReimbursementExpense(models.Model):
    """Individual expenses within a claim"""
    EXPENSE_TYPES = [
        ('TRAVEL', 'Travel'),
        ('FOOD', 'Food'),
        ('ACCOMMODATION', 'Accommodation'),
        ('FUEL', 'Fuel'),
        ('COMMUNICATION', 'Communication'),
        ('OFFICE_SUPPLIES', 'Office Supplies'),
        ('TRAINING', 'Training'),
        ('OTHER', 'Other'),
    ]
    
    claim = models.ForeignKey(
        ReimbursementClaim, 
        on_delete=models.CASCADE, 
        related_name='expenses'
    )
    expense_type = models.CharField(max_length=20, choices=EXPENSE_TYPES)
    description = models.CharField(max_length=255)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    expense_date = models.DateField()
    receipt = models.FileField(upload_to='receipts/', blank=True)
    
    def __str__(self):
        return f"{self.claim.employee} - {self.expense_type} - {self.amount}"
    
    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        # Update claim total
        self.claim.save()

class Notification(models.Model):
    """Enhanced notifications aligned with CRM hierarchy"""
    recipient = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='notifications')
    sender = models.ForeignKey(
        Employee,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='sent_notifications'
    )
    message = models.TextField()
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    link = models.CharField(max_length=255, blank=True)
    
    # Enhanced notification types
    notification_type = models.CharField(
        max_length=20,
        choices=[
            ('leave_request', 'Leave Request'),
            ('leave_approval', 'Leave Approval'),
            ('reimbursement', 'Reimbursement'),
            ('general', 'General'),
        ],
        default='general'
    )
    
    # Reference to related objects
    reference_id = models.CharField(max_length=50, blank=True)
    reference_model = models.CharField(max_length=50, blank=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"Notification for {self.recipient}"
    
    def mark_as_read(self):
        """Mark notification as read"""
        self.is_read = True
        self.save()
    
    @classmethod
    def create_leave_notification(cls, leave_request, recipient, message_type='request'):
        """Create leave-related notification"""
        if message_type == 'request':
            message = f"New leave request from {leave_request.employee.user.get_full_name()} for {leave_request.leave_type.name}"
        elif message_type == 'approval':
            message = f"Your leave request for {leave_request.leave_type.name} has been approved"
        elif message_type == 'rejection':
            message = f"Your leave request for {leave_request.leave_type.name} has been rejected"
        else:
            message = f"Leave request update: {leave_request}"
        
        return cls.objects.create(
            recipient=recipient,
            message=message,
            notification_type='leave_request',
            reference_id=str(leave_request.id),
            reference_model='LeaveRequest',
            link=f'/hrm/leave-requests/{leave_request.id}/'
        )
    
    @classmethod
    def create_reimbursement_notification(cls, claim, recipient, message_type='submission'):
        """Create reimbursement-related notification"""
        if message_type == 'submission':
            message = f"New reimbursement claim from {claim.employee.user.get_full_name()} for {claim.month}/{claim.year}"
        elif message_type == 'approval':
            message = f"Your reimbursement claim for {claim.month}/{claim.year} has been approved"
        else:
            message = f"Reimbursement claim update: {claim}"
        
        return cls.objects.create(
            recipient=recipient,
            message=message,
            notification_type='reimbursement',
            reference_id=str(claim.id),
            reference_model='ReimbursementClaim',
            link=f'/hrm/reimbursement-claims/{claim.id}/'
        )