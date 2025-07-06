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
    ClientInteraction, ClientPortfolio, ExecutionPlan, MutualFundScheme, PlanAction, PlanComment, PlanTemplate, PlanWorkflowHistory, ServiceRequestComment, ServiceRequestDocument, ServiceRequestType, ServiceRequestWorkflow, User, Team, TeamMembership, NoteList, Note,
    ClientProfile, MFUCANAccount,
    ClientProfileModification, Lead, LeadInteraction, ProductDiscussion, 
    LeadStatusChange, Client, Task, Reminder, ServiceRequest, 
    BusinessTracker
)
from django.contrib.auth.forms import UserChangeForm, UserCreationForm
from django.contrib import messages
from datetime import datetime, timedelta


class TeamMembershipInline(admin.TabularInline):
    model = TeamMembership
    extra = 0
    fields = ('team', 'date_joined', 'is_active')
    readonly_fields = ('date_joined',)


class CustomUserAdmin(BaseUserAdmin):
    form = UserChangeForm
    add_form = UserCreationForm
    
    list_display = (
        'username', 'email', 'first_name', 'last_name', 
        'role', 'manager_link', 'team_info', 'client_count', 'is_active', 'date_joined'
    )
    list_filter = ('role', 'is_active', 'is_staff', 'date_joined', 'groups')
    search_fields = ('username', 'email', 'first_name', 'last_name')
    ordering = ('role', 'username')
    
    fieldsets = (
        (None, {'fields': ('username', 'password')}),
        ('Personal info', {'fields': ('first_name', 'last_name', 'email')}),
        ('Permissions', {
            'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions'),
        }),
        ('Important dates', {'fields': ('last_login', 'date_joined')}),
        ('Hierarchy & Role', {
            'fields': ('role', 'manager', 'managed_groups')
        }),
    )
    
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('username', 'password1', 'password2'),
        }),
        ('Hierarchy & Role', {
            'fields': ('role', 'manager')
        }),
    )
    
    inlines = [TeamMembershipInline]
    
    def manager_link(self, obj):
        if obj.manager:
            url = reverse('admin:base_user_change', args=[obj.manager.pk])
            return format_html('<a href="{}">{}</a>', url, obj.manager.username)
        return '-'
    manager_link.short_description = 'Manager'
    
    def team_info(self, obj):
        if obj.role in ['rm_head', 'ops_team_lead']:
            team_count = obj.get_team_members().count()
            managed_teams = obj.led_teams.all()
            team_names = ', '.join([team.name for team in managed_teams])
            return f"{team_count} members | Teams: {team_names}" if team_names else f"{team_count} members"
        elif obj.role in ['rm', 'ops_exec']:
            teams = obj.teams.all()
            return ', '.join([team.name for team in teams]) if teams else 'No team'
        return '-'
    team_info.short_description = 'Team Info'
    
    def client_count(self, obj):
        """Calculate client count based on user role."""
        try:
            if obj.role == 'rm':
                return ClientProfile.objects.filter(mapped_rm=obj).count()
            elif obj.role == 'ops_exec':
                return ClientProfile.objects.filter(mapped_ops_exec=obj).count()
        except Exception:
            return 'Error'
        return '-'
    client_count.short_description = 'Client Count'

    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'manager'
        ).prefetch_related(
            'teams',
            'managed_groups',
            'subordinates',
            'led_teams',
        )


class TeamMembershipAdmin(admin.ModelAdmin):
    list_display = ('user', 'team', 'date_joined', 'is_active')
    list_filter = ('is_active', 'date_joined', 'team')
    search_fields = ('user__username', 'team__name')
    autocomplete_fields = ('user', 'team')


class TeamAdmin(admin.ModelAdmin):
    list_display = ('name', 'leader_link', 'member_count', 'is_ops_team', 'created_at')
    list_filter = ('created_at', 'is_ops_team', 'leader')
    search_fields = ('name', 'description')
    autocomplete_fields = ('leader',)
    
    def leader_link(self, obj):
        if obj.leader:
            url = reverse('admin:base_user_change', args=[obj.leader.pk])
            return format_html('<a href="{}">{}</a>', url, obj.leader.username)
        return 'No Leader'
    leader_link.short_description = 'Team Leader'
    
    def member_count(self, obj):
        return obj.members.filter(teammembership__is_active=True).count()
    member_count.short_description = 'Active Members'

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('leader').prefetch_related('members')


# Notes System Admin Classes
class NoteInline(admin.TabularInline):
    model = Note
    extra = 0
    fields = ('heading', 'content', 'creation_date', 'due_date', 'is_completed')
    readonly_fields = ('creation_date',)


class NoteListAdmin(admin.ModelAdmin):
    list_display = ('name', 'user_link', 'note_count', 'created_at', 'updated_at')
    list_filter = ('created_at', 'updated_at')
    search_fields = ('name', 'description', 'user__username')
    autocomplete_fields = ('user',)
    inlines = [NoteInline]
    
    def user_link(self, obj):
        url = reverse('admin:base_user_change', args=[obj.user.pk])
        return format_html('<a href="{}">{}</a>', url, obj.user.username)
    user_link.short_description = 'User'
    
    def note_count(self, obj):
        return obj.notes.count()
    note_count.short_description = 'Notes Count'
    
    def get_queryset(self, request):
        # Users can only see their own note lists
        qs = super().get_queryset(request).select_related('user').prefetch_related('notes')
        if not request.user.is_superuser:
            qs = qs.filter(user=request.user)
        return qs
    
    def has_change_permission(self, request, obj=None):
        if obj and not request.user.is_superuser:
            return obj.user == request.user
        return super().has_change_permission(request, obj)


