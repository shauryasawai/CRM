from django.db import models
from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import timezone

class Department(models.Model):
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)

    def __str__(self):
        return self.name

class Employee(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='employee')
    designation = models.CharField(max_length=100)
    department = models.ForeignKey(Department, on_delete=models.SET_NULL, null=True)
    date_of_joining = models.DateField()
    reporting_manager = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True)
    leave_balance = models.PositiveIntegerField(default=0)
    phone_number = models.CharField(max_length=15, blank=True)
    address = models.TextField(blank=True)
    
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

class LeaveType(models.Model):
    name = models.CharField(max_length=50)
    description = models.TextField(blank=True)
    max_days = models.PositiveIntegerField()

    def __str__(self):
        return self.name

class LeaveRequest(models.Model):
    STATUS_CHOICES = [
        ('P', 'Pending'),
        ('A', 'Approved'),
        ('R', 'Rejected'),
    ]
    
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE)
    leave_type = models.ForeignKey(LeaveType, on_delete=models.CASCADE)
    start_date = models.DateField()
    end_date = models.DateField()
    reason = models.TextField()
    status = models.CharField(max_length=1, choices=STATUS_CHOICES, default='P')
    applied_on = models.DateTimeField(auto_now_add=True)
    processed_by = models.ForeignKey(Employee, on_delete=models.SET_NULL, null=True, blank=True, related_name='processed_leaves')
    processed_on = models.DateTimeField(null=True, blank=True)
    
    def __str__(self):
        return f"{self.employee} - {self.leave_type} ({self.status})"

class Attendance(models.Model):
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE)
    date = models.DateField(default=timezone.now)
    login_time = models.DateTimeField()
    logout_time = models.DateTimeField(null=True, blank=True)
    login_location = models.CharField(max_length=255, blank=True)
    is_late = models.BooleanField(default=False)
    is_remote = models.BooleanField(default=False)
    
    def __str__(self):
        return f"{self.employee} - {self.date}"

class Notification(models.Model):
    recipient = models.ForeignKey(Employee, on_delete=models.CASCADE)
    message = models.TextField()
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    link = models.CharField(max_length=255, blank=True)
    
    def __str__(self):
        return f"Notification for {self.recipient}"