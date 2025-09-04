# models.py - Fixed version with single ServiceRequest model
import decimal
import re
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
from datetime import datetime
import random
import string

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
from collections import defaultdict
import hashlib

class SchemeUploadLog(models.Model):
    """Log entries for scheme upload processing"""
    upload = models.ForeignKey(
        'SchemeUpload',
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
    """Model to track scheme master file uploads - Optimized for AMFI data"""
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
    
    # AMFI-specific metrics
    empty_categories_count = models.PositiveIntegerField(default=0)
    empty_isins_count = models.PositiveIntegerField(default=0)
    duplicate_isins_found = models.PositiveIntegerField(default=0)
    
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
    skip_empty_categories = models.BooleanField(
        default=False,
        help_text="Skip schemes with empty categories"
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
    
    def create_log_batch(self, logs_data):
        """Create multiple log entries in batch"""
        log_objects = []
        for log_data in logs_data:
            log_objects.append(SchemeUploadLog(
                upload=self,
                row_number=log_data.get('row_number', 0),
                amc_name=log_data.get('amc_name', ''),
                scheme_name=log_data.get('scheme_name', ''),
                status=log_data['status'],
                message=log_data['message'],
                scheme=log_data.get('scheme'),
                created_at=timezone.now()
            ))
        
        if log_objects:
            SchemeUploadLog.objects.bulk_create(log_objects, batch_size=1000)
    
    def process_upload_with_logging(self):
        """Optimized main method to process AMFI scheme file"""
        import os
        
        try:
            self.status = 'processing'
            self.save()
            
            # Log start
            self.create_log(0, 'success', f"Started processing AMFI upload {self.upload_id}")
            
            # Check if file exists
            if not self.file or not os.path.exists(self.file.path):
                raise Exception(f"File not found: {self.file.path if self.file else 'No file attached'}")
            
            # Read AMFI Excel file with specific structure handling
            df = self._read_amfi_excel_file()
            if df is None or df.empty:
                raise Exception("Failed to read valid data from AMFI Excel file")
            
            # Validate and clean AMFI data
            df = self._validate_and_clean_amfi_data(df)
            
            # Build lookup caches for performance
            lookup_caches = self._build_amfi_lookup_caches()
            
            # Process in optimized batches
            self._process_amfi_data_in_batches(df, lookup_caches)
            
            # Mark missing schemes as inactive if requested
            if self.mark_missing_inactive:
                self._mark_missing_schemes_inactive()
            
            # Complete processing
            self._finalize_processing()
            
            return True
            
        except Exception as e:
            error_msg = f"AMFI processing failed: {str(e)}"
            self.status = 'failed'
            self.processed_at = timezone.now()
            self.error_details = {'error': str(e)}
            self.save()
            self.create_log(0, 'error', error_msg)
            logger.error(f"AMFI upload {self.upload_id} failed: {e}")
            return False
    
    def _read_amfi_excel_file(self):
        """Read AMFI Excel file with specific structure handling"""
        try:
            # AMFI files have:
            # Row 1: Headers (AMC Name, Scheme NAV Name, Category, ISIN Div Payout / ISIN Growth, ISIN Div Reinvestment)
            # Row 2: Empty row
            # Row 3+: Data
            
            df = pd.read_excel(
                self.file.path,
                engine='openpyxl',
                header=0,  # Use first row as headers
                skiprows=[1],  # Skip the empty second row
                dtype=str,  # Read all as strings to avoid type conversion
                na_filter=False,  # Don't convert to NaN
                usecols='A:E'  # Only read first 5 columns, ignore empty 6th column
            )
            
            self.create_log(0, 'success', f"Successfully read AMFI Excel file with {len(df)} rows")
            
            # Remove completely empty rows
            df = df.dropna(how='all')
            
            self.total_rows = len(df)
            self.save()
            
            # Log column information
            columns_found = list(df.columns)
            self.create_log(0, 'success', f"AMFI columns found: {', '.join(columns_found)}")
            
            return df
            
        except Exception as e:
            self.create_log(0, 'error', f"Failed to read AMFI Excel file: {str(e)}")
            raise
    
    def _validate_and_clean_amfi_data(self, df):
        """Validate and clean AMFI-specific data"""
        
        # Check for expected AMFI columns
        expected_columns = [
            'AMC Name',
            'Scheme NAV Name', 
            'Category',
            'ISIN Div Payout / ISIN Growth',
            'ISIN Div Reinvestment'
        ]
        
        missing_columns = [col for col in expected_columns if col not in df.columns]
        if missing_columns:
            error_msg = f"Missing AMFI columns: {', '.join(missing_columns)}"
            self.create_log(0, 'error', error_msg)
            raise Exception(error_msg)
        
        self.create_log(0, 'success', "AMFI column validation successful")
        
        # Clean string data
        for col in expected_columns:
            df[col] = df[col].astype(str).str.strip()
            df[col] = df[col].replace(['nan', 'NaN', 'None', '-'], '')
        
        # Count AMFI-specific data quality issues
        self.empty_categories_count = (df['Category'] == '').sum()
        self.empty_isins_count = (df['ISIN Div Payout / ISIN Growth'] == '').sum()
        
        # Check for duplicate ISINs
        isin_column = 'ISIN Div Payout / ISIN Growth'
        non_empty_isins = df[df[isin_column] != ''][isin_column]
        duplicate_isins = non_empty_isins.duplicated()
        self.duplicate_isins_found = duplicate_isins.sum()
        
        # Remove rows with missing critical data
        initial_count = len(df)
        df = df[(df['AMC Name'] != '') & (df['Scheme NAV Name'] != '')]
        removed_count = initial_count - len(df)
        
        if removed_count > 0:
            self.create_log(0, 'warning', f"Removed {removed_count} rows with missing AMC/Scheme names")
        
        # Optionally skip rows with empty categories
        if self.skip_empty_categories:
            category_initial = len(df)
            df = df[df['Category'] != '']
            category_removed = category_initial - len(df)
            if category_removed > 0:
                self.create_log(0, 'success', f"Skipped {category_removed} rows with empty categories")
        
        self.save()
        
        # Log AMFI data quality summary
        self.create_log(0, 'success', 
            f"AMFI data quality: {self.empty_categories_count} empty categories, "
            f"{self.empty_isins_count} empty ISINs, {self.duplicate_isins_found} duplicate ISINs")
        
        return df
    
    def _build_amfi_lookup_caches(self):
        """Build optimized lookup caches for AMFI processing"""
        
        self.create_log(0, 'success', "Building AMFI lookup caches...")
        
        # Get all existing schemes
        existing_schemes = MutualFundScheme.objects.all()
        
        caches = {
            'isin_to_scheme': {},
            'name_to_scheme': {},
            'amc_name_to_schemes': defaultdict(dict),
            'scheme_codes_used': set()
        }
        
        for scheme in existing_schemes:
            # ISIN lookup (primary for AMFI)
            if scheme.isin_growth:
                isin_key = scheme.isin_growth.strip().upper()
                caches['isin_to_scheme'][isin_key] = scheme
            
            # Name lookup (case-insensitive)
            name_key = scheme.scheme_name.strip().lower()
            caches['name_to_scheme'][name_key] = scheme
            
            # AMC + Name lookup
            amc_key = scheme.amc_name.strip().lower()
            caches['amc_name_to_schemes'][amc_key][name_key] = scheme
            
            # Track used scheme codes
            if scheme.scheme_code:
                caches['scheme_codes_used'].add(scheme.scheme_code)
        
        cache_stats = f"ISIN: {len(caches['isin_to_scheme'])}, Names: {len(caches['name_to_scheme'])}, AMCs: {len(caches['amc_name_to_schemes'])}"
        self.create_log(0, 'success', f"AMFI lookup caches built - {cache_stats}")
        
        return caches
    
    def _process_amfi_data_in_batches(self, df, lookup_caches):
        """Process AMFI data in optimized batches"""
        
        batch_size = 1000  # Optimized for AMFI data size
        total_batches = (len(df) + batch_size - 1) // batch_size
        
        schemes_to_create = []
        schemes_to_update = []
        logs_to_create = []
        
        for batch_num in range(total_batches):
            start_idx = batch_num * batch_size
            end_idx = min(start_idx + batch_size, len(df))
            batch_df = df.iloc[start_idx:end_idx]
            
            # Process batch
            for idx, row in batch_df.iterrows():
                row_number = idx + 1
                try:
                    result = self._process_single_amfi_row(row, row_number, lookup_caches)
                    
                    if result['action'] == 'create':
                        schemes_to_create.append(result['scheme_data'])
                        self.successful_rows += 1
                    elif result['action'] == 'update':
                        schemes_to_update.append(result)
                        self.updated_rows += 1
                    elif result['action'] == 'skip':
                        pass  # Already logged
                    
                    logs_to_create.append(result['log'])
                    
                except Exception as e:
                    self.failed_rows += 1
                    logs_to_create.append({
                        'row_number': row_number,
                        'status': 'error',
                        'message': f"AMFI row processing error: {str(e)}",
                        'amc_name': str(row.get('AMC Name', '')),
                        'scheme_name': str(row.get('Scheme NAV Name', '')),
                        'scheme': None
                    })
            
            # Execute database operations for this batch
            self._execute_amfi_batch_operations(schemes_to_create, schemes_to_update, logs_to_create)
            
            # Clear for next batch
            schemes_to_create = []
            schemes_to_update = []
            logs_to_create = []
            
            # Update progress
            self.processed_rows = end_idx
            self.save()
            
            # Log progress
            if (batch_num + 1) % 5 == 0 or batch_num == total_batches - 1:
                self.create_log(0, 'success', f"AMFI progress: {end_idx}/{len(df)} rows processed")
    
    def _process_single_amfi_row(self, row, row_number, lookup_caches):
        """Process a single AMFI row"""
        
        # Extract AMFI data
        amc_name = self._safe_string_convert(row.get('AMC Name', ''))
        scheme_name = self._safe_string_convert(row.get('Scheme NAV Name', ''))
        category = self._safe_string_convert(row.get('Category', ''))
        isin_growth = self._safe_string_convert(row.get('ISIN Div Payout / ISIN Growth', ''))
        isin_div = self._safe_string_convert(row.get('ISIN Div Reinvestment', ''))
        
        # Validate required fields
        if not amc_name or not scheme_name:
            return {
                'action': 'skip',
                'log': {
                    'row_number': row_number,
                    'status': 'error',
                    'message': f"Missing required AMFI fields - AMC: '{amc_name}', Scheme: '{scheme_name}'",
                    'amc_name': amc_name,
                    'scheme_name': scheme_name,
                    'scheme': None
                }
            }
        
        # Find existing scheme using AMFI-optimized search
        existing_scheme, search_method = self._find_existing_amfi_scheme(
            amc_name, scheme_name, isin_growth, lookup_caches
        )
        
        # Prepare AMFI scheme data
        scheme_data = {
            'amc_name': amc_name,
            'scheme_name': scheme_name,
            'category': category if category else 'Uncategorized',
            'scheme_type': self._categorize_amfi_scheme_type(category),
            'isin_growth': isin_growth if isin_growth else None,
            'isin_div_reinvestment': isin_div if isin_div else None,
            'scheme_code': self._generate_amfi_scheme_code(amc_name, scheme_name, isin_growth, lookup_caches['scheme_codes_used']),
            'is_active': True,
            'last_updated': timezone.now(),
            'upload_batch': self
        }
        
        if existing_scheme and self.update_existing:
            return {
                'action': 'update',
                'scheme_data': scheme_data,
                'existing_scheme': existing_scheme,
                'log': {
                    'row_number': row_number,
                    'status': 'success',
                    'message': f"Updated AMFI scheme ({search_method})",
                    'amc_name': amc_name,
                    'scheme_name': scheme_name,
                    'scheme': existing_scheme
                }
            }
        elif existing_scheme:
            return {
                'action': 'skip',
                'log': {
                    'row_number': row_number,
                    'status': 'warning',
                    'message': f"Skipped AMFI scheme ({search_method}) - update disabled",
                    'amc_name': amc_name,
                    'scheme_name': scheme_name,
                    'scheme': existing_scheme
                }
            }
        else:
            return {
                'action': 'create',
                'scheme_data': scheme_data,
                'log': {
                    'row_number': row_number,
                    'status': 'success',
                    'message': f"Created new AMFI scheme - Code: {scheme_data['scheme_code']}",
                    'amc_name': amc_name,
                    'scheme_name': scheme_name,
                    'scheme': None
                }
            }
    
    def _find_existing_amfi_scheme(self, amc_name, scheme_name, isin_growth, lookup_caches):
        """Find existing scheme using AMFI-optimized search methods"""
        
        # Method 1: Search by ISIN Growth (most reliable for AMFI)
        if isin_growth:
            isin_key = isin_growth.strip().upper()
            if isin_key in lookup_caches['isin_to_scheme']:
                return lookup_caches['isin_to_scheme'][isin_key], f"ISIN: {isin_growth}"
        
        # Method 2: Search by exact Scheme NAV Name
        name_key = scheme_name.strip().lower()
        if name_key in lookup_caches['name_to_scheme']:
            return lookup_caches['name_to_scheme'][name_key], f"Name: {scheme_name}"
        
        # Method 3: Search by AMC Name + Scheme NAV Name combination
        amc_key = amc_name.strip().lower()
        if amc_key in lookup_caches['amc_name_to_schemes']:
            if name_key in lookup_caches['amc_name_to_schemes'][amc_key]:
                scheme = lookup_caches['amc_name_to_schemes'][amc_key][name_key]
                return scheme, f"AMC+Name: {amc_name} - {scheme_name}"
        
        return None, ""
    
    def _categorize_amfi_scheme_type(self, category):
        """Categorize scheme type based on AMFI category"""
        if not category:
            return 'other'
        
        category_lower = category.lower()
        
        # AMFI-specific categorization
        if category_lower.startswith('equity'):
            return 'equity'
        elif category_lower.startswith('debt'):
            return 'debt'
        elif category_lower.startswith('hybrid'):
            return 'hybrid'
        elif 'liquid' in category_lower:
            return 'liquid'
        elif 'overnight' in category_lower:
            return 'overnight'
        elif 'ultra short' in category_lower:
            return 'ultra_short'
        elif 'elss' in category_lower:
            return 'elss'
        elif 'arbitrage' in category_lower:
            return 'arbitrage'
        elif 'fof' in category_lower:
            return 'fund_of_funds'
        elif 'etf' in category_lower:
            return 'etf'
        elif 'index' in category_lower:
            return 'index'
        else:
            return 'other'
    
    def _generate_amfi_scheme_code(self, amc_name, scheme_name, isin, scheme_codes_used):
        """Generate unique scheme code for AMFI schemes"""
        
        # Use ISIN as scheme code if available
        if isin:
            scheme_codes_used.add(isin)
            return isin
        
        # Generate from AMC and scheme name with hash for uniqueness
        amc_clean = ''.join(c for c in amc_name.upper() if c.isalnum())[:4]
        scheme_clean = ''.join(c for c in scheme_name.upper() if c.isalnum())[:8]
        
        # Create hash for uniqueness
        content = f"{amc_name}|{scheme_name}".encode('utf-8')
        hash_suffix = hashlib.md5(content).hexdigest()[:4].upper()
        
        base_code = f"{amc_clean}_{scheme_clean}_{hash_suffix}"
        
        # Ensure uniqueness
        counter = 1
        final_code = base_code
        while final_code in scheme_codes_used:
            final_code = f"{base_code}_{counter}"
            counter += 1
        
        scheme_codes_used.add(final_code)
        return final_code
    
    def _execute_amfi_batch_operations(self, schemes_to_create, schemes_to_update, logs_to_create):
        """Execute database operations for AMFI batch"""
        
        try:
            with transaction.atomic():
                # Bulk create new schemes
                if schemes_to_create:
                    scheme_objects = [MutualFundScheme(**data) for data in schemes_to_create]
                    MutualFundScheme.objects.bulk_create(scheme_objects, batch_size=1000)
                
                # Bulk update existing schemes
                for update_data in schemes_to_update:
                    scheme_data = update_data['scheme_data']
                    existing_scheme = update_data['existing_scheme']
                    
                    for field, value in scheme_data.items():
                        if field != 'upload_batch':  # Don't change upload_batch for existing
                            setattr(existing_scheme, field, value)
                    existing_scheme.save()
                
                # Bulk create logs
                if logs_to_create:
                    self.create_log_batch(logs_to_create)
                
        except Exception as e:
            logger.error(f"AMFI batch operation failed: {e}")
            # Fall back to individual operations if bulk fails
            self._fallback_individual_operations(schemes_to_create, schemes_to_update, logs_to_create)
    
    def _fallback_individual_operations(self, schemes_to_create, schemes_to_update, logs_to_create):
        """Fallback to individual operations if bulk operations fail"""
        
        for scheme_data in schemes_to_create:
            try:
                MutualFundScheme.objects.create(**scheme_data)
            except Exception as e:
                logger.error(f"Individual create failed: {e}")
        
        for update_data in schemes_to_update:
            try:
                scheme_data = update_data['scheme_data']
                existing_scheme = update_data['existing_scheme']
                for field, value in scheme_data.items():
                    if field != 'upload_batch':
                        setattr(existing_scheme, field, value)
                existing_scheme.save()
            except Exception as e:
                logger.error(f"Individual update failed: {e}")
    
    def _finalize_processing(self):
        """Finalize AMFI processing"""
        
        if self.failed_rows == 0:
            self.status = 'completed'
        else:
            self.status = 'partial'
        
        self.processed_at = timezone.now()
        self.save()
        
        # Create final summary
        summary = (
            f"AMFI processing completed. "
            f"Total: {self.total_rows}, "
            f"Created: {self.successful_rows}, "
            f"Updated: {self.updated_rows}, "
            f"Failed: {self.failed_rows}, "
            f"Empty Categories: {self.empty_categories_count}, "
            f"Empty ISINs: {self.empty_isins_count}, "
            f"Duplicate ISINs: {self.duplicate_isins_found}"
        )
        self.create_log(0, 'success', summary)
    
    def _safe_string_convert(self, value):
        """Safely convert values to string, handling NaN and None"""
        if value is None:
            return ''
        
        if pd.isna(value):
            return ''
        
        # Convert to string and strip whitespace
        result = str(value).strip()
        
        # Handle various empty representations
        if result.lower() in ['nan', 'none', '-', '']:
            return ''
            
        return result
    
    def _mark_missing_schemes_inactive(self):
        """Mark schemes not in current upload as inactive"""
        if self.successful_rows > 0:
            upload_logs = self.processing_logs.filter(
                status='success',
                scheme__isnull=False
            ).values_list('scheme__scheme_code', flat=True)
            
            inactive_count = MutualFundScheme.objects.exclude(
                scheme_code__in=upload_logs
            ).update(is_active=False)
            
            self.create_log(0, 'success', 
                f"Marked {inactive_count} schemes as inactive (not in current AMFI upload)")
    
    # Archive and delete methods (unchanged)
    def archive(self, user):
        """Archive instead of delete"""
        self.is_archived = True
        self.archived_at = timezone.now()
        self.archived_by = user
        self.status = 'archived'
        self.save()
        
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


@receiver(post_save, sender=SchemeUpload)
def auto_process_scheme_upload(sender, instance, created, **kwargs):
    """Safely process uploads without transaction conflicts"""
    if created and instance.status == 'pending':
        try:
            transaction.on_commit(lambda: process_upload_deferred(instance.id))
        except Exception as e:
            logger.error(f"Error scheduling AMFI upload processing for {instance.upload_id}: {e}")

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
    
from django.db import models
from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator
from django.core.exceptions import ValidationError


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
        'ClientProfile',  # Use string reference to avoid circular imports
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='lead_profile'
    )
    conversion_requested_at = models.DateTimeField(null=True, blank=True, help_text="When conversion was requested")
    conversion_requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        null=True, 
        blank=True, 
        on_delete=models.SET_NULL,
        related_name='requested_conversions',
        help_text="RM who requested the conversion"
    )
    business_verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='business_verified_leads',
        help_text="Ops team lead who verified business details"
    )
    business_verification_notes = models.TextField(
        blank=True,
        help_text="Business verification notes from ops team lead"
    )
    final_assigned_rm = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='final_assigned_clients',
        help_text="RM assigned to the client after conversion (can be different from original RM)"
    )
    generated_client = models.OneToOneField(
        'Client',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='source_lead',
        help_text="The client record generated from this lead"
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
        constraints = [
            models.CheckConstraint(
                check=(
                    models.Q(email__isnull=False, email__gt='') |
                    models.Q(mobile__isnull=False, mobile__gt='')
                ),
                name='lead_contact_method_required',
                violation_error_message='At least one contact method (email or mobile) is required.'
            )
        ]
    
    def __str__(self):
        return f"{self.lead_id} - {self.name} ({self.get_status_display()})"
    
    def clean(self):
        """Model-level validation to ensure either email or mobile is provided"""
        super().clean()
        
        # Check if both email and mobile are empty or contain only whitespace
        email_empty = not self.email or not self.email.strip()
        mobile_empty = not self.mobile or not self.mobile.strip()
        
        if email_empty and mobile_empty:
            raise ValidationError({
                '__all__': 'At least one contact method is required. Please provide either an email address or mobile number.'
            })
    
    def save(self, *args, **kwargs):
        # Generate lead_id if not exists
        if not self.lead_id:
            self.lead_id = self.generate_lead_id()
        
        # Call clean method to validate
        self.full_clean()
        
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
        """Generate a unique client ID - CORRECTED VERSION"""
        from datetime import datetime
        import random
        import string
        
        # Format: CL + YYYYMMDD + 4 random digits
        date_part = datetime.now().strftime("%Y%m%d")
        random_part = ''.join(random.choices(string.digits, k=4))
        
        client_id = f"CL{date_part}{random_part}"
        
        # ONLY check uniqueness against Lead model's client_id field
        # DO NOT check Client model since it doesn't have client_id field
        while Lead.objects.filter(client_id=client_id).exists():
            random_part = ''.join(random.choices(string.digits, k=4))
            client_id = f"CL{date_part}{random_part}"
        
        return client_id

    
    
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
    converted_from_lead = models.ForeignKey(
        'Lead',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='converted_client',
        help_text="The lead that was converted to create this client"
    )
    original_rm = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='original_rm_clients',
        help_text="Original RM who handled the lead"
    )
    conversion_approved_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='approved_conversions',
        help_text="Ops team lead who approved the conversion"
    )
    business_verification_notes = models.TextField(
        blank=True,
        help_text="Business verification notes from conversion approval"
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
    code = models.CharField(max_length=50, unique=True)
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
    """Model to track portfolio file uploads - OPTIMIZED"""
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
        """Create a log entry for this upload"""
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
    
    def create_bulk_logs(self, log_entries):
        """Create multiple log entries in bulk for better performance"""
        if not log_entries:
            return
            
        log_objects = [
            PortfolioUploadLog(
                upload=self,
                row_number=entry.get('row_number', 0),
                client_name=entry.get('client_name', '')[:255],  # Truncate to avoid overflow
                client_pan=entry.get('client_pan', '')[:50],
                scheme_name=entry.get('scheme_name', '')[:300],
                status=entry.get('status', 'success'),
                message=entry.get('message', '')[:2000],  # Truncate long messages
                portfolio_entry=entry.get('portfolio_entry', None)
            ) for entry in log_entries
        ]
        
        # Use ignore_conflicts=True for better performance
        PortfolioUploadLog.objects.bulk_create(log_objects, batch_size=2000, ignore_conflicts=True)
    
    def process_upload_with_logging(self):
        """Main method to process the uploaded portfolio file with comprehensive logging - OPTIMIZED"""
        try:
            self.status = 'processing'
            self.save(update_fields=['status'])  # Only update status field
            
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
            self.save(update_fields=['status', 'processed_at'])
            
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
            self.save(update_fields=['status', 'error_details', 'processed_at'])
            
            # Log the error
            self.create_log(
                row_number=0,
                status='error',
                message=f"Upload processing failed: {str(e)}"
            )
            return False
    
    def _process_file_with_logging(self):
        """Process the uploaded Excel file with detailed logging - HIGHLY OPTIMIZED"""
        import os
        
        try:
            # Determine file type and read accordingly
            file_ext = os.path.splitext(self.file.name)[1].lower()
            
            if file_ext == '.csv':
                # Optimized CSV reading
                df = pd.read_csv(
                    self.file.path,
                    dtype=str,
                    na_filter=False,
                    low_memory=False,
                    engine='c'  # Use C engine for better performance
                )
            elif file_ext in ['.xlsx', '.xls']:
                # Highly optimized Excel reading
                df = pd.read_excel(
                    self.file.path, 
                    engine='openpyxl' if file_ext == '.xlsx' else 'xlrd',
                    dtype=str,
                    na_filter=False,
                    keep_default_na=False,  # Don't convert to NaN
                    sheet_name=0  # Read only first sheet
                )
            else:
                raise ValueError(f"Unsupported file format: {file_ext}")
            
            # Drop completely empty rows
            df = df.dropna(how='all').reset_index(drop=True)
            
            self.total_rows = len(df)
            self.save(update_fields=['total_rows'])
            
            # Log file validation success
            self.create_log(
                row_number=0,
                status='success',
                message=f"File validation successful. Found {self.total_rows} rows to process"
            )
            
            # Clean column names - vectorized operation
            df.columns = df.columns.str.strip().str.upper()
            
            # MAJOR OPTIMIZATION: Process entire DataFrame at once instead of batches
            with transaction.atomic():
                # Use savepoint for rollback capability
                sid = transaction.savepoint()
                
                try:
                    result = self._process_entire_dataframe(df)
                    
                    # Update counters
                    self.processed_rows = len(df)
                    self.successful_rows = result['successful']
                    self.failed_rows = result['failed']
                    self.save(update_fields=['processed_rows', 'successful_rows', 'failed_rows'])
                    
                    # Bulk create logs
                    if result['logs']:
                        self.create_bulk_logs(result['logs'])
                    
                    transaction.savepoint_commit(sid)
                    
                except Exception as e:
                    transaction.savepoint_rollback(sid)
                    raise e
            
            return True
            
        except Exception as e:
            error_msg = f"File processing error: {str(e)}"
            self.create_log(
                row_number=0,
                status='error',
                message=error_msg
            )
            raise Exception(error_msg)
    
    def _process_entire_dataframe(self, df):
        """Process entire DataFrame at once using vectorized operations - MAXIMUM OPTIMIZATION"""
        
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
        
        result = {
            'successful': 0,
            'failed': 0,
            'logs': []
        }
        
        # VECTORIZED DATA CLEANING AND VALIDATION
        # Clean and validate required fields using pandas vectorized operations
        df['CLIENT'] = df.get('CLIENT', '').astype(str).str.strip()
        df['CLIENT PAN'] = df.get('CLIENT PAN', '').astype(str).str.strip()
        df['SCHEME'] = df.get('SCHEME', '').astype(str).str.strip()
        
        # Create mask for valid rows (vectorized operation)
        valid_mask = (df['CLIENT'] != '') & (df['SCHEME'] != '') & (df['CLIENT'] != 'nan') & (df['SCHEME'] != 'nan')
        
        # Separate valid and invalid rows
        valid_df = df[valid_mask].copy()
        invalid_df = df[~valid_mask].copy()
        
        # Process invalid rows for logging
        for idx in invalid_df.index:
            row = invalid_df.loc[idx]
            result['logs'].append({
                'row_number': idx + 1,
                'client_name': str(row.get('CLIENT', ''))[:255],
                'client_pan': str(row.get('CLIENT PAN', ''))[:50],
                'scheme_name': str(row.get('SCHEME', ''))[:300],
                'status': 'error',
                'message': "Missing required fields: client name or scheme name"
            })
            result['failed'] += 1
        
        if len(valid_df) == 0:
            return result
        
        # VECTORIZED DATA PREPARATION for valid rows
        portfolio_objects = []
        success_logs = []
        
        # Prepare common fields for all rows
        current_date = timezone.now().date()
        
        # Process valid rows efficiently
        for idx, row in valid_df.iterrows():
            try:
                # Extract basic info
                client_name = str(row.get('CLIENT', ''))[:255]
                client_pan = str(row.get('CLIENT PAN', ''))[:50]
                scheme_name = str(row.get('SCHEME', ''))[:300]
                
                # Prepare portfolio data
                portfolio_data = {
                    'upload_batch': self,
                    'data_as_of_date': current_date,
                    'is_active': True,
                    'is_mapped': False,
                    'client_name': client_name,
                    'client_pan': client_pan,
                    'scheme_name': scheme_name
                }
                
                # Process numeric fields with optimized conversion
                numeric_fields = [
                    'debt_value', 'equity_value', 'hybrid_value', 
                    'liquid_ultra_short_value', 'other_value', 'arbitrage_value',
                    'total_value', 'allocation_percentage', 'units'
                ]
                
                for excel_col, model_field in column_mapping.items():
                    if excel_col in row.index and str(row[excel_col]).strip():
                        value = row[excel_col]
                        
                        if model_field in numeric_fields:
                            portfolio_data[model_field] = ClientPortfolio.safe_decimal_convert(value)
                        else:
                            # Truncate string fields to avoid database errors
                            max_lengths = {
                                'client_name': 255, 'client_pan': 50, 'scheme_name': 300,
                                'family_head': 255, 'app_code': 50, 'equity_code': 50,
                                'operations_personnel': 255, 'operations_code': 50,
                                'relationship_manager': 255, 'rm_code': 50,
                                'sub_broker': 255, 'sub_broker_code': 50,
                                'isin_number': 20, 'client_iwell_code': 50,
                                'family_head_iwell_code': 50
                            }
                            max_len = max_lengths.get(model_field, 255)
                            portfolio_data[model_field] = str(value)[:max_len]
                
                # Create portfolio object
                portfolio_obj = ClientPortfolio(**portfolio_data)
                portfolio_objects.append(portfolio_obj)
                
                # Prepare success log
                total_value = portfolio_data.get('total_value', 0)
                success_logs.append({
                    'row_number': idx + 1,
                    'client_name': client_name,
                    'client_pan': client_pan,
                    'scheme_name': scheme_name,
                    'status': 'success',
                    'message': f"Portfolio entry created successfully. Total value: ₹{total_value}"
                })
                
            except Exception as e:
                result['failed'] += 1
                result['logs'].append({
                    'row_number': idx + 1,
                    'client_name': client_name if 'client_name' in locals() else '',
                    'client_pan': client_pan if 'client_pan' in locals() else '',
                    'scheme_name': scheme_name if 'scheme_name' in locals() else '',
                    'status': 'error',
                    'message': f"Row processing error: {str(e)}"
                })
        
        # BULK CREATE all portfolio objects at once (MAXIMUM PERFORMANCE)
        if portfolio_objects:
            try:
                # Use bulk_create with large batch size and ignore_conflicts for maximum speed
                created_objects = ClientPortfolio.objects.bulk_create(
                    portfolio_objects, 
                    batch_size=5000,  # Larger batch size
                    ignore_conflicts=False
                )
                
                result['successful'] = len(created_objects)
                result['logs'].extend(success_logs)
                
                # OPTIMIZED MAPPING: Use bulk operations
                self._bulk_process_all_mappings(created_objects, result)
                
            except Exception as e:
                # If bulk create fails
                result['failed'] += len(portfolio_objects)
                result['logs'].extend([
                    {
                        'row_number': i + 1,
                        'client_name': obj.client_name,
                        'client_pan': obj.client_pan,
                        'scheme_name': obj.scheme_name,
                        'status': 'error',
                        'message': f"Bulk creation failed: {str(e)}"
                    } for i, obj in enumerate(portfolio_objects)
                ])
                
                logger.error(f"Bulk create failed: {e}")
        
        return result
    
    def _bulk_process_all_mappings(self, portfolio_entries, result):
        """Process all mappings using bulk operations for maximum performance"""
        if not portfolio_entries:
            return
        
        try:
            # BULK CLIENT PROFILE MAPPING
            # Get all unique PANs
            pan_list = [entry.client_pan for entry in portfolio_entries if entry.client_pan]
            
            if pan_list:
                # Bulk fetch client profiles
                client_profiles = {
                    cp.pan_number: cp 
                    for cp in ClientProfile.objects.filter(pan_number__in=pan_list)
                }
                
                # Bulk update client mappings
                updates = []
                for entry in portfolio_entries:
                    if entry.client_pan in client_profiles:
                        entry.client_profile = client_profiles[entry.client_pan]
                        entry.is_mapped = True
                        entry.mapping_notes = f"Auto-mapped on {timezone.now().strftime('%Y-%m-%d %H:%M')}"
                        updates.append(entry)
                
                if updates:
                    ClientPortfolio.objects.bulk_update(
                        updates, 
                        ['client_profile', 'is_mapped', 'mapping_notes'],
                        batch_size=2000
                    )
            
            # BULK PERSONNEL MAPPING
            # Get all unique RM and Ops names
            rm_names = [entry.relationship_manager for entry in portfolio_entries if entry.relationship_manager]
            ops_names = [entry.operations_personnel for entry in portfolio_entries if entry.operations_personnel]
            
            # Bulk fetch users
            all_users = {}
            if rm_names or ops_names:
                users = User.objects.filter(
                    models.Q(role='rm') | models.Q(role__in=['ops_exec', 'ops_team_lead'])
                ).values('id', 'first_name', 'last_name', 'role')
                
                for user in users:
                    full_name = f"{user['first_name']} {user['last_name']}".strip()
                    all_users[full_name.lower()] = user
            
            # Map personnel
            personnel_updates = []
            for entry in portfolio_entries:
                updated = False
                
                # Map RM
                if entry.relationship_manager:
                    rm_key = entry.relationship_manager.lower().strip()
                    if rm_key in all_users and all_users[rm_key]['role'] == 'rm':
                        entry.mapped_rm_id = all_users[rm_key]['id']
                        updated = True
                
                # Map Operations
                if entry.operations_personnel:
                    ops_key = entry.operations_personnel.lower().strip()
                    if ops_key in all_users and all_users[ops_key]['role'] in ['ops_exec', 'ops_team_lead']:
                        entry.mapped_ops_id = all_users[ops_key]['id']
                        updated = True
                
                if updated:
                    personnel_updates.append(entry)
            
            if personnel_updates:
                ClientPortfolio.objects.bulk_update(
                    personnel_updates,
                    ['mapped_rm', 'mapped_ops'],
                    batch_size=2000
                )
            
            # Add mapping summary to logs
            mapped_clients = sum(1 for entry in portfolio_entries if entry.is_mapped)
            mapped_personnel = len(personnel_updates)
            
            if mapped_clients > 0 or mapped_personnel > 0:
                result['logs'].append({
                    'row_number': 0,
                    'client_name': '',
                    'client_pan': '',
                    'scheme_name': '',
                    'status': 'success',
                    'message': f"Bulk mapping completed: {mapped_clients} clients mapped, {mapped_personnel} personnel mapped"
                })
                
        except Exception as e:
            logger.error(f"Error in bulk mapping: {e}")
            result['logs'].append({
                'row_number': 0,
                'client_name': '',
                'client_pan': '',
                'scheme_name': '',
                'status': 'warning',
                'message': f"Bulk mapping partially failed: {str(e)}"
            })


class ClientPortfolio(models.Model):
    """Enhanced client portfolio model with Excel upload support - OPTIMIZED"""
    # Link to client profile
    client_profile = models.ForeignKey(
        ClientProfile,
        on_delete=models.CASCADE,
        related_name='portfolio_holdings',
        null=True,
        blank=True
    )
    
    # Excel Data Fields (matching the uploaded structure)
    client_name = models.CharField(max_length=255, help_text="Client name from Excel", db_index=True)
    client_pan = models.CharField(max_length=50, help_text="Client PAN from Excel", db_index=True)
    scheme_name = models.CharField(max_length=300, help_text="Mutual fund scheme name", db_index=True)
    
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
            models.Index(fields=['client_pan', 'is_mapped']),  # Combined index for faster lookups
            models.Index(fields=['upload_batch', 'created_at']),  # For upload tracking
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
                self.save(update_fields=['client_profile', 'is_mapped', 'mapping_notes'])
                
                return True, f"Successfully mapped to {client_profile.client_full_name}"
                
            except ClientProfile.DoesNotExist:
                self.mapping_notes = f"No client profile found with PAN {self.client_pan}"
                self.save(update_fields=['mapping_notes'])
                return False, f"No client profile found with PAN {self.client_pan}"
            except ClientProfile.MultipleObjectsReturned:
                self.mapping_notes = f"Multiple client profiles found with PAN {self.client_pan}"
                self.save(update_fields=['mapping_notes'])
                return False, f"Multiple client profiles found with PAN {self.client_pan}"
            except Exception as e:
                logger.error(f"Error mapping client profile: {e}")
                return False, f"Error mapping client profile: {str(e)}"
        
        return False, "No PAN number provided"
    
    def map_personnel(self):
        """Map RM and Operations personnel based on names"""
        mapped_count = 0
        update_fields = []
        
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
                        update_fields.append('mapped_rm')
                        mapped_count += 1
            except Exception as e:
                logger.warning(f"Error mapping RM {self.relationship_manager}: {e}")
        
        # Map Operations personnel
        if self.operations_personnel:
            try:
                name_parts = self.operations_personnel.strip().split()
                if len(name_parts) >= 1:
                    ops_user = ops_user.first()
                    if ops_user:
                        self.mapped_ops = ops_user
                        update_fields.append('mapped_ops')
                        mapped_count += 1
            except Exception as e:
                logger.warning(f"Error mapping operations personnel {self.operations_personnel}: {e}")
        
        if update_fields:
            self.save(update_fields=update_fields)
        
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
        """Safely convert values to Decimal for Django DecimalField - OPTIMIZED"""
        if value is None or pd.isna(value) or value == '' or value == 'nan':
            return Decimal(str(default))
        
         # Handle string values
        if isinstance(value, str):
            # Remove common formatting characters
            value = value.replace(',', '').replace('₹', '').replace(' ', '')
            if not value or value == 'nan':
                return Decimal(str(default))
       
        try:
            # Direct conversion for better performance
            if isinstance(value, (int, float)) and not pd.isna(value):
                return Decimal(str(value))
            else:
                return Decimal(str(float(value)))
        except (ValueError, TypeError, decimal.InvalidOperation):
            logger.warning(f"Could not convert decimal value: {value} (type: {type(value)})")
            return Decimal(str(default))
    
    @classmethod
    def safe_string_convert(cls, value):
        """Safely convert values to string, handling NaN and None - OPTIMIZED"""
        if value is None or pd.isna(value) or value == 'nan':
            return ''
        
        if isinstance(value, (int, float)):
            if pd.isna(value):
                return ''
            return str(value)
        
        return str(value).strip()


class PortfolioUploadLog(models.Model):
    """Enhanced log model with auto row number generation - OPTIMIZED"""
    upload = models.ForeignKey(
        PortfolioUpload,
        on_delete=models.CASCADE,
        related_name='processing_logs'
    )
    row_number = models.PositiveIntegerField(
        help_text="Row number in the uploaded file (0 for system messages)",
        db_index=True  # Index for faster queries
    )
    client_name = models.CharField(max_length=255, blank=True, db_index=True)
    client_pan = models.CharField(max_length=50, blank=True, db_index=True)
    scheme_name = models.CharField(max_length=300, blank=True)
    
    STATUS_CHOICES = [
        ('success', 'Success'),
        ('error', 'Error'),
        ('warning', 'Warning'),
    ]
    
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, db_index=True)
    message = models.TextField()
    portfolio_entry = models.ForeignKey(
        ClientPortfolio,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='upload_logs'
    )
    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    
    class Meta:
        ordering = ['upload', 'row_number', 'created_at']
        verbose_name = 'Portfolio Upload Log'
        verbose_name_plural = 'Portfolio Upload Logs'
        indexes = [
            models.Index(fields=['upload', 'status']),
            models.Index(fields=['upload', 'row_number']),
            models.Index(fields=['upload', 'created_at']),
        ]
    
    def __str__(self):
        if self.row_number == 0:
            return f"{self.upload.upload_id} - System Log ({self.get_status_display()})"
        return f"{self.upload.upload_id} - Row {self.row_number} ({self.get_status_display()})"


