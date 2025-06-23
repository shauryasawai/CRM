from django import forms
from .models import (
    Department, LeaveRequest, Employee, LeaveType, Attendance,
    Holiday, ReimbursementClaim, ReimbursementExpense
)
from django.contrib.auth.models import User
from django.contrib.auth.forms import UserCreationForm

class EmployeeRegistrationForm(UserCreationForm):
    designation = forms.CharField(max_length=100)
    department = forms.ModelChoiceField(queryset=Department.objects.all())
    date_of_joining = forms.DateField(widget=forms.DateInput(attrs={'type': 'date'}))
    phone_number = forms.CharField(max_length=15, required=False)
    address = forms.CharField(widget=forms.Textarea, required=False)
    hierarchy_level = forms.ChoiceField(choices=Employee.HIERARCHY_CHOICES)
    reporting_manager = forms.ModelChoiceField(
        queryset=Employee.objects.all(), 
        required=False
    )

    class Meta:
        model = User
        fields = ['username', 'first_name', 'last_name', 'email', 'password1', 'password2']

class LeaveRequestForm(forms.ModelForm):
    class Meta:
        model = LeaveRequest
        fields = ['leave_type', 'start_date', 'end_date', 'reason']
        widgets = {
            'start_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'end_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'reason': forms.Textarea(attrs={'rows': 3, 'class': 'form-control'}),
            'leave_type': forms.Select(attrs={'class': 'form-control'}),
        }

    def clean(self):
        cleaned_data = super().clean()
        start_date = cleaned_data.get('start_date')
        end_date = cleaned_data.get('end_date')

        if start_date and end_date:
            if start_date > end_date:
                raise forms.ValidationError("Start date cannot be after end date.")
            
            # Check if dates are in the past
            from django.utils import timezone
            if start_date < timezone.now().date():
                raise forms.ValidationError("Cannot apply for leave in the past.")

        return cleaned_data

class LeaveApprovalForm(forms.ModelForm):
    manager_comments = forms.CharField(
        widget=forms.Textarea(attrs={'rows': 3, 'class': 'form-control'}),
        required=False,
        label="Comments"
    )

    class Meta:
        model = LeaveRequest
        fields = ['status', 'manager_comments']
        widgets = {
            'status': forms.RadioSelect(choices=[
                ('A', 'Approved'),
                ('R', 'Rejected'),
                ('C', 'Cancelled')
            ])
        }

class AttendanceForm(forms.ModelForm):
    class Meta:
        model = Attendance
        fields = ['login_time', 'logout_time', 'login_location', 'notes']
        widgets = {
            'login_time': forms.DateTimeInput(attrs={'type': 'datetime-local', 'class': 'form-control'}),
            'logout_time': forms.DateTimeInput(attrs={'type': 'datetime-local', 'class': 'form-control'}),
            'login_location': forms.TextInput(attrs={'class': 'form-control'}),
            'notes': forms.Textarea(attrs={'rows': 2, 'class': 'form-control'}),
        }

class ReimbursementClaimForm(forms.ModelForm):
    class Meta:
        model = ReimbursementClaim
        fields = ['month', 'year']
        widgets = {
            'month': forms.Select(choices=[
                (1, 'January'), (2, 'February'), (3, 'March'),
                (4, 'April'), (5, 'May'), (6, 'June'),
                (7, 'July'), (8, 'August'), (9, 'September'),
                (10, 'October'), (11, 'November'), (12, 'December')
            ], attrs={'class': 'form-control'}),
            'year': forms.NumberInput(attrs={'class': 'form-control', 'min': '2020', 'max': '2030'}),
        }

class ReimbursementExpenseForm(forms.ModelForm):
    class Meta:
        model = ReimbursementExpense
        fields = ['expense_date', 'description', 'amount', 'receipt']
        widgets = {
            'expense_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'category': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'rows': 2, 'class': 'form-control'}),
            'amount': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0'}),
            'receipt': forms.FileInput(attrs={'class': 'form-control', 'accept': 'image/*,.pdf'}),
        }

    def clean_amount(self):
        amount = self.cleaned_data.get('amount')
        if amount and amount <= 0:
            raise forms.ValidationError("Amount must be greater than zero.")
        return amount

    def clean_expense_date(self):
        expense_date = self.cleaned_data.get('expense_date')
        if expense_date:
            from django.utils import timezone
            if expense_date > timezone.now().date():
                raise forms.ValidationError("Expense date cannot be in the future.")
        return expense_date

