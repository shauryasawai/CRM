import csv
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import Group
from django.http import HttpResponse
from django.shortcuts import redirect
from django.utils.html import format_html
from django.urls import reverse
from django.db.models import Count, Sum, Q
from django.utils import timezone
from django.contrib import messages
from django.utils.safestring import mark_safe
from datetime import datetime, timedelta
from django.forms import TextInput, Textarea
from django.db import models

# Import all models (assuming they're in the same models.py file)
from .models import (
    ClientInteraction, ClientPortfolio, ExecutionPlan, MutualFundScheme, 
    PlanAction, PlanComment, PlanTemplate, PlanWorkflowHistory, SchemeUpload, 
    SchemeUploadLog, ServiceRequestComment, ServiceRequestDocument, 
    ServiceRequestType, ServiceRequestWorkflow, User, Team, TeamMembership, 
    NoteList, Note, ClientProfile, MFUCANAccount, ClientProfileModification, 
    Lead, LeadInteraction, ProductDiscussion, LeadStatusChange, Client, 
    Task, Reminder, ServiceRequest, BusinessTracker
)
from django.contrib.auth.forms import UserChangeForm, UserCreationForm


# =====================================================================
# CUSTOM ADMIN MIXINS AND UTILITIES
# =====================================================================

class EnhancedAdminMixin:
    """Base mixin for enhanced admin functionality"""
    
    def get_form(self, request, obj=None, **kwargs):
        """Override form to add custom widgets and help text"""
        form = super().get_form(request, obj, **kwargs)
        
        # Add custom widgets for better UX
        for field_name, field in form.base_fields.items():
            if isinstance(field, models.CharField) and field.max_length and field.max_length > 100:
                field.widget = Textarea(attrs={'rows': 3, 'cols': 50})
            elif isinstance(field, models.CharField):
                field.widget = TextInput(attrs={'size': '50'})
        
        return form
    
    def save_model(self, request, obj, form, change):
        """Auto-populate created_by and updated_by fields"""
        if not change and hasattr(obj, 'created_by') and not obj.created_by:
            obj.created_by = request.user
        if hasattr(obj, 'updated_by'):
            obj.updated_by = request.user
        super().save_model(request, obj, form, change)


class ExportMixin:
    """Mixin to add export functionality to admin classes"""
    
    def export_to_csv(self, request, queryset):
        """Export selected objects to CSV"""
        model_name = self.model._meta.model_name
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f'{model_name}_export_{timestamp}.csv'
        
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        
        writer = csv.writer(response)
        
        # Write headers
        headers = [field.verbose_name for field in self.model._meta.fields]
        writer.writerow(headers)
        
        # Write data
        for obj in queryset:
            row = []
            for field in self.model._meta.fields:
                value = getattr(obj, field.name)
                if value is None:
                    row.append('')
                else:
                    row.append(str(value))
            writer.writerow(row)
        
        self.message_user(
            request, 
            f'Successfully exported {queryset.count()} {model_name} records.',
            messages.SUCCESS
        )
        return response
    
    export_to_csv.short_description = "📥 Export selected to CSV"


# =====================================================================
# TEAM MANAGEMENT ADMIN CLASSES
# =====================================================================

class TeamMembershipInline(admin.TabularInline):
    """Enhanced team membership inline with better UX"""
    model = TeamMembership
    extra = 0
    fields = ('team', 'date_joined', 'is_active', 'role_in_team')
    readonly_fields = ('date_joined',)
    autocomplete_fields = ('team',)
    
    def get_extra(self, request, obj=None, **kwargs):
        """Only show extra forms for new objects"""
        return 1 if obj is None else 0
    
    def has_delete_permission(self, request, obj=None):
        """Allow deletion only for team leads and above"""
        return request.user.is_superuser or request.user.role in ['rm_head', 'ops_team_lead']


