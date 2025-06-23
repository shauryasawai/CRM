from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import User
from django.utils.html import format_html
from django.urls import reverse
from django.utils import timezone
from django.utils.timesince import timesince
from .models import (
    Employee, LeaveRequest, LeaveType, Attendance, 
    Notification, Department, Holiday, LeaveQuota,
    ReimbursementClaim, ReimbursementExpense
)

class EmployeeInline(admin.StackedInline):
    model = Employee
    can_delete = False
    verbose_name_plural = 'Employee Details'
    fk_name = 'user'
    fieldsets = (
        (None, {
            'fields': (
                'employee_id', 'designation', 'department', 
                'reporting_manager', 'date_of_joining',
                'hierarchy_level', 'phone_number', 'office_location'
            )
        }),
    )
    readonly_fields = ('employee_id',)

class CustomUserAdmin(UserAdmin):
    inlines = (EmployeeInline,)
    list_display = (
        'username', 'email', 'first_name', 'last_name', 
        'is_staff', 'get_designation', 'get_department',
        'get_reporting_manager', 'hierarchy_level'
    )
    list_select_related = ('employee',)
    list_filter = ('employee__department', 'employee__hierarchy_level', 'is_staff', 'is_superuser')
    search_fields = ('username', 'email', 'first_name', 'last_name', 'employee__employee_id')

    def get_designation(self, instance):
        return instance.employee.designation if hasattr(instance, 'employee') else '-'
    get_designation.short_description = 'Designation'

    def get_department(self, instance):
        return instance.employee.department.name if hasattr(instance, 'employee') and instance.employee.department else '-'
    get_department.short_description = 'Department'

    def get_reporting_manager(self, instance):
        if hasattr(instance, 'employee') and instance.employee.reporting_manager:
            try:
                url = reverse('admin:auth_user_change', args=[instance.employee.reporting_manager.user.id])
                return format_html('<a href="{}">{}</a>', url, instance.employee.reporting_manager.user.get_full_name())
            except:
                return instance.employee.reporting_manager.user.get_full_name()
        return '-'
    get_reporting_manager.short_description = 'Reporting Manager'
    get_reporting_manager.admin_order_field = 'employee__reporting_manager__user__last_name'

    def hierarchy_level(self, instance):
        return instance.employee.get_hierarchy_level_display() if hasattr(instance, 'employee') else '-'
    hierarchy_level.short_description = 'Hierarchy Level'
    hierarchy_level.admin_order_field = 'employee__hierarchy_level'

    def get_inline_instances(self, request, obj=None):
        if not obj:
            return list()
        return super().get_inline_instances(request, obj)

# Unregister and re-register User model
if admin.site.is_registered(User):
    admin.site.unregister(User)
admin.site.register(User, CustomUserAdmin)

class LeaveTypeAdmin(admin.ModelAdmin):
    list_display = ('name', 'max_days', 'description_short')
    search_fields = ('name',)
    
    def description_short(self, obj):
        return obj.description[:50] + '...' if obj.description else '-'
    description_short.short_description = 'Description'

class LeaveRequestAdmin(admin.ModelAdmin):
    list_display = (
        'employee_link', 'leave_type', 'date_range', 
        'total_days', 'status_badge', 'applied_on',
        'processed_by_link', 'manager_comments_short'
    )
    list_filter = (
        'status', 'leave_type', 'employee__department',
        'employee__hierarchy_level'
    )
    search_fields = (
        'employee__user__first_name', 'employee__user__last_name',
        'employee__employee_id'
    )
    date_hierarchy = 'applied_on'
    readonly_fields = ('total_days', 'applied_on', 'processed_on')
    fieldsets = (
        (None, {
            'fields': ('employee', 'leave_type', 'start_date', 'end_date')
        }),
        ('Status', {
            'fields': ('status', 'manager_comments', 'processed_by')
        }),
        ('System', {
            'fields': ('total_days', 'applied_on', 'processed_on'),
            'classes': ('collapse',)
        }),
    )
    actions = ['approve_selected', 'reject_selected']

    def employee_link(self, obj):
        try:
            url = reverse('admin:auth_user_change', args=[obj.employee.user.id])
            return format_html('<a href="{}">{}</a>', url, obj.employee.user.get_full_name())
        except:
            return obj.employee.user.get_full_name()
    employee_link.short_description = 'Employee'
    employee_link.admin_order_field = 'employee__user__last_name'

    def processed_by_link(self, obj):
        if obj.processed_by:
            try:
                url = reverse('admin:auth_user_change', args=[obj.processed_by.user.id])
                return format_html('<a href="{}">{}</a>', url, obj.processed_by.user.get_full_name())
            except:
                return obj.processed_by.user.get_full_name()
        return '-'
    processed_by_link.short_description = 'Processed By'
    processed_by_link.admin_order_field = 'processed_by__user__last_name'

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
        if not hasattr(request.user, 'employee'):
            self.message_user(request, "Only employees can approve leaves.", level='error')
            return
        updated = queryset.filter(status='P').update(status='A', processed_by=request.user.employee)
        self.message_user(request, f"{updated} leave requests approved.")
    approve_selected.short_description = "Approve selected pending leaves"

    def reject_selected(self, request, queryset):
        if not hasattr(request.user, 'employee'):
            self.message_user(request, "Only employees can reject leaves.", level='error')
            return
        updated = queryset.filter(status='P').update(status='R', processed_by=request.user.employee)
        self.message_user(request, f"{updated} leave requests rejected.")
    reject_selected.short_description = "Reject selected pending leaves"

