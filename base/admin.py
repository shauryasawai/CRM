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
from .models import (
    ClientInteraction, ClientPortfolio, ExecutionPlan, MutualFundScheme, PlanAction, PlanComment, PlanTemplate, PlanWorkflowHistory, SchemeUpload, SchemeUploadLog, ServiceRequestComment, ServiceRequestDocument, ServiceRequestType, ServiceRequestWorkflow, User, Team, TeamMembership, NoteList, Note,
    ClientProfile, MFUCANAccount,
    ClientProfileModification, Lead, LeadInteraction, ProductDiscussion, 
    LeadStatusChange, Client, Task, Reminder, ServiceRequest, 
    BusinessTracker, PortfolioUpload, PortfolioUploadLog
)
from django.contrib.auth.forms import UserChangeForm, UserCreationForm
from django.contrib import messages
from datetime import datetime, timedelta
from django.contrib.admin import SimpleListFilter
from django.utils.safestring import mark_safe


# =============================================================================
# 🎨 ENHANCED ADMIN BASE CLASS WITH USER-FRIENDLY FEATURES
# =============================================================================

class UserFriendlyAdminMixin:
    """Base mixin to add user-friendly features to admin classes"""
    
    def get_list_display_links(self, request, list_display):
        """Make first column clickable with clear indication"""
        if list_display:
            return [list_display[0]]
        return super().get_list_display_links(request, list_display)
    
    def get_readonly_fields(self, request, obj=None):
        """Add help text for readonly fields"""
        readonly = super().get_readonly_fields(request, obj)
        if obj and hasattr(obj, 'pk'):
            # Add created_at and updated_at as readonly for existing objects
            readonly = list(readonly)
            if hasattr(obj, 'created_at') and 'created_at' not in readonly:
                readonly.append('created_at')
            if hasattr(obj, 'updated_at') and 'updated_at' not in readonly:
                readonly.append('updated_at')
        return readonly

    def get_fieldsets(self, request, obj=None):
        """Add helpful section organization"""
        fieldsets = super().get_fieldsets(request, obj)
        if not fieldsets:
            return None
        
        # Add icons and better descriptions to fieldsets
        enhanced_fieldsets = []
        for name, options in fieldsets:
            if name:
                # Add emoji icons to section names for better visual organization
                if 'Basic' in name or 'Information' in name:
                    name = f"📋 {name}"
                elif 'Status' in name or 'Workflow' in name:
                    name = f"📊 {name}"
                elif 'Date' in name or 'Time' in name:
                    name = f"📅 {name}"
                elif 'Contact' in name or 'Personal' in name:
                    name = f"👤 {name}"
                elif 'Permission' in name or 'Security' in name:
                    name = f"🔒 {name}"
                elif 'System' in name or 'Meta' in name:
                    name = f"⚙️ {name}"
                elif 'Upload' in name or 'File' in name:
                    name = f"📁 {name}"
                elif 'Financial' in name or 'Investment' in name:
                    name = f"💰 {name}"
            enhanced_fieldsets.append((name, options))
        return enhanced_fieldsets


# =============================================================================
# 👥 USER MANAGEMENT - ENHANCED FOR NON-TECH USERS
# =============================================================================

class TeamMembershipInline(admin.TabularInline):
    model = TeamMembership
    extra = 0
    fields = ('team', 'date_joined', 'is_active')
    readonly_fields = ('date_joined',)
    verbose_name = "Team Assignment"
    verbose_name_plural = "Team Assignments"


class CustomUserAdmin(BaseUserAdmin, UserFriendlyAdminMixin):
    form = UserChangeForm
    add_form = UserCreationForm
    
    list_display = (
        'username_with_status', 'full_name_display', 'role_badge', 
        'manager_link', 'team_summary', 'client_count_badge', 
        'last_login_friendly', 'actions_quick'
    )
    list_filter = ('role', 'is_active', 'is_staff', 'date_joined', 'groups')
    search_fields = ('username', 'email', 'first_name', 'last_name')
    ordering = ('role', 'username')
    list_per_page = 25
    
    fieldsets = (
        ('🔑 Login Credentials', {'fields': ('username', 'password')}),
        ('👤 Personal Information', {
            'fields': ('first_name', 'last_name', 'email'),
            'description': 'Basic personal details for the user account'
        }),
        ('🔒 Account Permissions', {
            'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions'),
            'description': 'Control what this user can access and do in the system'
        }),
        ('📅 Important Dates', {
            'fields': ('last_login', 'date_joined'),
            'classes': ('collapse',)
        }),
        ('🏢 Role & Management', {
            'fields': ('role', 'manager', 'managed_groups'),
            'description': 'Set the user\'s role in the organization and reporting structure'
        }),
    )
    
    add_fieldsets = (
        ('🆕 Create New User', {
            'classes': ('wide',),
            'fields': ('username', 'password1', 'password2'),
            'description': 'Create login credentials for the new user'
        }),
        ('🏢 Role Assignment', {
            'fields': ('role', 'manager'),
            'description': 'Assign role and manager for this user'
        }),
    )
    
    inlines = [TeamMembershipInline]
    
    def username_with_status(self, obj):
        status_icon = "🟢" if obj.is_active else "🔴"
        staff_badge = " 👑" if obj.is_superuser else " 🛡️" if obj.is_staff else ""
        return format_html(
            '<strong>{}</strong> {} {}',
            obj.username, status_icon, staff_badge
        )
    username_with_status.short_description = 'Username & Status'
    username_with_status.admin_order_field = 'username'
    
    def full_name_display(self, obj):
        full_name = obj.get_full_name()
        if full_name:
            return format_html('<span title="Email: {}">{}</span>', obj.email or 'No email', full_name)
        return format_html('<em>No name set</em>')
    full_name_display.short_description = 'Full Name'
    
    def role_badge(self, obj):
        role_colors = {
            'top_management': '#6f42c1',
            'business_head': '#e83e8c',
            'business_head_ops': '#fd7e14',
            'rm_head': '#007bff',
            'rm': '#28a745',
            'ops_team_lead': '#20c997',
            'ops_exec': '#6c757d'
        }
        color = role_colors.get(obj.role, '#6c757d')
        role_display = obj.get_role_display() if hasattr(obj, 'get_role_display') else obj.role
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 8px; border-radius: 12px; font-size: 11px; font-weight: bold;">{}</span>',
            color, role_display.upper()
        )
    role_badge.short_description = 'Role'
    role_badge.admin_order_field = 'role'
    
    def manager_link(self, obj):
        if obj.manager:
            url = reverse('admin:base_user_change', args=[obj.manager.pk])
            return format_html(
                '<a href="{}" title="View manager details">👤 {}</a>', 
                url, obj.manager.get_full_name() or obj.manager.username
            )
        return format_html('<span style="color: #6c757d;">No manager</span>')
    manager_link.short_description = 'Reports To'
    
    def team_summary(self, obj):
        if obj.role in ['rm_head', 'ops_team_lead']:
            team_count = obj.get_team_members().count() if hasattr(obj, 'get_team_members') else 0
            managed_teams = obj.led_teams.all() if hasattr(obj, 'led_teams') else []
            team_names = ', '.join([team.name for team in managed_teams])
            return format_html(
                '<span title="Teams: {}">👥 {} members</span>', 
                team_names or 'No teams', team_count
            )
        elif obj.role in ['rm', 'ops_exec']:
            teams = obj.teams.all() if hasattr(obj, 'teams') else []
            team_list = ', '.join([team.name for team in teams])
            return format_html(
                '<span title="Member of: {}">{}</span>', 
                team_list or 'No teams', team_list or 'No team assigned'
            )
        return '—'
    team_summary.short_description = 'Team Info'
    
    def client_count_badge(self, obj):
        try:
            if obj.role == 'rm':
                count = ClientProfile.objects.filter(mapped_rm=obj).count()
                color = '#28a745' if count > 0 else '#6c757d'
                return format_html(
                    '<span style="background-color: {}; color: white; padding: 2px 6px; border-radius: 10px; font-size: 11px;">👥 {} clients</span>',
                    color, count
                )
            elif obj.role == 'ops_exec':
                count = ClientProfile.objects.filter(mapped_ops_exec=obj).count()
                color = '#17a2b8' if count > 0 else '#6c757d'
                return format_html(
                    '<span style="background-color: {}; color: white; padding: 2px 6px; border-radius: 10px; font-size: 11px;">⚙️ {} clients</span>',
                    color, count
                )
        except Exception:
            return format_html('<span style="color: #dc3545;">Error</span>')
        return '—'
    client_count_badge.short_description = 'Assigned Clients'
    
    def last_login_friendly(self, obj):
        if obj.last_login:
            time_ago = timezone.now() - obj.last_login
            if time_ago.days == 0:
                return format_html('<span style="color: #28a745;">Today</span>')
            elif time_ago.days == 1:
                return format_html('<span style="color: #ffc107;">Yesterday</span>')
            elif time_ago.days <= 7:
                return format_html('<span style="color: #fd7e14;">{} days ago</span>', time_ago.days)
            else:
                return format_html('<span style="color: #6c757d;">{}</span>', obj.last_login.strftime('%b %d, %Y'))
        return format_html('<span style="color: #dc3545;">Never logged in</span>')
    last_login_friendly.short_description = 'Last Seen'
    
    def actions_quick(self, obj):
        actions = []
        
        # Edit button
        edit_url = reverse('admin:base_user_change', args=[obj.pk])
        actions.append(f'<a href="{edit_url}" class="button" style="margin: 1px; padding: 3px 6px; font-size: 11px;">✏️ Edit</a>')
        
        # View clients button for RMs and Ops
        if obj.role in ['rm', 'ops_exec']:
            if obj.role == 'rm':
                clients_url = reverse('admin:base_clientprofile_changelist') + f'?mapped_rm__id__exact={obj.pk}'
                actions.append(f'<a href="{clients_url}" class="button" style="margin: 1px; padding: 3px 6px; font-size: 11px; background: #28a745; color: white;">👥 Clients</a>')
            else:
                clients_url = reverse('admin:base_clientprofile_changelist') + f'?mapped_ops_exec__id__exact={obj.pk}'
                actions.append(f'<a href="{clients_url}" class="button" style="margin: 1px; padding: 3px 6px; font-size: 11px; background: #17a2b8; color: white;">⚙️ Clients</a>')
        
        return format_html('<div style="white-space: nowrap;">{}</div>', ''.join(actions))
    actions_quick.short_description = 'Quick Actions'

    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'manager'
        ).prefetch_related(
            'teams',
            'managed_groups',
            'subordinates',
            'led_teams',
        )


# =============================================================================
# 👥 TEAM MANAGEMENT - ENHANCED
# =============================================================================

class TeamMembershipAdmin(admin.ModelAdmin, UserFriendlyAdminMixin):
    list_display = ('user_badge', 'team_link', 'date_joined_friendly', 'status_badge')
    list_filter = ('is_active', 'date_joined', 'team')
    search_fields = ('user__username', 'user__first_name', 'user__last_name', 'team__name')
    autocomplete_fields = ('user', 'team')
    list_per_page = 50
    
    def user_badge(self, obj):
        return format_html(
            '<strong>{}</strong><br><small style="color: #6c757d;">{}</small>',
            obj.user.get_full_name() or obj.user.username,
            obj.user.get_role_display() if hasattr(obj.user, 'get_role_display') else obj.user.role
        )
    user_badge.short_description = 'Team Member'
    
    def team_link(self, obj):
        url = reverse('admin:base_team_change', args=[obj.team.pk])
        return format_html('<a href="{}">{}</a>', url, obj.team.name)
    team_link.short_description = 'Team'
    
    def date_joined_friendly(self, obj):
        if obj.date_joined:
            return obj.date_joined.strftime('%b %d, %Y')
        return '—'
    date_joined_friendly.short_description = 'Joined Date'
    
    def status_badge(self, obj):
        if obj.is_active:
            return format_html('<span style="color: #28a745; font-weight: bold;">✅ Active</span>')
        return format_html('<span style="color: #dc3545; font-weight: bold;">❌ Inactive</span>')
    status_badge.short_description = 'Status'


class TeamAdmin(admin.ModelAdmin, UserFriendlyAdminMixin):
    list_display = ('team_name_badge', 'leader_info', 'member_stats', 'team_type_badge', 'created_friendly')
    list_filter = ('created_at', 'is_ops_team', 'leader')
    search_fields = ('name', 'description')
    autocomplete_fields = ('leader',)
    list_per_page = 25
    
    def team_name_badge(self, obj):
        icon = "⚙️" if obj.is_ops_team else "👥"
        return format_html('<strong>{} {}</strong>', icon, obj.name)
    team_name_badge.short_description = 'Team Name'
    team_name_badge.admin_order_field = 'name'
    
    def leader_info(self, obj):
        if obj.leader:
            url = reverse('admin:base_user_change', args=[obj.leader.pk])
            full_name = obj.leader.get_full_name() or obj.leader.username
            return format_html(
                '<a href="{}" title="View leader profile">👤 {}</a><br><small style="color: #6c757d;">{}</small>',
                url, full_name, obj.leader.get_role_display() if hasattr(obj.leader, 'get_role_display') else obj.leader.role
            )
        return format_html('<span style="color: #dc3545;">No Leader Assigned</span>')
    leader_info.short_description = 'Team Leader'
    
    def member_stats(self, obj):
        total_members = obj.members.count()
        active_members = obj.members.filter(teammembership__is_active=True).count()
        
        if total_members > 0:
            return format_html(
                '<span style="color: #28a745; font-weight: bold;">{}</span> active<br>'
                '<span style="color: #6c757d;">{} total</span>',
                active_members, total_members
            )
        return format_html('<span style="color: #6c757d;">No members</span>')
    member_stats.short_description = 'Team Size'
    
    def team_type_badge(self, obj):
        if obj.is_ops_team:
            return format_html('<span style="background-color: #17a2b8; color: white; padding: 3px 8px; border-radius: 12px; font-size: 11px;">⚙️ OPERATIONS</span>')
        return format_html('<span style="background-color: #28a745; color: white; padding: 3px 8px; border-radius: 12px; font-size: 11px;">👥 SALES</span>')
    team_type_badge.short_description = 'Type'
    
    def created_friendly(self, obj):
        return obj.created_at.strftime('%b %Y')
    created_friendly.short_description = 'Created'
    created_friendly.admin_order_field = 'created_at'

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('leader').prefetch_related('members')


# =============================================================================
# 📝 NOTES SYSTEM - ENHANCED
# =============================================================================

class NoteInline(admin.TabularInline):
    model = Note
    extra = 0
    fields = ('heading', 'content_preview', 'creation_date', 'due_date', 'completion_status')
    readonly_fields = ('creation_date', 'content_preview', 'completion_status')
    
    def content_preview(self, obj):
        if obj.content:
            preview = obj.content[:50] + "..." if len(obj.content) > 50 else obj.content
            return format_html('<span title="{}">{}</span>', obj.content, preview)
        return '—'
    content_preview.short_description = 'Content Preview'
    
    def completion_status(self, obj):
        if obj.is_completed:
            return format_html('<span style="color: #28a745;">✅ Done</span>')
        elif obj.due_date and obj.due_date < timezone.now().date():
            return format_html('<span style="color: #dc3545;">⚠️ Overdue</span>')
        return format_html('<span style="color: #ffc107;">⏳ Pending</span>')
    completion_status.short_description = 'Status'


class NoteListAdmin(admin.ModelAdmin, UserFriendlyAdminMixin):
    list_display = ('list_name_badge', 'user_info', 'notes_summary', 'activity_summary', 'quick_actions')
    list_filter = ('created_at', 'updated_at')
    search_fields = ('name', 'description', 'user__username', 'user__first_name', 'user__last_name')
    autocomplete_fields = ('user',)
    inlines = [NoteInline]
    list_per_page = 25
    
    def list_name_badge(self, obj):
        return format_html(
            '<strong>📝 {}</strong><br><small style="color: #6c757d;">{}</small>',
            obj.name,
            obj.description[:50] + "..." if obj.description and len(obj.description) > 50 else obj.description or "No description"
        )
    list_name_badge.short_description = 'Note List'
    list_name_badge.admin_order_field = 'name'
    
    def user_info(self, obj):
        url = reverse('admin:base_user_change', args=[obj.user.pk])
        full_name = obj.user.get_full_name() or obj.user.username
        return format_html('<a href="{}" title="View user profile">👤 {}</a>', url, full_name)
    user_info.short_description = 'Owner'
    
    def notes_summary(self, obj):
        total = obj.notes.count()
        completed = obj.notes.filter(is_completed=True).count()
        overdue = obj.notes.filter(is_completed=False, due_date__lt=timezone.now().date()).count()
        
        summary_parts = []
        if total > 0:
            summary_parts.append(f'<span style="color: #007bff; font-weight: bold;">{total} total</span>')
            if completed > 0:
                summary_parts.append(f'<span style="color: #28a745;">{completed} done</span>')
            if overdue > 0:
                summary_parts.append(f'<span style="color: #dc3545;">{overdue} overdue</span>')
        else:
            summary_parts.append('<span style="color: #6c757d;">No notes</span>')
        
        return format_html('<br>'.join(summary_parts))
    notes_summary.short_description = 'Notes Summary'
    
    def activity_summary(self, obj):
        created = obj.created_at.strftime('%b %d, %Y')
        updated = obj.updated_at.strftime('%b %d, %Y') if obj.updated_at != obj.created_at else None
        
        if updated:
            return format_html(
                'Created: {}<br>Updated: {}',
                created, updated
            )
        return format_html('Created: {}', created)
    activity_summary.short_description = 'Activity'
    
    def quick_actions(self, obj):
        actions = []
        edit_url = reverse('admin:base_notelist_change', args=[obj.pk])
        actions.append(f'<a href="{edit_url}" class="button" style="margin: 1px; padding: 3px 6px; font-size: 11px;">✏️ Edit</a>')
        
        notes_url = reverse('admin:base_note_changelist') + f'?note_list__id__exact={obj.pk}'
        actions.append(f'<a href="{notes_url}" class="button" style="margin: 1px; padding: 3px 6px; font-size: 11px; background: #007bff; color: white;">📝 Notes</a>')
        
        return format_html('<div style="white-space: nowrap;">{}</div>', ''.join(actions))
    quick_actions.short_description = 'Actions'
    
    def get_queryset(self, request):
        qs = super().get_queryset(request).select_related('user').prefetch_related('notes')
        if not request.user.is_superuser:
            qs = qs.filter(user=request.user)
        return qs
    
    def has_change_permission(self, request, obj=None):
        if obj and not request.user.is_superuser:
            return obj.user == request.user
        return super().has_change_permission(request, obj)


