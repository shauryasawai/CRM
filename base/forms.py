from django import forms
from django.contrib.auth.forms import UserCreationForm, UserChangeForm
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from .models import User, Lead, Client, Task, ServiceRequest, InvestmentPlanReview, Team, BusinessTracker


class CustomUserCreationForm(UserCreationForm):
    """Custom user creation form with hierarchy validation"""
    
    class Meta:
        model = User
        fields = ('username', 'email', 'first_name', 'last_name', 'role', 'manager')
        
    def __init__(self, *args, **kwargs):
        self.current_user = kwargs.pop('current_user', None)
        super().__init__(*args, **kwargs)
        
        # Limit manager choices based on hierarchy
        if self.current_user:
            if self.current_user.role == 'top_management':
                # Top management can create any role
                pass
            elif self.current_user.role == 'business_head':
                # Business heads can create RM heads and RMs
                self.fields['role'].choices = [
                    ('rm_head', 'RM Head'),
                    ('rm', 'Relationship Manager'),
                ]
                # Manager can be business head or top management
                self.fields['manager'].queryset = User.objects.filter(
                    role__in=['business_head', 'top_management']
                )
            elif self.current_user.role == 'rm_head':
                # RM heads can only create RMs
                self.fields['role'].choices = [('rm', 'Relationship Manager')]
                self.fields['manager'].queryset = User.objects.filter(id=self.current_user.id)
                self.fields['manager'].initial = self.current_user
            else:
                # RMs cannot create users
                raise ValidationError("You don't have permission to create users.")

    def clean(self):
        cleaned_data = super().clean()
        role = cleaned_data.get('role')
        manager = cleaned_data.get('manager')
        
        # Validate hierarchy rules
        if role == 'top_management' and manager:
            raise ValidationError("Top Management cannot have a manager")
        elif role == 'business_head' and manager and manager.role != 'top_management':
            raise ValidationError("Business Head can only report to Top Management")
        elif role == 'rm_head' and manager and manager.role not in ['business_head', 'top_management']:
            raise ValidationError("RM Head can only report to Business Head or Top Management")
        elif role == 'rm' and manager and manager.role not in ['rm_head', 'business_head']:
            raise ValidationError("RM can only report to RM Head or Business Head")
            
        return cleaned_data


class CustomUserChangeForm(UserChangeForm):
    """Custom user change form"""
    
    class Meta:
        model = User
        fields = ('username', 'email', 'first_name', 'last_name', 'role', 'manager', 'is_active')


class TeamForm(forms.ModelForm):
    """Form for creating/editing teams"""
    
    class Meta:
        model = Team
        fields = ('name', 'head', 'description')
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Only RM Heads can be team heads
        self.fields['head'].queryset = User.objects.filter(role='rm_head')


class LeadForm(forms.ModelForm):
    """Form for creating/editing leads"""
    
    class Meta:
        model = Lead
        fields = ('name', 'contact_info', 'source', 'status', 'assigned_to', 'notes')
        widgets = {
            'notes': forms.Textarea(attrs={'rows': 4}),
            'contact_info': forms.TextInput(attrs={'placeholder': 'Phone/Email'}),
            'source': forms.TextInput(attrs={'placeholder': 'e.g., Website, Referral, Cold Call'}),
        }
    
    def __init__(self, *args, **kwargs):
        self.current_user = kwargs.pop('current_user', None)
        super().__init__(*args, **kwargs)
        
        # Limit assigned_to choices based on user role
        if self.current_user:
            if self.current_user.role in ['top_management', 'business_head']:
                # Can assign to any RM or RM Head
                self.fields['assigned_to'].queryset = User.objects.filter(
                    role__in=['rm', 'rm_head', 'business_head']
                )
            elif self.current_user.role == 'rm_head':
                # Can assign to team members or self
                accessible_users = self.current_user.get_accessible_users()
                self.fields['assigned_to'].queryset = User.objects.filter(
                    id__in=[u.id for u in accessible_users],
                    role__in=['rm', 'rm_head']
                )
            else:  # RM
                # Can only assign to self
                self.fields['assigned_to'].queryset = User.objects.filter(id=self.current_user.id)
                self.fields['assigned_to'].initial = self.current_user


