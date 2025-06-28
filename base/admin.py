from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import Group
from django.utils.html import format_html
from django.urls import reverse
from django.db.models import Count, Sum, Q
from django.utils import timezone
from .models import (
    User, Team, TeamMembership, NoteList, Note,
    ClientProfile, MFUCANAccount, MotilalDematAccount, PrabhudasDematAccount,
    ClientProfileModification, Lead, LeadInteraction, ProductDiscussion, 
    LeadStatusChange, Client, Task, Reminder, ServiceRequest, 
    BusinessTracker, InvestmentPlanReview
)
from django.contrib.auth.forms import UserChangeForm, UserCreationForm


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


class MotilalDematAccountInline(admin.TabularInline):
    model = MotilalDematAccount
    extra = 0
    fields = ('account_number', 'broker_name', 'dp_id', 'trading_enabled', 'kyc_status', 'is_primary')


class PrabhudasDematAccountInline(admin.TabularInline):
    model = PrabhudasDematAccount
    extra = 0
    fields = ('account_number', 'broker_name', 'dp_id', 'commodity_enabled', 'currency_enabled', 'kyc_status', 'is_primary')


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
        MFUCANAccountInline, MotilalDematAccountInline, 
        PrabhudasDematAccountInline, ClientProfileModificationInline
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


class MotilalDematAccountAdmin(admin.ModelAdmin):
    list_display = ('account_number', 'client_link', 'broker_name', 'dp_id', 'trading_enabled', 'kyc_status', 'is_primary')
    list_filter = ('kyc_status', 'is_primary', 'trading_enabled', 'margin_enabled', 'created_at')
    search_fields = ('account_number', 'dp_id', 'client__client_full_name', 'broker_name')
    autocomplete_fields = ('client',)
    
    def client_link(self, obj):
        url = reverse('admin:base_clientprofile_change', args=[obj.client.pk])
        return format_html('<a href="{}">{}</a>', url, obj.client.client_full_name)
    client_link.short_description = 'Client'


class PrabhudasDematAccountAdmin(admin.ModelAdmin):
    list_display = ('account_number', 'client_link', 'broker_name', 'dp_id', 'commodity_enabled', 'currency_enabled', 'kyc_status', 'is_primary')
    list_filter = ('kyc_status', 'is_primary', 'commodity_enabled', 'currency_enabled', 'created_at')
    search_fields = ('account_number', 'dp_id', 'client__client_full_name', 'broker_name')
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


# Legacy Client Admin (for backward compatibility)
class InvestmentPlanReviewInline(admin.TabularInline):
    model = InvestmentPlanReview
    extra = 0
    fields = ('goal', 'principal_amount', 'monthly_investment', 'tenure_years', 'expected_return_rate')


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
    inlines = [InvestmentPlanReviewInline, ServiceRequestInline]
    
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


class ServiceRequestAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'client_link', 'status', 'priority', 
        'raised_by_link', 'assigned_to_link', 'created_at'
    )
    list_filter = ('status', 'priority', 'created_at')
    search_fields = ('description', 'client__name', 'raised_by__username')
    ordering = ('-created_at',)
    autocomplete_fields = ('client', 'raised_by', 'assigned_to')
    date_hierarchy = 'created_at'
    actions = ['mark_as_resolved']
    
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
    
    def mark_as_resolved(self, request, queryset):
        updated = queryset.update(status='resolved', resolved_at=timezone.now())
        self.message_user(request, f"{updated} service requests marked as resolved")
    mark_as_resolved.short_description = "Mark selected requests as resolved"

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('client', 'raised_by', 'assigned_to')


# Business Tracking and Analytics Admin Classes
class InvestmentPlanReviewAdmin(admin.ModelAdmin):
    list_display = (
        'goal', 'client_link', 'created_by_link', 'principal_amount_display', 
        'monthly_investment_display', 'tenure_years', 'expected_return_rate', 
        'projected_return', 'created_at'
    )
    list_filter = ('tenure_years', 'created_at', 'expected_return_rate')
    search_fields = ('goal', 'client__name', 'created_by__username')
    ordering = ('-created_at',)
    autocomplete_fields = ('client', 'created_by')
    date_hierarchy = 'created_at'
    
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
    
    def principal_amount_display(self, obj):
        return f"₹{obj.principal_amount:,.2f}"
    principal_amount_display.short_description = 'Principal'
    
    def monthly_investment_display(self, obj):
        return f"₹{obj.monthly_investment:,.2f}"
    monthly_investment_display.short_description = 'Monthly SIP'
    
    def projected_return(self, obj):
        return f"₹{obj.projected_value():,.2f}"
    projected_return.short_description = 'Projected Value'

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('client', 'created_by')


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


# Register all models
admin.site.register(User, CustomUserAdmin)
admin.site.register(Team, TeamAdmin)
admin.site.register(TeamMembership, TeamMembershipAdmin)

# Notes System
admin.site.register(NoteList, NoteListAdmin)
admin.site.register(Note, NoteAdmin)

# Client Management
admin.site.register(ClientProfile, ClientProfileAdmin)
admin.site.register(MFUCANAccount, MFUCANAccountAdmin)
admin.site.register(MotilalDematAccount, MotilalDematAccountAdmin)
admin.site.register(PrabhudasDematAccount, PrabhudasDematAccountAdmin)
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
admin.site.register(InvestmentPlanReview, InvestmentPlanReviewAdmin)
admin.site.register(BusinessTracker, BusinessTrackerAdmin)

# Unregister default Group admin and register custom one
admin.site.unregister(Group)
admin.site.register(Group, CustomGroupAdmin)

# Customize admin site headers
admin.site.site_header = "CRM Administration"
admin.site.site_title = "CRM Admin"
admin.site.index_title = "Welcome to CRM Administration"