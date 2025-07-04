from django.db import models
from django.contrib.auth.models import AbstractUser, Group
from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.core.validators import MinValueValidator, MaxValueValidator, FileExtensionValidator

# Updated User roles with Ops roles
ROLE_CHOICES = (
    ('top_management', 'Top Management'),
    ('business_head', 'Business Head'),
    ('business_head_ops', 'Business Head - Ops'),  # New role
    ('rm_head', 'RM Head'),
    ('rm', 'Relationship Manager'),
    ('ops_team_lead', 'Operations Team Lead'),  # Updated
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
    
    # For RM Heads and Ops Team Leads to manage teams through Django Groups
    managed_groups = models.ManyToManyField(
        Group,
        blank=True,
        related_name='group_leaders',
        help_text="Groups managed by this user"
    )

    # Teams this user belongs to
    teams = models.ManyToManyField(
        Team,
        through='TeamMembership',
        related_name='members',
        blank=True,
        help_text="Teams this user belongs to"
    )
    
    def get_team_members(self):
        '''Get team members for RM Heads and Team Leads'''
        if hasattr(self, 'subordinates'):
            return self.subordinates.all()
        return User.objects.filter(supervisor=self)
    
    @property 
    def lead_count(self):
        '''Get count of leads assigned to this user'''
        return self.lead_set.count()
    
    @property
    def task_count(self):
        '''Get count of tasks assigned to this user'''
        return self.task_set.count()
    
    @property
    def performance_score(self):
        '''Calculate a performance score based on leads and tasks'''
        leads = self.lead_count
        tasks = self.task_count
        team_size = self.get_team_members().count()
        return min(100, (leads * 5) + (tasks * 2) + (team_size * 10))

    class Meta:
        verbose_name = 'User'
        verbose_name_plural = 'Users'
        ordering = ['role', 'username']

    def clean(self):
        """Validate hierarchy rules with updated ops roles"""
        super().clean()
        
        # Role-based manager validation
        if self.role == 'top_management' and self.manager:
            raise ValidationError("Top Management cannot have a manager")
            
        if self.role == 'business_head' and self.manager and self.manager.role != 'top_management':
            raise ValidationError("Business Head can only report to Top Management")
            
        if self.role == 'business_head_ops' and self.manager and self.manager.role not in ['top_management', 'business_head']:
            raise ValidationError("Business Head - Ops can only report to Top Management or Business Head")
            
        if self.role == 'rm_head' and self.manager and self.manager.role not in ['business_head', 'top_management']:
            raise ValidationError("RM Head can only report to Business Head or Top Management")
            
        if self.role == 'rm' and self.manager and self.manager.role not in ['rm_head', 'business_head']:
            raise ValidationError("RM can only report to RM Head or Business Head")
            
        if self.role == 'ops_team_lead' and self.manager and self.manager.role not in ['business_head_ops', 'business_head', 'top_management']:
            raise ValidationError("Ops Team Lead can only report to Business Head - Ops, Business Head, or Top Management")
            
        if self.role == 'ops_exec' and self.manager and self.manager.role != 'ops_team_lead':
            raise ValidationError("Ops Exec can only report to Ops Team Lead")
        
    def is_operations_team(self):
        """Check if user is in operations team"""
        return self.teams.filter(is_ops_team=True).exists() or self.role in ['business_head_ops', 'ops_team_lead', 'ops_exec']

    def can_modify_client_profile(self):
        """Check if user can modify client profiles"""
        return self.role in ['ops_team_lead', 'business_head', 'business_head_ops', 'top_management']

    def can_view_client_profile(self):
        """Check if user can view client profiles"""
        return self.role in ['rm', 'rm_head', 'business_head', 'business_head_ops', 'top_management', 'ops_team_lead', 'ops_exec']

    def get_team_members(self):
        """Get all team members for this user (if they're a team leader)"""
        if self.role == 'rm_head':
            # Get users in the same groups as this RM Head
            return User.objects.filter(
                role='rm',
                groups__in=self.managed_groups.all()
            ).distinct()
        elif self.role == 'business_head_ops':
            # Get all operations team members under this Business Head - Ops
            return User.objects.filter(
                role__in=['ops_team_lead', 'ops_exec'],
                manager__in=[self] + list(self.subordinates.all())
            ).distinct()
        elif self.role == 'ops_team_lead':
            # Get operations executives under this team lead
            return User.objects.filter(role='ops_exec', manager=self)
        return User.objects.none()

    def get_teams_display(self):
        """Display teams this user belongs to"""
        return ", ".join([team.name for team in self.teams.all()]) or "No teams"
    get_teams_display.short_description = 'Teams'

    def get_managed_teams_display(self):
        """Display teams this user manages"""
        if self.role in ['rm_head', 'ops_team_lead']:
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
        elif self.role == 'ops_exec':
            # Ops Exec should get approval from Ops Team Lead
            if self.manager and self.manager.role == 'ops_team_lead':
                return self.manager
        elif self.role == 'ops_team_lead':
            # Ops Team Lead should get approval from Business Head - Ops or Business Head
            if self.manager and self.manager.role in ['business_head_ops', 'business_head']:
                return self.manager
        
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
                
        # Ops Team Lead can approve for Ops Execs
        if self.role == 'ops_team_lead' and user.role == 'ops_exec':
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
        elif self.role in ['business_head', 'business_head_ops']:
            return True
        elif self.role in ['rm_head', 'ops_team_lead']:
            # Can access own data and team members' data
            if target_user == self:
                return True
            return target_user in self.get_team_members()
        else:  # RM, Ops Exec
            return target_user == self

    def get_accessible_users(self):
        """Get all users this user can access data for"""
        if self.role == 'top_management':
            return User.objects.all()
        elif self.role in ['business_head', 'business_head_ops']:
            return User.objects.all()
        elif self.role in ['rm_head', 'ops_team_lead']:
            team_members = self.get_team_members()
            return User.objects.filter(id__in=[self.id] + [tm.id for tm in team_members])
        else:  # RM, Ops Exec
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

# Notes System Models
class NoteList(models.Model):
    """Lists to organize notes by topic"""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='note_lists')
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ('user', 'name')
        ordering = ['name']
        verbose_name = 'Note List'
        verbose_name_plural = 'Note Lists'
    
    def __str__(self):
        return f"{self.name} - {self.user.username}"

def note_file_upload_path(instance, filename):
    """Generate file upload path for note attachments"""
    return f'notes/{instance.user.id}/{instance.id}/{filename}'

class Note(models.Model):
    """Individual notes with privacy (no manager access)"""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notes')
    note_list = models.ForeignKey(NoteList, on_delete=models.CASCADE, related_name='notes')
    
    # Note details
    heading = models.CharField(max_length=200)
    content = models.TextField()
    
    # Dates
    creation_date = models.DateField(default=timezone.now)
    reminder_date = models.DateTimeField(null=True, blank=True)
    due_date = models.DateField(null=True, blank=True)
    
    # File attachment (max 500KB)
    attachment = models.FileField(
        upload_to=note_file_upload_path,
        null=True,
        blank=True,
        validators=[
            FileExtensionValidator(allowed_extensions=['pdf', 'doc', 'docx', 'txt', 'jpg', 'jpeg', 'png', 'xlsx', 'xls'])
        ],
        help_text="Maximum file size: 500KB"
    )
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    # Status
    is_completed = models.BooleanField(default=False)
    completed_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        ordering = ['-updated_at']
        verbose_name = 'Note'
        verbose_name_plural = 'Notes'
    
    def __str__(self):
        return f"{self.heading} - {self.user.username}"
    
    def clean(self):
        """Validate file size (500KB limit)"""
        super().clean()
        if self.attachment:
            if self.attachment.size > 500 * 1024:  # 500KB in bytes
                raise ValidationError("File size cannot exceed 500KB")
    
    def save(self, *args, **kwargs):
        # Set completed_at when marking as completed
        if self.is_completed and not self.completed_at:
            self.completed_at = timezone.now()
        elif not self.is_completed:
            self.completed_at = None
        super().save(*args, **kwargs)
    
    @property
    def is_overdue(self):
        """Check if note is overdue"""
        if self.due_date and not self.is_completed:
            return timezone.now().date() > self.due_date
        return False
    
    @property
    def has_reminder_pending(self):
        """Check if reminder is pending"""
        if self.reminder_date and not self.is_completed:
            return timezone.now() < self.reminder_date
        return False

# Existing models continue below...

# Add interaction type choices
INTERACTION_TYPE_CHOICES = [
    ('call', 'Phone Call'),
    ('email', 'Email'),
    ('meeting', 'Meeting'),
    ('video_call', 'Video Call'),
    ('site_visit', 'Site Visit'),
    ('documentation', 'Documentation'),
    ('complaint', 'Complaint'),
    ('follow_up', 'Follow Up'),
    ('advisory', 'Advisory'),
    ('other', 'Other'),
]

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