class NoteAdmin(admin.ModelAdmin, UserFriendlyAdminMixin):
    list_display = (
        'note_heading_badge', 'user_info', 'note_list_link', 
        'dates_summary', 'priority_status', 'quick_actions'
    )
    list_filter = ('is_completed', 'creation_date', 'due_date', 'note_list')
    search_fields = ('heading', 'content', 'user__username', 'note_list__name')
    autocomplete_fields = ('user', 'note_list')
    readonly_fields = ('created_at', 'updated_at', 'completed_at')
    date_hierarchy = 'creation_date'
    list_per_page = 50
    
    fieldsets = (
        ('📝 Note Information', {
            'fields': ('user', 'note_list', 'heading', 'content'),
            'description': 'Basic note details and content'
        }),
        ('📅 Important Dates', {
            'fields': ('creation_date', 'reminder_date', 'due_date'),
            'description': 'Set dates for reminders and deadlines'
        }),
        ('✅ Completion Status', {
            'fields': ('is_completed', 'completed_at'),
            'description': 'Track completion status'
        }),
        ('📎 Attachment', {
            'fields': ('attachment',),
            'classes': ('collapse',)
        }),
        ('⚙️ System Information', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    actions = ['mark_as_completed', 'mark_as_incomplete', 'set_due_date_today']
    
    def note_heading_badge(self, obj):
        status_icon = "✅" if obj.is_completed else "⏳"
        priority_color = "#dc3545" if obj.is_overdue else "#28a745" if obj.is_completed else "#ffc107"
        
        return format_html(
            '<span style="color: {};">{}</span> <strong>{}</strong><br>'
            '<small style="color: #6c757d;">{}</small>',
            priority_color, status_icon, obj.heading,
            obj.content[:50] + "..." if obj.content and len(obj.content) > 50 else obj.content or "No content"
        )
    note_heading_badge.short_description = 'Note'
    note_heading_badge.admin_order_field = 'heading'
    
    def user_info(self, obj):
        url = reverse('admin:base_user_change', args=[obj.user.pk])
        return format_html('<a href="{}" title="View user profile">👤 {}</a>', url, obj.user.get_full_name() or obj.user.username)
    user_info.short_description = 'Owner'
    
    def note_list_link(self, obj):
        url = reverse('admin:base_notelist_change', args=[obj.note_list.pk])
        return format_html('<a href="{}" title="View note list">📂 {}</a>', url, obj.note_list.name)
    note_list_link.short_description = 'List'
    
    def dates_summary(self, obj):
        created = obj.creation_date.strftime('%b %d') if obj.creation_date else 'No date'
        due = obj.due_date.strftime('%b %d') if obj.due_date else None
        
        date_info = f'Created: {created}'
        if due:
            if obj.due_date < timezone.now().date() and not obj.is_completed:
                date_info += f'<br><span style="color: #dc3545;">Due: {due} (overdue)</span>'
            else:
                date_info += f'<br>Due: {due}'
        
        return format_html(date_info)
    dates_summary.short_description = 'Dates'
    
    def priority_status(self, obj):
        if obj.is_completed:
            return format_html('<span style="color: #28a745; font-weight: bold;">✅ Completed</span>')
        elif obj.is_overdue:
            days_overdue = (timezone.now().date() - obj.due_date).days
            return format_html('<span style="color: #dc3545; font-weight: bold;">🚨 {} days overdue</span>', days_overdue)
        elif obj.due_date:
            days_left = (obj.due_date - timezone.now().date()).days
            if days_left == 0:
                return format_html('<span style="color: #ffc107; font-weight: bold;">⚡ Due today</span>')
            elif days_left > 0:
                return format_html('<span style="color: #007bff;">⏰ {} days left</span>', days_left)
        
        return format_html('<span style="color: #6c757d;">⏳ No deadline</span>')
    priority_status.short_description = 'Priority Status'
    
    def quick_actions(self, obj):
        actions = []
        edit_url = reverse('admin:base_note_change', args=[obj.pk])
        actions.append(f'<a href="{edit_url}" class="button" style="margin: 1px; padding: 3px 6px; font-size: 11px;">✏️ Edit</a>')
        
        if not obj.is_completed:
            # We'll handle this with JavaScript for immediate feedback
            actions.append(f'<button onclick="markCompleted({obj.pk})" class="button" style="margin: 1px; padding: 3px 6px; font-size: 11px; background: #28a745; color: white;">✅ Complete</button>')
        
        return format_html('<div style="white-space: nowrap;">{}</div>', ''.join(actions))
    quick_actions.short_description = 'Actions'
    
    def mark_as_completed(self, request, queryset):
        updated = queryset.update(is_completed=True, completed_at=timezone.now())
        self.message_user(request, f"✅ {updated} notes marked as completed", level=messages.SUCCESS)
    mark_as_completed.short_description = "✅ Mark selected notes as completed"
    
    def mark_as_incomplete(self, request, queryset):
        updated = queryset.update(is_completed=False, completed_at=None)
        self.message_user(request, f"⏳ {updated} notes marked as incomplete", level=messages.SUCCESS)
    mark_as_incomplete.short_description = "⏳ Mark selected notes as incomplete"
    
    def set_due_date_today(self, request, queryset):
        updated = queryset.update(due_date=timezone.now().date())
        self.message_user(request, f"📅 {updated} notes due date set to today", level=messages.SUCCESS)
    set_due_date_today.short_description = "📅 Set due date to today"
    
    def get_queryset(self, request):
        qs = super().get_queryset(request).select_related('user', 'note_list')
        if not request.user.is_superuser:
            qs = qs.filter(user=request.user)
        return qs
    
    def has_change_permission(self, request, obj=None):
        if obj and not request.user.is_superuser:
            return obj.user == request.user
        return super().has_change_permission(request, obj)


# =============================================================================
# 👤 CLIENT MANAGEMENT - ENHANCED FOR BETTER UX
# =============================================================================

class MFUCANAccountInline(admin.TabularInline):
    model = MFUCANAccount
    extra = 0
    fields = ('account_number', 'folio_number', 'amc_name', 'kyc_status_badge', 'is_primary')
    readonly_fields = ('kyc_status_badge',)
    verbose_name = "Mutual Fund Account"
    verbose_name_plural = "Mutual Fund Accounts"
    
    def kyc_status_badge(self, obj):
        if obj.kyc_status == 'verified':
            return format_html('<span style="color: #28a745; font-weight: bold;">✅ Verified</span>')
        elif obj.kyc_status == 'pending':
            return format_html('<span style="color: #ffc107; font-weight: bold;">⏳ Pending</span>')
        else:
            return format_html('<span style="color: #dc3545; font-weight: bold;">❌ Not Verified</span>')
    kyc_status_badge.short_description = 'KYC Status'


class ClientProfileModificationInline(admin.TabularInline):
    model = ClientProfileModification
    extra = 0
    fields = ('status_badge', 'requested_at', 'requested_by', 'reason_preview', 'approved_by', 'approved_at')
    readonly_fields = ('requested_at', 'approved_at', 'status_badge', 'reason_preview')
    autocomplete_fields = ('requested_by', 'approved_by')
    can_delete = False
    verbose_name = "Modification Request"
    verbose_name_plural = "Modification Requests"
    
    def status_badge(self, obj):
        status_colors = {
            'pending': '#ffc107',
            'approved': '#28a745',
            'rejected': '#dc3545'
        }
        color = status_colors.get(obj.status, '#6c757d')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 2px 6px; border-radius: 10px; font-size: 11px;">{}</span>',
            color, obj.get_status_display().upper()
        )
    status_badge.short_description = 'Status'
    
    def reason_preview(self, obj):
        if obj.reason and len(obj.reason) > 30:
            return obj.reason[:30] + "..."
        return obj.reason
    reason_preview.short_description = 'Reason'
    
    def has_add_permission(self, request, obj):
        return False


class ClientProfileAdmin(admin.ModelAdmin, UserFriendlyAdminMixin):
    list_display = (
        'client_info_badge', 'contact_summary', 'mapped_personnel', 
        'status_badge', 'investment_summary', 'last_activity', 'quick_actions'
    )
    list_filter = ('status', 'created_at', 'mapped_rm__role', 'first_investment_date')
    search_fields = (
        'client_id', 'client_full_name', 'family_head_name', 'email', 
        'mobile_number', 'pan_number'
    )
    readonly_fields = ('client_id', 'created_at', 'updated_at')
    autocomplete_fields = ('mapped_rm', 'mapped_ops_exec', 'created_by', 'muted_by')
    inlines = [MFUCANAccountInline, ClientProfileModificationInline]
    date_hierarchy = 'created_at'
    list_per_page = 25
    
    fieldsets = (
        ('👤 Client Information', {
            'fields': (
                'client_id', 'client_full_name', 'family_head_name', 'pan_number',
                'date_of_birth', 'email', 'mobile_number'
            ),
            'description': 'Basic client identification and contact details'
        }),
        ('📍 Address & Documentation', {
            'fields': ('address_kyc',),
            'description': 'KYC address and documentation'
        }),
        ('💰 Investment Information', {
            'fields': ('first_investment_date', 'status'),
            'description': 'Investment history and current status'
        }),
        ('👥 Personnel Assignment', {
            'fields': ('mapped_rm', 'mapped_ops_exec'),
            'description': 'Assigned relationship manager and operations executive'
        }),
        ('🔇 Muting Information', {
            'fields': ('muted_reason', 'muted_date', 'muted_by'),
            'classes': ('collapse',),
            'description': 'Information about muted clients'
        }),
        ('⚙️ System Information', {
            'fields': ('created_by', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    actions = ['mark_as_active', 'mark_as_muted', 'export_client_data', 'assign_to_me']
    
    def client_info_badge(self, obj):
        status_icon = "🟢" if obj.status == 'active' else "🔇" if obj.status == 'muted' else "⏸️"
        return format_html(
            '<div><strong>{} {}</strong></div>'
            '<div style="font-size: 11px; color: #6c757d;">ID: {} | PAN: {}</div>'
            '<div style="font-size: 11px; color: #6c757d;">{}</div>',
            status_icon, obj.client_full_name,
            obj.client_id, obj.pan_number or 'Not set',
            obj.family_head_name or 'No family head'
        )
    client_info_badge.short_description = 'Client Details'
    client_info_badge.admin_order_field = 'client_full_name'
    
    def contact_summary(self, obj):
        contact_parts = []
        if obj.email:
            contact_parts.append(f'📧 {obj.email}')
        if obj.mobile_number:
            contact_parts.append(f'📱 {obj.mobile_number}')
        if obj.date_of_birth:
            age = (timezone.now().date() - obj.date_of_birth).days // 365
            contact_parts.append(f'🎂 {age} years')
        
        return format_html('<br>'.join(contact_parts)) if contact_parts else format_html('<em style="color: #6c757d;">No contact info</em>')
    contact_summary.short_description = 'Contact Info'
    
    def mapped_personnel(self, obj):
        personnel = []
        
        if obj.mapped_rm:
            rm_url = reverse('admin:base_user_change', args=[obj.mapped_rm.pk])
            rm_name = obj.mapped_rm.get_full_name() or obj.mapped_rm.username
            personnel.append(f'<a href="{rm_url}" title="Relationship Manager">👤 {rm_name}</a>')
        else:
            personnel.append('<span style="color: #dc3545;">No RM assigned</span>')
        
        if obj.mapped_ops_exec:
            ops_url = reverse('admin:base_user_change', args=[obj.mapped_ops_exec.pk])
            ops_name = obj.mapped_ops_exec.get_full_name() or obj.mapped_ops_exec.username
            personnel.append(f'<a href="{ops_url}" title="Operations Executive">⚙️ {ops_name}</a>')
        else:
            personnel.append('<span style="color: #ffc107;">No Ops assigned</span>')
        
        return format_html('<br>'.join(personnel))
    mapped_personnel.short_description = 'Assigned Staff'
    
    def status_badge(self, obj):
        status_config = {
            'active': ('#28a745', '🟢 Active'),
            'muted': ('#6c757d', '🔇 Muted'),
            'inactive': ('#dc3545', '⏸️ Inactive')
        }
        color, label = status_config.get(obj.status, ('#6c757d', obj.status))
        
        badge = format_html(
            '<span style="background-color: {}; color: white; padding: 3px 8px; border-radius: 12px; font-size: 11px; font-weight: bold;">{}</span>',
            color, label
        )
        
        if obj.status == 'muted' and obj.muted_reason:
            badge += format_html('<br><small style="color: #6c757d;" title="{}">{}</small>', 
                                obj.muted_reason, obj.muted_reason[:20] + "..." if len(obj.muted_reason) > 20 else obj.muted_reason)
        
        return badge
    status_badge.short_description = 'Status'
    status_badge.admin_order_field = 'status'
    
    def investment_summary(self, obj):
        summary = []
        
        if obj.first_investment_date:
            years_invested = (timezone.now().date() - obj.first_investment_date).days // 365
            summary.append(f'📅 {years_invested} years client')
            summary.append(f'Started: {obj.first_investment_date.strftime("%b %Y")}')
        else:
            summary.append('<span style="color: #ffc107;">No investment date</span>')
        
        # Add account count if available
        account_count = obj.mfucan_accounts.count() if hasattr(obj, 'mfucan_accounts') else 0
        if account_count > 0:
            summary.append(f'🏦 {account_count} accounts')
        
        return format_html('<br>'.join(summary))
    investment_summary.short_description = 'Investment Info'
    
    def last_activity(self, obj):
        last_modified = obj.updated_at if obj.updated_at != obj.created_at else None
        created = obj.created_at.strftime('%b %d, %Y')
        
        if last_modified:
            return format_html(
                'Modified: {}<br>Created: {}',
                last_modified.strftime('%b %d, %Y'), created
            )
        return format_html('Created: {}', created)
    last_activity.short_description = 'Activity'
    
    def quick_actions(self, obj):
        actions = []
        
        # Edit button
        edit_url = reverse('admin:base_clientprofile_change', args=[obj.pk])
        actions.append(f'<a href="{edit_url}" class="button" style="margin: 1px; padding: 3px 6px; font-size: 11px;">✏️ Edit</a>')
        
        # View interactions
        interactions_url = reverse('admin:base_clientinteraction_changelist') + f'?client_profile__id__exact={obj.pk}'
        actions.append(f'<a href="{interactions_url}" class="button" style="margin: 1px; padding: 3px 6px; font-size: 11px; background: #007bff; color: white;">💬 Interactions</a>')
        
        # View portfolio if available
        portfolio_url = reverse('admin:base_clientportfolio_changelist') + f'?client_profile__id__exact={obj.pk}'
        actions.append(f'<a href="{portfolio_url}" class="button" style="margin: 1px; padding: 3px 6px; font-size: 11px; background: #28a745; color: white;">📊 Portfolio</a>')
        
        return format_html('<div style="white-space: nowrap;">{}</div>', ''.join(actions))
    quick_actions.short_description = 'Quick Actions'
    
    def mark_as_active(self, request, queryset):
        updated = queryset.update(status='active', muted_reason=None, muted_date=None, muted_by=None)
        self.message_user(request, f"✅ {updated} client profiles marked as active", level=messages.SUCCESS)
    mark_as_active.short_description = "✅ Mark selected clients as active"
    
    def mark_as_muted(self, request, queryset):
        updated = queryset.update(status='muted', muted_date=timezone.now(), muted_by=request.user)
        self.message_user(request, f"🔇 {updated} client profiles marked as muted", level=messages.WARNING)
    mark_as_muted.short_description = "🔇 Mark selected clients as muted"
    
    def assign_to_me(self, request, queryset):
        if request.user.role == 'rm':
            updated = queryset.update(mapped_rm=request.user)
            self.message_user(request, f"👤 {updated} clients assigned to you as RM", level=messages.SUCCESS)
        elif request.user.role == 'ops_exec':
            updated = queryset.update(mapped_ops_exec=request.user)
            self.message_user(request, f"⚙️ {updated} clients assigned to you for operations", level=messages.SUCCESS)
        else:
            self.message_user(request, "❌ You cannot assign clients to yourself with your current role", level=messages.ERROR)
    assign_to_me.short_description = "👤 Assign selected clients to me"
    
    def export_client_data(self, request, queryset):
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="clients_export_{timezone.now().strftime("%Y%m%d_%H%M%S")}.csv"'
        
        writer = csv.writer(response)
        writer.writerow([
            'Client ID', 'Client Name', 'Family Head', 'PAN', 'Email', 'Mobile',
            'Status', 'RM', 'Ops Executive', 'First Investment', 'Created Date'
        ])
        
        for client in queryset.select_related('mapped_rm', 'mapped_ops_exec'):
            writer.writerow([
                client.client_id,
                client.client_full_name,
                client.family_head_name or '',
                client.pan_number or '',
                client.email or '',
                client.mobile_number or '',
                client.get_status_display(),
                client.mapped_rm.get_full_name() if client.mapped_rm else '',
                client.mapped_ops_exec.get_full_name() if client.mapped_ops_exec else '',
                client.first_investment_date.strftime('%Y-%m-%d') if client.first_investment_date else '',
                client.created_at.strftime('%Y-%m-%d')
            ])
        
        return response
    export_client_data.short_description = "📄 Export selected client data to CSV"
    
    def get_queryset(self, request):
        qs = super().get_queryset(request).select_related(
            'mapped_rm', 'mapped_ops_exec', 'created_by', 'muted_by'
        ).prefetch_related('modifications')
        
        # Apply hierarchy-based filtering based on user role
        user = request.user
        if user.is_superuser or user.role in ['top_management', 'business_head', 'business_head_ops']:
            return qs
        elif user.role == 'rm_head':
            accessible_users = user.get_accessible_users() if hasattr(user, 'get_accessible_users') else []
            return qs.filter(
                Q(mapped_rm__in=accessible_users) | 
                Q(created_by=user)
            )
        elif user.role == 'rm':
            return qs.filter(mapped_rm=user)
        elif user.role in ['ops_team_lead', 'ops_exec']:
            return qs
        else:
            return qs.none()
    
    def has_change_permission(self, request, obj=None):
        if obj is None:
            return super().has_change_permission(request)
        
        user = request.user
        if user.is_superuser or user.role in ['top_management', 'business_head', 'business_head_ops']:
            return True
        elif user.role == 'rm_head':
            return user.can_access_user_data(obj.mapped_rm) if obj.mapped_rm and hasattr(user, 'can_access_user_data') else False
        elif user.role == 'rm':
            return obj.mapped_rm == user
        elif user.role in ['ops_team_lead', 'ops_exec']:
            return hasattr(user, 'can_modify_client_profile') and user.can_modify_client_profile()
        
        return False


# =============================================================================
# 🎯 LEAD MANAGEMENT - ENHANCED
# =============================================================================

class ProductDiscussionInline(admin.TabularInline):
    model = ProductDiscussion
    extra = 0
    fields = ('product', 'interest_level_badge', 'discussed_on', 'discussed_by', 'notes_preview')
    readonly_fields = ('discussed_on', 'interest_level_badge', 'notes_preview')
    autocomplete_fields = ('discussed_by',)
    verbose_name = "Product Discussion"
    verbose_name_plural = "Product Discussions"
    
    def interest_level_badge(self, obj):
        level_config = {
            'high': ('#28a745', '🔥 High'),
            'medium': ('#ffc107', '👍 Medium'),
            'low': ('#6c757d', '👎 Low')
        }
        color, label = level_config.get(obj.interest_level, ('#6c757d', obj.interest_level))
        return format_html(
            '<span style="background-color: {}; color: white; padding: 2px 6px; border-radius: 10px; font-size: 11px;">{}</span>',
            color, label
        )
    interest_level_badge.short_description = 'Interest'
    
    def notes_preview(self, obj):
        if obj.notes and len(obj.notes) > 30:
            return obj.notes[:30] + "..."
        return obj.notes or "—"
    notes_preview.short_description = 'Notes'


class LeadInteractionInline(admin.TabularInline):
    model = LeadInteraction
    extra = 0
    fields = ('interaction_type', 'interaction_date', 'notes_preview', 'next_step_preview', 'next_date', 'interacted_by')
    readonly_fields = ('interaction_date', 'notes_preview', 'next_step_preview')
    autocomplete_fields = ('interacted_by',)
    verbose_name = "Lead Interaction"
    verbose_name_plural = "Lead Interactions"
    
    def notes_preview(self, obj):
        if obj.notes and len(obj.notes) > 30:
            return obj.notes[:30] + "..."
        return obj.notes or "—"
    notes_preview.short_description = 'Notes'
    
    def next_step_preview(self, obj):
        if obj.next_step and len(obj.next_step) > 30:
            return obj.next_step[:30] + "..."
        return obj.next_step or "—"
    next_step_preview.short_description = 'Next Step'


class LeadStatusChangeInline(admin.TabularInline):
    model = LeadStatusChange
    extra = 0
    fields = ('changed_at', 'changed_by', 'status_change_summary', 'notes_preview', 'approval_status')
    readonly_fields = ('changed_at', 'status_change_summary', 'notes_preview', 'approval_status')
    autocomplete_fields = ('changed_by', 'approved_by')
    verbose_name = "Status Change"
    verbose_name_plural = "Status Changes"
    
    def status_change_summary(self, obj):
        return format_html('{} → {}', obj.old_status, obj.new_status)
    status_change_summary.short_description = 'Status Change'
    
    def notes_preview(self, obj):
        if obj.notes and len(obj.notes) > 30:
            return obj.notes[:30] + "..."
        return obj.notes or "—"
    notes_preview.short_description = 'Notes'
    
    def approval_status(self, obj):
        if obj.needs_approval:
            if obj.approved:
                return format_html('<span style="color: #28a745;">✅ Approved</span>')
            else:
                return format_html('<span style="color: #ffc107;">⏳ Pending Approval</span>')
        return format_html('<span style="color: #6c757d;">No approval needed</span>')
    approval_status.short_description = 'Approval'


# Lead Priority Filter
class LeadPriorityFilter(SimpleListFilter):
    title = 'lead priority'
    parameter_name = 'priority'

    def lookups(self, request, model_admin):
        return (
            ('hot_leads', '🔥 Hot Leads (High Probability)'),
            ('warm_leads', '🌡️ Warm Leads (Medium Probability)'),
            ('cold_leads', '❄️ Cold Leads (Low Probability)'),
            ('converted', '✅ Converted Leads'),
            ('needs_attention', '⚠️ Needs Attention'),
        )

    def queryset(self, request, queryset):
        if self.value() == 'hot_leads':
            return queryset.filter(Q(status='hot') | Q(probability__gte=70))
        elif self.value() == 'warm_leads':
            return queryset.filter(Q(status='warm') | Q(probability__range=[30, 69]))
        elif self.value() == 'cold_leads':
            return queryset.filter(Q(status='cold') | Q(probability__lt=30))
        elif self.value() == 'converted':
            return queryset.filter(converted=True)
        elif self.value() == 'needs_attention':
            from datetime import timedelta
            cutoff_date = timezone.now() - timedelta(days=7)
            return queryset.filter(
                Q(next_interaction_date__lt=timezone.now().date()) |
                Q(updated_at__lt=cutoff_date, converted=False)
            )
        return queryset


class LeadAdmin(admin.ModelAdmin, UserFriendlyAdminMixin):
    list_display = (
        'lead_info_badge', 'contact_summary', 'status_progress', 
        'assigned_personnel', 'conversion_summary', 'activity_timeline', 'quick_actions'
    )
    list_filter = (
        LeadPriorityFilter, 'status', 'source', 'converted', 
        'assigned_to', 'created_by', 'created_at', 'probability'
    )
    search_fields = (
        'lead_id', 'name', 'email', 'mobile', 
        'client_id', 'source_details'
    )
    readonly_fields = (
        'lead_id', 'client_id', 'created_at', 'updated_at', 
        'first_interaction_date', 'converted_at'
    )
    list_per_page = 25
    
    fieldsets = (
        ('🎯 Lead Information', {
            'fields': (
                'lead_id', 'name', 'email', 'mobile', 
                'status', 'probability', 'client_id'
            ),
            'description': 'Basic lead identification and current status'
        }),
        ('📍 Source Information', {
            'fields': (
                'source', 'source_details', 'reference_client'
            ),
            'description': 'How this lead was acquired'
        }),
        ('👥 Assignment & Ownership', {
            'fields': (
                'assigned_to', 'created_by'
            ),
            'description': 'Who is responsible for this lead'
        }),
        ('🔄 Reassignment Workflow', {
            'fields': (
                'needs_reassignment_approval', 'reassignment_requested_to'
            ),
            'classes': ('collapse',),
            'description': 'Reassignment approval workflow'
        }),
        ('📅 Timeline & Dates', {
            'fields': (
                'created_at', 'updated_at', 
                'first_interaction_date', 'next_interaction_date',
                'converted_at'
            ),
            'classes': ('collapse',)
        }),
        ('✅ Conversion Information', {
            'fields': (
                'converted', 'converted_by', 'client_profile'
            ),
            'description': 'Conversion status and resulting client profile'
        }),
        ('📝 Additional Notes', {
            'fields': ('notes',),
            'classes': ('collapse',)
        }),
    )
    autocomplete_fields = (
        'assigned_to', 'created_by', 'reference_client', 'converted_by', 
        'reassignment_requested_to', 'client_profile'
    )
    inlines = [LeadInteractionInline, ProductDiscussionInline, LeadStatusChangeInline]
    actions = ['mark_as_converted', 'mark_as_hot', 'assign_to_me', 'create_client_profiles', 'schedule_follow_up']
    
    def lead_info_badge(self, obj):
        status_icons = {
            'new': '🆕',
            'contacted': '📞',
            'qualified': '✅',
            'hot': '🔥',
            'warm': '🌡️',
            'cold': '❄️',
            'converted': '💰',
            'lost': '❌'
        }
        icon = status_icons.get(obj.status, '📋')
        
        probability_color = '#28a745' if obj.probability >= 70 else '#ffc107' if obj.probability >= 30 else '#dc3545'
        
        return format_html(
            '<div><strong>{} {}</strong></div>'
            '<div style="font-size: 11px; color: #6c757d;">ID: {}</div>'
            '<div style="font-size: 11px;"><span style="color: {};">{}% probability</span></div>',
            icon, obj.name, obj.lead_id, probability_color, obj.probability
        )
    lead_info_badge.short_description = 'Lead Details'
    lead_info_badge.admin_order_field = 'name'
    
    def contact_summary(self, obj):
        contact_parts = []
        if obj.email:
            contact_parts.append(f'📧 {obj.email}')
        if obj.mobile:
            contact_parts.append(f'📱 {obj.mobile}')
        
        # Add source information
        if obj.source:
            source_display = obj.get_source_display() if hasattr(obj, 'get_source_display') else obj.source
            contact_parts.append(f'📍 {source_display}')
        
        return format_html('<br>'.join(contact_parts)) if contact_parts else format_html('<em style="color: #6c757d;">No contact info</em>')
    contact_summary.short_description = 'Contact & Source'
    
    def status_progress(self, obj):
        status_config = {
            'new': ('#007bff', '🆕 New'),
            'contacted': ('#17a2b8', '📞 Contacted'),
            'qualified': ('#28a745', '✅ Qualified'),
            'hot': ('#dc3545', '🔥 Hot'),
            'warm': ('#ffc107', '🌡️ Warm'),
            'cold': ('#6c757d', '❄️ Cold'),
            'converted': ('#28a745', '💰 Converted'),
            'lost': ('#dc3545', '❌ Lost')
        }
        color, label = status_config.get(obj.status, ('#6c757d', obj.status))
        
        badge = format_html(
            '<span style="background-color: {}; color: white; padding: 3px 8px; border-radius: 12px; font-size: 11px; font-weight: bold;">{}</span>',
            color, label
        )
        
        # Add probability bar
        prob_color = '#28a745' if obj.probability >= 70 else '#ffc107' if obj.probability >= 30 else '#dc3545'
        badge += format_html(
            '<br><div style="background: #f0f0f0; border-radius: 10px; height: 8px; margin-top: 3px;">'
            '<div style="background: {}; width: {}%; height: 8px; border-radius: 10px;"></div>'
            '</div>',
            prob_color, obj.probability
        )
        
        return badge
    status_progress.short_description = 'Status & Progress'
    status_progress.admin_order_field = 'status'
    
    def assigned_personnel(self, obj):
        personnel = []
        
        if obj.assigned_to:
            assigned_url = reverse('admin:base_user_change', args=[obj.assigned_to.pk])
            assigned_name = obj.assigned_to.get_full_name() or obj.assigned_to.username
            personnel.append(f'<a href="{assigned_url}" title="Assigned to">👤 {assigned_name}</a>')
        else:
            personnel.append('<span style="color: #dc3545;">Not assigned</span>')
        
        if obj.created_by and obj.created_by != obj.assigned_to:
            creator_url = reverse('admin:base_user_change', args=[obj.created_by.pk])
            creator_name = obj.created_by.get_full_name() or obj.created_by.username
            personnel.append(f'<a href="{creator_url}" title="Created by"><small>📝 {creator_name}</small></a>')
        
        return format_html('<br>'.join(personnel))
    assigned_personnel.short_description = 'Assigned Staff'
    
    def conversion_summary(self, obj):
        if obj.converted:
            converted_icon = "✅"
            converted_text = f"Converted on {obj.converted_at.strftime('%b %d, %Y') if obj.converted_at else 'Unknown date'}"
            
            if obj.client_profile:
                client_url = reverse('admin:base_clientprofile_change', args=[obj.client_profile.pk])
                converted_text += f'<br><a href="{client_url}" style="color: #28a745;">View Client Profile</a>'
            elif obj.client_id:
                converted_text += f'<br><small>Client ID: {obj.client_id}</small>'
            
            return format_html('<span style="color: #28a745;">{} {}</span>', converted_icon, converted_text)
        else:
            days_since_creation = (timezone.now().date() - obj.created_at.date()).days
            if days_since_creation > 30:
                return format_html('<span style="color: #ffc107;">⚠️ {} days old</span>', days_since_creation)
            return format_html('<span style="color: #6c757d;">⏳ In progress</span>')
    conversion_summary.short_description = 'Conversion Status'
    
    def activity_timeline(self, obj):
        timeline = []
        
        # Creation date
        created = obj.created_at.strftime('%b %d')
        timeline.append(f'📅 Created: {created}')
        
        # Last interaction
        if obj.first_interaction_date:
            first_interaction = obj.first_interaction_date.strftime('%b %d')
            timeline.append(f'💬 First contact: {first_interaction}')
        
        # Next scheduled interaction
        if obj.next_interaction_date:
            next_date = obj.next_interaction_date
            if next_date < timezone.now().date():
                timeline.append(f'<span style="color: #dc3545;">⚠️ Overdue: {next_date.strftime("%b %d")}</span>')
            elif next_date == timezone.now().date():
                timeline.append(f'<span style="color: #ffc107;">📅 Due today</span>')
            else:
                timeline.append(f'📅 Next: {next_date.strftime("%b %d")}')
        else:
            timeline.append('<span style="color: #6c757d;">No follow-up scheduled</span>')
        
        return format_html('<br>'.join(timeline))
    activity_timeline.short_description = 'Activity Timeline'
    
    def quick_actions(self, obj):
        actions = []
        
        # Edit button
        edit_url = reverse('admin:base_lead_change', args=[obj.pk])
        actions.append(f'<a href="{edit_url}" class="button" style="margin: 1px; padding: 3px 6px; font-size: 11px;">✏️ Edit</a>')
        
        # View interactions
        interactions_url = reverse('admin:base_leadinteraction_changelist') + f'?lead__id__exact={obj.pk}'
        actions.append(f'<a href="{interactions_url}" class="button" style="margin: 1px; padding: 3px 6px; font-size: 11px; background: #007bff; color: white;">💬 History</a>')
        
        # Quick status change buttons
        if not obj.converted:
            if obj.status != 'hot':
                actions.append(f'<button onclick="changeStatus({obj.pk}, \'hot\')" class="button" style="margin: 1px; padding: 3px 6px; font-size: 11px; background: #dc3545; color: white;">🔥 Hot</button>')
            
            if obj.status not in ['converted']:
                actions.append(f'<button onclick="markConverted({obj.pk})" class="button" style="margin: 1px; padding: 3px 6px; font-size: 11px; background: #28a745; color: white;">✅ Convert</button>')
        
        return format_html('<div style="white-space: nowrap;">{}</div>', ''.join(actions))
    quick_actions.short_description = 'Quick Actions'
    
    def mark_as_converted(self, request, queryset):
        updated = queryset.filter(converted=False).update(
            converted=True, 
            status='converted', 
            converted_at=timezone.now(),
            converted_by=request.user
        )
        self.message_user(request, f"✅ {updated} leads marked as converted", level=messages.SUCCESS)
    mark_as_converted.short_description = "✅ Mark selected leads as converted"
    
    def mark_as_hot(self, request, queryset):
        updated = queryset.update(status='hot', probability=75)
        self.message_user(request, f"🔥 {updated} leads marked as hot", level=messages.SUCCESS)
    mark_as_hot.short_description = "🔥 Mark selected leads as hot"
    
    def assign_to_me(self, request, queryset):
        updated = queryset.update(assigned_to=request.user)
        self.message_user(request, f"👤 {updated} leads assigned to you", level=messages.SUCCESS)
    assign_to_me.short_description = "👤 Assign selected leads to me"
    
    def schedule_follow_up(self, request, queryset):
        tomorrow = timezone.now().date() + timedelta(days=1)
        updated = queryset.filter(next_interaction_date__isnull=True).update(next_interaction_date=tomorrow)
        self.message_user(request, f"📅 {updated} leads scheduled for follow-up tomorrow", level=messages.SUCCESS)
    schedule_follow_up.short_description = "📅 Schedule follow-up for tomorrow"
    
    def create_client_profiles(self, request, queryset):
        created_count = 0
        for lead in queryset.filter(converted=True, client_profile__isnull=True):
            try:
                client_profile = ClientProfile.objects.create(
                    client_full_name=lead.name,
                    email=lead.email or '',
                    mobile_number=lead.mobile or '',
                    mapped_rm=lead.assigned_to,
                    created_by=request.user,
                    status='active',
                    pan_number='TEMP' + str(lead.id).zfill(6),
                    date_of_birth=timezone.now().date(),
                    address_kyc='To be updated'
                )
                lead.client_profile = client_profile
                lead.save()
                created_count += 1
            except Exception as e:
                self.message_user(request, f"❌ Error creating profile for {lead.name}: {str(e)}", level=messages.ERROR)
        
        if created_count > 0:
            self.message_user(request, f"✅ {created_count} client profiles created from leads", level=messages.SUCCESS)
    create_client_profiles.short_description = "👤 Create client profiles for converted leads"

    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'assigned_to', 'created_by', 'converted_by', 'reference_client', 'client_profile'
        )


# =============================================================================
# 📋 SERVICE REQUEST MANAGEMENT - ENHANCED
# =============================================================================

class ServiceRequestDocumentInline(admin.TabularInline):
    model = ServiceRequestDocument
    extra = 0
    readonly_fields = ('uploaded_at', 'uploaded_by', 'file_size_display')
    fields = ('document_name', 'document', 'file_size_display', 'uploaded_by', 'uploaded_at')
    verbose_name = "Document"
    verbose_name_plural = "Attached Documents"
    
    def file_size_display(self, obj):
        if obj.document:
            size_mb = obj.document.size / (1024 * 1024)
            return f"{size_mb:.2f} MB"
        return '—'
    file_size_display.short_description = 'File Size'
    
    def has_change_permission(self, request, obj=None):
        return False


class ServiceRequestCommentInline(admin.TabularInline):
    model = ServiceRequestComment
    extra = 0
    readonly_fields = ('created_at', 'commented_by')
    fields = ('comment', 'is_internal_badge', 'commented_by', 'created_at')
    ordering = ('-created_at',)
    verbose_name = "Comment"
    verbose_name_plural = "Comments & Updates"
    
    def is_internal_badge(self, obj):
        if obj.is_internal:
            return format_html('<span style="color: #ffc107;">🔒 Internal</span>')
        return format_html('<span style="color: #28a745;">👥 Client Visible</span>')
    is_internal_badge.short_description = 'Visibility'
    
    def has_change_permission(self, request, obj=None):
        return False


class ServiceRequestWorkflowInline(admin.TabularInline):
    model = ServiceRequestWorkflow
    extra = 0
    readonly_fields = ('status_change_display', 'user_change_display', 'transition_date', 'remarks')
    fields = ('status_change_display', 'user_change_display', 'transition_date', 'remarks')
    ordering = ('-transition_date',)
    verbose_name = "Workflow Step"
    verbose_name_plural = "Workflow History"
    
    def status_change_display(self, obj):
        return format_html('{} → {}', obj.from_status, obj.to_status)
    status_change_display.short_description = 'Status Change'
    
    def user_change_display(self, obj):
        from_user = obj.from_user.get_full_name() if obj.from_user else 'System'
        to_user = obj.to_user.get_full_name() if obj.to_user else 'Unassigned'
        return format_html('{} → {}', from_user, to_user)
    user_change_display.short_description = 'Assignment Change'
    
    def has_add_permission(self, request, obj=None):
        return False
    
    def has_change_permission(self, request, obj=None):
        return False
    
    def has_delete_permission(self, request, obj=None):
        return False


# Custom filters for Service Requests
class ServiceRequestStatusFilter(SimpleListFilter):
    title = 'request status'
    parameter_name = 'status_group'

    def lookups(self, request, model_admin):
        return (
            ('open', '📋 Open Requests'),
            ('in_progress', '⚙️ In Progress'),
            ('waiting', '⏳ Waiting for Client'),
            ('overdue', '🚨 Overdue'),
            ('completed', '✅ Completed'),
            ('closed', '🔒 Closed'),
        )

    def queryset(self, request, queryset):
        if self.value() == 'open':
            return queryset.filter(status__in=['submitted', 'documents_requested'])
        elif self.value() == 'in_progress':
            return queryset.filter(status__in=['documents_received', 'in_progress'])
        elif self.value() == 'waiting':
            return queryset.filter(status__in=['documents_requested', 'client_verification'])
        elif self.value() == 'overdue':
            return queryset.filter(
                expected_completion_date__lt=timezone.now(),
                status__in=['submitted', 'documents_requested', 'documents_received', 'in_progress']
            )
        elif self.value() == 'completed':
            return queryset.filter(status='resolved')
        elif self.value() == 'closed':
            return queryset.filter(status='closed')
        return queryset


class ServiceRequestAdmin(admin.ModelAdmin, UserFriendlyAdminMixin):
    list_display = (
        'request_info_badge', 'client_info_link', 'request_type_badge', 
        'status_progress_bar', 'assignment_summary', 'timeline_summary', 'quick_actions'
    )
    list_filter = (
        ServiceRequestStatusFilter, 'priority', 'request_type__category', 'request_type',
        'sla_breached', 'client_approved', 'created_at', 'resolved_at'
    )
    search_fields = (
        'request_id', 'description', 'client__name', 'client__email',
        'raised_by__username', 'raised_by__first_name', 'raised_by__last_name',
        'assigned_to__username', 'assigned_to__first_name', 'assigned_to__last_name'
    )
    ordering = ('-created_at',)
    autocomplete_fields = ('client', 'raised_by', 'assigned_to', 'current_owner')
    date_hierarchy = 'created_at'
    list_per_page = 25
    
    actions = [
        'mark_as_resolved', 'mark_as_in_progress', 'mark_as_closed',
        'assign_to_me', 'export_to_csv', 'mark_sla_breached'
    ]
    
    fieldsets = (
        ('📋 Request Information', {
            'fields': ('request_id', 'client', 'request_type', 'description', 'priority'),
            'description': 'Basic service request details'
        }),
        ('👥 Assignment & Ownership', {
            'fields': ('raised_by', 'assigned_to', 'current_owner'),
            'description': 'Who raised, is assigned to, and currently owns this request'
        }),
        ('📊 Status & Progress', {
            'fields': ('status', 'resolution_summary', 'client_approved'),
            'description': 'Current status and resolution details'
        }),
        ('📅 Timeline & SLA', {
            'fields': (
                'created_at', 'submitted_at', 'documents_requested_at',
                'documents_received_at', 'resolved_at', 'closed_at',
                'expected_completion_date', 'sla_breached'
            ),
            'classes': ('collapse',),
            'description': 'Important dates and SLA tracking'
        }),
        ('📎 Documents & Requirements', {
            'fields': ('required_documents_list', 'documents_complete'),
            'classes': ('collapse',),
            'description': 'Document requirements and completion status'
        }),
        ('📝 Additional Details', {
            'fields': ('additional_details',),
            'classes': ('collapse',)
        })
    )
    
    readonly_fields = (
        'request_id', 'created_at', 'updated_at', 'submitted_at',
        'documents_requested_at', 'documents_received_at', 'resolved_at',
        'closed_at', 'client_approval_date'
    )
    
    inlines = [ServiceRequestCommentInline, ServiceRequestDocumentInline, ServiceRequestWorkflowInline]
    
    def request_info_badge(self, obj):
        priority_colors = {
            'low': '#28a745',
            'medium': '#ffc107',
            'high': '#fd7e14',
            'urgent': '#dc3545'
        }
        priority_icons = {
            'low': '🟢',
            'medium': '🟡',
            'high': '🟠',
            'urgent': '🔴'
        }
        
        color = priority_colors.get(obj.priority, '#6c757d')
        icon = priority_icons.get(obj.priority, '⚪')
        
        return format_html(
            '<div><strong>{} {}</strong></div>'
            '<div style="font-size: 11px; color: #6c757d;">ID: {}</div>'
            '<div style="font-size: 11px;"><span style="color: {};">{} {}</span></div>',
            obj.request_id[:15] + "..." if len(obj.request_id) > 15 else obj.request_id,
            obj.description[:30] + "..." if len(obj.description) > 30 else obj.description,
            obj.request_id, color, icon, obj.get_priority_display().upper()
        )
    request_info_badge.short_description = 'Request Details'
    request_info_badge.admin_order_field = 'request_id'
    
    def client_info_link(self, obj):
        url = reverse('admin:base_client_change', args=[obj.client.pk])
        return format_html(
            '<a href="{}" title="View client details"><strong>👤 {}</strong></a>',
            url, obj.client.name
        )
    client_info_link.short_description = 'Client'
    
    def request_type_badge(self, obj):
        if obj.request_type:
            category_colors = {
                'investment': '#28a745',
                'account': '#007bff',
                'documentation': '#ffc107',
                'support': '#6c757d'
            }
            color = category_colors.get(obj.request_type.category, '#6c757d') if hasattr(obj.request_type, 'category') else '#6c757d'
            
            url = reverse('admin:base_servicerequesttype_change', args=[obj.request_type.pk])
            return format_html(
                '<a href="{}" style="background-color: {}; color: white; padding: 3px 8px; border-radius: 12px; font-size: 11px; text-decoration: none;">{}</a>',
                url, color, obj.request_type.name
            )
        return format_html('<span style="color: #6c757d;">No type</span>')
    request_type_badge.short_description = 'Type'
    
    def status_progress_bar(self, obj):
        status_config = {
            'draft': ('#6c757d', 0, '📝 Draft'),
            'submitted': ('#007bff', 20, '📤 Submitted'),
            'documents_requested': ('#ffc107', 40, '📄 Docs Requested'),
            'documents_received': ('#17a2b8', 60, '📥 Docs Received'),
            'in_progress': ('#fd7e14', 80, '⚙️ In Progress'),
            'resolved': ('#28a745', 95, '✅ Resolved'),
            'client_verification': ('#6f42c1', 90, '👀 Client Review'),
            'closed': ('#343a40', 100, '🔒 Closed'),
            'on_hold': ('#dc3545', 50, '⏸️ On Hold'),
            'rejected': ('#e83e8c', 100, '❌ Rejected')
        }
        
        color, progress, label = status_config.get(obj.status, ('#6c757d', 0, obj.status))
        
        # Add SLA warning
        sla_warning = ""
        if obj.sla_breached:
            sla_warning = '<br><span style="color: #dc3545; font-size: 10px; font-weight: bold;">🚨 SLA BREACHED</span>'
        elif obj.expected_completion_date and obj.expected_completion_date < timezone.now():
            sla_warning = '<br><span style="color: #ffc107; font-size: 10px; font-weight: bold;">⚠️ OVERDUE</span>'
        
        return format_html(
            '<div style="margin-bottom: 3px;"><span style="background-color: {}; color: white; padding: 2px 6px; border-radius: 10px; font-size: 11px; font-weight: bold;">{}</span></div>'
            '<div style="background: #f0f0f0; border-radius: 10px; height: 8px;">'
            '<div style="background: {}; width: {}%; height: 8px; border-radius: 10px;"></div>'
            '</div>{}',
            color, label, color, progress, sla_warning
        )
    status_progress_bar.short_description = 'Status & Progress'
    status_progress_bar.admin_order_field = 'status'
    
    def assignment_summary(self, obj):
        assignment = []
        
        if obj.raised_by:
            raised_name = obj.raised_by.get_full_name() or obj.raised_by.username
            assignment.append(f'📝 Raised by: {raised_name}')
        
        if obj.assigned_to:
            assigned_name = obj.assigned_to.get_full_name() or obj.assigned_to.username
            assignment.append(f'👤 Assigned to: {assigned_name}')
        else:
            assignment.append('<span style="color: #dc3545;">❌ Not assigned</span>')
        
        if obj.current_owner and obj.current_owner != obj.assigned_to:
            owner_name = obj.current_owner.get_full_name() or obj.current_owner.username
            assignment.append(f'👑 Current owner: {owner_name}')
        
        return format_html('<br>'.join(assignment))
    assignment_summary.short_description = 'Assignment'
    
    def timeline_summary(self, obj):
        timeline = []
        
        created = obj.created_at.strftime('%b %d')
        timeline.append(f'📅 Created: {created}')
        
        if obj.expected_completion_date:
            expected = obj.expected_completion_date.strftime('%b %d')
            if obj.expected_completion_date < timezone.now():
                timeline.append(f'<span style="color: #dc3545;">⚠️ Expected: {expected}</span>')
            else:
                timeline.append(f'📅 Expected: {expected}')
        
        if obj.resolved_at:
            resolved = obj.resolved_at.strftime('%b %d')
            timeline.append(f'✅ Resolved: {resolved}')
        
        # Days pending calculation
        if obj.status not in ['closed', 'rejected']:
            days_pending = (timezone.now() - obj.created_at).days
            if days_pending > 7:
                timeline.append(f'<span style="color: #dc3545; font-weight: bold;">🚨 {days_pending} days old</span>')
            elif days_pending > 3:
                timeline.append(f'<span style="color: #ffc107;">{days_pending} days old</span>')
        
        return format_html('<br>'.join(timeline))
    timeline_summary.short_description = 'Timeline'
    
    def quick_actions(self, obj):
        actions = []
        
        # Edit button
        edit_url = reverse('admin:base_servicerequest_change', args=[obj.pk])
        actions.append(f'<a href="{edit_url}" class="button" style="margin: 1px; padding: 3px 6px; font-size: 11px;">✏️ Edit</a>')
        
        # Status-specific action buttons
        if obj.status == 'submitted':
            actions.append(f'<button onclick="changeStatus({obj.pk}, \'in_progress\')" class="button" style="margin: 1px; padding: 3px 6px; font-size: 11px; background: #fd7e14; color: white;">⚙️ Start</button>')
        
        if obj.status in ['in_progress', 'documents_received']:
            actions.append(f'<button onclick="changeStatus({obj.pk}, \'resolved\')" class="button" style="margin: 1px; padding: 3px 6px; font-size: 11px; background: #28a745; color: white;">✅ Resolve</button>')
        
        if obj.status == 'resolved':
            actions.append(f'<button onclick="changeStatus({obj.pk}, \'closed\')" class="button" style="margin: 1px; padding: 3px 6px; font-size: 11px; background: #343a40; color: white;">🔒 Close</button>')
        
        # Assign to me button
        if not hasattr(obj, 'assigned_to') or obj.assigned_to != getattr(obj, '_request_user', None):
            actions.append(
            f'<button onclick="assignToMe({obj.pk})" class="button" '
            'style="margin: 1px; padding: 3px 6px; font-size: 11px; background: #007bff; color: white;">👤 Assign</button>'
        )
        
        return format_html('<div style="white-space: nowrap;">{}</div>', ''.join(actions))
    quick_actions.short_description = 'Quick Actions'
    
    def mark_as_resolved(self, request, queryset):
        updated_count = 0
        for obj in queryset:
            if obj.status not in ['resolved', 'closed']:
                obj.status = 'resolved'
                obj.resolved_at = timezone.now()
                obj.save()
                
                ServiceRequestWorkflow.objects.create(
                    service_request=obj,
                    from_status=obj.status,
                    to_status='resolved',
                    from_user=request.user,
                    to_user=obj.current_owner,
                    remarks='Bulk action: Marked as resolved via admin'
                )
                updated_count += 1
        
        self.message_user(
            request, 
            f"✅ {updated_count} service request(s) marked as resolved",
            messages.SUCCESS
        )
    mark_as_resolved.short_description = "✅ Mark selected requests as resolved"
    
    def assign_to_me(self, request, queryset):
        updated = queryset.update(assigned_to=request.user, current_owner=request.user)
        self.message_user(request, f"👤 {updated} requests assigned to you", level=messages.SUCCESS)
    assign_to_me.short_description = "👤 Assign selected requests to me"
    
    def export_to_csv(self, request, queryset):
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="service_requests_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv"'
        
        writer = csv.writer(response)
        writer.writerow([
            'Request ID', 'Client', 'Request Type', 'Status', 'Priority',
            'Raised By', 'Assigned To', 'Current Owner', 'Created At',
            'Expected Completion', 'SLA Breached', 'Description'
        ])
        
        for obj in queryset:
            writer.writerow([
                obj.request_id,
                obj.client.name,
                obj.request_type.name if obj.request_type else '',
                obj.get_status_display(),
                obj.get_priority_display(),
                obj.raised_by.get_full_name() if obj.raised_by else '',
                obj.assigned_to.get_full_name() if obj.assigned_to else '',
                obj.current_owner.get_full_name() if obj.current_owner else '',
                obj.created_at.strftime('%Y-%m-%d %H:%M:%S'),
                obj.expected_completion_date.strftime('%Y-%m-%d %H:%M:%S') if obj.expected_completion_date else '',
                'Yes' if obj.sla_breached else 'No',
                obj.description[:100] + '...' if len(obj.description) > 100 else obj.description
            ])
        
        return response
    export_to_csv.short_description = "📄 Export selected requests to CSV"
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'client', 'raised_by', 'assigned_to', 'current_owner', 'request_type'
        ).prefetch_related('comments', 'documents')


# =============================================================================
# 💰 PORTFOLIO MANAGEMENT - ENHANCED
# =============================================================================

@admin.register(PortfolioUpload)
class PortfolioUploadAdmin(admin.ModelAdmin, UserFriendlyAdminMixin):
    list_display = [
        'upload_info_badge', 'uploaded_by_info', 'status_progress', 
        'processing_summary', 'file_info', 'quick_actions'
    ]
    list_filter = ['status', 'uploaded_at', 'uploaded_by']
    search_fields = ['upload_id', 'file']
    readonly_fields = [
        'upload_id', 'uploaded_at', 'processed_at', 'total_rows',
        'processed_rows', 'successful_rows', 'failed_rows',
        'processing_summary', 'error_details'
    ]
    list_per_page = 25
    
    fieldsets = (
        ('📁 Upload Information', {
            'fields': ('upload_id', 'file', 'uploaded_by', 'uploaded_at'),
            'description': 'Basic upload details and file information'
        }),
        ('📊 Processing Status', {
            'fields': ('status', 'processed_at', 'total_rows', 'processed_rows', 
                      'successful_rows', 'failed_rows'),
            'description': 'Current processing status and statistics'
        }),
        ('📝 Processing Details', {
            'fields': ('processing_log', 'processing_summary', 'error_details'),
            'classes': ('collapse',),
            'description': 'Detailed processing logs and error information'
        })
    )
    
    actions = ['process_pending_uploads', 'retry_failed_uploads', 'mark_as_pending']
    
    def upload_info_badge(self, obj):
        status_icons = {
            'pending': '⏳',
            'processing': '⚙️',
            'completed': '✅',
            'failed': '❌',
            'partial': '⚠️'
        }
        icon = status_icons.get(obj.status, '📋')
        
        return format_html(
            '<div><strong>{} {}</strong></div>'
            '<div style="font-size: 11px; color: #6c757d;">{}</div>',
            icon, obj.upload_id, obj.file.name.split('/')[-1] if obj.file else 'No file'
        )
    upload_info_badge.short_description = 'Upload Details'
    upload_info_badge.admin_order_field = 'upload_id'
    
    def uploaded_by_info(self, obj):
        if obj.uploaded_by:
            url = reverse('admin:base_user_change', args=[obj.uploaded_by.pk])
            name = obj.uploaded_by.get_full_name() or obj.uploaded_by.username
            return format_html(
                '<a href="{}" title="View user profile">👤 {}</a><br>'
                '<small style="color: #6c757d;">{}</small>',
                url, name, obj.uploaded_at.strftime('%b %d, %Y at %I:%M %p')
            )
        return format_html('<span style="color: #6c757d;">System upload</span>')
    uploaded_by_info.short_description = 'Uploaded By'
    
    def status_progress(self, obj):
        status_config = {
            'pending': ('#6c757d', 0, '⏳ Pending'),
            'processing': ('#007bff', 50, '⚙️ Processing'),
            'completed': ('#28a745', 100, '✅ Completed'),
            'failed': ('#dc3545', 100, '❌ Failed'),
            'partial': ('#ffc107', 75, '⚠️ Partial')
        }
        
        color, progress, label = status_config.get(obj.status, ('#6c757d', 0, obj.status))
        
        # Calculate actual progress if processing
        if obj.total_rows > 0:
            actual_progress = (obj.processed_rows / obj.total_rows) * 100
            if obj.status == 'processing':
                progress = actual_progress
        
        return format_html(
            '<div style="margin-bottom: 3px;"><span style="background-color: {}; color: white; padding: 2px 6px; border-radius: 10px; font-size: 11px; font-weight: bold;">{}</span></div>'
            '<div style="background: #f0f0f0; border-radius: 10px; height: 8px;">'
            '<div style="background: {}; width: {}%; height: 8px; border-radius: 10px;"></div>'
            '</div>',
            color, label, color, min(progress, 100)
        )
    status_progress.short_description = 'Status & Progress'
    status_progress.admin_order_field = 'status'
    
    def processing_summary(self, obj):
        if obj.total_rows > 0:
            success_rate = (obj.successful_rows / obj.total_rows) * 100
            
            summary = [
                f'📊 Total: {obj.total_rows:,}',
                f'<span style="color: #28a745;">✅ Success: {obj.successful_rows:,}</span>',
            ]
            
            if obj.failed_rows > 0:
                summary.append(f'<span style="color: #dc3545;">❌ Failed: {obj.failed_rows:,}</span>')
            
            summary.append(f'<span style="color: #007bff;">📈 Rate: {success_rate:.1f}%</span>')
            
            return format_html('<br>'.join(summary))
        return format_html('<span style="color: #6c757d;">No data processed</span>')
    processing_summary.short_description = 'Processing Summary'
    
    def file_info(self, obj):
        if obj.file:
            try:
                file_size = obj.file.size / (1024 * 1024)  # Convert to MB
                return format_html(
                    '<a href="{}" target="_blank" title="Download file">📁 Download</a><br>'
                    '<small style="color: #6c757d;">{:.2f} MB</small>',
                    obj.file.url, file_size
                )
            except:
                return format_html('<span style="color: #dc3545;">File not accessible</span>')
        return format_html('<span style="color: #6c757d;">No file</span>')
    file_info.short_description = 'File'
    
    def quick_actions(self, obj):
        actions = []
        
        # Edit button
        edit_url = reverse('admin:base_portfolioupload_change', args=[obj.pk])
        actions.append(f'<a href="{edit_url}" class="button" style="margin: 1px; padding: 3px 6px; font-size: 11px;">✏️ Edit</a>')
        
        # Status-specific actions
        if obj.status == 'pending':
            actions.append(f'<button onclick="processUpload({obj.pk})" class="button" style="margin: 1px; padding: 3px 6px; font-size: 11px; background: #007bff; color: white;">🚀 Process</button>')
        
        if obj.status == 'failed':
            actions.append(f'<button onclick="retryUpload({obj.pk})" class="button" style="margin: 1px; padding: 3px 6px; font-size: 11px; background: #ffc107; color: black;">🔄 Retry</button>')
        
        # View logs if available
        if hasattr(obj, 'processing_logs') and obj.processing_logs.exists():
            logs_url = reverse('admin:base_portfoliouploadlog_changelist') + f'?upload__id__exact={obj.pk}'
            log_count = obj.processing_logs.count()
            actions.append(f'<a href="{logs_url}" class="button" style="margin: 1px; padding: 3px 6px; font-size: 11px; background: #6c757d; color: white;">📋 Logs ({log_count})</a>')
        
        # View portfolios if completed
        if obj.status in ['completed', 'partial'] and hasattr(obj, 'portfolio_entries') and obj.portfolio_entries.exists():
            portfolios_url = reverse('admin:base_clientportfolio_changelist') + f'?upload_batch__id__exact={obj.pk}'
            portfolio_count = obj.portfolio_entries.count()
            actions.append(f'<a href="{portfolios_url}" class="button" style="margin: 1px; padding: 3px 6px; font-size: 11px; background: #28a745; color: white;">📊 Portfolios ({portfolio_count})</a>')
        
        return format_html('<div style="white-space: nowrap;">{}</div>', ''.join(actions))
    quick_actions.short_description = 'Quick Actions'
    
    def process_pending_uploads(self, request, queryset):
        pending_uploads = queryset.filter(status='pending')
        processed_count = 0
        
        for upload in pending_uploads:
            try:
                upload.status = 'processing'
                upload.save()
                processed_count += 1
            except Exception as e:
                self.message_user(
                    request,
                    f"❌ Error processing {upload.upload_id}: {str(e)}",
                    level=messages.ERROR
                )
        
        if processed_count > 0:
            self.message_user(
                request,
                f"✅ Started processing {processed_count} uploads",
                level=messages.SUCCESS
            )
    process_pending_uploads.short_description = "🚀 Process selected pending uploads"
    
    def retry_failed_uploads(self, request, queryset):
        failed_uploads = queryset.filter(status='failed')
        updated = failed_uploads.update(status='pending', processed_rows=0, successful_rows=0, failed_rows=0)
        
        if updated > 0:
            self.message_user(
                request,
                f"🔄 Marked {updated} failed uploads for retry",
                level=messages.SUCCESS
            )
    retry_failed_uploads.short_description = "🔄 Retry selected failed uploads"
    
    def mark_as_pending(self, request, queryset):
        updated = queryset.update(status='pending')
        self.message_user(
            request,
            f"⏳ Marked {updated} uploads as pending for reprocessing",
            level=messages.SUCCESS
        )
    mark_as_pending.short_description = "⏳ Mark as pending for reprocessing"

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('uploaded_by').prefetch_related('processing_logs')


# =============================================================================
# 📊 CLIENT INTERACTION MANAGEMENT - ENHANCED
# =============================================================================

class FollowUpFilter(SimpleListFilter):
    title = 'follow-up status'
    parameter_name = 'followup'

    def lookups(self, request, model_admin):
        return (
            ('required', '📅 Follow-up Required'),
            ('overdue', '🚨 Overdue Follow-up'),
            ('today', '⚡ Due Today'),
            ('this_week', '📅 Due This Week'),
            ('completed', '✅ No Follow-up Needed'),
        )

    def queryset(self, request, queryset):
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


class InteractionPriorityFilter(SimpleListFilter):
    title = 'priority level'
    parameter_name = 'priority_level'

    def lookups(self, request, model_admin):
        return (
            ('high_urgent', '🔥 High & Urgent'),
            ('medium', '🟡 Medium Priority'),
            ('low', '🟢 Low Priority'),
        )

    def queryset(self, request, queryset):
        if self.value() == 'high_urgent':
            return queryset.filter(priority__in=['high', 'urgent'])
        elif self.value() == 'medium':
            return queryset.filter(priority='medium')
        elif self.value() == 'low':
            return queryset.filter(priority='low')
        return queryset


class ClientInteractionInline(admin.TabularInline):
    model = ClientInteraction
    extra = 0
    max_num = 5
    readonly_fields = ('created_at', 'updated_at', 'edit_status_display')
    fields = (
        'interaction_type', 'interaction_date', 'priority', 
        'notes_preview', 'follow_up_required', 'follow_up_date',
        'created_by', 'edit_status_display'
    )
    verbose_name = "Recent Interaction"
    verbose_name_plural = "Recent Interactions (Latest 5)"
    
    def notes_preview(self, obj):
        if obj.notes and len(obj.notes) > 50:
            return obj.notes[:50] + "..."
        return obj.notes or "—"
    notes_preview.short_description = 'Notes Preview'
    
    def edit_status_display(self, obj):
        if obj.pk:
            if timezone.now() - obj.created_at <= timedelta(hours=24):
                return format_html('<span style="color: green; font-size: 10px;">✓ Editable</span>')
            else:
                return format_html('<span style="color: red; font-size: 10px;">✗ Read-only</span>')
        return "—"
    edit_status_display.short_description = "Edit Status"

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('created_by').order_by('-interaction_date')


@admin.register(ClientInteraction)
class ClientInteractionAdmin(admin.ModelAdmin, UserFriendlyAdminMixin):
    list_display = [
        'interaction_info_badge', 'client_info_display', 'interaction_summary',
        'follow_up_status_display', 'created_by_info', 'edit_timeline', 'quick_actions'
    ]
    
    list_filter = [
        'interaction_type', InteractionPriorityFilter, FollowUpFilter,
        'interaction_date', 'created_at', 'created_by'
    ]
    
    search_fields = [
        'client_profile__client_full_name', 'client_profile__pan_number',
        'client_profile__client_id', 'notes', 'interaction_type'
    ]
    
    readonly_fields = [
        'created_at', 'updated_at', 'time_since_creation_display',
        'edit_status_display', 'client_details_display', 'follow_up_status_detailed'
    ]
    
    fieldsets = (
        ('👤 Client & Interaction Type', {
            'fields': (
                'client_profile',
                'client_details_display',
                ('interaction_type', 'interaction_date'),
                ('duration_minutes', 'priority'),
            ),
            'description': 'Select client and specify interaction details'
        }),
        ('📝 Interaction Details', {
            'fields': (
                'notes',
            ),
            'description': 'Detailed notes about the interaction'
        }),
        ('📅 Follow-up Planning', {
            'fields': (
                ('follow_up_required', 'follow_up_date'),
                'follow_up_status_detailed',
            ),
            'description': 'Set follow-up requirements and dates'
        }),
        ('⚙️ System Information', {
            'fields': (
                ('created_by', 'created_at'),
                ('updated_at', 'time_since_creation_display'),
                'edit_status_display',
            ),
            'classes': ('collapse',),
            'description': 'System-generated tracking information'
        }),
    )
    
    date_hierarchy = 'interaction_date'
    ordering = ['-interaction_date', '-created_at']
    actions = ['mark_follow_up_required', 'mark_follow_up_completed', 'change_priority_to_high', 'export_interactions']
    list_per_page = 25
    
    def interaction_info_badge(self, obj):
        type_icons = {
            'call': '📞',
            'email': '📧',
            'meeting': '🤝',
            'video_call': '📹',
            'sms': '📱',
            'visit': '🏢',
            'other': '💬'
        }
        icon = type_icons.get(obj.interaction_type, '💬')
        
        priority_colors = {
            'low': '#28a745',
            'medium': '#ffc107',
            'high': '#fd7e14',
            'urgent': '#dc3545'
        }
        priority_color = priority_colors.get(obj.priority, '#6c757d')
        
        return format_html(
            '<div><strong>{} {}</strong></div>'
            '<div style="font-size: 11px; color: #6c757d;">{}</div>'
            '<div style="font-size: 11px;"><span style="color: {};">● {}</span></div>',
            icon, obj.get_interaction_type_display() if hasattr(obj, 'get_interaction_type_display') else obj.interaction_type,
            obj.interaction_date.strftime('%b %d, %Y at %I:%M %p'),
            priority_color, obj.get_priority_display() if hasattr(obj, 'get_priority_display') else obj.priority
        )
    interaction_info_badge.short_description = 'Interaction'
    interaction_info_badge.admin_order_field = 'interaction_date'
    
    def client_info_display(self, obj):
        if obj.client_profile:
            url = reverse('admin:base_clientprofile_change', args=[obj.client_profile.pk])
            return format_html(
                '<a href="{}" title="View client profile"><strong>👤 {}</strong></a><br>'
                '<small style="color: #6c757d;">ID: {} | PAN: {}</small>',
                url,
                obj.client_profile.client_full_name,
                obj.client_profile.client_id,
                obj.client_profile.pan_number or 'Not set'
            )
        return format_html('<span style="color: #dc3545;">No client profile</span>')
    client_info_display.short_description = 'Client'
    
    def interaction_summary(self, obj):
        summary = []
        
        # Duration if available
        if obj.duration_minutes:
            summary.append(f'⏱️ {obj.duration_minutes} min')
        
        # Notes preview
        if obj.notes:
            notes_preview = obj.notes[:50] + "..." if len(obj.notes) > 50 else obj.notes
            summary.append(f'📝 {notes_preview}')
        else:
            summary.append('<em style="color: #6c757d;">No notes</em>')
        
        return format_html('<br>'.join(summary))
    interaction_summary.short_description = 'Summary'
    
    def follow_up_status_display(self, obj):
        if not obj.follow_up_required:
            return format_html('<span style="color: #28a745;">✅ No follow-up needed</span>')
        
        if not obj.follow_up_date:
            return format_html('<span style="color: #ffc107;">📅 Follow-up required<br><small>(No date set)</small></span>')
        
        today = timezone.now().date()
        days_diff = (obj.follow_up_date - today).days
        
        if days_diff < 0:
            overdue_days = abs(days_diff)
            return format_html(
                '<span style="color: #dc3545; font-weight: bold;">🚨 OVERDUE<br><small>{} days ago</small></span>',
                overdue_days
            )
        elif days_diff == 0:
            return format_html('<span style="color: #ffc107; font-weight: bold;">⚡ DUE TODAY</span>')
        elif days_diff <= 7:
            return format_html(
                '<span style="color: #007bff;">📅 Due in {} days<br><small>{}</small></span>',
                days_diff, obj.follow_up_date.strftime('%b %d')
            )
        else:
            return format_html(
                '<span style="color: #6c757d;">📅 Due {}<br><small>({} days)</small></span>',
                obj.follow_up_date.strftime('%b %d'), days_diff
            )
    follow_up_status_display.short_description = 'Follow-up Status'
    
    def created_by_info(self, obj):
        if obj.created_by:
            url = reverse('admin:base_user_change', args=[obj.created_by.pk])
            name = obj.created_by.get_full_name() or obj.created_by.username
            return format_html(
                '<a href="{}" title="View user profile">👤 {}</a>',
                url, name
            )
        return format_html('<span style="color: #6c757d;">System</span>')
    created_by_info.short_description = 'Created By'
    
    def edit_timeline(self, obj):
        if obj.pk:
            time_diff = timezone.now() - obj.created_at
            hours_passed = time_diff.total_seconds() / 3600
            
            if hours_passed <= 24:
                remaining_hours = round(24 - hours_passed, 1)
                edit_status = format_html(
                    '<span style="color: #28a745; font-weight: bold;">✅ Editable</span><br>'
                    '<small style="color: #6c757d;">{} hrs left</small>',
                    remaining_hours
                )
            else:
                expired_hours = round(hours_passed - 24, 1)
                edit_status = format_html(
                    '<span style="color: #dc3545; font-weight: bold;">🔒 Read-only</span><br>'
                    '<small style="color: #6c757d;">Expired {} hrs ago</small>',
                    expired_hours
                )
            
            created_time = obj.created_at.strftime('%b %d at %I:%M %p')
            return format_html(
                '{}<br><small style="color: #6c757d;">Created: {}</small>',
                edit_status, created_time
            )
        return "—"
    edit_timeline.short_description = 'Edit Status & Timeline'
    
    def quick_actions(self, obj):
        actions = []
        
        # Edit button (only if editable)
        time_diff = timezone.now() - obj.created_at
        if time_diff <= timedelta(hours=24):
            edit_url = reverse('admin:base_clientinteraction_change', args=[obj.pk])
            actions.append(f'<a href="{edit_url}" class="button" style="margin: 1px; padding: 3px 6px; font-size: 11px; background: #007bff; color: white;">✏️ Edit</a>')
        
        # Follow-up actions
        if obj.follow_up_required:
            actions.append(f'<button onclick="markFollowUpComplete({obj.pk})" class="button" style="margin: 1px; padding: 3px 6px; font-size: 11px; background: #28a745; color: white;">✅ Complete</button>')
        else:
            actions.append(f'<button onclick="setFollowUpRequired({obj.pk})" class="button" style="margin: 1px; padding: 3px 6px; font-size: 11px; background: #ffc107; color: black;">📅 Set F/U</button>')
        
        # View client profile
        if obj.client_profile:
            client_url = reverse('admin:base_clientprofile_change', args=[obj.client_profile.pk])
            actions.append(f'<a href="{client_url}" class="button" style="margin: 1px; padding: 3px 6px; font-size: 11px; background: #6c757d; color: white;">👤 Client</a>')
        
        return format_html('<div style="white-space: nowrap;">{}</div>', ''.join(actions))
    quick_actions.short_description = 'Quick Actions'
    
    # Helper readonly field methods
    def client_details_display(self, obj):
        if obj.client_profile:
            client = obj.client_profile
            url = reverse('admin:base_clientprofile_change', args=[client.pk])
            
            return format_html(
                '<div style="background: #f8f9fa; padding: 10px; border-radius: 5px; border-left: 4px solid #007bff;">'
                '<a href="{}" style="text-decoration: none; color: #007bff;"><strong>👤 {}</strong></a><br>'
                '<small>📋 ID: {} | 🆔 PAN: {}<br>'
                '📧 Email: {} | 📱 Mobile: {}<br>'
                '👤 RM: {} | ⚙️ Ops: {}</small>'
                '</div>',
                url,
                client.client_full_name,
                client.client_id,
                client.pan_number or 'Not set',
                client.email or 'Not set',
                client.mobile_number or 'Not set',
                client.mapped_rm.get_full_name() if client.mapped_rm else 'Not assigned',
                client.mapped_ops_exec.get_full_name() if client.mapped_ops_exec else 'Not assigned'
            )
        return format_html('<span style="color: #dc3545;">No client profile selected</span>')
    client_details_display.short_description = 'Client Information'
    
    def time_since_creation_display(self, obj):
        if obj.pk:
            return obj.get_time_since_creation() if hasattr(obj, 'get_time_since_creation') else str(timezone.now() - obj.created_at)
        return "—"
    time_since_creation_display.short_description = 'Time Since Creation'
    
    def edit_status_display(self, obj):
        if obj.pk:
            time_diff = timezone.now() - obj.created_at
            hours_passed = time_diff.total_seconds() / 3600
            
            if hours_passed <= 24:
                remaining_hours = round(24 - hours_passed, 1)
                return format_html(
                    '<div style="background: #d4edda; padding: 8px; border-radius: 5px; border-left: 4px solid #28a745;">'
                    '<strong style="color: #155724;">✅ Editable</strong><br>'
                    '<small>Edit window expires in {} hours</small>'
                    '</div>',
                    remaining_hours
                )
            else:
                expired_hours = round(hours_passed - 24, 1)
                return format_html(
                    '<div style="background: #f8d7da; padding: 8px; border-radius: 5px; border-left: 4px solid #dc3545;">'
                    '<strong style="color: #721c24;">🔒 Read-only</strong><br>'
                    '<small>Edit window expired {} hours ago</small>'
                    '</div>',
                    expired_hours
                )
        return "—"
    edit_status_display.short_description = 'Edit Window Status'
    
    def follow_up_status_detailed(self, obj):
        if not obj.follow_up_required:
            return format_html(
                '<div style="background: #d4edda; padding: 8px; border-radius: 5px; border-left: 4px solid #28a745;">'
                '<strong style="color: #155724;">✅ No follow-up required</strong><br>'
                '<small>This interaction is complete</small>'
                '</div>'
            )
        
        if not obj.follow_up_date:
            return format_html(
                '<div style="background: #fff3cd; padding: 8px; border-radius: 5px; border-left: 4px solid #ffc107;">'
                '<strong style="color: #856404;">📅 Follow-up required</strong><br>'
                '<small style="color: #dc3545;">⚠️ No date set - please set a follow-up date</small>'
                '</div>'
            )
        
        today = timezone.now().date()
        days_diff = (obj.follow_up_date - today).days
        
        if days_diff < 0:
            overdue_days = abs(days_diff)
            return format_html(
                '<div style="background: #f8d7da; padding: 8px; border-radius: 5px; border-left: 4px solid #dc3545;">'
                '<strong style="color: #721c24;">🚨 OVERDUE</strong><br>'
                '<small>Follow-up was due {} days ago on {}</small>'
                '</div>',
                overdue_days, obj.follow_up_date.strftime('%B %d, %Y')
            )
        elif days_diff == 0:
            return format_html(
                '<div style="background: #fff3cd; padding: 8px; border-radius: 5px; border-left: 4px solid #ffc107;">'
                '<strong style="color: #856404;">⚡ DUE TODAY</strong><br>'
                '<small>Follow-up scheduled for today</small>'
                '</div>'
            )
        elif days_diff <= 7:
            return format_html(
                '<div style="background: #cce5ff; padding: 8px; border-radius: 5px; border-left: 4px solid #007bff;">'
                '<strong style="color: #003d80;">📅 Due soon</strong><br>'
                '<small>Follow-up scheduled for {} ({} days from now)</small>'
                '</div>',
                obj.follow_up_date.strftime('%B %d, %Y'), days_diff
            )
        else:
            return format_html(
                '<div style="background: #e2e3e5; padding: 8px; border-radius: 5px; border-left: 4px solid #6c757d;">'
                '<strong style="color: #495057;">📅 Scheduled</strong><br>'
                '<small>Follow-up scheduled for {} ({} days from now)</small>'
                '</div>',
                obj.follow_up_date.strftime('%B %d, %Y'), days_diff
            )
    follow_up_status_detailed.short_description = 'Follow-up Status Details'
    
    # Actions
    @admin.action(description='✅ Mark selected interactions as follow-up completed')
    def mark_follow_up_completed(self, request, queryset):
        updated = queryset.update(follow_up_required=False, follow_up_date=None)
        self.message_user(
            request, 
            f'✅ {updated} interactions marked as follow-up completed.',
            level=messages.SUCCESS
        )
    
    @admin.action(description='🔥 Change priority to High for selected interactions')
    def change_priority_to_high(self, request, queryset):
        updated = queryset.update(priority='high')
        self.message_user(
            request, 
            f'🔥 {updated} interactions priority changed to High.',
            level=messages.SUCCESS
        )
    
    @admin.action(description='📄 Export selected interactions to CSV')
    def export_interactions(self, request, queryset):
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="client_interactions_{timezone.now().strftime("%Y%m%d_%H%M%S")}.csv"'
        
        writer = csv.writer(response)
        writer.writerow([
            'Client Name', 'Client ID', 'PAN', 'Interaction Type', 'Date', 
            'Duration (mins)', 'Priority', 'Notes', 'Follow-up Required', 
            'Follow-up Date', 'Created By', 'Created At'
        ])
        
        for interaction in queryset.select_related('client_profile', 'created_by'):
            writer.writerow([
                interaction.client_profile.client_full_name if interaction.client_profile else '',
                interaction.client_profile.client_id if interaction.client_profile else '',
                interaction.client_profile.pan_number if interaction.client_profile else '',
                interaction.get_interaction_type_display() if hasattr(interaction, 'get_interaction_type_display') else interaction.interaction_type,
                interaction.interaction_date.strftime('%Y-%m-%d %H:%M'),
                interaction.duration_minutes or '',
                interaction.get_priority_display() if hasattr(interaction, 'get_priority_display') else interaction.priority,
                interaction.notes,
                'Yes' if interaction.follow_up_required else 'No',
                interaction.follow_up_date.strftime('%Y-%m-%d') if interaction.follow_up_date else '',
                interaction.created_by.get_full_name() if interaction.created_by else '',
                interaction.created_at.strftime('%Y-%m-%d %H:%M')
            ])
        
        return response
    
    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)
    
    def has_change_permission(self, request, obj=None):
        if obj is None:
            return super().has_change_permission(request)
        
        user = request.user
        
        # Superuser and top management can always edit
        if user.is_superuser or user.role in ['top_management', 'business_head', 'business_head_ops']:
            return True
        
        # Check if within 24-hour edit window for creator
        if obj.created_by == user:
            return (timezone.now() - obj.created_at) <= timedelta(hours=24)
        
        # RM Head can edit interactions for their team members (within time limit)
        if user.role == 'rm_head':
            can_access = hasattr(user, 'can_access_user_data') and user.can_access_user_data(obj.client_profile.mapped_rm) if obj.client_profile and obj.client_profile.mapped_rm else False
            if can_access and obj.created_by == user:
                return (timezone.now() - obj.created_at) <= timedelta(hours=24)
        
        # RM can edit their own client interactions (within time limit)
        if user.role == 'rm' and obj.client_profile and obj.client_profile.mapped_rm == user:
            if obj.created_by == user:
                return (timezone.now() - obj.created_at) <= timedelta(hours=24)
        
        return False
    
    def has_delete_permission(self, request, obj=None):
        return self.has_change_permission(request, obj)
    
    def get_queryset(self, request):
        qs = super().get_queryset(request).select_related('client_profile', 'created_by')
        
        user = request.user
        if user.is_superuser or user.role in ['top_management', 'business_head', 'business_head_ops']:
            return qs
        elif user.role == 'rm_head':
            accessible_users = user.get_accessible_users() if hasattr(user, 'get_accessible_users') else []
            return qs.filter(client_profile__mapped_rm__in=accessible_users)
        elif user.role == 'rm':
            return qs.filter(client_profile__mapped_rm=user)
        elif user.role in ['ops_team_lead', 'ops_exec']:
            return qs  # Can view all interactions for operational purposes
        else:
            return qs.filter(created_by=user)  # Can only see own interactions


# =============================================================================
# 📊 BUSINESS ANALYTICS - ENHANCED
# =============================================================================

class BusinessTrackerAdmin(admin.ModelAdmin, UserFriendlyAdminMixin):
    list_display = (
        'period_badge', 'user_info_display', 'team_info_display', 
        'financial_summary', 'portfolio_stats', 'performance_indicator'
    )
    list_filter = ('month', 'user__role', 'team')
    search_fields = ('user__username', 'user__first_name', 'user__last_name', 'team__name')
    ordering = ('-month', 'user__username')
    autocomplete_fields = ('user', 'team')
    date_hierarchy = 'month'
    list_per_page = 50
    
    def period_badge(self, obj):
        month_name = obj.month.strftime('%B %Y')
        is_current_month = obj.month.month == timezone.now().month and obj.month.year == timezone.now().year
        
        if is_current_month:
            return format_html(
                '<strong style="color: #007bff;">📅 {}</strong><br>'
                '<small style="color: #28a745; font-weight: bold;">Current Month</small>',
                month_name
            )
        else:
            return format_html(
                '<strong>📅 {}</strong>',
                month_name
            )
    period_badge.short_description = 'Period'
    period_badge.admin_order_field = 'month'
    
    def user_info_display(self, obj):
        if obj.user:
            url = reverse('admin:base_user_change', args=[obj.user.pk])
            full_name = obj.user.get_full_name() or obj.user.username
            role_display = obj.user.get_role_display() if hasattr(obj.user, 'get_role_display') else obj.user.role
            
            role_colors = {
                'rm': '#28a745',
                'rm_head': '#007bff',
                'ops_exec': '#6c757d',
                'ops_team_lead': '#17a2b8'
            }
            role_color = role_colors.get(obj.user.role, '#6c757d')
            
            return format_html(
                '<a href="{}" title="View user profile"><strong>👤 {}</strong></a><br>'
                '<span style="background-color: {}; color: white; padding: 2px 6px; border-radius: 10px; font-size: 10px;">{}</span>',
                url, full_name, role_color, role_display.upper()
            )
        return format_html('<strong style="color: #6c757d;">📊 System Wide</strong>')
    user_info_display.short_description = 'User'
    
    def team_info_display(self, obj):
        if obj.team:
            url = reverse('admin:base_team_change', args=[obj.team.pk])
            return format_html(
                '<a href="{}" title="View team details">👥 {}</a>',
                url, obj.team.name
            )
        return format_html('<span style="color: #6c757d;">No team</span>')
    team_info_display.short_description = 'Team'
    
    def financial_summary(self, obj):
        aum_formatted = f"₹{obj.total_aum:,.0f}"
        sip_formatted = f"₹{obj.total_sip:,.0f}"
        
        # Determine AUM display format
        if obj.total_aum >= 10000000:  # 1 crore
            aum_display = f"₹{obj.total_aum/10000000:.1f}Cr"
        elif obj.total_aum >= 100000:  # 1 lakh
            aum_display = f"₹{obj.total_aum/100000:.1f}L"
        else:
            aum_display = f"₹{obj.total_aum:,.0f}"
        
        # Color coding based on AUM
        aum_color = '#28a745' if obj.total_aum >= 10000000 else '#ffc107' if obj.total_aum >= 1000000 else '#6c757d'
        
        return format_html(
            '<div><strong style="color: {};">💰 AUM: {}</strong></div>'
            '<div style="font-size: 11px; color: #6c757d;">💳 SIP: {}</div>',
            aum_color, aum_display, sip_formatted
        )
    financial_summary.short_description = 'Financial Summary'
    
    def portfolio_stats(self, obj):
        stats = []
        
        # Demat accounts
        demat_color = '#28a745' if obj.total_demat >= 50 else '#ffc107' if obj.total_demat >= 10 else '#6c757d'
        stats.append(f'<span style="color: {demat_color};">🏦 {obj.total_demat} accounts</span>')
        
        # Calculate averages if user-specific
        if obj.user and obj.total_demat > 0:
            avg_aum = obj.total_aum / obj.total_demat
            avg_sip = obj.total_sip / obj.total_demat
            
            if avg_aum >= 1000000:  # 10 lakh average
                avg_aum_display = f"₹{avg_aum/100000:.1f}L"
            else:
                avg_aum_display = f"₹{avg_aum:,.0f}"
            
            stats.append(f'📊 Avg AUM: {avg_aum_display}')
            stats.append(f'📈 Avg SIP: ₹{avg_sip:,.0f}')
        
        return format_html('<br>'.join(stats))
    portfolio_stats.short_description = 'Portfolio Stats'
    
    def performance_indicator(self, obj):
        indicators = []
        
        # Performance rating based on AUM
        if obj.total_aum >= 50000000:  # 5 crores
            indicators.append('<span style="color: #28a745; font-weight: bold;">🌟 Excellent</span>')
        elif obj.total_aum >= 20000000:  # 2 crores
            indicators.append('<span style="color: #28a745;">⭐ Very Good</span>')
        elif obj.total_aum >= 10000000:  # 1 crore
            indicators.append('<span style="color: #ffc107;">👍 Good</span>')
        elif obj.total_aum >= 5000000:  # 50 lakhs
            indicators.append('<span style="color: #fd7e14;">📈 Fair</span>')
        else:
            indicators.append('<span style="color: #6c757d;">📊 Developing</span>')
        
        # Growth indicators (if previous month data available)
        try:
            previous_month = obj.month.replace(day=1) - timedelta(days=1)
            previous_record = BusinessTracker.objects.filter(
                user=obj.user,
                team=obj.team,
                month__year=previous_month.year,
                month__month=previous_month.month
            ).first()
            
            if previous_record:
                aum_growth = ((obj.total_aum - previous_record.total_aum) / previous_record.total_aum) * 100 if previous_record.total_aum > 0 else 0
                if aum_growth > 10:
                    indicators.append('<span style="color: #28a745;">📈 +{:.1f}%</span>'.format(aum_growth))
                elif aum_growth > 0:
                    indicators.append('<span style="color: #ffc107;">📈 +{:.1f}%</span>'.format(aum_growth))
                elif aum_growth < -10:
                    indicators.append('<span style="color: #dc3545;">📉 {:.1f}%</span>'.format(aum_growth))
                else:
                    indicators.append('<span style="color: #6c757d;">➡️ {:.1f}%</span>'.format(aum_growth))
        except:
            pass
        
        return format_html('<br>'.join(indicators))
    performance_indicator.short_description = 'Performance'

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('user', 'team')


# =============================================================================
# 📋 ADMIN SITE CUSTOMIZATION
# =============================================================================

# Custom Group Admin for Team Management
class CustomGroupAdmin(admin.ModelAdmin, UserFriendlyAdminMixin):
    list_display = ('group_name_badge', 'member_summary', 'rm_head_info', 'permissions_summary')
    search_fields = ('name',)
    filter_horizontal = ('permissions',)
    list_per_page = 25
    
    def group_name_badge(self, obj):
        return format_html(
            '<strong>👥 {}</strong>',
            obj.name
        )
    group_name_badge.short_description = 'Group Name'
    group_name_badge.admin_order_field = 'name'
    
    def member_summary(self, obj):
        total_members = obj.user_set.count()
        rm_members = obj.user_set.filter(role='rm').count()
        
        if total_members > 0:
            return format_html(
                '<span style="color: #007bff; font-weight: bold;">{} total members</span><br>'
                '<small style="color: #6c757d;">{} RMs</small>',
                total_members, rm_members
            )
        return format_html('<span style="color: #6c757d;">No members</span>')
    member_summary.short_description = 'Members'
    
    def rm_head_info(self, obj):
        try:
            rm_head = User.objects.filter(
                role='rm_head',
                managed_groups=obj
            ).first()
            
            if rm_head:
                url = reverse('admin:base_user_change', args=[rm_head.pk])
                name = rm_head.get_full_name() or rm_head.username
                return format_html(
                    '<a href="{}" title="View team head profile">👑 {}</a>',
                    url, name
                )
            return format_html('<span style="color: #dc3545;">No head assigned</span>')
        except:
            return format_html('<span style="color: #6c757d;">—</span>')
    rm_head_info.short_description = 'Team Head'
    
    def permissions_summary(self, obj):
        perm_count = obj.permissions.count()
        if perm_count > 0:
            return format_html(
                '<span style="color: #28a745;">🔐 {} permissions</span>',
                perm_count
            )
        return format_html('<span style="color: #6c757d;">No special permissions</span>')
    permissions_summary.short_description = 'Permissions'

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related('user_set', 'permissions')


# =============================================================================
# 🎨 ADMIN SITE ENHANCEMENTS
# =============================================================================

class AdminSiteEnhanced(admin.AdminSite):
    """Enhanced admin site with better user experience"""
    
    site_header = "🏢 CRM Administration Dashboard"
    site_title = "CRM Admin"
    index_title = "Welcome to your CRM Control Center"
    
    def index(self, request, extra_context=None):
        """Enhanced admin index with dashboard-like features"""
        extra_context = extra_context or {}
        
        # Add user-specific context
        user = request.user
        user_context = {
            'user_role': user.role if hasattr(user, 'role') else 'Unknown',
            'user_display_name': user.get_full_name() or user.username,
            'is_manager': user.role in ['rm_head', 'ops_team_lead', 'business_head'] if hasattr(user, 'role') else False,
        }
        
        # Add quick stats
        try:
            stats = {}
            
            if user.role == 'rm':
                stats['my_clients'] = ClientProfile.objects.filter(mapped_rm=user).count()
                stats['pending_interactions'] = ClientInteraction.objects.filter(
                    client_profile__mapped_rm=user,
                    follow_up_required=True,
                    follow_up_date__lte=timezone.now().date()
                ).count()
            elif user.role in ['rm_head', 'business_head']:
                if hasattr(user, 'get_accessible_users'):
                    accessible_users = user.get_accessible_users()
                    stats['team_clients'] = ClientProfile.objects.filter(mapped_rm__in=accessible_users).count()
                    stats['team_leads'] = Lead.objects.filter(assigned_to__in=accessible_users, converted=False).count()
            
            # Common stats for all users
            stats['total_service_requests'] = ServiceRequest.objects.filter(
                Q(assigned_to=user) | Q(current_owner=user)
            ).exclude(status__in=['closed', 'rejected']).count()
            
            stats['my_tasks'] = Task.objects.filter(assigned_to=user, completed=False).count() if hasattr(request, 'user') else 0
            
            user_context['quick_stats'] = stats
            
        except Exception as e:
            user_context['quick_stats'] = {}
        
        extra_context.update(user_context)
        
        return super().index(request, extra_context)

class ClientProfileModificationAdmin(admin.ModelAdmin):
    list_display = (
        'client_link', 'requested_by_link', 'status', 'reason',
        'requested_at', 'approved_by_link', 'approved_at', 'requires_top_management'
    )
    list_filter = ('status', 'requested_at', 'approved_at', 'requires_top_management')
    search_fields = ('client__client_full_name', 'reason', 'requested_by__username')
    readonly_fields = ('requested_at', 'approved_at', 'modification_data')
    autocomplete_fields = ('client', 'requested_by', 'approved_by')
    date_hierarchy = 'requested_at'
    
    fieldsets = (
        ('Request Information', {
            'fields': ('client', 'requested_by', 'reason', 'requested_at')
        }),
        ('Modification Details', {
            'fields': ('modification_data', 'requires_top_management')
        }),
        ('Approval Information', {
            'fields': ('status', 'approved_by', 'approved_at')
        }),
    )
    
    actions = ['approve_selected', 'reject_selected']
    
    def client_link(self, obj):
        url = reverse('admin:base_clientprofile_change', args=[obj.client.pk])
        return format_html('<a href="{}">{}</a>', url, obj.client.client_full_name)
    client_link.short_description = 'Client'
    
    def requested_by_link(self, obj):
        url = reverse('admin:base_user_change', args=[obj.requested_by.pk])
        return format_html('<a href="{}">{}</a>', url, obj.requested_by.username)
    requested_by_link.short_description = 'Requested By'
    
    def approved_by_link(self, obj):
        if obj.approved_by:
            url = reverse('admin:base_user_change', args=[obj.approved_by.pk])
            return format_html('<a href="{}">{}</a>', url, obj.approved_by.username)
        return '-'
    approved_by_link.short_description = 'Approved By'
    
    def approve_selected(self, request, queryset):
        approved_count = 0
        for modification in queryset.filter(status='pending'):
            if modification.approve(request.user):
                approved_count += 1
        
        self.message_user(request, f"{approved_count} modification requests approved")
    approve_selected.short_description = "Approve selected modification requests"
    
    def reject_selected(self, request, queryset):
        rejected_count = 0
        for modification in queryset.filter(status='pending'):
            if modification.reject(request.user):
                rejected_count += 1
        
        self.message_user(request, f"{rejected_count} modification requests rejected")
    reject_selected.short_description = "Reject selected modification requests"
    
    def get_queryset(self, request):
        qs = super().get_queryset(request).select_related(
            'client', 'requested_by', 'approved_by'
        )
        
        # Filter based on user permissions
        user = request.user
        if user.is_superuser or user.role in ['top_management', 'business_head', 'business_head_ops']:
            return qs
        elif user.role == 'rm_head':
            accessible_users = user.get_accessible_users()
            return qs.filter(
                Q(client__mapped_rm__in=accessible_users) |
                Q(requested_by=user)
            )
        elif user.role == 'rm':
            return qs.filter(
                Q(client__mapped_rm=user) |
                Q(requested_by=user)
            )
        else:
            return qs.none()
    
    def has_change_permission(self, request, obj=None):
        if obj is None:
            return super().has_change_permission(request)
        
        user = request.user
        return user.is_superuser or user.role in ['top_management', 'business_head', 'business_head_ops']

class LeadInteractionAdmin(admin.ModelAdmin):
    list_display = ('lead_link', 'interaction_type', 'interaction_date', 'interacted_by', 'next_date')
    list_filter = ('interaction_type', 'interaction_date', 'next_date')
    search_fields = ('lead__name', 'lead__lead_id', 'notes')
    autocomplete_fields = ('lead', 'interacted_by')
    date_hierarchy = 'interaction_date'
    
    def lead_link(self, obj):
        url = reverse('admin:base_lead_change', args=[obj.lead.pk])
        return format_html('<a href="{}">{} - {}</a>', url, obj.lead.lead_id, obj.lead.name)
    lead_link.short_description = 'Lead'

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('lead', 'interacted_by')


class ProductDiscussionAdmin(admin.ModelAdmin):
    list_display = ('lead_link', 'product', 'interest_level', 'discussed_on', 'discussed_by')
    list_filter = ('product', 'interest_level', 'discussed_on')
    search_fields = ('lead__name', 'lead__lead_id', 'notes')
    autocomplete_fields = ('lead', 'discussed_by')
    date_hierarchy = 'discussed_on'
    
    def lead_link(self, obj):
        url = reverse('admin:base_lead_change', args=[obj.lead.pk])
        return format_html('<a href="{}">{} - {}</a>', url, obj.lead.lead_id, obj.lead.name)
    lead_link.short_description = 'Lead'

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('lead', 'discussed_by')


class LeadStatusChangeAdmin(admin.ModelAdmin):
    list_display = (
        'lead_link', 'changed_at', 'changed_by', 'old_status', 
        'new_status', 'needs_approval', 'approved', 'approved_by'
    )
    list_filter = ('changed_at', 'new_status', 'needs_approval', 'approved')
    search_fields = ('lead__name', 'lead__lead_id', 'notes')
    autocomplete_fields = ('lead', 'changed_by', 'approved_by', 'approval_by')
    date_hierarchy = 'changed_at'
    
    def lead_link(self, obj):
        url = reverse('admin:base_lead_change', args=[obj.lead.pk])
        return format_html('<a href="{}">{} - {}</a>', url, obj.lead.lead_id, obj.lead.name)
    lead_link.short_description = 'Lead'

    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'lead', 'changed_by', 'approved_by', 'approval_by'
        )
        

class ServiceRequestInline(admin.TabularInline):
    model = ServiceRequest
    extra = 0
    fields = ('description', 'status', 'priority', 'assigned_to')
    
class ClientAdmin(admin.ModelAdmin):
    list_display = (
        'name', 'user_link', 'aum_display', 'sip_amount_display', 
        'demat_count', 'lead_link', 'client_profile_link', 'created_at'
    )
    list_filter = ('created_at', 'user__role', 'demat_count')
    search_fields = ('name', 'contact_info', 'user__username', 'lead__lead_id')
    ordering = ('-aum', '-created_at')
    autocomplete_fields = ('user', 'lead', 'client_profile', 'created_by')
    inlines = [ServiceRequestInline]
    
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
            return format_html('<a href="{}">{}</a>', url, obj.lead.lead_id)
        return '-'
    lead_link.short_description = 'Original Lead'
    
    def client_profile_link(self, obj):
        if obj.client_profile:
            url = reverse('admin:base_clientprofile_change', args=[obj.client_profile.pk])
            return format_html('<a href="{}">View New Profile</a>', url)
        return format_html('<em>No new profile</em>')
    client_profile_link.short_description = 'New Client Profile'

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('user', 'lead', 'client_profile', 'created_by')


# Task and Service Management Admin Classes
class TaskAdmin(admin.ModelAdmin):
    list_display = (
        'title', 'assigned_to_link', 'assigned_by_link', 
        'priority', 'due_date', 'completed', 'created_at'
    )
    list_filter = ('priority', 'completed', 'created_at', 'due_date')
    search_fields = ('title', 'description', 'assigned_to__username')
    ordering = ('-created_at',)
    autocomplete_fields = ('assigned_to', 'assigned_by')
    date_hierarchy = 'created_at'
    actions = ['mark_as_completed']
    
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
    
    def mark_as_completed(self, request, queryset):
        updated = queryset.update(completed=True, completed_at=timezone.now())
        self.message_user(request, f"{updated} tasks marked as completed")
    mark_as_completed.short_description = "Mark selected tasks as completed"

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('assigned_to', 'assigned_by')


class ReminderAdmin(admin.ModelAdmin):
    list_display = ('user_link', 'message_preview', 'remind_at', 'is_done', 'created_at')
    list_filter = ('is_done', 'remind_at', 'created_at')
    search_fields = ('message', 'user__username')
    autocomplete_fields = ('user',)
    date_hierarchy = 'remind_at'
    actions = ['mark_as_done']
    
    def user_link(self, obj):
        url = reverse('admin:base_user_change', args=[obj.user.pk])
        return format_html('<a href="{}">{}</a>', url, obj.user.username)
    user_link.short_description = 'User'
    
    def message_preview(self, obj):
        return obj.message[:50] + "..." if len(obj.message) > 50 else obj.message
    message_preview.short_description = 'Message'
    
    def mark_as_done(self, request, queryset):
        updated = queryset.update(is_done=True)
        self.message_user(request, f"{updated} reminders marked as done")
    mark_as_done.short_description = "Mark selected reminders as done"

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('user')
    
# Create enhanced admin site instance
# admin_site = AdminSiteEnhanced(name='enhanced_admin')

# =============================================================================
# 📝 REGISTER ALL MODELS WITH ENHANCED ADMINS
# =============================================================================

# User Management
admin.site.register(User, CustomUserAdmin)
admin.site.register(Team, TeamAdmin)
admin.site.register(TeamMembership, TeamMembershipAdmin)

# Notes System
admin.site.register(NoteList, NoteListAdmin)
admin.site.register(Note, NoteAdmin)

# Client Management
admin.site.register(ClientProfile, ClientProfileAdmin)
admin.site.register(ClientProfileModification, ClientProfileModificationAdmin)

# Lead Management
admin.site.register(Lead, LeadAdmin)
admin.site.register(LeadInteraction, LeadInteractionAdmin)
admin.site.register(ProductDiscussion, ProductDiscussionAdmin)
admin.site.register(LeadStatusChange, LeadStatusChangeAdmin)

# Legacy Client (for backward compatibility)
admin.site.register(Client, ClientAdmin)

# Task and Service Management
admin.site.register(Task, TaskAdmin)
admin.site.register(Reminder, ReminderAdmin)
admin.site.register(ServiceRequest, ServiceRequestAdmin)

# Register Service Request related models with enhanced admins
@admin.register(ServiceRequestType)
class ServiceRequestTypeAdmin(admin.ModelAdmin, UserFriendlyAdminMixin):
    list_display = ('type_name_badge', 'category_badge', 'code_display', 'status_badge', 'usage_stats')
    list_filter = ('category', 'is_active')
    search_fields = ('name', 'code', 'description')
    ordering = ('category', 'name')
    list_per_page = 50
    
    fieldsets = (
        ('📋 Basic Information', {
            'fields': ('name', 'category', 'code', 'description', 'is_active'),
            'description': 'Basic service request type configuration'
        }),
        ('📄 Document Requirements', {
            'fields': ('required_documents',),
            'classes': ('collapse',),
            'description': 'Specify required documents for this request type'
        })
    )
    
    def type_name_badge(self, obj):
        return format_html('<strong>📋 {}</strong>', obj.name)
    type_name_badge.short_description = 'Request Type'
    type_name_badge.admin_order_field = 'name'
    
    def category_badge(self, obj):
        category_colors = {
            'investment': '#28a745',
            'account': '#007bff', 
            'documentation': '#ffc107',
            'support': '#6c757d'
        }
        color = category_colors.get(obj.category, '#6c757d')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 8px; border-radius: 12px; font-size: 11px;">{}</span>',
            color, obj.get_category_display() if hasattr(obj, 'get_category_display') else obj.category
        )
    category_badge.short_description = 'Category'
    category_badge.admin_order_field = 'category'
    
    def code_display(self, obj):
        return format_html('<code style="background: #f8f9fa; padding: 2px 4px; border-radius: 3px;">{}</code>', obj.code)
    code_display.short_description = 'Code'
    
    def status_badge(self, obj):
        if obj.is_active:
            return format_html('<span style="color: #28a745; font-weight: bold;">✅ Active</span>')
        return format_html('<span style="color: #dc3545; font-weight: bold;">❌ Inactive</span>')
    status_badge.short_description = 'Status'
    
    def usage_stats(self, obj):
        count = ServiceRequest.objects.filter(request_type=obj).count() if hasattr(obj, 'service_requests') else 0
        if count > 0:
            url = reverse('admin:base_servicerequest_changelist')
            return format_html(
                '<a href="{}?request_type__id__exact={}" style="color: #007bff; font-weight: bold;">📊 {} requests</a>',
                url, obj.id, count
            )
        return format_html('<span style="color: #6c757d;">No requests</span>')
    usage_stats.short_description = 'Usage'

