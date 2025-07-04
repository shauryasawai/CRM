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
import re

# Import CRM User model and HRM models
from base.models import User
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
    """Enhanced dashboard with CRM integration"""
    try:
        employee = Employee.objects.get(user=request.user)
    except Employee.DoesNotExist:
        # Create employee profile if doesn't exist
        employee = Employee.objects.create(
            user=request.user,
            designation=request.user.get_role_display(),
            date_of_joining=timezone.now().date(),
            hierarchy_level=request.user.role
        )
    
    # Auto-approve pending leaves (run this check)
    auto_approve_pending_leaves()
    
    # Get subordinates using CRM hierarchy
    subordinates = []
    if request.user.role in ['rm_head', 'ops_team_lead', 'business_head', 'business_head_ops', 'top_management']:
        # Get CRM subordinates and their employee profiles
        crm_subordinates = request.user.get_team_members()
        subordinates = Employee.objects.filter(user__in=crm_subordinates)
    
    # Dashboard statistics - items requiring approval
    pending_leaves = LeaveRequest.objects.filter(
        employee__in=subordinates,
        status='P'
    ).count()
    
    pending_reimbursements = ReimbursementClaim.objects.filter(
        employee__in=subordinates,
        status='P'
    ).count()
    
    # Get items requiring approval
    leaves_to_approve = LeaveRequest.objects.filter(
        employee__in=subordinates,
        status='P'
    ).select_related('employee', 'leave_type').order_by('-applied_on')[:5]
    
    reimbursements_to_approve = ReimbursementClaim.objects.filter(
        employee__in=subordinates,
        status='P'
    ).select_related('employee').order_by('-submitted_on')[:5]
    
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
    # Monthly attendance summary
    # Monthly attendance summary
    today = timezone.now().date()
    current_month_attendance = Attendance.objects.filter(
        employee=employee,
        date__year=today.year,
        date__month=today.month)
    total_working_days = current_month_attendance.count()
    present_days = current_month_attendance.filter(login_time__isnull=False).count()
    remote_days = current_month_attendance.filter(is_remote=True).count()

    # Get leave balance summary
    leave_balance_summary = []
    if hasattr(employee, 'annual_leave_balance'):
        leave_balance_summary = [
            {'type': 'Annual Leave', 'balance': employee.annual_leave_balance},
            {'type': 'Casual Leave', 'balance': employee.casual_leave_balance},
            {'type': 'Sick Leave', 'balance': employee.sick_leave_balance},
        ]
    
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
        'leave_balance_summary': leave_balance_summary,
        'can_approve_leaves': request.user.role in ['rm_head', 'ops_team_lead', 'business_head', 'business_head_ops', 'top_management'],
    }
    return render(request, 'hrm/dashboard.html', context)

