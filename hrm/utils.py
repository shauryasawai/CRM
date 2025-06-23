from django.utils import timezone
from django.db.models import Q
from datetime import datetime, timedelta, date
import logging

logger = logging.getLogger(__name__)

def get_next_approver(employee):
    """
    Get the next approver for an employee's requests based on hierarchy.
    
    Args:
        employee: Employee instance
        
    Returns:
        Employee instance of the next approver or None
    """
    from .models import Employee, LeaveRequest
    
    # First, check if direct reporting manager exists and is available
    if employee.reporting_manager:
        # Check if reporting manager is on leave
        if not employee.reporting_manager.is_on_leave():
            return employee.reporting_manager
        else:
            # If reporting manager is on leave, escalate to their manager
            if employee.reporting_manager.reporting_manager:
                return employee.reporting_manager.reporting_manager
    
    # If no reporting manager or escalation needed, find next level up
    current_hierarchy = employee.hierarchy_level
    
    # Define hierarchy escalation order
    hierarchy_order = ['RM', 'RMH', 'BH', 'TM']
    
    try:
        current_index = hierarchy_order.index(current_hierarchy)
        
        # Look for next level approvers
        for i in range(current_index + 1, len(hierarchy_order)):
            next_level = hierarchy_order[i]
            
            # Find available approvers at next level
            approvers = Employee.objects.filter(
                hierarchy_level=next_level
            ).exclude(id=employee.id)
            
            # Return first available approver (not on leave)
            for approver in approvers:
                if not approver.is_on_leave():
                    return approver
                    
    except ValueError:
        # Current hierarchy not in standard order, find any higher level
        pass
    
    # Fallback: Find any top management who is available
    top_management = Employee.objects.filter(
        hierarchy_level__in=['TM', 'BH']
    ).exclude(id=employee.id)
    
    for tm in top_management:
        if not tm.is_on_leave():
            return tm
    
    return None

def auto_approve_pending_leaves():
    """
    Auto-approve pending leaves when manager is on extended leave (>3 days).
    This function should be called periodically (e.g., daily cron job).
    
    Returns:
        int: Number of leaves auto-approved
    """
    from .models import LeaveRequest, Employee, Notification
    
    today = timezone.now().date()
    auto_approved_count = 0
    
    # Get all pending leave requests
    pending_leaves = LeaveRequest.objects.filter(
        status='P'
    ).select_related('employee', 'employee__reporting_manager')
    
    for leave_request in pending_leaves:
        employee = leave_request.employee
        manager = employee.reporting_manager
        
        if not manager:
            continue
            
        # Check if manager is on extended leave (>3 days)
        manager_leaves = LeaveRequest.objects.filter(
            employee=manager,
            status='A',
            start_date__lte=today,
            end_date__gte=today
        )
        
        for manager_leave in manager_leaves:
            # Calculate duration of manager's leave
            leave_duration = (manager_leave.end_date - manager_leave.start_date).days + 1
            
            # Check how long the leave request has been pending
            pending_duration = (today - leave_request.applied_on.date()).days
            
            # Auto-approve if manager is on leave >3 days and request is pending >2 days
            if leave_duration > 3 and pending_duration > 2:
                # Find next approver in hierarchy
                next_approver = get_next_approver(employee)
                
                if next_approver:
                    # Auto-approve the leave
                    leave_request.status = 'A'
                    leave_request.processed_by = next_approver
                    leave_request.processed_on = timezone.now()
                    leave_request.manager_comments = f"Auto-approved due to manager ({manager.user.get_full_name()}) being on extended leave"
                    leave_request.save()
                    
                    # Create notifications
                    Notification.objects.create(
                        recipient=employee,
                        message=f"Your {leave_request.leave_type.name} leave has been auto-approved due to manager unavailability",
                        link=f"/hrm/leave/view/{leave_request.id}/"
                    )
                    
                    Notification.objects.create(
                        recipient=next_approver,
                        message=f"Leave request from {employee.user.get_full_name()} was auto-approved under your authority",
                        link=f"/hrm/leave/view/{leave_request.id}/"
                    )
                    
                    auto_approved_count += 1
                    
                    logger.info(f"Auto-approved leave request {leave_request.id} for {employee.user.get_full_name()}")
                    break
    
    return auto_approved_count

