from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.utils import timezone
from django.db.models import Q, Sum
from datetime import datetime, timedelta, date
from geopy.distance import geodesic
from django.db import models
from django.core.paginator import Paginator
from django.template.loader import render_to_string
import calendar
import json
from .models import (
    Employee, LeaveRequest, LeaveType, Holiday, LeaveQuota,
    Attendance, Notification, Department, ReimbursementClaim,
    ReimbursementExpense
)
from .forms import (
    EmployeeRegistrationForm, LeaveRequestForm, LeaveApprovalForm,
    AttendanceForm, ReimbursementClaimForm, ReimbursementExpenseForm,
    HolidayForm, LeaveCancellationForm
)
from .utils import get_next_approver, auto_approve_pending_leaves

@login_required
def hrm_dashboard(request):
    employee = get_object_or_404(Employee, user=request.user)
    
    # Auto-approve pending leaves (run this check)
    auto_approve_pending_leaves()
    
    # Dashboard statistics
    pending_leaves = LeaveRequest.objects.filter(
        employee__reporting_manager=employee,
        status='P'
    ).count()
    
    pending_reimbursements = ReimbursementClaim.objects.filter(
        employee__reporting_manager=employee,
        status='P'
    ).count()
    
    # Get items requiring approval
    leaves_to_approve = LeaveRequest.objects.filter(
        employee__reporting_manager=employee,
        status='P'
    ).order_by('-applied_on')[:5]
    
    reimbursements_to_approve = ReimbursementClaim.objects.filter(
        employee__reporting_manager=employee,
        status='P'
    ).order_by('-submitted_on')[:5]
    
    # Get employee's recent activities
    recent_attendance = Attendance.objects.filter(
        employee=employee
    ).order_by('-date')[:5]
    
    my_leave_requests = LeaveRequest.objects.filter(
        employee=employee
    ).order_by('-applied_on')[:5]
    
    # Get notifications
    notifications = Notification.objects.filter(
        recipient=employee,
        is_read=False
    ).order_by('-created_at')[:5]
    
    # Monthly attendance summary
    today = timezone.now().date()
    current_month_attendance = Attendance.objects.filter(
        employee=employee,
        date__year=today.year,
        date__month=today.month
    )
    
    total_working_days = current_month_attendance.count()
    present_days = current_month_attendance.filter(login_time__isnull=False).count()
    remote_days = current_month_attendance.filter(is_remote=True).count()
    
    context = {
        'employee': employee,
        'pending_leaves': pending_leaves,
        'pending_reimbursements': pending_reimbursements,
        'leaves_to_approve': leaves_to_approve,
        'reimbursements_to_approve': reimbursements_to_approve,
        'recent_attendance': recent_attendance,
        'my_leave_requests': my_leave_requests,
        'notifications': notifications,
        'total_working_days': total_working_days,
        'present_days': present_days,
        'remote_days': remote_days,
    }
    return render(request, 'hrm/dashboard.html', context)

@login_required
def leave_calendar(request):
    """Leave calendar view with holiday management"""
    employee = get_object_or_404(Employee, user=request.user)
    
    # Get current month/year or from request
    today = timezone.now().date()
    year = int(request.GET.get('year', today.year))
    month = int(request.GET.get('month', today.month))
    
    # Get holidays for the month
    holidays = Holiday.objects.filter(
        date__year=year,
        date__month=month
    )
    
    # Get leave requests for the month
    leave_requests = LeaveRequest.objects.filter(
        employee=employee,
        start_date__year=year,
        start_date__month=month
    ).select_related('leave_type')
    
    # Get attendance for the month
    attendance_records = Attendance.objects.filter(
        employee=employee,
        date__year=year,
        date__month=month
    )
    
    # Create calendar data
    cal = calendar.monthcalendar(year, month)
    calendar_data = []
    
    for week in cal:
        week_data = []
        for day in week:
            if day == 0:
                week_data.append(None)
                continue
                
            day_date = date(year, month, day)
            day_info = {
                'day': day,
                'date': day_date,
                'is_holiday': holidays.filter(date=day_date).exists(),
                'holiday_name': holidays.filter(date=day_date).first().name if holidays.filter(date=day_date).exists() else None,
                'is_sunday': day_date.weekday() == 6,
                'leave_requests': leave_requests.filter(
                    start_date__lte=day_date,
                    end_date__gte=day_date
                ),
                'attendance': attendance_records.filter(date=day_date).first(),
                'is_today': day_date == today,
                'is_past': day_date < today,
            }
            week_data.append(day_info)
        calendar_data.append(week_data)
    
    # Get leave quotas for the employee
    leave_quotas = LeaveQuota.objects.filter(
        hierarchy_level=employee.hierarchy_level
    ).select_related('leave_type')
    
    # Calculate used leaves
    current_year_leaves = LeaveRequest.objects.filter(
        employee=employee,
        start_date__year=year,
        status__in=['A', 'P']  # Approved or Pending
    )
    
    quota_data = []
    for quota in leave_quotas:
        used = current_year_leaves.filter(leave_type=quota.leave_type).aggregate(
            total=Sum('total_days')
        )['total'] or 0
        
        quota_data.append({
            'leave_type': quota.leave_type,
            'total_quota': quota.quota,
            'used': used,
            'remaining': quota.quota - used
        })
    
    context = {
        'employee': employee,
        'calendar_data': calendar_data,
        'year': year,
        'month': month,
        'month_name': calendar.month_name[month],
        'holidays': holidays,
        'quota_data': quota_data,
        'prev_month': month - 1 if month > 1 else 12,
        'next_month': month + 1 if month < 12 else 1,
        'prev_year': year if month > 1 else year - 1,
        'next_year': year if month < 12 else year + 1,
    }
    return render(request, 'hrm/leave_calendar.html', context)