class PortfolioUploadLogAdmin(admin.ModelAdmin):
    list_display = [
        'upload_link', 'row_display', 'client_info', 'status_colored', 
        'message_preview', 'portfolio_link', 'created_at'
    ]
    list_filter = [
        'status', 
        ('upload', admin.RelatedOnlyFieldListFilter),
        'created_at',
        ('upload__uploaded_by', admin.RelatedOnlyFieldListFilter)
    ]
    search_fields = ['client_name', 'client_pan', 'scheme_name', 'message']
    readonly_fields = [
        'upload', 'row_number', 'client_name', 'client_pan', 
        'scheme_name', 'status', 'message', 'portfolio_entry', 'created_at'
    ]
    date_hierarchy = 'created_at'
    ordering = ['-created_at', 'upload', 'row_number']
    
    # Make this completely read-only - logs are auto-generated
    def has_add_permission(self, request):
        return False
    
    def has_change_permission(self, request, obj=None):
        return False
    
    def has_delete_permission(self, request, obj=None):
        # Only allow superusers to delete logs for cleanup
        return request.user.is_superuser
    
    def upload_link(self, obj):
        """Link to the upload with status"""
        url = reverse('admin:base_portfolioupload_change', args=[obj.upload.pk])
        return format_html(
            '<a href="{}" title="View upload details">{}</a><br><small style="color: gray;">{}</small>',
            url, obj.upload.upload_id, obj.upload.get_status_display()
        )
    upload_link.short_description = "Upload"
    upload_link.admin_order_field = 'upload__upload_id'
    
    def row_display(self, obj):
        """Display row number with special formatting for system messages"""
        if obj.row_number == 0:
            return format_html('<span style="background: #e9ecef; padding: 2px 6px; border-radius: 3px;">SYSTEM</span>')
        return format_html('<span style="font-family: monospace;">Row {}</span>', obj.row_number)
    row_display.short_description = "Row"
    row_display.admin_order_field = 'row_number'
    
    def client_info(self, obj):
        """Display client information if available"""
        if obj.client_name:
            client_info = f"<strong>{obj.client_name}</strong>"
            if obj.client_pan:
                client_info += f"<br><small>PAN: {obj.client_pan}</small>"
            if obj.scheme_name:
                # Truncate long scheme names
                scheme_display = obj.scheme_name[:30] + "..." if len(obj.scheme_name) > 30 else obj.scheme_name
                client_info += f"<br><small style='color: #6c757d;'>{scheme_display}</small>"
            return format_html(client_info)
        return format_html('<em style="color: #6c757d;">System Message</em>')
    client_info.short_description = "Client Info"
    
    def status_colored(self, obj):
        """Display status with appropriate colors"""
        colors = {
            'success': 'green',
            'warning': 'orange', 
            'error': 'red'
        }
        icons = {
            'success': '✅',
            'warning': '⚠️',
            'error': '❌'
        }
        color = colors.get(obj.status, 'black')
        icon = icons.get(obj.status, '•')
        
        return format_html(
            '<span style="color: {}; font-weight: bold;">{} {}</span>',
            color, icon, obj.get_status_display()
        )
    status_colored.short_description = "Status"
    status_colored.admin_order_field = 'status'
    
    def message_preview(self, obj):
        """Display truncated message with full message in tooltip"""
        if len(obj.message) > 80:
            preview = obj.message[:80] + "..."
            return format_html(
                '<span title="{}">{}</span>',
                obj.message.replace('"', '&quot;'), preview
            )
        return obj.message
    message_preview.short_description = "Message"
    
    def portfolio_link(self, obj):
        """Link to created portfolio entry if available"""
        if obj.portfolio_entry:
            url = reverse('admin:base_clientportfolio_change', args=[obj.portfolio_entry.pk])
            return format_html(
                '<a href="{}" style="color: #28a745;" title="View portfolio entry">📊 View</a>',
                url
            )
        return format_html('<span style="color: #6c757d;">-</span>')
    portfolio_link.short_description = "Portfolio"
    
    

