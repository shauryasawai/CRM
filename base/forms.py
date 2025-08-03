from django import forms
from django.contrib.auth.forms import UserCreationForm, UserChangeForm
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.db.models import Q
from django.core.validators import FileExtensionValidator
from .models import (
    PortfolioUpload, ServiceRequestComment, ServiceRequestDocument, ServiceRequestType, User, Lead, Client, Task, ServiceRequest, 
    Team, BusinessTracker, LeadInteraction, ProductDiscussion, 
    LeadStatusChange, TeamMembership, Reminder, ClientProfile,
    ClientProfileModification, MFUCANAccount, Note, NoteList
)
from base import models
import pandas as pd

# Updated Constants with new operations roles
ROLE_CHOICES = (
    ('top_management', 'Top Management'),
    ('business_head', 'Business Head'),
    ('business_head_ops', 'Business Head - Ops'),  # New role
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

# Notes System Forms
class NoteListForm(forms.ModelForm):
    """Form for creating and updating note lists"""
    
    class Meta:
        model = NoteList
        fields = ['name', 'description']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter list name',
                'maxlength': 100
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'placeholder': 'Optional description for this list',
                'rows': 3
            })
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['name'].required = True
        self.fields['description'].required = False

    def clean_name(self):
        """Validate list name uniqueness per user"""
        name = self.cleaned_data.get('name')
        if name:
            # This validation will be handled at the view level since we need user context
            return name.strip()
        return name


class NoteForm(forms.ModelForm):
    """Form for creating and updating notes"""
    
    class Meta:
        model = Note
        fields = [
            'note_list', 'heading', 'content', 'creation_date', 
            'reminder_date', 'due_date', 'attachment'
        ]
        widgets = {
            'note_list': forms.Select(attrs={
                'class': 'form-control',
                'required': True
            }),
            'heading': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter note heading',
                'maxlength': 200,
                'required': True
            }),
            'content': forms.Textarea(attrs={
                'class': 'form-control',
                'placeholder': 'Enter note content...',
                'rows': 6,
                'required': True
            }),
            'creation_date': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date',
                'readonly': 'readonly'
            }),
            'reminder_date': forms.DateTimeInput(attrs={
                'class': 'form-control',
                'type': 'datetime-local',
                'placeholder': 'Select reminder date and time'
            }),
            'due_date': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date',
                'placeholder': 'Select due date'
            }),
            'attachment': forms.FileInput(attrs={
                'class': 'form-control',
                'accept': '.pdf,.doc,.docx,.txt,.jpg,.jpeg,.png,.xlsx,.xls'
            })
        }
        labels = {
            'note_list': 'List',
            'heading': 'Note Heading',
            'content': 'Note Content',
            'creation_date': 'Creation Date',
            'reminder_date': 'Reminder Date & Time',
            'due_date': 'Due Date',
            'attachment': 'Attach File (Max 500KB)'
        }
    
    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        
        # Set creation date to today by default
        if not self.instance.pk:
            self.fields['creation_date'].initial = timezone.now().date()
        
        # Filter note_list to only show current user's lists
        if self.user:
            self.fields['note_list'].queryset = NoteList.objects.filter(user=self.user)
            
            # If user has no lists, create a default one
            if not self.fields['note_list'].queryset.exists():
                default_list = NoteList.objects.create(
                    user=self.user,
                    name='General',
                    description='Default note list'
                )
                self.fields['note_list'].queryset = NoteList.objects.filter(user=self.user)
                self.fields['note_list'].initial = default_list
        
        # Make fields optional except required ones
        self.fields['reminder_date'].required = False
        self.fields['due_date'].required = False
        self.fields['attachment'].required = False
    
    def clean_attachment(self):
        """Validate file size (500KB limit)"""
        attachment = self.cleaned_data.get('attachment')
        if attachment:
            if attachment.size > 500 * 1024:  # 500KB in bytes
                raise ValidationError("File size cannot exceed 500KB. Please choose a smaller file.")
        return attachment
    
    def clean_reminder_date(self):
        """Validate reminder date is in the future"""
        reminder_date = self.cleaned_data.get('reminder_date')
        if reminder_date and reminder_date <= timezone.now():
            raise ValidationError("Reminder date must be in the future.")
        return reminder_date
    
    def clean_due_date(self):
        """Validate due date"""
        due_date = self.cleaned_data.get('due_date')
        creation_date = self.cleaned_data.get('creation_date')
        
        if due_date and creation_date and due_date < creation_date:
            raise ValidationError("Due date cannot be before creation date.")
        
        return due_date
    
    def clean(self):
        """Cross-field validation"""
        cleaned_data = super().clean()
        reminder_date = cleaned_data.get('reminder_date')
        due_date = cleaned_data.get('due_date')
        
        # If both reminder and due date are provided, reminder should be before due date
        if reminder_date and due_date:
            if reminder_date.date() > due_date:
                raise ValidationError("Reminder date cannot be after due date.")
        
        return cleaned_data


class QuickNoteForm(forms.ModelForm):
    """Simplified form for quick note creation"""
    
    class Meta:
        model = Note
        fields = ['note_list', 'heading', 'content']
        widgets = {
            'note_list': forms.Select(attrs={
                'class': 'form-control form-control-sm',
            }),
            'heading': forms.TextInput(attrs={
                'class': 'form-control form-control-sm',
                'placeholder': 'Quick note heading...',
            }),
            'content': forms.Textarea(attrs={
                'class': 'form-control form-control-sm',
                'placeholder': 'Quick note content...',
                'rows': 3
            })
        }
    
    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        
        # Filter note_list to only show current user's lists
        if self.user:
            self.fields['note_list'].queryset = NoteList.objects.filter(user=self.user)
            
            # Set default list if exists
            default_list = self.fields['note_list'].queryset.first()
            if default_list:
                self.fields['note_list'].initial = default_list
    
    def save(self, commit=True):
        """Save quick note with default values"""
        note = super().save(commit=False)
        note.user = self.user
        note.creation_date = timezone.now().date()
        
        if commit:
            note.save()
        return note


# Updated User Management Forms
class CustomUserCreationForm(UserCreationForm):
    """Custom user creation form with updated hierarchy validation"""
    
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
        
        # Updated role choices including operations roles
        self.fields['role'].choices = ROLE_CHOICES
        
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
            elif self.current_user.role == 'business_head_ops':
                # Business Head - Ops can create operations roles
                self.fields['role'].choices = [
                    ('ops_team_lead', 'Operations Team Lead'),
                    ('ops_exec', 'Operations Executive'),
                ]
                self.fields['manager'].queryset = User.objects.filter(
                    role__in=['business_head_ops', 'business_head', 'top_management']
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
        
        # Updated hierarchy validation rules
        if role == 'top_management' and manager:
            raise ValidationError("Top Management cannot have a manager")
        elif role == 'business_head' and manager and manager.role != 'top_management':
            raise ValidationError("Business Head can only report to Top Management")
        elif role == 'business_head_ops' and manager and manager.role not in ['top_management', 'business_head']:
            raise ValidationError("Business Head - Ops can only report to Top Management or Business Head")
        elif role == 'rm_head' and manager and manager.role not in ['business_head', 'top_management']:
            raise ValidationError("RM Head can only report to Business Head or Top Management")
        elif role == 'rm' and manager and manager.role not in ['rm_head', 'business_head']:
            raise ValidationError("RM can only report to RM Head or Business Head")
        elif role == 'ops_team_lead' and manager and manager.role not in ['business_head_ops', 'business_head', 'top_management']:
            raise ValidationError("Ops Team Lead can only report to Business Head - Ops, Business Head, or Top Management")
        elif role == 'ops_exec' and manager and manager.role != 'ops_team_lead':
            raise ValidationError("Ops Exec can only report to Ops Team Lead")
            
        return cleaned_data


class CustomUserChangeForm(UserChangeForm):
    """Custom user change form with updated roles"""
    
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
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['role'].choices = ROLE_CHOICES


class TeamForm(forms.ModelForm):
    """Form for creating/editing teams with operations support"""
    
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
        # Include operations team leads as possible leaders
        self.fields['leader'].queryset = User.objects.filter(
            role__in=['rm_head', 'ops_team_lead'], 
            is_active=True
        )
        self.fields['leader'].empty_label = "Select Team Leader"


class TeamMembershipForm(forms.ModelForm):
    """Form for managing team memberships with operations support"""
    
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


# Updated Client Profile Form
class ClientProfileForm(forms.ModelForm):
    """Enhanced form for creating/editing client profiles with operations support"""
    
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
        # Handle both current_user and user parameters for backward compatibility
        self.current_user = kwargs.pop('current_user', None)
        if not self.current_user:
            self.current_user = kwargs.pop('user', None)
        
        super().__init__(*args, **kwargs)
        
        # Set querysets for mapped users
        if 'mapped_rm' in self.fields:
            self.fields['mapped_rm'].queryset = User.objects.filter(role='rm', is_active=True)
            
        if 'mapped_ops_exec' in self.fields:
            self.fields['mapped_ops_exec'].queryset = User.objects.filter(role='ops_exec', is_active=True)

        # Apply role-based restrictions
        if self.current_user:
            self._apply_role_restrictions()

    def _apply_role_restrictions(self):
        """Apply field restrictions based on user role including operations roles"""
        user_role = self.current_user.role
        
        if user_role == 'rm_head':
            # RM heads can only assign RMs under their hierarchy
            if hasattr(self.current_user, 'get_accessible_users'):
                try:
                    accessible_users = self.current_user.get_accessible_users()
                    accessible_rm_ids = [u.id for u in accessible_users if u.role == 'rm']
                    
                    if accessible_rm_ids:
                        self.fields['mapped_rm'].queryset = User.objects.filter(
                            id__in=accessible_rm_ids,
                            is_active=True
                        )
                    else:
                        # Fallback to all RMs
                        self.fields['mapped_rm'].queryset = User.objects.filter(
                            role='rm',
                            is_active=True
                        )
                except Exception:
                    # Fallback to all RMs
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
            self.fields['mapped_rm'].disabled = True
            if 'mapped_ops_exec' in self.fields:
                self.fields['mapped_ops_exec'].disabled = True
                
        elif user_role in ['business_head', 'business_head_ops', 'top_management']:
            # Senior management can assign to any RM
            self.fields['mapped_rm'].queryset = User.objects.filter(
                role='rm', 
                is_active=True
            )
            
        elif user_role == 'ops_team_lead':
            # Ops Team Lead can assign ops executives from their team
            if hasattr(self.current_user, 'get_team_members'):
                team_members = self.current_user.get_team_members()
                self.fields['mapped_ops_exec'].queryset = User.objects.filter(
                    id__in=[tm.id for tm in team_members],
                    is_active=True
                )
            # Can't change RM mapping
            if 'mapped_rm' in self.fields:
                self.fields['mapped_rm'].disabled = True
                
        elif user_role == 'ops_exec':
            # Ops Exec can only assign to themselves
            self.fields['mapped_ops_exec'].queryset = User.objects.filter(id=self.current_user.id)
            self.fields['mapped_ops_exec'].initial = self.current_user
            self.fields['mapped_ops_exec'].disabled = True
            # Can't change RM mapping
            if 'mapped_rm' in self.fields:
                self.fields['mapped_rm'].disabled = True
        
        # Status field restrictions - updated for operations roles
        if user_role not in ['ops_team_lead', 'business_head', 'business_head_ops', 'top_management', 'rm_head']:
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


# Updated Task Form with operations support
class TaskForm(forms.ModelForm):
    """Enhanced task form with operations roles support"""
    
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
            if self.current_user.role in ['top_management', 'business_head', 'business_head_ops']:
                # Senior management can assign to anyone
                self.fields['assigned_to'].queryset = User.objects.filter(is_active=True)
            elif self.current_user.role == 'rm_head':
                # Can assign to team members or self
                accessible_users = self.current_user.get_accessible_users()
                self.fields['assigned_to'].queryset = accessible_users
            elif self.current_user.role == 'ops_team_lead':
                # Can assign to operations team members
                team_members = self.current_user.get_team_members()
                self.fields['assigned_to'].queryset = User.objects.filter(
                    id__in=[self.current_user.id] + [tm.id for tm in team_members]
                )
            else:  # RM, Ops Exec
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




# Additional Lead Management Forms
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
                lead=self.lead,
                created_by=self.user
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


# Client and Investment Forms
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
            if self.current_user.role in ['top_management', 'business_head', 'business_head_ops']:
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


# Additional Operations Forms
class ConvertToClientForm(forms.ModelForm):
    """Form for converting client profile to full client"""
    
    class Meta:
        model = Client
        fields = ['aum', 'sip_amount', 'demat_count', 'contact_info']
        widgets = {
            'aum': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter AUM amount',
                'step': '0.01'
            }),
            'sip_amount': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter SIP amount',
                'step': '0.01'
            }),
            'demat_count': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': 'Number of demat accounts',
                'min': '0'
            }),
            'contact_info': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Additional contact information'
            })
        }
        labels = {
            'aum': 'Assets Under Management (AUM)',
            'sip_amount': 'SIP Amount',
            'demat_count': 'Number of Demat Accounts',
            'contact_info': 'Additional Contact Information'
        }


