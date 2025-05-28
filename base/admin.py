from time import timezone
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import Group
from django.utils.html import format_html
from django.urls import reverse
from django.db.models import Count, Sum
from .models import (
    User, Lead, Client, Task, ServiceRequest, 
    InvestmentPlanReview, BusinessTracker, Team
)
from .forms import CustomUserCreationForm, CustomUserChangeForm


class CustomUserAdmin(BaseUserAdmin):
    """Custom User Admin with hierarchy display"""
    
    add_form = CustomUserCreationForm
    form = CustomUserChangeForm
    model = User
    
    list_display = (
        'username', 'email', 'first_name', 'last_name', 
        'role', 'manager_link', 'team_info', 'is_active', 'date_joined'
    )
    list_filter = ('role', 'is_active', 'is_staff', 'date_joined', 'groups')
    search_fields = ('username', 'email', 'first_name', 'last_name')
    ordering = ('role', 'username')
    
    fieldsets = BaseUserAdmin.fieldsets + (
        ('Hierarchy & Role', {
            'fields': ('role', 'manager', 'managed_teams')
        }),
    )
    
    add_fieldsets = BaseUserAdmin.add_fieldsets + (
        ('Hierarchy & Role', {
            'fields': ('role', 'manager')
        }),
    )
    
    def manager_link(self, obj):
        if obj.manager:
            url = reverse('admin:base_user_change', args=[obj.manager.pk])
            return format_html('<a href="{}">{}</a>', url, obj.manager.username)
        return '-'
    manager_link.short_description = 'Manager'
    
    def team_info(self, obj):
        if obj.role == 'rm_head':
            team_count = obj.get_team_members().count()
            return f"{team_count} team members"
        elif obj.role == 'rm':
            teams = obj.groups.all()
            return ', '.join([team.name for team in teams]) if teams else 'No team'
        return '-'
    team_info.short_description = 'Team Info'
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('manager').prefetch_related('groups')


class TeamAdmin(admin.ModelAdmin):
    """Team Admin"""
    
    list_display = ('name', 'head_link', 'member_count', 'created_at')
    list_filter = ('created_at', 'head')
    search_fields = ('name', 'description')
    
    def head_link(self, obj):
        if obj.head:
            url = reverse('admin:base_user_change', args=[obj.head.pk])
            return format_html('<a href="{}">{}</a>', url, obj.head.username)
        return '-'
    head_link.short_description = 'Team Head'
    
    def member_count(self, obj):
        # Count members in the group associated with this team
        try:
            group = Group.objects.get(name=obj.name)
            return group.user_set.filter(role='rm').count()
        except Group.DoesNotExist:
            return 0
    member_count.short_description = 'Members'


class LeadAdmin(admin.ModelAdmin):
    """Lead Admin with hierarchy filters"""
    
    list_display = (
        'name', 'status', 'assigned_to_link', 'contact_info', 
        'source', 'created_by_link', 'created_at'
    )
    list_filter = ('status', 'source', 'created_at', 'assigned_to__role')
    search_fields = ('name', 'contact_info', 'source')
    ordering = ('-created_at',)
    
    fieldsets = (
        ('Lead Information', {
            'fields': ('name', 'contact_info', 'source', 'status')
        }),
        ('Assignment', {
            'fields': ('assigned_to', 'created_by')
        }),
        ('Additional Info', {
            'fields': ('notes',)
        }),
    )
    
    def assigned_to_link(self, obj):
        if obj.assigned_to:
            url = reverse('admin:base_user_change', args=[obj.assigned_to.pk])
            return format_html('<a href="{}">{} ({})</a>', 
                             url, obj.assigned_to.username, obj.assigned_to.get_role_display())
        return '-'
    assigned_to_link.short_description = 'Assigned To'
    
    def created_by_link(self, obj):
        if obj.created_by:
            url = reverse('admin:base_user_change', args=[obj.created_by.pk])
            return format_html('<a href="{}">{}</a>', url, obj.created_by.username)
        return '-'
    created_by_link.short_description = 'Created By'


class ClientAdmin(admin.ModelAdmin):
    """Client Admin with financial metrics"""
    
    list_display = (
        'name', 'user_link', 'aum_display', 'sip_amount_display', 
        'demat_count', 'lead_link', 'created_at'
    )
    list_filter = ('created_at', 'user__role', 'demat_count')
    search_fields = ('name', 'contact_info', 'user__username')
    ordering = ('-aum', '-created_at')
    
    def user_link(self, obj):
        if obj.user:
            url = reverse('admin:base_user_change', args=[obj.user.pk])
            return format_html('<a href="{}">{}</a>', url, obj.user.username)
        return '-'
    user_link.short_description = 'RM'
    
    def aum_display(self, obj):
        return f"₹{obj.aum:,.2f}"
    aum_display.short_description = 'AUM'
    
    def sip_amount_display(self, obj):
        return f"₹{obj.sip_amount:,.2f}"
    sip_amount_display.short_description = 'SIP Amount'
    
    def lead_link(self, obj):
        if obj.lead:
            url = reverse('admin:base_lead_change', args=[obj.lead.pk])
            return format_html('<a href="{}">{}</a>', url, obj.lead.name)
        return '-'
    lead_link.short_description = 'Original Lead'