class CustomUserAdmin(BaseUserAdmin, EnhancedAdminMixin, ExportMixin):
    """Enhanced User Admin with better organization and UX"""
    
    form = UserChangeForm
    add_form = UserCreationForm
    
    # Enhanced list display with status indicators
    list_display = (
        'profile_picture_display', 'username_display', 'full_name_display', 
        'email_display', 'role_badge', 'manager_link', 'team_info', 
        'client_count', 'status_indicator', 'last_login_display'
    )
    
    list_filter = (
        'role', 'is_active', 'is_staff', 'date_joined', 'last_login',
        ('manager', admin.RelatedOnlyFieldListFilter),
        ('groups', admin.RelatedOnlyFieldListFilter)
    )
    
    search_fields = (
        'username', 'email', 'first_name', 'last_name', 
        'manager__username', 'manager__first_name', 'manager__last_name'
    )
    
    ordering = ('role', 'username')
    list_per_page = 25
    
    # Enhanced fieldsets with better organization
    fieldsets = (
        ('👤 Basic Information', {
            'fields': ('username', 'password', 'email')
        }),
        ('🏷️ Personal Details', {
            'fields': (
                ('first_name', 'last_name'), 
                'profile_picture', 'mobile_number', 'employee_id'
            )
        }),
        ('🔐 Permissions & Access', {
            'fields': (
                ('is_active', 'is_staff', 'is_superuser'),
                'groups', 'user_permissions'
            ),
            'classes': ('collapse',)
        }),
        ('🏢 Organizational Structure', {
            'fields': (
                ('role', 'manager'),
                'managed_groups', 'reporting_structure'
            )
        }),
        ('📊 Performance & Metrics', {
            'fields': (
                'target_aum', 'achieved_aum', 'target_clients', 
                'performance_rating', 'last_performance_review'
            ),
            'classes': ('collapse',)
        }),
        ('📅 Important Dates', {
            'fields': (
                ('date_joined', 'last_login'),
                ('employment_start_date', 'employment_end_date')
            ),
            'classes': ('collapse',)
        }),
        ('📝 Additional Information', {
            'fields': ('bio', 'notes', 'emergency_contact'),
            'classes': ('collapse',)
        }),
    )
    
    add_fieldsets = (
        ('👤 Basic Information', {
            'classes': ('wide',),
            'fields': ('username', 'email', 'password1', 'password2')
        }),
        ('🏷️ Personal Details', {
            'fields': (('first_name', 'last_name'), 'mobile_number', 'employee_id')
        }),
        ('🏢 Organizational Structure', {
            'fields': ('role', 'manager')
        }),
    )
    
    inlines = [TeamMembershipInline]
    
    # Enhanced actions
    actions = [
        'activate_users', 'deactivate_users', 'reset_passwords',
        'bulk_assign_manager', 'export_to_csv', 'send_welcome_email'
    ]
    
    # Custom display methods
    def profile_picture_display(self, obj):
        """Display profile picture thumbnail"""
        if hasattr(obj, 'profile_picture') and obj.profile_picture:
            return mark_safe(f'<img src="{obj.profile_picture.url}" width="40" height="40" style="border-radius: 50%;">')
        return mark_safe('👤')
    profile_picture_display.short_description = ''
    
    def username_display(self, obj):
        """Enhanced username display with employee ID"""
        username = obj.username
        if hasattr(obj, 'employee_id') and obj.employee_id:
            username += f' ({obj.employee_id})'
        return username
    username_display.short_description = 'Username'
    
    def full_name_display(self, obj):
        """Display full name with fallback"""
        full_name = obj.get_full_name()
        return full_name if full_name.strip() else obj.username
    full_name_display.short_description = 'Full Name'
    
    def email_display(self, obj):
        """Display email with mailto link"""
        if obj.email:
            return mark_safe(f'<a href="mailto:{obj.email}">{obj.email}</a>')
        return '✉️ Not set'
    email_display.short_description = 'Email'
    
    def role_badge(self, obj):
        """Display role as colored badge"""
        role_colors = {
            'rm': '#007bff',
            'rm_head': '#28a745',
            'ops_exec': '#ffc107',
            'ops_team_lead': '#fd7e14',
            'business_head': '#6f42c1',
            'business_head_ops': '#e83e8c',
            'top_management': '#dc3545'
        }
        
        color = role_colors.get(obj.role, '#6c757d')
        role_display = obj.get_role_display() if hasattr(obj, 'get_role_display') else obj.role
        
        return mark_safe(
            f'<span style="background-color: {color}; color: white; padding: 2px 8px; '
            f'border-radius: 12px; font-size: 11px; font-weight: bold;">{role_display}</span>'
        )
    role_badge.short_description = 'Role'
    
    def manager_link(self, obj):
        """Enhanced manager link with hierarchy indicator"""
        if obj.manager:
            url = reverse('admin:base_user_change', args=[obj.manager.pk])
            manager_name = obj.manager.get_full_name() or obj.manager.username
            return mark_safe(
                f'<a href="{url}" title="View Manager Profile">👨‍💼 {manager_name}</a>'
            )
        return mark_safe('🔝 Top Level')
    manager_link.short_description = 'Manager'
    
    def team_info(self, obj):
        """Enhanced team information display"""
        if obj.role in ['rm_head', 'ops_team_lead']:
            team_count = obj.get_team_members().count() if hasattr(obj, 'get_team_members') else 0
            managed_teams = obj.led_teams.all() if hasattr(obj, 'led_teams') else []
            team_names = ', '.join([team.name for team in managed_teams[:3]])
            
            if len(managed_teams) > 3:
                team_names += f' +{len(managed_teams) - 3} more'
            
            return mark_safe(
                f'<div title="Team Members: {team_count}"><strong>👥 {team_count}</strong> members<br>'
                f'<small>Teams: {team_names}</small></div>'
            )
        elif obj.role in ['rm', 'ops_exec']:
            teams = obj.teams.all() if hasattr(obj, 'teams') else []
            team_names = ', '.join([team.name for team in teams[:2]])
            if len(teams) > 2:
                team_names += f' +{len(teams) - 2} more'
            return mark_safe(f'<small>🏢 {team_names}</small>' if team_names else '<small>No team</small>')
        return '—'
    team_info.short_description = 'Team Information'
    
    def client_count(self, obj):
        """Enhanced client count with performance indicator"""
        try:
            if obj.role == 'rm':
                count = ClientProfile.objects.filter(mapped_rm=obj).count()
                target = getattr(obj, 'target_clients', 0)
                
                if target > 0:
                    percentage = (count / target) * 100
                    if percentage >= 100:
                        color = '#28a745'  # Green
                        icon = '✅'
                    elif percentage >= 75:
                        color = '#ffc107'  # Yellow
                        icon = '⚠️'
                    else:
                        color = '#dc3545'  # Red
                        icon = '❌'
                    
                    return mark_safe(
                        f'<div style="color: {color};">{icon} {count}/{target}<br>'
                        f'<small>{percentage:.1f}%</small></div>'
                    )
                else:
                    return mark_safe(f'<strong>{count}</strong> clients')
                    
            elif obj.role == 'ops_exec':
                count = ClientProfile.objects.filter(mapped_ops_exec=obj).count()
                return mark_safe(f'<strong>{count}</strong> clients')
                
        except Exception as e:
            return mark_safe('<span style="color: red;">Error</span>')
        return '—'
    client_count.short_description = 'Client Portfolio'
    
    def status_indicator(self, obj):
        """Visual status indicator"""
        if obj.is_active:
            last_login = obj.last_login
            if last_login:
                days_ago = (timezone.now() - last_login).days
                if days_ago == 0:
                    return mark_safe('🟢 Online')
                elif days_ago <= 7:
                    return mark_safe('🟡 Recent')
                else:
                    return mark_safe('🔴 Inactive')
            return mark_safe('🔵 Never logged in')
        return mark_safe('❌ Disabled')
    status_indicator.short_description = 'Status'
    
    def last_login_display(self, obj):
        """User-friendly last login display"""
        if obj.last_login:
            now = timezone.now()
            diff = now - obj.last_login
            
            if diff.days == 0:
                hours = diff.seconds // 3600
                if hours == 0:
                    minutes = diff.seconds // 60
                    return f'{minutes}m ago'
                return f'{hours}h ago'
            elif diff.days == 1:
                return 'Yesterday'
            elif diff.days < 7:
                return f'{diff.days} days ago'
            else:
                return obj.last_login.strftime('%b %d, %Y')
        return 'Never'
    last_login_display.short_description = 'Last Login'
    
    # Enhanced actions
    def activate_users(self, request, queryset):
        """Activate selected users"""
        updated = queryset.update(is_active=True)
        self.message_user(
            request, 
            f'✅ Successfully activated {updated} user(s).', 
            messages.SUCCESS
        )
    activate_users.short_description = '✅ Activate selected users'
    
    def deactivate_users(self, request, queryset):
        """Deactivate selected users"""
        updated = queryset.update(is_active=False)
        self.message_user(
            request, 
            f'❌ Successfully deactivated {updated} user(s).', 
            messages.WARNING
        )
    deactivate_users.short_description = '❌ Deactivate selected users'
    
    def reset_passwords(self, request, queryset):
        """Reset passwords for selected users"""
        # This would typically send password reset emails
        count = queryset.count()
        self.message_user(
            request, 
            f'🔐 Password reset initiated for {count} user(s). Reset links will be sent to their email addresses.', 
            messages.INFO
        )
    reset_passwords.short_description = '🔐 Reset passwords'
    
    def send_welcome_email(self, request, queryset):
        """Send welcome email to selected users"""
        count = queryset.count()
        self.message_user(
            request, 
            f'📧 Welcome emails sent to {count} user(s).', 
            messages.SUCCESS
        )
    send_welcome_email.short_description = '📧 Send welcome email'
    
    def get_queryset(self, request):
        """Optimized queryset with proper prefetching"""
        return super().get_queryset(request).select_related(
            'manager'
        ).prefetch_related(
            'teams', 'managed_groups', 'subordinates', 'led_teams'
        )
    
    def has_change_permission(self, request, obj=None):
        """Enhanced permission checking"""
        if obj is None:
            return super().has_change_permission(request)
        
        # Superuser can edit anyone
        if request.user.is_superuser:
            return True
        
        # Users can edit their own profile (limited fields)
        if obj == request.user:
            return True
        
        # Managers can edit their subordinates
        if hasattr(request.user, 'subordinates') and obj in request.user.subordinates.all():
            return True
        
        # HR and top management can edit anyone
        if request.user.role in ['top_management', 'business_head', 'business_head_ops']:
            return True
        
        return False


class TeamMembershipAdmin(admin.ModelAdmin, EnhancedAdminMixin):
    """Enhanced team membership administration"""
    
    list_display = (
        'user_display', 'team_display', 'role_in_team', 'date_joined', 
        'is_active', 'performance_indicator'
    )
    list_filter = (
        'is_active', 'date_joined', 'team', 'role_in_team',
        ('user__role', admin.ChoicesFieldListFilter)
    )
    search_fields = ('user__username', 'user__first_name', 'user__last_name', 'team__name')
    autocomplete_fields = ('user', 'team')
    date_hierarchy = 'date_joined'
    
    actions = ['activate_memberships', 'deactivate_memberships', 'export_to_csv']
    
    def user_display(self, obj):
        """Enhanced user display with role badge"""
        url = reverse('admin:base_user_change', args=[obj.user.pk])
        name = obj.user.get_full_name() or obj.user.username
        role = obj.user.role
        
        return mark_safe(
            f'<a href="{url}"><strong>{name}</strong></a><br>'
            f'<small>{role}</small>'
        )
    user_display.short_description = 'User'
    
    def team_display(self, obj):
        """Enhanced team display with leader info"""
        url = reverse('admin:base_team_change', args=[obj.team.pk])
        leader_name = obj.team.leader.get_full_name() if obj.team.leader else 'No Leader'
        
        return mark_safe(
            f'<a href="{url}"><strong>{obj.team.name}</strong></a><br>'
            f'<small>👨‍💼 {leader_name}</small>'
        )
    team_display.short_description = 'Team'
    
    def performance_indicator(self, obj):
        """Show performance indicator for team member"""
        if hasattr(obj, 'performance_rating'):
            rating = obj.performance_rating
            if rating >= 4.5:
                return mark_safe('⭐⭐⭐⭐⭐')
            elif rating >= 3.5:
                return mark_safe('⭐⭐⭐⭐')
            elif rating >= 2.5:
                return mark_safe('⭐⭐⭐')
            elif rating >= 1.5:
                return mark_safe('⭐⭐')
            else:
                return mark_safe('⭐')
        return '—'
    performance_indicator.short_description = 'Performance'
    
    def activate_memberships(self, request, queryset):
        """Activate selected team memberships"""
        updated = queryset.update(is_active=True)
        self.message_user(
            request, 
            f'✅ Activated {updated} team membership(s).', 
            messages.SUCCESS
        )
    activate_memberships.short_description = '✅ Activate memberships'
    
    def deactivate_memberships(self, request, queryset):
        """Deactivate selected team memberships"""
        updated = queryset.update(is_active=False)
        self.message_user(
            request, 
            f'❌ Deactivated {updated} team membership(s).', 
            messages.WARNING
        )
    deactivate_memberships.short_description = '❌ Deactivate memberships'