@login_required
def leave_calendar(request):
    """Enhanced leave calendar with CRM integration"""
    try:
        employee = Employee.objects.get(user=request.user)
    except Employee.DoesNotExist:
        messages.error(request, 'Employee profile not found. Please contact HR.')
        return redirect('hrm_dashboard')
    
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
    
    # Get leave quotas for the employee using CRM role
    leave_quotas = LeaveQuota.objects.filter(
        hierarchy_level=employee.user.role  # Use CRM role directly
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
    """Enhanced leave application with CRM hierarchy validation"""
    try:
        employee = Employee.objects.get(user=request.user)
    except Employee.DoesNotExist:
        messages.error(request, 'Employee profile not found. Please contact HR.')
        return redirect('hrm_dashboard')
    
    if request.method == 'POST':
        form = LeaveRequestForm(request.POST)
        if form.is_valid():
            leave = form.save(commit=False)
            leave.employee = employee
            
            # Calculate total days
            delta = leave.end_date - leave.start_date
            leave.total_days = delta.days + 1
            
            # Check if employee has sufficient quota using CRM role
            try:
                quota = LeaveQuota.objects.get(
                    hierarchy_level=employee.user.role,  # Use CRM role
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
                messages.error(request, f'Leave quota not defined for your role: {employee.user.get_role_display()}.')
                return render(request, 'hrm/apply_leave.html', {'form': form, 'employee': employee})
            
            leave.save()
            
            # Get approver using CRM hierarchy
            approver_user = employee.user.get_approval_manager()
            if approver_user:
                try:
                    approver_employee = Employee.objects.get(user=approver_user)
                    Notification.create_leave_notification(leave, approver_employee, 'request')
                except Employee.DoesNotExist:
                    pass
            
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
    
    # Get leave types and quotas using CRM role
    leave_quotas = LeaveQuota.objects.filter(
        hierarchy_level=employee.user.role
    ).select_related('leave_type')
    
    context = {
        'form': form,
        'employee': employee,
        'leave_quotas': leave_quotas,
    }
    return render(request, 'hrm/apply_leave.html', context)

@login_required
def cancel_leave(request, leave_id):
    """Enhanced leave cancellation"""
    leave = get_object_or_404(LeaveRequest, id=leave_id, employee__user=request.user)
    
    if request.method == 'POST':
        form = LeaveCancellationForm(request.POST)
        if form.is_valid():
            leave.cancellation_reason = form.cleaned_data['cancellation_reason']
            leave.status = 'CR'  # Cancellation Requested
            leave.save()
            
            # Send notification to approver using CRM hierarchy
            approver_user = leave.employee.user.get_approval_manager()
            if approver_user:
                try:
                    approver_employee = Employee.objects.get(user=approver_user)
                    Notification.create_leave_notification(leave, approver_employee, 'cancellation')
                except Employee.DoesNotExist:
                    pass
            
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
    """Enhanced leave management view"""
    try:
        employee = Employee.objects.get(user=request.user)
    except Employee.DoesNotExist:
        messages.error(request, 'Employee profile not found.')
        return redirect('hrm_dashboard')
    
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
    """Enhanced leave approval using CRM hierarchy"""
    leave = get_object_or_404(LeaveRequest, id=leave_id)
    
    try:
        approver_employee = Employee.objects.get(user=request.user)
    except Employee.DoesNotExist:
        messages.error(request, 'Employee profile not found.')
        return redirect('hrm_dashboard')
    
    # Check authorization using CRM hierarchy
    if not request.user.can_approve_conversion(leave.employee.user):
        messages.error(request, 'You are not authorized to approve this leave request.')
        return redirect('hrm_dashboard')
    
    if request.method == 'POST':
        action = request.POST.get('action')
        comments = request.POST.get('manager_comments', '')
        
        if action == 'approve':
            if leave.approve(approver_employee, comments):
                Notification.create_leave_notification(leave, leave.employee, 'approval')
                messages.success(request, 'Leave request approved successfully.')
            else:
                messages.error(request, 'Failed to approve leave request.')
        
        elif action == 'reject':
            if leave.reject(approver_employee, comments):
                Notification.create_leave_notification(leave, leave.employee, 'rejection')
                messages.success(request, 'Leave request rejected.')
            else:
                messages.error(request, 'Failed to reject leave request.')
        
        elif action == 'approve_cancellation' and leave.status == 'CR':
            if leave.approve_cancellation(approver_employee):
                messages.success(request, 'Leave cancellation approved.')
            else:
                messages.error(request, 'Failed to approve cancellation.')
        
        return redirect('hrm_dashboard')
    
    context = {
        'leave': leave,
        'approver_employee': approver_employee,
    }
    return render(request, 'hrm/approve_leave.html', context)

def parse_coordinate(coord_str):
    """
    Parse coordinate string and extract numeric value
    Examples:
    '30.7333° N' -> 30.7333
    '77.1167° E' -> 77.1167 
    '-30.7333° S' -> -30.7333
    '30.7333' -> 30.7333
    """
    if not coord_str:
        return None
    
    # Remove whitespace
    coord_str = coord_str.strip()
    
    # Extract numeric part using regex
    numeric_match = re.search(r'-?\d+\.?\d*', coord_str)
    
    if numeric_match:
        numeric_value = float(numeric_match.group())
        
        # Check for direction indicators to determine sign
        if 'S' in coord_str.upper() or 'W' in coord_str.upper():
            # South and West are negative
            return -abs(numeric_value)
        else:
            # North and East are positive (or no direction specified)
            return numeric_value
    
    # If no numeric pattern found, try direct float conversion
    try:
        return float(coord_str)
    except ValueError:
        return None

@login_required
def attendance_tracking(request):
    """Enhanced attendance tracking with location validation"""
    try:
        employee = Employee.objects.get(user=request.user)
    except Employee.DoesNotExist:
        messages.error(request, 'Employee profile not found.')
        return redirect('hrm_dashboard')
    
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
                
                if employee.office_location:
                    try:
                        office_coords = employee.office_location.split(',')
                        if len(office_coords) >= 2:
                            office_lat = parse_coordinate(office_coords[0])
                            office_lng = parse_coordinate(office_coords[1])
                            
                            if office_lat is not None and office_lng is not None:
                                office_location = (office_lat, office_lng)
                            else:
                                messages.warning(request, 'Invalid office location format. Using default coordinates.')
                        else:
                            messages.warning(request, 'Incomplete office location data. Using default coordinates.')
                    except Exception as e:
                        messages.warning(request, f'Error parsing office location: {str(e)}. Using default coordinates.')
                
                is_remote = False  # Default to office work
                location_string = f"{latitude},{longitude}" if latitude and longitude else ""
                
                if latitude and longitude:
                    try:
                        # Parse user coordinates
                        user_lat = parse_coordinate(latitude)
                        user_lng = parse_coordinate(longitude)
                        
                        if user_lat is not None and user_lng is not None:
                            user_location = (user_lat, user_lng)
                            distance = geodesic(office_location, user_location).meters
                            is_remote = distance > 500
                        else:
                            messages.warning(request, 'Invalid user location coordinates received.')
                            is_remote = True
                    except Exception as e:
                        messages.warning(request, f'Error processing location: {str(e)}')
                        is_remote = True
                
                # Create attendance record without status field
                attendance = Attendance.objects.create(
                    employee=employee,
                    date=today,
                    login_time=timezone.now(),
                    login_location=location_string,
                    is_remote=is_remote,
                    is_late=timezone.now().time() > datetime.strptime('09:30', '%H:%M').time()
                )
                
                # Set additional fields based on work mode
                if is_remote:
                    attendance.notes = "Remote work - Outside 500m radius"
                    attendance.save()
                    
                    # Notify manager
                    manager_user = employee.user.manager
                    if manager_user:
                        try:
                            manager_employee = Employee.objects.get(user=manager_user)
                            Notification.objects.create(
                                recipient=manager_employee,
                                sender=employee,
                                message=f"{employee.user.get_full_name()} logged in remotely",
                                notification_type='attendance',
                                link="/hrm/attendance/monthly/"
                            )
                        except Employee.DoesNotExist:
                            pass
                
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
                
                # Check for early departure
                if timezone.now().time() < datetime.strptime('17:30', '%H:%M').time():
                    attendance.is_early_departure = True
                    early_minutes = (datetime.strptime('17:30', '%H:%M').time().hour * 60 + 
                                   datetime.strptime('17:30', '%H:%M').time().minute) - \
                                  (timezone.now().time().hour * 60 + timezone.now().time().minute)
                    attendance.early_departure_minutes = max(0, early_minutes)
                
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
    total_hours = sum(
        (att.logout_time - att.login_time).total_seconds() / 3600 
        for att in monthly_attendance 
        if att.login_time and att.logout_time
    )
    
    context = {
        'employee': employee,
        'today_attendance': today_attendance,
        'monthly_attendance': monthly_attendance,
        'total_days': total_days,
        'present_days': present_days,
        'remote_days': remote_days,
        'late_days': late_days,
        'total_hours': round(total_hours, 2) if total_hours else 0,
        'current_month': calendar.month_name[current_month],
        'current_year': current_year,
    }
    return render(request, 'hrm/attendance.html', context)

@login_required
def reimbursement_claims(request):
    """Enhanced reimbursement claims management"""
    try:
        employee = Employee.objects.get(user=request.user)
    except Employee.DoesNotExist:
        messages.error(request, 'Employee profile not found.')
        return redirect('hrm_dashboard')
    
    # Get all claims for the employee
    claims = ReimbursementClaim.objects.filter(
        employee=employee
    ).order_by('-created_at')
    
    # Get current month claim or create new one
    today = timezone.now().date()
    current_claim, created = ReimbursementClaim.objects.get_or_create(
        employee=employee,
        month=today.month,
        year=today.year,
        defaults={
            'status': 'draft',
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
    try:
        employee = Employee.objects.get(user=request.user)
    except Employee.DoesNotExist:
        messages.error(request, 'Employee profile not found.')
        return redirect('hrm_dashboard')
    
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
                    'status': 'draft',
                    'submitted_on': None
                }
            )
            
            expense.claim = claim
            expense.save()
            
            # Update claim total
            claim.save()  # This will trigger the total calculation in the model
            
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
    
    if not claim.submit_for_approval():
        messages.error(request, 'Cannot submit this claim. Check status and expenses.')
        return redirect('reimbursement_claims')
    
    # Send notification to approver using CRM hierarchy
    approver_user = claim.employee.user.get_approval_manager()
    if approver_user:
        try:
            approver_employee = Employee.objects.get(user=approver_user)
            Notification.create_reimbursement_notification(claim, approver_employee, 'submission')
        except Employee.DoesNotExist:
            pass
    
    messages.success(request, 'Reimbursement claim submitted successfully!')
    return redirect('reimbursement_claims')

@login_required
def approve_reimbursement(request, claim_id):
    """Enhanced reimbursement approval using CRM hierarchy"""
    claim = get_object_or_404(ReimbursementClaim, id=claim_id)
    
    try:
        approver_employee = Employee.objects.get(user=request.user)
    except Employee.DoesNotExist:
        messages.error(request, 'Employee profile not found.')
        return redirect('hrm_dashboard')
    
    # Check authorization using CRM hierarchy
    if not request.user.can_approve_conversion(claim.employee.user):
        messages.error(request, 'You are not authorized to approve this claim.')
        return redirect('hrm_dashboard')
    
    if request.method == 'POST':
        action = request.POST.get('action')
        comments = request.POST.get('comments', '')
        
        if action == 'approve':
            if claim.approve_by_manager(approver_employee, comments):
                Notification.create_reimbursement_notification(claim, claim.employee, 'approval')
                
                # Check if needs final approval
                if claim.status == 'manager_approved':
                    # Send to top management
                    top_managers = Employee.objects.filter(
                        user__role__in=['top_management', 'business_head']
                    )
                    for tm in top_managers:
                        notification = Notification.objects.create(
                            recipient=tm,
                            sender=approver_employee,
                            message=f"Reimbursement claim from {claim.employee.user.get_full_name()} requires final approval",
                            notification_type='reimbursement',
                            reference_id=str(claim.id),
                            reference_model='ReimbursementClaim',
                            link=f"/hrm/reimbursement/final-approve/{claim.id}/"
                        )
                    message_text = 'Claim approved and sent to top management for final approval.'
                else:
                    message_text = 'Claim approved for reimbursement.'
                
                messages.success(request, message_text)
            else:
                messages.error(request, 'Failed to approve claim.')
        
        elif action == 'reject':
            # Implement rejection logic
            claim.status = 'rejected'
            claim.manager_approved_by = approver_employee
            claim.manager_approved_on = timezone.now()
            claim.manager_comments = comments
            claim.save()
            
            Notification.objects.create(
                recipient=claim.employee,
                sender=approver_employee,
                message=f"Your reimbursement claim has been rejected: {comments}",
                notification_type='reimbursement',
                reference_id=str(claim.id),
                reference_model='ReimbursementClaim'
            )
            
            messages.success(request, 'Claim rejected.')
        
        return redirect('hrm_dashboard')
    
    context = {
        'claim': claim,
        'expenses': claim.expenses.all(),
        'approver_employee': approver_employee,
    }
    return render(request, 'hrm/approve_reimbursement.html', context)

@login_required
def final_approve_reimbursement(request, claim_id):
    """Final approval by top management"""
    claim = get_object_or_404(ReimbursementClaim, id=claim_id)
    
    try:
        approver_employee = Employee.objects.get(user=request.user)
    except Employee.DoesNotExist:
        messages.error(request, 'Employee profile not found.')
        return redirect('hrm_dashboard')
    
    # Check if user is top management
    if request.user.role not in ['top_management', 'business_head']:
        messages.error(request, 'You are not authorized for final approval.')
        return redirect('hrm_dashboard')
    
    if claim.status not in ['manager_approved', 'finance_approved']:
        messages.error(request, 'This claim is not ready for final approval.')
        return redirect('hrm_dashboard')
    
    if request.method == 'POST':
        action = request.POST.get('action')
        comments = request.POST.get('final_comments', '')
        
        if action == 'approve':
            if claim.final_approve(approver_employee, comments):
                Notification.create_reimbursement_notification(claim, claim.employee, 'approval')
                messages.success(request, 'Claim approved for reimbursement.')
            else:
                messages.error(request, 'Failed to approve claim.')
                
        elif action == 'reject':
            claim.status = 'rejected'
            claim.final_approved_by = approver_employee
            claim.final_approved_on = timezone.now()
            claim.final_comments = comments
            claim.save()
            
            Notification.objects.create(
                recipient=claim.employee,
                sender=approver_employee,
                message=f"Your reimbursement claim has been rejected by top management: {comments}",
                notification_type='reimbursement',
                reference_id=str(claim.id),
                reference_model='ReimbursementClaim'
            )
            
            messages.success(request, 'Claim rejected.')
        
        return redirect('hrm_dashboard')
    
    context = {
        'claim': claim,
        'expenses': claim.expenses.all(),
        'approver_employee': approver_employee,
    }
    return render(request, 'hrm/final_approve_reimbursement.html', context)

@login_required
def manage_holidays(request):
    """Manage holidays - Top management only"""
    try:
        employee = Employee.objects.get(user=request.user)
    except Employee.DoesNotExist:
        messages.error(request, 'Employee profile not found.')
        return redirect('hrm_dashboard')
    
    if request.user.role not in ['top_management', 'business_head']:
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
        'employee': employee,
    }
    return render(request, 'hrm/manage_holidays.html', context)

@login_required
def monthly_attendance_report(request):
    """Enhanced monthly attendance report for managers"""
    try:
        employee = Employee.objects.get(user=request.user)
    except Employee.DoesNotExist:
        messages.error(request, 'Employee profile not found.')
        return redirect('hrm_dashboard')
    
    # Check if user can view reports
    if request.user.role not in ['rm_head', 'ops_team_lead', 'business_head', 'business_head_ops', 'top_management']:
        messages.error(request, 'You are not authorized to view attendance reports.')
        return redirect('hrm_dashboard')
    
    # Get current month and year
    today = timezone.now().date()
    current_month = int(request.GET.get('month', today.month))
    current_year = int(request.GET.get('year', today.year))
    
    # Get subordinates using CRM hierarchy
    subordinate_users = request.user.get_accessible_users()
    subordinates = Employee.objects.filter(user__in=subordinate_users).exclude(user=request.user)
    
    # Get attendance data
    attendance_data = []
    for emp in subordinates:
        monthly_attendance = Attendance.objects.filter(
            employee=emp,
            date__year=current_year,
            date__month=current_month
        ).order_by('date')
        
        # Calculate statistics
        total_hours = sum(att.total_hours for att in monthly_attendance)
        
        attendance_data.append({
            'employee': emp,
            'attendance': monthly_attendance,
            'total_hours': round(total_hours, 2),
            'present_days': monthly_attendance.filter(login_time__isnull=False).count(),
            'remote_days': monthly_attendance.filter(work_mode='remote').count(),
            'late_days': monthly_attendance.filter(is_late=True).count(),
            'early_departures': monthly_attendance.filter(is_early_departure=True).count(),
        })
    
    context = {
        'attendance_data': attendance_data,
        'current_month': current_month,
        'current_year': current_year,
        'month_name': calendar.month_name[current_month],
        'employee': employee,
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
    
    try:
        employee = Employee.objects.get(user=request.user)
    except Employee.DoesNotExist:
        return JsonResponse({'error': 'Employee profile not found'})
    
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
            'work_mode': attendance.work_mode if attendance else None,
            'is_late': attendance.is_late if attendance else False,
            'total_hours': round(attendance.total_hours, 2) if attendance else 0,
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
    if request.user.role not in ['top_management', 'business_head']:
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
    if expense.claim.status != 'draft':
        return JsonResponse({'error': 'Cannot delete expense from submitted claim'}, status=400)
    
    claim = expense.claim
    expense.delete()
    
    # Update claim total (this will be handled by the model's save method)
    claim.save()
    
    return JsonResponse({'success': True, 'new_total': float(claim.total_amount)})

@login_required
def view_notification(request, notification_id):
    """View and mark notification as read"""
    notification = get_object_or_404(Notification, id=notification_id, recipient__user=request.user)
    notification.mark_as_read()
    return redirect(notification.action_url) if notification.action_url else redirect('hrm_dashboard')

@require_POST
@login_required
def mark_all_notifications_read(request):
    """Mark all notifications as read"""
    try:
        employee = Employee.objects.get(user=request.user)
        Notification.objects.filter(recipient=employee, is_read=False).update(is_read=True)
        return JsonResponse({'status': 'success'})
    except Employee.DoesNotExist:
        return JsonResponse({'error': 'Employee profile not found'}, status=400)

@login_required
def employee_directory(request):
    """Enhanced employee directory with CRM integration"""
    # Get all employees with their CRM user data
    employees = Employee.objects.all().select_related('user', 'department').order_by('user__role', 'user__last_name')
    departments = Department.objects.all()
    
    # Filtering
    department_id = request.GET.get('department')
    if department_id:
        employees = employees.filter(department_id=department_id)
    
    hierarchy_level = request.GET.get('hierarchy')
    if hierarchy_level:
        employees = employees.filter(user__role=hierarchy_level)  # Use CRM role
    
    search_query = request.GET.get('search')
    if search_query:
        employees = employees.filter(
            Q(user__first_name__icontains=search_query) |
            Q(user__last_name__icontains=search_query) |
            Q(designation__icontains=search_query) |
            Q(employee_id__icontains=search_query) |
            Q(user__username__icontains=search_query)
        )
    
    # Pagination
    paginator = Paginator(employees, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    # Get role choices from CRM User model
    from base.models import ROLE_CHOICES
    
    context = {
        'page_obj': page_obj,
        'departments': departments,
        'hierarchy_choices': ROLE_CHOICES,  # Use CRM role choices
        'current_user': request.user,
    }
    return render(request, 'hrm/employee_directory.html', context)

@login_required
def employee_profile(request, emp_id):
    """Enhanced employee profile view"""
    employee = get_object_or_404(Employee, id=emp_id)
    
    try:
        current_employee = Employee.objects.get(user=request.user)
    except Employee.DoesNotExist:
        messages.error(request, 'Your employee profile not found.')
        return redirect('employee_directory')
    
    # Check if current user can view this profile using CRM hierarchy
    can_view = (
        employee == current_employee or  # Own profile
        request.user.can_access_user_data(employee.user) or  # CRM access rules
        request.user.role in ['top_management', 'business_head']  # Top management
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
        'remote_days': monthly_attendance.filter(work_mode='remote').count(),
        'late_days': monthly_attendance.filter(is_late=True).count(),
        'total_days': monthly_attendance.count(),
        'total_hours': round(sum(att.total_hours for att in monthly_attendance), 2),
    }
    
    # Recent activities
    recent_leaves = LeaveRequest.objects.filter(employee=employee).order_by('-applied_on')[:5]
    recent_attendance = Attendance.objects.filter(employee=employee).order_by('-date')[:10]
    recent_claims = ReimbursementClaim.objects.filter(employee=employee).order_by('-created_at')[:5]
    
    # Team information using CRM
    team_members = []
    if employee.user.role in ['rm_head', 'ops_team_lead', 'business_head', 'business_head_ops']:
        team_member_users = employee.user.get_team_members()
        team_members = Employee.objects.filter(user__in=team_member_users)
    
    context = {
        'employee': employee,
        'current_employee': current_employee,
        'leave_stats': leave_stats,
        'attendance_stats': attendance_stats,
        'recent_leaves': recent_leaves,
        'recent_attendance': recent_attendance,
        'recent_claims': recent_claims,
        'team_members': team_members,
        'current_month': calendar.month_name[current_month],
        'current_year': current_year,
    }
    return render(request, 'hrm/employee_profile.html', context)

@login_required
def reports_dashboard(request):
    """Enhanced reports dashboard for managers and top management"""
    try:
        employee = Employee.objects.get(user=request.user)
    except Employee.DoesNotExist:
        messages.error(request, 'Employee profile not found.')
        return redirect('hrm_dashboard')
    
    # Check authorization using CRM roles
    if request.user.role not in ['top_management', 'business_head', 'business_head_ops', 'rm_head', 'ops_team_lead']:
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
    
    # Get subordinates using CRM hierarchy
    accessible_users = request.user.get_accessible_users()
    subordinates = Employee.objects.filter(user__in=accessible_users).exclude(user=request.user)
    
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
        remote_count=models.Count('id', filter=Q(work_mode='remote')),
        late_count=models.Count('id', filter=Q(is_late=True)),
        early_departure_count=models.Count('id', filter=Q(is_early_departure=True))
    )
    
    # Reimbursement statistics
    reimbursement_data = ReimbursementClaim.objects.filter(
        employee__in=subordinates,
        submitted_on__range=[start_date, end_date]
    ).values('status').annotate(
        count=models.Count('id'),
        total_amount=Sum('total_amount')
    )
    
    # Department-wise statistics
    dept_stats = subordinates.values('department__name').annotate(
        employee_count=models.Count('id')
    )
    
    context = {
        'employee': employee,
        'start_date': start_date,
        'end_date': end_date,
        'subordinates_count': subordinates.count(),
        'leave_data': leave_data,
        'attendance_data': attendance_data,
        'reimbursement_data': reimbursement_data,
        'dept_stats': dept_stats,
    }
    return render(request, 'hrm/reports_dashboard.html', context)

# Utility functions
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
    if request.user.role not in ['top_management', 'business_head']:
        messages.error(request, 'You are not authorized to trigger auto-approval.')
        return redirect('hrm_dashboard')
    
    from .utils import auto_approve_pending_leaves
    approved_count = auto_approve_pending_leaves()
    
    messages.success(request, f'{approved_count} leave requests were auto-approved.')
    return redirect('hrm_dashboard')

# Enhanced AJAX utility views
@login_required
def get_leave_quota(request):
    """Get leave quota for employee using CRM role"""
    try:
        employee = Employee.objects.get(user=request.user)
    except Employee.DoesNotExist:
        return JsonResponse({'error': 'Employee profile not found'})
    
    leave_type_id = request.GET.get('leave_type_id')
    
    if not leave_type_id:
        return JsonResponse({'error': 'Leave type not provided'})
    
    try:
        quota = LeaveQuota.objects.get(
            hierarchy_level=employee.user.role,  # Use CRM role
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
        return JsonResponse({'error': f'Leave quota not found for your role: {employee.user.get_role_display()}'})

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

@login_required
def get_team_attendance_summary(request):
    """Get attendance summary for team members"""
    try:
        employee = Employee.objects.get(user=request.user)
    except Employee.DoesNotExist:
        return JsonResponse({'error': 'Employee profile not found'})
    
    # Check if user can view team data
    if request.user.role not in ['rm_head', 'ops_team_lead', 'business_head', 'business_head_ops', 'top_management']:
        return JsonResponse({'error': 'Unauthorized'})
    
    # Get team members using CRM hierarchy
    team_member_users = request.user.get_team_members()
    team_members = Employee.objects.filter(user__in=team_member_users)
    
    today = timezone.now().date()
    
    # Get today's attendance for team
    team_attendance = []
    for member in team_members:
        attendance = Attendance.objects.filter(employee=member, date=today).first()
        team_attendance.append({
            'employee_name': member.user.get_full_name(),
            'employee_id': member.employee_id,
            'status': attendance.get_status_display() if attendance else 'Absent',
            'login_time': attendance.login_time.strftime('%H:%M') if attendance and attendance.login_time else None,
            'work_mode': attendance.work_mode if attendance else None,
            'is_late': attendance.is_late if attendance else False,
        })
    
    return JsonResponse({'team_attendance': team_attendance})

@login_required
def update_employee_location(request):
    """Update employee office location"""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST method required'})
    
    try:
        employee = Employee.objects.get(user=request.user)
    except Employee.DoesNotExist:
        return JsonResponse({'error': 'Employee profile not found'})
    
    latitude = request.POST.get('latitude')
    longitude = request.POST.get('longitude')
    
    if latitude and longitude:
        employee.office_location = f"{latitude},{longitude}"
        employee.save()
        return JsonResponse({'success': True, 'message': 'Office location updated'})
    
    return JsonResponse({'error': 'Invalid coordinates'})

@login_required
def get_notification_count(request):
    """Get unread notification count"""
    try:
        employee = Employee.objects.get(user=request.user)
        count = Notification.objects.filter(recipient=employee, is_read=False).count()
        return JsonResponse({'count': count})
    except Employee.DoesNotExist:
        return JsonResponse({'count': 0})

@login_required
def leave_balance_summary(request):
    """Get leave balance summary for current user"""
    try:
        employee = Employee.objects.get(user=request.user)
    except Employee.DoesNotExist:
        return JsonResponse({'error': 'Employee profile not found'})
    
    # Get leave quotas for employee's role
    leave_quotas = LeaveQuota.objects.filter(
        hierarchy_level=employee.user.role
    ).select_related('leave_type')
    
    current_year = timezone.now().year
    balance_data = []
    
    for quota in leave_quotas:
        used = LeaveRequest.objects.filter(
            employee=employee,
            leave_type=quota.leave_type,
            start_date__year=current_year,
            status__in=['A', 'P']
        ).aggregate(total=Sum('total_days'))['total'] or 0
        
        balance_data.append({
            'leave_type': quota.leave_type.name,
            'total_quota': quota.quota,
            'used': used,
            'remaining': quota.quota - used,
            'percentage_used': round((used / quota.quota) * 100, 1) if quota.quota > 0 else 0
        })
    
    return JsonResponse({'balance_data': balance_data})