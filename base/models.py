from django.db import models
from django.contrib.auth.models import AbstractUser, Group
from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.core.validators import MinValueValidator, MaxValueValidator

# Define User roles as constants (keep existing)
ROLE_CHOICES = (
    ('top_management', 'Top Management'),
    ('business_head', 'Business Head'),
    ('rm_head', 'RM Head'),
    ('rm', 'Relationship Manager'),
    ('ops_team_lead', 'Operations Team Lead'),
    ('ops_exec', 'Operations Executive'),
)

# Add these new status choices for client modifications
CLIENT_STATUS_CHOICES = (
    ('active', 'Active'),
    ('muted', 'Muted'),
)

APPROVAL_STATUS_CHOICES = (
    ('pending', 'Pending Approval'),
    ('approved', 'Approved'),
    ('rejected', 'Rejected'),
)

class Team(models.Model):
    """Represents a team structure for better organization"""
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    is_ops_team = models.BooleanField(default=False, help_text="Is this an operations team?")

    def __str__(self):
        return self.name

class User(AbstractUser):
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    
    # Hierarchy relationships
    manager = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='subordinates',
        help_text="Direct manager in the hierarchy"
    )
    
    # For RM Heads to manage teams through Django Groups
    managed_groups = models.ManyToManyField(
        Group,
        blank=True,
        related_name='group_leaders',
        help_text="Groups managed by this RM Head"
    )

    # Teams this user belongs to
    teams = models.ManyToManyField(
        Team,
        through='TeamMembership',
        related_name='members',
        blank=True,
        help_text="Teams this user belongs to"
    )

    class Meta:
        verbose_name = 'User'
        verbose_name_plural = 'Users'
        ordering = ['role', 'username']

    def clean(self):
        """Validate hierarchy rules"""
        super().clean()
        
        # Role-based manager validation
        if self.role == 'top_management' and self.manager:
            raise ValidationError("Top Management cannot have a manager")
            
        if self.role == 'business_head' and self.manager and self.manager.role != 'top_management':
            raise ValidationError("Business Head can only report to Top Management")
            
        if self.role == 'rm_head' and self.manager and self.manager.role not in ['business_head', 'top_management']:
            raise ValidationError("RM Head can only report to Business Head or Top Management")
            
        if self.role == 'rm' and self.manager and self.manager.role not in ['rm_head', 'business_head']:
            raise ValidationError("RM can only report to RM Head or Business Head")
            
        if self.role == 'ops_team_lead' and self.manager and self.manager.role not in ['business_head', 'top_management']:
            raise ValidationError("Ops Team Lead can only report to Business Head or Top Management")
            
        if self.role == 'ops_exec' and self.manager and self.manager.role != 'ops_team_lead':
            raise ValidationError("Ops Exec can only report to Ops Team Lead")
        
    def is_operations_team(self):
        """Check if user is in operations team"""
        return self.teams.filter(is_ops_team=True).exists()

    def can_modify_client_profile(self):
        """Check if user can modify client profiles"""
        return self.role in ['ops_team_lead', 'business_head', 'top_management']

    def can_view_client_profile(self):
        """Check if user can view client profiles"""
        return self.role in ['rm', 'rm_head', 'business_head', 'top_management', 'ops_team_lead', 'ops_exec']

    def get_team_members(self):
        """Get all team members for this user (if they're a team leader)"""
        if self.role == 'rm_head':
            # Get users in the same groups as this RM Head
            return User.objects.filter(
                role='rm',
                groups__in=self.managed_groups.all()
            ).distinct()
        return User.objects.none()

    def get_teams_display(self):
        """Display teams this user belongs to"""
        return ", ".join([team.name for team in self.teams.all()]) or "No teams"
    get_teams_display.short_description = 'Teams'

    def get_managed_teams_display(self):
        """Display teams this user manages (for RM Heads)"""
        if self.role == 'rm_head':
            return ", ".join([team.name for team in Team.objects.filter(leader=self)]) or "No teams managed"
        return "N/A"
    get_managed_teams_display.short_description = 'Managed Teams'

    def __str__(self):
        return f"{self.username} ({self.get_role_display()})"
    
    def get_line_manager(self):
        """Get the direct line manager for this user"""
        return self.manager
    
    def get_approval_manager(self):
        """Get the appropriate manager for approval requests based on role hierarchy"""
        if self.role == 'rm':
            # RM should get approval from RM Head
            if self.manager and self.manager.role == 'rm_head':
                return self.manager
            # If direct manager is not RM Head, find the RM Head in the hierarchy
            current = self.manager
            while current:
                if current.role == 'rm_head':
                    return current
                current = current.manager
        
        # For other roles, return direct manager
        return self.manager
    
    def can_approve_conversion(self, user):
        """Check if this user can approve conversion requests for the given user"""
        # Direct manager can approve
        if user.manager == self:
            return True
            
        # RM Head can approve for RMs in their hierarchy
        if self.role == 'rm_head' and user.role == 'rm':
            current = user
            while current:
                if current.manager == self:
                    return True
                current = current.manager
                
        return False

    def get_subordinates_recursive(self):
        """Get all subordinates in the hierarchy tree"""
        subordinates = list(self.subordinates.all())
        for subordinate in list(subordinates):
            subordinates.extend(subordinate.get_subordinates_recursive())
        return subordinates

    def can_access_user_data(self, target_user):
        """Check if this user can access target_user's data"""
        if self.role == 'top_management':
            return True
        elif self.role == 'business_head':
            return True
        elif self.role == 'rm_head':
            # Can access own data and team members' data
            if target_user == self:
                return True
            return target_user in self.get_team_members()
        else:  # RM
            return target_user == self

    def get_accessible_users(self):
        """Get all users this user can access data for"""
        if self.role == 'top_management':
            return User.objects.all()
        elif self.role == 'business_head':
            return User.objects.all()
        elif self.role == 'rm_head':
            team_members = self.get_team_members()
            return User.objects.filter(id__in=[self.id] + [tm.id for tm in team_members])
        else:  # RM
            return User.objects.filter(id=self.id)