@receiver(post_save, sender=PortfolioUpload)
def auto_process_portfolio_upload(sender, instance, created, **kwargs):
    """
    Automatically start processing when a new portfolio upload is created - OPTIMIZED
    """
    if created and instance.status == 'pending':
        # Log the trigger
        instance.create_log(
            row_number=0,
            status='success',
            message=f"Upload {instance.upload_id} queued for automatic processing"
        )
        
        # Always use thread fallback
        def process_in_background():
            try:
                instance.process_upload_with_logging()
            except Exception as e:
                logger.error(f"Auto-processing failed for {instance.upload_id}: {e}")
        
        thread = Thread(target=process_in_background)
        thread.daemon = True
        thread.start()

class MutualFundScheme(models.Model):
    """Enhanced mutual fund scheme model with upload support"""
    scheme_name = models.CharField(max_length=500)  # Increased length for long scheme names
    amc_name = models.CharField(max_length=200)     # Increased length for AMC names
    scheme_code = models.CharField(max_length=50)
    
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
    """Individual actions within an execution plan - Portfolio Independent Version"""
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
    
    # MODIFIED: Make scheme optional for portfolio-based actions
    scheme = models.ForeignKey(
        MutualFundScheme,
        on_delete=models.CASCADE,
        related_name='plan_actions',
        null=True,
        blank=True,
        help_text="Mutual Fund Scheme (for new investments only)"
    )
    
    # NEW: Portfolio scheme information for portfolio-based actions
    portfolio_scheme_name = models.CharField(
        max_length=500,
        blank=True,
        null=True,
        help_text="Scheme name from client portfolio (for portfolio-based actions)"
    )
    portfolio_holding_id = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Reference to ClientPortfolio holding ID"
    )
    portfolio_isin = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        help_text="ISIN from portfolio holding"
    )
    portfolio_folio_number = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        help_text="Folio number from portfolio holding"
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
    
    # NEW: Additional action-specific fields
    frequency = models.CharField(
        max_length=20,
        blank=True,
        null=True,
        choices=[
            ('daily', 'Daily'),
            ('weekly', 'Weekly'),
            ('fortnightly', 'Fortnightly'),
            ('monthly', 'Monthly'),
        ],
        help_text="Frequency for SIP/STP/SWP"
    )
    
    # For Switch/STP operations - target is always a new investment
    target_scheme = models.ForeignKey(
        MutualFundScheme,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='target_actions',
        help_text="Target scheme for switch/STP (always from MutualFundScheme)"
    )
    
    # NEW: Action execution mode
    action_mode = models.CharField(
        max_length=20,
        choices=[
            ('portfolio', 'Portfolio Action'),
            ('new_investment', 'New Investment'),
        ],
        default='new_investment',
        help_text="Whether this action is on existing portfolio or new investment"
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
        indexes = [
            models.Index(fields=['execution_plan', 'status']),
            models.Index(fields=['action_mode', 'action_type']),
            models.Index(fields=['portfolio_holding_id']),
        ]
    
    def __str__(self):
        scheme_name = self.get_scheme_display_name()
        return f"{self.get_action_type_display()} - {scheme_name}"

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

class PortfolioActionMapping(models.Model):
    """Track mapping between plan actions and portfolio holdings"""
    plan_action = models.OneToOneField(
        PlanAction,
        on_delete=models.CASCADE,
        related_name='portfolio_mapping'
    )
    
    # Portfolio holding reference
    portfolio_holding_id = models.PositiveIntegerField(
        help_text="Reference to ClientPortfolio ID"
    )
    original_scheme_name = models.CharField(
        max_length=500,
        help_text="Original scheme name from portfolio"
    )
    original_isin = models.CharField(
        max_length=50,
        blank=True,
        help_text="Original ISIN from portfolio"
    )
    original_folio_number = models.CharField(
        max_length=100,
        blank=True,
        help_text="Original folio number from portfolio"
    )
    original_units = models.DecimalField(
        max_digits=15,
        decimal_places=4,
        null=True,
        blank=True,
        help_text="Original units in portfolio at time of action creation"
    )
    original_value = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Original value in portfolio at time of action creation"
    )
    
    # Snapshot data
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name = 'Portfolio Action Mapping'
        verbose_name_plural = 'Portfolio Action Mappings'
        indexes = [
            models.Index(fields=['portfolio_holding_id']),
            models.Index(fields=['original_scheme_name']),
        ]
    
    def __str__(self):
        return f"Portfolio Mapping: {self.plan_action.get_action_type_display()} - {self.original_scheme_name}"
    
    @classmethod
    def create_mapping(cls, plan_action, portfolio_holding):
        """Create mapping from portfolio holding data"""
        if not plan_action.is_portfolio_action():
            return None
        
        mapping = cls.objects.create(
            plan_action=plan_action,
            portfolio_holding_id=portfolio_holding.id,
            original_scheme_name=portfolio_holding.scheme_name,
            original_isin=portfolio_holding.isin_number or '',
            original_folio_number=portfolio_holding.folio_number or '',
            original_units=portfolio_holding.units,
            original_value=portfolio_holding.total_value,
        )
        
        return mapping
    
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
    