class NoteAdmin(admin.ModelAdmin):
    list_display = (
        'heading', 'user_link', 'note_list_link', 'creation_date', 
        'due_date', 'is_completed', 'is_overdue_display', 'updated_at'
    )
    list_filter = ('is_completed', 'creation_date', 'due_date', 'note_list')
    search_fields = ('heading', 'content', 'user__username', 'note_list__name')
    autocomplete_fields = ('user', 'note_list')
    readonly_fields = ('created_at', 'updated_at', 'completed_at')
    date_hierarchy = 'creation_date'
    
    fieldsets = (
        ('Note Information', {
            'fields': ('user', 'note_list', 'heading', 'content')
        }),
        ('Dates', {
            'fields': ('creation_date', 'reminder_date', 'due_date')
        }),
        ('Status', {
            'fields': ('is_completed', 'completed_at')
        }),
        ('Attachment', {
            'fields': ('attachment',)
        }),
        ('System Information', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    actions = ['mark_as_completed', 'mark_as_incomplete']
    
    def user_link(self, obj):
        url = reverse('admin:base_user_change', args=[obj.user.pk])
        return format_html('<a href="{}">{}</a>', url, obj.user.username)
    user_link.short_description = 'User'
    
    def note_list_link(self, obj):
        url = reverse('admin:base_notelist_change', args=[obj.note_list.pk])
        return format_html('<a href="{}">{}</a>', url, obj.note_list.name)
    note_list_link.short_description = 'Note List'
    
    def is_overdue_display(self, obj):
        if obj.is_overdue:
            return format_html('<span style="color: red;">Yes</span>')
        return 'No'
    is_overdue_display.short_description = 'Overdue'
    
    def mark_as_completed(self, request, queryset):
        updated = queryset.update(is_completed=True, completed_at=timezone.now())
        self.message_user(request, f"{updated} notes marked as completed")
    mark_as_completed.short_description = "Mark selected notes as completed"
    
    def mark_as_incomplete(self, request, queryset):
        updated = queryset.update(is_completed=False, completed_at=None)
        self.message_user(request, f"{updated} notes marked as incomplete")
    mark_as_incomplete.short_description = "Mark selected notes as incomplete"
    
    def get_queryset(self, request):
        # Users can only see their own notes
        qs = super().get_queryset(request).select_related('user', 'note_list')
        if not request.user.is_superuser:
            qs = qs.filter(user=request.user)
        return qs
    
    def has_change_permission(self, request, obj=None):
        if obj and not request.user.is_superuser:
            return obj.user == request.user
        return super().has_change_permission(request, obj)


# Client Account Inlines
class MFUCANAccountInline(admin.TabularInline):
    model = MFUCANAccount
    extra = 0
    fields = ('account_number', 'folio_number', 'amc_name', 'kyc_status', 'is_primary')




class ClientProfileModificationInline(admin.TabularInline):
    model = ClientProfileModification
    extra = 0
    fields = ('status', 'requested_at', 'requested_by', 'reason', 'approved_by', 'approved_at')
    readonly_fields = ('requested_at', 'approved_at')
    autocomplete_fields = ('requested_by', 'approved_by')
    can_delete = False
    
    def has_add_permission(self, request, obj):
        return False


class ClientProfileAdmin(admin.ModelAdmin):
    list_display = (
        'client_id', 'client_full_name', 'pan_number', 'email', 'mobile_number',
        'mapped_rm_link', 'mapped_ops_exec_link', 'status', 'created_at'
    )
    list_filter = ('status', 'created_at', 'mapped_rm__role', 'first_investment_date')
    search_fields = (
        'client_id', 'client_full_name', 'family_head_name', 'email', 
        'mobile_number', 'pan_number'
    )
    readonly_fields = ('client_id', 'created_at', 'updated_at')
    autocomplete_fields = ('mapped_rm', 'mapped_ops_exec', 'created_by', 'muted_by')
    inlines = [
        MFUCANAccountInline, 
         ClientProfileModificationInline
    ]
    date_hierarchy = 'created_at'
    
    fieldsets = (
        ('Basic Information', {
            'fields': (
                'client_id', 'client_full_name', 'family_head_name', 'pan_number',
                'date_of_birth', 'email', 'mobile_number'
            )
        }),
        ('Address & KYC', {
            'fields': ('address_kyc',)
        }),
        ('Investment Information', {
            'fields': ('first_investment_date', 'status')
        }),
        ('Mapping', {
            'fields': ('mapped_rm', 'mapped_ops_exec')
        }),
        ('Muting Information', {
            'fields': ('muted_reason', 'muted_date', 'muted_by'),
            'classes': ('collapse',)
        }),
        ('System Information', {
            'fields': ('created_by', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    actions = ['mark_as_active', 'mark_as_muted', 'export_client_data']
    
    def mapped_rm_link(self, obj):
        if obj.mapped_rm:
            url = reverse('admin:base_user_change', args=[obj.mapped_rm.pk])
            return format_html('<a href="{}">{}</a>', url, obj.mapped_rm.username)
        return '-'
    mapped_rm_link.short_description = 'Mapped RM'
    
    def mapped_ops_exec_link(self, obj):
        if obj.mapped_ops_exec:
            url = reverse('admin:base_user_change', args=[obj.mapped_ops_exec.pk])
            return format_html('<a href="{}">{}</a>', url, obj.mapped_ops_exec.username)
        return '-'
    mapped_ops_exec_link.short_description = 'Ops Executive'
    
    def mark_as_active(self, request, queryset):
        updated = queryset.update(status='active', muted_reason=None, muted_date=None, muted_by=None)
        self.message_user(request, f"{updated} client profiles marked as active")
    mark_as_active.short_description = "Mark selected clients as active"
    
    def mark_as_muted(self, request, queryset):
        updated = queryset.update(status='muted', muted_date=timezone.now(), muted_by=request.user)
        self.message_user(request, f"{updated} client profiles marked as muted")
    mark_as_muted.short_description = "Mark selected clients as muted"
    
    def export_client_data(self, request, queryset):
        count = queryset.count()
        self.message_user(request, f"Export initiated for {count} client profiles")
    export_client_data.short_description = "Export selected client data"
    
    def get_queryset(self, request):
        qs = super().get_queryset(request).select_related(
            'mapped_rm', 'mapped_ops_exec', 'created_by', 'muted_by'
        ).prefetch_related('modifications')
        
        # Apply hierarchy-based filtering based on user role
        user = request.user
        if user.is_superuser or user.role in ['top_management', 'business_head', 'business_head_ops']:
            return qs
        elif user.role == 'rm_head':
            accessible_users = user.get_accessible_users()
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
            return user.can_access_user_data(obj.mapped_rm) if obj.mapped_rm else False
        elif user.role == 'rm':
            return obj.mapped_rm == user
        elif user.role in ['ops_team_lead', 'ops_exec']:
            return user.can_modify_client_profile()
        
        return False


# Client Account Admin Classes
class MFUCANAccountAdmin(admin.ModelAdmin):
    list_display = ('account_number', 'client_link', 'folio_number', 'amc_name', 'kyc_status', 'is_primary')
    list_filter = ('kyc_status', 'is_primary', 'amc_name', 'created_at')
    search_fields = ('account_number', 'folio_number', 'client__client_full_name', 'amc_name')
    autocomplete_fields = ('client',)
    
    def client_link(self, obj):
        url = reverse('admin:base_clientprofile_change', args=[obj.client.pk])
        return format_html('<a href="{}">{}</a>', url, obj.client.client_full_name)
    client_link.short_description = 'Client'



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


# Lead Management Admin Classes
class ProductDiscussionInline(admin.TabularInline):
    model = ProductDiscussion
    extra = 0
    fields = ('product', 'interest_level', 'discussed_on', 'discussed_by', 'notes')
    readonly_fields = ('discussed_on',)
    autocomplete_fields = ('discussed_by',)


class LeadInteractionInline(admin.TabularInline):
    model = LeadInteraction
    extra = 0
    fields = ('interaction_type', 'interaction_date', 'notes', 'next_step', 'next_date', 'interacted_by')
    readonly_fields = ('interaction_date',)
    autocomplete_fields = ('interacted_by',)


class LeadStatusChangeInline(admin.TabularInline):
    model = LeadStatusChange
    extra = 0
    fields = ('changed_at', 'changed_by', 'old_status', 'new_status', 'notes', 'needs_approval', 'approved')
    readonly_fields = ('changed_at',)
    autocomplete_fields = ('changed_by', 'approved_by')


class LeadAdmin(admin.ModelAdmin):
    list_display = (
        'lead_id', 'name', 'email', 'mobile', 'status', 
        'assigned_to', 'probability', 'created_at', 'converted', 'client_profile_link'
    )
    list_filter = (
        'status', 'source', 'converted', 
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
    fieldsets = (
        ('Lead Information', {
            'fields': (
                'lead_id', 'name', 'email', 'mobile', 
                'status', 'probability', 'client_id'
            )
        }),
        ('Source Information', {
            'fields': (
                'source', 'source_details', 'reference_client'
            )
        }),
        ('Assignment', {
            'fields': (
                'assigned_to', 'created_by'
            )
        }),
        ('Reassignment', {
            'fields': (
                'needs_reassignment_approval', 'reassignment_requested_to'
            )
        }),
        ('Dates', {
            'fields': (
                'created_at', 'updated_at', 
                'first_interaction_date', 'next_interaction_date',
                'converted_at'
            )
        }),
        ('Conversion', {
            'fields': (
                'converted', 'converted_by', 'client_profile'
            )
        }),
        ('Additional Info', {
            'fields': ('notes',)
        }),
    )
    autocomplete_fields = (
        'assigned_to', 'created_by', 'reference_client', 'converted_by', 
        'reassignment_requested_to', 'client_profile'
    )
    inlines = [LeadInteractionInline, ProductDiscussionInline, LeadStatusChangeInline]
    actions = ['mark_as_converted', 'mark_as_hot', 'assign_to_me', 'create_client_profiles']
    
    def client_profile_link(self, obj):
        if obj.client_profile:
            url = reverse('admin:base_clientprofile_change', args=[obj.client_profile.pk])
            return format_html('<a href="{}">View Profile</a>', url)
        return '-'
    client_profile_link.short_description = 'Client Profile'
    
    def create_client_profiles(self, request, queryset):
        created_count = 0
        for lead in queryset.filter(converted=True, client_profile__isnull=True):
            # Create client profile from lead data
            client_profile = ClientProfile.objects.create(
                client_full_name=lead.name,
                email=lead.email or '',
                mobile_number=lead.mobile or '',
                mapped_rm=lead.assigned_to,
                created_by=request.user,
                status='active',
                pan_number='TEMP' + str(lead.id).zfill(6),  # Temporary PAN until real one is provided
                date_of_birth=timezone.now().date(),  # Default date, should be updated
                address_kyc='To be updated'  # Default address
            )
            lead.client_profile = client_profile
            lead.save()
            created_count += 1
        
        self.message_user(request, f"{created_count} client profiles created from leads")
    create_client_profiles.short_description = "Create client profiles for converted leads"
    
    def mark_as_converted(self, request, queryset):
        updated = queryset.update(converted=True, status='converted', converted_at=timezone.now())
        self.message_user(request, f"{updated} leads marked as converted")
    mark_as_converted.short_description = "Mark selected leads as converted"
    
    def mark_as_hot(self, request, queryset):
        updated = queryset.update(status='hot')
        self.message_user(request, f"{updated} leads marked as hot")
    mark_as_hot.short_description = "Mark selected leads as hot"
    
    def assign_to_me(self, request, queryset):
        updated = queryset.update(assigned_to=request.user)
        self.message_user(request, f"{updated} leads assigned to you")
    assign_to_me.short_description = "Assign selected leads to me"

    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'assigned_to', 'created_by', 'converted_by', 'reference_client', 'client_profile'
        )


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


from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html
from django.utils import timezone
from django.db.models import Count, Q
from django.shortcuts import redirect
from django.contrib import messages
from django.http import HttpResponse
import csv
from datetime import datetime, timedelta


class ServiceRequestDocumentInline(admin.TabularInline):
    """Inline admin for service request documents"""
    model = ServiceRequestDocument
    extra = 0
    readonly_fields = ('uploaded_at', 'uploaded_by')
    fields = ('document_name', 'document', 'uploaded_by', 'uploaded_at')
    
    def has_change_permission(self, request, obj=None):
        return False  # Don't allow editing documents


class ServiceRequestCommentInline(admin.TabularInline):
    """Inline admin for service request comments"""
    model = ServiceRequestComment
    extra = 0
    readonly_fields = ('created_at', 'commented_by')
    fields = ('comment', 'is_internal', 'commented_by', 'created_at')
    ordering = ('-created_at',)
    
    def has_change_permission(self, request, obj=None):
        return False  # Don't allow editing comments


class ServiceRequestWorkflowInline(admin.TabularInline):
    """Inline admin for workflow history"""
    model = ServiceRequestWorkflow
    extra = 0
    readonly_fields = ('from_status', 'to_status', 'from_user', 'to_user', 'transition_date', 'remarks')
    fields = ('from_status', 'to_status', 'from_user', 'to_user', 'transition_date', 'remarks')
    ordering = ('-transition_date',)
    
    def has_add_permission(self, request, obj=None):
        return False
    
    def has_change_permission(self, request, obj=None):
        return False
    
    def has_delete_permission(self, request, obj=None):
        return False


class ServiceRequestAdmin(admin.ModelAdmin):
    list_display = (
        'request_id', 'client_link', 'request_type_link', 'status_colored', 
        'priority_colored', 'raised_by_link', 'assigned_to_link', 'current_owner_link',
        'created_at', 'sla_status', 'days_pending'
    )
    list_filter = (
        'status', 'priority', 'request_type__category', 'request_type',
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
    
    # Enhanced actions
    actions = [
        'mark_as_resolved', 'mark_as_in_progress', 'mark_as_closed',
        'bulk_reassign', 'export_to_csv', 'mark_sla_breached'
    ]
    
    # Fieldsets for better organization
    fieldsets = (
        ('Basic Information', {
            'fields': ('request_id', 'client', 'request_type', 'description', 'priority')
        }),
        ('Assignment & Ownership', {
            'fields': ('raised_by', 'assigned_to', 'current_owner')
        }),
        ('Status & Workflow', {
            'fields': ('status', 'resolution_summary', 'client_approved')
        }),
        ('Timestamps', {
            'fields': (
                'created_at', 'submitted_at', 'documents_requested_at',
                'documents_received_at', 'resolved_at', 'closed_at'
            ),
            'classes': ('collapse',)
        }),
        ('SLA & Tracking', {
            'fields': ('expected_completion_date', 'sla_breached', 'documents_complete'),
            'classes': ('collapse',)
        }),
        ('Additional Details', {
            'fields': ('additional_details', 'required_documents_list'),
            'classes': ('collapse',)
        })
    )
    
    readonly_fields = (
        'request_id', 'created_at', 'updated_at', 'submitted_at',
        'documents_requested_at', 'documents_received_at', 'resolved_at',
        'closed_at', 'client_approval_date'
    )
    
    inlines = [ServiceRequestCommentInline, ServiceRequestDocumentInline, ServiceRequestWorkflowInline]
    
    
    
    # Custom methods for display
    def request_type_link(self, obj):
        if obj.request_type:
            url = reverse('admin:base_servicerequesttype_change', args=[obj.request_type.pk])
            return format_html(
                '<a href="{}" title="{}">{}</a>',
                url, obj.request_type.description or '', obj.request_type.name
            )
        return '-'
    request_type_link.short_description = 'Request Type'
    
    def client_link(self, obj):
        url = reverse('admin:base_client_change', args=[obj.client.pk])
        return format_html(
            '<a href="{}" title="Client ID: {}">{}</a>',
            url, obj.client.pk, obj.client.name
        )
    client_link.short_description = 'Client'
    
    def raised_by_link(self, obj):
        if obj.raised_by:
            name = obj.raised_by.get_full_name() or obj.raised_by.username
            return name
        return '-'
    
    def assigned_to_link(self, obj):
        if obj.assigned_to:
            name = obj.assigned_to.get_full_name() or obj.assigned_to.username
            return name
        return '-'
    
    def current_owner_link(self, obj):
        if obj.current_owner:
            name = obj.current_owner.get_full_name() or obj.current_owner.username
            return name
        return '-'
    
    def status_colored(self, obj):
        colors = {
            'draft': '#6c757d',        # Gray
            'submitted': '#007bff',     # Blue
            'documents_requested': '#ffc107',  # Yellow
            'documents_received': '#17a2b8',   # Cyan
            'in_progress': '#fd7e14',   # Orange
            'resolved': '#28a745',      # Green
            'client_verification': '#6f42c1',  # Purple
            'closed': '#343a40',        # Dark
            'on_hold': '#dc3545',       # Red
            'rejected': '#e83e8c'       # Pink
        }
        color = colors.get(obj.status, '#6c757d')
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color, obj.get_status_display()
        )
    status_colored.short_description = 'Status'
    
    def priority_colored(self, obj):
        colors = {
            'low': '#28a745',      # Green
            'medium': '#ffc107',   # Yellow
            'high': '#fd7e14',     # Orange
            'urgent': '#dc3545'    # Red
        }
        color = colors.get(obj.priority, '#6c757d')
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color, obj.get_priority_display()
        )
    priority_colored.short_description = 'Priority'
    
    def sla_status(self, obj):
        if obj.sla_breached:
            return format_html('<span style="color: red; font-weight: bold;">BREACHED</span>')
        elif obj.expected_completion_date:
            if obj.expected_completion_date < timezone.now():
                return format_html('<span style="color: orange; font-weight: bold;">OVERDUE</span>')
            elif obj.expected_completion_date < timezone.now() + timedelta(hours=4):
                return format_html('<span style="color: orange;">AT RISK</span>')
            else:
                return format_html('<span style="color: green;">ON TRACK</span>')
        return '-'
    sla_status.short_description = 'SLA Status'
    
    def days_pending(self, obj):
        if obj.status in ['closed', 'rejected']:
            return '-'
        
        start_date = obj.created_at
        if obj.status == 'documents_requested':
            start_date = obj.documents_requested_at or obj.created_at
        elif obj.status in ['documents_received', 'in_progress']:
            start_date = obj.documents_received_at or obj.submitted_at or obj.created_at
        
        days = (timezone.now() - start_date).days
        
        if days > 7:
            return format_html('<span style="color: red; font-weight: bold;">{} days</span>', days)
        elif days > 3:
            return format_html('<span style="color: orange;">{} days</span>', days)
        else:
            return f'{days} days'
    days_pending.short_description = 'Days Pending'
    
    # Enhanced actions
    def mark_as_resolved(self, request, queryset):
        updated_count = 0
        for obj in queryset:
            if obj.status not in ['resolved', 'closed']:
                obj.status = 'resolved'
                obj.resolved_at = timezone.now()
                obj.save()
                
                # Create workflow history
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
            f"{updated_count} service request(s) marked as resolved",
            messages.SUCCESS
        )
    mark_as_resolved.short_description = "Mark selected requests as resolved"
    
    def mark_as_in_progress(self, request, queryset):
        updated_count = 0
        for obj in queryset:
            if obj.status in ['submitted', 'documents_received']:
                obj.status = 'in_progress'
                obj.save()
                
                ServiceRequestWorkflow.objects.create(
                    service_request=obj,
                    from_status=obj.status,
                    to_status='in_progress',
                    from_user=request.user,
                    to_user=obj.current_owner,
                    remarks='Bulk action: Started processing via admin'
                )
                updated_count += 1
        
        self.message_user(
            request,
            f"{updated_count} service request(s) marked as in progress",
            messages.SUCCESS
        )
    mark_as_in_progress.short_description = "Mark selected requests as in progress"
    
    def mark_as_closed(self, request, queryset):
        updated_count = 0
        for obj in queryset:
            if obj.status == 'client_verification':
                obj.status = 'closed'
                obj.closed_at = timezone.now()
                obj.client_approved = True
                obj.client_approval_date = timezone.now()
                obj.save()
                
                ServiceRequestWorkflow.objects.create(
                    service_request=obj,
                    from_status='client_verification',
                    to_status='closed',
                    from_user=request.user,
                    to_user=obj.current_owner,
                    remarks='Bulk action: Closed via admin'
                )
                updated_count += 1
        
        self.message_user(
            request,
            f"{updated_count} service request(s) marked as closed",
            messages.SUCCESS
        )
    mark_as_closed.short_description = "Mark selected requests as closed"
    
    def bulk_reassign(self, request, queryset):
        # This would redirect to a custom page for bulk reassignment
        selected_ids = ','.join(str(obj.id) for obj in queryset)
        return redirect(f'/admin/bulk-reassign/?ids={selected_ids}')
    bulk_reassign.short_description = "Bulk reassign selected requests"
    
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
    export_to_csv.short_description = "Export selected requests to CSV"
    
    def mark_sla_breached(self, request, queryset):
        updated_count = queryset.filter(
            expected_completion_date__lt=timezone.now(),
            status__in=['submitted', 'documents_requested', 'documents_received', 'in_progress']
        ).update(sla_breached=True)
        
        self.message_user(
            request,
            f"{updated_count} service request(s) marked as SLA breached",
            messages.WARNING
        )
    mark_sla_breached.short_description = "Mark overdue requests as SLA breached"
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'client', 'raised_by', 'assigned_to', 'current_owner', 'request_type'
        ).prefetch_related('comments', 'documents')
    


def changelist_view(self, request, extra_context=None):
    # Add summary statistics to changelist
    queryset = self.get_queryset(request)
    
    # Apply any filters that are currently active
    cl = self.get_changelist_instance(request)
    queryset = cl.get_queryset(request)
    
    extra_context = extra_context or {}
    extra_context['summary_stats'] = {
        'total_requests': queryset.count(),
        'open_requests': queryset.filter(
            status__in=['submitted', 'documents_requested', 'documents_received', 'in_progress']
        ).count(),
        'overdue_requests': queryset.filter(
            expected_completion_date__lt=timezone.now(),
            status__in=['submitted', 'documents_requested', 'documents_received', 'in_progress']
        ).count(),
        'urgent_requests': queryset.filter(
            priority='urgent',
            status__in=['submitted', 'documents_requested', 'documents_received', 'in_progress']
        ).count(),
        'sla_breached': queryset.filter(sla_breached=True).count(),
    }
    
    return super().changelist_view(request, extra_context=extra_context)


@admin.register(ServiceRequestType)
class ServiceRequestTypeAdmin(admin.ModelAdmin):
    list_display = ('name', 'category', 'code', 'is_active', 'request_count')
    list_filter = ('category', 'is_active')
    search_fields = ('name', 'code', 'description')
    ordering = ('category', 'name')
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'category', 'code', 'description', 'is_active')
        }),
        ('Configuration', {
            'fields': ('required_documents',),
            'classes': ('collapse',)
        })
    )
    
    def request_count(self, obj):
        count = obj.service_requests.count()
        if count > 0:
            url = reverse('admin:base_servicerequest_changelist')
            return format_html(
                '<a href="{}?request_type__id__exact={}">{}</a>',
                url, obj.id, count
            )
        return 0
    request_count.short_description = 'Request Count'


