from django.urls import path
from . import views

urlpatterns = [
    # HRM URLs
    path('', views.hrm_dashboard, name='hrm_dashboard'),
    path('directory/', views.employee_directory, name='employee_directory'),
    path('leave/', views.leave_management, name='leave_management'),
    path('leave/<int:leave_id>/approve/', views.approve_leave, name='approve_leave'),
    path('attendance/', views.attendance_tracking, name='attendance_tracking'),
    path('attendance/<int:emp_id>/mark/', views.mark_attendance, name='mark_attendance'),
    path('reports/monthly/', views.monthly_attendance_report, name='monthly_report'),
    path('notification/<int:notification_id>/', views.view_notification, name='view_notification'),
    path('notifications/mark-all-read/', views.mark_all_notifications_read, name='mark_all_notifications_read'),
]