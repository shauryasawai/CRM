# models.py - Fixed version with single ServiceRequest model

from django.db import models
from django.contrib.auth.models import AbstractUser, Group
from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.core.validators import MinValueValidator, MaxValueValidator, FileExtensionValidator
import pandas as pd
from django.db import transaction
import logging
from decimal import Decimal
from django.dispatch import receiver 
import pandas as pd
from threading import Thread
from django.db.models.signals import post_save
from django.db.models import Q

logger = logging.getLogger(__name__)

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
            return User.objects.filter(
                role='rm',
                teams__leader=self
                ).distinct()
        elif self.role == 'business_head_ops':
            return User.objects.filter(
            role__in=['ops_team_lead', 'ops_exec'],
            manager__in=[self] + list(self.subordinates.all())
        ).distinct()
        elif self.role == 'ops_team_lead':
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
        elif self.role == 'rm_head':
            # Can access own data and team members' data
            if target_user == self:
                return True
            # Check if target user is in any of the teams this RM Head leads
            return target_user in self.get_team_members()
        elif self.role == 'ops_team_lead':
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


####SCHEME PROCESSING

import pandas as pd

class SchemeUploadLog(models.Model):
    """Log entries for scheme upload processing"""
    upload = models.ForeignKey(
        'SchemeUpload',  # Use string reference since SchemeUpload is defined later
        on_delete=models.CASCADE,
        related_name='processing_logs'
    )
    row_number = models.PositiveIntegerField(
        help_text="Row number in the uploaded file (0 for system messages)"
    )
    amc_name = models.CharField(max_length=255, blank=True)
    scheme_name = models.CharField(max_length=500, blank=True)
    
    STATUS_CHOICES = [
        ('success', 'Success'),
        ('error', 'Error'),
        ('warning', 'Warning'),
    ]
    
    status = models.CharField(max_length=10, choices=STATUS_CHOICES)
    message = models.TextField()
    scheme = models.ForeignKey(
        'MutualFundScheme',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='upload_logs'
    )
    created_at = models.DateTimeField(default=timezone.now)
    
    class Meta:
        ordering = ['upload', 'row_number', 'created_at']
        verbose_name = 'Scheme Upload Log'
        verbose_name_plural = 'Scheme Upload Logs'
    
    def __str__(self):
        if self.row_number == 0:
            return f"{self.upload.upload_id} - System Log ({self.get_status_display()})"
        return f"{self.upload.upload_id} - Row {self.row_number} ({self.get_status_display()})"
    
class SchemeUpload(models.Model):
    """Model to track scheme master file uploads"""
    UPLOAD_STATUS_CHOICES = [
        ('pending', 'Pending Processing'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('partial', 'Partially Processed'),
        ('archived', 'Archived'),
    ]
    
    upload_id = models.CharField(max_length=20, unique=True, editable=False)
    file = models.FileField(
        upload_to='scheme_uploads/',
        validators=[FileExtensionValidator(allowed_extensions=['xlsx', 'xls'])]
    )
    uploaded_by = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='scheme_uploads'
    )
    uploaded_at = models.DateTimeField(default=timezone.now)
    processed_at = models.DateTimeField(null=True, blank=True)
    
    # Processing Status
    status = models.CharField(max_length=15, choices=UPLOAD_STATUS_CHOICES, default='pending')
    total_rows = models.PositiveIntegerField(default=0)
    processed_rows = models.PositiveIntegerField(default=0)
    successful_rows = models.PositiveIntegerField(default=0)
    failed_rows = models.PositiveIntegerField(default=0)
    updated_rows = models.PositiveIntegerField(default=0)
    
    # Processing Details
    processing_log = models.TextField(blank=True)
    error_details = models.JSONField(default=dict, blank=True)
    processing_summary = models.JSONField(default=dict, blank=True)
    
    # Options
    update_existing = models.BooleanField(
        default=True, 
        help_text="Update existing schemes if found"
    )
    mark_missing_inactive = models.BooleanField(
        default=False,
        help_text="Mark schemes not in upload as inactive"
    )
    
    # Archive fields
    is_archived = models.BooleanField(default=False, help_text="Mark as archived instead of deleting")
    archived_at = models.DateTimeField(null=True, blank=True)
    archived_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='archived_uploads'
    )
    
    class Meta:
        ordering = ['-uploaded_at']
        verbose_name = 'Scheme Upload'
        verbose_name_plural = 'Scheme Uploads'
    
    def save(self, *args, **kwargs):
        if not self.upload_id:
            self.upload_id = self.generate_upload_id()
        super().save(*args, **kwargs)
    
    def generate_upload_id(self):
        """Generate unique upload ID"""
        from datetime import datetime
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        return f"SU{timestamp}"
    
    def __str__(self):
        return f"{self.upload_id} - {self.file.name} ({self.get_status_display()})"
    
    def create_log(self, row_number, status, message, amc_name='', scheme_name='', scheme=None):
        """Create a log entry for this upload"""
        return SchemeUploadLog.objects.create(
            upload=self,
            row_number=row_number,
            amc_name=amc_name,
            scheme_name=scheme_name,
            status=status,
            message=message,
            scheme=scheme
        )
    
    def process_upload_with_logging(self):
        """Main method to process the uploaded scheme file"""
        import os
        
        try:
            self.status = 'processing'
            self.save()
            
            # Log start
            self.create_log(0, 'success', f"Started processing upload {self.upload_id}")
            
            # Check if file exists
            if not self.file or not os.path.exists(self.file.path):
                raise Exception(f"File not found: {self.file.path if self.file else 'No file attached'}")
            
            # Read Excel file
            try:
                # Try reading with header=1 (row 2 as header)
                df = pd.read_excel(self.file.path, engine='openpyxl', header=1)
                self.create_log(0, 'success', f"Successfully read Excel file with {len(df)} rows")
            except Exception as e:
                self.create_log(0, 'error', f"Failed to read Excel file: {str(e)}")
                raise
            
            # Remove any completely empty rows
            df = df.dropna(how='all')
            
            # Check if we have data
            if df.empty:
                raise Exception("Excel file contains no data rows")
            
            self.total_rows = len(df)
            self.save()
            
            self.create_log(0, 'success', f"Found {self.total_rows} rows to process")
            
            # Log column information
            columns_found = list(df.columns)
            self.create_log(0, 'success', f"Columns found: {', '.join(columns_found)}")
            
            # Expected columns based on your Excel file
            expected_columns = [
                'AMC Name',
                'Scheme NAV Name', 
                'Category',
                'ISIN Div Payout / ISIN Growth',
                'ISIN Div Reinvestment'
            ]
            
            # Check if required columns exist
            missing_columns = []
            for col in expected_columns:
                if col not in df.columns:
                    missing_columns.append(col)
            
            if missing_columns:
                error_msg = f"Missing required columns: {', '.join(missing_columns)}"
                self.create_log(0, 'error', error_msg)
                raise Exception(error_msg)
            
            self.create_log(0, 'success', f"Column validation successful")
            
            # Process each row
            for index, row in df.iterrows():
                try:
                    self._process_single_scheme_row(row, index + 1)
                    self.processed_rows += 1
                    
                    # Save progress every 100 rows
                    if self.processed_rows % 100 == 0:
                        self.save()
                        self.create_log(0, 'success', f"Progress: {self.processed_rows}/{self.total_rows} rows processed")
                        
                except Exception as row_error:
                    # Log the error but continue processing
                    self.create_log(index + 1, 'error', f"Row processing failed: {str(row_error)}")
                    self.failed_rows += 1
                    continue
            
            # Mark missing schemes as inactive if requested
            if self.mark_missing_inactive:
                self._mark_missing_schemes_inactive()
            
            # Complete processing
            if self.failed_rows == 0:
                self.status = 'completed'
            else:
                self.status = 'partial'
            
            self.processed_at = timezone.now()
            self.save()
            
            success_msg = f"Processing completed. Success: {self.successful_rows}, Failed: {self.failed_rows}, Updated: {self.updated_rows}"
            self.create_log(0, 'success', success_msg)
            
            return True
            
        except Exception as e:
            error_msg = f"Processing failed: {str(e)}"
            
            self.status = 'failed'
            self.processed_at = timezone.now()
            self.error_details = {'error': str(e)}
            self.save()
            
            self.create_log(0, 'error', error_msg)
            return False
    