class ClientPortfolioAdmin(admin.ModelAdmin):
    list_display = [
        'client_name', 'client_pan', 'scheme_name', 'total_value_display',
        'primary_asset_class', 'is_mapped', 'client_profile_link',
        'upload_batch_link', 'created_at'
    ]
    list_filter = [
        'is_mapped', 'upload_batch', 'created_at', 'data_as_of_date',
        'mapped_rm', 'mapped_ops'
    ]
    search_fields = [
        'client_name', 'client_pan', 'scheme_name', 'isin_number'
    ]
    readonly_fields = [
        'primary_asset_class', 'gain_loss', 'gain_loss_percentage',
        'created_at', 'updated_at'
    ]
    
    fieldsets = (
        ('Client Information', {
            'fields': (
                'client_name', 'client_pan', 'family_head',
                'client_profile', 'is_mapped', 'mapping_notes'
            )
        }),
        ('Scheme Information', {
            'fields': (
                'scheme_name', 'isin_number', 'folio_number'
            )
        }),
        ('Portfolio Values', {
            'fields': (
                ('total_value', 'cost_value', 'units'),
                ('debt_value', 'equity_value', 'hybrid_value'),
                ('liquid_ultra_short_value', 'other_value', 'arbitrage_value'),
                'allocation_percentage'
            )
        }),
        ('Personnel Mapping', {
            'fields': (
                ('relationship_manager', 'mapped_rm'),
                ('operations_personnel', 'mapped_ops'),
                ('rm_code', 'operations_code')
            )
        }),
        ('Additional Information', {
            'fields': (
                ('app_code', 'equity_code'),
                ('sub_broker', 'sub_broker_code'),
                ('client_iwell_code', 'family_head_iwell_code')
            ),
            'classes': ('collapse',)
        }),
        ('Metadata', {
            'fields': (
                'upload_batch', 'data_as_of_date', 'is_active',
                'created_at', 'updated_at'
            ),
            'classes': ('collapse',)
        })
    )
    
    actions = ['map_to_clients', 'export_to_csv', 'mark_inactive']
    
    def changelist_view(self, request, extra_context=None):
        """Override changelist view to add CSRF token to context"""
        extra_context = extra_context or {}
        extra_context['csrf_token'] = request.META.get('CSRF_COOKIE')
        return super().changelist_view(request, extra_context=extra_context)
    
    def actions_column(self, obj):
        """Action buttons for each upload - UPDATED with proper CSRF"""
        actions = []
        
        # Get the current request from thread local or use a simple approach
        csrf_token = "{{ csrf_token }}"  # This will be replaced by Django template
        
        # Process button for pending uploads
        if obj.status == 'pending':
            actions.append(f'''
                <a href="javascript:void(0)" 
                   onclick="processUpload({obj.pk})" 
                   class="button" 
                   style="background: #007bff; color: white; margin: 2px; text-decoration: none; padding: 4px 8px; border-radius: 3px; display: inline-block;">
                    🚀 Process
                </a>
            ''')
        
        # Retry button for failed uploads
        if obj.status == 'failed':
            actions.append(f'''
                <a href="javascript:void(0)" 
                   onclick="retryUpload({obj.pk})" 
                   class="button" 
                   style="background: #ffc107; color: black; margin: 2px; text-decoration: none; padding: 4px 8px; border-radius: 3px; display: inline-block;">
                    🔄 Retry
                </a>
            ''')
        
        # Logs button (always available if logs exist)
        if obj.processing_logs.exists():
            logs_url = reverse('admin:base_portfoliouploadlog_changelist') + f'?upload__id__exact={obj.pk}'
            actions.append(f'''
                <a href="{logs_url}" 
                   class="button" 
                   style="background: #6c757d; color: white; margin: 2px; text-decoration: none; padding: 4px 8px; border-radius: 3px; display: inline-block;">
                    📋 Logs ({obj.processing_logs.count()})
                </a>
            ''')
        
        # Portfolios button for successful uploads
        if obj.status in ['completed', 'partial'] and obj.portfolio_entries.exists():
            portfolios_url = reverse('admin:base_clientportfolio_changelist') + f'?upload_batch__id__exact={obj.pk}'
            actions.append(f'''
                <a href="{portfolios_url}" 
                   class="button" 
                   style="background: #28a745; color: white; margin: 2px; text-decoration: none; padding: 4px 8px; border-radius: 3px; display: inline-block;">
                    📊 Portfolios ({obj.portfolio_entries.count()})
                </a>
            ''')
        
        # Mapping button for uploads with unmapped portfolios
        if obj.status in ['completed', 'partial']:
            unmapped_count = obj.portfolio_entries.filter(is_mapped=False).count()
            if unmapped_count > 0:
                actions.append(f'''
                    <a href="javascript:void(0)" 
                       onclick="remapUpload({obj.pk})" 
                       class="button" 
                       style="background: #17a2b8; color: white; margin: 2px; text-decoration: none; padding: 4px 8px; border-radius: 3px; display: inline-block;">
                        🔗 Map ({unmapped_count})
                    </a>
                ''')
        
        # Add JavaScript for handling actions
        script = '''
        <script>
        function processUpload(uploadId) {
            if (confirm('Process this upload?')) {
                performAction('process_single_upload', uploadId);
            }
        }
        
        function retryUpload(uploadId) {
            if (confirm('Retry this upload?')) {
                performAction('retry_single_upload', uploadId);
            }
        }
        
        function remapUpload(uploadId) {
            if (confirm('Re-attempt client mapping?')) {
                performAction('remap_single_upload', uploadId);
            }
        }
        
        function performAction(action, uploadId) {
            const form = document.createElement('form');
            form.method = 'post';
            form.action = '';
            
            const actionInput = document.createElement('input');
            actionInput.type = 'hidden';
            actionInput.name = 'action';
            actionInput.value = action;
            
            const idInput = document.createElement('input');
            idInput.type = 'hidden';
            idInput.name = '_selected_action';
            idInput.value = uploadId;
            
            const csrfInput = document.createElement('input');
            csrfInput.type = 'hidden';
            csrfInput.name = 'csrfmiddlewaretoken';
            csrfInput.value = document.querySelector('[name=csrfmiddlewaretoken]').value;
            
            form.appendChild(actionInput);
            form.appendChild(idInput);
            form.appendChild(csrfInput);
            
            document.body.appendChild(form);
            form.submit();
        }
        </script>
        '''
        
        return format_html(''.join(actions) + script)
    actions_column.short_description = "Actions"
    
    def total_value_display(self, obj):
        """Display total value with currency formatting"""
        return f"₹{obj.total_value:,.2f}"
    total_value_display.short_description = "Total Value"
    total_value_display.admin_order_field = 'total_value'
    
    def client_profile_link(self, obj):
        """Link to client profile if mapped"""
        if obj.client_profile:
            url = reverse('admin:base_clientprofile_change', args=[obj.client_profile.pk])
            return format_html('<a href="{}">{}</a>', url, obj.client_profile.client_full_name)
        return format_html('<em style="color: orange;">Not mapped</em>')
    client_profile_link.short_description = "Client Profile"
    
    def upload_batch_link(self, obj):
        """Link to the upload batch"""
        if obj.upload_batch:
            url = reverse('admin:base_portfolioupload_change', args=[obj.upload_batch.pk])
            return format_html(
                '<a href="{}" title="View upload batch">{}</a><br><small>{}</small>',
                url, obj.upload_batch.upload_id, obj.upload_batch.get_status_display()
            )
        return '-'
    upload_batch_link.short_description = 'Upload Batch'
    
    def primary_asset_class(self, obj):
        return obj.primary_asset_class
    primary_asset_class.short_description = "Primary Asset Class"
    
    def map_to_clients(self, request, queryset):
        """Action to map selected portfolios to client profiles"""
        mapped_count = 0
        for portfolio in queryset.filter(is_mapped=False):
            mapped, message = portfolio.map_to_client_profile()
            if mapped:
                mapped_count += 1
        
        self.message_user(
            request,
            f"Successfully mapped {mapped_count} out of {queryset.count()} portfolios",
            level=messages.SUCCESS if mapped_count > 0 else messages.WARNING
        )
    map_to_clients.short_description = "Map selected portfolios to client profiles"
    
    def export_to_csv(self, request, queryset):
        """Export selected portfolios to CSV"""
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="portfolios.csv"'
        
        writer = csv.writer(response)
        writer.writerow([
            'Client Name', 'Client PAN', 'Scheme Name', 'Total Value',
            'Equity Value', 'Debt Value', 'Units', 'Is Mapped',
            'Client Profile', 'RM', 'Operations'
        ])
        
        for portfolio in queryset:
            writer.writerow([
                portfolio.client_name,
                portfolio.client_pan,
                portfolio.scheme_name,
                portfolio.total_value,
                portfolio.equity_value,
                portfolio.debt_value,
                portfolio.units,
                portfolio.is_mapped,
                portfolio.client_profile.client_full_name if portfolio.client_profile else '',
                portfolio.relationship_manager,
                portfolio.operations_personnel
            ])
        
        return response
    export_to_csv.short_description = "Export selected portfolios to CSV"
    
    def mark_inactive(self, request, queryset):
        """Mark selected portfolios as inactive"""
        updated = queryset.update(is_active=False)
        self.message_user(
            request,
            f"Marked {updated} portfolios as inactive",
            level=messages.SUCCESS
        )
    mark_inactive.short_description = "Mark selected portfolios as inactive"


