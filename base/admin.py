from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DefaultUserAdmin
from .models import User, Lead, Client, Task, Reminder, ServiceRequest, BusinessTracker, InvestmentPlanReview

@admin.register(User)
class UserAdmin(DefaultUserAdmin):
    list_display = ('username', 'email', 'first_name', 'last_name', 'role', 'is_staff', 'is_active')
    list_filter = ('role', 'is_staff', 'is_active')
    fieldsets = DefaultUserAdmin.fieldsets + (
        (None, {'fields': ('role',)}),
    )
    search_fields = ('username', 'email', 'first_name', 'last_name')
    ordering = ('username',)


@admin.register(Lead)
class LeadAdmin(admin.ModelAdmin):
    list_display = ('name', 'contact_info', 'assigned_to', 'status', 'created_at')
    list_filter = ('status', 'assigned_to')
    search_fields = ('name', 'contact_info')


@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    list_display = ('name', 'contact_info', 'user', 'aum', 'sip_amount', 'demat_count')
    search_fields = ('name', 'contact_info')


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = ('title', 'assigned_to', 'due_date', 'completed')
    list_filter = ('completed', 'due_date')
    search_fields = ('title', 'description')


@admin.register(Reminder)
class ReminderAdmin(admin.ModelAdmin):
    list_display = ('user', 'message', 'remind_at', 'is_done')
    list_filter = ('is_done',)
    search_fields = ('message',)


@admin.register(ServiceRequest)
class ServiceRequestAdmin(admin.ModelAdmin):
    list_display = ('client', 'raised_by', 'status', 'created_at', 'updated_at')
    list_filter = ('status',)
    search_fields = ('client__name', 'description')


@admin.register(BusinessTracker)
class BusinessTrackerAdmin(admin.ModelAdmin):
    list_display = ('month', 'total_sip', 'total_demat', 'total_aum')
    ordering = ('-month',)


@admin.register(InvestmentPlanReview)
class InvestmentPlanReviewAdmin(admin.ModelAdmin):
    list_display = ('client', 'goal', 'principal_amount', 'tenure_years', 'monthly_investment', 'created_at', 'total_investment')
    search_fields = ('client__name', 'goal')
    ordering = ('-created_at',)

    def total_investment(self, obj):
        return obj.total_investment
    total_investment.short_description = 'Total Investment'