def _process_single_scheme_row(self, row, row_number):
    """Process a single scheme row"""
    try:
        # Extract data with better error handling
        amc_name = self._safe_string_convert(row.get('AMC Name', ''))
        scheme_name = self._safe_string_convert(row.get('Scheme NAV Name', ''))
        category = self._safe_string_convert(row.get('Category', ''))
        isin_growth = self._safe_string_convert(row.get('ISIN Div Payout / ISIN Growth', ''))
        isin_div = self._safe_string_convert(row.get('ISIN Div Reinvestment', ''))
        
        # Validate required fields
        if not amc_name or not scheme_name:
            self.failed_rows += 1
            self.create_log(row_number, 'error', 
                f"Missing required fields - AMC: '{amc_name}', Scheme: '{scheme_name}'", 
                amc_name, scheme_name)
            return
        
        # Generate scheme code
        scheme_code = self._generate_scheme_code(amc_name, scheme_name, isin_growth)
        
        # Determine scheme type
        scheme_type = self._categorize_scheme_type(category)
        
        # Check if scheme exists with enhanced search methods
        existing_scheme = None
        search_method = ""
        
        # Method 1: Search by ISIN Growth
        if isin_growth:
            try:
                existing_scheme = MutualFundScheme.objects.get(isin_growth=isin_growth)
                search_method = f"ISIN Growth: {isin_growth}"
            except MutualFundScheme.DoesNotExist:
                pass
            except MutualFundScheme.MultipleObjectsReturned:
                # Handle duplicate ISINs
                existing_scheme = MutualFundScheme.objects.filter(isin_growth=isin_growth).first()
                search_method = f"ISIN Growth (multiple found): {isin_growth}"
        
        # Method 2: Search by exact Scheme NAV Name
        if not existing_scheme:
            try:
                existing_scheme = MutualFundScheme.objects.get(scheme_name__iexact=scheme_name)
                search_method = f"Scheme NAV Name (exact): {scheme_name}"
            except MutualFundScheme.DoesNotExist:
                pass
            except MutualFundScheme.MultipleObjectsReturned:
                existing_scheme = MutualFundScheme.objects.filter(scheme_name__iexact=scheme_name).first()
                search_method = f"Scheme NAV Name (multiple found): {scheme_name}"
        
        # Method 3: Search by AMC Name + Scheme NAV Name combination
        if not existing_scheme:
            try:
                existing_scheme = MutualFundScheme.objects.get(
                    amc_name__iexact=amc_name,
                    scheme_name__iexact=scheme_name
                )
                search_method = f"AMC + Scheme NAV Name: {amc_name} - {scheme_name}"
            except MutualFundScheme.DoesNotExist:
                pass
            except MutualFundScheme.MultipleObjectsReturned:
                existing_scheme = MutualFundScheme.objects.filter(
                    amc_name__iexact=amc_name,
                    scheme_name__iexact=scheme_name
                ).first()
                search_method = f"AMC + Scheme NAV Name (multiple found): {amc_name} - {scheme_name}"
        
        # Method 4: Fuzzy search by Scheme NAV Name (if enabled)
        if not existing_scheme and hasattr(self, 'enable_fuzzy_search') and self.enable_fuzzy_search:
            fuzzy_matches = self._fuzzy_search_by_scheme_name(scheme_name)
            if fuzzy_matches:
                existing_scheme = fuzzy_matches[0]
                search_method = f"Scheme NAV Name (fuzzy match): {scheme_name} -> {existing_scheme.scheme_name}"
        
        # Prepare scheme data
        scheme_data = {
            'amc_name': amc_name,
            'scheme_name': scheme_name,
            'category': category,
            'scheme_type': scheme_type,
            'isin_growth': isin_growth if isin_growth else None,
            'isin_div_reinvestment': isin_div if isin_div else None,
            'scheme_code': scheme_code,
            'is_active': True,
            'last_updated': timezone.now(),
            'upload_batch': self
        }
        
        if existing_scheme and self.update_existing:
            # Update existing scheme
            for field, value in scheme_data.items():
                if field != 'upload_batch':  # Don't change upload_batch for existing
                    setattr(existing_scheme, field, value)
            existing_scheme.save()
            
            self.updated_rows += 1
            self.create_log(row_number, 'success', 
                f"Updated existing scheme ({search_method})", 
                amc_name, scheme_name, existing_scheme)
            
        elif existing_scheme and not self.update_existing:
            # Skip existing scheme
            self.create_log(row_number, 'warning', 
                f"Skipped existing scheme ({search_method}) - update disabled", 
                amc_name, scheme_name)
            
        else:
            # Create new scheme
            new_scheme = MutualFundScheme.objects.create(**scheme_data)
            
            self.successful_rows += 1
            self.create_log(row_number, 'success', 
                f"Created new scheme - Code: {scheme_code}", 
                amc_name, scheme_name, new_scheme)
        
    except Exception as e:
        self.failed_rows += 1
        error_message = f"Row processing error: {str(e)}"
        
        self.create_log(row_number, 'error', error_message,
            amc_name if 'amc_name' in locals() else '',
            scheme_name if 'scheme_name' in locals() else '')
        
        logger.error(f"Error processing row {row_number}: {e}")

