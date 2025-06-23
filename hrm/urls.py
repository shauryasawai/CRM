from django.urls import path
from . import views

urlpatterns = [
    # Dashboard
    path('', views.hrm_dashboard, name='hrm_dashboard'),
    
    # Employee Management
    path('directory/', views.employee_directory, name='employee_directory'),
    path('employee/<int:emp_id>/', views.employee_profile, name='employee_profile'),
    
    # Leave Management
    path('leave/', views.leave_management, name='leave_management'),
    path('leave/calendar/', views.leave_calendar, name='leave_calendar'),
    path('leave/apply/', views.apply_leave, name='apply_leave'),
    path('leave/<int:leave_id>/approve/', views.approve_leave, name='approve_leave'),
    path('leave/<int:leave_id>/cancel/', views.cancel_leave, name='cancel_leave'),
    
    # Attendance Management
    path('attendance/', views.attendance_tracking, name='attendance_tracking'),
    path('attendance/monthly/', views.monthly_attendance_report, name='monthly_attendance_report'),
    
    # Reimbursement Management
    path('reimbursement/', views.reimbursement_claims, name='reimbursement_claims'),
    path('reimbursement/add-expense/', views.add_expense, name='add_expense'),
    path('reimbursement/<int:claim_id>/submit/', views.submit_claim, name='submit_claim'),
    path('reimbursement/<int:claim_id>/approve/', views.approve_reimbursement, name='approve_reimbursement'),
    path('reimbursement/<int:claim_id>/final-approve/', views.final_approve_reimbursement, name='final_approve_reimbursement'),
    
    # Holiday Management
    path('holidays/', views.manage_holidays, name='manage_holidays'),
    
    # Reports
    path('reports/', views.reports_dashboard, name='reports_dashboard'),
    
    # Notifications
    path('notification/<int:notification_id>/', views.view_notification, name='view_notification'),
    path('notifications/mark-all-read/', views.mark_all_notifications_read, name='mark_all_notifications_read'),
    
    # AJAX/API Endpoints
    path('api/calendar-day-details/', views.get_calendar_day_details, name='get_calendar_day_details'),
    path('api/leave-quota/', views.get_leave_quota, name='get_leave_quota'),
    path('api/calculate-leave-days/', views.calculate_leave_days, name='calculate_leave_days'),
    
    # Delete Operations (AJAX)
    path('api/holiday/<int:holiday_id>/delete/', views.delete_holiday, name='delete_holiday'),
    path('api/expense/<int:expense_id>/delete/', views.delete_expense, name='delete_expense'),
    
    # Utility Functions
    path('utils/auto-approve-leaves/', views.auto_approve_leaves_view, name='auto_approve_leaves'),
]