# Add leader relationship to Team after User is defined
Team.add_to_class('leader', models.ForeignKey(
    User,
    on_delete=models.SET_NULL,
    null=True,
    blank=True,
    limit_choices_to={'role__in': ['rm_head', 'ops_team_lead']},
    related_name='led_teams'
))

class TeamMembership(models.Model):
    """Intermediate model for team membership with additional fields"""
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    team = models.ForeignKey(Team, on_delete=models.CASCADE)
    date_joined = models.DateField(auto_now_add=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = ('user', 'team')
        verbose_name = 'Team Membership'
        verbose_name_plural = 'Team Memberships'

    def __str__(self):
        return f"{self.user} in {self.team}"
    
class ClientProfile(models.Model):
    """Main client profile model with all required fields"""
    # Add the missing client_id field
    client_id = models.CharField(max_length=20, unique=True, editable=False, null=True, blank=True)
    
    # Basic Information
    client_full_name = models.CharField(max_length=255)
    family_head_name = models.CharField(max_length=255, blank=True, null=True)
    address_kyc = models.TextField()
    date_of_birth = models.DateField()
    pan_number = models.CharField(max_length=10, unique=True)
    email = models.EmailField()
    mobile_number = models.CharField(max_length=15)
    first_investment_date = models.DateField(blank=True, null=True)
    
    # Mapped personnel
    mapped_rm = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        limit_choices_to={'role': 'rm'},
        related_name='rm_clients'
    )
    mapped_ops_exec = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        limit_choices_to={'role': 'ops_exec'},
        related_name='ops_clients'
    )
    
    # Status and metadata
    status = models.CharField(max_length=20, choices=CLIENT_STATUS_CHOICES, default='active')
    muted_reason = models.TextField(blank=True, null=True)
    muted_date = models.DateTimeField(blank=True, null=True)
    muted_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='muted_clients'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_client_profiles'
    )
    
    class Meta:
        ordering = ['client_full_name']
        verbose_name = 'Client Profile'
        verbose_name_plural = 'Client Profiles'
        permissions = [
            ('can_mute_client', 'Can mute/unmute client'),
            ('can_change_pan', 'Can change PAN number'),
            ('can_change_name', 'Can change client name'),
        ]
    
    def __str__(self):
        return f"{self.client_full_name} ({self.pan_number})"
    
    def clean(self):
        """Validate PAN number format"""
        super().clean()
        if len(self.pan_number) != 10:
            raise ValidationError("PAN number must be 10 characters long")
    
    def save(self, *args, **kwargs):
        """Generate client ID if not exists"""
        if not self.pk and not self.client_id:
            self.client_id = self.generate_client_id()
        super().save(*args, **kwargs)
        
    def generate_client_id(self):
        """Generate a unique client ID"""
        from datetime import datetime
        date_part = datetime.now().strftime("%Y%m%d")
        last_client = ClientProfile.objects.filter(client_id__startswith=f"CL{date_part}").order_by('-client_id').first()
        
        if last_client:
            last_num = int(last_client.client_id[-4:])
            new_num = last_num + 1
        else:
            new_num = 1
            
        return f"CL{date_part}{new_num:04d}"
    
    def mute_client(self, reason, muted_by):
        """Mute the client"""
        self.status = 'muted'
        self.muted_reason = reason
        self.muted_by = muted_by
        self.muted_date = timezone.now()
        self.save()
    
    def unmute_client(self, unmuted_by):
        """Unmute the client"""
        self.status = 'active'
        self.muted_reason = None
        self.muted_by = None
        self.muted_date = None
        self.save()
    
    def unmute_client(self, unmuted_by):
        """Unmute the client"""
        self.status = 'active'
        self.muted_reason = None
        self.muted_by = None
        self.muted_date = None
        self.save()
        