def _fuzzy_search_by_scheme_name(self, scheme_name, similarity_threshold=0.8):
    """
    Perform fuzzy search on scheme names using string similarity
    Returns list of matching schemes ordered by similarity
    """
    from difflib import SequenceMatcher
    
    # Get all schemes to compare against
    all_schemes = MutualFundScheme.objects.all()
    matches = []
    
    for scheme in all_schemes:
        # Calculate similarity ratio
        similarity = SequenceMatcher(None, scheme_name.lower(), scheme.scheme_name.lower()).ratio()
        
        if similarity >= similarity_threshold:
            matches.append((scheme, similarity))
    
    # Sort by similarity (highest first)
    matches.sort(key=lambda x: x[1], reverse=True)
    
    # Return just the scheme objects
    return [match[0] for match in matches]

def _safe_string_convert(self, value):
    """Safely convert values to string, handling NaN and None"""
    if value is None:
        return ''
    
    if pd.isna(value):
        return ''
    
    # Convert to string and strip whitespace
    result = str(value).strip()
    
    # Handle 'nan' string
    if result.lower() == 'nan':
        return ''
        
    return result

def _apply_scheme_nav_name_filter(self, queryset, search_term):
    """
    Apply search filter based on Scheme NAV Name column
    Supports exact match, partial match, and case-insensitive search
    """
    if not search_term:
        return queryset
    
    # Clean the search term
    search_term = search_term.strip()
    
    # Apply multiple search strategies
    return queryset.filter(
        Q(scheme_name__icontains=search_term) |  # Partial match (case-insensitive)
        Q(scheme_name__iexact=search_term) |     # Exact match (case-insensitive)
        Q(scheme_name__istartswith=search_term) | # Starts with (case-insensitive)
        Q(scheme_name__iendswith=search_term)     # Ends with (case-insensitive)
    ).distinct()

def get_filtered_schemes_by_nav_name(self, nav_name_filter=None):
    """
    Get schemes filtered by Scheme NAV Name
    """
    queryset = MutualFundScheme.objects.all()
    
    if nav_name_filter:
        queryset = self._apply_scheme_nav_name_filter(queryset, nav_name_filter)
    
    return queryset.order_by('amc_name', 'scheme_name')
    
    def _categorize_scheme_type(self, category):
        """Categorize scheme type based on category"""
        if not category:
            return 'other'
        
        category_lower = category.lower()
        if 'equity' in category_lower:
            return 'equity'
        elif 'debt' in category_lower:
            return 'debt'
        elif 'hybrid' in category_lower:
            return 'hybrid'
        elif 'liquid' in category_lower:
            return 'liquid'
        elif 'ultra short' in category_lower:
            return 'ultra_short'
        elif 'elss' in category_lower:
            return 'elss'
        elif 'index' in category_lower:
            return 'index'
        elif 'etf' in category_lower:
            return 'etf'
        elif 'arbitrage' in category_lower:
            return 'arbitrage'
        else:
            return 'other'
    
    def _generate_scheme_code(self, amc_name, scheme_name, isin=None):
        """Generate unique scheme code"""
        if isin:
            return isin
        
        # Create from AMC and scheme name
        amc_prefix = ''.join([c for c in amc_name.upper() if c.isalnum()])[:4]
        scheme_suffix = ''.join([c for c in scheme_name.upper() if c.isalnum()])[:8]
        base_code = f"{amc_prefix}_{scheme_suffix}"
        
        # Ensure uniqueness
        counter = 1
        code = base_code
        while MutualFundScheme.objects.filter(scheme_code=code).exists():
            code = f"{base_code}_{counter}"
            counter += 1
        
        return code
    
    def _mark_missing_schemes_inactive(self):
        """Mark schemes not in current upload as inactive"""
        if self.successful_rows > 0:
            # Get all scheme codes from this upload
            upload_logs = self.processing_logs.filter(
                status='success',
                scheme__isnull=False
            ).values_list('scheme__scheme_code', flat=True)
            
            # Mark others as inactive
            inactive_count = MutualFundScheme.objects.exclude(
                scheme_code__in=upload_logs
            ).update(is_active=False)
            
            self.create_log(0, 'success', 
                f"Marked {inactive_count} schemes as inactive (not in current upload)")
    
    # Archive and delete methods
    def archive(self, user):
        """Archive instead of delete"""
        self.is_archived = True
        self.archived_at = timezone.now()
        self.archived_by = user
        self.status = 'archived'
        self.save()
        
        # Clear upload_batch reference from schemes
        MutualFundScheme.objects.filter(upload_batch=self).update(upload_batch=None)
        return True
    
    def can_be_deleted(self):
        """Check if upload can be safely deleted"""
        scheme_count = MutualFundScheme.objects.filter(upload_batch=self).count()
        return scheme_count == 0
    
    def safe_delete(self, user):
        """Safely delete or archive the upload"""
        if self.can_be_deleted():
            self.delete()
            return True, "Upload deleted successfully"
        else:
            self.archive(user)
            return False, "Upload archived (schemes still reference this upload)"
    
    def delete(self, using=None, keep_parents=False):
        """Override delete to handle large datasets safely"""
        from django.db import transaction
        
        # Clear foreign key references first in batches
        with transaction.atomic():
            batch_size = 1000
            while True:
                scheme_batch = list(
                    self.uploaded_schemes.all()[:batch_size]
                )
                if not scheme_batch:
                    break
                
                scheme_ids = [scheme.id for scheme in scheme_batch]
                MutualFundScheme.objects.filter(
                    id__in=scheme_ids
                ).update(upload_batch=None)
        
        return super().delete(using=using, keep_parents=keep_parents)


@receiver(post_save, sender=SchemeUpload)
def auto_process_scheme_upload(sender, instance, created, **kwargs):
    """Safely process uploads without transaction conflicts"""
    if created and instance.status == 'pending':
        try:
            # Use transaction.on_commit to defer processing until after the current transaction
            transaction.on_commit(lambda: process_upload_deferred(instance.id))
        except Exception as e:
            logger.error(f"Error scheduling upload processing for {instance.upload_id}: {e}")