class AttendanceAdmin(admin.ModelAdmin):
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
    readonly_fields = ('duration_calculated',)

    def employee_link(self, obj):
        try:
            url = reverse('admin:auth_user_change', args=[obj.employee.user.id])
            return format_html('<a href="{}">{}</a>', url, obj.employee.user.get_full_name())
        except:
            return obj.employee.user.get_full_name()
    employee_link.short_description = 'Employee'
    employee_link.admin_order_field = 'employee__user__last_name'

    def duration(self, obj):
        if obj.login_time and obj.logout_time:
            delta = obj.logout_time - obj.login_time
            hours, remainder = divmod(delta.seconds, 3600)
            minutes = remainder // 60
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

    def duration_calculated(self, obj):
        return self.duration(obj)
    duration_calculated.short_description = 'Duration'

class ReimbursementExpenseInline(admin.TabularInline):
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
    inlines = [ReimbursementExpenseInline]
    actions = ['approve_selected', 'reject_selected']

    def employee_link(self, obj):
        try:
            url = reverse('admin:auth_user_change', args=[obj.employee.user.id])
            return format_html('<a href="{}">{}</a>', url, obj.employee.user.get_full_name())
        except:
            return obj.employee.user.get_full_name()
    employee_link.short_description = 'Employee'
    employee_link.admin_order_field = 'employee__user__last_name'

    def manager_link(self, obj):
        if obj.manager_approved_by:
            try:
                url = reverse('admin:auth_user_change', args=[obj.manager_approved_by.user.id])
                return format_html('<a href="{}">{}</a>', url, obj.manager_approved_by.user.get_full_name())
            except:
                return obj.manager_approved_by.user.get_full_name()
        return '-'
    manager_link.short_description = 'Manager'
    manager_link.admin_order_field = 'manager_approved_by__user__last_name'

    def period(self, obj):
        return f"{obj.get_month_display()} {obj.year}"
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
        if not hasattr(request.user, 'employee'):
            self.message_user(request, "Only employees can approve claims.", level='error')
            return
        
        updated = queryset.filter(status='P').update(
            status='MA',
            manager_approved_by=request.user.employee,
            manager_approved_on=timezone.now()
        )
        self.message_user(request, f"{updated} claims approved by manager.")
    approve_selected.short_description = "Approve selected pending claims"

    def reject_selected(self, request, queryset):
        if not hasattr(request.user, 'employee'):
            self.message_user(request, "Only employees can reject claims.", level='error')
            return
        
        updated = queryset.filter(status='P').update(
            status='R',
            manager_approved_by=request.user.employee,
            manager_approved_on=timezone.now()
        )
        self.message_user(request, f"{updated} claims rejected.")
    reject_selected.short_description = "Reject selected pending claims"

class HolidayAdmin(admin.ModelAdmin):
    list_display = ('name', 'date', 'is_past', 'days_until')
    list_filter = (('date', admin.DateFieldListFilter),)
    search_fields = ('name',)
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
    list_display = ('get_hierarchy_display', 'leave_type', 'quota')
    list_filter = ('hierarchy_level', 'leave_type')
    search_fields = ('leave_type__name',)
    
    def get_hierarchy_display(self, obj):
        return obj.get_hierarchy_level_display()
    get_hierarchy_display.short_description = 'Hierarchy Level'
    get_hierarchy_display.admin_order_field = 'hierarchy_level'

class NotificationAdmin(admin.ModelAdmin):
    list_display = ('recipient_link', 'message_short', 'is_read', 'created_ago')
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
            url = reverse('admin:auth_user_change', args=[obj.recipient.user.id])
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

# Register all models
admin.site.register(Department)
admin.site.register(LeaveType, LeaveTypeAdmin)
admin.site.register(LeaveRequest, LeaveRequestAdmin)
admin.site.register(Attendance, AttendanceAdmin)
admin.site.register(Notification, NotificationAdmin)
admin.site.register(Holiday, HolidayAdmin)
admin.site.register(ReimbursementClaim, ReimbursementClaimAdmin)
admin.site.register(LeaveQuota, LeaveQuotaAdmin)
admin.site.register(ReimbursementExpense)
admin.site.register(Employee)

# Custom admin site header
admin.site.site_header = "HRM System Administration"
admin.site.site_title = "HRM System Admin Portal"
admin.site.index_title = "Welcome to HRM System Administration"