@login_required
def apply_leave(request):
    """Apply for leave with calendar integration"""
    employee = get_object_or_404(Employee, user=request.user)
    
    if request.method == 'POST':
        form = LeaveRequestForm(request.POST)
        if form.is_valid():
            leave = form.save(commit=False)
            leave.employee = employee
            
            # Calculate total days
            delta = leave.end_date - leave.start_date
            leave.total_days = delta.days + 1
            
            # Check if employee has sufficient quota
            try:
                quota = LeaveQuota.objects.get(
                    hierarchy_level=employee.hierarchy_level,
                    leave_type=leave.leave_type
                )
                
                # Calculate used leaves for this year
                current_year_leaves = LeaveRequest.objects.filter(
                    employee=employee,
                    start_date__year=leave.start_date.year,
                    leave_type=leave.leave_type,
                    status__in=['A', 'P']
                ).aggregate(total=Sum('total_days'))['total'] or 0
                
                if current_year_leaves + leave.total_days > quota.quota:
                    messages.error(request, f'Insufficient {leave.leave_type.name} quota. Available: {quota.quota - current_year_leaves} days')
                    return render(request, 'hrm/apply_leave.html', {'form': form, 'employee': employee})
                
            except LeaveQuota.DoesNotExist:
                messages.error(request, f'Leave quota not defined for your hierarchy level.')
                return render(request, 'hrm/apply_leave.html', {'form': form, 'employee': employee})
            
            leave.save()
            
            # Send notification to manager or next approver
            approver = get_next_approver(employee)
            if approver:
                Notification.objects.create(
                    recipient=approver,
                    message=f"{employee.user.get_full_name()} has applied for {leave.leave_type.name} leave from {leave.start_date} to {leave.end_date}",
                    link=f"/hrm/leave/approve/{leave.id}/"
                )
            
            messages.success(request, 'Leave request submitted successfully!')
            return redirect('leave_calendar')
    else:
        # Pre-populate dates if provided
        start_date = request.GET.get('start_date')
        end_date = request.GET.get('end_date')
        initial_data = {}
        
        if start_date:
            initial_data['start_date'] = start_date
        if end_date:
            initial_data['end_date'] = end_date
            
        form = LeaveRequestForm(initial=initial_data)
    
    # Get leave types and quotas
    leave_quotas = LeaveQuota.objects.filter(
        hierarchy_level=employee.hierarchy_level
    ).select_related('leave_type')
    
    context = {
        'form': form,
        'employee': employee,
        'leave_quotas': leave_quotas,
    }
    return render(request, 'hrm/apply_leave.html', context)