def process_upload_deferred(upload_id):
    """Process upload after transaction commit"""
    try:
        upload = SchemeUpload.objects.get(id=upload_id)
        if upload.status == 'pending':
            upload.create_log(0, 'success', f"Upload {upload.upload_id} starting deferred processing")
            upload.process_upload_with_logging()
    except SchemeUpload.DoesNotExist:
        logger.error(f"Upload with id {upload_id} not found for deferred processing")
    except Exception as e:
        logger.error(f"Deferred processing failed for upload id {upload_id}: {e}")
        try:
            upload = SchemeUpload.objects.get(id=upload_id)
            upload.status = 'failed'
            upload.error_details = {'error': str(e)}
            upload.save()
        except:
            pass
            
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

# Service Request Models - Fixed to avoid duplicate definitions

class ServiceRequestType(models.Model):
    """
    Service Request Type categorization with essential fields only
    """
    CATEGORY_CHOICES = (
        ('personal_details', 'Personal Details Modification'),
        ('account_creation', 'Account Creation'),
        ('account_closure', 'Account Closure Request'),
        ('adhoc_mf', 'Adhoc Requests - Mutual Fund'),
        ('adhoc_demat', 'Adhoc Requests - Demat'),
        ('report_request', 'Report Request'),
        ('general', 'General Request'),
    )
    
    PRIORITY_CHOICES = (
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
        ('urgent', 'Urgent'),
    )
    
    # Basic Information
    name = models.CharField(max_length=100)
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES)
    code = models.CharField(max_length=20, unique=True)
    description = models.TextField(blank=True)
    
    # Essential Configuration
    is_active = models.BooleanField(default=True)
    default_priority = models.CharField(
        max_length=10, 
        choices=PRIORITY_CHOICES, 
        default='medium'
    )
    requires_approval = models.BooleanField(
        default=False, 
        help_text="Requires manager approval"
    )
    
    # SLA
    sla_hours = models.PositiveIntegerField(
        default=48, 
        help_text="Standard SLA in hours"
    )
    
    # Document Requirements
    required_documents = models.JSONField(
        default=list, 
        blank=True,
        help_text="List of required document types"
    )
    
    # Assignment
    department = models.CharField(
        max_length=50, 
        choices=[
            ('operations', 'Operations'),
            ('compliance', 'Compliance'),
            ('relationship', 'Relationship Management'),
        ],
        default='operations'
    )
    
    # Instructions
    internal_instructions = models.TextField(
        blank=True,
        help_text="Processing instructions for operations team"
    )
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['category', 'name']
        verbose_name = 'Service Request Type'
        verbose_name_plural = 'Service Request Types'
        indexes = [
            models.Index(fields=['category', 'is_active']),
            models.Index(fields=['code']),
        ]
    
    def __str__(self):
        return f"{self.name} ({self.get_category_display()})"
    
    def clean(self):
        """Basic validation"""
        super().clean()
        if self.sla_hours <= 0:
            raise ValidationError("SLA hours must be greater than 0")
    
    def save(self, *args, **kwargs):
        # Auto-generate code if not provided
        if not self.code:
            self.code = self.generate_code()
        super().save(*args, **kwargs)
    
    def generate_code(self):
        """Generate a unique code based on category and name"""
        category_prefix = self.category.upper()[:3]
        name_prefix = ''.join([word[0].upper() for word in self.name.split()[:2]])
        base_code = f"{category_prefix}_{name_prefix}"
        
        # Ensure uniqueness
        counter = 1
        code = base_code
        while ServiceRequestType.objects.filter(code=code).exists():
            code = f"{base_code}_{counter}"
            counter += 1
        
        return code
    
    def can_be_raised_by_role(self, role):
        """Check if a role can raise this type of request"""
        role_permissions = {
            'rm': ['personal_details', 'account_creation', 'report_request', 'general'],
            'rm_head': ['personal_details', 'account_creation', 'account_closure', 'report_request', 'general'],
            'ops_exec': ['adhoc_mf', 'adhoc_demat'],
            'ops_team_lead': ['adhoc_mf', 'adhoc_demat', 'compliance'],
            'business_head': list(dict(self.CATEGORY_CHOICES).keys()),
            'business_head_ops': ['adhoc_mf', 'adhoc_demat', 'compliance'],
            'top_management': list(dict(self.CATEGORY_CHOICES).keys()),
        }
        
        allowed_categories = role_permissions.get(role, [])
        return self.category in allowed_categories

class ServiceRequestIDCounter(models.Model):
    """Counter model to generate unique sequential service request IDs"""
    date_key = models.DateField(unique=True, help_text="Date for which this counter applies")
    current_value = models.PositiveIntegerField(default=0, help_text="Current counter value for this date")
    
    class Meta:
        verbose_name = 'Service Request ID Counter'
        verbose_name_plural = 'Service Request ID Counters'
    
    @classmethod
    def get_next_sequence(cls, date_key):
        """Get next sequence number for given date"""
        from django.db import transaction
        
        with transaction.atomic():
            counter, created = cls.objects.select_for_update().get_or_create(
                date_key=date_key,
                defaults={'current_value': 1}
            )
            if not created:
                counter.current_value += 1
                counter.save()
            
            return counter.current_value
    
    def __str__(self):
        return f"Counter for {self.date_key}: {self.current_value}"