@admin.register(ServiceRequestDocument)
class ServiceRequestDocumentAdmin(admin.ModelAdmin):
    list_display = ('document_name', 'service_request_link', 'uploaded_by', 'uploaded_at', 'file_size')
    list_filter = ('uploaded_at', 'uploaded_by')
    search_fields = ('document_name', 'service_request__request_id', 'uploaded_by__username')
    ordering = ('-uploaded_at',)
    readonly_fields = ('uploaded_at', 'file_size')
    
    def service_request_link(self, obj):
        url = reverse('admin:base_servicerequest_change', args=[obj.service_request.pk])
        return format_html('<a href="{}">{}</a>', url, obj.service_request.request_id)
    service_request_link.short_description = 'Service Request'
    
    def file_size(self, obj):
        if obj.document:
            size_mb = obj.document.size / (1024 * 1024)
            return f"{size_mb:.2f} MB"
        return '-'
    file_size.short_description = 'File Size'


@admin.register(ServiceRequestComment)
class ServiceRequestCommentAdmin(admin.ModelAdmin):
    list_display = ('service_request_link', 'comment_preview', 'commented_by', 'is_internal', 'created_at')
    list_filter = ('is_internal', 'created_at', 'commented_by')
    search_fields = ('comment', 'service_request__request_id', 'commented_by__username')
    ordering = ('-created_at',)
    readonly_fields = ('created_at',)
    
    def service_request_link(self, obj):
        url = reverse('admin:base_servicerequest_change', args=[obj.service_request.pk])
    service_request_link.short_description = 'Service Request'
    
    def comment_preview(self, obj):
        return obj.comment[:50] + '...' if len(obj.comment) > 50 else obj.comment
    comment_preview.short_description = 'Comment'