class ClientInteraction(models.Model):
    """Model to track all client interactions"""
    client_profile = models.ForeignKey(
        ClientProfile,
        on_delete=models.CASCADE,
        related_name='interactions'
    )
    interaction_type = models.CharField(
        max_length=20,
        choices=INTERACTION_TYPE_CHOICES,
        default='call'
    )
    interaction_date = models.DateTimeField(default=timezone.now)
    duration_minutes = models.PositiveIntegerField(
        blank=True,
        null=True,
        help_text="Duration in minutes (optional)"
    )
    notes = models.TextField(
        help_text="Detailed notes about the interaction"
    )
    follow_up_required = models.BooleanField(default=False)
    follow_up_date = models.DateField(
        blank=True,
        null=True,
        help_text="Date for follow-up (if required)"
    )
    priority = models.CharField(
        max_length=10,
        choices=[
            ('low', 'Low'),
            ('medium', 'Medium'),
            ('high', 'High'),
            ('urgent', 'Urgent'),
        ],
        default='medium'
    )
    
    # Tracking fields
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_interactions'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-interaction_date', '-created_at']
        verbose_name = 'Client Interaction'
        verbose_name_plural = 'Client Interactions'
        permissions = [
            ('can_view_all_interactions', 'Can view all client interactions'),
            ('can_edit_own_interactions', 'Can edit own interactions'),
        ]
    
    def __str__(self):
        return f"{self.client_profile.client_full_name} - {self.get_interaction_type_display()} on {self.interaction_date.strftime('%Y-%m-%d')}"
    
    def clean(self):
        """Validate interaction data"""
        super().clean()
        if self.follow_up_required and not self.follow_up_date:
            raise ValidationError("Follow-up date is required when follow-up is marked as required.")
        
        if self.follow_up_date and self.follow_up_date <= timezone.now().date():
            raise ValidationError("Follow-up date must be in the future.")
    
    def is_editable_by(self, user):
        """Check if the interaction can be edited by the given user"""
        from datetime import timedelta
        
        # Only creator can edit
        if user != self.created_by:
            return False
        
        # Only within 24 hours
        if timezone.now() - self.created_at > timedelta(hours=24):
            return False
        
        return True
    
    def get_time_since_creation(self):
        """Get human-readable time since creation"""
        from django.utils.timesince import timesince
        return timesince(self.created_at)
        
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

from django.db import models
from django.conf import settings
from django.utils import timezone
from django.core.exceptions import ValidationError


class ServiceRequestType(models.Model):
    """
    Service Request Type categorization
    """
    CATEGORY_CHOICES = (
        ('personal_details', 'Personal Details Modification'),
        ('account_creation', 'Account Creation'),
        ('account_closure', 'Account Closure Request'),
        ('adhoc_mf', 'Adhoc Requests - Mutual Fund'),
        ('adhoc_demat', 'Adhoc Requests - Demat'),
        ('report_request', 'Report Request'),
    )
    
    name = models.CharField(max_length=100)
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES)
    code = models.CharField(max_length=20, unique=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    required_documents = models.JSONField(default=list, blank=True)
    
    def __str__(self):
        return f"{self.name} ({self.get_category_display()})"


class ServiceRequestDocument(models.Model):
    """
    Documents attached to service requests
    """
    service_request = models.ForeignKey(
        'ServiceRequest',
        on_delete=models.CASCADE,
        related_name='documents'
    )
    document = models.FileField(upload_to='service_requests/documents/')
    document_name = models.CharField(max_length=255)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"Document: {self.document_name}"


class ServiceRequestComment(models.Model):
    """
    Comments/remarks for service requests
    """
    service_request = models.ForeignKey(
        'ServiceRequest',
        on_delete=models.CASCADE,
        related_name='comments'
    )
    comment = models.TextField()
    commented_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True
    )
    created_at = models.DateTimeField(auto_now_add=True)
    is_internal = models.BooleanField(default=False)  # Internal ops comments vs client-facing
    
    def __str__(self):
        return f"Comment by {self.commented_by} on {self.created_at}"


class ServiceRequest(models.Model):
    """
    Enhanced Service Request Model with complete workflow support
    """
    STATUS_CHOICES = (
        ('draft', 'Draft'),
        ('submitted', 'Submitted'),
        ('documents_requested', 'Documents Requested'),
        ('documents_received', 'Documents Received'),
        ('in_progress', 'In Progress'),
        ('resolved', 'Resolved'),
        ('client_verification', 'Client Verification'),
        ('closed', 'Closed'),
        ('on_hold', 'On Hold'),
        ('rejected', 'Rejected'),
    )
    
    PRIORITY_CHOICES = (
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
        ('urgent', 'Urgent'),
    )
    
    # Basic Information
    request_id = models.CharField(max_length=20, unique=True, editable=False)
    client = models.ForeignKey(
        'base.Client',  # Assuming you have a Client model
        on_delete=models.CASCADE,
        related_name='service_requests'
    )
    
    # Request Type and Details
    request_type = models.ForeignKey(
        ServiceRequestType,
        on_delete=models.PROTECT,
        related_name='service_requests'
    )
    description = models.TextField()
    additional_details = models.JSONField(default=dict, blank=True)  # For type-specific data
    
    # Assignment and Hierarchy
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
    current_owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='owned_service_requests',
        help_text="Current person responsible for the request"
    )
    
    # Status and Priority
    status = models.CharField(max_length=25, choices=STATUS_CHOICES, default='draft')
    priority = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default='medium')
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    documents_requested_at = models.DateTimeField(null=True, blank=True)
    documents_received_at = models.DateTimeField(null=True, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    
    # Document Requirements
    required_documents_list = models.JSONField(default=list, blank=True)
    documents_complete = models.BooleanField(default=False)
    
    # Resolution Details
    resolution_summary = models.TextField(blank=True)
    client_approved = models.BooleanField(default=False)
    client_approval_date = models.DateTimeField(null=True, blank=True)
    
    # SLA and Tracking
    expected_completion_date = models.DateTimeField(null=True, blank=True)
    sla_breached = models.BooleanField(default=False)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status', 'assigned_to']),
            models.Index(fields=['client', 'status']),
            models.Index(fields=['raised_by', 'created_at']),
        ]
    
    def save(self, *args, **kwargs):
        if not self.request_id:
            self.request_id = self.generate_request_id()
        super().save(*args, **kwargs)
    
    def generate_request_id(self):
        """Generate unique request ID"""
        from datetime import datetime
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        return f"SR{timestamp}"
    
    def submit_request(self, user=None):
        """Submit the request and move to operations tray"""
        if self.status == 'draft':
            self.status = 'submitted'
            self.submitted_at = timezone.now()
            if user:
                self.current_owner = self.assigned_to  # Move to ops
            self.save()
            
            # Add comment
            ServiceRequestComment.objects.create(
                service_request=self,
                comment="Service request submitted to operations team",
                commented_by=user,
                is_internal=True
            )
    
    def request_documents(self, document_list, user=None):
        """Request documents from RM"""
        self.status = 'documents_requested'
        self.documents_requested_at = timezone.now()
        self.required_documents_list = document_list
        self.current_owner = self.raised_by  # Back to RM
        self.save()
        
        # Add comment with document requirements
        comment_text = f"Documents requested: {', '.join(document_list)}"
        ServiceRequestComment.objects.create(
            service_request=self,
            comment=comment_text,
            commented_by=user,
            is_internal=False
        )
    
    def submit_documents(self, user=None):
        """Submit documents back to operations"""
        if self.status == 'documents_requested':
            self.status = 'documents_received'
            self.documents_received_at = timezone.now()
            self.current_owner = self.assigned_to  # Back to ops
            self.save()
            
            ServiceRequestComment.objects.create(
                service_request=self,
                comment="Documents submitted to operations team",
                commented_by=user,
                is_internal=True
            )
    
    def start_processing(self, user=None):
        """Start processing the request"""
        self.status = 'in_progress'
        self.save()
        
        ServiceRequestComment.objects.create(
            service_request=self,
            comment="Request processing started",
            commented_by=user,
            is_internal=True
        )
    
    def resolve_request(self, resolution_summary, user=None):
        """Resolve the request and send back to RM for verification"""
        self.status = 'resolved'
        self.resolved_at = timezone.now()
        self.resolution_summary = resolution_summary
        self.current_owner = self.raised_by  # Back to RM for verification
        self.save()
        
        ServiceRequestComment.objects.create(
            service_request=self,
            comment=f"Request resolved: {resolution_summary}",
            commented_by=user,
            is_internal=False
        )
    
    def client_verification_complete(self, approved=True, user=None):
        """RM confirms client approval"""
        if approved:
            self.status = 'client_verification'
            self.client_approved = True
            self.client_approval_date = timezone.now()
            
            ServiceRequestComment.objects.create(
                service_request=self,
                comment="Client verification completed - approved",
                commented_by=user,
                is_internal=True
            )
        else:
            self.status = 'in_progress'  # Back to processing
            self.current_owner = self.assigned_to
            
            ServiceRequestComment.objects.create(
                service_request=self,
                comment="Client verification failed - requires rework",
                commented_by=user,
                is_internal=True
            )
        
        self.save()
    
    def close_request(self, user=None):
        """Close the request after client approval"""
        if self.client_approved:
            self.status = 'closed'
            self.closed_at = timezone.now()
            self.save()
            
            ServiceRequestComment.objects.create(
                service_request=self,
                comment="Service request closed successfully",
                commented_by=user,
                is_internal=True
            )
        else:
            raise ValidationError("Cannot close request without client approval")
    
    def escalate_to_manager(self, user=None, reason=""):
        """Escalate request to line manager"""
        # Logic to find and assign to manager
        # This would depend on your user hierarchy model
        ServiceRequestComment.objects.create(
            service_request=self,
            comment=f"Request escalated to manager. Reason: {reason}",
            commented_by=user,
            is_internal=True
        )
        self.save()
    
    def can_be_raised_by(self, user):
        """Check if user can raise request for this client"""
        # Implement your mapping logic here
        # RM can only raise to mapped ops exec
        return True  # Placeholder
    
    def can_be_assigned_to(self, user):
        """Check if request can be assigned to this user"""
        # Implement hierarchy and mapping validation
        return True  # Placeholder
    
    def get_next_assignee_if_on_leave(self):
        """Get next assignee if current assignee is on leave"""
        # Implement leave handling logic based on hierarchy
        pass
    
    def is_sla_breached(self):
        """Check if SLA is breached"""
        if self.expected_completion_date and timezone.now() > self.expected_completion_date:
            self.sla_breached = True
            self.save()
            return True
        return False
    
    def __str__(self):
        return f"{self.request_id} - {self.request_type.name} for {self.client.name}"