def calculate_working_days(start_date, end_date, exclude_weekends=True, exclude_holidays=True):
    """
    Calculate working days between two dates.
    
    Args:
        start_date: Start date
        end_date: End date
        exclude_weekends: Whether to exclude weekends (default: True)
        exclude_holidays: Whether to exclude holidays (default: True)
        
    Returns:
        int: Number of working days
    """
    from .models import Holiday
    
    if start_date > end_date:
        return 0
    
    total_days = (end_date - start_date).days + 1
    working_days = total_days
    
    # Exclude weekends
    if exclude_weekends:
        current_date = start_date
        weekend_days = 0
        while current_date <= end_date:
            if current_date.weekday() == 6:  # Sunday
                weekend_days += 1
            current_date += timedelta(days=1)
        working_days -= weekend_days
    
    # Exclude holidays
    if exclude_holidays:
        holidays_count = Holiday.objects.filter(
            date__range=[start_date, end_date]
        ).count()
        working_days -= holidays_count
    
    return max(working_days, 1)  # At least 1 day

def check_leave_quota(employee, leave_type, requested_days, start_date):
    """
    Check if employee has sufficient leave quota.
    
    Args:
        employee: Employee instance
        leave_type: LeaveType instance
        requested_days: Number of days requested
        start_date: Start date of leave
        
    Returns:
        dict: {'valid': bool, 'message': str, 'remaining': int}
    """
    from .models import LeaveQuota, LeaveRequest
    from django.db.models import Sum
    
    try:
        quota = LeaveQuota.objects.get(
            hierarchy_level=employee.hierarchy_level,
            leave_type=leave_type
        )
    except LeaveQuota.DoesNotExist:
        return {
            'valid': False,
            'message': f'Leave quota not defined for your hierarchy level',
            'remaining': 0
        }
    
    # Calculate used leaves for the year
    current_year = start_date.year
    used_leaves = LeaveRequest.objects.filter(
        employee=employee,
        leave_type=leave_type,
        start_date__year=current_year,
        status__in=['A', 'P']  # Approved or Pending
    ).aggregate(total=Sum('total_days'))['total'] or 0
    
    remaining_quota = quota.quota - used_leaves
    
    if requested_days > remaining_quota:
        return {
            'valid': False,
            'message': f'Insufficient {leave_type.name} quota. Available: {remaining_quota} days',
            'remaining': remaining_quota
        }
    
    return {
        'valid': True,
        'message': 'Sufficient quota available',
        'remaining': remaining_quota - requested_days
    }

def validate_leave_dates(employee, start_date, end_date, exclude_leave_id=None):
    """
    Validate leave dates for conflicts and business rules.
    
    Args:
        employee: Employee instance
        start_date: Start date of leave
        end_date: End date of leave
        exclude_leave_id: Leave ID to exclude from conflict check (for updates)
        
    Returns:
        dict: {'valid': bool, 'message': str}
    """
    from .models import LeaveRequest
    
    # Check if dates are valid
    if start_date > end_date:
        return {'valid': False, 'message': 'Start date cannot be after end date'}
    
    # Check if start date is in the past (allow today)
    today = timezone.now().date()
    if start_date < today:
        return {'valid': False, 'message': 'Cannot apply for leave in the past'}
    
    # Check for overlapping leave requests
    overlapping_query = Q(
        employee=employee,
        status__in=['P', 'A'],  # Pending or Approved
        start_date__lte=end_date,
        end_date__gte=start_date
    )
    
    if exclude_leave_id:
        overlapping_query &= ~Q(id=exclude_leave_id)
    
    overlapping_leaves = LeaveRequest.objects.filter(overlapping_query)
    
    if overlapping_leaves.exists():
        return {
            'valid': False, 
            'message': 'You have overlapping leave requests for the selected dates'
        }
    
    # Check minimum notice period (e.g., 2 days advance notice)
    notice_period = 2
    if (start_date - today).days < notice_period:
        return {
            'valid': False,
            'message': f'Minimum {notice_period} days advance notice required'
        }
    
    return {'valid': True, 'message': 'Dates are valid'}