class ClientAccount(models.Model):
    """Base abstract model for all client account types"""
    ACCOUNT_TYPE_CHOICES = (
        ('mfu', 'MFU CAN Account'),
        ('motilal', 'Motilal Demat'),
        ('prabhudas', 'Prabhudas Lilladher Demat'),
    )
    
    client = models.ForeignKey(ClientProfile, on_delete=models.CASCADE, related_name='client_accounts')
    account_type = models.CharField(max_length=20, choices=ACCOUNT_TYPE_CHOICES)
    account_number = models.CharField(max_length=50, unique=True)
    is_primary = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        abstract = True

class MFUCANAccount(ClientAccount):
    """MFU CAN Account details"""
    folio_number = models.CharField(max_length=50)
    amc_name = models.CharField(max_length=100)
    kyc_status = models.BooleanField(default=False)
    last_transaction_date = models.DateField(null=True, blank=True)
    
    # Fix the related_name to be unique
    client = models.ForeignKey(
        ClientProfile, 
        on_delete=models.CASCADE, 
        related_name='mfu_accounts'
    )
    
    class Meta:
        verbose_name = 'MFU CAN Account'
        verbose_name_plural = 'MFU CAN Accounts'
    
    def __str__(self):
        return f"MFU CAN: {self.account_number}"

class DematAccount(ClientAccount):
    """Base model for Demat accounts"""
    broker_name = models.CharField(max_length=100)
    dp_id = models.CharField(max_length=20)
    kyc_status = models.BooleanField(default=False)
    last_activity_date = models.DateField(null=True, blank=True)
    
    class Meta:
        abstract = True

class MotilalDematAccount(DematAccount):
    """Motilal Oswal Demat account details"""
    trading_enabled = models.BooleanField(default=False)
    margin_enabled = models.BooleanField(default=False)
    
    # Fix the related_name to be unique
    client = models.ForeignKey(
        ClientProfile, 
        on_delete=models.CASCADE, 
        related_name='motilal_accounts'
    )
    
    class Meta:
        verbose_name = 'Motilal Demat Account'
        verbose_name_plural = 'Motilal Demat Accounts'
    
    def __str__(self):
        return f"Motilal Demat: {self.account_number}"

class PrabhudasDematAccount(DematAccount):
    """Prabhudas Lilladher Demat account details"""
    commodity_enabled = models.BooleanField(default=False)
    currency_enabled = models.BooleanField(default=False)
    
    # Fix the related_name to be unique
    client = models.ForeignKey(
        ClientProfile, 
        on_delete=models.CASCADE, 
        related_name='prabhudas_accounts'
    )
    
    class Meta:
        verbose_name = 'Prabhudas Demat Account'
        verbose_name_plural = 'Prabhudas Demat Accounts'
    
    def __str__(self):
        return f"Prabhudas Demat: {self.account_number}"

