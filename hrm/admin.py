from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.utils.html import format_html
from django.urls import reverse
from django.utils import timezone
from django.utils.timesince import timesince
from django.db.models import Q
import calendar

# Import CRM User model and HRM models
from base.models import User
from .models import (
    Employee, LeaveRequest, LeaveType, Attendance, 
    Notification, Department, Holiday, LeaveQuota,
    ReimbursementClaim, ReimbursementExpense
)

class EmployeeInline(admin.StackedInline):
    """Enhanced employee inline with CRM integration"""
    model = Employee
    can_delete = False
    verbose_name_plural = 'Employee Profile'
    fk_name = 'user'
    fieldsets = (
        ('Basic Information', {
            'fields': (
                'employee_id', 'designation', 'department', 
                'date_of_joining'
            )
        }),
        ('Contact & Location', {
            'fields': (
                'phone_number', 'emergency_contact', 'address', 'office_location'
            ),
            'classes': ('collapse',)
        }),
        ('Leave Management', {
            'fields': ('leave_balance',),
            'classes': ('collapse',)
        }),
        ('System Fields', {
            'fields': ('hierarchy_level',),
            'classes': ('collapse',)
        }),
    )
    readonly_fields = ('employee_id', 'hierarchy_level')

class EnhancedUserAdmin(UserAdmin):
    """Enhanced User admin with CRM integration"""
    inlines = (EmployeeInline,)
    list_display = (
        'username', 'email', 'first_name', 'last_name', 
        'get_role_display', 'get_designation', 'get_department',
        'get_manager', 'is_staff'
    )
    list_select_related = ('employee_profile',)
    list_filter = (
        'employee_profile__department', 
        'role',  # CRM role filter
        'is_staff', 
        'is_superuser'
    )
    search_fields = (
        'username', 'email', 'first_name', 'last_name', 
        'employee_profile__employee_id', 'employee_profile__designation'
    )
    
    # Add CRM role to fieldsets
    fieldsets = UserAdmin.fieldsets + (
        ('CRM Information', {
            'fields': ('role', 'manager'),
            'classes': ('collapse',)
        }),
    )

    def get_designation(self, instance):
        if hasattr(instance, 'employee_profile'):
            return instance.employee_profile.designation
        return '-'
    get_designation.short_description = 'Designation'

    def get_department(self, instance):
        if hasattr(instance, 'employee_profile') and instance.employee_profile.department:
            return instance.employee_profile.department.name
        return '-'
    get_department.short_description = 'Department'

    def get_manager(self, instance):
        if instance.manager:
            try:
                url = reverse('admin:base_user_change', args=[instance.manager.id])
                return format_html('<a href="{}">{}</a>', url, instance.manager.get_full_name())
            except:
                return instance.manager.get_full_name()
        return '-'
    get_manager.short_description = 'Manager (CRM)'
    get_manager.admin_order_field = 'manager__last_name'

    def get_inline_instances(self, request, obj=None):
        if not obj:
            return list()
        return super().get_inline_instances(request, obj)

# Register enhanced User admin only if using CRM User model
if admin.site.is_registered(User):
    admin.site.unregister(User)
admin.site.register(User, EnhancedUserAdmin)

class DepartmentAdmin(admin.ModelAdmin):
    """Enhanced department admin with CRM team integration"""
    list_display = ('name', 'head_link', 'team_link', 'employee_count')
    list_filter = ('team__is_ops_team',)
    search_fields = ('name', 'description')
    
    def head_link(self, obj):
        if obj.head:
            try:
                url = reverse('admin:base_user_change', args=[obj.head.id])
                return format_html('<a href="{}">{}</a>', url, obj.head.get_full_name())
            except:
                return obj.head.get_full_name()
        return '-'
    head_link.short_description = 'Department Head'
    
    def team_link(self, obj):
        if obj.team:
            try:
                # Assuming you have team admin in CRM
                url = reverse('admin:base_team_change', args=[obj.team.id])
                return format_html('<a href="{}">{}</a>', url, obj.team.name)
            except:
                return obj.team.name
        return '-'
    team_link.short_description = 'CRM Team'
    
    def employee_count(self, obj):
        return obj.employees.count()
    employee_count.short_description = 'Total Employees'

class LeaveTypeAdmin(admin.ModelAdmin):
    """Basic leave type admin matching actual model fields"""
    list_display = ('name', 'max_days', 'description_short')
    search_fields = ('name', 'description')
    
    def description_short(self, obj):
        return obj.description[:50] + '...' if obj.description else '-'
    description_short.short_description = 'Description'