# Account Management Forms
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


# Search and Filter Forms
class ClientSearchForm(forms.Form):
    """Form for searching clients with operations support"""
    
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
    from django import forms
from django.contrib.auth.forms import UserCreationForm, UserChangeForm
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.db.models import Q
from django.core.validators import FileExtensionValidator
from .models import (
    User, Lead, Client, Task, ServiceRequest, 
    Team, BusinessTracker, LeadInteraction, ProductDiscussion, 
    LeadStatusChange, TeamMembership, Reminder, ClientProfile,
    ClientProfileModification, MFUCANAccount, Note, NoteList
)

# Updated Constants with new operations roles
ROLE_CHOICES = (
    ('top_management', 'Top Management'),
    ('business_head', 'Business Head'),
    ('business_head_ops', 'Business Head - Ops'),  # New role
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

# Notes System Forms
class NoteListForm(forms.ModelForm):
    """Form for creating and updating note lists"""
    
    class Meta:
        model = NoteList
        fields = ['name', 'description']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter list name',
                'maxlength': 100
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'placeholder': 'Optional description for this list',
                'rows': 3
            })
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['name'].required = True
        self.fields['description'].required = False

    def clean_name(self):
        """Validate list name uniqueness per user"""
        name = self.cleaned_data.get('name')
        if name:
            # This validation will be handled at the view level since we need user context
            return name.strip()
        return name


class NoteForm(forms.ModelForm):
    """Form for creating and updating notes"""
    
    class Meta:
        model = Note
        fields = [
            'note_list', 'heading', 'content', 'creation_date', 
            'reminder_date', 'due_date', 'attachment'
        ]
        widgets = {
            'note_list': forms.Select(attrs={
                'class': 'form-control',
                'required': True
            }),
            'heading': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter note heading',
                'maxlength': 200,
                'required': True
            }),
            'content': forms.Textarea(attrs={
                'class': 'form-control',
                'placeholder': 'Enter note content...',
                'rows': 6,
                'required': True
            }),
            'creation_date': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date',
                'readonly': 'readonly'
            }),
            'reminder_date': forms.DateTimeInput(attrs={
                'class': 'form-control',
                'type': 'datetime-local',
                'placeholder': 'Select reminder date and time'
            }),
            'due_date': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date',
                'placeholder': 'Select due date'
            }),
            'attachment': forms.FileInput(attrs={
                'class': 'form-control',
                'accept': '.pdf,.doc,.docx,.txt,.jpg,.jpeg,.png,.xlsx,.xls'
            })
        }
        labels = {
            'note_list': 'List',
            'heading': 'Note Heading',
            'content': 'Note Content',
            'creation_date': 'Creation Date',
            'reminder_date': 'Reminder Date & Time',
            'due_date': 'Due Date',
            'attachment': 'Attach File (Max 500KB)'
        }
    
    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        
        # Set creation date to today by default
        if not self.instance.pk:
            self.fields['creation_date'].initial = timezone.now().date()
        
        # Filter note_list to only show current user's lists
        if self.user:
            self.fields['note_list'].queryset = NoteList.objects.filter(user=self.user)
            
            # If user has no lists, create a default one
            if not self.fields['note_list'].queryset.exists():
                default_list = NoteList.objects.create(
                    user=self.user,
                    name='General',
                    description='Default note list'
                )
                self.fields['note_list'].queryset = NoteList.objects.filter(user=self.user)
                self.fields['note_list'].initial = default_list
        
        # Make fields optional except required ones
        self.fields['reminder_date'].required = False
        self.fields['due_date'].required = False
        self.fields['attachment'].required = False
    
    def clean_attachment(self):
        """Validate file size (500KB limit)"""
        attachment = self.cleaned_data.get('attachment')
        if attachment:
            if attachment.size > 500 * 1024:  # 500KB in bytes
                raise ValidationError("File size cannot exceed 500KB. Please choose a smaller file.")
        return attachment
    
    def clean_reminder_date(self):
        """Validate reminder date is in the future"""
        reminder_date = self.cleaned_data.get('reminder_date')
        if reminder_date and reminder_date <= timezone.now():
            raise ValidationError("Reminder date must be in the future.")
        return reminder_date
    
    def clean_due_date(self):
        """Validate due date"""
        due_date = self.cleaned_data.get('due_date')
        creation_date = self.cleaned_data.get('creation_date')
        
        if due_date and creation_date and due_date < creation_date:
            raise ValidationError("Due date cannot be before creation date.")
        
        return due_date
    
    def clean(self):
        """Cross-field validation"""
        cleaned_data = super().clean()
        reminder_date = cleaned_data.get('reminder_date')
        due_date = cleaned_data.get('due_date')
        
        # If both reminder and due date are provided, reminder should be before due date
        if reminder_date and due_date:
            if reminder_date.date() > due_date:
                raise ValidationError("Reminder date cannot be after due date.")
        
        return cleaned_data


class QuickNoteForm(forms.ModelForm):
    """Simplified form for quick note creation"""
    
    class Meta:
        model = Note
        fields = ['note_list', 'heading', 'content']
        widgets = {
            'note_list': forms.Select(attrs={
                'class': 'form-control form-control-sm',
            }),
            'heading': forms.TextInput(attrs={
                'class': 'form-control form-control-sm',
                'placeholder': 'Quick note heading...',
            }),
            'content': forms.Textarea(attrs={
                'class': 'form-control form-control-sm',
                'placeholder': 'Quick note content...',
                'rows': 3
            })
        }
    
    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        
        # Filter note_list to only show current user's lists
        if self.user:
            self.fields['note_list'].queryset = NoteList.objects.filter(user=self.user)
            
            # Set default list if exists
            default_list = self.fields['note_list'].queryset.first()
            if default_list:
                self.fields['note_list'].initial = default_list
    
    def save(self, commit=True):
        """Save quick note with default values"""
        note = super().save(commit=False)
        note.user = self.user
        note.creation_date = timezone.now().date()
        
        if commit:
            note.save()
        return note


