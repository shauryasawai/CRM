from django import forms
from django.contrib.auth.forms import UserCreationForm, UserChangeForm
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.db.models import Q
from .models import (
    User, Lead, Client, Task, ServiceRequest, InvestmentPlanReview, 
    Team, BusinessTracker, LeadInteraction, ProductDiscussion, 
    LeadStatusChange, TeamMembership, Reminder, ClientProfile,
    ClientProfileModification, MFUCANAccount, MotilalDematAccount,
    PrabhudasDematAccount
)

# Constants from models
ROLE_CHOICES = (
    ('top_management', 'Top Management'),
    ('business_head', 'Business Head'),
    ('rm_head', 'RM Head'),
    ('rm', 'Relationship Manager'),
    ('ops_team_lead', 'Operations Team Lead'),
    ('ops_exec', 'Operations Executive'),
)

CLIENT_STATUS_CHOICES = (
    ('active', 'Active'),
    ('muted', 'Muted'),
)

APPROVAL_STATUS_CHOICES = (
    ('pending', 'Pending Approval'),
    ('approved', 'Approved'),
    ('rejected', 'Rejected'),
)

class CustomUserCreationForm(UserCreationForm):
    """Custom user creation form with hierarchy validation"""
    
    class Meta:
        model = User
        fields = ('username', 'email', 'first_name', 'last_name', 'role', 'manager', 'teams')
        widgets = {
            'teams': forms.SelectMultiple(attrs={'class': 'form-control'}),
            'role': forms.Select(attrs={'class': 'form-control'}),
            'manager': forms.Select(attrs={'class': 'form-control'}),
            'username': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'first_name': forms.TextInput(attrs={'class': 'form-control'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control'}),
        }
        
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
                    ('ops_team_lead', 'Operations Team Lead'),
                    ('ops_exec', 'Operations Executive'),
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
            elif self.current_user.role == 'ops_team_lead':
                # Ops Team Leads can only create Ops Execs
                self.fields['role'].choices = [('ops_exec', 'Operations Executive')]
                self.fields['manager'].queryset = User.objects.filter(id=self.current_user.id)
                self.fields['manager'].initial = self.current_user
            else:
                # RMs and Ops Execs cannot create users
                raise ValidationError("You don't have permission to create users.")

        # Limit team choices based on user role
        if self.current_user and self.current_user.role in ['rm_head', 'ops_team_lead']:
            self.fields['teams'].queryset = Team.objects.filter(leader=self.current_user)
        else:
            self.fields['teams'].queryset = Team.objects.all()

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
        elif role == 'ops_team_lead' and manager and manager.role not in ['business_head', 'top_management']:
            raise ValidationError("Ops Team Lead can only report to Business Head or Top Management")
        elif role == 'ops_exec' and manager and manager.role != 'ops_team_lead':
            raise ValidationError("Ops Exec can only report to Ops Team Lead")
            
        return cleaned_data


class CustomUserChangeForm(UserChangeForm):
    """Custom user change form"""
    
    class Meta:
        model = User
        fields = ('username', 'email', 'first_name', 'last_name', 'role', 'manager', 'is_active', 'teams')
        widgets = {
            'teams': forms.SelectMultiple(attrs={'class': 'form-control'}),
            'role': forms.Select(attrs={'class': 'form-control'}),
            'manager': forms.Select(attrs={'class': 'form-control'}),
            'username': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'first_name': forms.TextInput(attrs={'class': 'form-control'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }


class TeamForm(forms.ModelForm):
    """Form for creating/editing teams"""
    
    class Meta:
        model = Team
        fields = ['name', 'description', 'leader', 'is_ops_team']
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3, 'class': 'form-control'}),
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'leader': forms.Select(attrs={'class': 'form-control'}),
            'is_ops_team': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Only RM Heads or Ops Team Leads can be team leaders
        self.fields['leader'].queryset = User.objects.filter(
            role__in=['rm_head', 'ops_team_lead'], 
            is_active=True
        )
        self.fields['leader'].empty_label = "Select Team Leader"


class TeamMembershipForm(forms.ModelForm):
    """Form for managing team memberships"""
    
    class Meta:
        model = TeamMembership
        fields = ['user', 'team', 'is_active']
        widgets = {
            'user': forms.Select(attrs={'class': 'form-control'}),
            'team': forms.Select(attrs={'class': 'form-control'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def __init__(self, *args, **kwargs):
        current_user = kwargs.pop('current_user', None)
        super().__init__(*args, **kwargs)
        
        # Limit team choices based on user role
        if current_user and current_user.role in ['rm_head', 'ops_team_lead']:
            self.fields['team'].queryset = Team.objects.filter(leader=current_user)
        else:
            self.fields['team'].queryset = Team.objects.all()
        
        # Limit user choices based on team type
        if 'team' in self.data:  # Form was submitted
            try:
                team_id = int(self.data.get('team'))
                team = Team.objects.get(id=team_id)
                if team.is_ops_team:
                    self.fields['user'].queryset = User.objects.filter(role='ops_exec', is_active=True)
                else:
                    self.fields['user'].queryset = User.objects.filter(role='rm', is_active=True)
            except (ValueError, Team.DoesNotExist):
                self.fields['user'].queryset = User.objects.none()
        elif self.instance.pk:  # Editing existing instance
            if self.instance.team.is_ops_team:
                self.fields['user'].queryset = User.objects.filter(role='ops_exec', is_active=True)
            else:
                self.fields['user'].queryset = User.objects.filter(role='rm', is_active=True)
        else:
            self.fields['user'].queryset = User.objects.none()

from django import forms
from django.forms import ModelForm
from django.contrib.auth import get_user_model

User = get_user_model()

class ClientProfileForm(ModelForm):
    """Form for creating/editing client profiles"""
    
    class Meta:
        model = ClientProfile
        fields = [
            'client_full_name', 'family_head_name', 'address_kyc', 'date_of_birth',
            'pan_number', 'email', 'mobile_number', 'first_investment_date',
            'mapped_rm', 'mapped_ops_exec', 'status'
        ]
        widgets = {
            'client_full_name': forms.TextInput(attrs={'class': 'form-control'}),
            'family_head_name': forms.TextInput(attrs={'class': 'form-control'}),
            'address_kyc': forms.Textarea(attrs={'rows': 3, 'class': 'form-control'}),
            'date_of_birth': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'pan_number': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'mobile_number': forms.TextInput(attrs={'class': 'form-control'}),
            'first_investment_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'mapped_rm': forms.Select(attrs={'class': 'form-control'}),
            'mapped_ops_exec': forms.Select(attrs={'class': 'form-control'}),
            'status': forms.Select(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        # Pop custom parameters before calling super().__init__
        self.current_user = kwargs.pop('current_user', None)
        # Also handle 'user' parameter for backward compatibility
        if not self.current_user:
            self.current_user = kwargs.pop('user', None)
        
        # Call parent's __init__ with remaining args and kwargs
        super().__init__(*args, **kwargs)
        
        # Set querysets for mapped users first
        if 'mapped_rm' in self.fields:
            rm_queryset = User.objects.filter(role='rm', is_active=True)
            print(f"Initial RM queryset count: {rm_queryset.count()}")
            for rm in rm_queryset:
                print(f"RM found: {rm.username} - {rm.get_full_name()}")
            self.fields['mapped_rm'].queryset = rm_queryset
            
        if 'mapped_ops_exec' in self.fields:
            ops_queryset = User.objects.filter(role='ops_exec', is_active=True)
            print(f"Initial Ops Exec queryset count: {ops_queryset.count()}")
            self.fields['mapped_ops_exec'].queryset = ops_queryset

        # Apply role-based restrictions
        if self.current_user:
            self._apply_role_restrictions()

    def _apply_role_restrictions(self):
        """Apply field restrictions based on user role"""
        user_role = self.current_user.role
        
        if user_role == 'rm_head':
            # RM heads can only assign RMs under their hierarchy
            if hasattr(self.current_user, 'get_accessible_users'):
                try:
                    accessible_users = self.current_user.get_accessible_users()
                    accessible_rm_ids = [u.id for u in accessible_users if u.role == 'rm']
                    print(f"RM Head accessible users: {len(accessible_users)}")
                    print(f"RM Head accessible RM IDs: {accessible_rm_ids}")
                    
                    if accessible_rm_ids:
                        self.fields['mapped_rm'].queryset = User.objects.filter(
                            id__in=accessible_rm_ids,
                            is_active=True
                        )
                    else:
                        # If no accessible RMs, show all RMs as fallback
                        print("No accessible RMs found, showing all RMs")
                        self.fields['mapped_rm'].queryset = User.objects.filter(
                            role='rm',
                            is_active=True
                        )
                except Exception as e:
                    print(f"Error getting accessible users: {e}")
                    # Fallback to all RMs
                    self.fields['mapped_rm'].queryset = User.objects.filter(
                        role='rm',
                        is_active=True
                    )
            else:
                print("get_accessible_users method not found, showing all RMs")
                # Fallback if method doesn't exist
                self.fields['mapped_rm'].queryset = User.objects.filter(
                    role='rm',
                    is_active=True
                )
            # RM heads can't assign ops executives
            if 'mapped_ops_exec' in self.fields:
                self.fields['mapped_ops_exec'].disabled = True
                
        elif user_role == 'rm':
            # RMs can only assign to themselves
            self.fields['mapped_rm'].queryset = User.objects.filter(id=self.current_user.id)
            self.fields['mapped_rm'].initial = self.current_user
            # RMs can't change RM or Ops Exec mapping
            self.fields['mapped_rm'].disabled = True
            if 'mapped_ops_exec' in self.fields:
                self.fields['mapped_ops_exec'].disabled = True
                
        elif user_role in ['business_head', 'top_management']:
            # Business heads and top management can assign to any RM
            self.fields['mapped_rm'].queryset = User.objects.filter(
                role='rm', 
                is_active=True
            )
            
        elif user_role in ['ops_exec', 'ops_team_lead']:
            # Operations team can't change RM mapping
            if 'mapped_rm' in self.fields:
                self.fields['mapped_rm'].disabled = True
        
        # Status field restrictions
        if user_role not in ['ops_team_lead', 'business_head', 'top_management', 'rm_head']:
            if 'status' in self.fields:
                self.fields['status'].disabled = True

    def clean_pan_number(self):
        """Validate PAN number format"""
        pan = self.cleaned_data.get('pan_number', '').upper()
        if pan:
            import re
            pan_pattern = r'^[A-Z]{5}[0-9]{4}[A-Z]{1}$'
            if not re.match(pan_pattern, pan):
                raise forms.ValidationError("PAN number must be in format: ABCDE1234F")
        return pan

    def clean_mobile_number(self):
        """Validate mobile number"""
        mobile = self.cleaned_data.get('mobile_number', '')
        if mobile:
            # Remove any non-digit characters
            mobile_digits = ''.join(filter(str.isdigit, mobile))
            if len(mobile_digits) != 10:
                raise forms.ValidationError("Mobile number must be 10 digits")
        return mobile

    def clean_email(self):
        """Validate email uniqueness"""
        email = self.cleaned_data.get('email')
        if email:
            # Check if email already exists (excluding current instance)
            existing = ClientProfile.objects.filter(email=email)
            if self.instance and self.instance.pk:
                existing = existing.exclude(pk=self.instance.pk)
            if existing.exists():
                raise forms.ValidationError("A client with this email already exists")
        return email

    def clean_mapped_rm(self):
        """Handle RM field based on user permissions"""
        mapped_rm = self.cleaned_data.get('mapped_rm')
        
        # If user is RM, they can only assign to themselves
        if self.current_user and self.current_user.role == 'rm':
            return self.current_user
        
        # If field is disabled for ops team, keep existing value
        if (self.current_user and self.current_user.role in ['ops_exec', 'ops_team_lead'] 
            and self.instance and self.instance.pk and self.instance.mapped_rm):
            return self.instance.mapped_rm
            
        return mapped_rm

    def clean_mapped_ops_exec(self):
        """Handle Ops Exec field based on user permissions"""
        mapped_ops_exec = self.cleaned_data.get('mapped_ops_exec')
        
        # If field is disabled for certain roles, keep existing value
        if (self.current_user and self.current_user.role in ['rm', 'rm_head'] 
            and self.instance and self.instance.pk and self.instance.mapped_ops_exec):
            return self.instance.mapped_ops_exec
            
        return mapped_ops_exec

    def clean_status(self):
        """Handle status field based on user permissions"""
        status = self.cleaned_data.get('status')
        
        # If user can't change status, keep existing value
        if (self.current_user and 
            self.current_user.role not in ['ops_team_lead', 'business_head', 'top_management', 'rm_head'] and
            self.instance and self.instance.pk):
            return self.instance.status
            
        return status

class ClientProfileModificationForm(forms.ModelForm):
    """Form for requesting client profile modifications"""
    
    class Meta:
        model = ClientProfileModification
        fields = ['modification_data', 'reason', 'requires_top_management']
        widgets = {
            'reason': forms.Textarea(attrs={'rows': 4, 'class': 'form-control'}),
            'requires_top_management': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'modification_data': forms.HiddenInput(),
        }

    def __init__(self, *args, **kwargs):
        self.client_profile = kwargs.pop('client_profile', None)
        self.current_user = kwargs.pop('current_user', None)
        self.modification_fields = kwargs.pop('modification_fields', {})
        super().__init__(*args, **kwargs)
        
        if self.client_profile and self.current_user:
            # Add dynamic fields for modifications
            for field_name, field_value in self.modification_fields.items():
                self.fields[field_name] = forms.CharField(
                    initial=field_value,
                    widget=forms.TextInput(attrs={'class': 'form-control'})
                )
            
            # Remove the hidden modification_data field since we're using individual fields
            del self.fields['modification_data']

    def save(self, commit=True):
        modification = super().save(commit=False)
        if self.client_profile:
            modification.client = self.client_profile
        if self.current_user:
            modification.requested_by = self.current_user
        
        # Store all modified fields in modification_data
        modification_data = {}
        for field_name in self.modification_fields.keys():
            if field_name in self.cleaned_data:
                modification_data[field_name] = self.cleaned_data[field_name]
        
        modification.modification_data = modification_data
        
        if commit:
            modification.save()
        
        return modification


class MFUCANAccountForm(forms.ModelForm):
    """Form for MFU CAN Account details"""
    
    class Meta:
        model = MFUCANAccount
        fields = ['account_number', 'folio_number', 'amc_name', 'kyc_status', 'last_transaction_date', 'is_primary']
        widgets = {
            'account_number': forms.TextInput(attrs={'class': 'form-control'}),
            'folio_number': forms.TextInput(attrs={'class': 'form-control'}),
            'amc_name': forms.TextInput(attrs={'class': 'form-control'}),
            'kyc_status': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'last_transaction_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'is_primary': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }


class DematAccountForm(forms.ModelForm):
    """Base form for Demat accounts"""
    
    class Meta:
        fields = ['account_number', 'broker_name', 'dp_id', 'kyc_status', 'last_activity_date', 'is_primary']
        widgets = {
            'account_number': forms.TextInput(attrs={'class': 'form-control'}),
            'broker_name': forms.TextInput(attrs={'class': 'form-control'}),
            'dp_id': forms.TextInput(attrs={'class': 'form-control'}),
            'kyc_status': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'last_activity_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'is_primary': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }


class MotilalDematAccountForm(DematAccountForm):
    """Form for Motilal Oswal Demat accounts"""
    
    class Meta(DematAccountForm.Meta):
        model = MotilalDematAccount
        fields = DematAccountForm.Meta.fields + ['trading_enabled', 'margin_enabled']
        widgets = {
            **DematAccountForm.Meta.widgets,
            'trading_enabled': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'margin_enabled': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }


class PrabhudasDematAccountForm(DematAccountForm):
    """Form for Prabhudas Lilladher Demat accounts"""
    
    class Meta(DematAccountForm.Meta):
        model = PrabhudasDematAccount
        fields = DematAccountForm.Meta.fields + ['commodity_enabled', 'currency_enabled']
        widgets = {
            **DematAccountForm.Meta.widgets,
            'commodity_enabled': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'currency_enabled': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

class UserEditForm(forms.ModelForm):
    """Form for editing user profiles"""
    
    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'email', 'role', 'manager', 'teams']
        widgets = {
            'first_name': forms.TextInput(attrs={'class': 'form-control'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'role': forms.Select(attrs={'class': 'form-control'}),
            'manager': forms.Select(attrs={'class': 'form-control'}),
            'teams': forms.SelectMultiple(attrs={'class': 'form-control'}),
        }
        
    def __init__(self, *args, **kwargs):
        current_user = kwargs.pop('current_user', None)
        super().__init__(*args, **kwargs)
        
        # Configure manager choices based on role
        if self.instance and self.instance.role:
            if self.instance.role == 'top_management':
                self.fields['manager'].queryset = User.objects.none()
            elif self.instance.role == 'business_head':
                self.fields['manager'].queryset = User.objects.filter(role='top_management')
            elif self.instance.role == 'rm_head':
                self.fields['manager'].queryset = User.objects.filter(role__in=['business_head', 'top_management'])
            elif self.instance.role == 'rm':
                self.fields['manager'].queryset = User.objects.filter(role__in=['rm_head', 'business_head'])
            elif self.instance.role == 'ops_team_lead':
                self.fields['manager'].queryset = User.objects.filter(role__in=['business_head', 'top_management'])
            elif self.instance.role == 'ops_exec':
                self.fields['manager'].queryset = User.objects.filter(role='ops_team_lead')

        # Limit team choices based on user role
        if current_user and current_user.role in ['rm_head', 'ops_team_lead']:
            self.fields['teams'].queryset = Team.objects.filter(leader=current_user)
        else:
            self.fields['teams'].queryset = Team.objects.all()

        # Disable role field if not top management
        if current_user and current_user.role != 'top_management':
            self.fields['role'].disabled = True
            
from .models import ClientAccount

class ClientAccountAssignmentForm(forms.Form):
    """Form for assigning accounts to clients"""
    
    account_type = forms.ChoiceField(
        choices=ClientAccount.ACCOUNT_TYPE_CHOICES,
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    
    def __init__(self, *args, **kwargs):
        self.client = kwargs.pop('client', None)
        super().__init__(*args, **kwargs)


class LeadForm(forms.ModelForm):
    """Form for creating/editing leads with enhanced features"""
    
    assigned_to = forms.ModelChoiceField(
        queryset=User.objects.filter(is_active=True).order_by('first_name', 'last_name'),
        empty_label="Select a user...",
        widget=forms.Select(attrs={'class': 'form-select'}),
        label="Assigned To"
    )
    
    # Source radio buttons with conditional field
    source = forms.ChoiceField(
        choices=Lead.SOURCE_CHOICES,
        widget=forms.RadioSelect(attrs={'class': 'source-radio'}),
        initial='other'
    )
    reference_client = forms.ModelChoiceField(
        queryset=Lead.objects.filter(converted=True),
        required=False,
        label="Existing Client Name",
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    source_details = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'placeholder': 'Please specify source details',
            'class': 'form-control'
        })
    )
    
    class Meta:
        model = Lead
        fields = [
            'name', 'email', 'mobile', 'source', 'source_details', 'reference_client',
            'assigned_to', 'probability', 'notes', 'next_interaction_date'
        ]
        widgets = {
            'name': forms.TextInput(attrs={
                'placeholder': 'Full Name',
                'class': 'form-control'
            }),
            'email': forms.EmailInput(attrs={
                'placeholder': 'Email Address',
                'class': 'form-control'
            }),
            'mobile': forms.TextInput(attrs={
                'placeholder': 'Mobile Number',
                'pattern': '[0-9]{10}',
                'title': '10 digit mobile number',
                'class': 'form-control'
            }),
            'notes': forms.Textarea(attrs={
                'rows': 4,
                'placeholder': 'Additional notes about the lead...',
                'class': 'form-control'
            }),
            'probability': forms.NumberInput(attrs={
                'min': 0,
                'max': 100,
                'step': 5,
                'class': 'form-control'
            }),
            'next_interaction_date': forms.DateInput(attrs={
                'type': 'date',
                'class': 'form-control'
            }),
        }
        labels = {
            'probability': 'Conversion Probability (%)',
            'next_interaction_date': 'Next Follow-up Date'
        }
    
    def __init__(self, *args, **kwargs):
        self.current_user = kwargs.pop('current_user', None)
        super().__init__(*args, **kwargs)
        
        # Configure assigned_to field based on user role
        self.configure_assignment_field()
        
        # Set initial status to 'new' for new leads
        if not self.instance.pk:
            self.instance.status = 'new'
        
        # Configure source fields
        self.configure_source_fields()
        
        # Customize the display of users in dropdown
        self.fields['assigned_to'].label_from_instance = lambda obj: f"{obj.get_full_name()} ({obj.username})" if obj.get_full_name() else obj.username
    
    def configure_assignment_field(self):
        """Configure the assigned_to field based on user role"""
        try:
            if not self.current_user:
                # If no current user, show all active users with relevant roles
                self.fields['assigned_to'].queryset = User.objects.filter(
                    role__in=['rm', 'rm_head', 'business_head'],
                    is_active=True
                ).order_by('first_name', 'last_name')
                return
            
            if self.current_user.role in ['top_management', 'business_head']:
                # Can assign to any RM or RM Head
                self.fields['assigned_to'].queryset = User.objects.filter(
                    role__in=['rm', 'rm_head', 'business_head'],
                    is_active=True
                ).order_by('first_name', 'last_name')
            elif self.current_user.role == 'rm_head':
                # Can assign to team members or self
                accessible_users = self.current_user.get_accessible_users()
                self.fields['assigned_to'].queryset = accessible_users.filter(
                    role__in=['rm', 'rm_head']
                ).order_by('first_name', 'last_name')
            elif self.current_user.role == 'rm':
                # Can only assign to self
                self.fields['assigned_to'].queryset = User.objects.filter(id=self.current_user.id)
                self.fields['assigned_to'].initial = self.current_user
                self.fields['assigned_to'].widget.attrs['disabled'] = True
            else:
                # Default: show all users with relevant roles
                self.fields['assigned_to'].queryset = User.objects.filter(
                    role__in=['rm', 'rm_head', 'business_head'],
                    is_active=True
                ).order_by('first_name', 'last_name')
                
        except Exception as e:
            # Fallback: show all active users with relevant roles
            print(f"Error configuring assignment field: {e}")
            self.fields['assigned_to'].queryset = User.objects.filter(
                role__in=['rm', 'rm_head', 'business_head'],
                is_active=True
            ).order_by('first_name', 'last_name')
        
        # Ensure queryset is not empty
        if not self.fields['assigned_to'].queryset.exists():
            self.fields['assigned_to'].queryset = User.objects.filter(
                is_active=True
            ).order_by('first_name', 'last_name')
    
    def configure_source_fields(self):
        """Configure source-related fields and their requirements"""
        if 'source' in self.data:  # Form was submitted
            source = self.data.get('source')
        elif self.instance.pk:  # Editing existing lead
            source = self.instance.source
        else:  # New form
            source = self.fields['source'].initial
        
        # Show/hide and require fields based on source selection
        if source == 'existing_client':
            self.fields['reference_client'].required = True
            self.fields['source_details'].required = False
        elif source == 'other':
            self.fields['source_details'].required = True
            self.fields['reference_client'].required = False
        else:
            self.fields['source_details'].required = False
            self.fields['reference_client'].required = False
    
    def clean(self):
        cleaned_data = super().clean()
        source = cleaned_data.get('source')
        
        # Validate source-specific fields
        if source == 'existing_client' and not cleaned_data.get('reference_client'):
            self.add_error('reference_client', 'Please select an existing client')
        elif source == 'other' and not cleaned_data.get('source_details'):
            self.add_error('source_details', 'Please specify the source details')
        
        # Validate probability range
        probability = cleaned_data.get('probability', 0)
        if probability < 0 or probability > 100:
            self.add_error('probability', 'Probability must be between 0 and 100')
        
        return cleaned_data
    
    def save(self, commit=True):
        lead = super().save(commit=False)
        
        # Set created_by for new leads
        if not lead.pk and self.current_user:
            lead.created_by = self.current_user
        
        # Handle source data
        if lead.source == 'existing_client' and lead.reference_client:
            lead.source_details = f"Existing Client: {lead.reference_client.name}"
        elif lead.source == 'other':
            lead.source_details = self.cleaned_data.get('source_details', '')
        
        if commit:
            lead.save()
            if hasattr(self, 'save_m2m'):
                self.save_m2m()
        
        return lead


class LeadInteractionForm(forms.ModelForm):
    """Form for creating lead interactions"""
    
    class Meta:
        model = LeadInteraction
        fields = ['interaction_type', 'interaction_date', 'notes', 'next_step', 'next_date']
        widgets = {
            'interaction_date': forms.DateTimeInput(
                attrs={
                    'type': 'datetime-local',
                    'class': 'form-control'
                }
            ),
            'notes': forms.Textarea(
                attrs={
                    'rows': 4,
                    'class': 'form-control',
                    'placeholder': 'Enter interaction details...'
                }
            ),
            'next_step': forms.Textarea(
                attrs={
                    'rows': 3,
                    'class': 'form-control',
                    'placeholder': 'What is the next planned action?'
                }
            ),
            'next_date': forms.DateInput(
                attrs={
                    'type': 'date',
                    'class': 'form-control'
                }
            ),
            'interaction_type': forms.Select(
                attrs={'class': 'form-control'}
            )
        }
        labels = {
            'interaction_type': 'Type of Interaction',
            'interaction_date': 'Date & Time',
            'notes': 'Interaction Notes',
            'next_step': 'Next Action Plan',
            'next_date': 'Next Follow-up Date'
        }

    def __init__(self, *args, **kwargs):
        self.lead = kwargs.pop('lead', None)
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        
        # Set default interaction date to now
        if not self.instance.pk:
            self.fields['interaction_date'].initial = timezone.now()

    def save(self, commit=True):
        interaction = super().save(commit=False)
        if self.lead:
            interaction.lead = self.lead
        if self.user:
            interaction.interacted_by = self.user
        
        if commit:
            interaction.save()
            # Update lead's first_interaction_date if this is the first interaction
            if not self.lead.first_interaction_date:
                self.lead.first_interaction_date = interaction.interaction_date
                self.lead.save()
        
        return interaction


class ProductDiscussionForm(forms.ModelForm):
    """Form for recording product discussions with leads"""
    
    class Meta:
        model = ProductDiscussion
        fields = ['product', 'interest_level', 'notes']
        widgets = {
            'product': forms.Select(
                attrs={'class': 'form-control'}
            ),
            'interest_level': forms.NumberInput(
                attrs={
                    'class': 'form-control',
                    'min': 1,
                    'max': 10,
                    'step': 1
                }
            ),
            'notes': forms.Textarea(
                attrs={
                    'rows': 4,
                    'class': 'form-control',
                    'placeholder': 'Enter discussion details, client concerns, next steps...'
                }
            )
        }
        labels = {
            'product': 'Product Discussed',
            'interest_level': 'Interest Level (1-10)',
            'notes': 'Discussion Notes'
        }

    def __init__(self, *args, **kwargs):
        self.lead = kwargs.pop('lead', None)
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)

    def save(self, commit=True):
        discussion = super().save(commit=False)
        if self.lead:
            discussion.lead = self.lead
        if self.user:
            discussion.discussed_by = self.user
        
        if commit:
            discussion.save()
        
        return discussion


class LeadConversionForm(forms.Form):
    """Form for converting a lead to client"""
    
    confirm_conversion = forms.BooleanField(
        required=True,
        label="I confirm that this lead should be converted to a client",
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'})
    )
    
    conversion_notes = forms.CharField(
        required=False,
        widget=forms.Textarea(
            attrs={
                'rows': 4,
                'class': 'form-control',
                'placeholder': 'Enter any notes about the conversion...'
            }
        ),
        label="Conversion Notes"
    )
    
    # Client details for conversion
    client_name = forms.CharField(
        max_length=255,
        widget=forms.TextInput(attrs={'class': 'form-control'}),
        label="Client Name"
    )
    
    contact_info = forms.CharField(
        max_length=255,
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control'}),
        label="Contact Information"
    )
    
    initial_aum = forms.DecimalField(
        max_digits=15,
        decimal_places=2,
        required=False,
        initial=0.00,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
        label="Initial AUM"
    )
    
    initial_sip = forms.DecimalField(
        max_digits=15,
        decimal_places=2,
        required=False,
        initial=0.00,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
        label="Initial SIP Amount"
    )
    
    demat_count = forms.IntegerField(
        required=False,
        initial=0,
        widget=forms.NumberInput(attrs={'class': 'form-control'}),
        label="Number of Demat Accounts"
    )

    def __init__(self, *args, **kwargs):
        self.lead = kwargs.pop('lead', None)
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        
        if self.lead:
            # Pre-populate client name with lead name
            self.fields['client_name'].initial = self.lead.name
            self.fields['contact_info'].initial = f"{self.lead.email or ''} {self.lead.mobile or ''}".strip()

    def save(self):
        if self.lead and self.cleaned_data['confirm_conversion']:
            # Generate client ID
            self.lead.client_id = self.lead.generate_client_id()
            self.lead.converted = True
            self.lead.status = 'converted'
            self.lead.converted_at = timezone.now()
            self.lead.converted_by = self.user
            self.lead.save()
            
            # Create client record
            client = Client.objects.create(
                name=self.cleaned_data['client_name'],
                contact_info=self.cleaned_data.get('contact_info', 'N/A'),
                aum=self.cleaned_data.get('initial_aum', 0.00),
                sip_amount=self.cleaned_data.get('initial_sip', 0.00),
                demat_count=self.cleaned_data.get('demat_count', 0),
                user=self.lead.assigned_to,
                lead=self.lead
            )
            
            # Create status change record
            LeadStatusChange.objects.create(
                lead=self.lead,
                changed_by=self.user,
                old_status=self.lead.status,
                new_status='converted',
                notes=f"Lead converted to client. {self.cleaned_data.get('conversion_notes', '')}"
            )
            
            return self.lead, client
        return None, None


class LeadStatusChangeForm(forms.ModelForm):
    """Form for changing lead status"""
    
    class Meta:
        model = LeadStatusChange
        fields = ['new_status', 'notes']
        widgets = {
            'new_status': forms.Select(
                choices=Lead.STATUS_CHOICES,
                attrs={'class': 'form-control'}
            ),
            'notes': forms.Textarea(
                attrs={
                    'rows': 3,
                    'class': 'form-control',
                    'placeholder': 'Enter reason for status change...'
                }
            )
        }
        labels = {
            'new_status': 'New Status',
            'notes': 'Notes/Reason for Change'
        }

    def __init__(self, *args, **kwargs):
        self.lead = kwargs.pop('lead', None)
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        
        if self.lead:
            # Remove current status from choices
            current_status = self.lead.status
            choices = [choice for choice in Lead.STATUS_CHOICES if choice[0] != current_status]
            self.fields['new_status'].widget.choices = choices

    def clean_new_status(self):
        new_status = self.cleaned_data['new_status']
        if self.lead and new_status == self.lead.status:
            raise forms.ValidationError("Please select a different status.")
        return new_status

    def save(self, commit=True):
        status_change = super().save(commit=False)
        if self.lead:
            status_change.lead = self.lead
            status_change.old_status = self.lead.status
        if self.user:
            status_change.changed_by = self.user
        
        # Check if status change needs approval
        critical_status_changes = ['converted', 'lost']
        if status_change.new_status in critical_status_changes:
            # Get approval manager
            if self.lead.assigned_to:
                approval_manager = self.lead.assigned_to.get_approval_manager()
                if approval_manager:
                    status_change.needs_approval = True
                    status_change.approval_by = approval_manager
        
        if commit:
            status_change.save()
            # Update lead status only if no approval needed
            if not status_change.needs_approval:
                self.lead.status = status_change.new_status
                self.lead.save()
        
        return status_change


class LeadReassignmentForm(forms.Form):
    """Form for requesting lead reassignment"""
    
    new_assigned_to = forms.ModelChoiceField(
        queryset=None,
        empty_label="Select new RM...",
        widget=forms.Select(attrs={'class': 'form-control'}),
        label="Reassign To"
    )
    
    reason = forms.CharField(
        widget=forms.Textarea(
            attrs={
                'rows': 4,
                'class': 'form-control',
                'placeholder': 'Enter reason for reassignment request...'
            }
        ),
        label="Reason for Reassignment",
        help_text="Please provide a detailed reason for this reassignment request."
    )
    
    urgent = forms.BooleanField(
        required=False,
        label="Mark as Urgent",
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        help_text="Check if this reassignment is urgent and needs immediate attention."
    )

    def __init__(self, *args, **kwargs):
        self.lead = kwargs.pop('lead', None)
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        
        # Set queryset for available RMs (excluding current assigned RM)
        rm_roles = ['rm', 'rm_head', 'business_head']
        queryset = User.objects.filter(role__in=rm_roles, is_active=True)
        
        if self.lead and self.lead.assigned_to:
            queryset = queryset.exclude(id=self.lead.assigned_to.id)
        
        self.fields['new_assigned_to'].queryset = queryset

    def clean_new_assigned_to(self):
        new_rm = self.cleaned_data['new_assigned_to']
        if self.lead and self.lead.assigned_to == new_rm:
            raise forms.ValidationError("Please select a different RM.")
        return new_rm

    def save(self):
        if self.lead:
            new_rm = self.cleaned_data['new_assigned_to']
            reason = self.cleaned_data['reason']
            urgent = self.cleaned_data.get('urgent', False)
            
            # Use the lead's request_reassignment method
            success = self.lead.request_reassignment(new_rm, self.user)
            
            if success:
                # Add urgency note if marked urgent
                if urgent:
                    # Update the latest status change with urgent flag
                    latest_change = self.lead.status_changes.filter(
                        notes__contains='Reassignment requested'
                    ).first()
                    if latest_change:
                        latest_change.notes += f" [URGENT] {reason}"
                        latest_change.save()
                
                return True
            
        return False


class ClientForm(forms.ModelForm):
    """Form for creating/editing clients"""
    
    class Meta:
        model = Client
        fields = ('name', 'contact_info', 'user', 'lead', 'aum', 'sip_amount', 'demat_count')
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'contact_info': forms.TextInput(attrs={'placeholder': 'Phone/Email', 'class': 'form-control'}),
            'user': forms.Select(attrs={'class': 'form-control'}),
            'lead': forms.Select(attrs={'class': 'form-control'}),
            'aum': forms.NumberInput(attrs={'step': '0.01', 'min': '0', 'class': 'form-control'}),
            'sip_amount': forms.NumberInput(attrs={'step': '0.01', 'min': '0', 'class': 'form-control'}),
            'demat_count': forms.NumberInput(attrs={'min': '0', 'class': 'form-control'}),
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
            'title': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'rows': 4, 'class': 'form-control'}),
            'assigned_to': forms.Select(attrs={'class': 'form-control'}),
            'due_date': forms.DateTimeInput(attrs={'type': 'datetime-local', 'class': 'form-control'}),
            'priority': forms.Select(attrs={'class': 'form-control'}),
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
            'client': forms.Select(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'rows': 4, 'class': 'form-control'}),
            'priority': forms.Select(attrs={'class': 'form-control'}),
            'assigned_to': forms.Select(attrs={'class': 'form-control'}),
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
            'client': forms.Select(attrs={'class': 'form-control'}),
            'goal': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., Child Education, Retirement'
            }),
            'principal_amount': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01', 
                'min': '0'
            }),
            'monthly_investment': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01', 
                'min': '0'
            }),
            'tenure_years': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '1', 
                'max': '50'
            }),
            'expected_return_rate': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01', 
                'min': '0', 
                'max': '50'
            }),
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
            'month': forms.DateInput(attrs={
                'type': 'date',
                'class': 'form-control'
            }),
            'total_sip': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01', 
                'min': '0'
            }),
            'total_aum': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01', 
                'min': '0'
            }),
            'total_demat': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '0'
            }),
            'user': forms.Select(attrs={'class': 'form-control'}),
            'team': forms.Select(attrs={'class': 'form-control'}),
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
                self.fields['team'].queryset = Team.objects.filter(leader=self.current_user)
            else:  # RM
                # Can only track for self
                self.fields['user'].queryset = User.objects.filter(id=self.current_user.id)
                self.fields['user'].initial = self.current_user
                self.fields['team'].queryset = Team.objects.none()


