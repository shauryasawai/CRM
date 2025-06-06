from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.utils import timezone
from datetime import datetime, timedelta
from geopy.distance import geodesic
from django.db import models
from .models import (
    Employee, LeaveRequest, LeaveType, 
    Attendance, Notification, Department
)
from .forms import (
    EmployeeRegistrationForm, LeaveRequestForm,
    LeaveApprovalForm, AttendanceForm
)

@login_required
def hrm_dashboard(request):
    employee = get_object_or_404(Employee, user=request.user)
    pending_leaves = LeaveRequest.objects.filter(
        employee__reporting_manager=employee,
        status='P'
    ).count()
    
    # Get leaves pending approval
    leaves_to_approve = LeaveRequest.objects.filter(
        employee__reporting_manager=employee,
        status='P'
    )
    
    # Get recent attendance
    recent_attendance = Attendance.objects.filter(
        employee=employee
    ).order_by('-date')[:5]
    
    # Get notifications
    notifications = Notification.objects.filter(
        recipient=employee,
        is_read=False
    ).order_by('-created_at')[:5]
    
    context = {
        'employee': employee,
        'pending_leaves': pending_leaves,
        'leaves_to_approve': leaves_to_approve,
        'recent_attendance': recent_attendance,
        'notifications': notifications,
    }
    return render(request, 'hrm/dashboard.html', context)

@login_required
def employee_directory(request):
    employees = Employee.objects.all().order_by('hierarchy_level', 'user__last_name')
    departments = Department.objects.all()
    
    # Filtering
    department_id = request.GET.get('department')
    if department_id:
        employees = employees.filter(department_id=department_id)
    
    search_query = request.GET.get('search')
    if search_query:
        employees = employees.filter(
            models.Q(user__first_name__icontains=search_query) |
            models.Q(user__last_name__icontains=search_query) |
            models.Q(designation__icontains=search_query)
        )
    
    context = {
        'employees': employees,
        'departments': departments,
    }
    return render(request, 'hrm/directory.html', context)

@login_required
def leave_management(request):
    employee = get_object_or_404(Employee, user=request.user)
    leave_requests = LeaveRequest.objects.filter(employee=employee).order_by('-applied_on')
    leave_types = LeaveType.objects.all()
    
    if request.method == 'POST':
        form = LeaveRequestForm(request.POST)
        if form.is_valid():
            leave = form.save(commit=False)
            leave.employee = employee
            leave.save()
            
            # Create notification for manager
            if employee.reporting_manager:
                Notification.objects.create(
                    recipient=employee.reporting_manager,
                    message=f"{employee.user.get_full_name()} has applied for {leave.leave_type.name} leave",
                    link=f"/hrm/leave/{leave.id}/"
                )
            
            messages.success(request, 'Leave request submitted successfully!')
            return redirect('leave_management')
    else:
        form = LeaveRequestForm()
    
    context = {
        'employee': employee,
        'leave_requests': leave_requests,
        'leave_types': leave_types,
        'form': form,
    }
    return render(request, 'hrm/leave.html', context)

@login_required
def approve_leave(request, leave_id):
    leave = get_object_or_404(LeaveRequest, id=leave_id)
    employee = get_object_or_404(Employee, user=request.user)
    
    # Check if current user is the reporting manager
    if leave.employee.reporting_manager != employee:
        messages.error(request, 'You are not authorized to approve this leave request.')
        return redirect('hrm_dashboard')
    
    if request.method == 'POST':
        form = LeaveApprovalForm(request.POST, instance=leave)
        if form.is_valid():
            leave = form.save(commit=False)
            leave.processed_by = employee
            leave.processed_on = timezone.now()
            leave.save()
            
            # Create notification for employee
            Notification.objects.create(
                recipient=leave.employee,
                message=f"Your leave request has been {leave.get_status_display()}",
                link=f"/hrm/leave/{leave.id}/"
            )
            
            messages.success(request, f'Leave request {leave.get_status_display().lower()}.')
            return redirect('hrm_dashboard')
    else:
        form = LeaveApprovalForm(instance=leave)
    
    context = {
        'leave': leave,
        'form': form,
    }
    return render(request, 'hrm/approve_leave.html', context)

