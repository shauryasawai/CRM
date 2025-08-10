import cloudinary
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

# Robust fix for the dashboard list.count() error

# Fixed Dashboard to Show RM Head Reimbursements for Top Management

@login_required
def hrm_dashboard(request):
    """Enhanced dashboard with proper approval flow visibility - Fixed QuerySet issues"""
    try:
        employee = Employee.objects.get(user=request.user)
    except Employee.DoesNotExist:
        # Create employee profile if doesn't exist
        employee = Employee.objects.create(
            user=request.user,
            designation=getattr(request.user, 'get_role_display', lambda: 'Employee')(),
            date_of_joining=timezone.now().date(),
            hierarchy_level=getattr(request.user, 'role', 'employee')
        )
    
    # Auto-approve pending leaves (run this check)
    try:
        auto_approve_pending_leaves()
    except:
        pass  # Don't break if auto-approve fails
    
    user_role = getattr(request.user, 'role', 'employee')
    
    # Define what roles this user can approve based on the new hierarchy
    approval_authority = {
        'top_management': ['ops_exec', 'employee', 'intern', 'ops_team_lead', 'rm_head', 'business_head_ops'],
        'business_head': ['ops_exec', 'employee', 'intern', 'ops_team_lead', 'rm_head', 'business_head_ops'],
        'ops_team_lead': ['ops_exec'],  # First level approval for ops_exec
        'rm_head': ['employee', 'intern'],  # First level approval for employee/intern
        'business_head_ops': [],  # No direct reports in reimbursement hierarchy
    }
    
    can_approve_roles = approval_authority.get(user_role, [])
    
    print(f"DEBUG: User {request.user.get_full_name()} (Role: {user_role})")
    print(f"DEBUG: Can approve roles: {can_approve_roles}")
    
    # Initialize subordinate employee IDs list to avoid QuerySet union issues
    subordinate_employee_ids = []
    
    if user_role in ['top_management', 'business_head']:
        # Top management can see all employees for final approvals
        subordinate_employee_ids = list(
            Employee.objects.exclude(user=request.user).values_list('id', flat=True)
        )
        print(f"DEBUG: Top management - all employee IDs: {len(subordinate_employee_ids)}")
        
    elif can_approve_roles:
        # Get employees that this user can approve - convert to IDs list
        role_based_ids = list(
            Employee.objects.filter(user__role__in=can_approve_roles).values_list('id', flat=True)
        )
        subordinate_employee_ids.extend(role_based_ids)
        print(f"DEBUG: Role-based subordinate IDs: {len(role_based_ids)}")
        
        # Also try CRM hierarchy as fallback - convert to IDs list
        try:
            if hasattr(request.user, 'get_accessible_users'):
                accessible_users = request.user.get_accessible_users()
                if hasattr(accessible_users, 'values_list'):
                    accessible_user_ids = list(accessible_users.values_list('id', flat=True))
                    # Convert user IDs to employee IDs
                    crm_employee_ids = list(
                        Employee.objects.filter(user__id__in=accessible_user_ids).values_list('id', flat=True)
                    )
                    subordinate_employee_ids.extend(crm_employee_ids)
                    print(f"DEBUG: Added CRM employee IDs: {len(crm_employee_ids)}")
        except Exception as e:
            print(f"DEBUG: CRM integration error: {e}")
    
    # Remove duplicates and convert to final employee IDs list
    subordinate_employee_ids = list(set(subordinate_employee_ids))
    
    # Create a simple QuerySet for subordinates using the ID list
    subordinates = Employee.objects.filter(id__in=subordinate_employee_ids)
    
    print(f"DEBUG: Final subordinate count: {len(subordinate_employee_ids)}")
    
    # Dashboard statistics - items requiring approval
    try:
        pending_leaves = LeaveRequest.objects.filter(
            employee_id__in=subordinate_employee_ids,  # Use ID list instead of QuerySet
            status='P'
        ).count()
        print(f"DEBUG: Pending leaves count: {pending_leaves}")
    except Exception as e:
        print(f"DEBUG: Error counting pending leaves: {e}")
        pending_leaves = 0
    
    # Enhanced reimbursement counting based on approval flow
    try:
        if user_role in ['top_management', 'business_head']:
            # Top management sees:
            # 1. All 'P' status claims (can do direct approval)
            # 2. All 'MA' status claims (needs final approval)
            pending_reimbursements = ReimbursementClaim.objects.filter(
                status__in=['P', 'MA']
            ).exclude(status='D').count()
            
            print(f"DEBUG: Top management - all pending reimbursements: {pending_reimbursements}")
            
            # Break down by status for debugging
            p_status_count = ReimbursementClaim.objects.filter(status='P').count()
            ma_status_count = ReimbursementClaim.objects.filter(status='MA').count()
            print(f"DEBUG: P status: {p_status_count}, MA status: {ma_status_count}")
            
        elif user_role in ['ops_team_lead', 'rm_head']:
            # Team leads see only 'P' status claims from their direct reports
            pending_reimbursements = ReimbursementClaim.objects.filter(
                employee__user__role__in=can_approve_roles,
                status='P'  # Only first-level approvals
            ).count()
            
            print(f"DEBUG: {user_role} - first level approvals: {pending_reimbursements}")
            
        else:
            # Other roles have no approval authority
            pending_reimbursements = 0
            
    except Exception as e:
        print(f"DEBUG: Error counting pending reimbursements: {e}")
        pending_reimbursements = 0
    
    # Get items requiring approval based on new flow
    try:
        leaves_to_approve = LeaveRequest.objects.filter(
            employee_id__in=subordinate_employee_ids,  # Use ID list instead of QuerySet
            status__in=['P', 'CR']
        ).select_related('employee__user', 'leave_type').order_by('-applied_on')[:10]
    except Exception as e:
        print(f"DEBUG: Error getting leaves to approve: {e}")
        leaves_to_approve = []
    
    try:
        if user_role in ['top_management', 'business_head']:
            # Top management sees all reimbursements needing any approval
            reimbursements_to_approve = ReimbursementClaim.objects.filter(
                status__in=['P', 'MA']
            ).select_related('employee__user').order_by('-submitted_on')[:15]
            
        elif user_role in ['ops_team_lead', 'rm_head']:
            # Team leads see only first-level approvals for their reports
            reimbursements_to_approve = ReimbursementClaim.objects.filter(
                employee__user__role__in=can_approve_roles,
                status='P'  # Only pending first approval
            ).select_related('employee__user').order_by('-submitted_on')[:10]
            
        else:
            reimbursements_to_approve = []
            
        print(f"DEBUG: Reimbursements to approve: {len(reimbursements_to_approve)}")
            
    except Exception as e:
        print(f"DEBUG: Error getting reimbursements to approve: {e}")
        reimbursements_to_approve = []
    
    # Get team activities
    try:
        if user_role in ['top_management', 'business_head']:
            all_team_leaves = LeaveRequest.objects.all().select_related(
                'employee__user', 'leave_type'
            ).order_by('-applied_on')[:25]
            
            all_team_reimbursements = ReimbursementClaim.objects.exclude(
                status='D'
            ).select_related('employee__user').order_by('-created_at')[:25]
            
        else:
            all_team_leaves = LeaveRequest.objects.filter(
                employee_id__in=subordinate_employee_ids  # Use ID list instead of QuerySet
            ).select_related('employee__user', 'leave_type').order_by('-applied_on')[:20]
            
            all_team_reimbursements = ReimbursementClaim.objects.filter(
                employee_id__in=subordinate_employee_ids  # Use ID list instead of QuerySet
            ).exclude(status='D').select_related('employee__user').order_by('-created_at')[:20]
            
    except Exception as e:
        print(f"DEBUG: Error getting team activities: {e}")
        all_team_leaves = []
        all_team_reimbursements = []
    
    # Get employee's personal data (unchanged)
    try:
        recent_attendance = Attendance.objects.filter(employee=employee).order_by('-date')[:5]
        my_leave_requests = LeaveRequest.objects.filter(employee=employee).order_by('-applied_on')[:5]
        notifications = Notification.objects.filter(recipient=employee, is_read=False).order_by('-created_at')[:5]
    except Exception:
        recent_attendance = []
        my_leave_requests = []
        notifications = []
    
    # Monthly attendance summary (unchanged)
    today = timezone.now().date()
    try:
        current_month_attendance = Attendance.objects.filter(
            employee=employee,
            date__year=today.year,
            date__month=today.month
        )
        total_working_days = current_month_attendance.count()
        present_days = current_month_attendance.filter(login_time__isnull=False).count()
        remote_days = current_month_attendance.filter(is_remote=True).count()
    except Exception:
        total_working_days = 0
        present_days = 0
        remote_days = 0

    # Leave balance summary (unchanged)
    leave_balance_summary = []
    try:
        if hasattr(employee, 'annual_leave_balance'):
            leave_balance_summary = [
                {'type': 'Annual Leave', 'balance': getattr(employee, 'annual_leave_balance', 0)},
                {'type': 'Casual Leave', 'balance': getattr(employee, 'casual_leave_balance', 0)},
                {'type': 'Sick Leave', 'balance': getattr(employee, 'sick_leave_balance', 0)},
            ]
    except Exception:
        pass
    
    # Safe subordinates count
    subordinates_count = len(subordinate_employee_ids)
    
    # Special sections for different roles
    special_sections = {}
    
    if user_role in ['top_management', 'business_head']:
        # RM Head and Team Lead claims needing attention
        try:
            rm_head_claims = ReimbursementClaim.objects.filter(
                employee__user__role='rm_head',
                status__in=['P', 'MA']
            ).select_related('employee__user').order_by('-submitted_on')[:5]
            
            team_lead_claims = ReimbursementClaim.objects.filter(
                employee__user__role='ops_team_lead',
                status__in=['P', 'MA']
            ).select_related('employee__user').order_by('-submitted_on')[:5]
            
            # Claims needing final approval (MA status)
            final_approval_claims = ReimbursementClaim.objects.filter(
                status='MA'
            ).select_related('employee__user').order_by('-submitted_on')[:10]
            
            special_sections = {
                'rm_head_claims': rm_head_claims,
                'team_lead_claims': team_lead_claims,
                'final_approval_claims': final_approval_claims,
                'rm_head_claims_count': rm_head_claims.count(),
                'team_lead_claims_count': team_lead_claims.count(),
                'final_approval_claims_count': final_approval_claims.count(),
            }
            
        except Exception as e:
            print(f"DEBUG: Error getting special sections for top management: {e}")
    
    elif user_role in ['ops_team_lead', 'rm_head']:
        # Show claims from direct reports needing first approval
        try:
            direct_report_claims = ReimbursementClaim.objects.filter(
                employee__user__role__in=can_approve_roles,
                status='P'
            ).select_related('employee__user').order_by('-submitted_on')[:10]
            
            special_sections = {
                'direct_report_claims': direct_report_claims,
                'direct_report_claims_count': direct_report_claims.count(),
                'approval_level': 'first_level',
            }
            
        except Exception as e:
            print(f"DEBUG: Error getting special sections for {user_role}: {e}")
    
    # Debug final counts
    print(f"DEBUG: Final dashboard counts:")
    print(f"  - User role: {user_role}")
    print(f"  - Can approve roles: {can_approve_roles}")
    print(f"  - Subordinates: {subordinates_count}")
    print(f"  - Pending leaves: {pending_leaves}")
    print(f"  - Pending reimbursements: {pending_reimbursements}")
    print(f"  - Reimbursements to approve: {len(reimbursements_to_approve)}")
    
    context = {
        'employee': employee,
        'subordinates_count': subordinates_count,
        'pending_leaves': pending_leaves,
        'pending_reimbursements': pending_reimbursements,
        'leaves_to_approve': leaves_to_approve,
        'reimbursements_to_approve': reimbursements_to_approve,
        'all_team_leaves': all_team_leaves,
        'all_team_reimbursements': all_team_reimbursements,
        'recent_attendance': recent_attendance,
        'my_leave_requests': my_leave_requests,
        'notifications': notifications,
        'total_working_days': total_working_days,
        'present_days': present_days,
        'remote_days': remote_days,
        'leave_balance_summary': leave_balance_summary,
        'can_approve_leaves': user_role in ['rm_head', 'ops_team_lead', 'business_head', 'business_head_ops', 'top_management'],
        'can_approve_reimbursements': bool(can_approve_roles) or user_role in ['top_management', 'business_head'],
        'is_top_management': user_role in ['top_management', 'business_head'],
        'is_team_lead': user_role in ['ops_team_lead', 'rm_head'],
        'user_role': user_role,
        'can_approve_roles': can_approve_roles,
        # Add special sections
        **special_sections,
    }
    return render(request, 'hrm/dashboard.html', context)