class LeaveRequestAdmin(admin.ModelAdmin):
    """Enhanced leave request admin with CRM integration"""
    list_display = (
        'employee_link', 'leave_type', 'date_range', 
        'total_days', 'status_badge', 'applied_on',
        'processed_by_link', 'manager_comments_short'
    )
    list_filter = (
        'status', 'leave_type', 'employee__department',
        'employee__user__role',  # CRM role filter
        ('applied_on', admin.DateFieldListFilter)
    )
    search_fields = (
        'employee__user__first_name', 'employee__user__last_name',
        'employee__employee_id'
    )
    date_hierarchy = 'applied_on'
    readonly_fields = ('total_days', 'applied_on')
    
    fieldsets = (
        ('Request Information', {
            'fields': ('employee', 'leave_type')
        }),
        ('Leave Details', {
            'fields': (
                'start_date', 'end_date', 'total_days',
                'reason'
            )
        }),
        ('Approval Workflow', {
            'fields': (
                'status', 'processed_by', 'processed_on', 'manager_comments'
            ),
            'classes': ('collapse',)
        }),
        ('Cancellation', {
            'fields': ('cancellation_reason',),
            'classes': ('collapse',)
        }),
    )
    actions = ['approve_selected', 'reject_selected']

    def employee_link(self, obj):
        try:
            url = reverse('admin:base_user_change', args=[obj.employee.user.id])
            return format_html('<a href="{}">{}</a>', url, obj.employee.user.get_full_name())
        except:
            return obj.employee.user.get_full_name()
    employee_link.short_description = 'Employee'
    employee_link.admin_order_field = 'employee__user__last_name'

    def processed_by_link(self, obj):
        if obj.processed_by:
            try:
                url = reverse('admin:base_user_change', args=[obj.processed_by.user.id])
                return format_html('<a href="{}">{}</a>', url, obj.processed_by.user.get_full_name())
            except:
                return obj.processed_by.user.get_full_name()
        return '-'
    processed_by_link.short_description = 'Processed By'

    def date_range(self, obj):
        return f"{obj.start_date.strftime('%b %d')} - {obj.end_date.strftime('%b %d, %Y')}"
    date_range.short_description = 'Date Range'
    date_range.admin_order_field = 'start_date'

    def status_badge(self, obj):
        colors = {
            'P': 'warning',
            'A': 'success',
            'R': 'danger',
            'C': 'secondary',
            'CR': 'info'
        }
        return format_html(
            '<span class="badge bg-{}">{}</span>',
            colors.get(obj.status, 'secondary'),
            obj.get_status_display()
        )
    status_badge.short_description = 'Status'
    status_badge.admin_order_field = 'status'

    def manager_comments_short(self, obj):
        return obj.manager_comments[:30] + '...' if obj.manager_comments else '-'
    manager_comments_short.short_description = 'Comments'

    def approve_selected(self, request, queryset):
        if not hasattr(request.user, 'employee_profile'):
            self.message_user(request, "Only employees can approve leaves.", level='error')
            return
        updated = queryset.filter(status='P').update(status='A', processed_by=request.user.employee_profile)
        self.message_user(request, f"{updated} leave requests approved.")
    approve_selected.short_description = "Approve selected pending leaves"

    def reject_selected(self, request, queryset):
        if not hasattr(request.user, 'employee_profile'):
            self.message_user(request, "Only employees can reject leaves.", level='error')
            return
        updated = queryset.filter(status='P').update(status='R', processed_by=request.user.employee_profile)
        self.message_user(request, f"{updated} leave requests rejected.")
    reject_selected.short_description = "Reject selected pending leaves"