class ServiceRequestWorkflow(models.Model):
    """
    Track workflow transitions for audit trail
    """
    service_request = models.ForeignKey(
        ServiceRequest,
        on_delete=models.CASCADE,
        related_name='workflow_history'
    )
    from_status = models.CharField(max_length=25, choices=ServiceRequest.STATUS_CHOICES)
    to_status = models.CharField(max_length=25, choices=ServiceRequest.STATUS_CHOICES)
    from_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='workflow_from_transitions'
    )
    to_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='workflow_to_transitions'
    )
    transition_date = models.DateTimeField(auto_now_add=True)
    remarks = models.TextField(blank=True)
    
    class Meta:
        ordering = ['-transition_date']
    
    def __str__(self):
        return f"{self.service_request.request_id}: {self.from_status} → {self.to_status}"


# Pre-populate ServiceRequestType with your specified types
def populate_service_request_types():
    """
    Function to populate initial service request types
    Call this in a data migration or management command
    """
    types_data = [
        # Personal Details Modification
        {'name': 'Email Modification', 'category': 'personal_details', 'code': 'PDM_EMAIL'},
        {'name': 'Mobile Modification', 'category': 'personal_details', 'code': 'PDM_MOBILE'},
        {'name': 'Address Modification', 'category': 'personal_details', 'code': 'PDM_ADDRESS'},
        {'name': 'Bank Details Modification', 'category': 'personal_details', 'code': 'PDM_BANK'},
        {'name': 'Nominee Modification', 'category': 'personal_details', 'code': 'PDM_NOMINEE'},
        {'name': 'Name Change', 'category': 'personal_details', 'code': 'PDM_NAME'},
        {'name': 'Re-KYC', 'category': 'personal_details', 'code': 'PDM_REKYC'},
        
        # Account Creation
        {'name': 'Mutual Fund CAN', 'category': 'account_creation', 'code': 'AC_MF_CAN'},
        {'name': 'MOSL Demat', 'category': 'account_creation', 'code': 'AC_MOSL_DEMAT'},
        {'name': 'PL Demat', 'category': 'account_creation', 'code': 'AC_PL_DEMAT'},
        
        # Account Closure
        {'name': 'MOSL Demat Closure', 'category': 'account_closure', 'code': 'ACL_MOSL_DEMAT'},
        {'name': 'PL Demat Closure', 'category': 'account_closure', 'code': 'ACL_PL_DEMAT'},
        
        # Adhoc Requests - MF
        {'name': 'ARN Change', 'category': 'adhoc_mf', 'code': 'AH_MF_ARN'},
        {'name': 'RI to NRI Conversion', 'category': 'adhoc_mf', 'code': 'AH_MF_RI_NRI'},
        {'name': 'NRI to RI Conversion', 'category': 'adhoc_mf', 'code': 'AH_MF_NRI_RI'},
        {'name': 'Mandate Request Physical', 'category': 'adhoc_mf', 'code': 'AH_MF_MANDATE_PHY'},
        {'name': 'Mandate Request Online', 'category': 'adhoc_mf', 'code': 'AH_MF_MANDATE_ONL'},
        {'name': 'Change of Mapping', 'category': 'adhoc_mf', 'code': 'AH_MF_MAPPING'},
        
        # Adhoc Requests - Demat
        {'name': 'Brokerage Change', 'category': 'adhoc_demat', 'code': 'AH_DM_BROKERAGE'},
        {'name': 'DP Scheme Modification', 'category': 'adhoc_demat', 'code': 'AH_DM_DP_SCHEME'},
        {'name': 'Stock Transfer', 'category': 'adhoc_demat', 'code': 'AH_DM_STOCK_TRANSFER'},
        
        # Report Requests
        {'name': 'Capital Gain Set - MF', 'category': 'report_request', 'code': 'RPT_CG_MF'},
        {'name': 'Capital Gain Set - MOSL', 'category': 'report_request', 'code': 'RPT_CG_MOSL'},
        {'name': 'Capital Gain Set - PL', 'category': 'report_request', 'code': 'RPT_CG_PL'},
        {'name': 'MF SOA', 'category': 'report_request', 'code': 'RPT_MF_SOA'},
        {'name': 'CAS Upload', 'category': 'report_request', 'code': 'RPT_CAS_UPLOAD'},
    ]
    
    for type_data in types_data:
        ServiceRequestType.objects.get_or_create(
            code=type_data['code'],
            defaults=type_data
        )

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
    
# execution_plans/models.py
from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from decimal import Decimal


# models.py - Complete Updated Portfolio Models
import pandas as pd
from django.db import transaction
import logging

logger = logging.getLogger(__name__)

User = get_user_model()