@login_required
def attendance_tracking(request):
    employee = get_object_or_404(Employee, user=request.user)
    
    # Handle login/logout
    if request.method == 'POST':
        action = request.POST.get('action')
        location = request.POST.get('location', '')
        
        if action == 'login':
            # Check if already logged in today
            today = timezone.now().date()
            if Attendance.objects.filter(employee=employee, date=today).exists():
                messages.warning(request, 'You have already logged in today.')
            else:
                # Check location (simplified for example)
                office_location = (12.9716, 77.5946)  # Example coordinates
                user_location = tuple(map(float, location.split(','))) if location else (0, 0)
                distance = geodesic(office_location, user_location).meters
                
                Attendance.objects.create(
                    employee=employee,
                    login_time=timezone.now(),
                    login_location=location,
                    is_remote=distance > 500,
                    is_late=timezone.now().time() > datetime.strptime('09:30', '%H:%M').time()
                )
                messages.success(request, 'Login recorded successfully!')
                
                # Notify manager if remote
                if distance > 500 and employee.reporting_manager:
                    Notification.objects.create(
                        recipient=employee.reporting_manager,
                        message=f"{employee.user.get_full_name()} logged in remotely (500+ meters from office)",
                        link=f"/hrm/attendance/{employee.id}/"
                    )
        
        elif action == 'logout':
            today = timezone.now().date()
            attendance = Attendance.objects.filter(employee=employee, date=today, logout_time__isnull=True).first()
            if attendance:
                attendance.logout_time = timezone.now()
                attendance.save()
                messages.success(request, 'Logout recorded successfully!')
            else:
                messages.warning(request, 'No active login session found.')
        
        return redirect('attendance_tracking')
    
    # Get attendance records
    today = timezone.now().date()
    current_month = today.month
    current_year = today.year
    
    today_attendance = Attendance.objects.filter(employee=employee, date=today).first()
    monthly_attendance = Attendance.objects.filter(
        employee=employee,
        date__year=current_year,
        date__month=current_month
    ).order_by('-date')
    
    context = {
        'employee': employee,
        'today_attendance': today_attendance,
        'monthly_attendance': monthly_attendance,
    }
    return render(request, 'hrm/attendance.html', context)

@login_required
def mark_attendance(request, emp_id):
    # Manager view to mark attendance for employees
    if not request.user.employee.hierarchy_level in ['TM', 'BH', 'RMH']:
        messages.error(request, 'You are not authorized to access this page.')
        return redirect('hrm_dashboard')
    
    employee = get_object_or_404(Employee, id=emp_id)
    
    if request.method == 'POST':
        form = AttendanceForm(request.POST)
        if form.is_valid():
            attendance = form.save(commit=False)
            attendance.employee = employee
            attendance.save()
            messages.success(request, 'Attendance marked successfully!')
            return redirect('employee_directory')
    else:
        form = AttendanceForm()
    
    context = {
        'employee': employee,
        'form': form,
    }
    return render(request, 'hrm/mark_attendance.html', context)

@login_required
def monthly_attendance_report(request):
    if not request.user.employee.hierarchy_level in ['TM', 'BH', 'RMH']:
        messages.error(request, 'You are not authorized to access this page.')
        return redirect('hrm_dashboard')
    
    # Get current month and year
    today = timezone.now().date()
    current_month = today.month
    current_year = today.year
    
    # Get selected month/year from request
    selected_month = request.GET.get('month', current_month)
    selected_year = request.GET.get('year', current_year)
    
    # Get all employees in the hierarchy below current user
    employees = Employee.objects.all()
    if request.user.employee.hierarchy_level == 'BH':
        employees = employees.filter(hierarchy_level__in=['RMH', 'RM'])
    elif request.user.employee.hierarchy_level == 'RMH':
        employees = employees.filter(hierarchy_level='RM')
    
    # Get attendance data
    attendance_data = []
    for emp in employees:
        monthly_attendance = Attendance.objects.filter(
            employee=emp,
            date__year=selected_year,
            date__month=selected_month
        ).order_by('date')
        
        total_hours = sum(
            (att.logout_time - att.login_time).total_seconds() / 3600 
            for att in monthly_attendance 
            if att.logout_time
        )
        
        attendance_data.append({
            'employee': emp,
            'attendance': monthly_attendance,
            'total_hours': round(total_hours, 2),
            'remote_days': monthly_attendance.filter(is_remote=True).count(),
            'late_days': monthly_attendance.filter(is_late=True).count(),
        })
    
    context = {
        'attendance_data': attendance_data,
        'selected_month': int(selected_month),
        'selected_year': int(selected_year),
        'current_month': current_month,
        'current_year': current_year,
    }
    return render(request, 'hrm/monthly_report.html', context)

@login_required
def view_notification(request, notification_id):
    notification = get_object_or_404(Notification, id=notification_id, recipient__user=request.user)
    notification.is_read = True
    notification.save()
    return redirect(notification.link) if notification.link else redirect('hrm_dashboard')

@require_POST
@login_required
def mark_all_notifications_read(request):
    Notification.objects.filter(recipient__user=request.user, is_read=False).update(is_read=True)
    return JsonResponse({'status': 'success'})