def send_leave_notification(leave_request, action, approver=None):
    """
    Send notifications for leave-related actions.
    
    Args:
        leave_request: LeaveRequest instance
        action: Action type ('applied', 'approved', 'rejected', 'cancelled')
        approver: Employee who performed the action (optional)
    """
    from .models import Notification
    
    employee = leave_request.employee
    leave_type = leave_request.leave_type.name
    
    if action == 'applied':
        # Notify manager
        next_approver = get_next_approver(employee)
        if next_approver:
            Notification.objects.create(
                recipient=next_approver,
                message=f"{employee.user.get_full_name()} has applied for {leave_type} leave from {leave_request.start_date} to {leave_request.end_date}",
                link=f"/hrm/leave/approve/{leave_request.id}/"
            )
    
    elif action in ['approved', 'rejected', 'cancelled']:
        # Notify employee
        status_text = action
        Notification.objects.create(
            recipient=employee,
            message=f"Your {leave_type} leave request has been {status_text}",
            link=f"/hrm/leave/view/{leave_request.id}/"
        )
        
        # If approved, also notify HR/Admin
        if action == 'approved':
            from .models import Employee
            hr_users = Employee.objects.filter(
                hierarchy_level__in=['TM', 'BH']
            )
            for hr_user in hr_users:
                if hr_user != approver:  # Don't notify the approver
                    Notification.objects.create(
                        recipient=hr_user,
                        message=f"{employee.user.get_full_name()}'s {leave_type} leave has been approved",
                        link=f"/hrm/leave/view/{leave_request.id}/"
                    )

def send_reimbursement_notification(claim, action, approver=None):
    """
    Send notifications for reimbursement-related actions.
    
    Args:
        claim: ReimbursementClaim instance
        action: Action type ('submitted', 'manager_approved', 'final_approved', 'rejected')
        approver: Employee who performed the action (optional)
    """
    from .models import Notification, Employee
    import calendar
    
    employee = claim.employee
    month_name = calendar.month_name[claim.month]
    
    if action == 'submitted':
        # Notify manager
        if employee.reporting_manager:
            Notification.objects.create(
                recipient=employee.reporting_manager,
                message=f"{employee.user.get_full_name()} has submitted reimbursement claim for {month_name} {claim.year}",
                link=f"/hrm/reimbursement/approve/{claim.id}/"
            )
    
    elif action == 'manager_approved':
        # Notify employee
        Notification.objects.create(
            recipient=employee,
            message=f"Your reimbursement claim for {month_name} {claim.year} has been approved by manager",
            link=f"/hrm/reimbursement/view/{claim.id}/"
        )
        
        # Notify top management
        top_managers = Employee.objects.filter(hierarchy_level__in=['TM', 'BH'])
        for tm in top_managers:
            if tm != approver:
                Notification.objects.create(
                    recipient=tm,
                    message=f"Reimbursement claim from {employee.user.get_full_name()} awaiting final approval",
                    link=f"/hrm/reimbursement/final-approve/{claim.id}/"
                )
    
    elif action in ['final_approved', 'rejected']:
        # Notify employee
        status_text = 'approved for reimbursement' if action == 'final_approved' else 'rejected'
        Notification.objects.create(
            recipient=employee,
            message=f"Your reimbursement claim for {month_name} {claim.year} has been {status_text}",
            link=f"/hrm/reimbursement/view/{claim.id}/"
        )

def calculate_attendance_summary(employee, start_date, end_date):
    """
    Calculate attendance summary for an employee within a date range.
    
    Args:
        employee: Employee instance
        start_date: Start date
        end_date: End date
        
    Returns:
        dict: Attendance summary statistics
    """
    from .models import Attendance
    
    attendance_records = Attendance.objects.filter(
        employee=employee,
        date__range=[start_date, end_date]
    )
    
    total_days = attendance_records.count()
    present_days = attendance_records.filter(login_time__isnull=False).count()
    remote_days = attendance_records.filter(is_remote=True).count()
    late_days = attendance_records.filter(is_late=True).count()
    
    # Calculate total hours
    total_hours = 0
    for record in attendance_records:
        if record.login_time and record.logout_time:
            duration = record.logout_time - record.login_time
            total_hours += duration.total_seconds() / 3600
    
    return {
        'total_days': total_days,
        'present_days': present_days,
        'absent_days': total_days - present_days,
        'remote_days': remote_days,
        'late_days': late_days,
        'total_hours': round(total_hours, 2),
        'average_hours': round(total_hours / max(present_days, 1), 2)
    }