class PortfolioUpload(models.Model):
    """Model to track portfolio file uploads"""
    UPLOAD_STATUS_CHOICES = [
        ('pending', 'Pending Processing'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('partial', 'Partially Processed'),
    ]
    
    upload_id = models.CharField(max_length=20, unique=True, editable=False)
    file = models.FileField(
        upload_to='portfolio_uploads/',
        validators=[FileExtensionValidator(allowed_extensions=['xlsx', 'xls'])]
    )
    uploaded_by = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='portfolio_uploads'
    )
    uploaded_at = models.DateTimeField(default=timezone.now)
    processed_at = models.DateTimeField(null=True, blank=True)
    
    # Processing Status
    status = models.CharField(max_length=15, choices=UPLOAD_STATUS_CHOICES, default='pending')
    total_rows = models.PositiveIntegerField(default=0)
    processed_rows = models.PositiveIntegerField(default=0)
    successful_rows = models.PositiveIntegerField(default=0)
    failed_rows = models.PositiveIntegerField(default=0)
    
    # Processing Details
    processing_log = models.TextField(blank=True)
    error_details = models.JSONField(default=dict, blank=True)
    processing_summary = models.JSONField(default=dict, blank=True)
    
    class Meta:
        ordering = ['-uploaded_at']
        verbose_name = 'Portfolio Upload'
        verbose_name_plural = 'Portfolio Uploads'
    
    def save(self, *args, **kwargs):
        if not self.upload_id:
            self.upload_id = self.generate_upload_id()
        super().save(*args, **kwargs)
    
    def generate_upload_id(self):
        """Generate unique upload ID"""
        from datetime import datetime
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        return f"PU{timestamp}"
    
    def __str__(self):
        return f"{self.upload_id} - {self.file.name} ({self.get_status_display()})"
    
    def create_log(self, row_number, status, message, client_name='', client_pan='', scheme_name='', portfolio_entry=None):
        """
        Create a log entry for this upload
        """
        return PortfolioUploadLog.objects.create(
            upload=self,
            row_number=row_number,
            client_name=client_name,
            client_pan=client_pan,
            scheme_name=scheme_name,
            status=status,
            message=message,
            portfolio_entry=portfolio_entry
        )
    
    def process_upload_with_logging(self):
        """
        Main method to process the uploaded portfolio file with comprehensive logging
        """
        try:
            self.status = 'processing'
            self.save()
            
            # Log start of processing
            self.create_log(
                row_number=0,
                status='success',
                message=f"Started processing upload {self.upload_id} at {timezone.now()}"
            )
            
            # Process the file
            success = self._process_file_with_logging()
            
            if success:
                self.status = 'completed' if self.failed_rows == 0 else 'partial'
                final_message = f"Processing completed. Total: {self.total_rows}, Success: {self.successful_rows}, Failed: {self.failed_rows}"
            else:
                self.status = 'failed'
                final_message = f"Processing failed. Check error logs for details."
            
            self.processed_at = timezone.now()
            self.save()
            
            # Log completion
            self.create_log(
                row_number=0,
                status='success' if success else 'error',
                message=final_message
            )
            
            return success
            
        except Exception as e:
            self.status = 'failed'
            self.error_details = str(e)
            self.processed_at = timezone.now()
            self.save()
            
            # Log the error
            self.create_log(
                row_number=0,
                status='error',
                message=f"Upload processing failed: {str(e)}"
            )
            return False
    
    def _process_file_with_logging(self):
        """
        Process the uploaded CSV/Excel file with detailed logging
        """
        import pandas as pd
        import os
        from django.db import transaction
        
        try:
            # Determine file type and read accordingly
            file_ext = os.path.splitext(self.file.name)[1].lower()
            
            if file_ext == '.csv':
                df = pd.read_csv(self.file.path)
            elif file_ext in ['.xlsx', '.xls']:
                df = pd.read_excel(self.file.path, engine='openpyxl')
            else:
                raise ValueError(f"Unsupported file format: {file_ext}")
            
            self.total_rows = len(df)
            self.save()
            
            # Log file validation success
            self.create_log(
                row_number=0,
                status='success',
                message=f"File validation successful. Found {self.total_rows} rows to process"
            )
            
            # Clean column names
            df.columns = df.columns.str.strip()
            
            # Log column structure
            column_info = f"Columns found: {', '.join(df.columns.tolist())}"
            self.create_log(
                row_number=0,
                status='success',
                message=column_info
            )
            
            # Process each row with individual logging
            with transaction.atomic():
                for index, row in df.iterrows():
                    row_number = index + 1
                    self._process_single_row_with_logging(row, row_number)
                    
                    self.processed_rows += 1
                    
                    # Update progress every 50 rows
                    if self.processed_rows % 50 == 0:
                        self.save()
                        self.create_log(
                            row_number=0,
                            status='success',
                            message=f"Progress update: {self.processed_rows}/{self.total_rows} rows processed"
                        )
            
            # Final save
            self.save()
            
            return True
            
        except Exception as e:
            error_msg = f"File processing error: {str(e)}"
            self.create_log(
                row_number=0,
                status='error',
                message=error_msg
            )
            raise Exception(error_msg)
    
    def _process_single_row_with_logging(self, row, row_number):
        """
        Process a single row and create detailed logs
        """
        try:
            # Extract basic info for logging
            client_name = ClientPortfolio.safe_string_convert(row.get('CLIENT', ''))
            client_pan = ClientPortfolio.safe_string_convert(row.get('CLIENT PAN', ''))
            scheme_name = ClientPortfolio.safe_string_convert(row.get('SCHEME', ''))
            
            # Validate required fields
            if not client_name or not scheme_name:
                self.failed_rows += 1
                self.create_log(
                    row_number=row_number,
                    client_name=client_name,
                    client_pan=client_pan,
                    scheme_name=scheme_name,
                    status='error',
                    message="Missing required fields: client name or scheme name"
                )
                return
            
            if not client_pan or len(client_pan) != 10:
                self.create_log(
                    row_number=row_number,
                    client_name=client_name,
                    client_pan=client_pan,
                    scheme_name=scheme_name,
                    status='warning',
                    message=f"Invalid PAN format: '{client_pan}' (should be 10 characters)"
                )
            
            # Column mapping for portfolio data
            column_mapping = {
                'CLIENT': 'client_name',
                'CLIENT PAN': 'client_pan',
                'SCHEME': 'scheme_name',
                'DEBT': 'debt_value',
                'EQUITY': 'equity_value',
                'HYBRID': 'hybrid_value',
                'LIQUID AND ULTRA SHORT': 'liquid_ultra_short_value',
                'OTHER': 'other_value',
                'ARBITRAGE': 'arbitrage_value',
                'TOTAL': 'total_value',
                'ALLOCATION': 'allocation_percentage',
                'UNITS': 'units',
                'FAMILY HEAD': 'family_head',
                'APP CODE': 'app_code',
                'EQUITY CODE': 'equity_code',
                'OPERATIONS': 'operations_personnel',
                'OPERATIONS CODE': 'operations_code',
                'RELATIONSHIP MANAGER': 'relationship_manager',
                'RELATIONSHIP MANAGER CODE': 'rm_code',
                'SUB BROKER': 'sub_broker',
                'SUB BROKER CODE': 'sub_broker_code',
                'ISIN NO': 'isin_number',
                'CLIENT IWELL CODE': 'client_iwell_code',
                'FAMILY HEAD IWELL CODE': 'family_head_iwell_code'
            }
            
            # Prepare portfolio data
            portfolio_data = {
                'upload_batch': self,
                'data_as_of_date': timezone.now().date(),
                'is_active': True,
                'is_mapped': False
            }
            
            # Map columns with safe conversion
            for excel_col, model_field in column_mapping.items():
                if excel_col in row.index and pd.notna(row[excel_col]):
                    value = row[excel_col]
                    
                    if model_field in [
                        'debt_value', 'equity_value', 'hybrid_value', 
                        'liquid_ultra_short_value', 'other_value', 'arbitrage_value',
                        'total_value', 'allocation_percentage', 'units'
                    ]:
                        portfolio_data[model_field] = ClientPortfolio.safe_decimal_convert(value)
                    else:
                        portfolio_data[model_field] = ClientPortfolio.safe_string_convert(value)
            
            # Create portfolio entry
            portfolio_entry = ClientPortfolio.objects.create(**portfolio_data)
            
            # Log successful creation
            total_value = portfolio_data.get('total_value', 0)
            self.create_log(
                row_number=row_number,
                client_name=client_name,
                client_pan=client_pan,
                scheme_name=scheme_name,
                status='success',
                message=f"Portfolio entry created successfully. Total value: ₹{total_value}",
                portfolio_entry=portfolio_entry
            )
            
            # Try to map to client profile
            mapping_logs = []
            try:
                mapped, message = portfolio_entry.map_to_client_profile()
                if mapped:
                    mapping_logs.append(f"Client mapping: {message}")
                else:
                    mapping_logs.append(f"Client mapping failed: {message}")
                    
                # Try to map personnel
                personnel_mapped = portfolio_entry.map_personnel()
                if personnel_mapped > 0:
                    mapping_logs.append(f"Personnel mapped: {personnel_mapped} users")
                    
            except Exception as mapping_error:
                mapping_logs.append(f"Mapping error: {str(mapping_error)}")
            
            # Log mapping results if any
            if mapping_logs:
                self.create_log(
                    row_number=row_number,
                    client_name=client_name,
                    client_pan=client_pan,
                    scheme_name=scheme_name,
                    status='success',
                    message=f"Mapping results: {'; '.join(mapping_logs)}",
                    portfolio_entry=portfolio_entry
                )
            
            self.successful_rows += 1
            
        except Exception as e:
            self.failed_rows += 1
            error_message = f"Row processing error: {str(e)}"
            
            # Log the specific error
            self.create_log(
                row_number=row_number,
                client_name=client_name if 'client_name' in locals() else '',
                client_pan=client_pan if 'client_pan' in locals() else '',
                scheme_name=scheme_name if 'scheme_name' in locals() else '',
                status='error',
                message=error_message
            )
            
            logger.error(f"Error processing row {row_number}: {e}")