class ClientProfileModification(models.Model):
    """Track modifications to client profiles"""
    client = models.ForeignKey(ClientProfile, on_delete=models.CASCADE, related_name='modifications')
    requested_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='requested_modifications')
    requested_at = models.DateTimeField(auto_now_add=True)
    approved_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='approved_modifications'
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=APPROVAL_STATUS_CHOICES, default='pending')
    modification_data = models.JSONField(help_text="Stores the changed fields and values")
    reason = models.TextField()
    requires_top_management = models.BooleanField(default=False)
    
    class Meta:
        ordering = ['-requested_at']
        verbose_name = 'Client Profile Modification'
        verbose_name_plural = 'Client Profile Modifications'
    
    def __str__(self):
        return f"Modification for {self.client} ({self.get_status_display()})"
    
    def approve(self, approved_by):
        """Approve the modification"""
        if self.status != 'pending':
            return False
        
        self.status = 'approved'
        self.approved_by = approved_by
        self.approved_at = timezone.now()
        self.save()
        
        # Apply the changes to the client profile
        client = self.client
        for field, value in self.modification_data.items():
            setattr(client, field, value)
        client.save()
        
        return True
    
    def reject(self, rejected_by):
        """Reject the modification"""
        if self.status != 'pending':
            return False
        
        self.status = 'rejected'
        self.approved_by = rejected_by
        self.approved_at = timezone.now()
        self.save()
        return True
    
    
class Lead(models.Model):
    STATUS_CHOICES = (
        ('new', 'New Lead'),
        ('cold', 'Cold Lead'),
        ('warm', 'Warm Lead'),
        ('hot', 'Hot Lead'),
        ('contacted', 'Contacted'),
        ('follow_up', 'Follow Up'),
        ('conversion_requested', 'Conversion Requested'),
        ('converted', 'Converted to Client'),
        ('lost', 'Lost Lead'),
    )
    
    SOURCE_CHOICES = (
        ('existing_client', 'Existing Client'),
        ('own_circle', 'Own Circle'),
        ('social_media', 'Social Media'),
        ('referral', 'Referral'),
        ('other', 'Other'),
    )
    
    # Fix the related_name to be unique
    client_profile = models.OneToOneField(
        ClientProfile,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='lead_profile'
    )
    
    # Lead Identification
    lead_id = models.CharField(max_length=20, unique=True, editable=False, null=True, blank=True)
    client_id = models.CharField(max_length=20, blank=True, null=True, unique=True)
    
    # Basic Information
    name = models.CharField(max_length=255)
    email = models.EmailField(blank=True, null=True)
    mobile = models.CharField(max_length=15, null=True, blank=True)
    
    # Lead Source
    source = models.CharField(max_length=50, choices=SOURCE_CHOICES, null=True, blank=True)
    source_details = models.CharField(max_length=255, blank=True, null=True)
    reference_client = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        limit_choices_to={'converted': True},
        help_text="If source is Existing Client"
    )
    
    # Assignment and Tracking
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        limit_choices_to={'role__in': ['rm', 'rm_head', 'business_head']},
        on_delete=models.SET_NULL,
        null=True,
        related_name='leads'
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_leads'
    )
    
    # Status and Dates
    status = models.CharField(max_length=50, choices=STATUS_CHOICES, default='new')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    first_interaction_date = models.DateTimeField(blank=True, null=True)
    next_interaction_date = models.DateField(blank=True, null=True)
    converted_at = models.DateTimeField(blank=True, null=True)
    converted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='converted_leads'
    )
    
    # Flags
    converted = models.BooleanField(default=False)
    needs_reassignment_approval = models.BooleanField(default=False)
    reassignment_requested_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='reassignment_requests'
    )
    
    # Additional Information
    notes = models.TextField(blank=True, null=True)
    probability = models.PositiveIntegerField(
        default=0,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text="Probability of conversion (0-100)%"
    )
    
    class Meta:
        ordering = ['-created_at']
        permissions = [
            ('can_convert_lead', 'Can convert lead to client'),
            ('can_reassign_lead', 'Can reassign lead to another RM'),
        ]
    
    def __str__(self):
        return f"{self.lead_id} - {self.name} ({self.get_status_display()})"
    
    def save(self, *args, **kwargs):
        if not self.lead_id:
            self.lead_id = self.generate_lead_id()
        super().save(*args, **kwargs)
    
    def generate_lead_id(self):
        """Generate a unique lead ID in format LDYYYYMMDDXXXX"""
        from datetime import datetime
        date_part = datetime.now().strftime("%Y%m%d")
        last_lead = Lead.objects.filter(lead_id__startswith=f"LD{date_part}").order_by('-lead_id').first()
        
        if last_lead:
            last_num = int(last_lead.lead_id[-4:])
            new_num = last_num + 1
        else:
            new_num = 1
            
        return f"LD{date_part}{new_num:04d}"

    
    def days_to_first_interaction(self):
        """Calculate days from creation to first interaction"""
        if self.first_interaction_date:
            delta = self.first_interaction_date - self.created_at
            return delta.days
        return None
    
    def request_reassignment(self, new_rm, requested_by):
        """Request lead reassignment to another RM"""
        if self.assigned_to == new_rm:
            return False
        
        line_manager = self.assigned_to.get_line_manager()
        if not line_manager:
            return False
        
        self.needs_reassignment_approval = True
        self.reassignment_requested_to = line_manager
        self.save()
        
        # Create status change record
        LeadStatusChange.objects.create(
            lead=self,
            changed_by=requested_by,
            old_status=f"assigned_to:{self.assigned_to.id}",
            new_status=f"assigned_to:{new_rm.id}",
            notes=f"Reassignment requested from {self.assigned_to.get_full_name()} to {new_rm.get_full_name()}",
            needs_approval=True,
            approval_by=line_manager
        )
        
        return True