@admin.register(ServiceRequestWorkflow)
class ServiceRequestWorkflowAdmin(admin.ModelAdmin):
    list_display = ('service_request_link', 'from_status', 'to_status', 'from_user', 'to_user', 'transition_date')
    list_filter = ('from_status', 'to_status', 'transition_date')
    search_fields = ('service_request__request_id', 'from_user__username', 'to_user__username')
    ordering = ('-transition_date',)
    readonly_fields = ('transition_date',)
    
    def service_request_link(self, obj):
        url = reverse('admin:base_servicerequest_change', args=[obj.service_request.pk])
        return format_html('<a href="{}">{}</a>', url, obj.service_request.request_id)
    service_request_link.short_description = 'Service Request'



class BusinessTrackerAdmin(admin.ModelAdmin):
    list_display = (
        'month', 'user_link', 'team_link', 'total_aum_display', 
        'total_sip_display', 'total_demat'
    )
    list_filter = ('month', 'user__role', 'team')
    search_fields = ('user__username', 'team__name')
    ordering = ('-month',)
    autocomplete_fields = ('user', 'team')
    date_hierarchy = 'month'
    
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

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('user', 'team')


# Custom Group Admin for Team Management
class CustomGroupAdmin(admin.ModelAdmin):
    list_display = ('name', 'member_count', 'rm_head_link')
    search_fields = ('name',)
    filter_horizontal = ('permissions',)
    
    def member_count(self, obj):
        return obj.user_set.filter(role='rm').count()
    member_count.short_description = 'RM Members'
    
    def rm_head_link(self, obj):
        rm_head = User.objects.filter(
            role='rm_head',
            managed_groups=obj
        ).first()
        
        if rm_head:
            url = reverse('admin:base_user_change', args=[rm_head.pk])
            return format_html('<a href="{}">{}</a>', url, rm_head.username)
        return 'No Head Assigned'
    rm_head_link.short_description = 'Team Head'

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related('user_set')