@login_required
def cancel_leave(request, leave_id):
    """Cancel leave request"""
    leave = get_object_or_404(LeaveRequest, id=leave_id, employee__user=request.user)
    
    if request.method == 'POST':
        form = LeaveCancellationForm(request.POST)
        if form.is_valid():
            leave.cancellation_reason = form.cleaned_data['cancellation_reason']
            leave.status = 'CR'  # Cancellation Requested
            leave.save()
            
            # Send notification to manager
            approver = get_next_approver(leave.employee)
            if approver:
                Notification.objects.create(
                    recipient=approver,
                    message=f"{leave.employee.user.get_full_name()} has requested cancellation of {leave.leave_type.name} leave",
                    link=f"/hrm/leave/approve/{leave.id}/"
                )
            
            messages.success(request, 'Leave cancellation request submitted successfully!')
            return redirect('leave_management')
    else:
        form = LeaveCancellationForm()
    
    context = {
        'leave': leave,
        'form': form,
    }
    return render(request, 'hrm/cancel_leave.html', context)

@login_required
def leave_management(request):
    """View all leave requests for the employee"""
    employee = get_object_or_404(Employee, user=request.user)
    
    # Get all leave requests for the employee
    leave_requests = LeaveRequest.objects.filter(
        employee=employee
    ).select_related('leave_type', 'processed_by').order_by('-applied_on')
    
    # Pagination
    paginator = Paginator(leave_requests, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'employee': employee,
        'page_obj': page_obj,
    }
    return render(request, 'hrm/leave_management.html', context)

@login_required
def approve_leave(request, leave_id):
    """Approve or reject leave request"""
    leave = get_object_or_404(LeaveRequest, id=leave_id)
    employee = get_object_or_404(Employee, user=request.user)
    
    # Check authorization
    if not (leave.employee.reporting_manager == employee or 
            (leave.employee.reporting_manager and 
             leave.employee.reporting_manager.reporting_manager == employee and
             leave.employee.reporting_manager.is_on_leave())):
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
            status_text = "approved" if leave.status == 'A' else "rejected"
            if leave.status == 'C':
                status_text = "cancelled"
                
            Notification.objects.create(
                recipient=leave.employee,
                message=f"Your {leave.leave_type.name} leave request has been {status_text}",
                link=f"/hrm/leave/view/{leave.id}/"
            )
            
            messages.success(request, f'Leave request {status_text}.')
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
    """Attendance tracking with location validation"""
    employee = get_object_or_404(Employee, user=request.user)
    
    # Handle attendance actions
    if request.method == 'POST':
        action = request.POST.get('action')
        latitude = request.POST.get('latitude')
        longitude = request.POST.get('longitude')
        
        if action == 'login':
            today = timezone.now().date()
            
            # Check if already logged in today
            if Attendance.objects.filter(employee=employee, date=today).exists():
                messages.warning(request, 'You have already logged in today.')
            else:
                # Validate location
                office_location = (28.6139, 77.2090)  # Default office coordinates
                if hasattr(employee, 'office_location') and employee.office_location:
                    office_coords = employee.office_location.split(',')
                    office_location = (float(office_coords[0]), float(office_coords[1]))
                
                is_remote = True
                location_string = f"{latitude},{longitude}" if latitude and longitude else ""
                
                if latitude and longitude:
                    user_location = (float(latitude), float(longitude))
                    distance = geodesic(office_location, user_location).meters
                    is_remote = distance > 500
                
                # Create attendance record
                attendance = Attendance.objects.create(
                    employee=employee,
                    date=today,
                    login_time=timezone.now(),
                    login_location=location_string,
                    is_remote=is_remote,
                    is_late=timezone.now().time() > datetime.strptime('09:30', '%H:%M').time()
                )
                
                # Flag for remote work
                if is_remote:
                    attendance.notes = "Remote work - Outside 500m radius"
                    attendance.save()
                    
                    # Notify manager
                    if employee.reporting_manager:
                        Notification.objects.create(
                            recipient=employee.reporting_manager,
                            message=f"{employee.user.get_full_name()} logged in remotely (flagged as red)",
                            link=f"/hrm/attendance/monthly/"
                        )
                
                messages.success(request, 'Login recorded successfully!')
                
        elif action == 'logout':
            today = timezone.now().date()
            attendance = Attendance.objects.filter(
                employee=employee, 
                date=today, 
                logout_time__isnull=True
            ).first()
            
            if attendance:
                attendance.logout_time = timezone.now()
                attendance.logout_location = f"{latitude},{longitude}" if latitude and longitude else ""
                attendance.save()
                messages.success(request, 'Logout recorded successfully!')
            else:
                messages.warning(request, 'No active login session found.')
        
        return redirect('attendance_tracking')
    
    # Get attendance data
    today = timezone.now().date()
    current_month = today.month
    current_year = today.year
    
    today_attendance = Attendance.objects.filter(employee=employee, date=today).first()
    monthly_attendance = Attendance.objects.filter(
        employee=employee,
        date__year=current_year,
        date__month=current_month
    ).order_by('-date')
    
    # Calculate monthly summary
    total_days = monthly_attendance.count()
    present_days = monthly_attendance.filter(login_time__isnull=False).count()
    remote_days = monthly_attendance.filter(is_remote=True).count()
    late_days = monthly_attendance.filter(is_late=True).count()
    
    # Calculate total hours
    total_hours = 0
    for att in monthly_attendance:
        if att.login_time and att.logout_time:
            duration = att.logout_time - att.login_time
            total_hours += duration.total_seconds() / 3600
    
    context = {
        'employee': employee,
        'today_attendance': today_attendance,
        'monthly_attendance': monthly_attendance,
        'total_days': total_days,
        'present_days': present_days,
        'remote_days': remote_days,
        'late_days': late_days,
        'total_hours': round(total_hours, 2),
        'current_month': calendar.month_name[current_month],
        'current_year': current_year,
    }
    return render(request, 'hrm/attendance.html', context)