# Updated User Management Forms
class CustomUserCreationForm(UserCreationForm):
    """Custom user creation form with updated hierarchy validation"""
    
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
        
        # Updated role choices including operations roles
        self.fields['role'].choices = ROLE_CHOICES
        
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
            elif self.current_user.role == 'business_head_ops':
                # Business Head - Ops can create operations roles
                self.fields['role'].choices = [
                    ('ops_team_lead', 'Operations Team Lead'),
                    ('ops_exec', 'Operations Executive'),
                ]
                self.fields['manager'].queryset = User.objects.filter(
                    role__in=['business_head_ops', 'business_head', 'top_management']
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
        
        # Updated hierarchy validation rules
        if role == 'top_management' and manager:
            raise ValidationError("Top Management cannot have a manager")
        elif role == 'business_head' and manager and manager.role != 'top_management':
            raise ValidationError("Business Head can only report to Top Management")
        elif role == 'business_head_ops' and manager and manager.role not in ['top_management', 'business_head']:
            raise ValidationError("Business Head - Ops can only report to Top Management or Business Head")
        elif role == 'rm_head' and manager and manager.role not in ['business_head', 'top_management']:
            raise ValidationError("RM Head can only report to Business Head or Top Management")
        elif role == 'rm' and manager and manager.role not in ['rm_head', 'business_head']:
            raise ValidationError("RM can only report to RM Head or Business Head")
        elif role == 'ops_team_lead' and manager and manager.role not in ['business_head_ops', 'business_head', 'top_management']:
            raise ValidationError("Ops Team Lead can only report to Business Head - Ops, Business Head, or Top Management")
        elif role == 'ops_exec' and manager and manager.role != 'ops_team_lead':
            raise ValidationError("Ops Exec can only report to Ops Team Lead")
            
        return cleaned_data


class CustomUserChangeForm(UserChangeForm):
    """Custom user change form with updated roles"""
    
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
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['role'].choices = ROLE_CHOICES


class TeamForm(forms.ModelForm):
    """Form for creating/editing teams with operations support"""
    
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
        # Include operations team leads as possible leaders
        self.fields['leader'].queryset = User.objects.filter(
            role__in=['rm_head', 'ops_team_lead'], 
            is_active=True
        )
        self.fields['leader'].empty_label = "Select Team Leader"


class TeamMembershipForm(forms.ModelForm):
    """Form for managing team memberships with operations support"""
    
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


# Updated Client Profile Form
class ClientProfileForm(forms.ModelForm):
    """Enhanced form for creating/editing client profiles with operations support"""
    
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
        # Handle both current_user and user parameters for backward compatibility
        self.current_user = kwargs.pop('current_user', None)
        if not self.current_user:
            self.current_user = kwargs.pop('user', None)
        
        super().__init__(*args, **kwargs)
        
        # Set querysets for mapped users
        if 'mapped_rm' in self.fields:
            self.fields['mapped_rm'].queryset = User.objects.filter(role='rm', is_active=True)
            
        if 'mapped_ops_exec' in self.fields:
            self.fields['mapped_ops_exec'].queryset = User.objects.filter(role='ops_exec', is_active=True)

        # Apply role-based restrictions
        if self.current_user:
            self._apply_role_restrictions()

    def _apply_role_restrictions(self):
        """Apply field restrictions based on user role including operations roles"""
        user_role = self.current_user.role
        
        if user_role == 'rm_head':
            # RM heads can only assign RMs under their hierarchy
            if hasattr(self.current_user, 'get_accessible_users'):
                try:
                    accessible_users = self.current_user.get_accessible_users()
                    accessible_rm_ids = [u.id for u in accessible_users if u.role == 'rm']
                    
                    if accessible_rm_ids:
                        self.fields['mapped_rm'].queryset = User.objects.filter(
                            id__in=accessible_rm_ids,
                            is_active=True
                        )
                    else:
                        # Fallback to all RMs
                        self.fields['mapped_rm'].queryset = User.objects.filter(
                            role='rm',
                            is_active=True
                        )
                except Exception:
                    # Fallback to all RMs
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
            self.fields['mapped_rm'].disabled = True
            if 'mapped_ops_exec' in self.fields:
                self.fields['mapped_ops_exec'].disabled = True
                
        elif user_role in ['business_head', 'business_head_ops', 'top_management']:
            # Senior management can assign to any RM
            self.fields['mapped_rm'].queryset = User.objects.filter(
                role='rm', 
                is_active=True
            )
            
        elif user_role == 'ops_team_lead':
            # Ops Team Lead can assign ops executives from their team
            if hasattr(self.current_user, 'get_team_members'):
                team_members = self.current_user.get_team_members()
                self.fields['mapped_ops_exec'].queryset = User.objects.filter(
                    id__in=[tm.id for tm in team_members],
                    is_active=True
                )
            # Can't change RM mapping
            if 'mapped_rm' in self.fields:
                self.fields['mapped_rm'].disabled = True
                
        elif user_role == 'ops_exec':
            # Ops Exec can only assign to themselves
            self.fields['mapped_ops_exec'].queryset = User.objects.filter(id=self.current_user.id)
            self.fields['mapped_ops_exec'].initial = self.current_user
            self.fields['mapped_ops_exec'].disabled = True
            # Can't change RM mapping
            if 'mapped_rm' in self.fields:
                self.fields['mapped_rm'].disabled = True
        
        # Status field restrictions - updated for operations roles
        if user_role not in ['ops_team_lead', 'business_head', 'business_head_ops', 'top_management', 'rm_head']:
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


# Updated Task Form with operations support
class TaskForm(forms.ModelForm):
    """Enhanced task form with operations roles support"""
    
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
            if self.current_user.role in ['top_management', 'business_head', 'business_head_ops']:
                # Senior management can assign to anyone
                self.fields['assigned_to'].queryset = User.objects.filter(is_active=True)
            elif self.current_user.role == 'rm_head':
                # Can assign to team members or self
                accessible_users = self.current_user.get_accessible_users()
                self.fields['assigned_to'].queryset = accessible_users
            elif self.current_user.role == 'ops_team_lead':
                # Can assign to operations team members
                team_members = self.current_user.get_team_members()
                self.fields['assigned_to'].queryset = User.objects.filter(
                    id__in=[self.current_user.id] + [tm.id for tm in team_members]
                )
            else:  # RM, Ops Exec
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


from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone
from datetime import timedelta

from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone
from datetime import timedelta
from django.contrib.auth import get_user_model

User = get_user_model()


class ServiceRequestForm(forms.ModelForm):
    request_type = forms.ModelChoiceField(
        queryset=ServiceRequestType.objects.filter(is_active=True),
        widget=forms.Select(attrs={'class': 'form-control'}),
        empty_label="Select Request Type"
    )
    
    class Meta:
        model = ServiceRequest
        fields = (
            'client', 'request_type', 'description', 'priority', 
            'assigned_to'
        )
        widgets = {
            'client': forms.Select(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={
                'rows': 4, 
                'class': 'form-control',
                'placeholder': 'Describe the service request in detail...'
            }),
            'priority': forms.Select(attrs={'class': 'form-control'}),
            'assigned_to': forms.Select(attrs={'class': 'form-control'}),
        }
    
    def __init__(self, *args, **kwargs):
        self.current_user = kwargs.pop('current_user', None)
        super().__init__(*args, **kwargs)
        
        # Set default priority
        self.fields['priority'].initial = 'medium'
        
        if self.current_user:
            self._setup_client_queryset()
            self._setup_assigned_to_queryset()
            self._configure_field_access()
    
    def _setup_client_queryset(self):
        """Setup client queryset based on user role"""
        user_role = self.current_user.role
        
        if user_role in ['top_management', 'business_head', 'business_head_ops']:
            self.fields['client'].queryset = Client.objects.all()
            
        elif user_role == 'rm_head':
            if hasattr(self.current_user, 'get_accessible_users'):
                accessible_users = self.current_user.get_accessible_users()
                self.fields['client'].queryset = Client.objects.filter(user__in=accessible_users)
            else:
                self.fields['client'].queryset = Client.objects.all()
                
        elif user_role == 'rm':
            self.fields['client'].queryset = Client.objects.filter(user=self.current_user)
            
        elif user_role in ['ops_team_lead', 'ops_exec']:
            self.fields['client'].queryset = Client.objects.all()
            
        else:
            self.fields['client'].queryset = Client.objects.all()
    
    def _setup_assigned_to_queryset(self):
        """Setup assigned_to queryset based on user role"""
        user_role = self.current_user.role
        
        if user_role in ['top_management', 'business_head', 'business_head_ops']:
            # Can assign to any operations team member
            self.fields['assigned_to'].queryset = User.objects.filter(
                role__in=['ops_exec', 'ops_team_lead'],
                is_active=True
            ).order_by('first_name', 'last_name')
            
        elif user_role in ['rm_head', 'rm']:
            # Auto-assignment - show available ops executives
            self.fields['assigned_to'].queryset = User.objects.filter(
                role='ops_exec',
                is_active=True
            ).order_by('first_name', 'last_name')
            
        elif user_role == 'ops_team_lead':
            # Can assign to team members
            if hasattr(self.current_user, 'get_team_members'):
                team_members = self.current_user.get_team_members()
                self.fields['assigned_to'].queryset = User.objects.filter(
                    id__in=[tm.id for tm in team_members if tm.role == 'ops_exec'],
                    is_active=True
                )
            else:
                self.fields['assigned_to'].queryset = User.objects.filter(
                    role='ops_exec',
                    is_active=True
                )
                
        elif user_role == 'ops_exec':
            # Can assign to self or team lead
            self.fields['assigned_to'].queryset = User.objects.filter(
                id=self.current_user.id
            )
            
        else:
            self.fields['assigned_to'].queryset = User.objects.filter(
                role='ops_exec',
                is_active=True
            )
    
    def _configure_field_access(self):
        """Configure field access based on user role"""
        user_role = self.current_user.role
        
        if user_role == 'rm':
            # RM sees assignment as auto-assigned
            self.fields['assigned_to'].help_text = "Will be auto-assigned to appropriate operations executive"
            self.fields['client'].help_text = "Select from your assigned clients"
            
        elif user_role == 'rm_head':
            self.fields['assigned_to'].help_text = "Will be auto-assigned to appropriate operations executive"
            
        elif user_role in ['ops_exec', 'ops_team_lead']:
            self.fields['client'].help_text = "Client for whom the service request is being processed"
    
    def clean(self):
        """Custom form validation"""
        cleaned_data = super().clean()
        
        client = cleaned_data.get('client')
        assigned_to = cleaned_data.get('assigned_to')
        
        # Validate client permissions
        if client and self.current_user:
            if self.current_user.role == 'rm':
                if client.user != self.current_user:
                    raise ValidationError(
                        "You can only create service requests for your own clients."
                    )
            elif self.current_user.role == 'rm_head':
                if hasattr(self.current_user, 'get_accessible_users'):
                    accessible_users = self.current_user.get_accessible_users()
                    if client.user not in accessible_users:
                        raise ValidationError(
                            "You can only create service requests for clients in your team."
                        )
        
        # Validate operations assignment
        if assigned_to:
            if not assigned_to.is_active:
                raise ValidationError("Cannot assign to inactive user.")
            
            if assigned_to.role not in ['ops_exec', 'ops_team_lead']:
                raise ValidationError(
                    "Service requests can only be assigned to operations team members."
                )
        
        return cleaned_data
    
    def save(self, commit=True):
        """Enhanced save method with additional logic"""
        instance = super().save(commit=False)
        
        # Set raised_by if creating new request
        if not instance.pk and self.current_user:
            instance.raised_by = self.current_user
        
        # Auto-assign operations executive if not set
        if not instance.assigned_to and self.current_user:
            instance.assigned_to = self._get_auto_assigned_ops_exec()
        
        # Set current owner
        if instance.assigned_to:
            instance.current_owner = instance.assigned_to
        
        # Set initial status
        if not instance.pk:
            instance.status = 'draft'
        
        if commit:
            instance.save()
            self._create_audit_trail(instance)
        
        return instance
    
    def _get_auto_assigned_ops_exec(self):
        """Auto-assign operations executive based on workload"""
        from django.db.models import Count
        
        # Get the ops executive with least workload
        ops_executives = User.objects.filter(
            role='ops_exec',
            is_active=True
        ).annotate(
            active_requests=Count(
                'assigned_service_requests',
                filter=models.Q(
                    assigned_service_requests__status__in=[
                        'submitted', 'documents_requested', 'documents_received', 'in_progress'
                    ]
                )
            )
        ).order_by('active_requests')
        
        return ops_executives.first()
    
    def _create_audit_trail(self, instance):
        """Create audit trail for the form submission"""
        if self.current_user:
            action = "created" if not self.instance.pk else "updated"
            
            ServiceRequestComment.objects.create(
                service_request=instance,
                comment=f"Service request {action} by {self.current_user.get_full_name() or self.current_user.username}",
                commented_by=self.current_user,
                is_internal=True
            )


# Additional form for admin interface to match your image
class ServiceRequestAdminForm(forms.ModelForm):
    """Admin form with all fields visible like in your image"""
    
    class Meta:
        model = ServiceRequest
        fields = '__all__'
        widgets = {
            'description': forms.Textarea(attrs={'rows': 4}),
            'resolution_summary': forms.Textarea(attrs={'rows': 4}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Make some fields readonly in admin
        if self.instance.pk:
            self.fields['request_id'].widget.attrs['readonly'] = True
            self.fields['created_at'].widget.attrs['readonly'] = True
            self.fields['updated_at'].widget.attrs['readonly'] = True


# Simple form for quick actions
class ServiceRequestActionForm(forms.Form):
    """Form for workflow actions"""
    action = forms.ChoiceField(choices=[])
    comments = forms.CharField(
        widget=forms.Textarea(attrs={'rows': 3}),
        required=False,
        help_text="Optional comments about this action"
    )
    
    def __init__(self, *args, **kwargs):
        available_actions = kwargs.pop('available_actions', [])
        super().__init__(*args, **kwargs)
        
        action_choices = [
            ('submit', 'Submit Request'),
            ('request_documents', 'Request Documents'),
            ('start_processing', 'Start Processing'),
            ('resolve', 'Resolve Request'),
            ('verify', 'Verify Resolution'),
            ('close', 'Close Request'),
        ]
        
        # Filter choices based on available actions
        self.fields['action'].choices = [
            (value, label) for value, label in action_choices 
            if value in available_actions
        ]


# Document upload form
class ServiceRequestDocumentForm(forms.ModelForm):
    """Form for uploading documents"""
    
    class Meta:
        model = ServiceRequestDocument
        fields = ['document', 'document_name']
        widgets = {
            'document': forms.ClearableFileInput(attrs={
                'accept': '.pdf,.jpg,.jpeg,.png,.doc,.docx,.xls,.xlsx'
            }),
        }
    
    def clean_document(self):
        document = self.cleaned_data.get('document')
        
        if document:
            # Check file size (10MB limit)
            if document.size > 10 * 1024 * 1024:
                raise ValidationError("File size cannot exceed 10MB.")
            
            # Check file type
            allowed_extensions = ['.pdf', '.jpg', '.jpeg', '.png', '.doc', '.docx', '.xls', '.xlsx']
            file_extension = '.' + document.name.split('.')[-1].lower()
            
            if file_extension not in allowed_extensions:
                raise ValidationError(
                    f"File type not supported. Allowed types: {', '.join(allowed_extensions)}"
                )
        
        return document
    
    def save(self, commit=True):
        instance = super().save(commit=False)
        
        # Set document name from file if not provided
        if not instance.document_name and instance.document:
            instance.document_name = instance.document.name
        
        if commit:
            instance.save()
        
        return instance


# Updated Lead Form with operations awareness
class LeadForm(forms.ModelForm):
    """Enhanced lead form with operations context"""
    
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
            
            if self.current_user.role in ['top_management', 'business_head', 'business_head_ops']:
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
                # Default: show all users with relevant roles (excluding operations-only roles for leads)
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


# Additional Lead Management Forms
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
                lead=self.lead,
                created_by=self.user
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


# Client and Investment Forms
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
            if self.current_user.role in ['top_management', 'business_head', 'business_head_ops']:
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




# Additional Operations Forms
class ConvertToClientForm(forms.ModelForm):
    """Form for converting client profile to full client"""
    
    class Meta:
        model = Client
        fields = ['aum', 'sip_amount', 'demat_count', 'contact_info']
        widgets = {
            'aum': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter AUM amount',
                'step': '0.01'
            }),
            'sip_amount': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter SIP amount',
                'step': '0.01'
            }),
            'demat_count': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': 'Number of demat accounts',
                'min': '0'
            }),
            'contact_info': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Additional contact information'
            })
        }
        labels = {
            'aum': 'Assets Under Management (AUM)',
            'sip_amount': 'SIP Amount',
            'demat_count': 'Number of Demat Accounts',
            'contact_info': 'Additional Contact Information'
        }