class AttendanceAdmin(admin.ModelAdmin):
    """Enhanced attendance admin"""
    list_display = (
        'employee_link', 'date', 'login_time', 
        'logout_time', 'duration', 'status_badges'
    )
    list_filter = (
        'is_late', 'is_remote', 'employee__department',
        ('date', admin.DateFieldListFilter)
    )
    search_fields = (
        'employee__user__first_name', 'employee__user__last_name',
        'employee__employee_id'
    )
    date_hierarchy = 'date'
    readonly_fields = ('total_hours_display',)
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('employee', 'date')
        }),
        ('Time Tracking', {
            'fields': ('login_time', 'logout_time', 'total_hours_display')
        }),
        ('Location & Work Mode', {
            'fields': ('login_location', 'logout_location', 'is_remote')
        }),
        ('Status Flags', {
            'fields': ('is_late', 'notes')
        }),
    )

    def employee_link(self, obj):
        try:
            url = reverse('admin:base_user_change', args=[obj.employee.user.id])
            return format_html('<a href="{}">{}</a>', url, obj.employee.user.get_full_name())
        except:
            return obj.employee.user.get_full_name()
    employee_link.short_description = 'Employee'
    employee_link.admin_order_field = 'employee__user__last_name'

    def duration(self, obj):
        total_hours = obj.total_hours
        if total_hours:
            hours = int(total_hours)
            minutes = int((total_hours - hours) * 60)
            return f"{hours}h {minutes}m"
        return '-'
    duration.short_description = 'Duration'

    def status_badges(self, obj):
        badges = []
        if obj.is_remote:
            badges.append('<span class="badge bg-warning">Remote</span>')
        if obj.is_late:
            badges.append('<span class="badge bg-danger">Late</span>')
        if not obj.login_time:
            badges.append('<span class="badge bg-secondary">Absent</span>')
        return format_html(' '.join(badges)) if badges else '-'
    status_badges.short_description = 'Status'

    def total_hours_display(self, obj):
        return self.duration(obj)
    total_hours_display.short_description = 'Total Hours'

class ReimbursementExpenseInline(admin.TabularInline):
    """Expense inline"""
    model = ReimbursementExpense
    extra = 1
    fields = ('expense_type', 'expense_date', 'description', 'amount', 'receipt')
    readonly_fields = ('receipt_preview',)

    def receipt_preview(self, obj):
        if obj.receipt:
            return format_html('<a href="{}" target="_blank">View Receipt</a>', obj.receipt.url)
        return '-'
    receipt_preview.short_description = 'Receipt'

class ReimbursementClaimAdmin(admin.ModelAdmin):
    """Enhanced reimbursement claim admin"""
    list_display = (
        'employee_link', 'period', 'total_amount', 
        'status_badge', 'submitted_on', 'manager_link'
    )
    list_filter = (
        'status', 'month', 'year', 'employee__department'
    )
    search_fields = (
        'employee__user__first_name', 'employee__user__last_name',
        'employee__employee_id'
    )
    date_hierarchy = 'submitted_on'
    readonly_fields = ('total_amount',)
    inlines = [ReimbursementExpenseInline]
    actions = ['approve_selected', 'reject_selected']
    
    fieldsets = (
        ('Claim Information', {
            'fields': ('employee', 'month', 'year')
        }),
        ('Financial Details', {
            'fields': ('total_amount', 'status')
        }),
        ('Manager Approval', {
            'fields': (
                'manager_approved_by', 'manager_approved_on', 'manager_comments'
            ),
            'classes': ('collapse',)
        }),
        ('Final Approval', {
            'fields': (
                'final_approved_by', 'final_approved_on', 'final_comments'
            ),
            'classes': ('collapse',)
        }),
    )

    def employee_link(self, obj):
        try:
            url = reverse('admin:base_user_change', args=[obj.employee.user.id])
            return format_html('<a href="{}">{}</a>', url, obj.employee.user.get_full_name())
        except:
            return obj.employee.user.get_full_name()
    employee_link.short_description = 'Employee'
    employee_link.admin_order_field = 'employee__user__last_name'

    def manager_link(self, obj):
        manager = obj.final_approved_by or obj.manager_approved_by
        if manager:
            try:
                url = reverse('admin:base_user_change', args=[manager.user.id])
                return format_html('<a href="{}">{}</a>', url, manager.user.get_full_name())
            except:
                return manager.user.get_full_name()
        return '-'
    manager_link.short_description = 'Approved By'

    def period(self, obj):
        return f"{calendar.month_name[obj.month]} {obj.year}"
    period.short_description = 'Period'
    period.admin_order_field = 'year'

    def status_badge(self, obj):
        colors = {
            'D': 'secondary',
            'P': 'warning',
            'MA': 'info',
            'A': 'success',
            'R': 'danger'
        }
        return format_html(
            '<span class="badge bg-{}">{}</span>',
            colors.get(obj.status, 'secondary'),
            obj.get_status_display()
        )
    status_badge.short_description = 'Status'
    status_badge.admin_order_field = 'status'

    def approve_selected(self, request, queryset):
        if not hasattr(request.user, 'employee_profile'):
            self.message_user(request, "Only employees can approve claims.", level='error')
            return
        
        updated = queryset.filter(status='P').update(
            status='MA',
            manager_approved_by=request.user.employee_profile,
            manager_approved_on=timezone.now()
        )
        self.message_user(request, f"{updated} claims approved by manager.")
    approve_selected.short_description = "Approve selected pending claims"

    def reject_selected(self, request, queryset):
        if not hasattr(request.user, 'employee_profile'):
            self.message_user(request, "Only employees can reject claims.", level='error')
            return
        
        updated = queryset.filter(status='P').update(
            status='R',
            manager_approved_by=request.user.employee_profile,
            manager_approved_on=timezone.now()
        )
        self.message_user(request, f"{updated} claims rejected.")
    reject_selected.short_description = "Reject selected pending claims"