class ClientForm(forms.ModelForm):
    """Form for creating/editing clients"""
    
    class Meta:
        model = Client
        fields = ('name', 'contact_info', 'user', 'lead', 'aum', 'sip_amount', 'demat_count')
        widgets = {
            'contact_info': forms.TextInput(attrs={'placeholder': 'Phone/Email'}),
            'aum': forms.NumberInput(attrs={'step': '0.01', 'min': '0'}),
            'sip_amount': forms.NumberInput(attrs={'step': '0.01', 'min': '0'}),
            'demat_count': forms.NumberInput(attrs={'min': '0'}),
        }
    
    def __init__(self, *args, **kwargs):
        self.current_user = kwargs.pop('current_user', None)
        super().__init__(*args, **kwargs)
        
        # Limit user choices based on current user's role
        if self.current_user:
            if self.current_user.role in ['top_management', 'business_head']:
                # Can assign to any RM
                self.fields['user'].queryset = User.objects.filter(role='rm')
            elif self.current_user.role == 'rm_head':
                # Can assign to team RMs
                team_members = self.current_user.get_team_members()
                self.fields['user'].queryset = team_members
            else:  # RM
                # Can only assign to self
                self.fields['user'].queryset = User.objects.filter(id=self.current_user.id)
                self.fields['user'].initial = self.current_user
        
        # Limit lead choices to converted leads without clients
        self.fields['lead'].queryset = Lead.objects.filter(
            status='converted',
            client__isnull=True
        )
        self.fields['lead'].required = False


class TaskForm(forms.ModelForm):
    """Form for creating/editing tasks"""
    
    class Meta:
        model = Task
        fields = ('title', 'description', 'assigned_to', 'due_date', 'priority')
        widgets = {
            'description': forms.Textarea(attrs={'rows': 4}),
            'due_date': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
        }
    
    def __init__(self, *args, **kwargs):
        self.current_user = kwargs.pop('current_user', None)
        super().__init__(*args, **kwargs)
        
        # Limit assigned_to choices based on user role
        if self.current_user:
            if self.current_user.role in ['top_management', 'business_head']:
                # Can assign to anyone
                self.fields['assigned_to'].queryset = User.objects.all()
            elif self.current_user.role == 'rm_head':
                # Can assign to team members or self
                accessible_users = self.current_user.get_accessible_users()
                self.fields['assigned_to'].queryset = accessible_users
            else:  # RM
                # Can only assign to self
                self.fields['assigned_to'].queryset = User.objects.filter(id=self.current_user.id)
                self.fields['assigned_to'].initial = self.current_user

    def save(self, commit=True):
        task = super().save(commit=False)
        if self.current_user:
            task.assigned_by = self.current_user
        if commit:
            task.save()
        return task


class ServiceRequestForm(forms.ModelForm):
    """Form for creating/editing service requests"""
    
    class Meta:
        model = ServiceRequest
        fields = ('client', 'description', 'priority', 'assigned_to')
        widgets = {
            'description': forms.Textarea(attrs={'rows': 4}),
        }
    
    def __init__(self, *args, **kwargs):
        self.current_user = kwargs.pop('current_user', None)
        super().__init__(*args, **kwargs)
        
        # Limit client choices based on user role
        if self.current_user:
            if self.current_user.role in ['top_management', 'business_head']:
                # Can create service requests for any client
                self.fields['client'].queryset = Client.objects.all()
                self.fields['assigned_to'].queryset = User.objects.filter(role__in=['rm', 'rm_head'])
            elif self.current_user.role == 'rm_head':
                # Can create for team clients
                accessible_users = self.current_user.get_accessible_users()
                self.fields['client'].queryset = Client.objects.filter(user__in=accessible_users)
                self.fields['assigned_to'].queryset = accessible_users.filter(role='rm')
            else:  # RM
                # Can only create for own clients
                self.fields['client'].queryset = Client.objects.filter(user=self.current_user)
                self.fields['assigned_to'].queryset = User.objects.filter(id=self.current_user.id)
                self.fields['assigned_to'].initial = self.current_user