class ClientPortfolio(models.Model):
    """Enhanced client portfolio model with Excel upload support"""
    # Link to client profile
    client_profile = models.ForeignKey(
        'ClientProfile',  # Reference to your existing ClientProfile model
        on_delete=models.CASCADE,
        related_name='portfolio_holdings',
        null=True,
        blank=True
    )
    
    # Excel Data Fields (matching the uploaded structure)
    client_name = models.CharField(max_length=255, help_text="Client name from Excel")
    client_pan = models.CharField(max_length=50, help_text="Client PAN from Excel", db_index=True)
    scheme_name = models.CharField(max_length=300, help_text="Mutual fund scheme name")
    
    # Asset Allocation Values
    debt_value = models.DecimalField(max_digits=15, decimal_places=2, default=0, help_text="Debt allocation value")
    equity_value = models.DecimalField(max_digits=15, decimal_places=2, default=0, help_text="Equity allocation value")
    hybrid_value = models.DecimalField(max_digits=15, decimal_places=2, default=0, help_text="Hybrid allocation value")
    liquid_ultra_short_value = models.DecimalField(max_digits=15, decimal_places=2, default=0, help_text="Liquid & Ultra Short value")
    other_value = models.DecimalField(max_digits=15, decimal_places=2, default=0, help_text="Other category value")
    arbitrage_value = models.DecimalField(max_digits=15, decimal_places=2, default=0, help_text="Arbitrage value")
    
    # Portfolio Details
    total_value = models.DecimalField(max_digits=15, decimal_places=2, default=0, help_text="Total holding value")
    allocation_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=0, help_text="Portfolio allocation %")
    units = models.DecimalField(max_digits=15, decimal_places=4, default=0, help_text="Number of units held")
    
    # Family and Personnel Information
    family_head = models.CharField(max_length=255, blank=True, help_text="Family head name")
    app_code = models.CharField(max_length=50, blank=True, help_text="Application code")
    equity_code = models.CharField(max_length=50, blank=True, help_text="Equity code")
    operations_personnel = models.CharField(max_length=255, blank=True, help_text="Operations personnel")
    operations_code = models.CharField(max_length=50, blank=True, help_text="Operations code")
    relationship_manager = models.CharField(max_length=255, blank=True, help_text="Relationship manager name")
    rm_code = models.CharField(max_length=50, blank=True, help_text="RM code")
    sub_broker = models.CharField(max_length=255, blank=True, help_text="Sub broker name")
    sub_broker_code = models.CharField(max_length=50, blank=True, help_text="Sub broker code")
    
    # Scheme Information
    isin_number = models.CharField(max_length=20, blank=True, help_text="ISIN number of the scheme")
    client_iwell_code = models.CharField(max_length=50, blank=True, help_text="Client iWell code")
    family_head_iwell_code = models.CharField(max_length=50, blank=True, help_text="Family head iWell code")
    
    # Folio Information (additional fields)
    folio_number = models.CharField(max_length=50, blank=True, help_text="Folio number")
    nav_date = models.DateField(null=True, blank=True, help_text="NAV date")
    nav_price = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True, help_text="NAV price")
    cost_value = models.DecimalField(max_digits=15, decimal_places=2, default=0, help_text="Cost value of investment")
    
    # Upload Tracking
    upload_batch = models.ForeignKey(
        PortfolioUpload,
        on_delete=models.CASCADE,
        related_name='portfolio_entries',
        null=True,
        blank=True
    )
    
    # Status and Metadata
    is_active = models.BooleanField(default=True)
    is_mapped = models.BooleanField(default=False, help_text="Is mapped to a client profile")
    mapping_notes = models.TextField(blank=True, help_text="Notes about client mapping")
    
    # Timestamps
    data_as_of_date = models.DateField(default=timezone.now, help_text="Date when this data was valid")
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    
    # Linked Personnel (FK relationships)
    mapped_rm = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        limit_choices_to={'role': 'rm'},
        related_name='portfolio_rm_clients',
        help_text="Mapped RM from User model"
    )
    mapped_ops = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        limit_choices_to={'role__in': ['ops_exec', 'ops_team_lead']},
        related_name='portfolio_ops_clients',
        help_text="Mapped Operations person from User model"
    )
    
    class Meta:
        ordering = ['client_name', 'scheme_name']
        verbose_name = 'Client Portfolio'
        verbose_name_plural = 'Client Portfolios'
        indexes = [
            models.Index(fields=['client_pan', 'scheme_name']),
            models.Index(fields=['client_name']),
            models.Index(fields=['is_mapped', 'client_pan']),
            models.Index(fields=['upload_batch', 'is_mapped']),
        ]
        # Allow multiple entries for same client-scheme combination from different uploads
        # unique_together = ['client_pan', 'scheme_name', 'upload_batch']
    
    def __str__(self):
        return f"{self.client_name} - {self.scheme_name} ({self.client_pan})"
    
    def clean(self):
        """Validate portfolio data"""
        super().clean()
        
        # Validate PAN format
        if self.client_pan and len(self.client_pan) != 10:
            raise ValidationError("PAN number must be 10 characters long")
        
        # Validate that total_value matches sum of category values
        calculated_total = (
            self.debt_value + self.equity_value + self.hybrid_value + 
            self.liquid_ultra_short_value + self.other_value + self.arbitrage_value
        )
        if self.total_value and abs(self.total_value - calculated_total) > 0.01:
            raise ValidationError(
                f"Total value ({self.total_value}) doesn't match sum of category values ({calculated_total})"
            )
    
    def map_to_client_profile(self):
        """Map this portfolio entry to a client profile based on PAN"""
        if self.client_pan:
            try:
                # Import here to avoid circular imports
                from base.models import ClientProfile  # Adjust import based on your app structure
                client_profile = ClientProfile.objects.get(pan_number=self.client_pan)
                
                self.client_profile = client_profile
                self.is_mapped = True
                self.mapping_notes = f"Auto-mapped to {client_profile.client_full_name} on {timezone.now().strftime('%Y-%m-%d %H:%M')}"
                self.save()
                
                return True, f"Successfully mapped to {client_profile.client_full_name}"
                
            except Exception as e:
                if 'DoesNotExist' in str(type(e)):
                    self.mapping_notes = f"No client profile found with PAN {self.client_pan}"
                    self.save()
                    return False, f"No client profile found with PAN {self.client_pan}"
                elif 'MultipleObjectsReturned' in str(type(e)):
                    self.mapping_notes = f"Multiple client profiles found with PAN {self.client_pan}"
                    self.save()
                    return False, f"Multiple client profiles found with PAN {self.client_pan}"
                else:
                    logger.error(f"Error mapping client profile: {e}")
                    return False, f"Error mapping client profile: {str(e)}"
        
        return False, "No PAN number provided"
    
    def map_personnel(self):
        """Map RM and Operations personnel based on names"""
        mapped_count = 0
        
        # Map RM
        if self.relationship_manager:
            try:
                name_parts = self.relationship_manager.strip().split()
                if len(name_parts) >= 1:
                    rm_user = User.objects.filter(
                        role='rm',
                        first_name__icontains=name_parts[0]
                    )
                    if len(name_parts) > 1:
                        rm_user = rm_user.filter(last_name__icontains=name_parts[-1])
                    
                    rm_user = rm_user.first()
                    if rm_user:
                        self.mapped_rm = rm_user
                        mapped_count += 1
            except Exception as e:
                logger.warning(f"Error mapping RM {self.relationship_manager}: {e}")
        
        # Map Operations personnel
        if self.operations_personnel:
            try:
                name_parts = self.operations_personnel.strip().split()
                if len(name_parts) >= 1:
                    ops_user = User.objects.filter(
                        role__in=['ops_exec', 'ops_team_lead'],
                        first_name__icontains=name_parts[0]
                    )
                    if len(name_parts) > 1:
                        ops_user = ops_user.filter(last_name__icontains=name_parts[-1])
                    
                    ops_user = ops_user.first()
                    if ops_user:
                        self.mapped_ops = ops_user
                        mapped_count += 1
            except Exception as e:
                logger.warning(f"Error mapping operations personnel {self.operations_personnel}: {e}")
        
        if mapped_count > 0:
            self.save()
        
        return mapped_count
    
    @property
    def gain_loss(self):
        """Calculate gain/loss if cost value is available"""
        if self.cost_value and self.cost_value > 0:
            return self.total_value - self.cost_value
        return None
    
    @property
    def gain_loss_percentage(self):
        """Calculate gain/loss percentage"""
        if self.cost_value and self.cost_value > 0:
            return ((self.total_value - self.cost_value) / self.cost_value) * 100
        return None
    
    @property
    def primary_asset_class(self):
        """Determine primary asset class based on highest allocation"""
        values = {
            'Debt': self.debt_value,
            'Equity': self.equity_value,
            'Hybrid': self.hybrid_value,
            'Liquid/Ultra Short': self.liquid_ultra_short_value,
            'Other': self.other_value,
            'Arbitrage': self.arbitrage_value,
        }
        
        if max(values.values()) > 0:
            return max(values, key=values.get)
        return 'Unknown'
    
    @classmethod
    def safe_decimal_convert(cls, value, default=0):
        """Safely convert values to Decimal for Django DecimalField"""
        if value is None or pd.isna(value):
            return Decimal(str(default))
        
        # Handle string values
        if isinstance(value, str):
            # Remove common formatting characters
            value = value.replace(',', '').replace('₹', '').replace('$', '').strip()
            if not value:
                return Decimal(str(default))
        
        try:
            return Decimal(str(float(value)))
        except (ValueError, TypeError):
            logger.warning(f"Could not convert decimal value: {value} (type: {type(value)})")
            return Decimal(str(default))
    
    @classmethod
    def safe_string_convert(cls, value):
        """Safely convert values to string, handling NaN and None"""
        if value is None or pd.isna(value):
            return ''
        
        if isinstance(value, (int, float)):
            if pd.isna(value):
                return ''
            return str(value)
        
        return str(value).strip()
    
    @classmethod
    def process_excel_file(cls, file_path, upload_instance):
        """Process Excel file and create portfolio entries with enhanced error handling"""
        results = {
            'total_rows': 0,
            'processed_rows': 0,
            'successful_rows': 0,
            'failed_rows': 0,
            'errors': [],
            'summary': {}
        }
        
        try:
            # Read Excel file with better handling
            df = pd.read_excel(file_path, engine='openpyxl')
            results['total_rows'] = len(df)
            
            # Clean column names (remove extra spaces)
            df.columns = df.columns.str.strip()
            
            # Column mapping based on the Excel structure
            column_mapping = {
                'CLIENT': 'client_name',
                'CLIENT PAN': 'client_pan',
                'SCHEME': 'scheme_name',
                'DEBT': 'debt_value',
                ' DEBT': 'debt_value',
                'EQUITY': 'equity_value',
                ' EQUITY': 'equity_value',
                'HYBRID': 'hybrid_value',
                ' HYBRID': 'hybrid_value',
                'LIQUID AND ULTRA SHORT': 'liquid_ultra_short_value',
                ' LIQUID AND  ULTRA  SHORT': 'liquid_ultra_short_value',
                'OTHER': 'other_value',
                ' OTHER': 'other_value',
                'ARBITRAGE': 'arbitrage_value',
                ' ARBITRAGE': 'arbitrage_value',
                'TOTAL': 'total_value',
                'ALLOCATION': 'allocation_percentage',
                'UNITS': 'units',
                'FAMILY HEAD': 'family_head',
                'APP CODE': 'app_code',
                'EQUITY CODE': 'equity_code',
                'OPERATIONS': 'operations_personnel',
                ' OPERATIONS': 'operations_personnel',
                'OPERATIONS CODE': 'operations_code',
                ' OPERATIONS CODE': 'operations_code',
                'RELATIONSHIP MANAGER': 'relationship_manager',
                ' RELATIONSHIP  MANAGER': 'relationship_manager',
                'RELATIONSHIP MANAGER CODE': 'rm_code',
                ' RELATIONSHIP  MANAGER CODE': 'rm_code',
                'SUB BROKER': 'sub_broker',
                ' SUB  BROKER': 'sub_broker',
                'SUB BROKER CODE': 'sub_broker_code',
                ' SUB  BROKER CODE': 'sub_broker_code',
                'ISIN NO': 'isin_number',
                'CLIENT IWELL CODE': 'client_iwell_code',
                'FAMILY HEAD IWELL CODE': 'family_head_iwell_code'
            }
            
            # Process each row
            with transaction.atomic():
                for index, row in df.iterrows():
                    try:
                        results['processed_rows'] += 1
                        
                        # Prepare data for portfolio entry
                        portfolio_data = {
                            'upload_batch': upload_instance,
                            'data_as_of_date': timezone.now().date(),
                            'is_active': True,
                            'is_mapped': False
                        }
                        
                        # Map columns with safe conversion
                        for excel_col, model_field in column_mapping.items():
                            if excel_col in row.index and pd.notna(row[excel_col]):
                                value = row[excel_col]
                                
                                # Handle different data types
                                if model_field in [
                                    'debt_value', 'equity_value', 'hybrid_value', 
                                    'liquid_ultra_short_value', 'other_value', 'arbitrage_value',
                                    'total_value', 'allocation_percentage', 'units'
                                ]:
                                    portfolio_data[model_field] = cls.safe_decimal_convert(value)
                                else:
                                    portfolio_data[model_field] = cls.safe_string_convert(value)
                        
                        # Validate required fields
                        if not portfolio_data.get('client_name') or not portfolio_data.get('scheme_name'):
                            results['failed_rows'] += 1
                            results['errors'].append(f"Row {index + 2}: Missing client name or scheme name")
                            continue
                        
                        # Create portfolio entry
                        portfolio_entry = cls.objects.create(**portfolio_data)
                        
                        # Try to map to client profile
                        try:
                            mapped, message = portfolio_entry.map_to_client_profile()
                            # Try to map personnel
                            personnel_mapped = portfolio_entry.map_personnel()
                        except Exception as mapping_error:
                            logger.warning(f"Mapping failed for row {index + 2}: {mapping_error}")
                        
                        results['successful_rows'] += 1
                        
                    except Exception as e:
                        results['failed_rows'] += 1
                        error_msg = f"Row {index + 2}: {str(e)}"
                        results['errors'].append(error_msg)
                        logger.error(f"Error processing row {index + 2}: {e}")
            
            # Update summary
            results['summary'] = {
                'unique_clients': cls.objects.filter(upload_batch=upload_instance).values('client_pan').distinct().count(),
                'unique_schemes': cls.objects.filter(upload_batch=upload_instance).values('scheme_name').distinct().count(),
                'mapped_clients': cls.objects.filter(upload_batch=upload_instance, is_mapped=True).count(),
                'total_aum': cls.objects.filter(upload_batch=upload_instance).aggregate(
                    total=models.Sum('total_value')
                )['total'] or 0
            }
            
        except Exception as e:
            results['errors'].append(f"File processing error: {str(e)}")
            results['failed_rows'] = results.get('total_rows', 0)
            logger.error(f"File processing failed: {e}")
        
        return results