class LeadInteraction(models.Model):
    INTERACTION_CHOICES = [
        ('call', 'Phone Call'),
        ('meeting', 'In-Person Meeting'),
        ('email', 'Email'),
        ('message', 'Message'),
        ('other', 'Other')
    ]
    
    lead = models.ForeignKey(Lead, on_delete=models.CASCADE, related_name='interactions')
    interaction_type = models.CharField(max_length=50, choices=INTERACTION_CHOICES)
    interaction_date = models.DateTimeField(default=timezone.now)
    notes = models.TextField()
    next_step = models.TextField(blank=True, null=True)
    next_date = models.DateField(blank=True, null=True)
    interacted_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    
    class Meta:
        ordering = ['-interaction_date']
        verbose_name = 'Lead Interaction'
        verbose_name_plural = 'Lead Interactions'
    
    def __str__(self):
        return f"{self.get_interaction_type_display()} on {self.interaction_date.strftime('%Y-%m-%d')}"

class ProductDiscussion(models.Model):
    PRODUCT_CHOICES = [
        ('mf_sip', 'Mutual Fund SIP'),
        ('mf_lumpsum', 'Mutual Fund Lumpsum'),
        ('equity', 'Equity'),
        ('ai_portfolio', 'AI Portfolio'),
        ('loans', 'Loans'),
        ('insurance', 'Insurance'),
        ('pms', 'Portfolio Management Services'),
        ('aif', 'Alternative Investment Funds'),
        ('other', 'Other')
    ]
    
    lead = models.ForeignKey(Lead, on_delete=models.CASCADE, related_name='product_discussions')
    product = models.CharField(max_length=50, choices=PRODUCT_CHOICES)
    interest_level = models.PositiveIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(10)],
        help_text="Interest level (1-10)"
    )
    notes = models.TextField(blank=True, null=True)
    discussed_on = models.DateTimeField(default=timezone.now)
    discussed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    
    class Meta:
        ordering = ['-discussed_on']
        verbose_name = 'Product Discussion'
        verbose_name_plural = 'Product Discussions'
    
    def __str__(self):
        return f"{self.get_product_display()} (Interest: {self.interest_level}/10)"

