from django import forms
from .models import Department, LeaveRequest, Employee, LeaveType, Attendance
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
            'start_date': forms.DateInput(attrs={'type': 'date'}),
            'end_date': forms.DateInput(attrs={'type': 'date'}),
            'reason': forms.Textarea(attrs={'rows': 3}),
        }

class LeaveApprovalForm(forms.ModelForm):
    class Meta:
        model = LeaveRequest
        fields = ['status']
        widgets = {
            'status': forms.RadioSelect(choices=LeaveRequest.STATUS_CHOICES[1:])
        }

class AttendanceForm(forms.ModelForm):
    class Meta:
        model = Attendance
        fields = ['login_time', 'logout_time', 'login_location']
        widgets = {
            'login_time': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
            'logout_time': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
        }