@login_required
def reimbursement_claims(request):
    """Manage reimbursement claims"""
    employee = get_object_or_404(Employee, user=request.user)
    
    # Get all claims for the employee
    claims = ReimbursementClaim.objects.filter(
        employee=employee
    ).order_by('-submitted_on')
    
    # Get current month claim or create new one
    today = timezone.now().date()
    current_claim, created = ReimbursementClaim.objects.get_or_create(
        employee=employee,
        month=today.month,
        year=today.year,
        defaults={
            'status': 'D',  # Draft
            'submitted_on': None
        }
    )
    
    # Get expenses for current claim
    expenses = ReimbursementExpense.objects.filter(
        claim=current_claim
    ).order_by('-expense_date')
    
    context = {
        'employee': employee,
        'claims': claims,
        'current_claim': current_claim,
        'expenses': expenses,
    }
    return render(request, 'hrm/reimbursement_claims.html', context)

@login_required
def add_expense(request):
    """Add expense to current month's claim"""
    employee = get_object_or_404(Employee, user=request.user)
    
    if request.method == 'POST':
        form = ReimbursementExpenseForm(request.POST, request.FILES)
        if form.is_valid():
            expense = form.save(commit=False)
            
            # Get or create current month claim
            today = timezone.now().date()
            claim, created = ReimbursementClaim.objects.get_or_create(
                employee=employee,
                month=today.month,
                year=today.year,
                defaults={
                    'status': 'D',
                    'submitted_on': None
                }
            )
            
            expense.claim = claim
            expense.save()
            
            # Update claim total
            claim.total_amount = claim.expenses.aggregate(
                total=Sum('amount')
            )['total'] or 0
            claim.save()
            
            messages.success(request, 'Expense added successfully!')
            return redirect('reimbursement_claims')
    else:
        form = ReimbursementExpenseForm()
    
    context = {
        'form': form,
        'employee': employee,
    }
    return render(request, 'hrm/add_expense.html', context)

@login_required
def submit_claim(request, claim_id):
    """Submit monthly reimbursement claim"""
    claim = get_object_or_404(ReimbursementClaim, id=claim_id, employee__user=request.user)
    
    if claim.status != 'D':
        messages.error(request, 'This claim has already been submitted.')
        return redirect('reimbursement_claims')
    
    if not claim.expenses.exists():
        messages.error(request, 'Cannot submit claim without expenses.')
        return redirect('reimbursement_claims')
    
    # Submit claim
    claim.status = 'P'  # Pending
    claim.submitted_on = timezone.now()
    claim.save()
    
    # Send notification to manager
    if claim.employee.reporting_manager:
        Notification.objects.create(
            recipient=claim.employee.reporting_manager,
            message=f"{claim.employee.user.get_full_name()} has submitted reimbursement claim for {calendar.month_name[claim.month]} {claim.year}",
            link=f"/hrm/reimbursement/approve/{claim.id}/"
        )
    
    messages.success(request, 'Reimbursement claim submitted successfully!')
    return redirect('reimbursement_claims')