# Account Management Forms
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


# Search and Filter Forms
class ClientSearchForm(forms.Form):
    """Form for searching clients with operations support"""
    
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
    from django import forms
from django.contrib.auth.forms import UserCreationForm, UserChangeForm
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.db.models import Q
from django.core.validators import FileExtensionValidator
from .models import (
    User, Lead, Client, Task, ServiceRequest,
    Team, BusinessTracker, LeadInteraction, ProductDiscussion, 
    LeadStatusChange, TeamMembership, Reminder, ClientProfile,
    ClientProfileModification, MFUCANAccount, Note, NoteList
)

# Updated Constants with new operations roles
ROLE_CHOICES = (
    ('top_management', 'Top Management'),
    ('business_head', 'Business Head'),
    ('business_head_ops', 'Business Head - Ops'),  # New role
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

# Notes System Forms
class NoteListForm(forms.ModelForm):
    """Form for creating and updating note lists"""
    
    class Meta:
        model = NoteList
        fields = ['name', 'description']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter list name',
                'maxlength': 100
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'placeholder': 'Optional description for this list',
                'rows': 3
            })
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['name'].required = True
        self.fields['description'].required = False

    def clean_name(self):
        """Validate list name uniqueness per user"""
        name = self.cleaned_data.get('name')
        if name:
            # This validation will be handled at the view level since we need user context
            return name.strip()
        return name


class NoteForm(forms.ModelForm):
    """Form for creating and updating notes"""
    
    class Meta:
        model = Note
        fields = [
            'note_list', 'heading', 'content', 'creation_date', 
            'reminder_date', 'due_date', 'attachment'
        ]
        widgets = {
            'note_list': forms.Select(attrs={
                'class': 'form-control',
                'required': True
            }),
            'heading': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter note heading',
                'maxlength': 200,
                'required': True
            }),
            'content': forms.Textarea(attrs={
                'class': 'form-control',
                'placeholder': 'Enter note content...',
                'rows': 6,
                'required': True
            }),
            'creation_date': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date',
                'readonly': 'readonly'
            }),
            'reminder_date': forms.DateTimeInput(attrs={
                'class': 'form-control',
                'type': 'datetime-local',
                'placeholder': 'Select reminder date and time'
            }),
            'due_date': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date',
                'placeholder': 'Select due date'
            }),
            'attachment': forms.FileInput(attrs={
                'class': 'form-control',
                'accept': '.pdf,.doc,.docx,.txt,.jpg,.jpeg,.png,.xlsx,.xls'
            })
        }
        labels = {
            'note_list': 'List',
            'heading': 'Note Heading',
            'content': 'Note Content',
            'creation_date': 'Creation Date',
            'reminder_date': 'Reminder Date & Time',
            'due_date': 'Due Date',
            'attachment': 'Attach File (Max 500KB)'
        }
    
    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        
        # Set creation date to today by default
        if not self.instance.pk:
            self.fields['creation_date'].initial = timezone.now().date()
        
        # Filter note_list to only show current user's lists
        if self.user:
            self.fields['note_list'].queryset = NoteList.objects.filter(user=self.user)
            
            # If user has no lists, create a default one
            if not self.fields['note_list'].queryset.exists():
                default_list = NoteList.objects.create(
                    user=self.user,
                    name='General',
                    description='Default note list'
                )
                self.fields['note_list'].queryset = NoteList.objects.filter(user=self.user)
                self.fields['note_list'].initial = default_list
        
        # Make fields optional except required ones
        self.fields['reminder_date'].required = False
        self.fields['due_date'].required = False
        self.fields['attachment'].required = False
    
    def clean_attachment(self):
        """Validate file size (500KB limit)"""
        attachment = self.cleaned_data.get('attachment')
        if attachment:
            if attachment.size > 500 * 1024:  # 500KB in bytes
                raise ValidationError("File size cannot exceed 500KB. Please choose a smaller file.")
        return attachment
    
    def clean_reminder_date(self):
        """Validate reminder date is in the future"""
        reminder_date = self.cleaned_data.get('reminder_date')
        if reminder_date and reminder_date <= timezone.now():
            raise ValidationError("Reminder date must be in the future.")
        return reminder_date
    
    def clean_due_date(self):
        """Validate due date"""
        due_date = self.cleaned_data.get('due_date')
        creation_date = self.cleaned_data.get('creation_date')
        
        if due_date and creation_date and due_date < creation_date:
            raise ValidationError("Due date cannot be before creation date.")
        
        return due_date
    
    def clean(self):
        """Cross-field validation"""
        cleaned_data = super().clean()
        reminder_date = cleaned_data.get('reminder_date')
        due_date = cleaned_data.get('due_date')
        
        # If both reminder and due date are provided, reminder should be before due date
        if reminder_date and due_date:
            if reminder_date.date() > due_date:
                raise ValidationError("Reminder date cannot be after due date.")
        
        return cleaned_data