class PortfolioUploadLog(models.Model):
    """Enhanced log model with auto row number generation"""
    upload = models.ForeignKey(
        PortfolioUpload,
        on_delete=models.CASCADE,
        related_name='processing_logs'
    )
    row_number = models.PositiveIntegerField(
        help_text="Row number in the uploaded file (0 for system messages)"
    )
    client_name = models.CharField(max_length=255, blank=True)
    client_pan = models.CharField(max_length=50, blank=True)
    scheme_name = models.CharField(max_length=300, blank=True)
    
    STATUS_CHOICES = [
        ('success', 'Success'),
        ('error', 'Error'),
        ('warning', 'Warning'),
    ]
    
    status = models.CharField(max_length=10, choices=STATUS_CHOICES)
    message = models.TextField()
    portfolio_entry = models.ForeignKey(
        ClientPortfolio,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='upload_logs'
    )
    created_at = models.DateTimeField(default=timezone.now)
    
    class Meta:
        ordering = ['upload', 'row_number', 'created_at']
        verbose_name = 'Portfolio Upload Log'
        verbose_name_plural = 'Portfolio Upload Logs'
        indexes = [
            models.Index(fields=['upload', 'status']),
            models.Index(fields=['upload', 'row_number']),
        ]
    
    def __str__(self):
        if self.row_number == 0:
            return f"{self.upload.upload_id} - System Log ({self.get_status_display()})"
        return f"{self.upload.upload_id} - Row {self.row_number} ({self.get_status_display()})"

class MutualFundScheme(models.Model):
    """Enhanced mutual fund scheme model"""
    scheme_name = models.CharField(max_length=300)  # Increased length
    amc_name = models.CharField(max_length=100)
    scheme_code = models.CharField(max_length=50, unique=True)
    isin_number = models.CharField(max_length=20, unique=True, null=True, blank=True)
    
    scheme_type = models.CharField(max_length=50, choices=[
        ('equity', 'Equity'),
        ('debt', 'Debt'),
        ('hybrid', 'Hybrid'),
        ('liquid', 'Liquid'),
        ('ultra_short', 'Ultra Short'),
        ('elss', 'ELSS'),
        ('index', 'Index'),
        ('etf', 'ETF'),
        ('arbitrage', 'Arbitrage'),
        ('other', 'Other'),
    ])
    
    # Asset allocation from portfolio data
    primary_asset_class = models.CharField(max_length=50, blank=True)
    risk_category = models.CharField(max_length=20, choices=[
        ('low', 'Low'),
        ('moderate', 'Moderate'),
        ('high', 'High'),
        ('very_high', 'Very High'),
    ], default='moderate')
    
    # Investment limits
    minimum_investment = models.DecimalField(max_digits=10, decimal_places=2, default=500.00)
    minimum_sip = models.DecimalField(max_digits=10, decimal_places=2, default=500.00)
    
    # Status and tracking
    is_active = models.BooleanField(default=True)
    last_nav_date = models.DateField(null=True, blank=True)
    last_nav_price = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True)
    
    # Metadata
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['amc_name', 'scheme_name']
        verbose_name = 'Mutual Fund Scheme'
        verbose_name_plural = 'Mutual Fund Schemes'
    
    def __str__(self):
        return f"{self.amc_name} - {self.scheme_name}"
    
    @classmethod
    def create_from_portfolio_data(cls, scheme_name, isin_number=None):
        """Create scheme from portfolio data if it doesn't exist"""
        try:
            if isin_number:
                scheme = cls.objects.get(isin_number=isin_number)
            else:
                scheme = cls.objects.get(scheme_name=scheme_name)
            return scheme
        except cls.DoesNotExist:
            # Try to parse AMC name and scheme type from scheme name
            amc_name = scheme_name.split()[0] if scheme_name else 'Unknown'
            
            # Determine scheme type based on name
            scheme_type = 'other'
            name_lower = scheme_name.lower()
            if any(word in name_lower for word in ['equity', 'growth', 'large', 'mid', 'small', 'cap']):
                scheme_type = 'equity'
            elif any(word in name_lower for word in ['debt', 'bond', 'income']):
                scheme_type = 'debt'
            elif any(word in name_lower for word in ['hybrid', 'balanced']):
                scheme_type = 'hybrid'
            elif any(word in name_lower for word in ['liquid']):
                scheme_type = 'liquid'
            elif any(word in name_lower for word in ['elss', 'tax']):
                scheme_type = 'elss'
            
            # Generate scheme code
            scheme_code = isin_number or f"AUTO_{scheme_name[:20].replace(' ', '_').upper()}"
            
            return cls.objects.create(
                scheme_name=scheme_name,
                amc_name=amc_name,
                scheme_code=scheme_code,
                isin_number=isin_number,
                scheme_type=scheme_type,
                primary_asset_class=scheme_type.title()
            )
        except cls.MultipleObjectsReturned:
            # Return the first one if multiple exist
            if isin_number:
                return cls.objects.filter(isin_number=isin_number).first()
            else:
                return cls.objects.filter(scheme_name=scheme_name).first()

