from django.db import models
from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import timezone
from django.db.models import Sum
from decimal import Decimal
import uuid

class Department(models.Model):
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)

    def __str__(self):
        return self.name

class Employee(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='employee')
    employee_id = models.CharField(
        max_length=36,
        default=uuid.uuid4,
        unique=True,
        editable=False
    )
    designation = models.CharField(max_length=100)
    department = models.ForeignKey(Department, on_delete=models.SET_NULL, null=True)
    date_of_joining = models.DateField()
    reporting_manager = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True)
    leave_balance = models.PositiveIntegerField(default=0)
    phone_number = models.CharField(max_length=15, blank=True)
    emergency_contact = models.CharField(max_length=15, blank=True)
    address = models.TextField(blank=True)
    office_location = models.CharField(max_length=100, blank=True, help_text="Latitude,Longitude format")
    
    # Hierarchy levels
    HIERARCHY_CHOICES = [
        ('TM', 'Top Management'),
        ('BH', 'Business Head'),
        ('RMH', 'RM Head'),
        ('RM', 'RM'),
    ]
    hierarchy_level = models.CharField(max_length=3, choices=HIERARCHY_CHOICES)
    
    def __str__(self):
        return f"{self.user.get_full_name()} - {self.get_hierarchy_level_display()}"
    
    def is_on_leave(self):
        """Check if employee is currently on approved leave"""
        today = timezone.now().date()
        return LeaveRequest.objects.filter(
            employee=self,
            status='A',
            start_date__lte=today,
            end_date__gte=today
        ).exists()

class LeaveType(models.Model):
    name = models.CharField(max_length=50)
    description = models.TextField(blank=True)
    max_days = models.PositiveIntegerField()

    def __str__(self):
        return self.name

class LeaveQuota(models.Model):
    """Leave quota per hierarchy level"""
    hierarchy_level = models.CharField(max_length=3, choices=Employee.HIERARCHY_CHOICES)
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
    
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE)
    leave_type = models.ForeignKey(LeaveType, on_delete=models.CASCADE)
    start_date = models.DateField()
    end_date = models.DateField()
    total_days = models.PositiveIntegerField(default=1)
    reason = models.TextField()
    status = models.CharField(max_length=2, choices=STATUS_CHOICES, default='P')
    applied_on = models.DateTimeField(auto_now_add=True)
    processed_by = models.ForeignKey(Employee, on_delete=models.SET_NULL, null=True, blank=True, related_name='processed_leaves')
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
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE)
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
    """Monthly reimbursement claims"""
    STATUS_CHOICES = [
        ('D', 'Draft'),
        ('P', 'Pending'),
        ('MA', 'Manager Approved'),
        ('A', 'Approved'),
        ('R', 'Rejected'),
    ]
    
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE)
    month = models.PositiveIntegerField(validators=[MinValueValidator(1), MaxValueValidator(12)])
    year = models.PositiveIntegerField()
    total_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    status = models.CharField(max_length=2, choices=STATUS_CHOICES, default='D')
    
    # Submission details
    submitted_on = models.DateTimeField(null=True, blank=True)
    
    # Manager approval
    manager_approved_by = models.ForeignKey(Employee, on_delete=models.SET_NULL, null=True, blank=True, related_name='manager_approved_claims')
    manager_approved_on = models.DateTimeField(null=True, blank=True)
    manager_comments = models.TextField(blank=True)
    
    # Final approval (Top Management)
    final_approved_by = models.ForeignKey(Employee, on_delete=models.SET_NULL, null=True, blank=True, related_name='final_approved_claims')
    final_approved_on = models.DateTimeField(null=True, blank=True)
    final_comments = models.TextField(blank=True)
    
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
    
    claim = models.ForeignKey(ReimbursementClaim, on_delete=models.CASCADE, related_name='expenses')
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
    recipient = models.ForeignKey(Employee, on_delete=models.CASCADE)
    message = models.TextField()
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    link = models.CharField(max_length=255, blank=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"Notification for {self.recipient}"