# models.py - Add these models to your existing models.py file
class ClientUpload(models.Model):
    """Model to track client profile file uploads"""
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
        upload_to='client_uploads/',
        validators=[FileExtensionValidator(allowed_extensions=['xlsx', 'xls'])]
    )
    uploaded_by = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='client_uploads'
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
        help_text="Update existing client profiles if found"
    )
    
    # Archive fields
    is_archived = models.BooleanField(default=False)
    archived_at = models.DateTimeField(null=True, blank=True)
    archived_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='archived_client_uploads'
    )
    
    class Meta:
        ordering = ['-uploaded_at']
        verbose_name = 'Client Upload'
        verbose_name_plural = 'Client Uploads'
    
    def save(self, *args, **kwargs):
        if not self.upload_id:
            self.upload_id = self.generate_upload_id()
        super().save(*args, **kwargs)
    
    def generate_upload_id(self):
        """Generate unique upload ID"""
        from datetime import datetime
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        return f"CU{timestamp}"
    
    def generate_unique_pan_id(self, row_number, client_name):
        """Generate a unique PAN ID that fits in 10 characters with collision handling"""
        import hashlib
        import time
        from django.db import IntegrityError
        
        # Add timestamp to ensure uniqueness across uploads
        timestamp = str(int(time.time()))[-4:]  # Last 4 digits of timestamp
        
        # Create base hash input
        base_input = f"{row_number}_{client_name}_{self.upload_id}_{timestamp}"
        hash_obj = hashlib.md5(base_input.encode())
        hash_hex = hash_obj.hexdigest()[:4]  # Take first 4 characters of hash
        
        # Format: NA + 4 char hash + 4 char timestamp = 10 characters total
        unique_id = f"NA{hash_hex.upper()}{timestamp}"
        
        # Ensure we don't exceed 10 characters
        unique_id = unique_id[:10]
        
        # Check for existing PAN in database to avoid duplicates
        counter = 0
        original_id = unique_id
        
        while self._pan_exists_in_db(unique_id):
            counter += 1
            # If collision, use counter at the end
            counter_str = str(counter)
            if len(original_id) + len(counter_str) > 10:
                # Truncate original and add counter
                truncated_length = 10 - len(counter_str)
                unique_id = f"{original_id[:truncated_length]}{counter_str}"
            else:
                unique_id = f"{original_id}{counter_str}"
            
            # Safety check to prevent infinite loop
            if counter > 999:
                # Fallback to pure timestamp + counter
                fallback_time = str(int(time.time()))[-6:]
                unique_id = f"NA{fallback_time[:4]}"
                break
        
        return unique_id
    
    def _pan_exists_in_db(self, pan_number):
        """Check if PAN number already exists in database"""
        try:
            from django.core.exceptions import ObjectDoesNotExist
            return ClientProfile.objects.filter(pan_number=pan_number).exists()
        except Exception:
            return False
    
    def __str__(self):
        return f"{self.upload_id} - {self.file.name} ({self.get_status_display()})"
    
    def create_log(self, row_number, status, message, client_name='', pan_number='', client_profile=None):
        """Create a log entry for this upload"""
        return ClientUploadLog.objects.create(
            upload=self,
            row_number=row_number,
            client_name=client_name,
            pan_number=pan_number,
            status=status,
            message=message,
            client_profile=client_profile
        )
    
    def process_upload_with_logging(self):
        """Main method to process the uploaded client file - OPTIMIZED VERSION WITH FIXED PAN HANDLING"""
        import os
        import pandas as pd
        from django.db import transaction
        from decimal import Decimal
        import re
        from collections import defaultdict
        
        try:
            self.status = 'processing'
            self.save()
            
            # Batch for log entries
            log_entries = []
            
            # Log start
            log_entries.append(self._create_log_entry(0, 'success', f"Started processing upload {self.upload_id}"))
            
            # Check if file exists
            if not self.file or not os.path.exists(self.file.path):
                raise Exception(f"File not found: {self.file.path if self.file else 'No file attached'}")
            
            # Read Excel file
            try:
                df = pd.read_excel(self.file.path, engine='openpyxl')
                log_entries.append(self._create_log_entry(0, 'success', f"Successfully read Excel file with {len(df)} rows"))
            except Exception as e:
                log_entries.append(self._create_log_entry(0, 'error', f"Failed to read Excel file: {str(e)}"))
                raise
            
            # Remove any completely empty rows
            df = df.dropna(how='all')
            
            # Check if we have data
            if df.empty:
                raise Exception("Excel file contains no data rows")
            
            self.total_rows = len(df)
            self.save()
            
            log_entries.append(self._create_log_entry(0, 'success', f"Found {self.total_rows} rows to process"))
            
            # Log column information
            columns_found = list(df.columns)
            log_entries.append(self._create_log_entry(0, 'success', f"Columns found: {', '.join(columns_found)}"))
            
            # Expected columns validation
            required_columns = ['NAME']  # Remove PAN as required since we now handle NA
            missing_columns = [col for col in required_columns if col not in df.columns]
            
            if missing_columns:
                error_msg = f"Missing required columns: {', '.join(missing_columns)}"
                log_entries.append(self._create_log_entry(0, 'error', error_msg))
                raise Exception(error_msg)
            
            # Check if PAN column exists, if not add a warning
            if 'PAN' not in df.columns:
                log_entries.append(self._create_log_entry(0, 'warning', "PAN column not found, all entries will be treated as new profiles"))
                df['PAN'] = 'NA'  # Add a default PAN column with NA values
            
            log_entries.append(self._create_log_entry(0, 'success', f"Column validation successful"))
            
            # OPTIMIZATION 1: Pre-load all existing data to avoid repeated queries
            existing_profiles_map = self._preload_existing_profiles(df)
            users_map = self._preload_users()
            existing_clients_map = self._preload_existing_clients()
            
            # OPTIMIZATION 2: Prepare batch data structures
            profiles_to_create = []
            profiles_to_update = []
            clients_to_create = []
            clients_to_update = []
            
            # Track generated PAN IDs in this batch to avoid duplicates
            generated_pan_ids = set()
            
            # Process each row
            for index, row in df.iterrows():
                try:
                    result = self._process_single_client_row_optimized(
                        row, index + 1, existing_profiles_map, users_map, existing_clients_map, log_entries, generated_pan_ids
                    )
                    
                    if result:
                        profile_data, client_data, operation_type = result
                        
                        if operation_type == 'create_profile':
                            profiles_to_create.append(profile_data)
                        elif operation_type == 'update_profile':
                            profiles_to_update.append(profile_data)
                        
                        if client_data:
                            if client_data.get('operation') == 'create':
                                clients_to_create.append(client_data)
                            elif client_data.get('operation') == 'update':
                                clients_to_update.append(client_data)
                    
                    self.processed_rows += 1
                    
                    # Save progress and logs every 500 rows
                    if self.processed_rows % 500 == 0:
                        self._bulk_save_logs(log_entries)
                        log_entries = []
                        self.save()
                        log_entries.append(self._create_log_entry(0, 'success', f"Progress: {self.processed_rows}/{self.total_rows} rows processed"))
                        
                except Exception as row_error:
                    log_entries.append(self._create_log_entry(index + 1, 'error', f"Row processing failed: {str(row_error)}"))
                    self.failed_rows += 1
                    continue
            
            # OPTIMIZATION 3: Bulk database operations - FIXED VERSION WITH DUPLICATE HANDLING
            with transaction.atomic():
                # Bulk create new profiles - FIXED to avoid duplicates
                if profiles_to_create:
                    # Filter out any profiles that might already exist (safety check)
                    safe_profiles_to_create = []
                    duplicate_count = 0
                    
                    for profile_data in profiles_to_create:
                        pan_number = profile_data.get('pan_number')
                        
                        # Double-check that this PAN doesn't exist
                        if not ClientProfile.objects.filter(pan_number=pan_number).exists():
                            safe_profiles_to_create.append(profile_data)
                        else:
                            duplicate_count += 1
                            log_entries.append(self._create_log_entry(0, 'warning', 
                                f"Skipped duplicate PAN during bulk create: {pan_number}"))
                    
                    if duplicate_count > 0:
                        log_entries.append(self._create_log_entry(0, 'warning', 
                            f"Filtered out {duplicate_count} duplicate profiles from bulk create"))
                    
                    if safe_profiles_to_create:
                        # Convert dictionaries to ClientProfile objects
                        profile_objects = []
                        for profile_data in safe_profiles_to_create:
                            try:
                                profile_objects.append(ClientProfile(**profile_data))
                            except Exception as e:
                                log_entries.append(self._create_log_entry(0, 'error', 
                                    f"Failed to create profile object for PAN {profile_data.get('pan_number', 'unknown')}: {str(e)}"))
                        
                        if profile_objects:
                            try:
                                created_profiles = ClientProfile.objects.bulk_create(
                                    profile_objects, 
                                    batch_size=1000,
                                    ignore_conflicts=True  # This will ignore duplicate key violations
                                )
                                self.successful_rows += len(created_profiles)
                                log_entries.append(self._create_log_entry(0, 'success', 
                                    f"Bulk created {len(created_profiles)} new profiles (ignored conflicts)"))
                                
                                # Update existing_profiles_map with new profiles
                                for profile in created_profiles:
                                    existing_profiles_map[profile.pan_number] = profile
                            except Exception as e:
                                log_entries.append(self._create_log_entry(0, 'error', 
                                    f"Bulk create failed: {str(e)}"))
                                # Fallback to individual saves
                                individual_success = 0
                                for profile_obj in profile_objects:
                                    try:
                                        profile_obj.save()
                                        existing_profiles_map[profile_obj.pan_number] = profile_obj
                                        individual_success += 1
                                    except Exception as individual_error:
                                        log_entries.append(self._create_log_entry(0, 'error', 
                                            f"Individual save failed for PAN {profile_obj.pan_number}: {str(individual_error)}"))
                                
                                self.successful_rows += individual_success
                                log_entries.append(self._create_log_entry(0, 'warning', 
                                    f"Fallback individual saves: {individual_success} profiles created"))
                
                # Bulk update existing profiles - IMPROVED ERROR HANDLING
                if profiles_to_update:
                    update_batch = []
                    for profile_data in profiles_to_update:
                        pan_number = profile_data.get('pan_number')
                        
                        # Check if profile exists in the map
                        if not pan_number or pan_number not in existing_profiles_map:
                            log_entries.append(self._create_log_entry(0, 'error', 
                                f"Profile not found in existing_profiles_map for PAN: {pan_number}"))
                            continue
                            
                        profile = existing_profiles_map[pan_number]
                        
                        # Verify profile is not None
                        if profile is None:
                            log_entries.append(self._create_log_entry(0, 'error', 
                                f"Profile is None for PAN: {pan_number}"))
                            continue
                        
                        # Create a copy of profile_data for updating (don't modify original)
                        update_data = profile_data.copy()
                        update_data.pop('pan_number', None)  # Remove pan_number from update data
                        
                        # Update profile attributes
                        for field, value in update_data.items():
                            if field not in ['created_by']:  # Skip fields that shouldn't be updated
                                setattr(profile, field, value)
                        
                        update_batch.append(profile)
                        
                        if len(update_batch) >= 1000:
                            try:
                                ClientProfile.objects.bulk_update(update_batch, [
                                    'client_full_name', 'email', 'mobile_number', 'address_kyc',
                                    'family_head_name', 'mapped_rm', 'mapped_ops_exec', 'date_of_birth',
                                    'first_investment_date', 'status'
                                ])
                                self.updated_rows += len(update_batch)
                                log_entries.append(self._create_log_entry(0, 'success', 
                                    f"Bulk updated {len(update_batch)} profiles"))
                            except Exception as e:
                                log_entries.append(self._create_log_entry(0, 'error', 
                                    f"Bulk update failed: {str(e)}"))
                            update_batch = []
                    
                    # Handle remaining profiles in batch
                    if update_batch:
                        try:
                            ClientProfile.objects.bulk_update(update_batch, [
                                'client_full_name', 'email', 'mobile_number', 'address_kyc',
                                'family_head_name', 'mapped_rm', 'mapped_ops_exec', 'date_of_birth',
                                'first_investment_date', 'status'
                            ])
                            self.updated_rows += len(update_batch)
                            log_entries.append(self._create_log_entry(0, 'success', 
                                f"Final bulk updated {len(update_batch)} profiles"))
                        except Exception as e:
                            log_entries.append(self._create_log_entry(0, 'error', 
                                f"Final bulk update failed: {str(e)}"))
                
                # Bulk create/update clients - IMPROVED ERROR HANDLING
                if clients_to_create:
                    client_objects = []
                    for client_data in clients_to_create:
                        pan_number = client_data.get('pan_number')
                        
                        # Verify profile exists
                        if not pan_number or pan_number not in existing_profiles_map:
                            log_entries.append(self._create_log_entry(0, 'error', 
                                f"Cannot create client - profile not found for PAN: {pan_number}"))
                            continue
                            
                        profile = existing_profiles_map[pan_number]
                        if profile is None:
                            log_entries.append(self._create_log_entry(0, 'error', 
                                f"Cannot create client - profile is None for PAN: {pan_number}"))
                            continue
                        
                        client_data_copy = client_data.copy()
                        client_data_copy.pop('pan_number', None)
                        client_data_copy.pop('operation', None)
                        
                        client_objects.append(Client(
                            client_profile=profile,
                            name=client_data_copy.get('name', ''),
                            contact_info=client_data_copy.get('contact_info', 'N/A'),
                            aum=client_data_copy.get('aum', 0),
                            user=client_data_copy.get('user'),
                            created_by=self.uploaded_by
                        ))
                    
                    if client_objects:
                        try:
                            created_clients = Client.objects.bulk_create(
                                client_objects, 
                                batch_size=1000,
                                ignore_conflicts=True  # Ignore conflicts if any
                            )
                            log_entries.append(self._create_log_entry(0, 'success', 
                                f"Bulk created {len(created_clients)} new clients"))
                        except Exception as e:
                            log_entries.append(self._create_log_entry(0, 'error', 
                                f"Client bulk create failed: {str(e)}"))
                
                if clients_to_update:
                    client_update_batch = []
                    for client_data in clients_to_update:
                        pan_number = client_data.get('pan_number')
                        
                        # Check if client exists
                        if not pan_number or pan_number not in existing_clients_map:
                            log_entries.append(self._create_log_entry(0, 'warning', 
                                f"Client not found for update, PAN: {pan_number}"))
                            continue
                            
                        client = existing_clients_map[pan_number]
                        
                        # Verify client is not None
                        if client is None:
                            log_entries.append(self._create_log_entry(0, 'warning', 
                                f"Client is None for PAN: {pan_number}"))
                            continue
                        
                        # Create a copy and remove operation flags
                        update_data = client_data.copy()
                        update_data.pop('pan_number', None)
                        update_data.pop('operation', None)
                        
                        client.name = update_data.get('name', client.name)
                        client.contact_info = update_data.get('contact_info', client.contact_info)
                        client.aum = update_data.get('aum', client.aum)
                        client.user = update_data.get('user', client.user)
                        client_update_batch.append(client)
                        
                        if len(client_update_batch) >= 1000:
                            try:
                                Client.objects.bulk_update(client_update_batch, ['name', 'contact_info', 'aum', 'user'])
                                log_entries.append(self._create_log_entry(0, 'success', 
                                    f"Bulk updated {len(client_update_batch)} clients"))
                            except Exception as e:
                                log_entries.append(self._create_log_entry(0, 'error', 
                                    f"Client bulk update failed: {str(e)}"))
                            client_update_batch = []
                    
                    # Handle remaining clients
                    if client_update_batch:
                        try:
                            Client.objects.bulk_update(client_update_batch, ['name', 'contact_info', 'aum', 'user'])
                            log_entries.append(self._create_log_entry(0, 'success', 
                                f"Final bulk updated {len(client_update_batch)} clients"))
                        except Exception as e:
                            log_entries.append(self._create_log_entry(0, 'error', 
                                f"Final client bulk update failed: {str(e)}"))
            
            # Complete processing
            if self.failed_rows == 0:
                self.status = 'completed'
            else:
                self.status = 'partial'
            
            self.processed_at = timezone.now()
            self.save()
            
            success_msg = f"Processing completed. Success: {self.successful_rows}, Failed: {self.failed_rows}, Updated: {self.updated_rows}"
            log_entries.append(self._create_log_entry(0, 'success', success_msg))
            
            # Save remaining logs
            self._bulk_save_logs(log_entries)
            
            return True
            
        except Exception as e:
            error_msg = f"Processing failed: {str(e)}"
            
            self.status = 'failed'
            self.processed_at = timezone.now()
            self.error_details = {'error': str(e)}
            self.save()
            
            log_entries.append(self._create_log_entry(0, 'error', error_msg))
            self._bulk_save_logs(log_entries)
            return False

    def _create_log_entry(self, row_number, status, message, client_name='', pan_number='', client_profile=None):
        """Helper to create log entry dict"""
        return {
            'upload': self,
            'row_number': row_number,
            'client_name': client_name,
            'pan_number': pan_number,
            'status': status,
            'message': message,
            'client_profile': client_profile,
            'created_at': timezone.now()
        }

    def _bulk_save_logs(self, log_entries):
        """Bulk save log entries"""
        if log_entries:
            log_objects = [ClientUploadLog(**entry) for entry in log_entries]
            ClientUploadLog.objects.bulk_create(log_objects, batch_size=1000)

    def _preload_existing_profiles(self, df):
        """Pre-load all existing profiles to avoid repeated queries"""
        try:
            # Filter out NA and empty PAN numbers for preloading
            pan_numbers = df['PAN'].dropna().str.upper().str.strip()
            pan_numbers = pan_numbers[pan_numbers != ''].unique()
            # Remove NA entries from preloading since they won't match existing records
            pan_numbers = [pan for pan in pan_numbers if pan != 'NA' and not pan.startswith('NA')]
            
            if pan_numbers:
                existing_profiles = ClientProfile.objects.filter(pan_number__in=pan_numbers).select_related()
                profiles_map = {profile.pan_number: profile for profile in existing_profiles}
            else:
                profiles_map = {}
            
            # Also preload any existing NA-prefixed PANs to avoid collisions
            existing_na_profiles = ClientProfile.objects.filter(pan_number__startswith='NA').values_list('pan_number', flat=True)
            self._existing_na_pans = set(existing_na_profiles)
            
            # Log how many profiles were found
            self.create_log(0, 'success', f"Pre-loaded {len(profiles_map)} existing profiles from {len(pan_numbers)} unique valid PANs and {len(self._existing_na_pans)} existing NA entries")
            
            return profiles_map
        except Exception as e:
            self.create_log(0, 'error', f"Failed to preload existing profiles: {str(e)}")
            self._existing_na_pans = set()
            return {}

    def _preload_users(self):
        """Pre-load all users for mapping"""
        try:
            users = User.objects.filter(role__in=['rm', 'ops_exec', 'ops_team_lead']).only(
                'id', 'first_name', 'last_name', 'role'
            )
            users_map = {
                'rm': {},
                'ops': {}
            }
            
            for user in users:
                full_name = f"{user.first_name} {user.last_name}".strip().lower()
                first_name = user.first_name.lower() if user.first_name else ''
                last_name = user.last_name.lower() if user.last_name else ''
                
                if user.role == 'rm':
                    users_map['rm'][full_name] = user
                    users_map['rm'][first_name] = user
                    if last_name:
                        users_map['rm'][last_name] = user
                elif user.role in ['ops_exec', 'ops_team_lead']:
                    users_map['ops'][full_name] = user
                    users_map['ops'][first_name] = user
                    if last_name:
                        users_map['ops'][last_name] = user
            
            self.create_log(0, 'success', f"Pre-loaded {len(users)} users for mapping")
            return users_map
        except Exception as e:
            self.create_log(0, 'error', f"Failed to preload users: {str(e)}")
            return {'rm': {}, 'ops': {}}

    def _preload_existing_clients(self):
        """Pre-load existing clients"""
        try:
            clients = Client.objects.select_related('client_profile').all()
            # Only include clients with valid PANs (not NA entries)
            clients_map = {}
            for client in clients:
                if (client.client_profile and 
                    client.client_profile.pan_number and 
                    client.client_profile.pan_number != 'NA' and 
                    not client.client_profile.pan_number.startswith('NA')):
                    clients_map[client.client_profile.pan_number] = client
            
            self.create_log(0, 'success', f"Pre-loaded {len(clients_map)} existing clients")
            return clients_map
        except Exception as e:
            self.create_log(0, 'error', f"Failed to preload existing clients: {str(e)}")
            return {}

    def _process_single_client_row_optimized(self, row, row_number, existing_profiles_map, users_map, existing_clients_map, log_entries, generated_pan_ids):
        """Optimized version of single row processing - FIXED PAN GENERATION WITH COLLISION HANDLING"""
        try:
            import pandas as pd
            from decimal import Decimal
            import re
            
            # Helper functions
            def safe_string_convert(value):
                if value is None or pd.isna(value):
                    return ''
                result = str(value).strip()
                return '' if result.lower() == 'nan' else result
            
            def safe_decimal_convert(value, default=0):
                if value is None or pd.isna(value):
                    return Decimal(str(default))
                if isinstance(value, str):
                    value = value.replace(',', '').replace('₹', '').replace('$', '').strip()
                    if not value:
                        return Decimal(str(default))
                try:
                    return Decimal(str(float(value)))
                except (ValueError, TypeError):
                    return Decimal(str(default))
            
            def parse_date(date_value):
                if pd.isna(date_value) or not date_value:
                    return None
                
                from datetime import datetime as dt
                
                if isinstance(date_value, dt):
                    return date_value.date()
                
                date_str = str(date_value).strip()
                date_formats = [
                    '%d-%m-%Y', '%d/%m/%Y', '%Y-%m-%d', '%Y/%m/%d',
                    '%d-%m-%y', '%d/%m/%y', '%Y-%m-%dT%H:%M:%S.%fZ',
                    '%Y-%m-%dT%H:%M:%SZ'
                ]
                
                for format_str in date_formats:
                    try:
                        return dt.strptime(date_str, format_str).date()
                    except ValueError:
                        continue
                
                log_entries.append(self._create_log_entry(row_number, 'warning', f"Could not parse date: {date_value}"))
                return None
            
            def validate_pan(pan):
                if not pan or pan.strip() == '':
                    return True, "NA"  # Return NA instead of failing
                
                pan = pan.upper().strip()
                
                # If it's already NA, keep it as NA
                if pan == "NA":
                    return True, "NA"
                
                # Validate proper PAN format only if not empty/NA
                if len(pan) != 10:
                    log_entries.append(self._create_log_entry(row_number, 'warning', 
                        f"Invalid PAN length, setting to NA: {pan}"))
                    return True, "NA"
                
                pan_pattern = r'^[A-Z]{5}[0-9]{4}[A-Z]{1}$'
                if not re.match(pan_pattern, pan):
                    log_entries.append(self._create_log_entry(row_number, 'warning', 
                        f"Invalid PAN format, setting to NA: {pan}"))
                    return True, "NA"
                
                return True, pan
            
            def combine_address(row):
                address_parts = []
                for field in ['ADDRESS1', 'ADDRESS2', 'ADDRESS3', 'CITY', 'STATE', 'PIN']:
                    if field in row and not pd.isna(row[field]) and str(row[field]).strip():
                        address_parts.append(str(row[field]).strip())
                return ', '.join(address_parts) if address_parts else ''
            
            def find_user_optimized(name, user_type):
                """Optimized user lookup using pre-loaded data"""
                if not name:
                    return None
                
                name_lower = name.lower().strip()
                name_parts = name_lower.split()
                
                # Try exact match first
                if name_lower in users_map[user_type]:
                    return users_map[user_type][name_lower]
                
                # Try first name
                if name_parts and name_parts[0] in users_map[user_type]:
                    return users_map[user_type][name_parts[0]]
                
                # Try last name
                if len(name_parts) > 1 and name_parts[-1] in users_map[user_type]:
                    return users_map[user_type][name_parts[-1]]
                
                return None
            
            # Extract data
            client_name = safe_string_convert(row.get('NAME', ''))
            pan_number = safe_string_convert(row.get('PAN', ''))[:10] if safe_string_convert(row.get('PAN', '')) else ''
            email = safe_string_convert(row.get('EMAIL', ''))
            mobile_number = safe_string_convert(row.get('MOBILE', ''))
            
            # Validate required fields
            if not client_name:
                self.failed_rows += 1
                log_entries.append(self._create_log_entry(row_number, 'error', "Client name is required", client_name, pan_number))
                return None
            
            # Validate PAN - now handles empty/invalid PANs gracefully
            pan_valid, pan_result = validate_pan(pan_number)
            if not pan_valid:
                # This should never happen now since validate_pan always returns True
                self.failed_rows += 1
                log_entries.append(self._create_log_entry(row_number, 'error', pan_result, client_name, pan_number))
                return None
            
            pan_number = pan_result
            
            # Generate unique identifier for NA PAN entries - FIXED WITH COLLISION HANDLING
            if pan_number == "NA":
                unique_id = self.generate_unique_pan_id(row_number, client_name)
                
                # Check against already generated IDs in this batch
                counter = 0
                original_id = unique_id
                while unique_id in generated_pan_ids or self._pan_exists_in_db(unique_id):
                    counter += 1
                    # Create new variation
                    counter_str = str(counter)
                    if len(original_id) + len(counter_str) > 10:
                        truncated_length = 10 - len(counter_str)
                        unique_id = f"{original_id[:truncated_length]}{counter_str}"
                    else:
                        unique_id = f"{original_id}{counter_str}"[:10]
                    
                    # Safety check
                    if counter > 999:
                        # Generate completely new ID using current timestamp
                        import time
                        timestamp = str(int(time.time() * 1000))[-6:]  # Microsecond precision
                        unique_id = f"NA{timestamp}"[:10]
                        break
                
                # Add to generated set
                generated_pan_ids.add(unique_id)
                
                # Double-check length constraint
                if len(unique_id) > 10:
                    # Final fallback to sequential numbering
                    import time
                    timestamp = str(int(time.time()))[-4:]
                    unique_id = f"NA{timestamp}{counter:02d}"[:10]
                
                log_entries.append(self._create_log_entry(row_number, 'warning',
                    f"PAN is NA for {client_name}, using unique ID: {unique_id}", client_name, unique_id))
                pan_number = unique_id
            
            # Parse dates
            date_of_birth = parse_date(row.get('DATE OF BIRTH'))
            first_investment_date = parse_date(row.get('First Investment Date'))
            
            # Combine address
            address_kyc = combine_address(row)
            
            # Get other fields
            family_head_name = safe_string_convert(row.get('FAMILY HEAD', ''))
            aum_value = safe_decimal_convert(row.get('AUM', 0))
            
            # Personnel information - optimized lookup
            rm_name = safe_string_convert(row.get('RELATIONSHIP  MANAGER', ''))
            ops_name = safe_string_convert(row.get('OPERATIONS', ''))
            
            mapped_rm = find_user_optimized(rm_name, 'rm')
            mapped_ops = find_user_optimized(ops_name, 'ops')
            
            # Check existing profile using pre-loaded data
            # For NA PAN entries, we'll treat them as new profiles since we can't match them
            if pan_number.startswith("NA"):
                existing_profile = None
                update_existing = False
                log_entries.append(self._create_log_entry(row_number, 'info',
                    f"Generated unique PAN entry will be created as new profile: {client_name}", client_name, pan_number))
            else:
                existing_profile = existing_profiles_map.get(pan_number)
                update_existing = existing_profile is not None
            
            if existing_profile and not self.update_existing:
                log_entries.append(self._create_log_entry(row_number, 'warning',
                    f"Skipped existing profile for {client_name} - update disabled", client_name, pan_number))
                return None
            
            # Prepare profile data
            profile_data = {
                'client_full_name': client_name,
                'pan_number': pan_number,
                'email': email,
                'mobile_number': mobile_number,
                'address_kyc': address_kyc or 'Address not provided',
                'family_head_name': family_head_name,
                'mapped_rm': mapped_rm,
                'mapped_ops_exec': mapped_ops,
                'created_by': self.uploaded_by,
                'status': 'active'
            }
            
            # Add date fields
            if date_of_birth:
                profile_data['date_of_birth'] = date_of_birth
            else:
                from datetime import date
                profile_data['date_of_birth'] = date(1900, 1, 1)
                log_entries.append(self._create_log_entry(row_number, 'warning',
                    f"Using default date of birth for {client_name}", client_name, pan_number))
            
            if first_investment_date:
                profile_data['first_investment_date'] = first_investment_date
            
            # Prepare client data
            client_data = {
                'pan_number': pan_number,
                'name': client_name,
                'contact_info': mobile_number or email or 'N/A',
                'aum': aum_value,
                'user': mapped_rm,
            }
            
            if update_existing:
                log_entries.append(self._create_log_entry(row_number, 'success',
                    f"Prepared update for existing profile: {client_name}", client_name, pan_number))
                
                # Check if client exists
                existing_client = existing_clients_map.get(pan_number)
                if existing_client:
                    client_data['operation'] = 'update'
                else:
                    client_data['operation'] = 'create'
                
                return profile_data, client_data, 'update_profile'
            else:
                log_entries.append(self._create_log_entry(row_number, 'success',
                    f"Prepared creation for new profile: {client_name}", client_name, pan_number))
                
                # Create new profile object for mapping (but don't save yet)
                profile_obj = ClientProfile(**profile_data)
                existing_profiles_map[pan_number] = profile_obj
                
                client_data['operation'] = 'create'
                return profile_data, client_data, 'create_profile'
                
        except Exception as e:
            self.failed_rows += 1
            error_message = f"Row processing error: {str(e)}"
            log_entries.append(self._create_log_entry(row_number, 'error', error_message,
                client_name if 'client_name' in locals() else '',
                pan_number if 'pan_number' in locals() else ''))
            return None