class ReminderForm(forms.ModelForm):
    """Form for creating reminders"""
    
    class Meta:
        model = Reminder
        fields = ['message', 'remind_at']
        widgets = {
            'remind_at': forms.DateTimeInput(attrs={
                'type': 'datetime-local',
                'class': 'form-control'
            }),
            'message': forms.Textarea(attrs={
                'rows': 3,
                'class': 'form-control'
            }),
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        
        if not self.instance.pk:
            self.fields['remind_at'].initial = timezone.now() + timezone.timedelta(hours=1)

    def save(self, commit=True):
        reminder = super().save(commit=False)
        if self.user:
            reminder.user = self.user
        if commit:
            reminder.save()
        return reminder


class ClientSearchForm(forms.Form):
    """Form for searching clients"""
    
    search_query = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'placeholder': 'Search by name, PAN, mobile...',
            'class': 'form-control'
        })
    )
    
    status = forms.ChoiceField(
        choices=[('', 'All Statuses')] + list(CLIENT_STATUS_CHOICES),
        required=False,
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    
    rm = forms.ModelChoiceField(
        queryset=User.objects.filter(role='rm'),
        required=False,
        empty_label="All RMs",
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    
    ops_exec = forms.ModelChoiceField(
        queryset=User.objects.filter(role='ops_exec'),
        required=False,
        empty_label="All Ops Execs",
        widget=forms.Select(attrs={'class': 'form-control'})
    )


class LeadSearchForm(forms.Form):
    """Form for searching leads"""
    
    search_query = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'placeholder': 'Search by name, mobile, email...',
            'class': 'form-control'
        })
    )
    
    status = forms.ChoiceField(
        choices=[('', 'All Statuses')] + list(Lead.STATUS_CHOICES),
        required=False,
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    
    assigned_to = forms.ModelChoiceField(
        queryset=User.objects.filter(role__in=['rm', 'rm_head']),
        required=False,
        empty_label="All RMs",
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    
    source = forms.ChoiceField(
        choices=[('', 'All Sources')] + list(Lead.SOURCE_CHOICES),
        required=False,
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    
    converted = forms.ChoiceField(
        choices=[('', 'All'), ('true', 'Converted'), ('false', 'Not Converted')],
        required=False,
        widget=forms.Select(attrs={'class': 'form-control'})
    )


class QuickStatsForm(forms.Form):
    """Form for filtering dashboard stats"""
    
    date_from = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'})
    )
    date_to = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'})
    )
    team = forms.ModelChoiceField(
        queryset=Team.objects.all(),
        required=False,
        empty_label="All Teams",
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    user = forms.ModelChoiceField(
        queryset=User.objects.filter(role__in=['rm', 'rm_head']),
        required=False,
        empty_label="All Users",
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    
    def __init__(self, *args, **kwargs):
        self.current_user = kwargs.pop('current_user', None)
        super().__init__(*args, **kwargs)
        
        # Limit choices based on user role
        if self.current_user:
            if self.current_user.role == 'rm_head':
                accessible_users = self.current_user.get_accessible_users()
                self.fields['user'].queryset = accessible_users
                self.fields['team'].queryset = Team.objects.filter(leader=self.current_user)
            elif self.current_user.role == 'rm':
                self.fields['user'].queryset = User.objects.filter(id=self.current_user.id)
                self.fields['user'].initial = self.current_user
                self.fields['team'].queryset = Team.objects.none()