class MutualFundSchemeAdmin(admin.ModelAdmin):
    list_display = [
        'scheme_name', 'amc_name', 'scheme_type', 'category_short',
        'risk_category', 'is_active', 'portfolio_count'
    ]
    list_filter = ['scheme_type', 'risk_category', 'is_active', 'amc_name', 'upload_batch']
    search_fields = ['scheme_name', 'amc_name', 'scheme_code', 'isin_growth', 'isin_div_reinvestment', 'category']
    readonly_fields = ['scheme_code', 'created_at', 'updated_at', 'portfolio_count', 'upload_batch', 'last_updated']
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('scheme_name', 'amc_name', 'scheme_code', 'category')
        }),
        ('ISIN Information', {
            'fields': ('isin_growth', 'isin_div_reinvestment')
        }),
        ('Classification', {
            'fields': ('scheme_type', 'risk_category')
        }),
        ('Investment Limits', {
            'fields': ('minimum_investment', 'minimum_sip')
        }),
        ('Status & NAV', {
            'fields': ('is_active', 'last_nav_date', 'last_nav_price')
        }),
        ('Upload Tracking', {
            'fields': ('upload_batch', 'last_updated'),
            'classes': ('collapse',)
        }),
        ('Metadata', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )
    
    def category_short(self, obj):
        """Display shortened category name"""
        if obj.category and len(obj.category) > 30:
            return obj.category[:30] + "..."
        return obj.category or "-"
    category_short.short_description = "Category"
    
    def portfolio_count(self, obj):
        """Count portfolio entries for this scheme"""
        return ClientPortfolio.objects.filter(scheme_name__iexact=obj.scheme_name).count()
    portfolio_count.short_description = "Portfolio Entries"
    
    def get_queryset(self, request):
        """Optimize queryset with select_related"""
        return super().get_queryset(request).select_related('upload_batch')