class TaskAdmin(admin.ModelAdmin):
    """Task Admin with assignment tracking"""
    
    list_display = (
        'title', 'assigned_to_link', 'assigned_by_link', 
        'priority', 'due_date', 'completed', 'created_at'
    )
    list_filter = ('priority', 'completed', 'created_at', 'due_date')
    search_fields = ('title', 'description', 'assigned_to__username')
    ordering = ('-created_at',)
    
    fieldsets = (
        ('Task Information', {
            'fields': ('title', 'description', 'priority', 'due_date')
        }),
        ('Assignment', {
            'fields': ('assigned_to', 'assigned_by')
        }),
        ('Status', {
            'fields': ('completed', 'completed_at')
        }),
    )
    
    def assigned_to_link(self, obj):
        if obj.assigned_to:
            url = reverse('admin:base_user_change', args=[obj.assigned_to.pk])
            return format_html('<a href="{}">{}</a>', url, obj.assigned_to.username)
        return '-'
    assigned_to_link.short_description = 'Assigned To'
    
    def assigned_by_link(self, obj):
        if obj.assigned_by:
            url = reverse('admin:base_user_change', args=[obj.assigned_by.pk])
            return format_html('<a href="{}">{}</a>', url, obj.assigned_by.username)
        return '-'
    assigned_by_link.short_description = 'Assigned By'


class ServiceRequestAdmin(admin.ModelAdmin):
    """Service Request Admin"""
    
    list_display = (
        'id', 'client_link', 'status', 'priority', 
        'raised_by_link', 'assigned_to_link', 'created_at'
    )
    list_filter = ('status', 'priority', 'created_at')
    search_fields = ('description', 'client__name', 'raised_by__username')
    ordering = ('-created_at',)
    
    def client_link(self, obj):
        url = reverse('admin:base_client_change', args=[obj.client.pk])
        return format_html('<a href="{}">{}</a>', url, obj.client.name)
    client_link.short_description = 'Client'
    
    def raised_by_link(self, obj):
        if obj.raised_by:
            url = reverse('admin:base_user_change', args=[obj.raised_by.pk])
            return format_html('<a href="{}">{}</a>', url, obj.raised_by.username)
        return '-'
    raised_by_link.short_description = 'Raised By'
    
    def assigned_to_link(self, obj):
        if obj.assigned_to:
            url = reverse('admin:base_user_change', args=[obj.assigned_to.pk])
            return format_html('<a href="{}">{}</a>', url, obj.assigned_to.username)
        return '-'
    assigned_to_link.short_description = 'Assigned To'


class InvestmentPlanReviewAdmin(admin.ModelAdmin):
    """Investment Plan Review Admin"""
    
    list_display = (
        'goal', 'client_link', 'created_by_link', 'principal_amount', 
        'monthly_investment', 'tenure_years', 'projected_return', 'created_at'
    )
    list_filter = ('tenure_years', 'created_at', 'expected_return_rate')
    search_fields = ('goal', 'client__name', 'created_by__username')
    ordering = ('-created_at',)
    
    def client_link(self, obj):
        url = reverse('admin:base_client_change', args=[obj.client.pk])
        return format_html('<a href="{}">{}</a>', url, obj.client.name)
    client_link.short_description = 'Client'
    
    def created_by_link(self, obj):
        if obj.created_by:
            url = reverse('admin:base_user_change', args=[obj.created_by.pk])
            return format_html('<a href="{}">{}</a>', url, obj.created_by.username)
        return '-'
    created_by_link.short_description = 'Created By'
    
    def projected_return(self, obj):
        return f"₹{obj.projected_value():,.2f}"
    projected_return.short_description = 'Projected Value'