# Add these imports to your existing admin.py
from django.utils.html import format_html
from django.urls import reverse
from django.utils import timezone
from django.db.models import Count, Q
from django.contrib.admin import SimpleListFilter
from datetime import timedelta

# Custom Filters for ClientInteraction
class FollowUpFilter(SimpleListFilter):
    """Filter interactions by follow-up status"""
    title = 'follow-up status'
    parameter_name = 'followup'

    def lookups(self, request, model_admin):
        return (
            ('required', 'Follow-up required'),
            ('overdue', 'Overdue follow-up'),
            ('today', 'Due today'),
            ('this_week', 'Due this week'),
            ('completed', 'No follow-up needed'),
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
    """Filter interactions by priority"""
    title = 'priority'
    parameter_name = 'priority_level'

    def lookups(self, request, model_admin):
        return (
            ('high_urgent', 'High & Urgent'),
            ('medium', 'Medium'),
            ('low', 'Low'),
        )

    def queryset(self, request, queryset):
        if self.value() == 'high_urgent':
            return queryset.filter(priority__in=['high', 'urgent'])
        elif self.value() == 'medium':
            return queryset.filter(priority='medium')
        elif self.value() == 'low':
            return queryset.filter(priority='low')
        return queryset


# Inline Admin for ClientInteraction (to add to your existing ClientProfileAdmin)
class ClientInteractionInline(admin.TabularInline):
    """Inline admin for client interactions"""
    model = ClientInteraction
    extra = 0
    max_num = 5  # Show only 5 most recent in inline
    readonly_fields = ('created_at', 'updated_at', 'get_edit_status')
    fields = (
        'interaction_type', 'interaction_date', 'priority', 
        'notes', 'follow_up_required', 'follow_up_date',
        'created_by', 'get_edit_status'
    )
    
    def get_edit_status(self, obj):
        if obj.pk:
            if timezone.now() - obj.created_at <= timedelta(hours=24):
                return format_html('<span style="color: green;">✓ Editable</span>')
            else:
                return format_html('<span style="color: red;">✗ Read-only</span>')
        return "-"
    get_edit_status.short_description = "Edit Status"

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('created_by').order_by('-interaction_date')


# Main ClientInteraction Admin
@admin.register(ClientInteraction)
class ClientInteractionAdmin(admin.ModelAdmin):
    list_display = [
        'get_client_info', 'interaction_type', 'interaction_date', 
        'priority', 'duration_minutes', 'follow_up_required', 
        'get_follow_up_status', 'created_by', 'get_edit_status'
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
        'created_at', 'updated_at', 'get_time_since_creation',
        'get_edit_status', 'get_client_details', 'get_follow_up_status'
    ]
    
    fieldsets = (
        ('Client & Interaction', {
            'fields': (
                'client_profile',
                'get_client_details',
                ('interaction_type', 'interaction_date'),
                ('duration_minutes', 'priority'),
            )
        }),
        ('Interaction Details', {
            'fields': (
                'notes',
            )
        }),
        ('Follow-up', {
            'fields': (
                ('follow_up_required', 'follow_up_date'),
                'get_follow_up_status',
            )
        }),
        ('Metadata', {
            'fields': (
                ('created_by', 'created_at'),
                ('updated_at', 'get_time_since_creation'),
                'get_edit_status',
            ),
            'classes': ('collapse',)
        }),
    )
    
    date_hierarchy = 'interaction_date'
    ordering = ['-interaction_date', '-created_at']
    actions = ['mark_follow_up_required', 'mark_follow_up_completed', 'change_priority_to_high', 'export_interactions']
    
    def get_queryset(self, request):
        qs = super().get_queryset(request).select_related(
            'client_profile', 'created_by', 'client_profile__mapped_rm'
        )
        
        # Apply the same permission logic as your ClientProfile
        user = request.user
        if user.is_superuser or user.role in ['top_management', 'business_head', 'business_head_ops']:
            return qs
        elif user.role == 'rm_head':
            accessible_users = user.get_accessible_users()
            return qs.filter(client_profile__mapped_rm__in=accessible_users)
        elif user.role == 'rm':
            return qs.filter(client_profile__mapped_rm=user)
        elif user.role in ['ops_team_lead', 'ops_exec']:
            return qs  # Can view all interactions for operational purposes
        else:
            return qs.filter(created_by=user)  # Can only see own interactions
    
    def get_client_info(self, obj):
        """Display client info with link"""
        if obj.client_profile:
            url = reverse('admin:base_clientprofile_change', args=[obj.client_profile.pk])
            return format_html(
                '<a href="{}" title="View client profile"><strong>{}</strong><br><small>{}</small></a>',
                url,
                obj.client_profile.client_full_name,
                obj.client_profile.client_id
            )
        return "-"
    get_client_info.short_description = "Client"
    get_client_info.admin_order_field = 'client_profile__client_full_name'
    
    def get_edit_status(self, obj):
        """Show edit status with detailed info - COMPLETELY FIXED"""
        if obj.pk:
            time_diff = timezone.now() - obj.created_at
            hours_passed = time_diff.total_seconds() / 3600
            
            if hours_passed <= 24:
                remaining_hours = round(24 - hours_passed, 1)
                return format_html(
                    '<span style="color: green;" title="Editable for {} more hours">✓ Editable</span>',
                    remaining_hours
                )
            else:
                expired_hours = round(hours_passed - 24, 1)
                return format_html(
                    '<span style="color: red;" title="Edit window expired {} hours ago">✗ Read-only</span>',
                    expired_hours
                )
        return "-"
    get_edit_status.short_description = "Edit Status"
    
    def get_follow_up_status(self, obj):
        """Show follow-up status with color coding - COMPLETELY FIXED"""
        if not obj.follow_up_required:
            return format_html('<span style="color: green;">No follow-up needed</span>')
        
        if not obj.follow_up_date:
            return format_html('<span style="color: orange;">Follow-up required (no date set)</span>')
        
        today = timezone.now().date()
        days_diff = (obj.follow_up_date - today).days
        
        if days_diff < 0:
            overdue_days = abs(days_diff)
            return format_html(
                '<span style="color: red; font-weight: bold;" title="Overdue by {} days">OVERDUE</span>',
                overdue_days
            )
        elif days_diff == 0:
            return format_html('<span style="color: orange; font-weight: bold;">DUE TODAY</span>')
        elif days_diff <= 7:
            return format_html(
                '<span style="color: blue;" title="Due in {} days">Due in {} days</span>',
                days_diff, days_diff
            )
        else:
            due_date = obj.follow_up_date.strftime('%Y-%m-%d')
            return format_html(
                '<span style="color: gray;" title="Due in {} days">Due {}</span>',
                days_diff, due_date
            )
    get_follow_up_status.short_description = "Follow-up Status"
    
    def get_time_since_creation(self, obj):
        """Get human-readable time since creation"""
        if obj.pk:
            return obj.get_time_since_creation()
        return "-"
    get_time_since_creation.short_description = "Created"
    
    def get_client_details(self, obj):
        """Show detailed client information - COMPLETELY FIXED"""
        if obj.client_profile:
            client = obj.client_profile
            url = reverse('admin:base_clientprofile_change', args=[client.pk])
            
            # Build HTML content with safe formatting
            client_name = client.client_full_name
            client_id = client.client_id
            pan_number = client.pan_number
            email = client.email
            mobile = client.mobile_number
            rm_name = client.mapped_rm or 'Not assigned'
            
            html_template = '''
            <div style="background: #f8f9fa; padding: 10px; border-radius: 5px;">
                <a href="{}" style="text-decoration: none;">
                    <strong>{}</strong> ({})<br>
                    <small>PAN: {} | Email: {}<br>
                    Mobile: {} | RM: {}</small>
                </a>
            </div>
            '''
            
            return format_html(
                html_template,
                url, client_name, client_id, pan_number, email, mobile, rm_name
            )
        return "-"
    get_client_details.short_description = "Client Details"
    
    def save_model(self, request, obj, form, change):
        """Set created_by for new objects"""
        if not change:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)
    
    def has_change_permission(self, request, obj=None):
        """Check if user can change this interaction"""
        if obj is None:
            return super().has_change_permission(request)
        
        user = request.user
        
        # Superuser and top management can always edit
        if user.is_superuser or user.role in ['top_management', 'business_head', 'business_head_ops']:
            return True
        
        # Check if within 24-hour edit window for creator
        if obj.created_by == user:
            return obj.is_editable_by(user)
        
        # RM Head can edit interactions for their team members
        if user.role == 'rm_head':
            return user.can_access_user_data(obj.client_profile.mapped_rm)
        
        # RM can edit their own client interactions (within time limit)
        if user.role == 'rm' and obj.client_profile.mapped_rm == user:
            return obj.is_editable_by(user) if obj.created_by == user else False
        
        return False
    
    def has_delete_permission(self, request, obj=None):
        """Same logic as change permission"""
        return self.has_change_permission(request, obj)
    
    # COMPLETELY FIXED Admin Actions - No f-strings
    @admin.action(description='Mark selected interactions as requiring follow-up')
    def mark_follow_up_required(self, request, queryset):
        """Mark interactions as requiring follow-up"""
        updated = queryset.update(follow_up_required=True)
        message = '{} interactions marked as requiring follow-up.'.format(updated)
        self.message_user(request, message)
    
    @admin.action(description='Mark selected interactions as follow-up completed')
    def mark_follow_up_completed(self, request, queryset):
        """Mark interactions as follow-up completed"""
        updated = queryset.update(follow_up_required=False, follow_up_date=None)
        message = '{} interactions marked as follow-up completed.'.format(updated)
        self.message_user(request, message)
    
    @admin.action(description='Change priority to High for selected interactions')
    def change_priority_to_high(self, request, queryset):
        """Change priority to high"""
        updated = queryset.update(priority='high')
        message = '{} interactions priority changed to High.'.format(updated)
        self.message_user(request, message)
    
    @admin.action(description='Export selected interactions to CSV')
    def export_interactions(self, request, queryset):
        """Export interactions to CSV"""
        import csv
        from django.http import HttpResponse
        
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="client_interactions.csv"'
        
        writer = csv.writer(response)
        writer.writerow([
            'Client Name', 'Client ID', 'PAN', 'Interaction Type', 'Date', 
            'Duration (mins)', 'Priority', 'Notes', 'Follow-up Required', 
            'Follow-up Date', 'Created By', 'Created At'
        ])
        
        for interaction in queryset.select_related('client_profile', 'created_by'):
            # Safe handling of all data
            client_name = interaction.client_profile.client_full_name if interaction.client_profile else ''
            client_id = interaction.client_profile.client_id if interaction.client_profile else ''
            pan_number = interaction.client_profile.pan_number if interaction.client_profile else ''
            interaction_type = interaction.get_interaction_type_display()
            interaction_date = interaction.interaction_date.strftime('%Y-%m-%d %H:%M')
            duration = interaction.duration_minutes or ''
            priority = interaction.get_priority_display()
            notes = interaction.notes
            follow_up_required = 'Yes' if interaction.follow_up_required else 'No'
            follow_up_date = interaction.follow_up_date.strftime('%Y-%m-%d') if interaction.follow_up_date else ''
            created_by = interaction.created_by.get_full_name() if interaction.created_by else ''
            created_at = interaction.created_at.strftime('%Y-%m-%d %H:%M')
            
            writer.writerow([
                client_name, client_id, pan_number, interaction_type, interaction_date,
                duration, priority, notes, follow_up_required, follow_up_date,
                created_by, created_at
            ])
        
        return response
    
    