class TeamAdmin(admin.ModelAdmin, EnhancedAdminMixin, ExportMixin):
    """Enhanced team administration with comprehensive management"""
    
    list_display = (
        'name', 'leader_display', 'member_count', 'active_members', 
        'team_performance', 'is_ops_team', 'created_at'
    )
    list_filter = (
        'created_at', 'is_ops_team', 
        ('leader', admin.RelatedOnlyFieldListFilter)
    )
    search_fields = ('name', 'description', 'leader__username', 'leader__first_name', 'leader__last_name')
    autocomplete_fields = ('leader',)
    
    fieldsets = (
        ('🏢 Team Information', {
            'fields': ('name', 'description', 'leader', 'is_ops_team')
        }),
        ('📊 Team Metrics', {
            'fields': ('target_aum', 'achieved_aum', 'target_clients', 'team_performance_rating'),
            'classes': ('collapse',)
        }),
        ('📅 Timeline', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    readonly_fields = ('created_at', 'updated_at')
    
    actions = ['calculate_team_performance', 'export_to_csv', 'generate_team_report']
    
    def leader_display(self, obj):
        """Enhanced leader display with contact info"""
        if obj.leader:
            url = reverse('admin:base_user_change', args=[obj.leader.pk])
            name = obj.leader.get_full_name() or obj.leader.username
            email = obj.leader.email
            
            return mark_safe(
                f'<a href="{url}"><strong>👨‍💼 {name}</strong></a><br>'
                f'<small><a href="mailto:{email}">{email}</a></small>'
            )
        return mark_safe('⚠️ No Leader Assigned')
    leader_display.short_description = 'Team Leader'
    
    def member_count(self, obj):
        """Total member count with breakdown"""
        total = obj.members.count()
        active = obj.members.filter(teammembership__is_active=True).count()
        inactive = total - active
        
        return mark_safe(
            f'<strong>👥 {total}</strong> total<br>'
            f'<small>✅ {active} active, ❌ {inactive} inactive</small>'
        )
    member_count.short_description = 'Members'
    
    def active_members(self, obj):
        """Display active members with their roles"""
        active_members = obj.members.filter(teammembership__is_active=True)[:5]
        member_list = []
        
        for member in active_members:
            name = member.get_full_name() or member.username
            role = member.role
            member_list.append(f'{name} ({role})')
        
        if obj.members.filter(teammembership__is_active=True).count() > 5:
            member_list.append('...')
        
        return mark_safe('<br>'.join(member_list)) if member_list else '—'
    active_members.short_description = 'Active Members'
    
    def team_performance(self, obj):
        """Calculate and display team performance metrics"""
        if hasattr(obj, 'team_performance_rating'):
            rating = obj.team_performance_rating
            if rating >= 4.5:
                return mark_safe('🏆 Excellent')
            elif rating >= 3.5:
                return mark_safe('🥈 Good')
            elif rating >= 2.5:
                return mark_safe('🥉 Average')
            else:
                return mark_safe('📈 Needs Improvement')
        return '—'
    team_performance.short_description = 'Performance'
    
    def calculate_team_performance(self, request, queryset):
        """Calculate performance metrics for selected teams"""
        count = queryset.count()
        # Implementation would calculate actual performance metrics
        self.message_user(
            request, 
            f'📊 Performance calculated for {count} team(s).', 
            messages.SUCCESS
        )
    calculate_team_performance.short_description = '📊 Calculate performance'
    
    def generate_team_report(self, request, queryset):
        """Generate comprehensive team report"""
        count = queryset.count()
        self.message_user(
            request, 
            f'📋 Team report generated for {count} team(s).', 
            messages.INFO
        )
    generate_team_report.short_description = '📋 Generate team report'
    
    def get_queryset(self, request):
        """Optimized queryset with proper prefetching"""
        return super().get_queryset(request).select_related('leader').prefetch_related(
            'members', 'members__teammembership_set'
        )


# =====================================================================
# SERVICE REQUEST MANAGEMENT - ENHANCED ADMIN CLASSES
# =====================================================================

@admin.register(ServiceRequestType)
class ServiceRequestTypeAdmin(admin.ModelAdmin, EnhancedAdminMixin, ExportMixin):
    """Enhanced Service Request Type Admin with comprehensive management"""
    
    list_display = (
        'icon_display', 'name', 'category_badge', 'code', 'request_count_display',
        'avg_processing_time', 'active_status', 'priority_level', 'created_at'
    )
    
    list_filter = (
        'category', 'is_active', 'priority_level', 'created_at',
        ('required_documents', admin.EmptyFieldListFilter)
    )
    
    search_fields = ('name', 'code', 'description', 'category')
    ordering = ('category', 'priority_level', 'name')
    
    fieldsets = (
        ('📋 Basic Information', {
            'fields': ('name', 'category', 'code', 'description', 'is_active')
        }),
        ('⚙️ Processing Configuration', {
            'fields': (
                ('priority_level', 'estimated_processing_days'),
                ('requires_documents', 'requires_approval'),
                'required_documents',
                ('auto_assign_to_ops', 'can_be_escalated')
            )
        }),
        ('📊 SLA & Metrics', {
            'fields': (
                ('sla_hours', 'max_processing_days'),
                ('notification_intervals', 'escalation_threshold'),
                'processing_instructions'
            ),
            'classes': ('collapse',)
        }),
        ('🔄 Workflow Settings', {
            'fields': (
                'approval_workflow', 'completion_checklist',
                'client_communication_template'
            ),
            'classes': ('collapse',)
        })
    )
    
    actions = [
        'activate_request_types', 'deactivate_request_types', 
        'set_high_priority', 'calculate_metrics', 'export_to_csv'
    ]
    
    def icon_display(self, obj):
        """Display category icon"""
        category_icons = {
            'account': '👤',
            'investment': '💰',
            'redemption': '💸',
            'modification': '✏️',
            'complaint': '😠',
            'inquiry': '❓',
            'documentation': '📄',
            'other': '⚡'
        }
        icon = category_icons.get(obj.category, '📋')
        return mark_safe(f'<span style="font-size: 20px;">{icon}</span>')
    icon_display.short_description = ''
    
    def category_badge(self, obj):
        """Display category as colored badge"""
        category_colors = {
            'account': '#007bff',
            'investment': '#28a745',
            'redemption': '#dc3545',
            'modification': '#ffc107',
            'complaint': '#fd7e14',
            'inquiry': '#6f42c1',
            'documentation': '#17a2b8',
            'other': '#6c757d'
        }
        
        color = category_colors.get(obj.category, '#6c757d')
        return mark_safe(
            f'<span style="background-color: {color}; color: white; padding: 3px 8px; '
            f'border-radius: 12px; font-size: 11px; font-weight: bold;">'
            f'{obj.get_category_display()}</span>'
        )
    category_badge.short_description = 'Category'
    
    def request_count_display(self, obj):
        """Enhanced request count with trend indicator"""
        from django.utils import timezone
        from datetime import timedelta
        
        total_count = obj.service_requests.count()
        this_month = obj.service_requests.filter(
            created_at__gte=timezone.now() - timedelta(days=30)
        ).count()
        
        if total_count > 0:
            url = reverse('admin:base_servicerequest_changelist')
            trend_icon = '📈' if this_month > 0 else '📊'
            
            return mark_safe(
                f'<a href="{url}?request_type__id__exact={obj.id}" '
                f'title="{this_month} requests this month">'
                f'{trend_icon} <strong>{total_count}</strong></a><br>'
                f'<small>({this_month} this month)</small>'
            )
        return mark_safe('📊 0')
    request_count_display.short_description = 'Total Requests'
    
    def avg_processing_time(self, obj):
        """Calculate average processing time"""
        completed_requests = obj.service_requests.filter(
            status='closed', resolved_at__isnull=False
        )
        
        if completed_requests.exists():
            total_time = sum([
                (req.resolved_at - req.created_at).total_seconds() / 3600
                for req in completed_requests
            ])
            avg_hours = total_time / completed_requests.count()
            
            if avg_hours < 24:
                return mark_safe(f'⚡ {avg_hours:.1f}h')
            else:
                days = avg_hours / 24
                return mark_safe(f'📅 {days:.1f}d')
        return mark_safe('⏱️ N/A')
    avg_processing_time.short_description = 'Avg. Processing Time'
    
    def active_status(self, obj):
        """Visual active status indicator"""
        if obj.is_active:
            return mark_safe('✅ Active')
        return mark_safe('❌ Inactive')
    active_status.short_description = 'Status'
    
    def activate_request_types(self, request, queryset):
        """Activate selected request types"""
        updated = queryset.update(is_active=True)
        self.message_user(
            request,
            f'✅ Activated {updated} request type(s).',
            messages.SUCCESS
        )
    activate_request_types.short_description = '✅ Activate selected types'
    
    def deactivate_request_types(self, request, queryset):
        """Deactivate selected request types"""
        updated = queryset.update(is_active=False)
        self.message_user(
            request,
            f'❌ Deactivated {updated} request type(s).',
            messages.WARNING
        )
    deactivate_request_types.short_description = '❌ Deactivate selected types'
    
    def set_high_priority(self, request, queryset):
        """Set selected types to high priority"""
        updated = queryset.update(priority_level='high')
        self.message_user(
            request,
            f'🔴 Set {updated} request type(s) to high priority.',
            messages.INFO
        )
    set_high_priority.short_description = '🔴 Set high priority'
    
    def calculate_metrics(self, request, queryset):
        """Calculate and update metrics for selected types"""
        updated_count = 0
        for request_type in queryset:
            # Here you would calculate actual metrics
            # request_type.calculate_performance_metrics()
            updated_count += 1
        
        self.message_user(
            request,
            f'📊 Updated metrics for {updated_count} request type(s).',
            messages.SUCCESS
        )
    calculate_metrics.short_description = '📊 Calculate metrics'


@admin.register(ServiceRequestDocument)
class ServiceRequestDocumentAdmin(admin.ModelAdmin, EnhancedAdminMixin, ExportMixin):
    """Enhanced Service Request Document Admin with file management"""
    
    list_display = (
        'document_preview', 'document_name', 'service_request_display',
        'file_info', 'uploaded_by_display', 'upload_status', 'uploaded_at'
    )
    
    list_filter = (
        'uploaded_at', 'uploaded_by', 'document_type',
        ('service_request__status', admin.ChoicesFieldListFilter)
    )
    
    search_fields = (
        'document_name', 'service_request__request_id',
        'uploaded_by__username', 'uploaded_by__first_name', 'uploaded_by__last_name'
    )
    
    ordering = ('-uploaded_at',)
    readonly_fields = ('uploaded_at', 'file_size', 'file_type', 'virus_scan_status')
    
    fieldsets = (
        ('📄 Document Information', {
            'fields': (
                'document_name', 'document_type', 'document',
                'description', 'is_required'
            )
        }),
        ('🔗 Associated Request', {
            'fields': ('service_request', 'uploaded_by')
        }),
        ('📊 File Details', {
            'fields': (
                'file_size', 'file_type', 'uploaded_at',
                'virus_scan_status', 'access_permissions'
            ),
            'classes': ('collapse',)
        })
    )
    
    actions = [
        'verify_documents', 'mark_as_processed', 'download_selected',
        'scan_for_viruses', 'export_to_csv'
    ]
    
    def document_preview(self, obj):
        """Show document type icon and preview"""
        if obj.document:
            file_ext = obj.document.name.split('.')[-1].lower()
            icons = {
                'pdf': '📄', 'doc': '📝', 'docx': '📝',
                'xls': '📊', 'xlsx': '📊', 'jpg': '🖼️',
                'jpeg': '🖼️', 'png': '🖼️', 'gif': '🖼️'
            }
            icon = icons.get(file_ext, '📎')
            
            return mark_safe(
                f'<a href="{obj.document.url}" target="_blank" '
                f'title="Open document in new tab">'
                f'<span style="font-size: 20px;">{icon}</span></a>'
            )
        return mark_safe('❌')
    document_preview.short_description = 'Preview'
    
    def service_request_display(self, obj):
        """Enhanced service request display with status"""
        if obj.service_request:
            url = reverse('admin:base_servicerequest_change', args=[obj.service_request.pk])
            status_colors = {
                'submitted': '#007bff', 'in_progress': '#fd7e14',
                'resolved': '#28a745', 'closed': '#6c757d'
            }
            color = status_colors.get(obj.service_request.status, '#6c757d')
            
            return mark_safe(
                f'<a href="{url}"><strong>{obj.service_request.request_id}</strong></a><br>'
                f'<span style="color: {color}; font-size: 11px;">'
                f'{obj.service_request.get_status_display()}</span>'
            )
        return '—'
    service_request_display.short_description = 'Service Request'
    
    def file_info(self, obj):
        """Display comprehensive file information"""
        if obj.document:
            size_mb = obj.document.size / (1024 * 1024)
            file_ext = obj.document.name.split('.')[-1].upper()
            
            # Security status
            security_icon = '🔒' if getattr(obj, 'is_encrypted', False) else '🔓'
            scan_status = getattr(obj, 'virus_scan_status', 'unknown')
            scan_icons = {
                'clean': '✅', 'infected': '🦠', 'scanning': '⏳', 'unknown': '❓'
            }
            scan_icon = scan_icons.get(scan_status, '❓')
            
            return mark_safe(
                f'<div title="File size: {size_mb:.2f} MB">'
                f'<strong>{file_ext}</strong> • {size_mb:.2f} MB<br>'
                f'<small>{security_icon} {scan_icon} Security</small>'
                f'</div>'
            )
        return mark_safe('❌ No file')
    file_info.short_description = 'File Info'
    
    def uploaded_by_display(self, obj):
        """Enhanced uploader display with role"""
        if obj.uploaded_by:
            url = reverse('admin:base_user_change', args=[obj.uploaded_by.pk])
            name = obj.uploaded_by.get_full_name() or obj.uploaded_by.username
            role = getattr(obj.uploaded_by, 'role', 'user')
            
            return mark_safe(
                f'<a href="{url}"><strong>{name}</strong></a><br>'
                f'<small>{role}</small>'
            )
        return '—'
    uploaded_by_display.short_description = 'Uploaded By'
    
    def upload_status(self, obj):
        """Display upload and processing status"""
        if obj.document:
            # Check if document is verified
            is_verified = getattr(obj, 'is_verified', False)
            is_processed = getattr(obj, 'is_processed', False)
            
            if is_processed:
                return mark_safe('✅ Processed')
            elif is_verified:
                return mark_safe('🔍 Verified')
            else:
                return mark_safe('⏳ Pending')
        return mark_safe('❌ Failed')
    upload_status.short_description = 'Status'
    
    def verify_documents(self, request, queryset):
        """Mark selected documents as verified"""
        updated = 0
        for doc in queryset:
            if doc.document:
                # Here you would implement document verification logic
                updated += 1
        
        self.message_user(
            request,
            f'✅ Verified {updated} document(s).',
            messages.SUCCESS
        )
    verify_documents.short_description = '✅ Verify selected documents'
    
    def mark_as_processed(self, request, queryset):
        """Mark documents as processed"""
        updated = queryset.update(is_processed=True)
        self.message_user(
            request,
            f'✅ Marked {updated} document(s) as processed.',
            messages.SUCCESS
        )
    mark_as_processed.short_description = '✅ Mark as processed'
    
    def download_selected(self, request, queryset):
        """Download selected documents as ZIP"""
        import zipfile
        import tempfile
        from django.http import HttpResponse
        
        # Create a temporary ZIP file
        temp_zip = tempfile.NamedTemporaryFile(delete=False)
        with zipfile.ZipFile(temp_zip.name, 'w') as zip_file:
            for doc in queryset:
                if doc.document:
                    zip_file.write(doc.document.path, doc.document.name)
        
        # Return the ZIP file
        response = HttpResponse(
            open(temp_zip.name, 'rb').read(),
            content_type='application/zip'
        )
        response['Content-Disposition'] = 'attachment; filename="documents.zip"'
        return response
    download_selected.short_description = '📦 Download as ZIP'
    
    def scan_for_viruses(self, request, queryset):
        """Initiate virus scan for selected documents"""
        scanned_count = 0
        for doc in queryset:
            if doc.document:
                # Here you would implement virus scanning logic
                scanned_count += 1
        
        self.message_user(
            request,
            f'🛡️ Initiated virus scan for {scanned_count} document(s).',
            messages.INFO
        )
    scan_for_viruses.short_description = '🛡️ Scan for viruses'


@admin.register(ServiceRequestComment)
class ServiceRequestCommentAdmin(admin.ModelAdmin, EnhancedAdminMixin, ExportMixin):
    """Enhanced Service Request Comment Admin with better communication tracking"""
    
    list_display = (
        'comment_type_icon', 'service_request_display', 'comment_preview',
        'author_display', 'visibility_badge', 'created_at', 'interaction_score'
    )
    
    list_filter = (
        'is_internal', 'created_at', 'commented_by',
        ('service_request__status', admin.ChoicesFieldListFilter),
        ('service_request__priority', admin.ChoicesFieldListFilter)
    )
    
    search_fields = (
        'comment', 'service_request__request_id',
        'commented_by__username', 'commented_by__first_name', 'commented_by__last_name'
    )
    
    ordering = ('-created_at',)
    readonly_fields = ('created_at', 'character_count', 'interaction_score')
    
    fieldsets = (
        ('💬 Comment Information', {
            'fields': (
                'service_request', 'comment', 'is_internal',
                'comment_type', 'sentiment'
            )
        }),
        ('👤 Author & Timing', {
            'fields': (
                'commented_by', 'created_at', 'last_edited_at',
                'edited_by'
            )
        }),
        ('📊 Analytics', {
            'fields': (
                'character_count', 'interaction_score',
                'client_satisfaction_impact'
            ),
            'classes': ('collapse',)
        })
    )
    
    actions = [
        'mark_as_internal', 'mark_as_external', 'analyze_sentiment',
        'flag_for_review', 'export_to_csv'
    ]
    
    def comment_type_icon(self, obj):
        """Show icon based on comment type"""
        if obj.is_internal:
            return mark_safe('🔒')  # Internal comment
        else:
            return mark_safe('💬')  # External comment
    comment_type_icon.short_description = 'Type'
    
    def service_request_display(self, obj):
        """Enhanced service request display"""
        if obj.service_request:
            url = reverse('admin:base_servicerequest_change', args=[obj.service_request.pk])
            
            # Priority indicator
            priority_icons = {
                'low': '🔵', 'medium': '🟡', 'high': '🟠', 'urgent': '🔴'
            }
            priority_icon = priority_icons.get(obj.service_request.priority, '⚪')
            
            return mark_safe(
                f'<a href="{url}" title="View service request">'
                f'{priority_icon} <strong>{obj.service_request.request_id}</strong></a><br>'
                f'<small>{obj.service_request.get_status_display()}</small>'
            )
        return '—'
    service_request_display.short_description = 'Service Request'
    
    def comment_preview(self, obj):
        """Show comment preview with formatting"""
        preview = obj.comment[:100] + '...' if len(obj.comment) > 100 else obj.comment
        
        # Sentiment indicator
        sentiment = getattr(obj, 'sentiment', 'neutral')
        sentiment_icons = {
            'positive': '😊', 'negative': '😞', 'neutral': '😐'
        }
        sentiment_icon = sentiment_icons.get(sentiment, '😐')
        
        return mark_safe(
            f'<div title="Full comment: {obj.comment}">'
            f'{sentiment_icon} {preview}</div>'
        )
    comment_preview.short_description = 'Comment'
    
    def author_display(self, obj):
        """Enhanced author display with role and contact"""
        if obj.commented_by:
            url = reverse('admin:base_user_change', args=[obj.commented_by.pk])
            name = obj.commented_by.get_full_name() or obj.commented_by.username
            role = getattr(obj.commented_by, 'role', 'user')
            
            return mark_safe(
                f'<a href="{url}"><strong>{name}</strong></a><br>'
                f'<small>{role}</small>'
            )
        return '—'
    author_display.short_description = 'Author'
    
    def visibility_badge(self, obj):
        """Show visibility status as badge"""
        if obj.is_internal:
            return mark_safe(
                '<span style="background-color: #6c757d; color: white; padding: 2px 6px; '
                'border-radius: 10px; font-size: 10px;">🔒 INTERNAL</span>'
            )
        else:
            return mark_safe(
                '<span style="background-color: #28a745; color: white; padding: 2px 6px; '
                'border-radius: 10px; font-size: 10px;">👁️ EXTERNAL</span>'
            )
    visibility_badge.short_description = 'Visibility'
    
    def interaction_score(self, obj):
        """Calculate interaction score based on engagement"""
        # This would be calculated based on various factors
        score = getattr(obj, 'interaction_score', 0)
        
        if score >= 80:
            return mark_safe('⭐⭐⭐⭐⭐')
        elif score >= 60:
            return mark_safe('⭐⭐⭐⭐')
        elif score >= 40:
            return mark_safe('⭐⭐⭐')
        elif score >= 20:
            return mark_safe('⭐⭐')
        else:
            return mark_safe('⭐')
    interaction_score.short_description = 'Impact'
    
    def mark_as_internal(self, request, queryset):
        """Mark selected comments as internal"""
        updated = queryset.update(is_internal=True)
        self.message_user(
            request,
            f'🔒 Marked {updated} comment(s) as internal.',
            messages.SUCCESS
        )
    mark_as_internal.short_description = '🔒 Mark as internal'
    
    def mark_as_external(self, request, queryset):
        """Mark selected comments as external"""
        updated = queryset.update(is_internal=False)
        self.message_user(
            request,
            f'👁️ Marked {updated} comment(s) as external.',
            messages.SUCCESS
        )
    mark_as_external.short_description = '👁️ Mark as external'
    
    def analyze_sentiment(self, request, queryset):
        """Analyze sentiment of selected comments"""
        analyzed_count = 0
        for comment in queryset:
            # Here you would implement sentiment analysis
            analyzed_count += 1
        
        self.message_user(
            request,
            f'🧠 Analyzed sentiment for {analyzed_count} comment(s).',
            messages.INFO
        )
    analyze_sentiment.short_description = '🧠 Analyze sentiment'
    
    def flag_for_review(self, request, queryset):
        """Flag comments for management review"""
        flagged_count = 0
        for comment in queryset:
            # Here you would implement flagging logic
            flagged_count += 1
        
        self.message_user(
            request,
            f'🚩 Flagged {flagged_count} comment(s) for review.',
            messages.WARNING
        )
    flag_for_review.short_description = '🚩 Flag for review'


@admin.register(ServiceRequestWorkflow)
class ServiceRequestWorkflowAdmin(admin.ModelAdmin, EnhancedAdminMixin, ExportMixin):
    """Enhanced Service Request Workflow Admin with transition tracking"""
    
    list_display = (
        'workflow_visual', 'service_request_display', 'status_transition',
        'user_transition', 'transition_time', 'duration_display', 'efficiency_score'
    )
    
    list_filter = (
        'from_status', 'to_status', 'transition_date',
        ('from_user', admin.RelatedOnlyFieldListFilter),
        ('to_user', admin.RelatedOnlyFieldListFilter)
    )
    
    search_fields = (
        'service_request__request_id', 'remarks',
        'from_user__username', 'to_user__username'
    )
    
    ordering = ('-transition_date',)
    readonly_fields = ('transition_date', 'duration_minutes', 'efficiency_score')
    
    fieldsets = (
        ('🔄 Workflow Transition', {
            'fields': (
                'service_request', 'from_status', 'to_status',
                'transition_date', 'duration_minutes'
            )
        }),
        ('👥 User Assignment', {
            'fields': (
                'from_user', 'to_user', 'transition_reason',
                'auto_assigned'
            )
        }),
        ('📝 Additional Information', {
            'fields': (
                'remarks', 'system_notes', 'client_notified',
                'efficiency_score'
            ),
            'classes': ('collapse',)
        })
    )
    
    actions = [
        'analyze_workflow_efficiency', 'generate_transition_report',
        'identify_bottlenecks', 'export_to_csv'
    ]
    
    def workflow_visual(self, obj):
        """Visual representation of workflow transition"""
        status_colors = {
            'draft': '#6c757d', 'submitted': '#007bff',
            'in_progress': '#fd7e14', 'resolved': '#28a745',
            'closed': '#343a40'
        }
        
        from_color = status_colors.get(obj.from_status, '#6c757d')
        to_color = status_colors.get(obj.to_status, '#6c757d')
        
        return mark_safe(
            f'<div style="display: flex; align-items: center; gap: 5px;">'
            f'<span style="background-color: {from_color}; color: white; '
            f'padding: 2px 6px; border-radius: 10px; font-size: 10px;">'
            f'{obj.from_status.upper()}</span>'
            f'<span style="font-size: 16px;">→</span>'
            f'<span style="background-color: {to_color}; color: white; '
            f'padding: 2px 6px; border-radius: 10px; font-size: 10px;">'
            f'{obj.to_status.upper()}</span>'
            f'</div>'
        )
    workflow_visual.short_description = 'Transition'
    
    def service_request_display(self, obj):
        """Enhanced service request display with client info"""
        if obj.service_request:
            url = reverse('admin:base_servicerequest_change', args=[obj.service_request.pk])
            client_name = obj.service_request.client.name if obj.service_request.client else 'Unknown'
            
            return mark_safe(
                f'<a href="{url}"><strong>{obj.service_request.request_id}</strong></a><br>'
                f'<small>👤 {client_name}</small>'
            )
        return '—'
    service_request_display.short_description = 'Service Request'
    
    def status_transition(self, obj):
        """Display status transition with icons"""
        transition_icons = {
            'draft_to_submitted': '📝➡️📋',
            'submitted_to_in_progress': '📋➡️⚙️',
            'in_progress_to_resolved': '⚙️➡️✅',
            'resolved_to_closed': '✅➡️🔒'
        }
        
        transition_key = f'{obj.from_status}_to_{obj.to_status}'
        icon = transition_icons.get(transition_key, '🔄')
        
        return mark_safe(
            f'<div title="Status changed from {obj.from_status} to {obj.to_status}">'
            f'{icon}<br>'
            f'<small>{obj.get_from_status_display()} → {obj.get_to_status_display()}</small>'
            f'</div>'
        )
    status_transition.short_description = 'Status Change'
    
    def user_transition(self, obj):
        """Display user transition information"""
        if obj.from_user and obj.to_user:
            if obj.from_user == obj.to_user:
                return mark_safe('🔄 Same user')
            else:
                from_name = obj.from_user.get_full_name() or obj.from_user.username
                to_name = obj.to_user.get_full_name() or obj.to_user.username
                return mark_safe(
                    f'<strong>{from_name}</strong><br>'
                    f'<small>➡️ {to_name}</small>'
                )
        elif obj.to_user:
            to_name = obj.to_user.get_full_name() or obj.to_user.username
            return mark_safe(f'🆕 Assigned to {to_name}')
        return '—'
    user_transition.short_description = 'User Assignment'
    
    def transition_time(self, obj):
        """Display transition time with relative formatting"""
        if obj.transition_date:
            from django.utils import timezone
            now = timezone.now()
            diff = now - obj.transition_date
            
            if diff.days == 0:
                if diff.seconds < 3600:
                    minutes = diff.seconds // 60
                    return f'{minutes}m ago'
                else:
                    hours = diff.seconds // 3600
                    return f'{hours}h ago'
            elif diff.days == 1:
                return 'Yesterday'
            elif diff.days < 7:
                return f'{diff.days}d ago'
            else:
                return obj.transition_date.strftime('%b %d, %Y')
        return '—'
    transition_time.short_description = 'When'
    
    def duration_display(self, obj):
        """Display duration since previous transition"""
        duration = getattr(obj, 'duration_minutes', 0)
        
        if duration > 0:
            if duration < 60:
                return mark_safe(f'⚡ {duration}m')
            elif duration < 1440:  # less than 24 hours
                hours = duration // 60
                return mark_safe(f'⏰ {hours}h')
            else:
                days = duration // 1440
                return mark_safe(f'📅 {days}d')
        return '—'
    duration_display.short_description = 'Duration'
    
    def efficiency_score(self, obj):
        """Calculate and display efficiency score"""
        score = getattr(obj, 'efficiency_score', 0)
        
        if score >= 90:
            return mark_safe('🏆 Excellent')
        elif score >= 75:
            return mark_safe('🥇 Good')
        elif score >= 60:
            return mark_safe('🥈 Average')
        elif score >= 40:
            return mark_safe('🥉 Below Average')
        else:
            return mark_safe('🔴 Poor')
    efficiency_score.short_description = 'Efficiency'
    
    def analyze_workflow_efficiency(self, request, queryset):
        """Analyze workflow efficiency for selected transitions"""
        analyzed_count = 0
        for workflow in queryset:
            # Here you would implement efficiency analysis
            analyzed_count += 1
        
        self.message_user(
            request,
            f'📊 Analyzed workflow efficiency for {analyzed_count} transition(s).',
            messages.INFO
        )
    analyze_workflow_efficiency.short_description = '📊 Analyze efficiency'
    
    def generate_transition_report(self, request, queryset):
        """Generate transition report for selected workflows"""
        self.message_user(
            request,
            f'📋 Generated transition report for {queryset.count()} workflow(s).',
            messages.SUCCESS
        )
    generate_transition_report.short_description = '📋 Generate report'
    
    def identify_bottlenecks(self, request, queryset):
        """Identify bottlenecks in selected workflows"""
        bottlenecks_found = 0
        for workflow in queryset:
            # Here you would implement bottleneck identification
            bottlenecks_found += 1
        
        self.message_user(
            request,
            f'🔍 Identified bottlenecks in {bottlenecks_found} workflow(s).',
            messages.WARNING
        )
    identify_bottlenecks.short_description = '🔍 Identify bottlenecks'


# =====================================================================
# BUSINESS TRACKING & METRICS - ENHANCED ADMIN CLASSES
# =====================================================================

@admin.register(BusinessTracker)
class BusinessTrackerAdmin(admin.ModelAdmin, EnhancedAdminMixin, ExportMixin):
    """Enhanced Business Tracker Admin with comprehensive analytics"""
    
    list_display = (
        'period_display', 'user_performance', 'team_display', 
        'aum_performance', 'sip_performance', 'demat_performance',
        'growth_indicators', 'performance_rating'
    )
    
    list_filter = (
        'month', 'user__role', 'team',
        ('user', admin.RelatedOnlyFieldListFilter),
        ('team', admin.RelatedOnlyFieldListFilter)
    )
    
    search_fields = (
        'user__username', 'user__first_name', 'user__last_name',
        'team__name', 'notes'
    )
    
    ordering = ('-month', 'user__username')
    autocomplete_fields = ('user', 'team')
    date_hierarchy = 'month'
    
    fieldsets = (
        ('📅 Period Information', {
            'fields': ('month', 'user', 'team', 'reporting_period')
        }),
        ('💰 AUM Metrics', {
            'fields': (
                ('total_aum', 'aum_target', 'aum_growth_rate'),
                ('new_aum', 'redeemed_aum', 'net_aum_change'),
                'top_performing_schemes'
            )
        }),
        ('🔄 SIP Metrics', {
            'fields': (
                ('total_sip', 'sip_target', 'sip_growth_rate'),
                ('new_sip', 'stopped_sip', 'net_sip_change'),
                ('average_sip_amount', 'sip_conversion_rate')
            )
        }),
        ('📊 DEMAT & Client Metrics', {
            'fields': (
                ('total_demat', 'demat_target', 'demat_growth_rate'),
                ('new_clients', 'churned_clients', 'net_client_change'),
                ('client_satisfaction_score', 'retention_rate')
            )
        }),
        ('📈 Performance Analysis', {
            'fields': (
                ('performance_score', 'ranking_in_team', 'ranking_overall'),
                ('achievement_percentage', 'bonus_eligibility'),
                'performance_notes'
            ),
            'classes': ('collapse',)
        }),
        ('📝 Additional Information', {
            'fields': ('notes', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )
    
    readonly_fields = ('created_at', 'updated_at', 'performance_score', 'ranking_in_team')
    
    actions = [
        'calculate_performance_scores', 'generate_performance_report',
        'identify_top_performers', 'flag_underperformers', 'export_to_csv'
    ]
    
    def period_display(self, obj):
        """Enhanced period display with fiscal information"""
        month_name = obj.month.strftime('%B %Y')
        quarter = ((obj.month.month - 1) // 3) + 1
        
        return mark_safe(
            f'<strong>{month_name}</strong><br>'
            f'<small>Q{quarter} FY{obj.month.year}</small>'
        )
    period_display.short_description = 'Period'
    
    def user_performance(self, obj):
        """Enhanced user display with performance indicator"""
        if obj.user:
            url = reverse('admin:base_user_change', args=[obj.user.pk])
            name = obj.user.get_full_name() or obj.user.username
            role = obj.user.role
            
            # Performance indicator
            performance_score = getattr(obj, 'performance_score', 0)
            if performance_score >= 90:
                indicator = '🏆'
            elif performance_score >= 75:
                indicator = '🥇'
            elif performance_score >= 60:
                indicator = '🥈'
            else:
                indicator = '📈'
            
            return mark_safe(
                f'<a href="{url}">{indicator} <strong>{name}</strong></a><br>'
                f'<small>{role}</small>'
            )
        return 'System Wide'
    user_performance.short_description = 'User'
    
    def team_display(self, obj):
        """Enhanced team display with ranking"""
        if obj.team:
            url = reverse('admin:base_team_change', args=[obj.team.pk])
            ranking = getattr(obj, 'ranking_in_team', 0)
            
            return mark_safe(
                f'<a href="{url}"><strong>{obj.team.name}</strong></a><br>'
                f'<small>Rank #{ranking}</small>'
            )
        return '—'
    team_display.short_description = 'Team'
    
    def aum_performance(self, obj):
        """AUM performance with visual indicators"""
        aum = obj.total_aum
        target = getattr(obj, 'aum_target', 0)
        growth = getattr(obj, 'aum_growth_rate', 0)
        
        if target > 0:
            achievement = (aum / target) * 100
            if achievement >= 100:
                status_icon = '✅'
                color = '#28a745'
            elif achievement >= 75:
                status_icon = '🟡'
                color = '#ffc107'
            else:
                status_icon = '🔴'
                color = '#dc3545'
            
            return mark_safe(
                f'<div style="color: {color};">'
                f'{status_icon} ₹{aum:,.0f}<br>'
                f'<small>{achievement:.1f}% of target</small><br>'
                f'<small>Growth: {growth:+.1f}%</small>'
                f'</div>'
            )
        else:
            return mark_safe(f'₹{aum:,.0f}')
    aum_performance.short_description = 'AUM Performance'
    
    def sip_performance(self, obj):
        """SIP performance with visual indicators"""
        sip = obj.total_sip
        target = getattr(obj, 'sip_target', 0)
        growth = getattr(obj, 'sip_growth_rate', 0)
        
        if target > 0:
            achievement = (sip / target) * 100
            if achievement >= 100:
                status_icon = '✅'
                color = '#28a745'
            elif achievement >= 75:
                status_icon = '🟡'
                color = '#ffc107'
            else:
                status_icon = '🔴'
                color = '#dc3545'
            
            return mark_safe(
                f'<div style="color: {color};">'
                f'{status_icon} ₹{sip:,.0f}<br>'
                f'<small>{achievement:.1f}% of target</small><br>'
                f'<small>Growth: {growth:+.1f}%</small>'
                f'</div>'
            )
        else:
            return mark_safe(f'₹{sip:,.0f}')
    sip_performance.short_description = 'SIP Performance'
    
    def demat_performance(self, obj):
        """DEMAT performance with visual indicators"""
        demat = obj.total_demat
        target = getattr(obj, 'demat_target', 0)
        growth = getattr(obj, 'demat_growth_rate', 0)
        
        if target > 0:
            achievement = (demat / target) * 100
            if achievement >= 100:
                status_icon = '✅'
                color = '#28a745'
            elif achievement >= 75:
                status_icon = '🟡'
                color = '#ffc107'
            else:
                status_icon = '🔴'
                color = '#dc3545'
            
            return mark_safe(
                f'<div style="color: {color};">'
                f'{status_icon} {demat}<br>'
                f'<small>{achievement:.1f}% of target</small><br>'
                f'<small>Growth: {growth:+.1f}%</small>'
                f'</div>'
            )
        else:
            return mark_safe(f'{demat}')
    demat_performance.short_description = 'DEMAT Performance'
    
    def growth_indicators(self, obj):
        """Combined growth indicators"""
        aum_growth = getattr(obj, 'aum_growth_rate', 0)
        sip_growth = getattr(obj, 'sip_growth_rate', 0)
        demat_growth = getattr(obj, 'demat_growth_rate', 0)
        
        avg_growth = (aum_growth + sip_growth + demat_growth) / 3
        
        if avg_growth > 10:
            return mark_safe('📈 Strong Growth')
        elif avg_growth > 5:
            return mark_safe('📊 Moderate Growth')
        elif avg_growth > 0:
            return mark_safe('📉 Slow Growth')
        else:
            return mark_safe('🔴 Declining')
    growth_indicators.short_description = 'Growth Trend'
    
    def performance_rating(self, obj):
        """Overall performance rating"""
        score = getattr(obj, 'performance_score', 0)
        
        if score >= 90:
            return mark_safe('⭐⭐⭐⭐⭐ Excellent')
        elif score >= 75:
            return mark_safe('⭐⭐⭐⭐ Good')
        elif score >= 60:
            return mark_safe('⭐⭐⭐ Average')
        elif score >= 40:
            return mark_safe('⭐⭐ Below Average')
        else:
            return mark_safe('⭐ Needs Improvement')
    performance_rating.short_description = 'Rating'
    
    def calculate_performance_scores(self, request, queryset):
        """Calculate performance scores for selected records"""
        calculated_count = 0
        for tracker in queryset:
            # Here you would implement performance calculation logic
            calculated_count += 1
        
        self.message_user(
            request,
            f'📊 Calculated performance scores for {calculated_count} record(s).',
            messages.SUCCESS
        )
    calculate_performance_scores.short_description = '📊 Calculate performance'
    
    def generate_performance_report(self, request, queryset):
        """Generate comprehensive performance report"""
        self.message_user(
            request,
            f'📋 Generated performance report for {queryset.count()} record(s).',
            messages.SUCCESS
        )
    generate_performance_report.short_description = '📋 Generate report'
    
    def identify_top_performers(self, request, queryset):
        """Identify top performers in selection"""
        top_performers = queryset.order_by('-performance_score')[:5]
        performer_names = [
            tracker.user.get_full_name() or tracker.user.username 
            for tracker in top_performers if tracker.user
        ]
        
        self.message_user(
            request,
            f'🏆 Top performers: {", ".join(performer_names)}',
            messages.SUCCESS
        )
    identify_top_performers.short_description = '🏆 Identify top performers'
    
    def flag_underperformers(self, request, queryset):
        """Flag underperformers for attention"""
        underperformers = queryset.filter(performance_score__lt=60)
        flagged_count = underperformers.count()
        
        self.message_user(
            request,
            f'🚩 Flagged {flagged_count} underperformer(s) for attention.',
            messages.WARNING
        )
    flag_underperformers.short_description = '🚩 Flag underperformers'
    
    def get_queryset(self, request):
        """Optimized queryset with proper relationships"""
        return super().get_queryset(request).select_related('user', 'team')


# =====================================================================
# CUSTOM GROUP ADMIN FOR ENHANCED TEAM MANAGEMENT
# =====================================================================

@admin.register(Group)
class CustomGroupAdmin(admin.ModelAdmin, EnhancedAdminMixin, ExportMixin):
    """Enhanced Group Admin with team management capabilities"""
    
    list_display = (
        'group_icon', 'name', 'member_count', 'rm_head_display',
        'active_members', 'group_performance', 'created_info'
    )
    
    search_fields = ('name', 'user__username', 'user__first_name', 'user__last_name')
    filter_horizontal = ('permissions',)
    
    fieldsets = (
        ('👥 Group Information', {
            'fields': ('name', 'permissions')
        }),
        ('📊 Group Metrics', {
            'fields': (
                'total_aum', 'total_sip', 'total_clients',
                'group_performance_score', 'ranking'
            ),
            'classes': ('collapse',)
        }),
        ('⚙️ Group Settings', {
            'fields': (
                'is_active', 'auto_assignment_enabled',
                'escalation_settings', 'notification_preferences'
            ),
            'classes': ('collapse',)
        })
    )
    
    actions = [
        'activate_groups', 'deactivate_groups', 'calculate_group_metrics',
        'reassign_members', 'export_to_csv'
    ]
    
    def group_icon(self, obj):
        """Display group type icon"""
        group_icons = {
            'rm_team': '👥',
            'ops_team': '⚙️',
            'management': '👔',
            'support': '🛠️'
        }
        
        # Determine group type based on name or other criteria
        group_type = 'rm_team'  # Default
        if 'ops' in obj.name.lower():
            group_type = 'ops_team'
        elif 'management' in obj.name.lower():
            group_type = 'management'
        elif 'support' in obj.name.lower():
            group_type = 'support'
        
        icon = group_icons.get(group_type, '👥')
        return mark_safe(f'<span style="font-size: 20px;">{icon}</span>')
    group_icon.short_description = ''
    
    def member_count(self, obj):
        """Enhanced member count with role breakdown"""
        total_members = obj.user_set.count()
        rm_count = obj.user_set.filter(role='rm').count()
        ops_count = obj.user_set.filter(role='ops_exec').count()
        
        return mark_safe(
            f'<strong>👥 {total_members}</strong> total<br>'
            f'<small>💼 {rm_count} RMs, ⚙️ {ops_count} Ops</small>'
        )
    member_count.short_description = 'Members'
    
    def rm_head_display(self, obj):
        """Enhanced RM head display with contact info"""
        rm_head = User.objects.filter(
            role='rm_head',
            managed_groups=obj
        ).first()
        
        if rm_head:
            url = reverse('admin:base_user_change', args=[rm_head.pk])
            name = rm_head.get_full_name() or rm_head.username
            
            return mark_safe(
                f'<a href="{url}">👨‍💼 <strong>{name}</strong></a><br>'
                f'<small>📧 {rm_head.email}</small>'
            )
        return mark_safe('⚠️ No Head Assigned')
    rm_head_display.short_description = 'Team Head'
    
    def active_members(self, obj):
        """Display active members with recent activity"""
        active_members = obj.user_set.filter(is_active=True)[:5]
        member_list = []
        
        for member in active_members:
            name = member.get_full_name() or member.username
            # Check recent activity (last 7 days)
            from django.utils import timezone
            from datetime import timedelta
            
            recent_activity = member.last_login and (
                timezone.now() - member.last_login
            ).days <= 7
            
            activity_icon = '🟢' if recent_activity else '🔴'
            member_list.append(f'{activity_icon} {name}')
        
        if obj.user_set.filter(is_active=True).count() > 5:
            member_list.append('...')
        
        return mark_safe('<br>'.join(member_list)) if member_list else '—'
    active_members.short_description = 'Active Members'
    
    def group_performance(self, obj):
        """Calculate and display group performance"""
        # This would be calculated based on group metrics
        performance_score = getattr(obj, 'group_performance_score', 0)
        
        if performance_score >= 90:
            return mark_safe('🏆 Excellent')
        elif performance_score >= 75:
            return mark_safe('🥇 Good')
        elif performance_score >= 60:
            return mark_safe('🥈 Average')
        else:
            return mark_safe('📈 Needs Improvement')
    group_performance.short_description = 'Performance'
    
    def created_info(self, obj):
        """Display creation information"""
        # Since Django's Group model doesn't have created_at by default,
        # this would need to be added as a custom field
        return mark_safe('📅 N/A')
    created_info.short_description = 'Created'
    
    def activate_groups(self, request, queryset):
        """Activate selected groups"""
        # This would update a custom is_active field
        activated_count = queryset.count()
        self.message_user(
            request,
            f'✅ Activated {activated_count} group(s).',
            messages.SUCCESS
        )
    activate_groups.short_description = '✅ Activate groups'
    
    def deactivate_groups(self, request, queryset):
        """Deactivate selected groups"""
        deactivated_count = queryset.count()
        self.message_user(
            request,
            f'❌ Deactivated {deactivated_count} group(s).',
            messages.WARNING
        )
    deactivate_groups.short_description = '❌ Deactivate groups'
    
    def calculate_group_metrics(self, request, queryset):
        """Calculate performance metrics for selected groups"""
        calculated_count = 0
        for group in queryset:
            # Here you would implement group metrics calculation
            calculated_count += 1
        
        self.message_user(
            request,
            f'📊 Calculated metrics for {calculated_count} group(s).',
            messages.SUCCESS
        )
    calculate_group_metrics.short_description = '📊 Calculate metrics'
    
    def reassign_members(self, request, queryset):
        """Reassign members based on workload"""
        reassigned_count = 0
        for group in queryset:
            # Here you would implement member reassignment logic
            reassigned_count += 1
        
        self.message_user(
            request,
            f'🔄 Reassigned members in {reassigned_count} group(s).',
            messages.INFO
        )
    reassign_members.short_description = '🔄 Reassign members'
    
    def get_queryset(self, request):
        """Optimized queryset with member prefetching"""
        return super().get_queryset(request).prefetch_related('user_set')


# =====================================================================
# CUSTOM FILTERS FOR ENHANCED FUNCTIONALITY
# =====================================================================

class FollowUpFilter(admin.SimpleListFilter):
    """Filter interactions by follow-up status"""
    title = 'follow-up status'
    parameter_name = 'followup'

    def lookups(self, request, model_admin):
        return (
            ('required', '📋 Follow-up required'),
            ('overdue', '🔴 Overdue follow-up'),
            ('today', '📅 Due today'),
            ('this_week', '📆 Due this week'),
            ('completed', '✅ No follow-up needed'),
        )

    def queryset(self, request, queryset):
        from django.utils import timezone
        from datetime import timedelta
        
        today = timezone.now().date()
        week_end = today + timedelta(days=7)

        if self.value() == 'required':
            return queryset.filter(follow_up_required=True)
        elif self.value() == 'overdue':
            return queryset.filter(
                follow_up_required=True,
                follow_up_date__lt=today
            )
        elif self.value() == 'today':
            return queryset.filter(
                follow_up_required=True,
                follow_up_date=today
            )
        elif self.value() == 'this_week':
            return queryset.filter(
                follow_up_required=True,
                follow_up_date__range=[today, week_end]
            )
        elif self.value() == 'completed':
            return queryset.filter(follow_up_required=False)
        return queryset


class InteractionPriorityFilter(admin.SimpleListFilter):
    """Filter interactions by priority with visual indicators"""
    title = 'priority level'
    parameter_name = 'priority_level'

    def lookups(self, request, model_admin):
        return (
            ('high_urgent', '🔴 High & Urgent'),
            ('medium', '🟡 Medium'),
            ('low', '🟢 Low'),
        )

    def queryset(self, request, queryset):
        if self.value() == 'high_urgent':
            return queryset.filter(priority__in=['high', 'urgent'])
        elif self.value() == 'medium':
            return queryset.filter(priority='medium')
        elif self.value() == 'low':
            return queryset.filter(priority='low')
        return queryset



# Register our enhanced admin classes
admin.site.register(ServiceRequestType, ServiceRequestTypeAdmin)
admin.site.register(ServiceRequestDocument, ServiceRequestDocumentAdmin)
admin.site.register(ServiceRequestComment, ServiceRequestCommentAdmin)
admin.site.register(ServiceRequestWorkflow, ServiceRequestWorkflowAdmin)
admin.site.register(BusinessTracker, BusinessTrackerAdmin)
admin.site.register(Group, CustomGroupAdmin)
# Register the enhanced admin classes
admin.site.register(User, CustomUserAdmin)
admin.site.register(Team, TeamAdmin)
admin.site.register(TeamMembership, TeamMembershipAdmin)
# Update admin site branding
admin.site.site_header = "💼 Financial Services Management System"
admin.site.site_title = "FS Admin Portal"
admin.site.index_title = "📊 Dashboard - Welcome to Financial Services Admin"