@login_required
def approve_reimbursement(request, claim_id):
    """Approve reimbursement claim"""
    claim = get_object_or_404(ReimbursementClaim, id=claim_id)
    employee = get_object_or_404(Employee, user=request.user)
    
    # Check authorization
    if claim.employee.reporting_manager != employee:
        messages.error(request, 'You are not authorized to approve this claim.')
        return redirect('hrm_dashboard')
    
    if request.method == 'POST':
        action = request.POST.get('action')
        comments = request.POST.get('comments', '')
        
        if action == 'approve':
            claim.status = 'MA'  # Manager Approved
            claim.manager_approved_by = employee
            claim.manager_approved_on = timezone.now()
            claim.manager_comments = comments
            
            # If manager approved, send to top management
            if employee.hierarchy_level not in ['TM', 'BH']:
                # Send to top management
                top_managers = Employee.objects.filter(hierarchy_level__in=['TM', 'BH'])
                for tm in top_managers:
                    Notification.objects.create(
                        recipient=tm,
                        message=f"Reimbursement claim from {claim.employee.user.get_full_name()} approved by manager, awaiting final approval",
                        link=f"/hrm/reimbursement/final-approve/{claim.id}/"
                    )
                message_text = 'Claim approved and sent to top management for final approval.'
            else:
                # Top management approval - directly approved
                claim.status = 'A'
                claim.final_approved_by = employee
                claim.final_approved_on = timezone.now()
                message_text = 'Claim approved for reimbursement.'
            
        elif action == 'reject':
            claim.status = 'R'
            claim.manager_approved_by = employee
            claim.manager_approved_on = timezone.now()
            claim.manager_comments = comments
            message_text = 'Claim rejected.'
        
        claim.save()
        
        # Notify employee
        Notification.objects.create(
            recipient=claim.employee,
            message=f"Your reimbursement claim has been {claim.get_status_display()}",
            link=f"/hrm/reimbursement/view/{claim.id}/"
        )
        
        messages.success(request, message_text)
        return redirect('hrm_dashboard')
    
    context = {
        'claim': claim,
        'expenses': claim.expenses.all(),
    }
    return render(request, 'hrm/approve_reimbursement.html', context)

@login_required
def final_approve_reimbursement(request, claim_id):
    """Final approval by top management"""
    claim = get_object_or_404(ReimbursementClaim, id=claim_id)
    employee = get_object_or_404(Employee, user=request.user)
    
    # Check if user is top management
    if employee.hierarchy_level not in ['TM', 'BH']:
        messages.error(request, 'You are not authorized for final approval.')
        return redirect('hrm_dashboard')
    
    if claim.status != 'MA':
        messages.error(request, 'This claim is not ready for final approval.')
        return redirect('hrm_dashboard')
    
    if request.method == 'POST':
        action = request.POST.get('action')
        comments = request.POST.get('final_comments', '')
        
        if action == 'approve':
            claim.status = 'A'
            claim.final_approved_by = employee
            claim.final_approved_on = timezone.now()
            claim.final_comments = comments
            message_text = 'Claim approved for reimbursement.'
            
        elif action == 'reject':
            claim.status = 'R'
            claim.final_approved_by = employee
            claim.final_approved_on = timezone.now()
            claim.final_comments = comments
            message_text = 'Claim rejected.'
        
        claim.save()
        
        # Notify employee
        Notification.objects.create(
            recipient=claim.employee,
            message=f"Your reimbursement claim has been {message_text.lower()}",
            link=f"/hrm/reimbursement/view/{claim.id}/"
        )
        
        messages.success(request, message_text)
        return redirect('hrm_dashboard')
    
    context = {
        'claim': claim,
        'expenses': claim.expenses.all(),
    }
    return render(request, 'hrm/final_approve_reimbursement.html', context)

@login_required
def manage_holidays(request):
    """Manage holidays - Top management only"""
    employee = get_object_or_404(Employee, user=request.user)
    
    if employee.hierarchy_level not in ['TM', 'BH']:
        messages.error(request, 'You are not authorized to manage holidays.')
        return redirect('hrm_dashboard')
    
    if request.method == 'POST':
        form = HolidayForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Holiday added successfully!')
            return redirect('manage_holidays')
    else:
        form = HolidayForm()
    
    # Get current year holidays
    current_year = timezone.now().year
    holidays = Holiday.objects.filter(date__year=current_year).order_by('date')
    
    context = {
        'form': form,
        'holidays': holidays,
        'current_year': current_year,
    }
    return render(request, 'hrm/manage_holidays.html', context)