class StatusFilter(SimpleListFilter):
    """Custom filter for execution plan status"""
    title = 'status'
    parameter_name = 'status'

    def lookups(self, request, model_admin):
        return ExecutionPlan.STATUS_CHOICES

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(status=self.value())
        return queryset


class CreatedByFilter(SimpleListFilter):
    """Filter by creator role"""
    title = 'created by role'
    parameter_name = 'creator_role'

    def lookups(self, request, model_admin):
        return [
            ('rm', 'Relationship Manager'),
            ('rm_head', 'RM Head'),
        ]

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(created_by__role=self.value())
        return queryset


class PlanActionInline(admin.TabularInline):
    """Inline for plan actions"""
    model = PlanAction
    extra = 0
    readonly_fields = ('executed_at', 'transaction_id', 'executed_amount', 'executed_units', 'nav_price')
    fields = (
        'action_type', 'scheme', 'amount', 'units', 'sip_date', 
        'target_scheme', 'priority', 'status', 'executed_by',
        'transaction_id', 'executed_amount', 'executed_units', 'notes'
    )
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('scheme', 'target_scheme', 'executed_by')


class PlanCommentInline(admin.TabularInline):
    """Inline for plan comments"""
    model = PlanComment
    extra = 0
    readonly_fields = ('commented_by', 'created_at')
    fields = ('comment', 'is_internal', 'commented_by', 'created_at')
    
    def save_model(self, request, obj, form, change):
        if not obj.pk:
            obj.commented_by = request.user
        super().save_model(request, obj, form, change)


    