# Optional: Add these admin actions for bulk operations
@admin.action(description='Mark selected schemes as active')
def make_schemes_active(modeladmin, request, queryset):
    updated = queryset.update(is_active=True)
    modeladmin.message_user(request, f"{updated} schemes marked as active.")

@admin.action(description='Mark selected schemes as inactive')
def make_schemes_inactive(modeladmin, request, queryset):
    updated = queryset.update(is_active=False)
    modeladmin.message_user(request, f"{updated} schemes marked as inactive.")

# Add the actions to the admin class
MutualFundSchemeAdmin.actions = [make_schemes_active, make_schemes_inactive]

# Also add the SchemeUpload and SchemeUploadLog admin classes if you haven't already:

class SchemeUploadAdmin(admin.ModelAdmin):
    list_display = [
        'upload_id', 'uploaded_by', 'status', 'total_rows', 
        'successful_rows', 'failed_rows', 'updated_rows', 'uploaded_at'
    ]
    list_filter = ['status', 'uploaded_at', 'update_existing', 'mark_missing_inactive']
    readonly_fields = [
        'upload_id', 'processed_at', 'total_rows', 'processed_rows', 
        'successful_rows', 'failed_rows', 'updated_rows', 'processing_summary', 'error_details'
    ]
    search_fields = ['upload_id', 'uploaded_by__username']
    
    fieldsets = (
        ('Upload Information', {
            'fields': ('upload_id', 'file', 'uploaded_by', 'uploaded_at')
        }),
        ('Processing Options', {
            'fields': ('update_existing', 'mark_missing_inactive')
        }),
        ('Processing Status', {
            'fields': ('status', 'processed_at', 'total_rows', 'processed_rows', 
                      'successful_rows', 'failed_rows', 'updated_rows')
        }),
        ('Processing Details', {
            'fields': ('processing_log', 'processing_summary', 'error_details'),
            'classes': ('collapse',)
        })
    )