class ServiceRequest(models.Model):
    """
    Service Request Model with complete workflow support
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
        Client,
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
    additional_details = models.JSONField(default=dict, blank=True)
    
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
            models.Index(fields=['request_id']),
        ]
        verbose_name = 'Service Request'
        verbose_name_plural = 'Service Requests'
    
    def save(self, *args, **kwargs):
        if not self.request_id:
            self.request_id = self.generate_request_id()
        super().save(*args, **kwargs)
    
    def generate_request_id(self):
        """Generate unique request ID using date-based counter"""
        from datetime import datetime
        
        # Get current date
        today = datetime.now().date()
        date_str = today.strftime("%Y%m%d")
        
        # Get next sequence number for today
        sequence = ServiceRequestIDCounter.get_next_sequence(today)
        
        # Format: SR + YYYYMMDD + 4-digit sequence
        return f"SR{date_str}{sequence:04d}"
    
    def submit_request(self, user=None):
        """Submit the request and move to operations tray"""
        if self.status == 'draft':
            self.status = 'submitted'
            self.submitted_at = timezone.now()
            if user:
                self.current_owner = self.assigned_to  # Move to ops
            self.save()
            return True
        return False
    
    def request_documents(self, document_list, user=None):
        """Request documents from RM"""
        self.status = 'documents_requested'
        self.documents_requested_at = timezone.now()
        self.required_documents_list = document_list
        self.current_owner = self.raised_by  # Back to RM
        self.save()
        return True
    
    def submit_documents(self, user=None):
        """Submit documents back to operations"""
        if self.status == 'documents_requested':
            self.status = 'documents_received'
            self.documents_received_at = timezone.now()
            self.current_owner = self.assigned_to  # Back to ops
            self.save()
            return True
        return False
    
    def start_processing(self, user=None):
        """Start processing the request"""
        self.status = 'in_progress'
        self.save()
        return True
    
    def resolve_request(self, resolution_summary, user=None):
        """Resolve the request and send back to RM for verification"""
        self.status = 'resolved'
        self.resolved_at = timezone.now()
        self.resolution_summary = resolution_summary
        self.current_owner = self.raised_by  # Back to RM for verification
        self.save()
        return True
    
    def client_verification_complete(self, approved=True, user=None):
        """RM confirms client approval"""
        if approved:
            self.status = 'client_verification'
            self.client_approved = True
            self.client_approval_date = timezone.now()
        else:
            self.status = 'in_progress'  # Back to processing
            self.current_owner = self.assigned_to
        
        self.save()
        return True
    
    def close_request(self, user=None):
        """Close the request after client approval"""
        if self.client_approved:
            self.status = 'closed'
            self.closed_at = timezone.now()
            self.save()
            return True
        else:
            raise ValidationError("Cannot close request without client approval")
    
    def escalate_to_manager(self, user=None, reason=""):
        """Escalate request to line manager"""
        # Logic to find and assign to manager would go here
        self.save()
        return True
    
    def can_be_raised_by(self, user):
        """Check if user can raise request for this client"""
        # Implement your mapping logic here
        return True  # Placeholder
    
    def can_be_assigned_to(self, user):
        """Check if request can be assigned to this user"""
        # Implement hierarchy and mapping validation
        return True  # Placeholder
    
    def is_sla_breached(self):
        """Check if SLA is breached"""
        if self.expected_completion_date and timezone.now() > self.expected_completion_date:
            self.sla_breached = True
            self.save()
            return True
        return False
    
    def get_age_in_hours(self):
        """Get request age in hours"""
        if self.created_at:
            delta = timezone.now() - self.created_at
            return delta.total_seconds() / 3600
        return 0
    
    def get_sla_remaining_hours(self):
        """Get remaining SLA hours"""
        if self.request_type and self.created_at:
            sla_deadline = self.created_at + timezone.timedelta(hours=self.request_type.sla_hours)
            remaining = sla_deadline - timezone.now()
            return max(0, remaining.total_seconds() / 3600)
        return 0
    
    def __str__(self):
        return f"{self.request_id} - {self.request_type.name} for {self.client.name}"

class ServiceRequestDocument(models.Model):
    """
    Documents attached to service requests
    """
    service_request = models.ForeignKey(
        ServiceRequest,
        on_delete=models.CASCADE,
        related_name='documents'
    )
    document = models.FileField(
        upload_to='service_requests/documents/',
        validators=[FileExtensionValidator(allowed_extensions=['pdf', 'doc', 'docx', 'jpg', 'jpeg', 'png', 'xlsx', 'xls'])]
    )
    document_name = models.CharField(max_length=255)
    document_type = models.CharField(
        max_length=50,
        blank=True,
        help_text="Type of document (e.g., 'identity_proof', 'bank_statement')"
    )
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='uploaded_service_documents'
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)
    file_size = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="File size in bytes"
    )
    is_verified = models.BooleanField(default=False)
    verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='verified_service_documents'
    )
    verified_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        ordering = ['-uploaded_at']
        verbose_name = 'Service Request Document'
        verbose_name_plural = 'Service Request Documents'
    
    def save(self, *args, **kwargs):
        if self.document:
            self.file_size = self.document.size
            if not self.document_name:
                self.document_name = self.document.name
        super().save(*args, **kwargs)
    
    def __str__(self):
        return f"Document: {self.document_name} for {self.service_request.request_id}"
    
    def get_file_size_display(self):
        """Return human readable file size"""
        if self.file_size:
            if self.file_size < 1024:
                return f"{self.file_size} bytes"
            elif self.file_size < 1024 * 1024:
                return f"{self.file_size / 1024:.1f} KB"
            else:
                return f"{self.file_size / (1024 * 1024):.1f} MB"
        return "Unknown"

class ServiceRequestComment(models.Model):
    """
    Comments/remarks for service requests
    """
    service_request = models.ForeignKey(
        ServiceRequest,
        on_delete=models.CASCADE,
        related_name='comments'
    )
    comment = models.TextField()
    commented_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='service_request_comments'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_internal = models.BooleanField(
        default=False, 
        help_text="Internal ops comments vs client-facing"
    )
    comment_type = models.CharField(
        max_length=20,
        choices=[
            ('general', 'General Comment'),
            ('status_update', 'Status Update'),
            ('document_request', 'Document Request'),
            ('escalation', 'Escalation'),
            ('resolution', 'Resolution'),
            ('client_communication', 'Client Communication'),
        ],
        default='general'
    )
    
    # For replies/threading
    parent_comment = models.ForeignKey(
        'self',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='replies'
    )
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Service Request Comment'
        verbose_name_plural = 'Service Request Comments'
        indexes = [
            models.Index(fields=['service_request', 'created_at']),
            models.Index(fields=['commented_by', 'created_at']),
        ]
    
    def __str__(self):
        comment_preview = self.comment[:50] + "..." if len(self.comment) > 50 else self.comment
        return f"Comment by {self.commented_by} on {self.service_request.request_id}: {comment_preview}"
    
    def is_reply(self):
        """Check if this comment is a reply to another comment"""
        return self.parent_comment is not None
    
    def get_replies(self):
        """Get all replies to this comment"""
        return self.replies.all()

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
    auto_transition = models.BooleanField(
        default=False,
        help_text="Was this an automatic transition?"
    )
    
    class Meta:
        ordering = ['-transition_date']
        verbose_name = 'Service Request Workflow'
        verbose_name_plural = 'Service Request Workflows'
        indexes = [
            models.Index(fields=['service_request', 'transition_date']),
        ]
    
    def __str__(self):
        return f"{self.service_request.request_id}: {self.from_status} → {self.to_status}"
    
    @classmethod
    def log_transition(cls, service_request, from_status, to_status, user=None, remarks="", auto=False):
        """Create a workflow log entry"""
        return cls.objects.create(
            service_request=service_request,
            from_status=from_status,
            to_status=to_status,
            from_user=user,
            to_user=service_request.current_owner,
            remarks=remarks,
            auto_transition=auto
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

# Portfolio and Execution Plan Models

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
            self.error_details = {'error': str(e)}
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
        import os
        
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
        ClientProfile,
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
                # Try to find client profile by PAN
                client_profile = ClientProfile.objects.get(pan_number=self.client_pan)
                
                self.client_profile = client_profile
                self.is_mapped = True
                self.mapping_notes = f"Auto-mapped to {client_profile.client_full_name} on {timezone.now().strftime('%Y-%m-%d %H:%M')}"
                self.save()
                
                return True, f"Successfully mapped to {client_profile.client_full_name}"
                
            except ClientProfile.DoesNotExist:
                self.mapping_notes = f"No client profile found with PAN {self.client_pan}"
                self.save()
                return False, f"No client profile found with PAN {self.client_pan}"
            except ClientProfile.MultipleObjectsReturned:
                self.mapping_notes = f"Multiple client profiles found with PAN {self.client_pan}"
                self.save()
                return False, f"Multiple client profiles found with PAN {self.client_pan}"
            except Exception as e:
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
    
    def __str__(self):
        if self.row_number == 0:
            return f"{self.upload.upload_id} - System Log ({self.get_status_display()})"
        return f"{self.upload.upload_id} - Row {self.row_number} ({self.get_status_display()})"

class MutualFundScheme(models.Model):
    """Enhanced mutual fund scheme model with upload support"""
    scheme_name = models.CharField(max_length=500)  # Increased length for long scheme names
    amc_name = models.CharField(max_length=200)     # Increased length for AMC names
    scheme_code = models.CharField(max_length=50, unique=True)
    
    # ISIN fields based on Excel structure
    isin_growth = models.CharField(
        max_length=20, 
        unique=True, 
        null=True, 
        blank=True,
        help_text="ISIN for Growth/Div Payout option"
    )
    isin_div_reinvestment = models.CharField(
        max_length=20, 
        unique=True, 
        null=True, 
        blank=True,
        help_text="ISIN for Dividend Reinvestment option"
    )
    
    # Category from Excel
    category = models.CharField(
        max_length=100, 
        blank=True,
        help_text="Category as per AMFI classification"
    )
    
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
    
    # Risk and investment details
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
    
    # Upload tracking
    upload_batch = models.ForeignKey(
        SchemeUpload,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='uploaded_schemes'
    )
    last_updated = models.DateTimeField(default=timezone.now)
    
    # Metadata
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['amc_name', 'scheme_name']
        verbose_name = 'Mutual Fund Scheme'
        verbose_name_plural = 'Mutual Fund Schemes'
        indexes = [
            models.Index(fields=['amc_name', 'scheme_name']),
            models.Index(fields=['scheme_code']),
            models.Index(fields=['isin_growth']),
            models.Index(fields=['category', 'scheme_type']),
            models.Index(fields=['is_active']),
        ]
    
    def __str__(self):
        return f"{self.amc_name} - {self.scheme_name}"
    
    def clean(self):
        """Validate scheme data"""
        super().clean()
        
        # Validate ISIN format (basic)
        for isin_field in [self.isin_growth, self.isin_div_reinvestment]:
            if isin_field and len(isin_field) != 12:
                raise ValidationError(f"ISIN {isin_field} must be 12 characters long")
    
    def get_primary_isin(self):
        """Get the primary ISIN (prefer growth over div reinvestment)"""
        return self.isin_growth or self.isin_div_reinvestment
    
    def has_multiple_options(self):
        """Check if scheme has multiple ISIN options"""
        return bool(self.isin_growth and self.isin_div_reinvestment)
    
    def get_scheme_display_name(self):
        """Get a clean display name for the scheme"""
        # Remove common suffixes for display
        name = self.scheme_name
        suffixes_to_remove = [
            '- DIRECT - IDCW',
            '- REGULAR - IDCW', 
            '- Direct Plan-Growth',
            '- Regular Plan-Growth',
            '- DIRECT - MONTHLY IDCW',
            '- REGULAR - MONTHLY IDCW'
        ]
        
        for suffix in suffixes_to_remove:
            if name.endswith(suffix):
                name = name[:-len(suffix)].strip()
                break
        
        return name
    
    @classmethod
    def get_schemes_by_amc(cls, amc_name):
        """Get all active schemes for a given AMC"""
        return cls.objects.filter(amc_name__iexact=amc_name, is_active=True)
    
    @classmethod
    def get_schemes_by_category(cls, category):
        """Get all active schemes for a given category"""
        return cls.objects.filter(category__icontains=category, is_active=True)
    
    @classmethod
    def search_schemes(cls, query):
        """Search schemes by name, AMC, or ISIN"""
        return cls.objects.filter(
            models.Q(scheme_name__icontains=query) |
            models.Q(amc_name__icontains=query) |
            models.Q(isin_growth__icontains=query) |
            models.Q(isin_div_reinvestment__icontains=query),
            is_active=True
        )

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
        Client,
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
    rejected_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='rejected_execution_plans'
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
    rejected_at = models.DateTimeField(null=True, blank=True)
    
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
    
    def save(self, *args, **kwargs):
        if not self.plan_id:
            self.plan_id = self.generate_plan_id()
        super().save(*args, **kwargs)
        
    def approve(self, approved_by):
        """Approve the execution plan"""
        from django.utils import timezone
        
        if self.status != 'pending_approval':
            return False
        
        if not self.can_be_approved_by(approved_by):
            return False
        
        self.status = 'approved'
        self.approved_by = approved_by
        self.approved_at = timezone.now()
        self.save()
        return True
    
    def reject(self, rejected_by, reason):
        """Reject the execution plan"""
        from django.utils import timezone
        
        if self.status != 'pending_approval':
            return False
        
        if not self.can_be_approved_by(rejected_by):
            return False
        
        self.status = 'rejected'
        self.rejected_by = rejected_by
        self.rejected_at = timezone.now()
        self.rejection_reason = reason
        self.save()
        return True
    
    def submit_for_approval(self, submitted_by=None):
        """Submit plan for approval"""
        from django.utils import timezone
        
        if self.status != 'draft':
            return False
        
        if submitted_by and self.created_by != submitted_by:
            return False
        
        self.status = 'pending_approval'
        self.submitted_at = timezone.now()
        self.save()
        return True
    
    def mark_client_approved(self, user=None):
        """Mark as client approved"""
        from django.utils import timezone
        
        if self.status != 'approved':
            return False
        
        if user and self.created_by != user:
            return False
        
        self.status = 'client_approved'
        self.client_approved_at = timezone.now()
        self.save()
        return True
    
    def start_execution(self, user=None):
        """Start execution"""
        from django.utils import timezone
        
        if self.status != 'client_approved':
            return False
        
        self.status = 'in_execution'
        self.execution_started_at = timezone.now()
        self.save()
        return True
    
    def complete_execution(self, user=None):
        """Mark execution as completed"""
        from django.utils import timezone
        
        if self.status != 'in_execution':
            return False
        
        self.status = 'completed'
        self.completed_at = timezone.now()
        self.save()
        return True
    
    # Essential Permission Methods (to fix the error)
    def can_be_approved_by(self, user):
        """Check if user can approve this execution plan"""
        if self.status != 'pending_approval':
            return False
        
        # User cannot approve their own plan
        if self.created_by == user:
            return False
        
        # Check user role
        if hasattr(user, 'role'):
            if user.role in ['top_management', 'business_head', 'business_head_ops']:
                return True
            elif user.role == 'rm_head':
                # RM Head can approve plans from their subordinates
                return getattr(self.created_by, 'manager', None) == user
        
        return False
    
    def can_be_executed_by(self, user):
        """Check if user can execute this plan"""
        if self.status not in ['client_approved', 'in_execution']:
            return False
        
        if hasattr(user, 'role'):
            return user.role in ['ops_exec', 'ops_team_lead', 'business_head_ops', 'top_management']
        
        return False
    
    def can_be_edited_by(self, user):
        """Check if user can edit this plan"""
        if self.status not in ['draft', 'rejected']:
            return False
        
        return self.created_by == user
    
    def can_be_accessed_by(self, user):
        """Check if user can access this plan"""
        if hasattr(user, 'role'):
            if user.role in ['top_management', 'business_head', 'business_head_ops']:
                return True
            elif user.role == 'rm_head':
                return (self.created_by == user or 
                        getattr(self.created_by, 'manager', None) == user)
            elif user.role == 'rm':
                return self.created_by == user
            elif user.role in ['ops_exec', 'ops_team_lead']:
                return self.status in ['client_approved', 'in_execution', 'completed']
        
        return False
    
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

# Django signals for auto-processing
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

class PortfolioActionPlan(models.Model):
    """Action plan for portfolio operations"""
    
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('pending_approval', 'Pending Approval'),
        ('approved', 'Approved'),
        ('executed', 'Executed'),
        ('rejected', 'Rejected'),
        ('cancelled', 'Cancelled'),
    ]
    
    # Basic Information
    plan_id = models.CharField(max_length=20, unique=True, editable=False)
    client_portfolio = models.ForeignKey(
        ClientPortfolio,
        on_delete=models.CASCADE,
        related_name='action_plans'
    )
    plan_name = models.CharField(max_length=200, help_text="Name for this action plan")
    description = models.TextField(blank=True, help_text="Optional description")
    
    # Status and Workflow
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    created_by = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='created_action_plans'
    )
    approved_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='approved_action_plans'
    )
    
    # Timestamps
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    executed_at = models.DateTimeField(null=True, blank=True)
    
    # Notes and comments
    notes = models.TextField(blank=True)
    approval_notes = models.TextField(blank=True)
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Portfolio Action Plan'
        verbose_name_plural = 'Portfolio Action Plans'
    
    def save(self, *args, **kwargs):
        if not self.plan_id:
            self.plan_id = self.generate_plan_id()
        super().save(*args, **kwargs)
    
    def generate_plan_id(self):
        """Generate unique plan ID"""
        from datetime import datetime
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        return f"PAP{timestamp}"
    
    def __str__(self):
        return f"{self.plan_id} - {self.plan_name} ({self.client_portfolio.client_name})"
    
    def can_be_edited(self):
        """Check if plan can be edited"""
        return self.status in ['draft', 'rejected']
    
    def can_be_approved(self):
        """Check if plan can be approved"""
        return self.status == 'pending_approval'
    
    def submit_for_approval(self):
        """Submit plan for approval"""
        if self.status == 'draft':
            self.status = 'pending_approval'
            self.save()
            return True
        return False
    
    def approve(self, approved_by, notes=""):
        """Approve the action plan"""
        if self.status == 'pending_approval':
            self.status = 'approved'
            self.approved_by = approved_by
            self.approved_at = timezone.now()
            self.approval_notes = notes
            self.save()
            return True
        return False
    
    def reject(self, rejected_by, notes=""):
        """Reject the action plan"""
        if self.status == 'pending_approval':
            self.status = 'rejected'
            self.approved_by = rejected_by
            self.approved_at = timezone.now()
            self.approval_notes = notes
            self.save()
            return True
        return False

class PortfolioAction(models.Model):
    """Individual actions within a portfolio action plan"""
    
    ACTION_TYPE_CHOICES = [
        ('redeem', 'Redeem'),
        ('switch', 'Switch'),
        ('stp', 'STP (Systematic Transfer Plan)'),
        ('sip', 'SIP (Systematic Investment Plan)'),
        ('swp', 'SWP (Systematic Withdrawal Plan)'),
    ]
    
    REDEEM_BY_CHOICES = [
        ('all_units', 'All Units'),
        ('specific_amount', 'Specific Amount'),
        ('specific_units', 'Specific Units'),
    ]
    
    FREQUENCY_CHOICES = [
        ('daily', 'Daily'),
        ('weekly', 'Weekly'),
        ('fortnightly', 'Fortnightly'),
        ('monthly', 'Monthly'),
    ]
    
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('executed', 'Executed'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
    ]
    
    # Basic Information
    action_plan = models.ForeignKey(
        PortfolioActionPlan,
        on_delete=models.CASCADE,
        related_name='actions'
    )
    action_type = models.CharField(max_length=20, choices=ACTION_TYPE_CHOICES)
    priority = models.PositiveIntegerField(default=1, help_text="Execution priority (1 = highest)")
    
    # Scheme Information
    source_scheme = models.CharField(
        max_length=300,
        help_text="Source scheme name (for current portfolio scheme or switch/STP source)"
    )
    target_scheme = models.CharField(
        max_length=300,
        blank=True,
        help_text="Target scheme name (for switch/STP/SIP target)"
    )
    
    # Redeem Action Fields
    redeem_by = models.CharField(
        max_length=20,
        choices=REDEEM_BY_CHOICES,
        blank=True,
        help_text="Method of redemption"
    )
    redeem_amount = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal('0.01'))],
        help_text="Amount to redeem (if redeem_by is specific_amount)"
    )
    redeem_units = models.DecimalField(
        max_digits=15,
        decimal_places=4,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal('0.0001'))],
        help_text="Units to redeem (if redeem_by is specific_units)"
    )
    
    # Switch Action Fields
    switch_by = models.CharField(
        max_length=20,
        choices=REDEEM_BY_CHOICES,
        blank=True,
        help_text="Method of switching"
    )
    switch_amount = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal('0.01'))],
        help_text="Amount to switch"
    )
    switch_units = models.DecimalField(
        max_digits=15,
        decimal_places=4,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal('0.0001'))],
        help_text="Units to switch"
    )
    
    # STP Action Fields
    stp_amount = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal('0.01'))],
        help_text="Amount to transfer regularly in STP"
    )
    stp_frequency = models.CharField(
        max_length=20,
        choices=FREQUENCY_CHOICES,
        blank=True,
        help_text="Frequency of STP transfers"
    )
    
    # SIP Action Fields
    sip_amount = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal('0.01'))],
        help_text="SIP investment amount"
    )
    sip_frequency = models.CharField(
        max_length=20,
        choices=FREQUENCY_CHOICES,
        blank=True,
        help_text="SIP frequency"
    )
    sip_date = models.PositiveIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(31)],
        help_text="SIP execution date (1-31)"
    )
    
    # SWP Action Fields
    swp_amount = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal('0.01'))],
        help_text="SWP withdrawal amount"
    )
    swp_frequency = models.CharField(
        max_length=20,
        choices=FREQUENCY_CHOICES,
        blank=True,
        help_text="SWP frequency"
    )
    swp_date = models.PositiveIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(31)],
        help_text="SWP execution date (1-31)"
    )
    
    # Execution Details
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    executed_at = models.DateTimeField(null=True, blank=True)
    executed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='executed_portfolio_actions'
    )
    
    # Transaction Details (post-execution)
    transaction_id = models.CharField(max_length=100, blank=True)
    execution_notes = models.TextField(blank=True)
    failure_reason = models.TextField(blank=True)
    
    # Metadata
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['priority', 'created_at']
        verbose_name = 'Portfolio Action'
        verbose_name_plural = 'Portfolio Actions'
    
    def __str__(self):
        return f"{self.get_action_type_display()} - {self.source_scheme}"
    
    def clean(self):
        """Validate action data based on action type"""
        super().clean()
        
        if self.action_type == 'redeem':
            if not self.redeem_by:
                raise ValidationError("Redeem method is required for redeem actions")
            
            if self.redeem_by == 'specific_amount' and not self.redeem_amount:
                raise ValidationError("Redeem amount is required when redeeming by specific amount")
            elif self.redeem_by == 'specific_units' and not self.redeem_units:
                raise ValidationError("Redeem units is required when redeeming by specific units")
        
        elif self.action_type == 'switch':
            if not self.target_scheme:
                raise ValidationError("Target scheme is required for switch actions")
            if not self.switch_by:
                raise ValidationError("Switch method is required for switch actions")
            
            if self.switch_by == 'specific_amount' and not self.switch_amount:
                raise ValidationError("Switch amount is required when switching by specific amount")
            elif self.switch_by == 'specific_units' and not self.switch_units:
                raise ValidationError("Switch units is required when switching by specific units")
        
        elif self.action_type == 'stp':
            if not self.target_scheme:
                raise ValidationError("Target scheme is required for STP actions")
            if not self.stp_amount:
                raise ValidationError("STP amount is required")
            if not self.stp_frequency:
                raise ValidationError("STP frequency is required")
        
        elif self.action_type == 'sip':
            if not self.target_scheme:
                raise ValidationError("Target scheme is required for SIP actions")
            if not self.sip_amount:
                raise ValidationError("SIP amount is required")
            if not self.sip_frequency:
                raise ValidationError("SIP frequency is required")
            if not self.sip_date:
                raise ValidationError("SIP date is required")
        
        elif self.action_type == 'swp':
            if not self.swp_amount:
                raise ValidationError("SWP amount is required")
            if not self.swp_frequency:
                raise ValidationError("SWP frequency is required")
            if not self.swp_date:
                raise ValidationError("SWP date is required")
    
    def get_action_summary(self):
        """Get a human-readable summary of the action"""
        if self.action_type == 'redeem':
            if self.redeem_by == 'all_units':
                return f"Redeem all units from {self.source_scheme}"
            elif self.redeem_by == 'specific_amount':
                return f"Redeem ₹{self.redeem_amount:,.2f} from {self.source_scheme}"
            elif self.redeem_by == 'specific_units':
                return f"Redeem {self.redeem_units:,.4f} units from {self.source_scheme}"
        
        elif self.action_type == 'switch':
            if self.switch_by == 'all_units':
                return f"Switch all units from {self.source_scheme} to {self.target_scheme}"
            elif self.switch_by == 'specific_amount':
                return f"Switch ₹{self.switch_amount:,.2f} from {self.source_scheme} to {self.target_scheme}"
            elif self.switch_by == 'specific_units':
                return f"Switch {self.switch_units:,.4f} units from {self.source_scheme} to {self.target_scheme}"
        
        elif self.action_type == 'stp':
            return f"STP ₹{self.stp_amount:,.2f} {self.stp_frequency} from {self.source_scheme} to {self.target_scheme}"
        
        elif self.action_type == 'sip':
            return f"SIP ₹{self.sip_amount:,.2f} {self.sip_frequency} on {self.sip_date} into {self.target_scheme}"
        
        elif self.action_type == 'swp':
            return f"SWP ₹{self.swp_amount:,.2f} {self.swp_frequency} on {self.swp_date} from {self.source_scheme}"
        
        return f"{self.get_action_type_display()} action"

class ActionPlanComment(models.Model):
    """Comments on action plans"""
    action_plan = models.ForeignKey(
        PortfolioActionPlan,
        on_delete=models.CASCADE,
        related_name='comments'
    )
    comment = models.TextField()
    commented_by = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='action_plan_comments'
    )
    created_at = models.DateTimeField(default=timezone.now)
    is_internal = models.BooleanField(default=True, help_text="Internal comment (not visible to client)")
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Action Plan Comment'
        verbose_name_plural = 'Action Plan Comments'
    
    def __str__(self):
        return f"Comment by {self.commented_by.username} on {self.action_plan.plan_id}"

class ActionPlanWorkflow(models.Model):
    """Track workflow history for action plans"""
    action_plan = models.ForeignKey(
        PortfolioActionPlan,
        on_delete=models.CASCADE,
        related_name='workflow_history'
    )
    from_status = models.CharField(max_length=20)
    to_status = models.CharField(max_length=20)
    changed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='action_plan_workflow_changes'
    )
    changed_at = models.DateTimeField(default=timezone.now)
    notes = models.TextField(blank=True)
    
    class Meta:
        ordering = ['-changed_at']
        verbose_name = 'Action Plan Workflow'
        verbose_name_plural = 'Action Plan Workflows'
    
    def __str__(self):
        return f"{self.action_plan.plan_id}: {self.from_status} → {self.to_status}"
    
    
    