# Register all models
admin.site.register(User, CustomUserAdmin)
admin.site.register(Team, TeamAdmin)
admin.site.register(TeamMembership, TeamMembershipAdmin)

# Notes Systemfrom django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse, path
from django.utils.safestring import mark_safe
from django.db.models import Sum, Count
from django.shortcuts import redirect
from django.contrib import messages
from django.http import HttpResponse
from .models import (
    PortfolioUpload, ClientPortfolio, PortfolioUploadLog, 
    MutualFundScheme
)
import csv

@admin.register(PortfolioUpload)
class PortfolioUploadAdmin(admin.ModelAdmin):
    list_display = [
        'upload_id', 'file_link', 'uploaded_by_link', 'uploaded_at', 
        'status_colored', 'progress_display', 'total_rows', 'successful_rows', 
        'failed_rows', 'log_count', 'actions_column'
    ]
    list_filter = ['status', 'uploaded_at', 'uploaded_by']
    search_fields = ['upload_id', 'file']
    readonly_fields = [
        'upload_id', 'uploaded_at', 'processed_at', 'total_rows',
        'processed_rows', 'successful_rows', 'failed_rows',
        'processing_summary', 'error_details'
    ]
    
    fieldsets = (
        ('Upload Information', {
            'fields': ('upload_id', 'file', 'uploaded_by', 'uploaded_at')
        }),
        ('Processing Status', {
            'fields': ('status', 'processed_at', 'total_rows', 'processed_rows', 
                      'successful_rows', 'failed_rows')
        }),
        ('Details', {
            'fields': ('processing_log', 'processing_summary', 'error_details'),
            'classes': ('collapse',)
        })
    )
    
    actions = ['process_pending_uploads', 'retry_failed_uploads', 'mark_as_pending']
    
    def file_link(self, obj):
        """Display file name with download link"""
        if obj.file:
            return format_html(
                '<a href="{}" target="_blank" title="Download file">{}</a>',
                obj.file.url, obj.file.name.split('/')[-1]
            )
        return "-"
    file_link.short_description = "File"
    
    def uploaded_by_link(self, obj):
        """Link to user who uploaded"""
        if obj.uploaded_by:
            url = reverse('admin:base_user_change', args=[obj.uploaded_by.pk])
            return format_html('<a href="{}">{}</a>', url, obj.uploaded_by.username)
        return '-'
    uploaded_by_link.short_description = 'Uploaded By'
    
    def status_colored(self, obj):
        """Display status with color coding"""
        colors = {
            'pending': '#6c757d',       # Gray
            'processing': '#007bff',    # Blue
            'completed': '#28a745',     # Green
            'failed': '#dc3545',        # Red
            'partial': '#ffc107',       # Yellow
        }
        color = colors.get(obj.status, '#6c757d')
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color, obj.get_status_display()
        )
    status_colored.short_description = 'Status'
    
    def progress_display(self, obj):
        """Display progress bar and statistics"""
        if obj.total_rows > 0:
            success_percentage = (obj.successful_rows / obj.total_rows) * 100
            failed_percentage = (obj.failed_rows / obj.total_rows) * 100
            
            return format_html(
                '<div style="width: 120px; background-color: #f0f0f0; border-radius: 3px; height: 15px; position: relative;">'
                '<div style="width: {}%; background-color: #28a745; height: 15px; border-radius: 3px 0 0 3px; float: left;"></div>'
                '<div style="width: {}%; background-color: #dc3545; height: 15px; border-radius: 0 3px 3px 0; float: left;"></div>'
                '</div>'
                '<small>Success: {} | Failed: {} | Total: {}</small>',
                success_percentage, failed_percentage,
                obj.successful_rows, obj.failed_rows, obj.total_rows
            )
        return "No data"
    progress_display.short_description = "Progress"
    
    def log_count(self, obj):
        """Display log count with link"""
        count = obj.processing_logs.count()
        if count > 0:
            logs_url = reverse('admin:base_portfoliouploadlog_changelist') + f'?upload__id__exact={obj.pk}'
            
            error_count = obj.processing_logs.filter(status='error').count()
            warning_count = obj.processing_logs.filter(status='warning').count()
            
            if error_count > 0:
                style = "color: red; font-weight: bold;"
                icon = "❌"
            elif warning_count > 0:
                style = "color: orange;"
                icon = "⚠️"
            else:
                style = "color: green;"
                icon = "✅"
            
            return format_html(
                '<a href="{}" style="{}">{} {} logs</a>',
                logs_url, style, icon, count
            )
        return "No logs"
    log_count.short_description = "Logs"
    
    def actions_column(self, obj):
        """Action buttons for each upload - FIXED"""
        actions = []
        
        # Process button for pending uploads
        if obj.status == 'pending':
            # Use a form-based approach for better reliability
            actions.append(f'''
                <form method="post" action="" style="display: inline;">
                    <input type="hidden" name="action" value="process_single_upload">
                    <input type="hidden" name="_selected_action" value="{obj.pk}">
                    <input type="hidden" name="csrfmiddlewaretoken" value="{self.get_csrf_token()}">
                    <button type="submit" class="button" style="background: #007bff; color: white; margin: 2px; border: none; padding: 4px 8px; border-radius: 3px;">
                        🚀 Process
                    </button>
                </form>
            ''')
        
        # Retry button for failed uploads
        if obj.status == 'failed':
            actions.append(f'''
                <form method="post" action="" style="display: inline;">
                    <input type="hidden" name="action" value="retry_single_upload">
                    <input type="hidden" name="_selected_action" value="{obj.pk}">
                    <input type="hidden" name="csrfmiddlewaretoken" value="{self.get_csrf_token()}">
                    <button type="submit" class="button" style="background: #ffc107; color: black; margin: 2px; border: none; padding: 4px 8px; border-radius: 3px;">
                        🔄 Retry
                    </button>
                </form>
            ''')
        
        # Logs button (always available if logs exist)
        if obj.processing_logs.exists():
            logs_url = reverse('admin:base_portfoliouploadlog_changelist') + f'?upload__id__exact={obj.pk}'
            actions.append(f'''
                <a href="{logs_url}" class="button" style="background: #6c757d; color: white; margin: 2px; text-decoration: none; padding: 4px 8px; border-radius: 3px; display: inline-block;">
                    📋 Logs ({obj.processing_logs.count()})
                </a>
            ''')
        
        # Portfolios button for successful uploads
        if obj.status in ['completed', 'partial'] and obj.portfolio_entries.exists():
            portfolios_url = reverse('admin:base_clientportfolio_changelist') + f'?upload_batch__id__exact={obj.pk}'
            actions.append(f'''
                <a href="{portfolios_url}" class="button" style="background: #28a745; color: white; margin: 2px; text-decoration: none; padding: 4px 8px; border-radius: 3px; display: inline-block;">
                    📊 Portfolios ({obj.portfolio_entries.count()})
                </a>
            ''')
        
        # Mapping button for uploads with unmapped portfolios
        if obj.status in ['completed', 'partial']:
            unmapped_count = obj.portfolio_entries.filter(is_mapped=False).count()
            if unmapped_count > 0:
                actions.append(f'''
                    <form method="post" action="" style="display: inline;">
                        <input type="hidden" name="action" value="remap_single_upload">
                        <input type="hidden" name="_selected_action" value="{obj.pk}">
                        <input type="hidden" name="csrfmiddlewaretoken" value="{self.get_csrf_token()}">
                        <button type="submit" class="button" style="background: #17a2b8; color: white; margin: 2px; border: none; padding: 4px 8px; border-radius: 3px;">
                            🔗 Map ({unmapped_count})
                        </button>
                    </form>
                ''')
        
        return format_html(''.join(actions))
    actions_column.short_description = "Actions"
    
    def get_csrf_token(self):
        """Helper method to get CSRF token for forms"""
        # This is a placeholder - in the actual implementation, you'd get this from the request
        # For now, we'll use Django's get_token function
        from django.middleware.csrf import get_token
        from django.http import HttpRequest
        
        # Create a dummy request to get CSRF token
        # In the actual admin, this would come from the current request
        request = HttpRequest()
        return get_token(request)
    
    # Admin Actions - These handle the form submissions
    def process_single_upload(self, request, queryset):
        """Process a single upload"""
        for upload in queryset:
            if upload.status == 'pending':
                try:
                    # Here you would call your processing method
                    # upload.process_upload_with_logging()
                    upload.status = 'processing'
                    upload.save()
                    self.message_user(
                        request,
                        f"✅ Upload {upload.upload_id} processing started!",
                        level=messages.SUCCESS
                    )
                except Exception as e:
                    self.message_user(
                        request,
                        f"❌ Error processing {upload.upload_id}: {str(e)}",
                        level=messages.ERROR
                    )
    process_single_upload.short_description = "Process upload"
    
    def retry_single_upload(self, request, queryset):
        """Retry a failed upload"""
        for upload in queryset:
            if upload.status == 'failed':
                try:
                    upload.status = 'pending'
                    upload.processed_rows = 0
                    upload.successful_rows = 0
                    upload.failed_rows = 0
                    upload.save()
                    
                    self.message_user(
                        request,
                        f"✅ Upload {upload.upload_id} marked for retry!",
                        level=messages.SUCCESS
                    )
                except Exception as e:
                    self.message_user(
                        request,
                        f"❌ Error retrying {upload.upload_id}: {str(e)}",
                        level=messages.ERROR
                    )
    retry_single_upload.short_description = "Retry upload"
    
    def remap_single_upload(self, request, queryset):
        """Re-attempt client mapping for an upload"""
        for upload in queryset:
            try:
                mapped_count = 0
                unmapped_portfolios = upload.portfolio_entries.filter(is_mapped=False)
                
                for portfolio in unmapped_portfolios:
                    # Here you would call the mapping method
                    # mapped, message = portfolio.map_to_client_profile()
                    # if mapped:
                    #     mapped_count += 1
                    pass
                
                self.message_user(
                    request,
                    f"🔗 Client mapping attempted for upload {upload.upload_id}",
                    level=messages.SUCCESS
                )
            except Exception as e:
                self.message_user(
                    request,
                    f"❌ Error mapping {upload.upload_id}: {str(e)}",
                    level=messages.ERROR
                )
    remap_single_upload.short_description = "Remap clients"
    
    # Bulk actions for selected items
    def process_pending_uploads(self, request, queryset):
        """Process selected pending uploads"""
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
    process_pending_uploads.short_description = "Process selected pending uploads"
    
    def retry_failed_uploads(self, request, queryset):
        """Retry selected failed uploads"""
        failed_uploads = queryset.filter(status='failed')
        updated = failed_uploads.update(status='pending')
        
        if updated > 0:
            self.message_user(
                request,
                f"✅ Marked {updated} failed uploads for retry",
                level=messages.SUCCESS
            )
    retry_failed_uploads.short_description = "Retry selected failed uploads"
    
    def mark_as_pending(self, request, queryset):
        """Mark uploads as pending for reprocessing"""
        updated = queryset.update(status='pending')
        self.message_user(
            request,
            f"✅ Marked {updated} uploads as pending for reprocessing",
            level=messages.SUCCESS
        )
    mark_as_pending.short_description = "Mark as pending for reprocessing"
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('uploaded_by').prefetch_related('processing_logs')
    
    def get_actions(self, request):
        """Override to include our custom single-item actions"""
        actions = super().get_actions(request)
        
        # Add our custom actions
        actions['process_single_upload'] = (
            self.process_single_upload,
            'process_single_upload',
            self.process_single_upload.short_description
        )
        actions['retry_single_upload'] = (
            self.retry_single_upload,
            'retry_single_upload', 
            self.retry_single_upload.short_description
        )
        actions['remap_single_upload'] = (
            self.remap_single_upload,
            'remap_single_upload',
            self.remap_single_upload.short_description
        )
        
        return actions