# Debug helper function to check RM Head reimbursement visibility
@login_required
def debug_rm_head_reimbursements(request):
    """Debug function to check RM Head reimbursement visibility"""
    if request.user.role not in ['top_management', 'business_head']:
        return JsonResponse({'error': 'Access denied'})
    
    # Get all RM Head employees
    rm_head_employees = Employee.objects.filter(user__role='rm_head')
    
    # Get all their reimbursement claims
    rm_head_claims = ReimbursementClaim.objects.filter(
        employee__in=rm_head_employees
    ).select_related('employee__user')
    
    debug_data = {
        'rm_head_employees_count': rm_head_employees.count(),
        'rm_head_employees': [
            {
                'name': emp.user.get_full_name(),
                'role': emp.user.role,
                'id': emp.id
            } for emp in rm_head_employees
        ],
        'rm_head_claims_total': rm_head_claims.count(),
        'rm_head_claims': [
            {
                'employee': claim.employee.user.get_full_name(),
                'status': claim.status,
                'amount': float(claim.total_amount),
                'month': claim.month,
                'year': claim.year,
                'submitted_on': claim.submitted_on.isoformat() if claim.submitted_on else None
            } for claim in rm_head_claims
        ],
        'pending_rm_head_claims': rm_head_claims.filter(status__in=['P', 'MA']).count(),
    }
    
    return JsonResponse(debug_data, indent=2)