@login_required
def monthly_attendance_report(request):
    """Monthly attendance report for managers"""
    employee = get_object_or_404(Employee, user=request.user)
    
    # Get current month and year
    today = timezone.now().date()
    current_month = int(request.GET.get('month', today.month))
    current_year = int(request.GET.get('year', today.year))
    
    # Get subordinates based on hierarchy
    subordinates = Employee.objects.filter(reporting_manager=employee)
    
    # Get attendance data
    attendance_data = []
    for emp in subordinates:
        monthly_attendance = Attendance.objects.filter(
            employee=emp,
            date__year=current_year,
            date__month=current_month
        ).order_by('date')
        
        # Calculate statistics
        total_hours = 0
        for att in monthly_attendance:
            if att.login_time and att.logout_time:
                duration = att.logout_time - att.login_time
                total_hours += duration.total_seconds() / 3600
        
        attendance_data.append({
            'employee': emp,
            'attendance': monthly_attendance,
            'total_hours': round(total_hours, 2),
            'present_days': monthly_attendance.filter(login_time__isnull=False).count(),
            'remote_days': monthly_attendance.filter(is_remote=True).count(),
            'late_days': monthly_attendance.filter(is_late=True).count(),
        })
    
    context = {
        'attendance_data': attendance_data,
        'current_month': current_month,
        'current_year': current_year,
        'month_name': calendar.month_name[current_month],
    }
    return render(request, 'hrm/monthly_attendance_report.html', context)

# AJAX Views
@login_required
def get_calendar_day_details(request):
    """Get details for a specific calendar day"""
    date_str = request.GET.get('date')
    if not date_str:
        return JsonResponse({'error': 'Date not provided'})
    
    try:
        day_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        return JsonResponse({'error': 'Invalid date format'})
    
    employee = get_object_or_404(Employee, user=request.user)
    
    # Get day details
    holiday = Holiday.objects.filter(date=day_date).first()
    attendance = Attendance.objects.filter(employee=employee, date=day_date).first()
    leave_requests = LeaveRequest.objects.filter(
        employee=employee,
        start_date__lte=day_date,
        end_date__gte=day_date
    )
    
    data = {
        'date': day_date.strftime('%Y-%m-%d'),
        'is_holiday': bool(holiday),
        'holiday_name': holiday.name if holiday else None,
        'is_sunday': day_date.weekday() == 6,
        'attendance': {
            'present': bool(attendance and attendance.login_time),
            'login_time': attendance.login_time.strftime('%H:%M') if attendance and attendance.login_time else None,
            'logout_time': attendance.logout_time.strftime('%H:%M') if attendance and attendance.logout_time else None,
            'is_remote': attendance.is_remote if attendance else False,
            'is_late': attendance.is_late if attendance else False,
        },
        'leaves': [
            {
                'type': lr.leave_type.name,
                'status': lr.get_status_display(),
                'start_date': lr.start_date.strftime('%Y-%m-%d'),
                'end_date': lr.end_date.strftime('%Y-%m-%d'),
            } for lr in leave_requests
        ]
    }
    
    return JsonResponse(data)

@require_POST
@login_required
def delete_holiday(request, holiday_id):
    """Delete holiday - Top management only"""
    employee = get_object_or_404(Employee, user=request.user)
    
    if employee.hierarchy_level not in ['TM', 'BH']:
        return JsonResponse({'error': 'Unauthorized'}, status=403)
    
    holiday = get_object_or_404(Holiday, id=holiday_id)
    holiday.delete()
    
    return JsonResponse({'success': True})

@require_POST
@login_required
def delete_expense(request, expense_id):
    """Delete expense from claim"""
    expense = get_object_or_404(ReimbursementExpense, id=expense_id, claim__employee__user=request.user)
    
    # Can only delete if claim is in draft status
    if expense.claim.status != 'D':
        return JsonResponse({'error': 'Cannot delete expense from submitted claim'}, status=400)
    
    claim = expense.claim
    expense.delete()
    
    # Update claim total
    claim.total_amount = claim.expenses.aggregate(
        total=Sum('amount')
    )['total'] or 0
    claim.save()
    
    return JsonResponse({'success': True, 'new_total': float(claim.total_amount)})

@login_required
def view_notification(request, notification_id):
    """View and mark notification as read"""
    notification = get_object_or_404(Notification, id=notification_id, recipient__user=request.user)
    notification.is_read = True
    notification.save()
    return redirect(notification.link) if notification.link else redirect('hrm_dashboard')