class ClientUploadLog(models.Model):
    """Log entries for client upload processing"""
    upload = models.ForeignKey(
        ClientUpload,
        on_delete=models.CASCADE,
        related_name='processing_logs'
    )
    row_number = models.PositiveIntegerField(
        help_text="Row number in the uploaded file (0 for system messages)"
    )
    client_name = models.CharField(max_length=255, blank=True)
    pan_number = models.CharField(max_length=10, blank=True)
    
    STATUS_CHOICES = [
        ('success', 'Success'),
        ('error', 'Error'),
        ('warning', 'Warning'),
    ]
    
    status = models.CharField(max_length=10, choices=STATUS_CHOICES)
    message = models.TextField()
    client_profile = models.ForeignKey(
        'ClientProfile',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='upload_logs'
    )
    created_at = models.DateTimeField(default=timezone.now)
    
    class Meta:
        ordering = ['upload', 'row_number', 'created_at']
        verbose_name = 'Client Upload Log'
        verbose_name_plural = 'Client Upload Logs'
        indexes = [
            models.Index(fields=['upload', 'status']),
            models.Index(fields=['upload', 'row_number']),
        ]
    
    def __str__(self):
        if self.row_number == 0:
            return f"{self.upload.upload_id} - System Log ({self.get_status_display()})"
        return f"{self.upload.upload_id} - Row {self.row_number} ({self.get_status_display()})"


# Signal to auto-process uploads
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.db import transaction
import logging

logger = logging.getLogger(__name__)


@receiver(post_save, sender=ClientUpload)
def auto_process_client_upload(sender, instance, created, **kwargs):
    """Automatically process client uploads when created"""
    if created and instance.status == 'pending':
        try:
            transaction.on_commit(lambda: process_client_upload_deferred(instance.id))
        except Exception as e:
            logger.error(f"Error scheduling client upload processing for {instance.upload_id}: {e}")


def process_client_upload_deferred(upload_id):
    """Process client upload after transaction commit"""
    try:
        upload = ClientUpload.objects.get(id=upload_id)
        if upload.status == 'pending':
            upload.create_log(0, 'success', f"Upload {upload.upload_id} starting deferred processing")
            upload.process_upload_with_logging()
    except ClientUpload.DoesNotExist:
        logger.error(f"Client upload with id {upload_id} not found for deferred processing")
    except Exception as e:
        logger.error(f"Deferred processing failed for client upload id {upload_id}: {e}")
        try:
            upload = ClientUpload.objects.get(id=upload_id)
            upload.status = 'failed'
            upload.error_details = {'error': str(e)}
            upload.save()
        except:
            pass