class HolidayForm(forms.ModelForm):
    class Meta:
        model = Holiday
        fields = ['name', 'date', 'description']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'description': forms.Textarea(attrs={'rows': 2, 'class': 'form-control'}),
        }

    def clean_date(self):
        date = self.cleaned_data.get('date')
        if date:
            # Check if holiday already exists for this date
            if Holiday.objects.filter(date=date).exclude(pk=self.instance.pk if self.instance else None).exists():
                raise forms.ValidationError("A holiday already exists for this date.")
        return date

class LeaveCancellationForm(forms.Form):
    cancellation_reason = forms.CharField(
        widget=forms.Textarea(attrs={'rows': 3, 'class': 'form-control'}),
        label="Reason for Cancellation",
        help_text="Please provide a reason for cancelling this leave request."
    )

    def clean_cancellation_reason(self):
        reason = self.cleaned_data.get('cancellation_reason')
        if reason and len(reason.strip()) < 10:
            raise forms.ValidationError("Please provide a detailed reason (at least 10 characters).")
        return reason

# Additional forms for enhanced functionality

class EmployeeUpdateForm(forms.ModelForm):
    """Form for updating employee profile"""
    class Meta:
        model = Employee
        fields = ['designation', 'phone_number', 'address', 'emergency_contact']
        widgets = {
            'designation': forms.TextInput(attrs={'class': 'form-control'}),
            'phone_number': forms.TextInput(attrs={'class': 'form-control'}),
            'address': forms.Textarea(attrs={'rows': 3, 'class': 'form-control'}),
            'emergency_contact': forms.TextInput(attrs={'class': 'form-control'}),
        }

class UserUpdateForm(forms.ModelForm):
    """Form for updating user information"""
    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'email']
        widgets = {
            'first_name': forms.TextInput(attrs={'class': 'form-control'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
        }

class AttendanceFilterForm(forms.Form):
    """Form for filtering attendance records"""
    start_date = forms.DateField(
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
        required=False
    )
    end_date = forms.DateField(
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
        required=False
    )
    employee = forms.ModelChoiceField(
        queryset=Employee.objects.all(),
        widget=forms.Select(attrs={'class': 'form-control'}),
        required=False,
        empty_label="All Employees"
    )

class LeaveFilterForm(forms.Form):
    """Form for filtering leave requests"""
    FILTER_STATUS_CHOICES = [
        ('', 'All Status'),
        ('P', 'Pending'),
        ('A', 'Approved'),
        ('R', 'Rejected'),
        ('C', 'Cancelled'),
        ('CR', 'Cancellation Requested'),
    ]
    
    status = forms.ChoiceField(
        choices=FILTER_STATUS_CHOICES,
        widget=forms.Select(attrs={'class': 'form-control'}),
        required=False
    )
    leave_type = forms.ModelChoiceField(
        queryset=LeaveType.objects.all(),
        widget=forms.Select(attrs={'class': 'form-control'}),
        required=False,
        empty_label="All Leave Types"
    )
    start_date = forms.DateField(
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
        required=False,
        label="From Date"
    )
    end_date = forms.DateField(
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
        required=False,
        label="To Date"
    )

class ReimbursementFilterForm(forms.Form):
    """Form for filtering reimbursement claims"""
    FILTER_STATUS_CHOICES = [
        ('', 'All Status'),
        ('D', 'Draft'),
        ('P', 'Pending'),
        ('MA', 'Manager Approved'),
        ('A', 'Approved'),
        ('R', 'Rejected'),
    ]
    
    status = forms.ChoiceField(
        choices=FILTER_STATUS_CHOICES,
        widget=forms.Select(attrs={'class': 'form-control'}),
        required=False
    )
    month = forms.ChoiceField(
        choices=[('', 'All Months')] + [
            (i, month) for i, month in enumerate([
                'January', 'February', 'March', 'April', 'May', 'June',
                'July', 'August', 'September', 'October', 'November', 'December'
            ], 1)
        ],
        widget=forms.Select(attrs={'class': 'form-control'}),
        required=False
    )
    year = forms.ChoiceField(
        choices=[('', 'All Years')] + [(i, i) for i in range(2020, 2031)],
        widget=forms.Select(attrs={'class': 'form-control'}),
        required=False
    )

class BulkApprovalForm(forms.Form):
    """Form for bulk approval of requests"""
    action = forms.ChoiceField(
        choices=[
            ('approve', 'Approve Selected'),
            ('reject', 'Reject Selected'),
        ],
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    comments = forms.CharField(
        widget=forms.Textarea(attrs={'rows': 2, 'class': 'form-control'}),
        required=False,
        label="Comments (optional)"
    )
    selected_items = forms.CharField(
        widget=forms.HiddenInput(),
        required=True
    )