# Legacy ClientPortfolio compatibility for existing execution plans
class LegacyClientPortfolio(models.Model):
    """Legacy client portfolio model for backward compatibility"""
    client = models.ForeignKey(
        'Client',
        on_delete=models.CASCADE,
        related_name='legacy_portfolio'
    )
    scheme = models.ForeignKey(
        MutualFundScheme,
        on_delete=models.CASCADE,
        related_name='legacy_holdings'
    )
    folio_number = models.CharField(max_length=50, blank=True)
    units = models.DecimalField(max_digits=15, decimal_places=4, default=0)
    current_value = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    cost_value = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    sip_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    sip_date = models.PositiveIntegerField(null=True, blank=True, help_text="SIP date (1-28)")
    last_updated = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ['client', 'scheme', 'folio_number']
        ordering = ['client', 'scheme']
        verbose_name = 'Legacy Client Portfolio'
        verbose_name_plural = 'Legacy Client Portfolios'
    
    def __str__(self):
        return f"{self.client.name} - {self.scheme.scheme_name}"
    
    @property
    def gain_loss(self):
        return self.current_value - self.cost_value
    
    @property
    def gain_loss_percentage(self):
        if self.cost_value > 0:
            return ((self.current_value - self.cost_value) / self.cost_value) * 100
        return 0

class ExecutionPlan(models.Model):
    """Main execution plan model"""
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('pending_approval', 'Pending Approval'),
        ('approved', 'Approved'),
        ('client_approved', 'Client Approved'),
        ('in_execution', 'In Execution'),
        ('completed', 'Completed'),
        ('rejected', 'Rejected'),
        ('cancelled', 'Cancelled'),
    ]
    
    # Basic Information
    plan_id = models.CharField(max_length=20, unique=True, editable=False)
    client = models.ForeignKey(
        'base.Client',
        on_delete=models.CASCADE,
        related_name='execution_plans'
    )
    plan_name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    
    # Assignment and Approval
    created_by = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='created_execution_plans',
        limit_choices_to={'role__in': ['rm', 'rm_head']}
    )
    approved_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='approved_execution_plans',
        limit_choices_to={'role__in': ['rm_head', 'business_head']}
    )
    
    # Status and Timeline
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    client_approved_at = models.DateTimeField(null=True, blank=True)
    execution_started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    
    # File Management
    excel_file = models.FileField(
        upload_to='execution_plans/excel/',
        null=True,
        blank=True,
        help_text="Generated Excel file for the plan"
    )
    
    # Metadata
    notes = models.TextField(blank=True)
    rejection_reason = models.TextField(blank=True)
    client_communication_sent = models.BooleanField(default=False)
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Execution Plan'
        verbose_name_plural = 'Execution Plans'
        permissions = [
            ('can_approve_execution_plan', 'Can approve execution plans'),
            ('can_execute_plan', 'Can execute approved plans'),
        ]
    
    def save(self, *args, **kwargs):
        if not self.plan_id:
            self.plan_id = self.generate_plan_id()
        super().save(*args, **kwargs)
    
    def generate_plan_id(self):
        """Generate unique plan ID in format EPYYYYMMDDXXXX"""
        from datetime import datetime
        date_part = datetime.now().strftime("%Y%m%d")
        last_plan = ExecutionPlan.objects.filter(
            plan_id__startswith=f"EP{date_part}"
        ).order_by('-plan_id').first()
        
        if last_plan:
            last_num = int(last_plan.plan_id[-4:])
            new_num = last_num + 1
        else:
            new_num = 1
            
        return f"EP{date_part}{new_num:04d}"
    
    def __str__(self):
        return f"{self.plan_id} - {self.plan_name} ({self.client.name})"
    
    def get_filename(self):
        """Generate Excel filename"""
        date_str = self.created_at.strftime('%d%m%Y')
        return f"{self.client.name}_ExecutionPlan_{date_str}.xlsx"
    
    def can_be_approved_by(self, user):
        """Check if user can approve this plan"""
        if user.role not in ['rm_head', 'business_head', 'top_management']:
            return False
        
        # RM Head can approve plans created by their team RMs
        if user.role == 'rm_head':
            return self.created_by.manager == user
        
        # Business Head and Top Management can approve any plan
        return True
    
    def can_be_executed_by(self, user):
        """Check if user can execute this plan"""
        return user.role in ['ops_exec', 'ops_team_lead'] and self.status == 'client_approved'
    
    def submit_for_approval(self):
        """Submit plan for approval"""
        if self.status == 'draft':
            self.status = 'pending_approval'
            self.submitted_at = timezone.now()
            self.save()
            return True
        return False
    
    def approve(self, approved_by):
        """Approve the plan"""
        if self.status == 'pending_approval' and self.can_be_approved_by(approved_by):
            self.status = 'approved'
            self.approved_by = approved_by
            self.approved_at = timezone.now()
            self.save()
            return True
        return False
    
    def reject(self, rejected_by, reason):
        """Reject the plan"""
        if self.status == 'pending_approval' and self.can_be_approved_by(rejected_by):
            self.status = 'rejected'
            self.rejection_reason = reason
            self.approved_by = rejected_by
            self.approved_at = timezone.now()
            self.save()
            return True
        return False
    
    def mark_client_approved(self):
        """Mark as client approved"""
        if self.status == 'approved':
            self.status = 'client_approved'
            self.client_approved_at = timezone.now()
            self.save()
            return True
        return False
    
    def start_execution(self, executor):
        """Start plan execution"""
        if self.status == 'client_approved' and self.can_be_executed_by(executor):
            self.status = 'in_execution'
            self.execution_started_at = timezone.now()
            self.save()
            return True
        return False
    
    def complete_execution(self):
        """Complete plan execution"""
        if self.status == 'in_execution':
            # Check if all actions are completed
            pending_actions = self.actions.filter(status__in=['pending', 'in_progress'])
            if not pending_actions.exists():
                self.status = 'completed'
                self.completed_at = timezone.now()
                self.save()
                return True
        return False