@require_POST
@login_required
def mark_all_notifications_read(request):
    """Mark all notifications as read"""
    Notification.objects.filter(recipient__user=request.user, is_read=False).update(is_read=True)
    return JsonResponse({'status': 'success'})

@login_required
def employee_directory(request):
    """Employee directory with search and filters"""
    employees = Employee.objects.all().select_related('user', 'department', 'reporting_manager').order_by('hierarchy_level', 'user__last_name')
    departments = Department.objects.all()
    
    # Filtering
    department_id = request.GET.get('department')
    if department_id:
        employees = employees.filter(department_id=department_id)
    
    hierarchy_level = request.GET.get('hierarchy')
    if hierarchy_level:
        employees = employees.filter(hierarchy_level=hierarchy_level)
    
    search_query = request.GET.get('search')
    if search_query:
        employees = employees.filter(
            Q(user__first_name__icontains=search_query) |
            Q(user__last_name__icontains=search_query) |
            Q(designation__icontains=search_query) |
            Q(employee_id__icontains=search_query)
        )
    
    # Pagination
    paginator = Paginator(employees, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'page_obj': page_obj,
        'departments': departments,
        'hierarchy_choices': Employee.HIERARCHY_CHOICES,
    }
    return render(request, 'hrm/employee_directory.html', context)

@login_required
def employee_profile(request, emp_id):
    """View employee profile"""
    employee = get_object_or_404(Employee, id=emp_id)
    current_employee = get_object_or_404(Employee, user=request.user)
    
    # Check if current user can view this profile
    can_view = (
        employee == current_employee or  # Own profile
        employee.reporting_manager == current_employee or  # Subordinate
        current_employee.hierarchy_level in ['TM', 'BH'] or  # Top management
        current_employee.reporting_manager == employee.reporting_manager  # Same manager
    )
    
    if not can_view:
        messages.error(request, 'You are not authorized to view this profile.')
        return redirect('employee_directory')
    
    # Get employee statistics
    today = timezone.now().date()
    current_year = today.year
    current_month = today.month
    
    # Leave statistics
    leave_stats = LeaveRequest.objects.filter(
        employee=employee,
        start_date__year=current_year
    ).values('leave_type__name', 'status').annotate(
        total_days=Sum('total_days')
    )
    
    # Attendance statistics
    monthly_attendance = Attendance.objects.filter(
        employee=employee,
        date__year=current_year,
        date__month=current_month
    )
    
    attendance_stats = {
        'present_days': monthly_attendance.filter(login_time__isnull=False).count(),
        'remote_days': monthly_attendance.filter(is_remote=True).count(),
        'late_days': monthly_attendance.filter(is_late=True).count(),
        'total_days': monthly_attendance.count(),
    }
    
    # Recent activities
    recent_leaves = LeaveRequest.objects.filter(employee=employee).order_by('-applied_on')[:5]
    recent_attendance = Attendance.objects.filter(employee=employee).order_by('-date')[:10]
    
    context = {
        'employee': employee,
        'current_employee': current_employee,
        'leave_stats': leave_stats,
        'attendance_stats': attendance_stats,
        'recent_leaves': recent_leaves,
        'recent_attendance': recent_attendance,
        'current_month': calendar.month_name[current_month],
        'current_year': current_year,
    }
    return render(request, 'hrm/employee_profile.html', context)