@admin.register(PortfolioUploadLog)
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


# Enhanced ClientPortfolio Admin
@admin.register(ClientPortfolio)
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

@admin.register(MutualFundScheme)
class MutualFundSchemeAdmin(admin.ModelAdmin):
    list_display = [
        'scheme_name', 'amc_name', 'scheme_type', 'primary_asset_class',
        'risk_category', 'is_active', 'portfolio_count'
    ]
    list_filter = ['scheme_type', 'primary_asset_class', 'risk_category', 'is_active', 'amc_name']
    search_fields = ['scheme_name', 'amc_name', 'scheme_code', 'isin_number']
    readonly_fields = ['created_at', 'updated_at', 'portfolio_count']
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('scheme_name', 'amc_name', 'scheme_code', 'isin_number')
        }),
        ('Classification', {
            'fields': ('scheme_type', 'primary_asset_class', 'risk_category')
        }),
        ('Investment Limits', {
            'fields': ('minimum_investment', 'minimum_sip')
        }),
        ('Status & NAV', {
            'fields': ('is_active', 'last_nav_date', 'last_nav_price')
        }),
        ('Metadata', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )
    
    def portfolio_count(self, obj):
        return ClientPortfolio.objects.filter(scheme_name=obj.scheme_name).count()
    portfolio_count.short_description = "Portfolio Entries"
    
admin.site.register(NoteList, NoteListAdmin)
admin.site.register(Note, NoteAdmin)

# Client Management
admin.site.register(ClientProfile, ClientProfileAdmin)
admin.site.register(MFUCANAccount, MFUCANAccountAdmin)
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

# Business Analytics
admin.site.register(BusinessTracker, BusinessTrackerAdmin)

# Unregister default Group admin and register custom one
admin.site.unregister(Group)
admin.site.register(Group, CustomGroupAdmin)
from django.contrib.auth import get_user_model
# For the User model:
User = get_user_model()
user_change_url = f'admin:{User._meta.app_label}_{User._meta.model_name}_change'


# Customize admin site headers
admin.site.site_header = "CRM Administration"
admin.site.site_title = "CRM Admin"
admin.site.index_title = "Welcome to CRM Administration"

from django.db.models.signals import post_save
from django.dispatch import receiver
from threading import Thread
import logging

logger = logging.getLogger(__name__)

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
            message=f"Upload {instance.upload_id} created and queued for automatic processing"
        )
        
        # Process in background thread to avoid blocking the request
        def process_in_background():
            try:
                instance.process_upload_with_logging()
            except Exception as e:
                logger.error(f"Auto-processing failed for {instance.upload_id}: {e}")
                instance.create_log(
                    row_number=0,
                    status='error',
                    message=f"Auto-processing failed: {str(e)}"
                )
        
        # Start background processing
        thread = Thread(target=process_in_background)
        thread.daemon = True
        thread.start()