class PlanAction(models.Model):
    """Individual actions within an execution plan"""
    ACTION_TYPES = [
        ('purchase', 'Purchase'),
        ('redemption', 'Redemption'),
        ('sip_start', 'SIP Start'),
        ('sip_modify', 'SIP Modify'),
        ('sip_stop', 'SIP Stop'),
        ('switch', 'Switch'),
        ('stp_start', 'STP Start'),
        ('stp_stop', 'STP Stop'),
        ('swp_start', 'SWP Start'),
        ('swp_stop', 'SWP Stop'),
    ]
    
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
    ]
    
    execution_plan = models.ForeignKey(
        ExecutionPlan,
        on_delete=models.CASCADE,
        related_name='actions'
    )
    action_type = models.CharField(max_length=20, choices=ACTION_TYPES)
    scheme = models.ForeignKey(
        MutualFundScheme,
        on_delete=models.CASCADE,
        related_name='plan_actions'
    )
    
    # Action Details
    amount = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal('0.01'))]
    )
    units = models.DecimalField(
        max_digits=15,
        decimal_places=4,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal('0.0001'))]
    )
    sip_date = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="SIP date (1-28)"
    )
    
    # For Switch/STP operations
    target_scheme = models.ForeignKey(
        MutualFundScheme,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='target_actions',
        help_text="Target scheme for switch/STP"
    )
    
    # Execution Details
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default='pending')
    priority = models.PositiveIntegerField(default=1, help_text="Execution priority (1=highest)")
    executed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='executed_actions',
        limit_choices_to={'role__in': ['ops_exec', 'ops_team_lead']}
    )
    executed_at = models.DateTimeField(null=True, blank=True)
    
    # Transaction Details (post-execution)
    transaction_id = models.CharField(max_length=100, blank=True)
    executed_amount = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        null=True,
        blank=True
    )
    executed_units = models.DecimalField(
        max_digits=15,
        decimal_places=4,
        null=True,
        blank=True
    )
    nav_price = models.DecimalField(
        max_digits=10,
        decimal_places=4,
        null=True,
        blank=True
    )
    
    # Notes and Documentation
    notes = models.TextField(blank=True)
    failure_reason = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['priority', 'created_at']
        verbose_name = 'Plan Action'
        verbose_name_plural = 'Plan Actions'
    
    def __str__(self):
        return f"{self.get_action_type_display()} - {self.scheme.scheme_name}"
    
    def clean(self):
        """Validate action data"""
        super().clean()
        
        # Validate amount or units is provided
        if not self.amount and not self.units:
            raise ValidationError("Either amount or units must be specified")
        
        # Validate SIP actions have SIP date
        if self.action_type in ['sip_start', 'sip_modify'] and not self.sip_date:
            raise ValidationError("SIP date is required for SIP actions")
        
        # Validate switch/STP actions have target scheme
        if self.action_type in ['switch', 'stp_start'] and not self.target_scheme:
            raise ValidationError("Target scheme is required for switch/STP actions")
        
        # Validate SIP date range
        if self.sip_date and not (1 <= self.sip_date <= 28):
            raise ValidationError("SIP date must be between 1 and 28")
    
    def execute(self, executor, transaction_details=None):
        """Execute the action"""
        if self.status != 'pending':
            return False
        
        if not self.execution_plan.can_be_executed_by(executor):
            return False
        
        self.status = 'in_progress'
        self.executed_by = executor
        self.save()
        
        # Here you would integrate with actual transaction systems
        # For now, we'll simulate execution
        try:
            # Simulate transaction processing
            self.status = 'completed'
            self.executed_at = timezone.now()
            
            if transaction_details:
                self.transaction_id = transaction_details.get('transaction_id', '')
                self.executed_amount = transaction_details.get('amount', self.amount)
                self.executed_units = transaction_details.get('units', self.units)
                self.nav_price = transaction_details.get('nav_price')
            
            self.save()
            
            # Check if all actions in plan are completed
            self.execution_plan.complete_execution()
            
            return True
            
        except Exception as e:
            self.status = 'failed'
            self.failure_reason = str(e)
            self.save()
            return False
    
    def mark_failed(self, reason, failed_by=None):
        """Mark action as failed"""
        self.status = 'failed'
        self.failure_reason = reason
        if failed_by:
            self.executed_by = failed_by
        self.executed_at = timezone.now()
        self.save()
    
    def can_be_cancelled(self):
        """Check if action can be cancelled"""
        return self.status in ['pending', 'in_progress']
    
    def cancel(self, cancelled_by, reason=""):
        """Cancel the action"""
        if self.can_be_cancelled():
            self.status = 'cancelled'
            self.failure_reason = reason
            self.executed_by = cancelled_by
            self.executed_at = timezone.now()
            self.save()
            return True
        return False

class PlanWorkflowHistory(models.Model):
    """Track workflow history for audit trail"""
    execution_plan = models.ForeignKey(
        ExecutionPlan,
        on_delete=models.CASCADE,
        related_name='workflow_history'
    )
    from_status = models.CharField(max_length=20, choices=ExecutionPlan.STATUS_CHOICES)
    to_status = models.CharField(max_length=20, choices=ExecutionPlan.STATUS_CHOICES)
    changed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='plan_status_changes'
    )
    changed_at = models.DateTimeField(auto_now_add=True)
    comments = models.TextField(blank=True)
    
    class Meta:
        ordering = ['-changed_at']
        verbose_name = 'Plan Workflow History'
        verbose_name_plural = 'Plan Workflow Histories'
    
    def __str__(self):
        return f"{self.execution_plan.plan_id}: {self.from_status} → {self.to_status}"

class PlanComment(models.Model):
    """Comments and discussions on execution plans"""
    execution_plan = models.ForeignKey(
        ExecutionPlan,
        on_delete=models.CASCADE,
        related_name='comments'
    )
    comment = models.TextField()
    commented_by = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='plan_comments'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    is_internal = models.BooleanField(
        default=True,
        help_text="Internal comment (not visible to client)"
    )
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Plan Comment'
        verbose_name_plural = 'Plan Comments'
    
    def __str__(self):
        return f"Comment by {self.commented_by.username} on {self.execution_plan.plan_id}"

class PlanTemplate(models.Model):
    """Pre-defined plan templates for common scenarios"""
    name = models.CharField(max_length=200)
    description = models.TextField()
    created_by = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='created_templates'
    )
    is_active = models.BooleanField(default=True)
    is_public = models.BooleanField(
        default=False,
        help_text="Available to all RMs"
    )
    template_data = models.JSONField(
        help_text="Template structure and default values"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['name']
        verbose_name = 'Plan Template'
        verbose_name_plural = 'Plan Templates'
    
    def __str__(self):
        return self.name
    
    def can_be_used_by(self, user):
        """Check if user can use this template"""
        return self.is_public or self.created_by == user or user.role in ['rm_head', 'business_head']

class ExecutionMetrics(models.Model):
    """Track execution metrics for reporting"""
    execution_plan = models.OneToOneField(
        ExecutionPlan,
        on_delete=models.CASCADE,
        related_name='metrics'
    )
    
    # Time Metrics (in hours)
    time_to_approval = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Hours from creation to approval"
    )
    time_to_client_approval = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Hours from approval to client approval"
    )
    time_to_execution = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Hours from client approval to execution start"
    )
    total_execution_time = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Hours from execution start to completion"
    )
    
    # Business Metrics
    total_investment_amount = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=0
    )
    total_redemption_amount = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=0
    )
    net_investment = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=0
    )
    sip_count = models.PositiveIntegerField(default=0)
    total_monthly_sip = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0
    )
    
    # Execution Success Rate
    total_actions = models.PositiveIntegerField(default=0)
    successful_actions = models.PositiveIntegerField(default=0)
    failed_actions = models.PositiveIntegerField(default=0)
    
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = 'Execution Metrics'
        verbose_name_plural = 'Execution Metrics'
    
    def __str__(self):
        return f"Metrics for {self.execution_plan.plan_id}"
    
    def calculate_metrics(self):
        """Calculate all metrics for the execution plan"""
        plan = self.execution_plan
        
        # Time metrics
        if plan.submitted_at and plan.approved_at:
            self.time_to_approval = (plan.approved_at - plan.submitted_at).total_seconds() / 3600
        
        if plan.approved_at and plan.client_approved_at:
            self.time_to_client_approval = (plan.client_approved_at - plan.approved_at).total_seconds() / 3600
        
        if plan.client_approved_at and plan.execution_started_at:
            self.time_to_execution = (plan.execution_started_at - plan.client_approved_at).total_seconds() / 3600
        
        if plan.execution_started_at and plan.completed_at:
            self.total_execution_time = (plan.completed_at - plan.execution_started_at).total_seconds() / 3600
        
        # Business metrics
        purchase_actions = plan.actions.filter(action_type='purchase', status='completed')
        redemption_actions = plan.actions.filter(action_type='redemption', status='completed')
        sip_actions = plan.actions.filter(action_type__in=['sip_start', 'sip_modify'], status='completed')
        
        self.total_investment_amount = sum(action.executed_amount or action.amount or 0 for action in purchase_actions)
        self.total_redemption_amount = sum(action.executed_amount or action.amount or 0 for action in redemption_actions)
        self.net_investment = self.total_investment_amount - self.total_redemption_amount
        
        self.sip_count = sip_actions.count()
        self.total_monthly_sip = sum(action.executed_amount or action.amount or 0 for action in sip_actions)
        
        # Success metrics
        all_actions = plan.actions.all()
        self.total_actions = all_actions.count()
        self.successful_actions = all_actions.filter(status='completed').count()
        self.failed_actions = all_actions.filter(status='failed').count()
        
        self.save()
    
    @property
    def success_rate(self):
        """Calculate success rate percentage"""
        if self.total_actions > 0:
            return (self.successful_actions / self.total_actions) * 100
        return 0
    
    
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.core.management import call_command
from threading import Thread

@receiver(post_save, sender=PortfolioUpload)
def auto_process_portfolio_upload(sender, instance, created, **kwargs):
    """
    Automatically start processing when a new portfolio upload is created
    """
    if created and instance.status == 'pending':
        # Log the trigger
        instance.create_log(
            row_number=0,
            status='success',
            message=f"Upload {instance.upload_id} queued for automatic processing"
        )
        
        # Process in background thread to avoid blocking the request
        def process_in_background():
            try:
                instance.process_upload_with_logging()
            except Exception as e:
                logger.error(f"Auto-processing failed for {instance.upload_id}: {e}")
        
        # Start background processing
        thread = Thread(target=process_in_background)
        thread.daemon = True
        thread.start()