class QuickNoteForm(forms.ModelForm):
    """Simplified form for quick note creation"""
    
    class Meta:
        model = Note
        fields = ['note_list', 'heading', 'content']
        widgets = {
            'note_list': forms.Select(attrs={
                'class': 'form-control form-control-sm',
            }),
            'heading': forms.TextInput(attrs={
                'class': 'form-control form-control-sm',
                'placeholder': 'Quick note heading...',
            }),
            'content': forms.Textarea(attrs={
                'class': 'form-control form-control-sm',
                'placeholder': 'Quick note content...',
                'rows': 3
            })
        }
    
    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        
        # Filter note_list to only show current user's lists
        if self.user:
            self.fields['note_list'].queryset = NoteList.objects.filter(user=self.user)
            
            # Set default list if exists
            default_list = self.fields['note_list'].queryset.first()
            if default_list:
                self.fields['note_list'].initial = default_list
    
    def save(self, commit=True):
        """Save quick note with default values"""
        note = super().save(commit=False)
        note.user = self.user
        note.creation_date = timezone.now().date()
        
        if commit:
            note.save()
        return note


# Updated User Management Forms
class CustomUserCreationForm(UserCreationForm):
    """Custom user creation form with updated hierarchy validation"""
    
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
        
        # Updated role choices including operations roles
        self.fields['role'].choices = ROLE_CHOICES
        
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
            elif self.current_user.role == 'business_head_ops':
                # Business Head - Ops can create operations roles
                self.fields['role'].choices = [
                    ('ops_team_lead', 'Operations Team Lead'),
                    ('ops_exec', 'Operations Executive'),
                ]
                self.fields['manager'].queryset = User.objects.filter(
                    role__in=['business_head_ops', 'business_head', 'top_management']
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
        
        # Updated hierarchy validation rules
        if role == 'top_management' and manager:
            raise ValidationError("Top Management cannot have a manager")
        elif role == 'business_head' and manager and manager.role != 'top_management':
            raise ValidationError("Business Head can only report to Top Management")
        elif role == 'business_head_ops' and manager and manager.role not in ['top_management', 'business_head']:
            raise ValidationError("Business Head - Ops can only report to Top Management or Business Head")
        elif role == 'rm_head' and manager and manager.role not in ['business_head', 'top_management']:
            raise ValidationError("RM Head can only report to Business Head or Top Management")
        elif role == 'rm' and manager and manager.role not in ['rm_head', 'business_head']:
            raise ValidationError("RM can only report to RM Head or Business Head")
        elif role == 'ops_team_lead' and manager and manager.role not in ['business_head_ops', 'business_head', 'top_management']:
            raise ValidationError("Ops Team Lead can only report to Business Head - Ops, Business Head, or Top Management")
        elif role == 'ops_exec' and manager and manager.role != 'ops_team_lead':
            raise ValidationError("Ops Exec can only report to Ops Team Lead")
            
        return cleaned_data


class CustomUserChangeForm(UserChangeForm):
    """Custom user change form with updated roles"""
    
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
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['role'].choices = ROLE_CHOICES


class TeamForm(forms.ModelForm):
    """Form for creating/editing teams with operations support"""
    
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
        # Include operations team leads as possible leaders
        self.fields['leader'].queryset = User.objects.filter(
            role__in=['rm_head', 'ops_team_lead'], 
            is_active=True
        )
        self.fields['leader'].empty_label = "Select Team Leader"


class TeamMembershipForm(forms.ModelForm):
    """Form for managing team memberships with operations support"""
    
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


# Updated Client Profile Form
class ClientProfileForm(forms.ModelForm):
    """Enhanced form for creating/editing client profiles with operations support"""
    
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
        # Handle both current_user and user parameters for backward compatibility
        self.current_user = kwargs.pop('current_user', None)
        if not self.current_user:
            self.current_user = kwargs.pop('user', None)
        
        super().__init__(*args, **kwargs)
        
        # Set querysets for mapped users
        if 'mapped_rm' in self.fields:
            self.fields['mapped_rm'].queryset = User.objects.filter(role='rm', is_active=True)
            
        if 'mapped_ops_exec' in self.fields:
            self.fields['mapped_ops_exec'].queryset = User.objects.filter(role='ops_exec', is_active=True)

        # Apply role-based restrictions
        if self.current_user:
            self._apply_role_restrictions()

    def _apply_role_restrictions(self):
        """Apply field restrictions based on user role including operations roles"""
        user_role = self.current_user.role
        
        if user_role == 'rm_head':
            # RM heads can only assign RMs under their hierarchy
            if hasattr(self.current_user, 'get_accessible_users'):
                try:
                    accessible_users = self.current_user.get_accessible_users()
                    accessible_rm_ids = [u.id for u in accessible_users if u.role == 'rm']
                    
                    if accessible_rm_ids:
                        self.fields['mapped_rm'].queryset = User.objects.filter(
                            id__in=accessible_rm_ids,
                            is_active=True
                        )
                    else:
                        # Fallback to all RMs
                        self.fields['mapped_rm'].queryset = User.objects.filter(
                            role='rm',
                            is_active=True
                        )
                except Exception:
                    # Fallback to all RMs
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
            self.fields['mapped_rm'].disabled = True
            if 'mapped_ops_exec' in self.fields:
                self.fields['mapped_ops_exec'].disabled = True
                
        elif user_role in ['business_head', 'business_head_ops', 'top_management']:
            # Senior management can assign to any RM
            self.fields['mapped_rm'].queryset = User.objects.filter(
                role='rm', 
                is_active=True
            )
            
        elif user_role == 'ops_team_lead':
            # Ops Team Lead can assign ops executives from their team
            if hasattr(self.current_user, 'get_team_members'):
                team_members = self.current_user.get_team_members()
                self.fields['mapped_ops_exec'].queryset = User.objects.filter(
                    id__in=[tm.id for tm in team_members],
                    is_active=True
                )
            # Can't change RM mapping
            if 'mapped_rm' in self.fields:
                self.fields['mapped_rm'].disabled = True
                
        elif user_role == 'ops_exec':
            # Ops Exec can only assign to themselves
            self.fields['mapped_ops_exec'].queryset = User.objects.filter(id=self.current_user.id)
            self.fields['mapped_ops_exec'].initial = self.current_user
            self.fields['mapped_ops_exec'].disabled = True
            # Can't change RM mapping
            if 'mapped_rm' in self.fields:
                self.fields['mapped_rm'].disabled = True
        
        # Status field restrictions - updated for operations roles
        if user_role not in ['ops_team_lead', 'business_head', 'business_head_ops', 'top_management', 'rm_head']:
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


# Updated Task Form with operations support
class TaskForm(forms.ModelForm):
    """Enhanced task form with operations roles support"""
    
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
            if self.current_user.role in ['top_management', 'business_head', 'business_head_ops']:
                # Senior management can assign to anyone
                self.fields['assigned_to'].queryset = User.objects.filter(is_active=True)
            elif self.current_user.role == 'rm_head':
                # Can assign to team members or self
                accessible_users = self.current_user.get_accessible_users()
                self.fields['assigned_to'].queryset = accessible_users
            elif self.current_user.role == 'ops_team_lead':
                # Can assign to operations team members
                team_members = self.current_user.get_team_members()
                self.fields['assigned_to'].queryset = User.objects.filter(
                    id__in=[self.current_user.id] + [tm.id for tm in team_members]
                )
            else:  # RM, Ops Exec
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


# Updated Service Request Form

            
            
class OperationsTaskAssignmentForm(forms.ModelForm):
   """Specialized form for operations task assignment"""
   
   class Meta:
       model = Task
       fields = ['title', 'description', 'assigned_to', 'due_date', 'priority']
       widgets = {
           'title': forms.TextInput(attrs={
               'class': 'form-control',
               'placeholder': 'Enter task title',
               'required': True
           }),
           'description': forms.Textarea(attrs={
               'class': 'form-control',
               'rows': 4,
               'placeholder': 'Describe the task details...'
           }),
           'assigned_to': forms.Select(attrs={
               'class': 'form-control',
               'required': True
           }),
           'due_date': forms.DateTimeInput(attrs={
               'type': 'datetime-local',
               'class': 'form-control'
           }),
           'priority': forms.Select(attrs={
               'class': 'form-control'
           }),
       }
       labels = {
           'title': 'Task Title',
           'description': 'Task Description',
           'assigned_to': 'Assign To',
           'due_date': 'Due Date & Time',
           'priority': 'Priority Level'
       }
   
   def __init__(self, *args, **kwargs):
       self.current_user = kwargs.pop('current_user', None)
       super().__init__(*args, **kwargs)
       
       # Set default due date to 24 hours from now
       if not self.instance.pk:
           default_due = timezone.now() + timezone.timedelta(hours=24)
           self.fields['due_date'].initial = default_due.strftime('%Y-%m-%dT%H:%M')
       
       # Limit assigned_to to operations team members based on current user's role
       if self.current_user:
           if self.current_user.role == 'business_head_ops':
               # Can assign to all operations team
               self.fields['assigned_to'].queryset = User.objects.filter(
                   role__in=['ops_team_lead', 'ops_exec'],
                   is_active=True
               ).order_by('first_name', 'last_name')
               
           elif self.current_user.role == 'ops_team_lead':
               # Can assign to team members and self
               team_members = self.current_user.get_team_members()
               assignable_users = User.objects.filter(
                   id__in=[self.current_user.id] + [tm.id for tm in team_members],
                   is_active=True
               ).order_by('first_name', 'last_name')
               self.fields['assigned_to'].queryset = assignable_users
               
           else:
               # Default to operations roles for other users
               self.fields['assigned_to'].queryset = User.objects.filter(
                   role__in=['ops_exec', 'ops_team_lead'],
                   is_active=True
               ).order_by('first_name', 'last_name')
       else:
           # Fallback if no current user
           self.fields['assigned_to'].queryset = User.objects.filter(
               role__in=['ops_exec', 'ops_team_lead'],
               is_active=True
           ).order_by('first_name', 'last_name')
       
       # Enhance the display of users in dropdown
       self.fields['assigned_to'].label_from_instance = lambda obj: f"{obj.get_full_name()} ({obj.get_role_display()})" if obj.get_full_name() else f"{obj.username} ({obj.get_role_display()})"
       
       # Make description optional
       self.fields['description'].required = False
       self.fields['due_date'].required = False
   
   def clean_due_date(self):
       """Validate due date is in the future"""
       due_date = self.cleaned_data.get('due_date')
       if due_date and due_date <= timezone.now():
           raise forms.ValidationError("Due date must be in the future.")
       return due_date
   
   def clean_assigned_to(self):
       """Validate assigned user is from operations team"""
       assigned_to = self.cleaned_data.get('assigned_to')
       if assigned_to and assigned_to.role not in ['ops_team_lead', 'ops_exec']:
           raise forms.ValidationError("Tasks can only be assigned to operations team members.")
       return assigned_to
   
   def save(self, commit=True):
       """Save task with assigned_by field"""
       task = super().save(commit=False)
       
       if self.current_user:
           task.assigned_by = self.current_user
       
       # Set default priority if not specified
       if not task.priority:
           task.priority = 'medium'
       
       if commit:
           task.save()
       
       return task
   
class UserEditForm(forms.ModelForm):
   """Form for editing user profiles with operations support"""
   
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
       
       # Set role choices
       self.fields['role'].choices = ROLE_CHOICES
       
       # Configure manager choices based on role
       if self.instance and self.instance.role:
           if self.instance.role == 'top_management':
               self.fields['manager'].queryset = User.objects.none()
           elif self.instance.role == 'business_head':
               self.fields['manager'].queryset = User.objects.filter(role='top_management')
           elif self.instance.role == 'business_head_ops':
               self.fields['manager'].queryset = User.objects.filter(role__in=['top_management', 'business_head'])
           elif self.instance.role == 'rm_head':
               self.fields['manager'].queryset = User.objects.filter(role__in=['business_head', 'top_management'])
           elif self.instance.role == 'rm':
               self.fields['manager'].queryset = User.objects.filter(role__in=['rm_head', 'business_head'])
           elif self.instance.role == 'ops_team_lead':
               self.fields['manager'].queryset = User.objects.filter(role__in=['business_head_ops', 'business_head', 'top_management'])
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
           
# forms.py
from django import forms
from django.utils import timezone
from django.core.exceptions import ValidationError
from .models import ClientInteraction, INTERACTION_TYPE_CHOICES


class ClientInteractionForm(forms.ModelForm):
    """Form for creating and updating client interactions"""
    
    class Meta:
        model = ClientInteraction
        fields = [
            'interaction_type', 'interaction_date', 'duration_minutes',
            'notes', 'priority', 'follow_up_required', 'follow_up_date'
        ]
        widgets = {
            'interaction_type': forms.Select(
                attrs={
                    'class': 'form-select',
                    'id': 'id_interaction_type'
                }
            ),
            'interaction_date': forms.DateTimeInput(
                attrs={
                    'type': 'datetime-local',
                    'class': 'form-control',
                    'id': 'id_interaction_date'
                }
            ),
            'duration_minutes': forms.NumberInput(
                attrs={
                    'class': 'form-control',
                    'placeholder': 'Enter duration in minutes',
                    'min': '1',
                    'max': '480',  # 8 hours max
                    'id': 'id_duration_minutes'
                }
            ),
            'notes': forms.Textarea(
                attrs={
                    'class': 'form-control',
                    'rows': 6,
                    'placeholder': 'Enter detailed notes about the interaction...',
                    'id': 'id_notes'
                }
            ),
            'priority': forms.Select(
                attrs={
                    'class': 'form-select',
                    'id': 'id_priority'
                }
            ),
            'follow_up_required': forms.CheckboxInput(
                attrs={
                    'class': 'form-check-input',
                    'id': 'id_follow_up_required'
                }
            ),
            'follow_up_date': forms.DateInput(
                attrs={
                    'type': 'date',
                    'class': 'form-control',
                    'id': 'id_follow_up_date'
                }
            ),
        }
        help_texts = {
            'duration_minutes': 'Optional: How long did the interaction last?',
            'notes': 'Provide detailed information about what was discussed',
            'follow_up_date': 'Required if follow-up is marked as needed',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Set default interaction_date to now if creating new interaction
        if not self.instance.pk:
            self.fields['interaction_date'].initial = timezone.now()
        
        # Make notes field required
        self.fields['notes'].required = True
        
        # Set up conditional follow_up_date requirement
        self.fields['follow_up_date'].required = False

    def clean_interaction_date(self):
        """Validate interaction date"""
        interaction_date = self.cleaned_data.get('interaction_date')
        
        if interaction_date:
            # Don't allow future dates beyond 24 hours
            if interaction_date > timezone.now() + timezone.timedelta(hours=24):
                raise ValidationError(
                    "Interaction date cannot be more than 24 hours in the future."
                )
            
            # Don't allow dates too far in the past (1 year)
            if interaction_date < timezone.now() - timezone.timedelta(days=365):
                raise ValidationError(
                    "Interaction date cannot be more than 1 year in the past."
                )
        
        return interaction_date

    def clean_duration_minutes(self):
        """Validate duration"""
        duration = self.cleaned_data.get('duration_minutes')
        
        if duration is not None:
            if duration < 1:
                raise ValidationError("Duration must be at least 1 minute.")
            if duration > 480:  # 8 hours
                raise ValidationError("Duration cannot exceed 8 hours (480 minutes).")
        
        return duration

    def clean_follow_up_date(self):
        """Validate follow-up date"""
        follow_up_date = self.cleaned_data.get('follow_up_date')
        follow_up_required = self.cleaned_data.get('follow_up_required')
        
        if follow_up_required and not follow_up_date:
            raise ValidationError("Follow-up date is required when follow-up is marked as needed.")
        
        if follow_up_date:
            if follow_up_date <= timezone.now().date():
                raise ValidationError("Follow-up date must be in the future.")
            
            # Don't allow follow-up dates more than 1 year in future
            if follow_up_date > timezone.now().date() + timezone.timedelta(days=365):
                raise ValidationError("Follow-up date cannot be more than 1 year in the future.")
        
        return follow_up_date

    def clean_notes(self):
        """Validate notes field"""
        notes = self.cleaned_data.get('notes')
        
        if notes:
            # Remove extra whitespace
            notes = notes.strip()
            
            # Minimum length check
            if len(notes) < 10:
                raise ValidationError("Notes must be at least 10 characters long.")
            
            # Maximum length check
            if len(notes) > 2000:
                raise ValidationError("Notes cannot exceed 2000 characters.")
        
        return notes

    def clean(self):
        """Cross-field validation"""
        cleaned_data = super().clean()
        follow_up_required = cleaned_data.get('follow_up_required')
        follow_up_date = cleaned_data.get('follow_up_date')
        interaction_date = cleaned_data.get('interaction_date')
        
        # Ensure follow-up date is after interaction date
        if follow_up_date and interaction_date:
            if follow_up_date <= interaction_date.date():
                raise ValidationError({
                    'follow_up_date': 'Follow-up date must be after the interaction date.'
                })
        
        # Clear follow_up_date if not required
        if not follow_up_required:
            cleaned_data['follow_up_date'] = None
        
        return cleaned_data


class InteractionFilterForm(forms.Form):
    """Form for filtering interactions in the list view"""
    
    PRIORITY_CHOICES = [
        ('', 'All Priorities'),
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
        ('urgent', 'Urgent'),
    ]
    
    FOLLOW_UP_CHOICES = [
        ('', 'All'),
        ('yes', 'Follow-up Required'),
        ('no', 'No Follow-up'),
    ]
    
    search = forms.CharField(
        required=False,
        widget=forms.TextInput(
            attrs={
                'class': 'form-control',
                'placeholder': 'Search in notes or interaction type...',
            }
        )
    )
    
    interaction_type = forms.ChoiceField(
        choices=[('', 'All Types')] + INTERACTION_TYPE_CHOICES,
        required=False,
        widget=forms.Select(
            attrs={'class': 'form-select'}
        )
    )
    
    priority = forms.ChoiceField(
        choices=PRIORITY_CHOICES,
        required=False,
        widget=forms.Select(
            attrs={'class': 'form-select'}
        )
    )
    
    follow_up_required = forms.ChoiceField(
        choices=FOLLOW_UP_CHOICES,
        required=False,
        widget=forms.Select(
            attrs={'class': 'form-select'}
        )
    )
    
    date_from = forms.DateField(
        required=False,
        widget=forms.DateInput(
            attrs={
                'type': 'date',
                'class': 'form-control'
            }
        )
    )
    
    date_to = forms.DateField(
        required=False,
        widget=forms.DateInput(
            attrs={
                'type': 'date',
                'class': 'form-control'
            }
        )
    )

    def clean(self):
        """Validate date range"""
        cleaned_data = super().clean()
        date_from = cleaned_data.get('date_from')
        date_to = cleaned_data.get('date_to')
        
        if date_from and date_to:
            if date_from > date_to:
                raise ValidationError("Start date must be before end date.")
        
        return cleaned_data


class BulkInteractionActionForm(forms.Form):
    """Form for bulk actions on interactions"""
    
    ACTION_CHOICES = [
        ('mark_follow_up', 'Mark as requiring follow-up'),
        ('unmark_follow_up', 'Remove follow-up requirement'),
        ('change_priority', 'Change priority'),
    ]
    
    action = forms.ChoiceField(
        choices=ACTION_CHOICES,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    new_priority = forms.ChoiceField(
        choices=[
            ('low', 'Low'),
            ('medium', 'Medium'),
            ('high', 'High'),
            ('urgent', 'Urgent'),
        ],
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    interaction_ids = forms.CharField(
        widget=forms.HiddenInput()
    )

    def clean(self):
        cleaned_data = super().clean()
        action = cleaned_data.get('action')
        new_priority = cleaned_data.get('new_priority')
        
        if action == 'change_priority' and not new_priority:
            raise ValidationError("Priority is required when changing priority.")
        
        return cleaned_data
    
    
# execution_plans/forms.py
from django import forms
from django.core.exceptions import ValidationError
from decimal import Decimal
from .models import ExecutionPlan, PlanAction, PlanComment


class PlanApprovalForm(forms.Form):
    """Form for approving/rejecting plans"""
    
    ACTION_CHOICES = [
        ('approve', 'Approve'),
        ('reject', 'Reject')
    ]
    
    action = forms.ChoiceField(
        choices=ACTION_CHOICES,
        widget=forms.RadioSelect(attrs={
            'class': 'form-check-input'
        }),
        required=True
    )
    
    comments = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 3,
            'placeholder': 'Add comments (required for rejection)'
        })
    )
    
    def clean(self):
        cleaned_data = super().clean()
        action = cleaned_data.get('action')
        comments = cleaned_data.get('comments', '').strip()
        
        if action == 'reject' and not comments:
            raise ValidationError("Comments are required when rejecting a plan.")
        
        return cleaned_data


class PlanCommentForm(forms.ModelForm):
    """Form for adding comments to plans"""
    
    class Meta:
        model = PlanComment
        fields = ['comment', 'is_internal']
        widgets = {
            'comment': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Enter your comment...',
                'required': True
            }),
            'is_internal': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            })
        }
    
    def clean_comment(self):
        comment = self.cleaned_data.get('comment', '').strip()
        if len(comment) < 5:
            raise ValidationError("Comment must be at least 5 characters long.")
        return comment


