from django.db import models
from django.contrib.auth.models import AbstractUser, Group
from django.conf import settings
from django.core.exceptions import ValidationError

# Define User roles as constants
ROLE_CHOICES = (
    ('top_management', 'Top Management'),
    ('business_head', 'Business Head'),
    ('rm_head', 'RM Head'),
    ('rm', 'Relationship Manager'),
)

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
    managed_teams = models.ManyToManyField(
        Group,
        blank=True,
        related_name='team_leaders',
        help_text="Teams managed by this RM Head"
    )

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

    def get_team_members(self):
        """Get all team members for RM Heads"""
        if self.role == 'rm_head':
            # Get RMs in the same groups as this RM Head
            return User.objects.filter(
                role='rm',
                groups__in=self.groups.all()
            ).distinct()
        return User.objects.none()

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

    def __str__(self):
        return f"{self.username} ({self.get_role_display()})"


class Team(models.Model):
    """Represents a team structure for better organization"""
    name = models.CharField(max_length=100, unique=True)
    head = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        limit_choices_to={'role': 'rm_head'},
        related_name='led_teams'
    )
    description = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return self.name


from django.db import models
from django.utils import timezone
from django.core.validators import MinValueValidator, MaxValueValidator
from django.conf import settings


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
    
    # Lead Identification
    lead_id = models.CharField(max_length=20, unique=True, editable=False, null=True, blank=True)
    client_id = models.CharField(max_length=20, blank=True, null=True, unique=True)
    
    # Basic Information
    name = models.CharField(max_length=255)
    email = models.EmailField(blank=True, null=True)
    mobile = models.CharField(max_length=15, null=True, blank=True)
    
    # Lead Source
    source = models.CharField(max_length=50, choices=SOURCE_CHOICES,null=True, blank=True)
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
    
    def generate_client_id(self):
        """Generate a unique client ID when lead is converted"""
        from datetime import datetime
        date_part = datetime.now().strftime("%Y%m%d")
        last_client = Lead.objects.filter(client_id__startswith=f"CL{date_part}").order_by('-client_id').first()
        
        if last_client:
            last_num = int(last_client.client_id[-4:])
            new_num = last_num + 1
        else:
            new_num = 1
            
        return f"CL{date_part}{new_num:04d}"
    
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
        
        # TODO: Send notification to line manager
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
    lead = models.OneToOneField(
        Lead,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='client'
    )
    name = models.CharField(max_length=255)
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