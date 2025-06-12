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


from django import forms
from django.db.models import Q
from .models import Lead, User

from django import forms
from django.contrib.auth import get_user_model
from django.utils import timezone
from .models import Lead, LeadInteraction, ProductDiscussion, LeadStatusChange

User = get_user_model()


class LeadInteractionForm(forms.ModelForm):
    """Form for creating lead interactions"""
    
    class Meta:
        model = LeadInteraction
        fields = [
            'interaction_type', 
            'interaction_date', 
            'notes', 
            'next_step', 
            'next_date'
        ]
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
        fields = [
            'product', 
            'interest_level', 
            'notes'
        ]
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
    
    products_subscribed = forms.MultipleChoiceField(
        choices=ProductDiscussion.PRODUCT_CHOICES,
        required=False,
        widget=forms.CheckboxSelectMultiple(
            attrs={'class': 'form-check-input'}
        ),
        label="Products Client Subscribed To"
    )

    def __init__(self, *args, **kwargs):
        self.lead = kwargs.pop('lead', None)
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        
        if self.lead:
            # Pre-populate with discussed products
            discussed_products = self.lead.product_discussions.values_list('product', flat=True)
            self.fields['products_subscribed'].initial = list(discussed_products)

    def save(self):
        if self.lead and self.cleaned_data['confirm_conversion']:
            # Generate client ID
            self.lead.client_id = self.lead.generate_client_id()
            self.lead.converted = True
            self.lead.status = 'converted'
            self.lead.converted_at = timezone.now()
            self.lead.converted_by = self.user
            self.lead.save()
            
            # Create status change record
            LeadStatusChange.objects.create(
                lead=self.lead,
                changed_by=self.user,
                old_status=self.lead.status,
                new_status='converted',
                notes=f"Lead converted to client. {self.cleaned_data.get('conversion_notes', '')}"
            )
            
            return self.lead
        return None


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
            # Get line manager for approval
            if self.lead.assigned_to:
                line_manager = getattr(self.lead.assigned_to, 'get_line_manager', lambda: None)()
                if line_manager:
                    status_change.needs_approval = True
                    status_change.approval_by = line_manager
        
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


# Additional utility form for bulk operations
class BulkLeadActionForm(forms.Form):
    """Form for bulk actions on leads"""
    
    ACTION_CHOICES = [
        ('', 'Select Action...'),
        ('reassign', 'Reassign Selected Leads'),
        ('status_change', 'Change Status'),
        ('export', 'Export Selected Leads'),
    ]
    
    action = forms.ChoiceField(
        choices=ACTION_CHOICES,
        widget=forms.Select(attrs={'class': 'form-control'}),
        label="Bulk Action"
    )
    
    new_assigned_to = forms.ModelChoiceField(
        queryset=None,
        required=False,
        empty_label="Select RM...",
        widget=forms.Select(attrs={'class': 'form-control'}),
        label="Assign To"
    )
    
    new_status = forms.ChoiceField(
        choices=[('', 'Select Status...')] + list(Lead.STATUS_CHOICES),
        required=False,
        widget=forms.Select(attrs={'class': 'form-control'}),
        label="New Status"
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Set queryset for RMs
        rm_roles = ['rm', 'rm_head', 'business_head']
        self.fields['new_assigned_to'].queryset = User.objects.filter(
            role__in=rm_roles, 
            is_active=True
        )

class LeadForm(forms.ModelForm):
    """Form for creating/editing leads with enhanced features"""
    
    assigned_to = forms.ModelChoiceField(
        queryset=User.objects.filter(is_active=True).order_by('first_name', 'last_name'),
        empty_label="Select a user...",
        widget=forms.Select(attrs={'class': 'form-select'}),
        label="Assigned To"
    )
    
    # Source radio buttons with conditional field
    SOURCE_CHOICES = Lead.SOURCE_CHOICES
    source = forms.ChoiceField(
        choices=SOURCE_CHOICES,
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
            'assigned_to', 'probability', 'notes'
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
        }
        labels = {
            'probability': 'Conversion Probability (%)'
        }
    
    def __init__(self, *args, **kwargs):
        self.current_user = kwargs.pop('current_user', None)
        super().__init__(*args, **kwargs)
        
        # Set initial lead ID if editing
        if self.instance and self.instance.pk:
            self.fields['lead_id'] = forms.CharField(
                initial=self.instance.lead_id,
                disabled=True,
                label="Lead ID",
                widget=forms.TextInput(attrs={'class': 'form-control'})
            )
        
        # Configure assigned_to field based on user role
        self.configure_assignment_field()
        
        # Set initial status to 'new' for new leads
        if not self.instance.pk:
            self.instance.status = 'new'
        
        # Conditionally require source details based on source selection
        self.configure_source_fields()
        
        # Customize the display of users in dropdown
        self.fields['assigned_to'].label_from_instance = lambda obj: f"{obj.get_full_name()} ({obj.username})" if obj.get_full_name() else obj.username
    
    def configure_assignment_field(self):
        """Configure the assigned_to field based on user role"""
        try:
            if not self.current_user:
                # If no current user, show all active users
                self.fields['assigned_to'].queryset = User.objects.filter(is_active=True).order_by('first_name', 'last_name')
                return
            
            # Check if User model has role field
            if hasattr(User, 'role') and hasattr(self.current_user, 'role'):
                if self.current_user.role in ['top_management', 'business_head']:
                    # Can assign to any RM or RM Head
                    self.fields['assigned_to'].queryset = User.objects.filter(
                        role__in=['rm', 'rm_head', 'business_head'],
                        is_active=True
                    ).order_by('first_name', 'last_name')
                elif self.current_user.role == 'rm_head':
                    # Can assign to team members or self
                    if hasattr(self.current_user, 'get_accessible_users'):
                        accessible_users = self.current_user.get_accessible_users()
                        accessible_ids = [u.id for u in accessible_users] + [self.current_user.id]
                        self.fields['assigned_to'].queryset = User.objects.filter(
                            id__in=accessible_ids,
                            role__in=['rm', 'rm_head'],
                            is_active=True
                        ).order_by('first_name', 'last_name')
                    else:
                        # Fallback: show all RMs and RM heads
                        self.fields['assigned_to'].queryset = User.objects.filter(
                            role__in=['rm', 'rm_head'],
                            is_active=True
                        ).order_by('first_name', 'last_name')
                elif self.current_user.role == 'rm':
                    # Can only assign to self
                    self.fields['assigned_to'].queryset = User.objects.filter(id=self.current_user.id)
                    self.fields['assigned_to'].initial = self.current_user
                    self.fields['assigned_to'].widget.attrs['disabled'] = True
                else:
                    # Default: show all users with relevant roles
                    self.fields['assigned_to'].queryset = User.objects.filter(
                        is_active=True
                    ).order_by('first_name', 'last_name')
            else:
                # If no role field exists, show all active users
                self.fields['assigned_to'].queryset = User.objects.filter(is_active=True).order_by('first_name', 'last_name')
                
        except Exception as e:
            # Fallback: show all active users if there's any error
            print(f"Error configuring assignment field: {e}")
            self.fields['assigned_to'].queryset = User.objects.filter(is_active=True).order_by('first_name', 'last_name')
        
        # Ensure queryset is not empty
        if not self.fields['assigned_to'].queryset.exists():
            self.fields['assigned_to'].queryset = User.objects.filter(is_active=True).order_by('first_name', 'last_name')
    
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
        
        # Generate lead ID for new leads
        if not lead.pk and hasattr(lead, 'generate_lead_id'):
            lead.lead_id = lead.generate_lead_id()
        
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