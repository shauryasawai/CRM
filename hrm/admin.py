from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import User
from .models import Employee, LeaveRequest, LeaveType, Attendance, Notification, Department

class EmployeeInline(admin.StackedInline):
    model = Employee
    can_delete = False
    verbose_name_plural = 'Employee Details'
    fk_name = 'user'

class CustomUserAdmin(UserAdmin):
    inlines = (EmployeeInline,)
    list_display = ('username', 'email', 'first_name', 'last_name', 'is_staff', 'get_designation', 'get_department')
    list_select_related = ('employee',)

    def get_designation(self, instance):
        return instance.employee.designation if hasattr(instance, 'employee') else '-'
    get_designation.short_description = 'Designation'

    def get_department(self, instance):
        return instance.employee.department if hasattr(instance, 'employee') else '-'
    get_department.short_description = 'Department'

    def get_inline_instances(self, request, obj=None):
        if not obj:
            return list()
        return super().get_inline_instances(request, obj)

# Only unregister User if it's already registered
if admin.site.is_registered(User):
    admin.site.unregister(User)
admin.site.register(User, CustomUserAdmin)

@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ('name',)
    search_fields = ('name',)

@admin.register(LeaveType)
class LeaveTypeAdmin(admin.ModelAdmin):
    list_display = ('name', 'max_days')
    search_fields = ('name',)

@admin.register(LeaveRequest)
class LeaveRequestAdmin(admin.ModelAdmin):
    list_display = ('employee', 'leave_type', 'start_date', 'end_date', 'status', 'applied_on')
    list_filter = ('status', 'leave_type')
    search_fields = ('employee__user__first_name', 'employee__user__last_name')
    date_hierarchy = 'applied_on'

@admin.register(Attendance)
class AttendanceAdmin(admin.ModelAdmin):
    list_display = ('employee', 'date', 'login_time', 'logout_time', 'is_late', 'is_remote')
    list_filter = ('is_late', 'is_remote')
    search_fields = ('employee__user__first_name', 'employee__user__last_name')
    date_hierarchy = 'date'

@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ('recipient', 'message', 'is_read', 'created_at')
    list_filter = ('is_read',)
    search_fields = ('recipient__user__first_name', 'recipient__user__last_name')
    date_hierarchy = 'created_at'