class HolidayAdmin(admin.ModelAdmin):
    """Basic holiday admin"""
    list_display = ('name', 'date', 'is_past', 'days_until')
    list_filter = (('date', admin.DateFieldListFilter),)
    search_fields = ('name', 'description')
    date_hierarchy = 'date'
    ordering = ('date',)

    def is_past(self, obj):
        return obj.date < timezone.now().date()
    is_past.boolean = True
    is_past.short_description = 'Past?'

    def days_until(self, obj):
        delta = obj.date - timezone.now().date()
        if delta.days > 0:
            return f"In {delta.days} days"
        elif delta.days == 0:
            return "Today"
        else:
            return f"{abs(delta.days)} days ago"
    days_until.short_description = 'When'

class LeaveQuotaAdmin(admin.ModelAdmin):
    """Enhanced leave quota admin using CRM roles"""
    list_display = ('get_role_display', 'leave_type', 'quota')
    list_filter = ('hierarchy_level', 'leave_type')
    search_fields = ('leave_type__name',)
    
    def get_role_display(self, obj):
        # Use CRM role choices for display
        from base.models import ROLE_CHOICES
        role_dict = dict(ROLE_CHOICES)
        return role_dict.get(obj.hierarchy_level, obj.hierarchy_level)
    get_role_display.short_description = 'Role'
    get_role_display.admin_order_field = 'hierarchy_level'

class NotificationAdmin(admin.ModelAdmin):
    """Basic notification admin"""
    list_display = (
        'recipient_link', 'message_short', 'is_read', 'created_ago'
    )
    list_filter = ('is_read', 'recipient__department')
    search_fields = (
        'recipient__user__first_name', 'recipient__user__last_name',
        'message'
    )
    date_hierarchy = 'created_at'
    readonly_fields = ('created_at',)
    actions = ['mark_as_read', 'mark_as_unread']

    def recipient_link(self, obj):
        try:
            url = reverse('admin:base_user_change', args=[obj.recipient.user.id])
            return format_html('<a href="{}">{}</a>', url, obj.recipient.user.get_full_name())
        except:
            return obj.recipient.user.get_full_name()
    recipient_link.short_description = 'Recipient'
    recipient_link.admin_order_field = 'recipient__user__last_name'

    def message_short(self, obj):
        return obj.message[:50] + '...' if len(obj.message) > 50 else obj.message
    message_short.short_description = 'Message'

    def created_ago(self, obj):
        return timesince(obj.created_at)
    created_ago.short_description = 'Created'

    def mark_as_read(self, request, queryset):
        updated = queryset.update(is_read=True)
        self.message_user(request, f"{updated} notifications marked as read.")
    mark_as_read.short_description = "Mark selected as read"

    def mark_as_unread(self, request, queryset):
        updated = queryset.update(is_read=False)
        self.message_user(request, f"{updated} notifications marked as unread.")
    mark_as_unread.short_description = "Mark selected as unread"