def get_subordinate_roles(user_role):
    """Get roles that are subordinate to the given role"""
    role_hierarchy = {
        'top_management': ['business_head', 'business_head_ops', 'rm_head', 'ops_team_lead', 'employee', 'intern'],
        'business_head': ['business_head_ops', 'rm_head', 'ops_team_lead', 'employee', 'intern'],
        'business_head_ops': ['ops_team_lead', 'employee', 'intern'],
        'rm_head': ['employee', 'intern'],
        'ops_team_lead': ['employee', 'intern'],
    }
    return role_hierarchy.get(user_role, [])

@login_required
def leave_calendar(request):
    """Optimized leave calendar with improved performance"""
    try:
        employee = Employee.objects.get(user=request.user)
    except Employee.DoesNotExist:
        messages.error(request, 'Employee profile not found. Please contact HR.')
        return redirect('hrm_dashboard')
    
    # Get current month/year or from request
    today = timezone.now().date()
    year = int(request.GET.get('year', today.year))
    month = int(request.GET.get('month', today.month))
    
    # Calculate month boundaries
    month_start = date(year, month, 1)
    if month == 12:
        month_end = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        month_end = date(year, month + 1, 1) - timedelta(days=1)
    
    # Single query for all month data with select_related/prefetch_related
    holidays = Holiday.objects.filter(
        date__range=[month_start, month_end]
    ).values('date', 'name')
    
    leave_requests = LeaveRequest.objects.filter(
        employee=employee,
        start_date__lte=month_end,
        end_date__gte=month_start
    ).select_related('leave_type').values(
        'start_date', 'end_date', 'status', 'leave_type__name'
    )
    
    attendance_records = Attendance.objects.filter(
        employee=employee,
        date__range=[month_start, month_end]
    ).values('date', 'login_time', 'logout_time', 'is_remote', 'notes')
    
    # Convert to dictionaries for O(1) lookup
    holidays_dict = {h['date']: h['name'] for h in holidays}
    attendance_dict = {a['date']: a for a in attendance_records}
    
    # Process leave requests into date ranges
    leave_dict = {}
    for leave in leave_requests:
        current_date = leave['start_date']
        while current_date <= leave['end_date']:
            if current_date not in leave_dict:
                leave_dict[current_date] = []
            leave_dict[current_date].append({
                'status': leave['status'],
                'leave_type_name': leave['leave_type__name']
            })
            current_date += timedelta(days=1)
    
    # Generate calendar data efficiently
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
                'is_holiday': day_date in holidays_dict,
                'holiday_name': holidays_dict.get(day_date),
                'is_weekend': day_date.weekday() >= 5,  # Saturday=5, Sunday=6
                'leave_requests': leave_dict.get(day_date, []),
                'attendance': attendance_dict.get(day_date),
                'is_today': day_date == today,
                'is_past': day_date < today,
            }
            week_data.append(day_info)
        calendar_data.append(week_data)
    
    # Get leave quotas efficiently
    leave_quotas = LeaveQuota.objects.filter(
        hierarchy_level=employee.user.role
    ).select_related('leave_type').values(
        'leave_type__id', 'leave_type__name', 'quota'
    )
    
    # Calculate used leaves for current year in single query
    year_start = date(year, 1, 1)
    year_end = date(year, 12, 31)
    
    used_leaves = LeaveRequest.objects.filter(
        employee=employee,
        start_date__year=year,
        status__in=['A', 'P']
    ).values('leave_type__id').annotate(
        total_used=Sum('total_days')
    )
    
    # Convert to dict for O(1) lookup
    used_dict = {item['leave_type__id']: item['total_used'] for item in used_leaves}
    
    # Build quota data
    quota_data = []
    for quota in leave_quotas:
        used = used_dict.get(quota['leave_type__id'], 0)
        quota_data.append({
            'leave_type': {'name': quota['leave_type__name']},
            'total_quota': quota['quota'],
            'used': used,
            'remaining': quota['quota'] - used
        })
    
    # Calculate navigation dates
    if month == 1:
        prev_month, prev_year = 12, year - 1
    else:
        prev_month, prev_year = month - 1, year
        
    if month == 12:
        next_month, next_year = 1, year + 1
    else:
        next_month, next_year = month + 1, year
    
    context = {
        'employee': employee,
        'calendar_data': calendar_data,
        'year': year,
        'month': month,
        'month_name': calendar.month_name[month],
        'quota_data': quota_data,
        'prev_month': prev_month,
        'next_month': next_month,
        'prev_year': prev_year,
        'next_year': next_year,
        'today_month': today.month,
        'today_year': today.year,
        'weekdays': ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
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
    """Enhanced leave approval - Top Management can directly approve RM Head leaves"""
    leave = get_object_or_404(LeaveRequest, id=leave_id)
    
    try:
        approver_employee = Employee.objects.get(user=request.user)
    except Employee.DoesNotExist:
        messages.error(request, 'Employee profile not found.')
        return redirect('hrm_dashboard')
    
    # Enhanced authorization logic
    can_approve = False
    is_direct_top_management_approval = False
    
    # Top management can approve ANYONE directly (including RM Heads)
    if request.user.role in ['top_management', 'business_head']:
        can_approve = True
        # Check if this is a direct approval of RM Head by top management
        if leave.employee.user.role == 'rm_head':
            is_direct_top_management_approval = True
            print(f"DEBUG: Top management direct approval for RM Head {leave.employee.user.get_full_name()}")
    
    # Regular hierarchy check for non-top-management
    elif hasattr(request.user, 'can_approve_conversion'):
        try:
            can_approve = request.user.can_approve_conversion(leave.employee.user)
        except Exception as e:
            print(f"DEBUG: CRM approval check failed: {e}")
            can_approve = leave.employee.user.role in get_subordinate_roles(request.user.role)
    else:
        # Fallback authorization check
        if leave.employee.user.role in get_subordinate_roles(request.user.role):
            can_approve = True
        if hasattr(leave.employee.user, 'manager') and leave.employee.user.manager == request.user:
            can_approve = True
    
    if not can_approve:
        messages.error(request, 'You are not authorized to approve this leave request.')
        return redirect('all_leave_requests')
    
    # Debug information
    print(f"DEBUG: Leave ID {leave.id} - Employee: {leave.employee.user.get_full_name()} (Role: {leave.employee.user.role})")
    print(f"DEBUG: Approver: {approver_employee.user.get_full_name()} (Role: {request.user.role})")
    print(f"DEBUG: Direct top management approval: {is_direct_top_management_approval}")
    
    if request.method == 'POST':
        action = request.POST.get('action')
        comments = request.POST.get('manager_comments', '')
        
        if action == 'approve':
            try:
                # Enhanced approval logic
                if hasattr(leave, 'approve') and callable(leave.approve):
                    success = leave.approve(approver_employee, comments)
                else:
                    # Manual approval
                    leave.status = 'A'  # Approved
                    leave.processed_by = approver_employee
                    leave.processed_on = timezone.now()
                    leave.manager_comments = comments
                    
                    # For direct top management approval of RM Head
                    if is_direct_top_management_approval:
                        leave.final_approved_by = approver_employee
                        leave.final_approved_on = timezone.now()
                        leave.final_comments = f"Direct approval by top management: {comments}"
                    
                    leave.save()
                    success = True
                
                if success:
                    # Create approval notification
                    try:
                        if hasattr(Notification, 'create_leave_notification'):
                            Notification.create_leave_notification(leave, leave.employee, 'approval')
                        else:
                            Notification.objects.create(
                                recipient=leave.employee,
                                sender=approver_employee,
                                message=f"Your leave request for {leave.leave_type.name} ({leave.start_date} to {leave.end_date}) has been approved by {approver_employee.user.get_full_name()}",
                                notification_type='leave',
                                reference_id=str(leave.id),
                                reference_model='LeaveRequest'
                            )
                    except Exception as e:
                        print(f"DEBUG: Error creating approval notification: {e}")
                    
                    if is_direct_top_management_approval:
                        messages.success(request, f'RM Head leave request approved directly by top management.')
                    else:
                        messages.success(request, 'Leave request approved successfully.')
                else:
                    messages.error(request, 'Failed to approve leave request.')
                    
            except Exception as e:
                print(f"DEBUG: Exception during leave approval: {e}")
                messages.error(request, f'Error approving leave: {str(e)}')
        
        elif action == 'reject':
            try:
                if hasattr(leave, 'reject') and callable(leave.reject):
                    success = leave.reject(approver_employee, comments)
                else:
                    # Manual rejection
                    leave.status = 'R'  # Rejected
                    leave.processed_by = approver_employee
                    leave.processed_on = timezone.now()
                    leave.manager_comments = comments
                    leave.save()
                    success = True
                
                if success:
                    # Create rejection notification
                    Notification.objects.create(
                        recipient=leave.employee,
                        sender=approver_employee,
                        message=f"Your leave request for {leave.leave_type.name} has been rejected by {approver_employee.user.get_full_name()}. Reason: {comments}",
                        notification_type='leave',
                        reference_id=str(leave.id),
                        reference_model='LeaveRequest'
                    )
                    messages.success(request, 'Leave request rejected.')
                else:
                    messages.error(request, 'Failed to reject leave request.')
                    
            except Exception as e:
                print(f"DEBUG: Exception during leave rejection: {e}")
                messages.error(request, f'Error rejecting leave: {str(e)}')
        
        elif action == 'approve_cancellation' and leave.status == 'CR':
            try:
                if hasattr(leave, 'approve_cancellation') and callable(leave.approve_cancellation):
                    success = leave.approve_cancellation(approver_employee)
                else:
                    # Manual cancellation approval
                    leave.status = 'C'  # Cancelled
                    leave.processed_by = approver_employee
                    leave.processed_on = timezone.now()
                    leave.manager_comments = f"Cancellation approved: {comments}"
                    leave.save()
                    success = True
                
                if success:
                    messages.success(request, 'Leave cancellation approved.')
                else:
                    messages.error(request, 'Failed to approve cancellation.')
                    
            except Exception as e:
                print(f"DEBUG: Exception during cancellation approval: {e}")
                messages.error(request, f'Error approving cancellation: {str(e)}')
        
        return redirect('all_leave_requests')
    
    context = {
        'leave': leave,
        'approver_employee': approver_employee,
        'is_direct_top_management_approval': is_direct_top_management_approval,
        'can_direct_approve': request.user.role in ['top_management', 'business_head'],
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
            'status': 'D',  # ✅ Use 'D' for Draft (matches STATUS_CHOICES)
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

def validate_receipt_file(file):
    """Validate receipt file format and size"""
    # Check file size (5MB limit)
    if file.size > 5 * 1024 * 1024:
        return False
    
    # Check file extension
    allowed_extensions = ['.jpg', '.jpeg', '.png', '.pdf']
    file_extension = file.name.lower().split('.')[-1]
    if f'.{file_extension}' not in allowed_extensions:
        return False
    
    # Check MIME type
    allowed_mimes = ['image/jpeg', 'image/png', 'application/pdf']
    if hasattr(file, 'content_type') and file.content_type not in allowed_mimes:
        return False
    
    return True

from django.core.exceptions import ValidationError


    
@login_required
def add_expense(request):
    try:
        employee = Employee.objects.get(user=request.user)
    except Employee.DoesNotExist:
        messages.error(request, 'Employee profile not found.')
        return redirect('hrm_dashboard')
    
    if request.method == 'POST':
        form = ReimbursementExpenseForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                print("Form data before save:", form.cleaned_data)
                
                expense = form.save(commit=False)
                
                # Get or create claim
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
                print("Claim status:", claim.status)
                
                expense.claim = claim
                
                # Handle receipt upload from hidden fields (uploaded via AJAX)
                receipt_public_id = request.POST.get('receipt_public_id')
                receipt_url = request.POST.get('receipt_url')
                receipt_filename = request.POST.get('receipt_filename')
                
                if receipt_public_id and receipt_url:
                    expense.receipt_public_id = receipt_public_id
                    expense.receipt_url = receipt_url
                    expense.receipt_filename = receipt_filename
                    print(f"Receipt linked: {receipt_url}")
                
                # Handle direct file upload (fallback)
                elif 'receipt' in request.FILES:
                    receipt_file = request.FILES['receipt']
                    
                    if not validate_receipt_file(receipt_file):
                        messages.error(request, 'Invalid file format. Please upload JPG, PNG, or PDF files only.')
                        return render(request, 'hrm/add_expense.html', {'form': form, 'employee': employee})
                    
                    try:
                        # Upload to Cloudinary with minimal parameters
                        upload_result = cloudinary.uploader.upload(
                            receipt_file,
                            folder=f"receipts/{employee.employee_id}",
                            resource_type='auto',
                            tags=[f"employee_{employee.employee_id}", "expense_receipt"]
                        )
                        
                        # Store Cloudinary details
                        expense.receipt_public_id = upload_result['public_id']
                        expense.receipt_url = upload_result['secure_url']
                        expense.receipt_filename = receipt_file.name
                        
                        print(f"Receipt uploaded successfully: {upload_result['secure_url']}")
                        
                    except Exception as e:
                        print(f"Error uploading receipt: {e}")
                        messages.error(request, 'Error uploading receipt. Please try again.')
                        return render(request, 'hrm/add_expense.html', {'form': form, 'employee': employee})
                
                expense.save()
                
                messages.success(request, 'Expense added successfully!')
                return redirect('reimbursement_claims')
                
            except Exception as e:
                print(f"Error saving expense: {e}")
                messages.error(request, f'Error saving expense: {str(e)}')
                return render(request, 'hrm/add_expense.html', {'form': form, 'employee': employee})
        else:
            print("Form errors:", form.errors)
            messages.error(request, 'Please correct the errors below.')
    else:
        form = ReimbursementExpenseForm()
    
    context = {
        'form': form,
        'employee': employee,
    }
    return render(request, 'hrm/add_expense.html', context)

def format_file_size(size_bytes):
    """Format file size in human readable format"""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{round(size_bytes / 1024, 1)} KB"
    else:
        return f"{round(size_bytes / (1024 * 1024), 1)} MB"

from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
import os

@csrf_exempt
@require_http_methods(["POST"])
@login_required
def upload_receipt_ajax(request):
    """AJAX endpoint for receipt upload with progress"""
    try:
        if 'receipt' not in request.FILES:
            return JsonResponse({'success': False, 'error': 'No file provided'})
        
        receipt_file = request.FILES['receipt']
        
        if not validate_receipt_file(receipt_file):
            return JsonResponse({'success': False, 'error': 'Invalid file format or size'})
        
        employee = Employee.objects.get(user=request.user)
        
        # Verify Cloudinary configuration
        if not all([
            os.getenv('CLOUDINARY_CLOUD_NAME'),
            os.getenv('CLOUDINARY_API_KEY'),
            os.getenv('CLOUDINARY_API_SECRET')
        ]):
            return JsonResponse({
                'success': False, 
                'error': 'Cloudinary configuration missing. Please check environment variables.'
            })
        
        # Upload to Cloudinary with minimal parameters
        upload_result = cloudinary.uploader.upload(
            receipt_file,
            folder=f"receipts/{employee.employee_id}",
            resource_type='auto',
            tags=[f"employee_{employee.employee_id}", "temp_receipt"]
        )
        
        return JsonResponse({
            'success': True,
            'public_id': upload_result['public_id'],
            'secure_url': upload_result['secure_url'],
            'filename': receipt_file.name,
            'file_size': receipt_file.size,
            'file_size_formatted': format_file_size(receipt_file.size)
        })
        
    except Employee.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Employee not found'})
    except Exception as e:
        print(f"Error in AJAX upload: {e}")
        return JsonResponse({'success': False, 'error': f'Upload failed: {str(e)}'})

    
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
    """Enhanced reimbursement approval with proper hierarchy flow"""
    claim = get_object_or_404(ReimbursementClaim, id=claim_id)
    
    try:
        approver_employee = Employee.objects.get(user=request.user)
    except Employee.DoesNotExist:
        messages.error(request, 'Employee profile not found.')
        return redirect('hrm_dashboard')
    
    # Enhanced authorization and flow logic based on employee role and approver role
    can_approve = False
    is_direct_top_management_approval = False
    employee_role = claim.employee.user.role
    approver_role = request.user.role
    
    # Define approval flows based on employee role
    approval_flows = {
        'ops_exec': ['ops_team_lead', 'top_management', 'business_head'],  # ops_exec -> ops_team_lead -> top_management
        'employee': ['rm_head', 'top_management', 'business_head'],        # employee -> rm_head -> top_management  
        'intern': ['rm_head', 'top_management', 'business_head'],          # intern -> rm_head -> top_management
        'ops_team_lead': ['top_management', 'business_head'],              # ops_team_lead -> top_management (direct)
        'rm_head': ['top_management', 'business_head'],                    # rm_head -> top_management (direct)
        'business_head_ops': ['top_management', 'business_head'],          # business_head_ops -> top_management (direct)
    }
    
    # Get the approval flow for this employee
    required_approvers = approval_flows.get(employee_role, ['top_management', 'business_head'])
    
    print(f"DEBUG: Employee {claim.employee.user.get_full_name()} (Role: {employee_role})")
    print(f"DEBUG: Approver {approver_employee.user.get_full_name()} (Role: {approver_role})")
    print(f"DEBUG: Required approvers: {required_approvers}")
    print(f"DEBUG: Current claim status: {claim.status}")
    
    # Check authorization based on claim status and approval flow
    if claim.status == 'P':  # Pending - First approval
        # Check if approver is the first required approver in the flow
        if len(required_approvers) >= 2:
            # Two-step approval required
            first_approver = required_approvers[0]
            if approver_role == first_approver:
                can_approve = True
                print(f"DEBUG: First level approval by {approver_role}")
            elif approver_role in ['top_management', 'business_head']:
                # Top management can directly approve anyone
                can_approve = True
                is_direct_top_management_approval = True
                print(f"DEBUG: Direct top management approval for {employee_role}")
        else:
            # Single step approval (direct to top management)
            if approver_role in required_approvers:
                can_approve = True
                is_direct_top_management_approval = True
                print(f"DEBUG: Direct approval for {employee_role}")
    
    elif claim.status == 'MA':  # Manager Approved - Final approval needed
        # Only top management can do final approval
        if approver_role in ['top_management', 'business_head']:
            can_approve = True
            print(f"DEBUG: Final approval by top management")
    
    if not can_approve:
        messages.error(request, f'You are not authorized to approve this claim. Required approvers: {", ".join(required_approvers)}')
        return redirect('hrm_dashboard')
    
    # Debug current claim details
    print(f"DEBUG: Claim ID {claim.id} - Amount: ₹{claim.total_amount}")
    print(f"DEBUG: Authorization check passed - can_approve: {can_approve}")
    print(f"DEBUG: Is direct top management approval: {is_direct_top_management_approval}")
    
    if request.method == 'POST':
        action = request.POST.get('action')
        comments = request.POST.get('comments', '')
        
        if action == 'approve':
            try:
                if claim.status == 'P':
                    # First time approval
                    if is_direct_top_management_approval:
                        # Direct approval by top management - skip manager approval step
                        print("DEBUG: Processing direct top management approval")
                        claim.status = 'A'  # Direct final approval
                        claim.manager_approved_by = approver_employee
                        claim.manager_approved_on = timezone.now()
                        claim.manager_comments = f"Direct approval by top management: {comments}"
                        claim.final_approved_by = approver_employee
                        claim.final_approved_on = timezone.now()
                        claim.final_comments = f"Direct approval by {approver_employee.user.get_full_name()}"
                        claim.save()
                        
                        message_text = f'Claim directly approved by top management for payment. (Amount: ₹{claim.total_amount})'
                        
                    elif len(required_approvers) >= 2 and approver_role == required_approvers[0]:
                        # First level approval - send to top management for final approval
                        claim.status = 'MA'  # Manager Approved - needs final approval
                        claim.manager_approved_by = approver_employee
                        claim.manager_approved_on = timezone.now()
                        claim.manager_comments = comments
                        claim.save()
                        
                        # Send notification to top management for final approval
                        top_managers = Employee.objects.filter(
                            user__role__in=['top_management', 'business_head']
                        )
                        for tm in top_managers:
                            Notification.objects.create(
                                recipient=tm,
                                sender=approver_employee,
                                message=f"Reimbursement claim from {claim.employee.user.get_full_name()} ({employee_role}) for ₹{claim.total_amount} requires final approval",
                                notification_type='reimbursement',
                                reference_id=str(claim.id),
                                reference_model='ReimbursementClaim',
                                link=f"/hrm/reimbursement/{claim.id}/approve/"
                            )
                        
                        message_text = f'Claim approved by {approver_role} and sent to top management for final approval. (Amount: ₹{claim.total_amount})'
                        
                    else:
                        # Single step approval (shouldn't reach here with current logic)
                        claim.status = 'A'  # Approved
                        claim.manager_approved_by = approver_employee
                        claim.manager_approved_on = timezone.now()
                        claim.manager_comments = comments
                        claim.final_approved_by = approver_employee
                        claim.final_approved_on = timezone.now()
                        claim.save()
                        
                        message_text = f'Claim fully approved for reimbursement. (Amount: ₹{claim.total_amount})'
                
                elif claim.status == 'MA':
                    # Final approval by top management
                    print("DEBUG: Processing final approval for MA status claim")
                    
                    if approver_role in ['top_management', 'business_head']:
                        claim.status = 'A'  # Final Approved
                        claim.final_approved_by = approver_employee
                        claim.final_approved_on = timezone.now()
                        claim.final_comments = comments
                        claim.save()
                        
                        message_text = f'Claim finally approved for payment by top management. (Amount: ₹{claim.total_amount})'
                    else:
                        messages.error(request, 'This claim requires final approval by top management.')
                        return redirect('hrm_dashboard')
                
                elif claim.status == 'A':
                    messages.warning(request, 'This claim is already fully approved.')
                    return redirect('hrm_dashboard')
                
                else:
                    messages.error(request, f'Cannot approve claim with status: {claim.get_status_display()}')
                    return redirect('hrm_dashboard')
                
                # Create approval notification for employee
                Notification.objects.create(
                    recipient=claim.employee,
                    sender=approver_employee,
                    message=f"Your reimbursement claim for ₹{claim.total_amount} has been approved by {approver_employee.user.get_full_name()} ({approver_role})",
                    notification_type='reimbursement',
                    reference_id=str(claim.id),
                    reference_model='ReimbursementClaim'
                )
                
                # Additional notification for direct top management approval
                if is_direct_top_management_approval:
                    Notification.objects.create(
                        recipient=claim.employee,
                        sender=approver_employee,
                        message=f"Your reimbursement claim was directly approved by top management and is ready for payment processing",
                        notification_type='reimbursement',
                        reference_id=str(claim.id),
                        reference_model='ReimbursementClaim'
                    )
                
                messages.success(request, message_text)
                print(f"DEBUG: Approval successful - New status: {claim.status}")
                
            except Exception as e:
                print(f"DEBUG: Exception during approval: {e}")
                messages.error(request, f'Error approving claim: {str(e)}')
                return redirect('hrm_dashboard')
        
        elif action == 'reject':
            try:
                # Rejection logic - can reject from any approvable status
                if claim.status in ['P', 'MA']:
                    claim.status = 'R'  # Rejected
                    
                    # Set appropriate rejection fields based on current status
                    if claim.status == 'P':
                        claim.manager_approved_by = approver_employee
                        claim.manager_approved_on = timezone.now()
                        claim.manager_comments = f"REJECTED: {comments}"
                    else:  # MA status
                        claim.final_approved_by = approver_employee
                        claim.final_approved_on = timezone.now()
                        claim.final_comments = f"REJECTED: {comments}"
                    
                    claim.save()
                    
                    # Create rejection notification
                    rejection_message = f"Your reimbursement claim for ₹{claim.total_amount} has been rejected by {approver_employee.user.get_full_name()} ({approver_role})."
                    if is_direct_top_management_approval:
                        rejection_message += " (Rejected by top management)"
                    if comments:
                        rejection_message += f" Reason: {comments}"
                    
                    Notification.objects.create(
                        recipient=claim.employee,
                        sender=approver_employee,
                        message=rejection_message,
                        notification_type='reimbursement',
                        reference_id=str(claim.id),
                        reference_model='ReimbursementClaim'
                    )
                    
                    messages.success(request, f'Claim rejected successfully. (Amount: ₹{claim.total_amount})')
                else:
                    messages.error(request, f'Cannot reject claim with status: {claim.get_status_display()}')
                    return redirect('hrm_dashboard')
                
            except Exception as e:
                print(f"DEBUG: Exception during rejection: {e}")
                messages.error(request, f'Error rejecting claim: {str(e)}')
        
        return redirect('hrm_dashboard')
    
    # Determine what actions are available based on claim status, user role, and approval flow
    can_manager_approve = (claim.status == 'P' and 
                          len(required_approvers) >= 2 and 
                          approver_role == required_approvers[0])
    
    can_final_approve = (claim.status == 'MA' and 
                        approver_role in ['top_management', 'business_head'])
    
    can_direct_approve = (claim.status == 'P' and 
                         approver_role in ['top_management', 'business_head'])
    
    can_reject = claim.status in ['P', 'MA']
    
    # Get expenses for display
    try:
        expenses = claim.expenses.all() if hasattr(claim, 'expenses') else []
    except Exception:
        expenses = ReimbursementExpense.objects.filter(claim=claim)
    
    # Get approval history
    approval_history = []
    if claim.manager_approved_by:
        approval_history.append({
            'stage': 'First Level Approval' if claim.status in ['MA', 'A'] else 'Manager Approval',
            'approver': claim.manager_approved_by.user.get_full_name(),
            'approver_role': claim.manager_approved_by.user.role,
            'date': claim.manager_approved_on,
            'comments': claim.manager_comments,
            'status': 'Approved'
        })
    
    if claim.final_approved_by and claim.status == 'A':
        approval_history.append({
            'stage': 'Final Approval',
            'approver': claim.final_approved_by.user.get_full_name(),
            'approver_role': claim.final_approved_by.user.role,
            'date': claim.final_approved_on,
            'comments': claim.final_comments,
            'status': 'Approved'
        })
    
    # Show the approval flow for this employee
    approval_flow_display = []
    for i, role in enumerate(required_approvers):
        status = 'completed'
        if i == 0 and claim.manager_approved_by:
            status = 'completed'
        elif i == 1 and claim.final_approved_by:
            status = 'completed'  
        elif claim.status == 'P' and i == 0:
            status = 'current'
        elif claim.status == 'MA' and i == 1:
            status = 'current'
        else:
            status = 'pending'
            
        approval_flow_display.append({
            'role': role,
            'status': status,
            'is_current_user': approver_role == role
        })
    
    context = {
        'claim': claim,
        'expenses': expenses,
        'approver_employee': approver_employee,
        'can_manager_approve': can_manager_approve,
        'can_final_approve': can_final_approve,
        'can_direct_approve': can_direct_approve,
        'can_reject': can_reject,
        'claim_status_display': claim.get_status_display() if hasattr(claim, 'get_status_display') else claim.status,
        'approval_history': approval_history,
        'approval_flow_display': approval_flow_display,
        'required_approvers': required_approvers,
        'employee_role': employee_role,
        'approver_role': approver_role,
        'is_direct_top_management_approval': is_direct_top_management_approval,
        'is_two_step_approval': len(required_approvers) >= 2,
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

@login_required
def get_calendar_day_details(request):
    """Optimized day details for calendar"""
    date_str = request.GET.get('date')
    if not date_str:
        return JsonResponse({'error': 'Date not provided'}, status=400)
    
    try:
        selected_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        employee = Employee.objects.get(user=request.user)
    except (ValueError, Employee.DoesNotExist):
        return JsonResponse({'error': 'Invalid date or employee not found'}, status=400)
    
    # Get all data in single queries
    holiday = Holiday.objects.filter(date=selected_date).first()
    attendance = Attendance.objects.filter(employee=employee, date=selected_date).first()
    leaves = LeaveRequest.objects.filter(
        employee=employee,
        start_date__lte=selected_date,
        end_date__gte=selected_date
    ).select_related('leave_type').values(
        'leave_type__name', 'status', 'start_date', 'end_date', 'reason'
    )
    
    # Build response
    response_data = {
        'date': selected_date.strftime('%B %d, %Y'),
        'is_holiday': bool(holiday),
        'holiday_name': holiday.name if holiday else None,
        'is_sunday': selected_date.weekday() == 6,
        'attendance': {
            'present': bool(attendance and attendance.login_time),
            'login_time': attendance.login_time.strftime('%H:%M') if attendance and attendance.login_time else None,
            'logout_time': attendance.logout_time.strftime('%H:%M') if attendance and attendance.logout_time else None,
            'is_remote': attendance.is_remote if attendance else False,
            'is_late': attendance.is_late if attendance else False,
            'notes': attendance.notes if attendance else None
        },
        'leaves': [
            {
                'type': leave['leave_type__name'],
                'status': dict(LeaveRequest.STATUS_CHOICES)[leave['status']],
                'start_date': leave['start_date'].strftime('%Y-%m-%d'),
                'end_date': leave['end_date'].strftime('%Y-%m-%d'),
                'reason': leave['reason']
            }
            for leave in leaves
        ]
    }
    
    return JsonResponse(response_data)

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

# Fixed view_notification function for your HRM system

@login_required
def view_notification(request, notification_id):
    """View and mark notification as read - Compatible with your URL structure"""
    try:
        notification = get_object_or_404(Notification, id=notification_id, recipient__user=request.user)
        
        # Mark notification as read
        if hasattr(notification, 'mark_as_read'):
            notification.mark_as_read()
        else:
            notification.is_read = True
            notification.save()
        
        # Determine redirect URL based on notification content and type
        redirect_url = 'hrm_dashboard'  # Default fallback
        
        try:
            # Check if notification has a direct link field
            if hasattr(notification, 'link') and notification.link:
                # If link starts with /, it's a direct URL path
                if notification.link.startswith('/'):
                    return redirect(notification.link)
                else:
                    # Otherwise treat as named URL
                    return redirect(notification.link)
            
            # Determine redirect based on notification type and message content
            if hasattr(notification, 'notification_type'):
                notification_type = notification.notification_type
                message = notification.message.lower()
                
                if notification_type == 'leave':
                    # Check if it's an approval request
                    if any(keyword in message for keyword in ['approve', 'approval', 'pending']):
                        # Check if we have reference_id for direct approval link
                        if hasattr(notification, 'reference_id') and notification.reference_id:
                            try:
                                leave_id = int(notification.reference_id)
                                # Check if user can approve this leave
                                if request.user.role in ['rm_head', 'ops_team_lead', 'business_head', 'business_head_ops', 'top_management']:
                                    redirect_url = f'/hrm/leave/{leave_id}/approve/'
                                else:
                                    redirect_url = 'leave_management'
                            except (ValueError, TypeError):
                                redirect_url = 'leave_management'
                        else:
                            redirect_url = 'leave_management'
                    elif 'cancel' in message:
                        # Cancellation request
                        if hasattr(notification, 'reference_id') and notification.reference_id:
                            try:
                                leave_id = int(notification.reference_id)
                                if request.user.role in ['rm_head', 'ops_team_lead', 'business_head', 'business_head_ops', 'top_management']:
                                    redirect_url = f'/hrm/leave/{leave_id}/approve/'
                                else:
                                    redirect_url = 'leave_management'
                            except (ValueError, TypeError):
                                redirect_url = 'leave_management'
                        else:
                            redirect_url = 'leave_management'
                    else:
                        # General leave notification - go to leave management or calendar
                        redirect_url = 'leave_calendar'
                
                elif notification_type == 'reimbursement':
                    # Check if it's an approval request
                    if 'final approval' in message:
                        # Needs final approval by top management
                        if hasattr(notification, 'reference_id') and notification.reference_id:
                            try:
                                claim_id = int(notification.reference_id)
                                if request.user.role in ['top_management', 'business_head']:
                                    redirect_url = f'/hrm/reimbursement/{claim_id}/final-approve/'
                                else:
                                    redirect_url = 'reimbursement_claims'
                            except (ValueError, TypeError):
                                redirect_url = 'reimbursement_claims'
                        else:
                            redirect_url = 'reimbursement_claims'
                    elif any(keyword in message for keyword in ['approve', 'approval', 'pending']):
                        # Regular manager approval
                        if hasattr(notification, 'reference_id') and notification.reference_id:
                            try:
                                claim_id = int(notification.reference_id)
                                if request.user.role in ['rm_head', 'ops_team_lead', 'business_head', 'business_head_ops', 'top_management']:
                                    redirect_url = f'/hrm/reimbursement/{claim_id}/approve/'
                                else:
                                    redirect_url = 'reimbursement_claims'
                            except (ValueError, TypeError):
                                redirect_url = 'reimbursement_claims'
                        else:
                            redirect_url = 'reimbursement_claims'
                    else:
                        # General reimbursement notification
                        redirect_url = 'reimbursement_claims'
                
                elif notification_type == 'attendance':
                    # Attendance related notification
                    if request.user.role in ['rm_head', 'ops_team_lead', 'business_head', 'business_head_ops', 'top_management']:
                        redirect_url = 'monthly_attendance_report'
                    else:
                        redirect_url = 'attendance_tracking'
                
                else:
                    # Unknown notification type - go to dashboard
                    redirect_url = 'hrm_dashboard'
            
            else:
                # No notification type - try to determine from message content
                message = notification.message.lower() if notification.message else ''
                
                if any(keyword in message for keyword in ['leave', 'vacation', 'absent']):
                    redirect_url = 'leave_management'
                elif any(keyword in message for keyword in ['reimbursement', 'expense', 'claim']):
                    redirect_url = 'reimbursement_claims'
                elif any(keyword in message for keyword in ['attendance', 'login', 'remote']):
                    redirect_url = 'attendance_tracking'
                else:
                    redirect_url = 'hrm_dashboard'
        
        except Exception as e:
            print(f"Error processing notification redirect: {e}")
            redirect_url = 'hrm_dashboard'
        
        # Handle the redirect
        if redirect_url.startswith('/'):
            # Direct URL path
            return redirect(redirect_url)
        else:
            # Named URL pattern
            return redirect(redirect_url)
    
    except Notification.DoesNotExist:
        messages.error(request, 'Notification not found or you do not have permission to view it.')
        return redirect('hrm_dashboard')
    
    except Exception as e:
        messages.error(request, f'Error processing notification: {str(e)}')
        return redirect('hrm_dashboard')

# Helper function to create better notifications (add this to your views)
def create_notification_with_link(recipient, sender, message, notification_type, reference_id=None, reference_model=None):
    """Create notification with appropriate action link"""
    
    link = None
    
    if notification_type == 'leave' and reference_id:
        if 'approve' in message.lower():
            link = f'/hrm/leave/{reference_id}/approve/'
        else:
            link = 'leave_management'
    elif notification_type == 'reimbursement' and reference_id:
        if 'final approval' in message.lower():
            link = f'/hrm/reimbursement/{reference_id}/final-approve/'
        elif 'approve' in message.lower():
            link = f'/hrm/reimbursement/{reference_id}/approve/'
        else:
            link = 'reimbursement_claims'
    elif notification_type == 'attendance':
        link = 'attendance_tracking'
    
    # Create notification with appropriate fields
    notification_data = {
        'recipient': recipient,
        'sender': sender,
        'message': message,
        'notification_type': notification_type,
    }
    
    # Add optional fields if they exist in your model
    if hasattr(Notification, 'reference_id'):
        notification_data['reference_id'] = str(reference_id) if reference_id else None
    if hasattr(Notification, 'reference_model'):
        notification_data['reference_model'] = reference_model
    if hasattr(Notification, 'link'):
        notification_data['link'] = link
    
    return Notification.objects.create(**notification_data)

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
        remote_count=models.Count('id', filter=Q(is_remote=True)),
        late_count=models.Count('id', filter=Q(is_late=True)),
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