class ActionExecutionForm(forms.Form):
    """Form for executing plan actions"""
    
    transaction_id = forms.CharField(
        required=False,
        max_length=100,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Transaction ID (optional)'
        })
    )
    
    executed_amount = forms.DecimalField(
        required=False,
        max_digits=15,
        decimal_places=2,
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'placeholder': 'Executed amount',
            'step': '0.01'
        })
    )
    
    executed_units = forms.DecimalField(
        required=False,
        max_digits=15,
        decimal_places=4,
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'placeholder': 'Executed units',
            'step': '0.0001'
        })
    )
    
    nav_price = forms.DecimalField(
        required=False,
        max_digits=10,
        decimal_places=4,
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'placeholder': 'NAV price',
            'step': '0.0001'
        })
    )
    
    notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 2,
            'placeholder': 'Execution notes (optional)'
        })
    )
    
    def clean(self):
        cleaned_data = super().clean()
        executed_amount = cleaned_data.get('executed_amount')
        executed_units = cleaned_data.get('executed_units')
        
        if not executed_amount and not executed_units:
            raise ValidationError("Either executed amount or executed units must be provided.")
        
        return cleaned_data


class ActionFailureForm(forms.Form):
    """Form for marking actions as failed"""
    
    reason = forms.CharField(
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 3,
            'placeholder': 'Enter reason for failure...',
            'required': True
        })
    )
    
    def clean_reason(self):
        reason = self.cleaned_data.get('reason', '').strip()
        if len(reason) < 10:
            raise ValidationError("Failure reason must be at least 10 characters long.")
        return reason


