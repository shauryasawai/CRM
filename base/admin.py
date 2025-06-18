from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import Group
from django.utils.html import format_html
from django.urls import reverse
from django.db.models import Count, Sum
from .models import (
    User, Team, TeamMembership, Lead, LeadInteraction, ProductDiscussion, 
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
        'role', 'manager_link', 'team_info', 'is_active', 'date_joined'
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
        if obj.role == 'rm_head':
            team_count = obj.get_team_members().count()
            managed_teams = obj.led_teams.all()
            team_names = ', '.join([team.name for team in managed_teams])
            return f"{team_count} members | Teams: {team_names}" if team_names else f"{team_count} members"
        elif obj.role == 'rm':
            teams = obj.teams.all()
            return ', '.join([team.name for team in teams]) if teams else 'No team'
        return '-'
    team_info.short_description = 'Team Info'

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('manager').prefetch_related('teams', 'led_teams', 'managed_groups')


class TeamMembershipAdmin(admin.ModelAdmin):
    list_display = ('user', 'team', 'date_joined', 'is_active')
    list_filter = ('is_active', 'date_joined', 'team')
    search_fields = ('user__username', 'team__name')
    autocomplete_fields = ('user', 'team')


class TeamAdmin(admin.ModelAdmin):
    list_display = ('name', 'leader_link', 'member_count', 'created_at')
    list_filter = ('created_at', 'leader')
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
        'assigned_to', 'probability', 'created_at', 'converted'
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
                'converted', 'converted_by'
            )
        }),
        ('Additional Info', {
            'fields': ('notes',)
        }),
    )
    autocomplete_fields = (
        'assigned_to', 'created_by', 'reference_client', 'converted_by', 'reassignment_requested_to'
    )
    inlines = [LeadInteractionInline, ProductDiscussionInline, LeadStatusChangeInline]
    actions = ['mark_as_converted', 'mark_as_hot', 'assign_to_me']
    
    def mark_as_converted(self, request, queryset):
        updated = queryset.update(converted=True, status='converted')
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
            'assigned_to', 'created_by', 'converted_by', 'reference_client'
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
        'demat_count', 'lead_link', 'created_at'
    )
    list_filter = ('created_at', 'user__role', 'demat_count')
    search_fields = ('name', 'contact_info', 'user__username', 'lead__lead_id')
    ordering = ('-aum', '-created_at')
    autocomplete_fields = ('user', 'lead')
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

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('user', 'lead')


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
        from django.utils import timezone
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
        from django.utils import timezone
        updated = queryset.update(status='resolved', resolved_at=timezone.now())
        self.message_user(request, f"{updated} service requests marked as resolved")
    mark_as_resolved.short_description = "Mark selected requests as resolved"

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('client', 'raised_by', 'assigned_to')


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


# Register models
admin.site.register(User, CustomUserAdmin)
admin.site.register(Team, TeamAdmin)
admin.site.register(TeamMembership, TeamMembershipAdmin)
admin.site.register(Lead, LeadAdmin)
admin.site.register(LeadInteraction, LeadInteractionAdmin)
admin.site.register(ProductDiscussion, ProductDiscussionAdmin)
admin.site.register(LeadStatusChange, LeadStatusChangeAdmin)
admin.site.register(Client, ClientAdmin)
admin.site.register(Task, TaskAdmin)
admin.site.register(Reminder, ReminderAdmin)
admin.site.register(ServiceRequest, ServiceRequestAdmin)
admin.site.register(InvestmentPlanReview, InvestmentPlanReviewAdmin)
admin.site.register(BusinessTracker, BusinessTrackerAdmin)

# Unregister default Group admin and register custom one
admin.site.unregister(Group)
admin.site.register(Group, CustomGroupAdmin)

# Customize admin site headers
admin.site.site_header = "CRM Administration"
admin.site.site_title = "CRM Admin"
admin.site.index_title = "Welcome to CRM Administration"