class BusinessTrackerAdmin(admin.ModelAdmin):
    """Business Tracker Admin"""
    
    list_display = (
        'month', 'user_link', 'team_link', 'total_aum_display', 
        'total_sip_display', 'total_demat'
    )
    list_filter = ('month', 'user__role', 'team')
    search_fields = ('user__username', 'team__name')
    ordering = ('-month',)
    
    def user_link(self, obj):
        if obj.user:
            url = reverse('admin:base_user_change', args=[obj.user.pk])
            return format_html('<a href="{}">{}</a>', url, obj.user.username)
        return 'System Wide'
    user_link.short_description = 'User'
    
    def team_link(self, obj):
        if obj.team:
            url = reverse('admin:base_team_change', args=[obj.team.pk])
            return format_html('<a href="{}">{}</a>', url, obj.team.name)
        return '-'
    team_link.short_description = 'Team'
    
    def total_aum_display(self, obj):
        return f"₹{obj.total_aum:,.2f}"
    total_aum_display.short_description = 'Total AUM'
    
    def total_sip_display(self, obj):
        return f"₹{obj.total_sip:,.2f}"
    total_sip_display.short_description = 'Total SIP'


# Register models with custom admin classes
admin.site.register(User, CustomUserAdmin)
admin.site.register(Team, TeamAdmin)
admin.site.register(Lead, LeadAdmin)
admin.site.register(Client, ClientAdmin)
admin.site.register(Task, TaskAdmin)
admin.site.register(ServiceRequest, ServiceRequestAdmin)
admin.site.register(InvestmentPlanReview, InvestmentPlanReviewAdmin)
admin.site.register(BusinessTracker, BusinessTrackerAdmin)

# Customize admin site headers
admin.site.site_header = "CRM Administration"
admin.site.site_title = "CRM Admin"
admin.site.index_title = "Welcome to CRM Administration"

# Add custom admin actions
@admin.action(description='Mark selected leads as contacted')
def mark_leads_contacted(modeladmin, request, queryset):
    queryset.update(status='contacted')

@admin.action(description='Mark selected tasks as completed')
def mark_tasks_completed(modeladmin, request, queryset):
    queryset.update(completed=True, completed_at=timezone.now())

@admin.action(description='Close selected service requests')
def close_service_requests(modeladmin, request, queryset):
    queryset.update(status='closed', resolved_at=timezone.now())

# Add actions to respective admin
# Customize admin site headers
admin.site.site_header = "CRM Administration"
admin.site.site_title = "CRM Admin"
admin.site.index_title = "Welcome to CRM Administration"

from django.contrib import admin
from django.contrib.auth.models import Group
from django.contrib.auth.admin import GroupAdmin
from django.utils.html import format_html
from django.urls import reverse

class CustomGroupAdmin(GroupAdmin):
    """Enhanced Group Admin for Team Management"""
    
    list_display = ('name', 'member_count', 'rm_head_link', 'created_date')
    search_fields = ('name',)
    filter_horizontal = ('permissions',)
    
    def member_count(self, obj):
        return obj.user_set.filter(role='rm').count()
    member_count.short_description = 'RM Members'
    
    def rm_head_link(self, obj):
        # Find RM Head managing this team
        rm_head = User.objects.filter(
            role='rm_head',
            managed_teams=obj
        ).first()
        
        if rm_head:
            url = reverse('admin:base_user_change', args=[rm_head.pk])
            return format_html('<a href="{}">{}</a>', url, rm_head.username)
        return 'No Head Assigned'
    rm_head_link.short_description = 'Team Head'
    
    def created_date(self, obj):
        # Groups don't have created date, so we'll show a placeholder
        return "N/A"
    created_date.short_description = 'Created'

# Unregister default Group admin and register custom one
admin.site.unregister(Group)
admin.site.register(Group, CustomGroupAdmin)


# Enhanced User Admin for Team Management
class EnhancedUserAdmin(admin.ModelAdmin):
    list_display = (
        'username', 'email', 'role', 'manager_link', 
        'teams_display', 'is_active'
    )
    list_filter = ('role', 'is_active', 'groups')
    search_fields = ('username', 'email', 'first_name', 'last_name')
    filter_horizontal = ('groups', 'managed_teams')  # This makes team assignment easier
    
    fieldsets = (
        ('User Info', {
            'fields': ('username', 'email', 'first_name', 'last_name', 'password')
        }),
        ('Role & Hierarchy', {
            'fields': ('role', 'manager')
        }),
        ('Team Management', {
            'fields': ('groups', 'managed_teams'),
            'description': 'Groups = Teams this user belongs to, Managed Teams = Teams this user leads'
        }),
        ('Permissions', {
            'fields': ('is_active', 'is_staff', 'is_superuser'),
            'classes': ('collapse',)
        }),
    )
    
    def teams_display(self, obj):
        if obj.role == 'rm':
            teams = obj.groups.all()
            return ', '.join([team.name for team in teams]) if teams else 'No Team'
        elif obj.role == 'rm_head':
            managed = obj.managed_teams.all()
            return f"Manages: {', '.join([team.name for team in managed])}" if managed else 'No Teams'
        return '-'
    teams_display.short_description = 'Teams'