class LeadStatusChange(models.Model):
    lead = models.ForeignKey(Lead, on_delete=models.CASCADE, related_name='status_changes')
    changed_at = models.DateTimeField(default=timezone.now)
    changed_by = models.ForeignKey(settings.AUTH_USER_MODEL, related_name='status_changes_made', on_delete=models.SET_NULL, null=True)
    old_status = models.CharField(max_length=255)
    new_status = models.CharField(max_length=255)
    notes = models.TextField(blank=True, null=True)
    needs_approval = models.BooleanField(default=False)
    approved = models.BooleanField(default=False)
    approval_by = models.ForeignKey(settings.AUTH_USER_MODEL, related_name='approvals_to_make', on_delete=models.SET_NULL, null=True, blank=True)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='approved_status_changes'
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-changed_at']
        verbose_name = 'Status Change'
        verbose_name_plural = 'Status Changes'

    def __str__(self):
        return f"LeadStatusChange for Lead {self.lead.id} by {self.changed_by}"

class Client(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        limit_choices_to={'role': 'rm'},
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='clients'
    )
    client_profile = models.OneToOneField(
        ClientProfile,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='legacy_client'
    )
    lead = models.OneToOneField(
        Lead,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='client'
    )
    name = models.CharField(max_length=255)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='created_clients')
    contact_info = models.CharField(max_length=255, default='N/A')
    aum = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
    sip_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
    demat_count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

class Task(models.Model):
    PRIORITY_CHOICES = (
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
        ('urgent', 'Urgent'),
    )
    
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='tasks'
    )
    
    assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assigned_tasks',
        help_text="User who assigned this task"
    )
    
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    due_date = models.DateTimeField(null=True, blank=True)
    priority = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default='medium')
    completed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.title} ({'Done' if self.completed else 'Pending'})"

class Reminder(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='reminders'
    )
    message = models.TextField(default='Reminder message')
    remind_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    is_done = models.BooleanField(default=False)

    def __str__(self):
        return f"Reminder for {self.user.username}: {self.message}"

class ServiceRequest(models.Model):
    STATUS_CHOICES = (
        ('open', 'Open'),
        ('in_progress', 'In Progress'),
        ('resolved', 'Resolved'),
        ('closed', 'Closed'),
    )
    
    client = models.ForeignKey(
        Client,
        on_delete=models.CASCADE,
        related_name='service_requests'
    )
    raised_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='raised_service_requests'
    )
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assigned_service_requests'
    )
    description = models.TextField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='open')
    priority = models.CharField(max_length=10, choices=Task.PRIORITY_CHOICES, default='medium')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"ServiceRequest ({self.status}) for {self.client.name}"

class BusinessTracker(models.Model):
    month = models.DateField()
    total_sip = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    total_demat = models.PositiveIntegerField(default=0)
    total_aum = models.DecimalField(max_digits=20, decimal_places=2, default=0)
    
    # Track by team/user for better insights
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='business_metrics'
    )
    team = models.ForeignKey(
        Team,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='business_metrics'
    )

    class Meta: 
        unique_together = ['month', 'user']

    def __str__(self):
        user_str = f" - {self.user.username}" if self.user else ""
        return f"{self.month.strftime('%B %Y')}{user_str}"

class InvestmentPlanReview(models.Model):
    client = models.ForeignKey(
        'Client',
        on_delete=models.CASCADE,
        related_name='investment_reviews'
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_investment_plans'
    )
    goal = models.CharField(max_length=255, null=True, blank=True)
    principal_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
    tenure_years = models.PositiveIntegerField(default=1)
    monthly_investment = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    expected_return_rate = models.DecimalField(max_digits=5, decimal_places=2, default=12.00, help_text="Expected annual return percentage")
    created_at = models.DateTimeField(auto_now_add=True, null=True, blank=True)
    last_reviewed = models.DateTimeField(auto_now=True)

    def total_investment(self):
        return self.monthly_investment * 12 * self.tenure_years + self.principal_amount

    def projected_value(self):
        """Calculate projected value based on expected return rate"""
        monthly_rate = self.expected_return_rate / 100 / 12
        months = self.tenure_years * 12
        
        # Future value of lump sum
        fv_lump = self.principal_amount * ((1 + monthly_rate) ** months)
        
        # Future value of monthly SIP
        if monthly_rate > 0:
            fv_sip = self.monthly_investment * (((1 + monthly_rate) ** months - 1) / monthly_rate)
        else:
            fv_sip = self.monthly_investment * months
            
        return fv_lump + fv_sip

    def __str__(self):
        return f"{self.goal or 'No Goal'} for {self.client.name}"