class SchemeUploadLogAdmin(admin.ModelAdmin):
    list_display = ['upload', 'row_number', 'status', 'amc_name', 'scheme_name_short', 'created_at']
    list_filter = ['status', 'upload', 'created_at']
    search_fields = ['amc_name', 'scheme_name', 'message', 'upload__upload_id']
    raw_id_fields = ['upload', 'scheme']
    readonly_fields = ['created_at']
    
    def scheme_name_short(self, obj):
        """Display shortened scheme name"""
        if obj.scheme_name and len(obj.scheme_name) > 50:
            return obj.scheme_name[:50] + "..."
        return obj.scheme_name
    scheme_name_short.short_description = 'Scheme Name'
    
from django.urls import path
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.http import HttpResponse
from django.core.paginator import Paginator
from django.db.models import Q
from .models import ClientUpload, ClientUploadLog, ClientProfile, Client

@admin.register(ClientUpload)
class ClientUploadAdmin(admin.ModelAdmin):
    list_display = [
        'upload_id', 'file', 'uploaded_by', 'status', 'uploaded_at',
        'total_rows', 'successful_rows', 'updated_rows', 'failed_rows',
        'processed_at'
    ]
    list_filter = ['status', 'uploaded_at', 'processed_at']
    search_fields = ['upload_id', 'file', 'uploaded_by__username']
    readonly_fields = [
        'upload_id', 'uploaded_at', 'processed_at', 'status',
        'total_rows', 'processed_rows', 'successful_rows', 
        'failed_rows', 'updated_rows', 'processing_log',
        'error_details', 'processing_summary'
    ]
    
    fieldsets = (
        ('Upload Information', {
            'fields': ('upload_id', 'file', 'uploaded_by', 'uploaded_at')
        }),
        ('Processing Status', {
            'fields': ('status', 'processed_at', 'total_rows', 'processed_rows',
                      'successful_rows', 'updated_rows', 'failed_rows')
        }),
        ('Options', {
            'fields': ('update_existing',)
        }),
        ('Processing Details', {
            'fields': ('processing_log', 'error_details', 'processing_summary'),
            'classes': ('collapse',)
        }),
        ('Archive', {
            'fields': ('is_archived', 'archived_at', 'archived_by'),
            'classes': ('collapse',)
        })
    )
    
    actions = ['reprocess_uploads', 'archive_uploads']
    
    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('<int:upload_id>/logs/', self.admin_site.admin_view(self.view_logs), 
                 name='client_upload_logs'),
            path('<int:upload_id>/reprocess/', self.admin_site.admin_view(self.reprocess_upload), 
                 name='client_upload_reprocess'),
            path('upload/', self.admin_site.admin_view(self.upload_file), 
                 name='client_upload_file'),
        ]
        return custom_urls + urls
    
    def view_logs(self, request, upload_id):
        """View detailed logs for an upload"""
        upload = get_object_or_404(ClientUpload, id=upload_id)
        logs = upload.processing_logs.all().order_by('row_number', 'created_at')
        
        # Filter logs if requested
        status_filter = request.GET.get('status')
        if status_filter:
            logs = logs.filter(status=status_filter)
        
        search_query = request.GET.get('search')
        if search_query:
            logs = logs.filter(
                Q(client_name__icontains=search_query) |
                Q(pan_number__icontains=search_query) |
                Q(message__icontains=search_query)
            )
        
        # Paginate logs
        paginator = Paginator(logs, 50)
        page = request.GET.get('page', 1)
        logs_page = paginator.get_page(page)
        
        context = {
            'title': f'Upload Logs - {upload.upload_id}',
            'upload': upload,
            'logs': logs_page,
            'status_choices': ClientUploadLog.STATUS_CHOICES,
            'current_status': status_filter,
            'search_query': search_query,
        }
        
        return render(request, 'admin/client_upload_logs.html', context)
    
    def reprocess_upload(self, request, upload_id):
        """Reprocess a failed or partial upload"""
        upload = get_object_or_404(ClientUpload, id=upload_id)
        
        if request.method == 'POST':
            if upload.status in ['failed', 'partial', 'completed']:
                # Reset counters
                upload.status = 'pending'
                upload.processed_at = None
                upload.processed_rows = 0
                upload.successful_rows = 0
                upload.failed_rows = 0
                upload.updated_rows = 0
                upload.processing_log = ''
                upload.error_details = {}
                upload.save()
                
                # Clear old logs
                upload.processing_logs.all().delete()
                
                # Start reprocessing
                from .models import process_client_upload_deferred
                process_client_upload_deferred(upload.id)
                
                messages.success(request, f'Upload {upload.upload_id} has been queued for reprocessing.')
                return redirect('admin:myapp_clientupload_change', upload.id)
            else:
                messages.error(request, 'Upload cannot be reprocessed in current status.')
        
        context = {
            'title': f'Reprocess Upload - {upload.upload_id}',
            'upload': upload,
        }
        
        return render(request, 'admin/client_upload_reprocess.html', context)
    
    def upload_file(self, request):
        """Custom upload interface"""
        if request.method == 'POST':
            if 'file' in request.FILES:
                upload = ClientUpload.objects.create(
                    file=request.FILES['file'],
                    uploaded_by=request.user,
                    update_existing=request.POST.get('update_existing') == 'on'
                )
                
                messages.success(request, 
                    f'File uploaded successfully as {upload.upload_id}. Processing will start automatically.')
                return redirect('admin:myapp_clientupload_change', upload.id)
            else:
                messages.error(request, 'Please select a file to upload.')
        
        context = {
            'title': 'Upload Client Data File',
        }
        
        return render(request, 'admin/client_upload_file.html', context)
    
    def reprocess_uploads(self, request, queryset):
        """Action to reprocess selected uploads"""
        count = 0
        for upload in queryset.filter(status__in=['failed', 'partial']):
            upload.status = 'pending'
            upload.processed_at = None
            upload.save()
            
            from .models import process_client_upload_deferred
            process_client_upload_deferred(upload.id)
            count += 1
        
        self.message_user(request, f'{count} uploads queued for reprocessing.')
    
    reprocess_uploads.short_description = "Reprocess selected uploads"
    
    def archive_uploads(self, request, queryset):
        """Action to archive selected uploads"""
        count = queryset.filter(is_archived=False).update(
            is_archived=True,
            archived_at=timezone.now(),
            archived_by=request.user
        )
        self.message_user(request, f'{count} uploads archived.')
    
    archive_uploads.short_description = "Archive selected uploads"