def is_within_office_radius(user_location, office_location, radius_meters=500):
    """
    Check if user location is within office radius.
    
    Args:
        user_location: Tuple of (latitude, longitude)
        office_location: Tuple of (latitude, longitude)
        radius_meters: Radius in meters (default: 500)
        
    Returns:
        bool: True if within radius
    """
    try:
        from geopy.distance import geodesic
        distance = geodesic(office_location, user_location).meters
        return distance <= radius_meters
    except Exception as e:
        logger.error(f"Error calculating distance: {e}")
        return False

def get_monthly_calendar_data(employee, year, month):
    """
    Get calendar data for a specific month including holidays, leaves, and attendance.
    
    Args:
        employee: Employee instance
        year: Year
        month: Month
        
    Returns:
        dict: Calendar data with daily information
    """
    from .models import Holiday, LeaveRequest, Attendance
    import calendar
    
    # Get month calendar
    cal = calendar.monthcalendar(year, month)
    
    # Get data for the month
    holidays = Holiday.objects.filter(date__year=year, date__month=month)
    leave_requests = LeaveRequest.objects.filter(
        employee=employee,
        start_date__year=year,
        start_date__month=month
    ).select_related('leave_type')
    attendance_records = Attendance.objects.filter(
        employee=employee,
        date__year=year,
        date__month=month
    )
    
    # Build calendar data
    calendar_data = []
    today = timezone.now().date()
    
    for week in cal:
        week_data = []
        for day in week:
            if day == 0:
                week_data.append(None)
                continue
            
            day_date = date(year, month, day)
            
            # Get day-specific data
            day_holiday = holidays.filter(date=day_date).first()
            day_attendance = attendance_records.filter(date=day_date).first()
            day_leaves = leave_requests.filter(
                start_date__lte=day_date,
                end_date__gte=day_date
            )
            
            day_info = {
                'day': day,
                'date': day_date,
                'is_today': day_date == today,
                'is_past': day_date < today,
                'is_sunday': day_date.weekday() == 6,
                'is_holiday': bool(day_holiday),
                'holiday_name': day_holiday.name if day_holiday else None,
                'attendance': day_attendance,
                'leaves': list(day_leaves),
                'has_leave': day_leaves.exists(),
                'is_present': bool(day_attendance and day_attendance.login_time),
                'is_remote': bool(day_attendance and day_attendance.is_remote),
                'is_late': bool(day_attendance and day_attendance.is_late),
            }
            
            week_data.append(day_info)
        calendar_data.append(week_data)
    
    return calendar_data

def cleanup_old_notifications(days=30):
    """
    Clean up old read notifications.
    
    Args:
        days: Number of days to keep (default: 30)
        
    Returns:
        int: Number of notifications deleted
    """
    from .models import Notification
    
    cutoff_date = timezone.now() - timedelta(days=days)
    old_notifications = Notification.objects.filter(
        is_read=True,
        created_at__lt=cutoff_date
    )
    
    count = old_notifications.count()
    old_notifications.delete()
    
    return count

def generate_employee_report(employee, start_date, end_date):
    """
    Generate comprehensive employee report.
    
    Args:
        employee: Employee instance
        start_date: Start date
        end_date: End date
        
    Returns:
        dict: Comprehensive employee report
    """
    from .models import LeaveRequest, ReimbursementClaim
    from django.db.models import Sum
    
    # Attendance summary
    attendance_summary = calculate_attendance_summary(employee, start_date, end_date)
    
    # Leave summary
    leaves_taken = LeaveRequest.objects.filter(
        employee=employee,
        start_date__range=[start_date, end_date],
        status='A'
    ).aggregate(total=Sum('total_days'))['total'] or 0
    
    # Reimbursement summary
    reimbursements = ReimbursementClaim.objects.filter(
        employee=employee,
        submitted_on__range=[start_date, end_date]
    ).aggregate(total=Sum('total_amount'))['total'] or 0
    
    return {
        'employee': employee,
        'period': {'start': start_date, 'end': end_date},
        'attendance': attendance_summary,
        'leaves_taken': leaves_taken,
        'reimbursements_claimed': float(reimbursements),
        'generated_on': timezone.now()
    }