class ClientSelectionForm(forms.Form):
    """Form for selecting client in plan creation"""
    
    client = forms.ModelChoiceField(
        queryset=Client.objects.none(),
        widget=forms.Select(attrs={
            'class': 'form-control',
            'required': True
        }),
        empty_label="Select a client..."
    )
    
    def __init__(self, *args, current_user=None, **kwargs):
        super().__init__(*args, **kwargs)
        
        if current_user:
            # Filter clients based on user role
            if current_user.role == 'rm':
                self.fields['client'].queryset = Client.objects.filter(user=current_user)
            elif current_user.role == 'rm_head':
                team_rms = User.objects.filter(manager=current_user, role='rm')
                self.fields['client'].queryset = Client.objects.filter(user__in=team_rms)
            elif current_user.role in ['business_head', 'top_management']:
                self.fields['client'].queryset = Client.objects.all()


class PlanFilterForm(forms.Form):
    """Form for filtering execution plans"""
    
    STATUS_CHOICES = [
        ('', 'All Statuses'),
        ('draft', 'Draft'),
        ('pending_approval', 'Pending Approval'),
        ('approved', 'Approved'),
        ('client_approved', 'Client Approved'),
        ('in_execution', 'In Execution'),
        ('completed', 'Completed'),
        ('rejected', 'Rejected'),
    ]
    
    status = forms.ChoiceField(
        choices=STATUS_CHOICES,
        required=False,
        widget=forms.Select(attrs={
            'class': 'form-control'
        })
    )
    
    search = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Search by plan name, client name, or plan ID...'
        })
    )
    
    date_from = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={
            'class': 'form-control',
            'type': 'date'
        })
    )
    
    date_to = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={
            'class': 'form-control',
            'type': 'date'
        })
    )
    
    

class PortfolioUploadForm(forms.ModelForm):
    """Form for uploading portfolio Excel files"""
    
    process_immediately = forms.BooleanField(
        required=False,
        initial=True,
        help_text="Process the file immediately after upload",
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'})
    )
    
    validate_data = forms.BooleanField(
        required=False,
        initial=True,
        help_text="Validate data before processing",
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'})
    )
    
    class Meta:
        model = PortfolioUpload
        fields = ['file']
        widgets = {
            'file': forms.FileInput(attrs={
                'accept': '.xlsx,.xls',
                'class': 'form-control',
                'id': 'portfolio-file-input'
            })
        }
        labels = {
            'file': 'Portfolio Excel File'
        }
        help_texts = {
            'file': 'Upload an Excel file (.xlsx or .xls) containing portfolio data. Maximum file size: 25MB.'
        }
    
    def clean_file(self):
        file = self.cleaned_data['file']
        
        # Check if file is provided
        if not file:
            raise ValidationError("Please select a file to upload.")
        
        # Check file extension
        if not file.name.lower().endswith(('.xlsx', '.xls')):
            raise ValidationError("Please upload an Excel file (.xlsx or .xls)")
        
        # Check file size (max 25MB)
        max_size = 25 * 1024 * 1024  # 25MB in bytes
        if file.size > max_size:
            raise ValidationError(f"File size cannot exceed 25MB. Your file is {file.size / (1024*1024):.1f}MB")
        
        # Validate file content if requested
        if self.cleaned_data.get('validate_data', True):
            try:
                # Try to read the file
                df = pd.read_excel(file)
                
                # Check if file has data
                if df.empty:
                    raise ValidationError("The Excel file appears to be empty")
                
                # Check for required columns
                required_columns = ['CLIENT', 'CLIENT PAN', 'SCHEME', 'TOTAL']
                missing_columns = []
                
                # Clean column names for comparison
                df_columns = [col.strip() for col in df.columns]
                
                for col in required_columns:
                    # Check exact match and variations with spaces
                    if (col not in df_columns and 
                        f' {col}' not in df_columns and 
                        f'{col} ' not in df_columns):
                        missing_columns.append(col)
                
                if missing_columns:
                    available_cols = ', '.join(df_columns[:10])  # Show first 10 columns
                    if len(df_columns) > 10:
                        available_cols += f" ... and {len(df_columns) - 10} more"
                    
                    raise ValidationError(
                        f"Missing required columns: {', '.join(missing_columns)}. "
                        f"Available columns: {available_cols}"
                    )
                
                # Check for minimum data
                if len(df) < 1:
                    raise ValidationError("File must contain at least one data row")
                
                # Reset file pointer for later use
                file.seek(0)
                
            except pd.errors.ExcelFileError:
                raise ValidationError("Invalid Excel file format. Please ensure the file is a valid Excel file.")
            except Exception as e:
                if "Missing required columns" in str(e) or "File must contain" in str(e):
                    raise  # Re-raise our custom validation errors
                raise ValidationError(f"Error validating file: {str(e)}")
        
        return file
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Add CSS classes and attributes
        for field_name, field in self.fields.items():
            if field_name != 'file':
                field.widget.attrs.update({'class': 'form-control'})
                
                
# forms.py - Add these forms to your existing forms.py

from django import forms
from django.core.exceptions import ValidationError
from .models import PortfolioActionPlan, PortfolioAction, ClientPortfolio
from decimal import Decimal

class PortfolioActionPlanForm(forms.ModelForm):
    """Form for creating portfolio action plans"""
    
    class Meta:
        model = PortfolioActionPlan
        fields = ['plan_name', 'description', 'notes']
        widgets = {
            'plan_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter a name for this action plan'
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Optional description of the action plan'
            }),
            'notes': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Any additional notes or instructions'
            })
        }