class InvestmentPlanReviewForm(forms.ModelForm):
    """Form for creating/editing investment plan reviews"""
    
    class Meta:
        model = InvestmentPlanReview
        fields = ('client', 'goal', 'principal_amount', 'monthly_investment', 
                 'tenure_years', 'expected_return_rate')
        widgets = {
            'goal': forms.TextInput(attrs={'placeholder': 'e.g., Child Education, Retirement'}),
            'principal_amount': forms.NumberInput(attrs={'step': '0.01', 'min': '0'}),
            'monthly_investment': forms.NumberInput(attrs={'step': '0.01', 'min': '0'}),
            'tenure_years': forms.NumberInput(attrs={'min': '1', 'max': '50'}),
            'expected_return_rate': forms.NumberInput(attrs={'step': '0.01', 'min': '0', 'max': '50'}),
        }
    
    def __init__(self, *args, **kwargs):
        self.current_user = kwargs.pop('current_user', None)
        super().__init__(*args, **kwargs)
        
        # Limit client choices based on user role
        if self.current_user:
            if self.current_user.role in ['top_management', 'business_head']:
                # Can create for any client
                self.fields['client'].queryset = Client.objects.all()
            elif self.current_user.role == 'rm_head':
                # Can create for team clients
                accessible_users = self.current_user.get_accessible_users()
                self.fields['client'].queryset = Client.objects.filter(user__in=accessible_users)
            else:  # RM
                # Can only create for own clients
                self.fields['client'].queryset = Client.objects.filter(user=self.current_user)

    def save(self, commit=True):
        plan = super().save(commit=False)
        if self.current_user:
            plan.created_by = self.current_user
        if commit:
            plan.save()
        return plan


class BusinessTrackerForm(forms.ModelForm):
    """Form for business tracking metrics"""
    
    class Meta:
        model = BusinessTracker
        fields = ('month', 'total_sip', 'total_demat', 'total_aum', 'user', 'team')
        widgets = {
            'month': forms.DateInput(attrs={'type': 'date'}),
            'total_sip': forms.NumberInput(attrs={'step': '0.01', 'min': '0'}),
            'total_aum': forms.NumberInput(attrs={'step': '0.01', 'min': '0'}),
            'total_demat': forms.NumberInput(attrs={'min': '0'}),
        }
    
    def __init__(self, *args, **kwargs):
        self.current_user = kwargs.pop('current_user', None)
        super().__init__(*args, **kwargs)
        
        # Limit user and team choices based on current user's role
        if self.current_user:
            if self.current_user.role in ['top_management', 'business_head']:
                # Can track for anyone
                self.fields['user'].queryset = User.objects.all()
                self.fields['team'].queryset = Team.objects.all()
            elif self.current_user.role == 'rm_head':
                # Can track for team members
                accessible_users = self.current_user.get_accessible_users()
                self.fields['user'].queryset = accessible_users
                self.fields['team'].queryset = Team.objects.filter(head=self.current_user)
            else:  # RM
                # Can only track for self
                self.fields['user'].queryset = User.objects.filter(id=self.current_user.id)
                self.fields['user'].initial = self.current_user
                self.fields['team'].queryset = Team.objects.none()


class UserAssignmentForm(forms.Form):
    """Form for assigning users to teams (for RM Heads)"""
    
    users = forms.ModelMultipleChoiceField(
        queryset=User.objects.filter(role='rm'),
        widget=forms.CheckboxSelectMultiple,
        required=False
    )
    
    def __init__(self, *args, **kwargs):
        self.rm_head = kwargs.pop('rm_head', None)
        super().__init__(*args, **kwargs)
        
        if self.rm_head:
            # Only show RMs that can be managed by this RM Head
            available_rms = User.objects.filter(
                role='rm',
                manager__in=[self.rm_head] + list(User.objects.filter(role='business_head'))
            )
            self.fields['users'].queryset = available_rms


class QuickStatsForm(forms.Form):
    """Form for filtering dashboard stats"""
    
    date_from = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'type': 'date'})
    )
    date_to = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'type': 'date'})
    )
    team = forms.ModelChoiceField(
        queryset=Team.objects.all(),
        required=False,
        empty_label="All Teams"
    )
    user = forms.ModelChoiceField(
        queryset=User.objects.filter(role__in=['rm', 'rm_head']),
        required=False,
        empty_label="All Users"
    )
    
    def __init__(self, *args, **kwargs):
        self.current_user = kwargs.pop('current_user', None)
        super().__init__(*args, **kwargs)
        
        # Limit choices based on user role
        if self.current_user:
            if self.current_user.role == 'rm_head':
                accessible_users = self.current_user.get_accessible_users()
                self.fields['user'].queryset = accessible_users
                self.fields['team'].queryset = Team.objects.filter(head=self.current_user)
            elif self.current_user.role == 'rm':
                self.fields['user'].queryset = User.objects.filter(id=self.current_user.id)
                self.fields['user'].initial = self.current_user
                self.fields['team'].queryset = Team.objects.none()