class EmployeeAdmin(admin.ModelAdmin):
    """Basic employee admin"""
    list_display = (
        'employee_id', 'user_link', 'designation', 'department',
        'hierarchy_level_display', 'leave_balance'
    )
    list_filter = (
        'department', 'user__role', 'hierarchy_level'
    )
    search_fields = (
        'employee_id', 'user__first_name', 'user__last_name',
        'user__username', 'designation'
    )
    readonly_fields = ('employee_id', 'hierarchy_level', 'created_at', 'updated_at')
    
    fieldsets = (
        ('User Account', {
            'fields': ('user',)
        }),
        ('Employment Details', {
            'fields': (
                'employee_id', 'designation', 'department',
                'date_of_joining', 'hierarchy_level'
            )
        }),
        ('Contact Information', {
            'fields': (
                'phone_number', 'emergency_contact', 'address', 'office_location'
            )
        }),
        ('Leave Management', {
            'fields': ('leave_balance',)
        }),
        ('System Information', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def user_link(self, obj):
        try:
            url = reverse('admin:base_user_change', args=[obj.user.id])
            return format_html('<a href="{}">{}</a>', url, obj.user.get_full_name())
        except:
            return obj.user.get_full_name()
    user_link.short_description = 'User Account'
    user_link.admin_order_field = 'user__last_name'

    def hierarchy_level_display(self, obj):
        return obj.get_hierarchy_level_display()
    hierarchy_level_display.short_description = 'Role'

class ReimbursementExpenseAdmin(admin.ModelAdmin):
    """Standalone expense admin"""
    list_display = (
        'claim_link', 'expense_type', 'expense_date', 'amount', 'has_receipt'
    )
    list_filter = (
        'expense_type', 'claim__status',
        ('expense_date', admin.DateFieldListFilter)
    )
    search_fields = (
        'description', 'claim__employee__user__first_name', 'claim__employee__user__last_name'
    )
    date_hierarchy = 'expense_date'
    
    def claim_link(self, obj):
        try:
            url = reverse('admin:hrm_reimbursementclaim_change', args=[obj.claim.id])
            return format_html('<a href="{}">{}</a>', 
                             url, f"{obj.claim.employee.user.get_full_name()} - {obj.claim.month}/{obj.claim.year}")
        except:
            return f"{obj.claim.employee.user.get_full_name()} - {obj.claim.month}/{obj.claim.year}"
    claim_link.short_description = 'Claim'

    def has_receipt(self, obj):
        return bool(obj.receipt)
    has_receipt.boolean = True
    has_receipt.short_description = 'Receipt'

# Register all models
admin.site.register(Department, DepartmentAdmin)
admin.site.register(LeaveType, LeaveTypeAdmin)
admin.site.register(LeaveRequest, LeaveRequestAdmin)
admin.site.register(Attendance, AttendanceAdmin)
admin.site.register(Notification, NotificationAdmin)
admin.site.register(Holiday, HolidayAdmin)
admin.site.register(ReimbursementClaim, ReimbursementClaimAdmin)
admin.site.register(LeaveQuota, LeaveQuotaAdmin)
admin.site.register(ReimbursementExpense, ReimbursementExpenseAdmin)
admin.site.register(Employee, EmployeeAdmin)

# Custom admin site header
admin.site.site_header = "HRM System Administration"
admin.site.site_title = "HRM Admin Portal"
admin.site.index_title = "Welcome to HRM System Administration"

# Advanced Admin Actions
def export_employee_data(modeladmin, request, queryset):
    """Export employee data to CSV"""
    import csv
    from django.http import HttpResponse
    
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="employees.csv"'
    
    writer = csv.writer(response)
    writer.writerow([
        'Employee ID', 'Name', 'Email', 'Designation', 'Department',
        'Role', 'Manager', 'Join Date', 'Phone'
    ])
    
    for employee in queryset:
        writer.writerow([
            employee.employee_id,
            employee.user.get_full_name(),
            employee.user.email,
            employee.designation,
            employee.department.name if employee.department else '',
            employee.user.get_role_display(),
            employee.user.manager.get_full_name() if employee.user.manager else '',
            employee.date_of_joining,
            employee.phone_number
        ])
    
    return response
export_employee_data.short_description = "Export selected employees to CSV"

def generate_leave_report(modeladmin, request, queryset):
    """Generate leave report for selected requests"""
    import csv
    from django.http import HttpResponse
    
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="leave_report.csv"'
    
    writer = csv.writer(response)
    writer.writerow([
        'Employee', 'Leave Type', 'Start Date', 'End Date',
        'Total Days', 'Status', 'Applied On', 'Approved By', 'Comments'
    ])
    
    for leave in queryset:
        writer.writerow([
            leave.employee.user.get_full_name(),
            leave.leave_type.name,
            leave.start_date,
            leave.end_date,
            leave.total_days,
            leave.get_status_display(),
            leave.applied_on,
            leave.processed_by.user.get_full_name() if leave.processed_by else '',
            leave.manager_comments or ''
        ])
    
    return response
generate_leave_report.short_description = "Generate leave report (CSV)"

# Add custom actions to admin classes
EmployeeAdmin.actions = [export_employee_data]
LeaveRequestAdmin.actions.extend([generate_leave_report])