class PortfolioActionForm(forms.ModelForm):
    """Dynamic form for portfolio actions"""
    
    class Meta:
        model = PortfolioAction
        fields = [
            'action_type', 'priority', 'source_scheme', 'target_scheme',
            'redeem_by', 'redeem_amount', 'redeem_units',
            'switch_by', 'switch_amount', 'switch_units',
            'stp_amount', 'stp_frequency',
            'sip_amount', 'sip_frequency', 'sip_date',
            'swp_amount', 'swp_frequency', 'swp_date'
        ]
        widgets = {
            'action_type': forms.Select(attrs={'class': 'form-control action-type-selector'}),
            'priority': forms.NumberInput(attrs={'class': 'form-control', 'min': 1}),
            'source_scheme': forms.TextInput(attrs={'class': 'form-control', 'readonly': True}),
            'target_scheme': forms.TextInput(attrs={'class': 'form-control'}),
            
            # Redeem fields
            'redeem_by': forms.Select(attrs={'class': 'form-control redeem-method'}),
            'redeem_amount': forms.NumberInput(attrs={
                'class': 'form-control', 
                'step': '0.01', 
                'placeholder': 'Enter amount'
            }),
            'redeem_units': forms.NumberInput(attrs={
                'class': 'form-control', 
                'step': '0.0001', 
                'placeholder': 'Enter units'
            }),
            
            # Switch fields
            'switch_by': forms.Select(attrs={'class': 'form-control switch-method'}),
            'switch_amount': forms.NumberInput(attrs={
                'class': 'form-control', 
                'step': '0.01', 
                'placeholder': 'Enter amount'
            }),
            'switch_units': forms.NumberInput(attrs={
                'class': 'form-control', 
                'step': '0.0001', 
                'placeholder': 'Enter units'
            }),
            
            # STP fields
            'stp_amount': forms.NumberInput(attrs={
                'class': 'form-control', 
                'step': '0.01', 
                'placeholder': 'Enter transfer amount'
            }),
            'stp_frequency': forms.Select(attrs={'class': 'form-control'}),
            
            # SIP fields
            'sip_amount': forms.NumberInput(attrs={
                'class': 'form-control', 
                'step': '0.01', 
                'placeholder': 'Enter SIP amount'
            }),
            'sip_frequency': forms.Select(attrs={'class': 'form-control'}),
            'sip_date': forms.NumberInput(attrs={
                'class': 'form-control', 
                'min': 1, 
                'max': 31, 
                'placeholder': 'Date (1-31)'
            }),
            
            # SWP fields
            'swp_amount': forms.NumberInput(attrs={
                'class': 'form-control', 
                'step': '0.01', 
                'placeholder': 'Enter withdrawal amount'
            }),
            'swp_frequency': forms.Select(attrs={'class': 'form-control'}),
            'swp_date': forms.NumberInput(attrs={
                'class': 'form-control', 
                'min': 1, 
                'max': 31, 
                'placeholder': 'Date (1-31)'
            }),
        }
    
    def __init__(self, *args, **kwargs):
        portfolio = kwargs.pop('portfolio', None)
        super().__init__(*args, **kwargs)
        
        # Set source scheme from portfolio
        if portfolio:
            self.fields['source_scheme'].initial = portfolio.scheme_name
        
        # Limit target scheme choices to active mutual fund schemes
        try:
            from .models import MutualFundScheme
            active_schemes = MutualFundScheme.objects.filter(is_active=True)
            scheme_choices = [(scheme.scheme_name, scheme.scheme_name) for scheme in active_schemes]
            self.fields['target_scheme'].widget = forms.Select(
                choices=[('', 'Select Target Scheme')] + scheme_choices,
                attrs={'class': 'form-control'}
            )
        except:
            pass  # If MutualFundScheme model doesn't exist, keep as text input
    
    def clean(self):
        cleaned_data = super().clean()
        action_type = cleaned_data.get('action_type')
        
        if action_type == 'redeem':
            redeem_by = cleaned_data.get('redeem_by')
            if not redeem_by:
                raise ValidationError("Please select a redemption method")
            
            if redeem_by == 'specific_amount':
                if not cleaned_data.get('redeem_amount'):
                    raise ValidationError("Please enter the amount to redeem")
            elif redeem_by == 'specific_units':
                if not cleaned_data.get('redeem_units'):
                    raise ValidationError("Please enter the units to redeem")
        
        elif action_type == 'switch':
            if not cleaned_data.get('target_scheme'):
                raise ValidationError("Please select a target scheme for switching")
            
            switch_by = cleaned_data.get('switch_by')
            if not switch_by:
                raise ValidationError("Please select a switching method")
            
            if switch_by == 'specific_amount':
                if not cleaned_data.get('switch_amount'):
                    raise ValidationError("Please enter the amount to switch")
            elif switch_by == 'specific_units':
                if not cleaned_data.get('switch_units'):
                    raise ValidationError("Please enter the units to switch")
        
        elif action_type == 'stp':
            if not cleaned_data.get('target_scheme'):
                raise ValidationError("Please select a target scheme for STP")
            if not cleaned_data.get('stp_amount'):
                raise ValidationError("Please enter the STP amount")
            if not cleaned_data.get('stp_frequency'):
                raise ValidationError("Please select STP frequency")
        
        elif action_type == 'sip':
            if not cleaned_data.get('target_scheme'):
                raise ValidationError("Please select a target scheme for SIP")
            if not cleaned_data.get('sip_amount'):
                raise ValidationError("Please enter the SIP amount")
            if not cleaned_data.get('sip_frequency'):
                raise ValidationError("Please select SIP frequency")
            if not cleaned_data.get('sip_date'):
                raise ValidationError("Please enter the SIP date")
        
        elif action_type == 'swp':
            if not cleaned_data.get('swp_amount'):
                raise ValidationError("Please enter the SWP amount")
            if not cleaned_data.get('swp_frequency'):
                raise ValidationError("Please select SWP frequency")
            if not cleaned_data.get('swp_date'):
                raise ValidationError("Please enter the SWP date")
        
        return cleaned_data

class RedeemActionForm(forms.Form):
    """Simplified form specifically for redeem actions"""
    
    REDEEM_BY_CHOICES = [
        ('all_units', 'All Units'),
        ('specific_amount', 'Specific Amount'),
        ('specific_units', 'Specific Units'),
    ]
    
    redeem_by = forms.ChoiceField(
        choices=REDEEM_BY_CHOICES,
        widget=forms.RadioSelect(attrs={'class': 'form-check-input'}),
        label='Redeem By'
    )
    
    redeem_amount = forms.DecimalField(
        required=False,
        min_value=Decimal('0.01'),
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'step': '0.01',
            'placeholder': 'Enter amount to redeem'
        }),
        label='Amount (₹)'
    )
    
    redeem_units = forms.DecimalField(
        required=False,
        min_value=Decimal('0.0001'),
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'step': '0.0001',
            'placeholder': 'Enter units to redeem'
        }),
        label='Units'
    )
    
    def clean(self):
        cleaned_data = super().clean()
        redeem_by = cleaned_data.get('redeem_by')
        
        if redeem_by == 'specific_amount' and not cleaned_data.get('redeem_amount'):
            raise ValidationError("Amount is required when redeeming by specific amount")
        elif redeem_by == 'specific_units' and not cleaned_data.get('redeem_units'):
            raise ValidationError("Units are required when redeeming by specific units")
        
        return cleaned_data

class SwitchActionForm(forms.Form):
    """Simplified form for switch actions"""
    
    SWITCH_BY_CHOICES = [
        ('all_units', 'All Units'),
        ('specific_amount', 'Specific Amount'),
        ('specific_units', 'Specific Units'),
    ]
    
    target_scheme = forms.CharField(
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter target scheme name'
        }),
        label='Target Scheme'
    )
    
    switch_by = forms.ChoiceField(
        choices=SWITCH_BY_CHOICES,
        widget=forms.RadioSelect(attrs={'class': 'form-check-input'}),
        label='Switch By'
    )
    
    switch_amount = forms.DecimalField(
        required=False,
        min_value=Decimal('0.01'),
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'step': '0.01',
            'placeholder': 'Enter amount to switch'
        }),
        label='Amount (₹)'
    )
    
    switch_units = forms.DecimalField(
        required=False,
        min_value=Decimal('0.0001'),
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'step': '0.0001',
            'placeholder': 'Enter units to switch'
        }),
        label='Units'
    )

class STPActionForm(forms.Form):
    """Form for STP (Systematic Transfer Plan) actions"""
    
    FREQUENCY_CHOICES = [
        ('monthly', 'Monthly'),
        ('weekly', 'Weekly'),
    ]
    
    target_scheme = forms.CharField(
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter target scheme name'
        }),
        label='Target Scheme'
    )
    
    stp_amount = forms.DecimalField(
        min_value=Decimal('0.01'),
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'step': '0.01',
            'placeholder': 'Enter transfer amount'
        }),
        label='Transfer Amount (₹)'
    )
    
    stp_frequency = forms.ChoiceField(
        choices=FREQUENCY_CHOICES,
        widget=forms.Select(attrs={'class': 'form-control'}),
        label='Frequency'
    )

class SIPActionForm(forms.Form):
    """Form for SIP (Systematic Investment Plan) actions"""
    
    FREQUENCY_CHOICES = [
        ('daily', 'Daily'),
        ('weekly', 'Weekly'),
        ('fortnightly', 'Fortnightly'),
        ('monthly', 'Monthly'),
    ]
    
    target_scheme = forms.CharField(
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter scheme name for SIP'
        }),
        label='Scheme Name'
    )
    
    sip_amount = forms.DecimalField(
        min_value=Decimal('0.01'),
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'step': '0.01',
            'placeholder': 'Enter SIP amount'
        }),
        label='SIP Amount (₹)'
    )
    
    sip_frequency = forms.ChoiceField(
        choices=FREQUENCY_CHOICES,
        widget=forms.Select(attrs={'class': 'form-control'}),
        label='SIP Frequency'
    )
    
    sip_date = forms.IntegerField(
        min_value=1,
        max_value=31,
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'placeholder': 'Date (1-31)'
        }),
        label='SIP Date'
    )

class SWPActionForm(forms.Form):
    """Form for SWP (Systematic Withdrawal Plan) actions"""
    
    FREQUENCY_CHOICES = [
        ('monthly', 'Monthly'),
        ('weekly', 'Weekly'),
    ]
    
    swp_amount = forms.DecimalField(
        min_value=Decimal('0.01'),
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'step': '0.01',
            'placeholder': 'Enter withdrawal amount'
        }),
        label='SWP Amount (₹)'
    )
    
    swp_frequency = forms.ChoiceField(
        choices=FREQUENCY_CHOICES,
        widget=forms.Select(attrs={'class': 'form-control'}),
        label='SWP Frequency'
    )
    
    swp_date = forms.IntegerField(
        min_value=1,
        max_value=31,
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'placeholder': 'Date (1-31)'
        }),
        label='SWP Date'
    )

class ActionPlanApprovalForm(forms.Form):
    """Form for approving/rejecting action plans"""
    
    ACTION_CHOICES = [
        ('approve', 'Approve'),
        ('reject', 'Reject'),
    ]
    
    action = forms.ChoiceField(
        choices=ACTION_CHOICES,
        widget=forms.RadioSelect(attrs={'class': 'form-check-input'}),
        label='Action'
    )
    
    notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 3,
            'placeholder': 'Optional notes for approval/rejection'
        }),
        label='Notes'
    )
    
    def clean(self):
        cleaned_data = super().clean()
        action = cleaned_data.get('action')
        notes = cleaned_data.get('notes')
        
        if action == 'reject' and not notes:
            raise ValidationError("Please provide a reason for rejection")
        
        return cleaned_data
    
# Add this to your forms.py file

from django import forms
from .models import Client, User

class ClientCreationForm(forms.Form):
    """Form for ops team lead to assign client to RM during conversion approval"""
    assigned_rm = forms.ModelChoiceField(
        queryset=User.objects.filter(role__in=['rm', 'rm_head'], is_active=True),
        empty_label="Select RM to assign client",
        widget=forms.Select(attrs={'class': 'form-control'}),
        label="Assign Client to RM"
    )
    business_verification_notes = forms.CharField(
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 3,
            'placeholder': 'Enter business verification notes...'
        }),
        label="Business Verification Notes",
        help_text="Enter details about business verification and why this lead should be converted to client",
        required=True
    )

class ClientReassignmentForm(forms.Form):
    """Form for reassigning clients to different RMs"""
    assigned_to = forms.ModelChoiceField(
        queryset=User.objects.filter(role__in=['rm', 'rm_head'], is_active=True),
        empty_label="Select RM",
        widget=forms.Select(attrs={'class': 'form-control'}),
        label="Reassign to RM"
    )
    reason = forms.CharField(
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 2,
            'placeholder': 'Enter reason for reassignment...'
        }),
        label="Reason for Reassignment",
        required=True
    )

    def __init__(self, user=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if user and user.role in ['rm_head', 'business_head', 'top_management']:
            # Managers can assign to any RM
            self.fields['assigned_to'].queryset = User.objects.filter(
                role__in=['rm', 'rm_head'], 
                is_active=True
            ).order_by('first_name', 'last_name')