@admin.register(ClientUploadLog)
class ClientUploadLogAdmin(admin.ModelAdmin):
    list_display = [
        'upload', 'row_number', 'client_name', 'pan_number', 
        'status', 'message_preview', 'created_at'
    ]
    list_filter = ['status', 'upload', 'created_at']
    search_fields = ['client_name', 'pan_number', 'message']
    readonly_fields = ['upload', 'row_number', 'client_name', 'pan_number', 
                      'status', 'message', 'client_profile', 'created_at']
    
    def message_preview(self, obj):
        return obj.message[:100] + "..." if len(obj.message) > 100 else obj.message
    message_preview.short_description = "Message Preview"
    
    def has_add_permission(self, request):
        return False
    
# Business Analytics
admin.site.register(BusinessTracker, BusinessTrackerAdmin)

# Portfolio Management (already registered above)
# admin.site.register(PortfolioUpload, PortfolioUploadAdmin) - already done
admin.site.register(PortfolioUploadLog, PortfolioUploadLogAdmin)
admin.site.register(ClientPortfolio, ClientPortfolioAdmin)
admin.site.register(MutualFundScheme, MutualFundSchemeAdmin)

# Additional Models with basic enhanced admin
admin.site.register(SchemeUpload, SchemeUploadAdmin)
admin.site.register(SchemeUploadLog, SchemeUploadLogAdmin)

# Unregister default Group admin and register enhanced one
admin.site.unregister(Group)
admin.site.register(Group, CustomGroupAdmin)

# =============================================================================
# 🎨 FINAL ADMIN SITE CUSTOMIZATION
# =============================================================================

# Enhanced admin site headers and branding
admin.site.site_header = "🏢 CRM Administration Dashboard"
admin.site.site_title = "CRM Admin Portal"
admin.site.index_title = "🎯 Welcome to Your CRM Control Center"

# Add custom CSS for better styling
admin.site.enable_nav_sidebar = True

# Custom admin template context processor for additional features
def admin_context_processor(request):
    """Add custom context to admin templates"""
    return {
        'user_display_name': request.user.get_full_name() or request.user.username if request.user.is_authenticated else 'Guest',
        'user_role_display': request.user.get_role_display() if hasattr(request.user, 'get_role_display') else 'Unknown Role',
        'is_manager_role': request.user.role in ['rm_head', 'ops_team_lead', 'business_head', 'business_head_ops'] if hasattr(request.user, 'role') else False,
    }

# JavaScript for enhanced interactivity
ENHANCED_ADMIN_JS = """
<script>
// Enhanced admin JavaScript for better user experience
document.addEventListener('DOMContentLoaded', function() {
    // Add loading states for action buttons
    document.querySelectorAll('button[onclick]').forEach(button => {
        button.addEventListener('click', function() {
            this.style.opacity = '0.6';
            this.innerHTML = '⏳ Processing...';
            this.disabled = true;
        });
    });
    
    // Add confirmation dialogs for important actions
    document.querySelectorAll('input[name="action"]').forEach(select => {
        select.addEventListener('change', function() {
            const action = this.value;
            const dangerousActions = ['delete_selected', 'mark_as_muted', 'mark_sla_breached'];
            
            if (dangerousActions.includes(action)) {
                const confirmed = confirm('⚠️ Are you sure you want to perform this action? This may have significant impact.');
                if (!confirmed) {
                    this.value = '';
                }
            }
        });
    });
    
    // Enhanced tooltips
    document.querySelectorAll('[title]').forEach(element => {
        element.style.cursor = 'help';
    });
    
    // Auto-refresh for processing status
    if (window.location.href.includes('portfolioupload') && 
        document.querySelector('[style*="Processing"]')) {
        setTimeout(() => window.location.reload(), 10000); // Refresh every 10 seconds
    }
});

// Helper functions for admin actions
function markCompleted(noteId) {
    if (confirm('Mark this note as completed?')) {
        // Implementation would go here
        window.location.reload();
    }
}

function changeStatus(objectId, newStatus) {
    if (confirm(`Change status to ${newStatus}?`)) {
        // Implementation would go here
        window.location.reload();
    }
}

function assignToMe(objectId) {
    if (confirm('Assign this item to yourself?')) {
        // Implementation would go here
        window.location.reload();
    }
}

function processUpload(uploadId) {
    if (confirm('Start processing this upload?')) {
        // Implementation would go here
        window.location.reload();
    }
}

function retryUpload(uploadId) {
    if (confirm('Retry this failed upload?')) {
        // Implementation would go here
        window.location.reload();
    }
}

function markFollowUpComplete(interactionId) {
    if (confirm('Mark follow-up as complete?')) {
        // Implementation would go here
        window.location.reload();
    }
}

function setFollowUpRequired(interactionId) {
    if (confirm('Set follow-up as required?')) {
        // Implementation would go here
        window.location.reload();
    }
}

// Show success/error messages with better styling
function showAdminMessage(message, type = 'success') {
    const messageDiv = document.createElement('div');
    messageDiv.className = `alert alert-${type}`;
    messageDiv.style.cssText = `
        position: fixed;
        top: 20px;
        right: 20px;
        padding: 15px;
        border-radius: 5px;
        z-index: 9999;
        max-width: 400px;
        background: ${type === 'success' ? '#d4edda' : '#f8d7da'};
        border: 1px solid ${type === 'success' ? '#c3e6cb' : '#f5c6cb'};
        color: ${type === 'success' ? '#155724' : '#721c24'};
    `;
    messageDiv.innerHTML = `${type === 'success' ? '✅' : '❌'} ${message}`;
    
    document.body.appendChild(messageDiv);
    
    setTimeout(() => {
        messageDiv.remove();
    }, 5000);
}
</script>
"""