@login_required
def reports_dashboard(request):
    """Reports dashboard for managers and top management"""
    employee = get_object_or_404(Employee, user=request.user)
    
    # Check authorization
    if employee.hierarchy_level not in ['TM', 'BH', 'RMH']:
        messages.error(request, 'You are not authorized to access reports.')
        return redirect('hrm_dashboard')
    
    # Get date range
    today = timezone.now().date()
    start_date = request.GET.get('start_date', today.replace(day=1))
    end_date = request.GET.get('end_date', today)
    
    if isinstance(start_date, str):
        start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
    if isinstance(end_date, str):
        end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
    
    # Get subordinates
    if employee.hierarchy_level == 'TM':
        subordinates = Employee.objects.all()
    elif employee.hierarchy_level == 'BH':
        subordinates = Employee.objects.filter(
            Q(reporting_manager=employee) |
            Q(reporting_manager__reporting_manager=employee)
        )
    else:
        subordinates = Employee.objects.filter(reporting_manager=employee)
    
    # Leave statistics
    leave_data = LeaveRequest.objects.filter(
        employee__in=subordinates,
        start_date__range=[start_date, end_date]
    ).values('leave_type__name', 'status').annotate(
        count=models.Count('id'),
        total_days=Sum('total_days')
    )
    
    # Attendance statistics
    attendance_data = Attendance.objects.filter(
        employee__in=subordinates,
        date__range=[start_date, end_date]
    ).aggregate(
        total_records=models.Count('id'),
        remote_count=models.Count('id', filter=Q(is_remote=True)),
        late_count=models.Count('id', filter=Q(is_late=True))
    )
    
    # Reimbursement statistics
    reimbursement_data = ReimbursementClaim.objects.filter(
        employee__in=subordinates,
        submitted_on__range=[start_date, end_date]
    ).values('status').annotate(
        count=models.Count('id'),
        total_amount=Sum('total_amount')
    )
    
    context = {
        'employee': employee,
        'start_date': start_date,
        'end_date': end_date,
        'subordinates_count': subordinates.count(),
        'leave_data': leave_data,
        'attendance_data': attendance_data,
        'reimbursement_data': reimbursement_data,
    }
    return render(request, 'hrm/reports_dashboard.html', context)

# Utility function to check if manager is on leave
def is_manager_on_leave(manager):
    """Check if manager is on approved leave today"""
    today = timezone.now().date()
    return LeaveRequest.objects.filter(
        employee=manager,
        status='A',
        start_date__lte=today,
        end_date__gte=today
    ).exists()

@login_required
def auto_approve_leaves_view(request):
    """Manual trigger for auto-approval (for testing/admin)"""
    employee = get_object_or_404(Employee, user=request.user)
    
    if employee.hierarchy_level not in ['TM', 'BH']:
        messages.error(request, 'You are not authorized to trigger auto-approval.')
        return redirect('hrm_dashboard')
    
    from .utils import auto_approve_pending_leaves
    approved_count = auto_approve_pending_leaves()
    
    messages.success(request, f'{approved_count} leave requests were auto-approved.')
    return redirect('hrm_dashboard')

# Additional utility views for AJAX calls
@login_required
def get_leave_quota(request):
    """Get leave quota for employee"""
    employee = get_object_or_404(Employee, user=request.user)
    leave_type_id = request.GET.get('leave_type_id')
    
    if not leave_type_id:
        return JsonResponse({'error': 'Leave type not provided'})
    
    try:
        quota = LeaveQuota.objects.get(
            hierarchy_level=employee.hierarchy_level,
            leave_type_id=leave_type_id
        )
        
        # Calculate used leaves
        current_year = timezone.now().year
        used = LeaveRequest.objects.filter(
            employee=employee,
            leave_type_id=leave_type_id,
            start_date__year=current_year,
            status__in=['A', 'P']
        ).aggregate(total=Sum('total_days'))['total'] or 0
        
        data = {
            'total_quota': quota.quota,
            'used': used,
            'remaining': quota.quota - used,
            'leave_type': quota.leave_type.name
        }
        
        return JsonResponse(data)
        
    except LeaveQuota.DoesNotExist:
        return JsonResponse({'error': 'Leave quota not found for your hierarchy level'})

@login_required
def calculate_leave_days(request):
    """Calculate working days between two dates"""
    start_date_str = request.GET.get('start_date')
    end_date_str = request.GET.get('end_date')
    
    if not start_date_str or not end_date_str:
        return JsonResponse({'error': 'Start date and end date are required'})
    
    try:
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
    except ValueError:
        return JsonResponse({'error': 'Invalid date format'})
    
    if start_date > end_date:
        return JsonResponse({'error': 'Start date cannot be after end date'})
    
    # Calculate total days
    delta = end_date - start_date
    total_days = delta.days + 1
    
    # Get holidays in the date range
    holidays = Holiday.objects.filter(
        date__range=[start_date, end_date]
    ).count()
    
    # Calculate Sundays in the range
    sundays = 0
    current_date = start_date
    while current_date <= end_date:
        if current_date.weekday() == 6:  # Sunday
            sundays += 1
        current_date += timedelta(days=1)
    
    working_days = total_days - holidays - sundays
    
    data = {
        'total_days': total_days,
        'working_days': max(working_days, 1),  # At least 1 day
        'holidays': holidays,
        'sundays': sundays
    }
    
    return JsonResponse(data)