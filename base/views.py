from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth import authenticate, login, logout
from django.urls import reverse
from django.contrib import messages
from django.utils import timezone
from django.db.models import Sum, Count, Q, Avg
from django.http import JsonResponse, HttpResponseForbidden
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Sum, Avg, F, Q
from django.db.models.functions import Extract
from django.utils import timezone
from django.db import transaction
from django.views.decorators.http import require_POST
from django.core.files.storage import default_storage
import json
from django.views.decorators.http import require_POST, require_GET
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.http import JsonResponse, Http404, HttpResponseForbidden
from django.core.exceptions import PermissionDenied
from django.db.models import Sum, Count, Q, Avg, F
from django.db.models.functions import Extract
from django.utils import timezone
from django.db import transaction
from django.views.decorators.http import require_POST, require_GET
from django.views.decorators.csrf import csrf_exempt
from django.core.paginator import Paginator
from django.urls import reverse
from datetime import datetime, timedelta
from .models import (
    User, Lead, Client, Task, ServiceRequest, BusinessTracker, 
    InvestmentPlanReview, Team, ProductDiscussion, ClientProfile,
    Note, NoteList
)
from .forms import (
    ClientSearchForm, LeadForm, OperationsTaskAssignmentForm, TaskForm, ServiceRequestForm, InvestmentPlanReviewForm,
    ClientProfileForm, NoteForm, NoteListForm, QuickNoteForm
)

# Helper functions for role checks
def is_top_management(user):
    return user.role == 'top_management'

def is_business_head(user):
    return user.role == 'business_head'

def is_business_head_ops(user):
    return user.role == 'business_head_ops'

def is_rm_head(user):
    return user.role == 'rm_head'

def is_rm(user):
    return user.role == 'rm'

def is_ops_team_lead(user):
    return user.role == 'ops_team_lead'

def is_ops_exec(user):
    return user.role == 'ops_exec'

# Login View
def user_login(request):
    if request.user.is_authenticated:
        return redirect('dashboard')

    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)
        if user:
            login(request, user)
            return redirect('dashboard')
        else:
            return render(request, 'base/login.html', {'error': 'Invalid credentials'})
    return render(request, 'base/login.html')

# Logout View
@login_required
def user_logout(request):
    logout(request)
    return redirect('login')

def can_manage_user(manager, target_user):
    """Check if manager can manage target_user based on hierarchy"""
    if manager.role == 'top_management':
        return True
    elif manager.role == 'business_head':
        return True
    elif manager.role == 'rm_head':
        return target_user in manager.get_team_members() or target_user == manager
    else:
        return target_user == manager

def get_user_accessible_data(user, model_class, user_field='assigned_to'):
    """Generic method to get accessible data based on user role and hierarchy"""
    if user.role in ['top_management', 'business_head']:
        return model_class.objects.all()
    elif user.role == 'rm_head':
        accessible_users = user.get_accessible_users()
        filter_kwargs = {f"{user_field}__in": accessible_users}
        return model_class.objects.filter(**filter_kwargs)
    else:  # RM
        filter_kwargs = {user_field: user}
        return model_class.objects.filter(**filter_kwargs)

@login_required
def dashboard(request):
    user = request.user
    context = {}

    if user.role == 'top_management':
        # Aggregate KPIs across entire system
        total_aum = Client.objects.aggregate(total=Sum('aum'))['total'] or 0
        total_sip = Client.objects.aggregate(total=Sum('sip_amount'))['total'] or 0
        total_clients = Client.objects.count()
        total_leads = Lead.objects.count()
        total_tasks = Task.objects.filter(completed=False).count()
        open_service_requests = ServiceRequest.objects.filter(status='open').count()

        # Team metrics
        business_heads_count = User.objects.filter(role='business_head').count()
        business_heads_ops_count = User.objects.filter(role='business_head_ops').count()
        rm_heads_count = User.objects.filter(role='rm_head').count()
        rms_count = User.objects.filter(role='rm').count()
        ops_team_leads_count = User.objects.filter(role='ops_team_lead').count()
        ops_execs_count = User.objects.filter(role='ops_exec').count()

        # Recent activities
        recent_leads = Lead.objects.order_by('-created_at')[:5]
        recent_service_requests = ServiceRequest.objects.order_by('-created_at')[:5]
        recent_notes = Note.objects.filter(user=user).order_by('-updated_at')[:3]

        context.update({
            'total_aum': total_aum,
            'total_sip': total_sip,
            'total_clients': total_clients,
            'total_leads': total_leads,
            'total_tasks': total_tasks,
            'open_service_requests': open_service_requests,
            'business_heads_count': business_heads_count,
            'business_heads_ops_count': business_heads_ops_count,
            'rm_heads_count': rm_heads_count,
            'rms_count': rms_count,
            'ops_team_leads_count': ops_team_leads_count,
            'ops_execs_count': ops_execs_count,
            'recent_leads': recent_leads,
            'recent_service_requests': recent_service_requests,
            'recent_notes': recent_notes,
        })
        template_name = 'base/dashboard_top_management.html'

    elif user.role == 'business_head':
        # Monitor all RM Heads and their performance
        rm_heads = User.objects.filter(role='rm_head')
        all_rms = User.objects.filter(role='rm')
        
        # System-wide metrics
        total_leads = Lead.objects.count()
        converted_leads = Lead.objects.filter(status='converted').count()
        open_service_requests = ServiceRequest.objects.filter(status='open')
        
        # Performance metrics
        lead_conversion_rate = (converted_leads / total_leads * 100) if total_leads > 0 else 0
        
        # Calculate average response time using Python datetime operations
        resolved_requests = ServiceRequest.objects.filter(
            status__in=['resolved', 'closed'],
            resolved_at__isnull=False
        ).values('created_at', 'resolved_at')
        
        if resolved_requests.exists():
            total_response_seconds = 0
            request_count = 0
            
            for request in resolved_requests:
                response_time = request['resolved_at'] - request['created_at']
                total_response_seconds += response_time.total_seconds()
                request_count += 1
            
            avg_response_time_days = (total_response_seconds / request_count) / (24 * 60 * 60) if request_count > 0 else 0
        else:
            avg_response_time_days = 0

        recent_notes = Note.objects.filter(user=user).order_by('-updated_at')[:3]

        context.update({
            'rm_heads': rm_heads,
            'all_rms': all_rms,
            'total_leads': total_leads,
            'converted_leads': converted_leads,
            'lead_conversion_rate': round(lead_conversion_rate, 2),
            'open_service_requests': open_service_requests,
            'avg_response_time': round(avg_response_time_days, 2),
            'recent_notes': recent_notes,
        })
        template_name = 'base/dashboard_business_head.html'

    elif user.role == 'business_head_ops':
        # Operations oversight dashboard
        ops_team_leads = User.objects.filter(role='ops_team_lead')
        ops_execs = User.objects.filter(role='ops_exec')
        
        # Operations metrics
        total_client_profiles = ClientProfile.objects.count()
        active_profiles = ClientProfile.objects.filter(status='active').count()
        muted_profiles = ClientProfile.objects.filter(status='muted').count()
        
        # Service requests related to operations
        ops_service_requests = ServiceRequest.objects.filter(
            Q(assigned_to__role__in=['ops_team_lead', 'ops_exec']) |
            Q(raised_by__role__in=['ops_team_lead', 'ops_exec'])
        )
        
        # Task metrics for operations team
        ops_tasks = Task.objects.filter(assigned_to__role__in=['ops_team_lead', 'ops_exec'])
        pending_ops_tasks = ops_tasks.filter(completed=False).count()
        overdue_ops_tasks = ops_tasks.filter(
            completed=False, 
            due_date__lt=timezone.now()
        ).count()

        # Team performance data
        team_performance = []
        for lead in ops_team_leads:
            team_members = lead.get_team_members()
            team_tasks = Task.objects.filter(assigned_to__in=team_members)
            team_service_requests = ServiceRequest.objects.filter(
                Q(assigned_to__in=team_members) | Q(raised_by__in=team_members)
            )
            
            team_performance.append({
                'lead': lead,
                'team_size': team_members.count(),
                'pending_tasks': team_tasks.filter(completed=False).count(),
                'total_service_requests': team_service_requests.count(),
                'open_service_requests': team_service_requests.filter(status='open').count(),
            })

        recent_notes = Note.objects.filter(user=user).order_by('-updated_at')[:3]

        context.update({
            'ops_team_leads': ops_team_leads,
            'ops_execs': ops_execs,
            'total_client_profiles': total_client_profiles,
            'active_profiles': active_profiles,
            'muted_profiles': muted_profiles,
            'ops_service_requests': ops_service_requests,
            'pending_ops_tasks': pending_ops_tasks,
            'overdue_ops_tasks': overdue_ops_tasks,
            'team_performance': team_performance,
            'recent_notes': recent_notes,
        })
        template_name = 'base/dashboard_business_head_ops.html'

    elif user.role == 'rm_head':
        team_members = user.get_team_members()
        accessible_users = user.get_accessible_users()
        
        # Team metrics
        team_leads = Lead.objects.filter(assigned_to__in=accessible_users)
        team_clients = Client.objects.filter(user__in=accessible_users)
        team_tasks = Task.objects.filter(assigned_to__in=accessible_users)
        team_service_requests = ServiceRequest.objects.filter(
            Q(raised_by__in=accessible_users) | Q(client__user__in=accessible_users)
        )
        
        # Performance metrics
        pending_tasks = team_tasks.filter(completed=False).count()
        overdue_tasks = team_tasks.filter(
            completed=False, 
            due_date__lt=timezone.now()
        ).count()
        
        team_aum = team_clients.aggregate(total=Sum('aum'))['total'] or 0
        team_sip = team_clients.aggregate(total=Sum('sip_amount'))['total'] or 0
        
        # Prepare detailed member statistics
        team_members_data = []
        for member in team_members:
            member_leads = team_leads.filter(assigned_to=member)
            member_clients = team_clients.filter(user=member)
            member_tasks = team_tasks.filter(assigned_to=member)
            
            team_members_data.append({
                'member': member,
                'lead_count': member_leads.count(),
                'client_count': member_clients.count(),
                'aum': member_clients.aggregate(total=Sum('aum'))['total'] or 0,
                'sip': member_clients.aggregate(total=Sum('sip_amount'))['total'] or 0,
                'pending_tasks': member_tasks.filter(completed=False).count(),
                'overdue_tasks': member_tasks.filter(completed=False, due_date__lt=timezone.now()).count(),
                'performance_score': getattr(member, 'performance_score', 0)
            })

        recent_notes = Note.objects.filter(user=user).order_by('-updated_at')[:3]

        context.update({
            'team_members': team_members,
            'team_leads': team_leads,
            'team_clients': team_clients,
            'team_tasks': team_tasks,
            'team_service_requests': team_service_requests,
            'pending_tasks': pending_tasks,
            'overdue_tasks': overdue_tasks,
            'team_aum': team_aum,
            'team_sip': team_sip,
            'leads_count': team_leads.count(),
            'clients_count': team_clients.count(),
            'team_members_data': team_members_data,
            'recent_notes': recent_notes,
        })
        template_name = 'base/dashboard_rm_head.html'

    elif user.role == 'ops_team_lead':
        # Operations Team Lead dashboard
        team_members = user.get_team_members()  # Ops Executives under this lead
        
        # Team metrics
        team_tasks = Task.objects.filter(assigned_to__in=team_members.union(User.objects.filter(id=user.id)))
        team_service_requests = ServiceRequest.objects.filter(
            Q(assigned_to__in=team_members.union(User.objects.filter(id=user.id))) |
            Q(raised_by__in=team_members.union(User.objects.filter(id=user.id)))
        )
        
        # Client profiles managed by team
        team_client_profiles = ClientProfile.objects.filter(
            Q(mapped_ops_exec__in=team_members) | Q(created_by__in=team_members.union(User.objects.filter(id=user.id)))
        )
        
        # Performance metrics
        pending_tasks = team_tasks.filter(completed=False).count()
        overdue_tasks = team_tasks.filter(
            completed=False, 
            due_date__lt=timezone.now()
        ).count()
        
        # Service request metrics
        open_requests = team_service_requests.filter(status='open').count()
        in_progress_requests = team_service_requests.filter(status='in_progress').count()
        
        # Team member performance
        team_members_data = []
        for member in team_members:
            member_tasks = team_tasks.filter(assigned_to=member)
            member_service_requests = team_service_requests.filter(
                Q(assigned_to=member) | Q(raised_by=member)
            )
            member_client_profiles = team_client_profiles.filter(mapped_ops_exec=member)
            
            team_members_data.append({
                'member': member,
                'task_count': member_tasks.count(),
                'pending_tasks': member_tasks.filter(completed=False).count(),
                'service_requests': member_service_requests.count(),
                'open_requests': member_service_requests.filter(status='open').count(),
                'client_profiles': member_client_profiles.count(),
            })

        recent_notes = Note.objects.filter(user=user).order_by('-updated_at')[:3]

        context.update({
            'team_members': team_members,
            'team_tasks': team_tasks,
            'team_service_requests': team_service_requests,
            'team_client_profiles': team_client_profiles,
            'pending_tasks': pending_tasks,
            'overdue_tasks': overdue_tasks,
            'open_requests': open_requests,
            'in_progress_requests': in_progress_requests,
            'team_members_data': team_members_data,
            'recent_notes': recent_notes,
        })
        template_name = 'base/dashboard_ops_team_lead.html'

    elif user.role == 'ops_exec':
        # Operations Executive dashboard
        my_tasks = Task.objects.filter(assigned_to=user)
        my_service_requests = ServiceRequest.objects.filter(
            Q(assigned_to=user) | Q(raised_by=user)
        )
        my_client_profiles = ClientProfile.objects.filter(mapped_ops_exec=user)
        
        # Personal metrics
        pending_tasks = my_tasks.filter(completed=False).count()
        overdue_tasks = my_tasks.filter(completed=False, due_date__lt=timezone.now()).count()
        open_requests = my_service_requests.filter(status='open').count()
        
        # Recent activities
        recent_tasks = my_tasks.order_by('-created_at')[:5]
        recent_service_requests = my_service_requests.order_by('-created_at')[:5]
        recent_client_profiles = my_client_profiles.order_by('-updated_at')[:5]
        recent_notes = Note.objects.filter(user=user).order_by('-updated_at')[:3]

        context.update({
            'my_tasks': my_tasks,
            'my_service_requests': my_service_requests,
            'my_client_profiles': my_client_profiles,
            'pending_tasks': pending_tasks,
            'overdue_tasks': overdue_tasks,
            'open_requests': open_requests,
            'recent_tasks': recent_tasks,
            'recent_service_requests': recent_service_requests,
            'recent_client_profiles': recent_client_profiles,
            'recent_notes': recent_notes,
        })
        template_name = 'base/dashboard_ops_exec.html'

    else:  # Relationship Manager
        # Personal dashboard
        leads = Lead.objects.filter(assigned_to=user)
        clients = Client.objects.filter(user=user)
        tasks = Task.objects.filter(assigned_to=user)
        reminders = user.reminders.filter(is_done=False, remind_at__gte=timezone.now()) if hasattr(user, 'reminders') else []
        service_requests = ServiceRequest.objects.filter(raised_by=user)
        
        # Personal metrics
        pending_tasks = tasks.filter(completed=False).count()
        overdue_tasks = tasks.filter(completed=False, due_date__lt=timezone.now()).count()
        my_aum = clients.aggregate(total=Sum('aum'))['total'] or 0
        my_sip = clients.aggregate(total=Sum('sip_amount'))['total'] or 0
        
        # Recent activities
        recent_clients = clients.order_by('-created_at')[:3]
        recent_notes = Note.objects.filter(user=user).order_by('-updated_at')[:3]

        context.update({
            'leads': leads,
            'clients': clients,
            'tasks': tasks,
            'reminders': reminders,
            'service_requests': service_requests,
            'pending_tasks': pending_tasks,
            'overdue_tasks': overdue_tasks,
            'my_aum': my_aum,
            'my_sip': my_sip,
            'recent_clients': recent_clients,
            'recent_notes': recent_notes,
            'leads_count': leads.count(),
            'clients_count': clients.count(),
        })
        template_name = 'base/dashboard_rm.html'

    return render(request, template_name, context)

# Notes System Views
@login_required
def notes_dashboard(request):
    """Main notes dashboard with overview"""
    user = request.user
    
    # Get user's note lists and notes
    note_lists = NoteList.objects.filter(user=user)
    notes = Note.objects.filter(user=user)
    
    # Notes statistics
    total_notes = notes.count()
    completed_notes = notes.filter(is_completed=True).count()
    pending_notes = notes.filter(is_completed=False).count()
    overdue_notes = notes.filter(is_completed=False, due_date__lt=timezone.now().date()).count()
    
    # Recent notes
    recent_notes = notes.order_by('-updated_at')[:10]
    
    # Upcoming reminders
    upcoming_reminders = notes.filter(
        reminder_date__gte=timezone.now(),
        is_completed=False
    ).order_by('reminder_date')[:5]
    
    # Due soon (next 7 days)
    from datetime import timedelta
    due_soon = notes.filter(
        due_date__lte=timezone.now().date() + timedelta(days=7),
        due_date__gte=timezone.now().date(),
        is_completed=False
    ).order_by('due_date')[:5]
    
    context = {
        'note_lists': note_lists,
        'total_notes': total_notes,
        'completed_notes': completed_notes,
        'pending_notes': pending_notes,
        'overdue_notes': overdue_notes,
        'recent_notes': recent_notes,
        'upcoming_reminders': upcoming_reminders,
        'due_soon': due_soon,
    }
    
    return render(request, 'notes/dashboard.html', context)

@login_required
def note_list_view(request):
    """View all notes with filtering options"""
    user = request.user
    notes = Note.objects.filter(user=user)
    
    # Filtering
    status_filter = request.GET.get('status')
    if status_filter == 'completed':
        notes = notes.filter(is_completed=True)
    elif status_filter == 'pending':
        notes = notes.filter(is_completed=False)
    elif status_filter == 'overdue':
        notes = notes.filter(is_completed=False, due_date__lt=timezone.now().date())
    
    list_filter = request.GET.get('list')
    if list_filter:
        notes = notes.filter(note_list_id=list_filter)
    
    # Search
    search_query = request.GET.get('search')
    if search_query:
        notes = notes.filter(
            Q(heading__icontains=search_query) |
            Q(content__icontains=search_query)
        )
    
    # Sorting
    sort_by = request.GET.get('sort', '-updated_at')
    notes = notes.order_by(sort_by)
    
    # Get note lists for filter dropdown
    note_lists = NoteList.objects.filter(user=user)
    
    context = {
        'notes': notes,
        'note_lists': note_lists,
        'status_filter': status_filter,
        'list_filter': list_filter,
        'search_query': search_query,
        'sort_by': sort_by,
    }
    
    return render(request, 'notes/note_list.html', context)

@login_required
def note_create(request):
    """Create a new note"""
    if request.method == 'POST':
        form = NoteForm(request.POST, request.FILES, user=request.user)
        if form.is_valid():
            note = form.save(commit=False)
            note.user = request.user
            try:
                note.save()
                messages.success(request, "Note created successfully.")
                return redirect('note_detail', pk=note.pk)
            except ValidationError as e:
                messages.error(request, str(e))
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        form = NoteForm(user=request.user)
    
    return render(request, 'notes/note_form.html', {
        'form': form, 
        'action': 'Create',
        'title': 'Create New Note'
    })

@login_required
def note_detail(request, pk):
    """View note details"""
    note = get_object_or_404(Note, pk=pk, user=request.user)
    
    context = {
        'note': note,
        'can_edit': True,  # User can always edit their own notes
        'can_delete': True,  # User can always delete their own notes
    }
    
    return render(request, 'notes/note_detail.html', context)

@login_required
def note_update(request, pk):
    """Update a note"""
    note = get_object_or_404(Note, pk=pk, user=request.user)
    
    if request.method == 'POST':
        form = NoteForm(request.POST, request.FILES, instance=note, user=request.user)
        if form.is_valid():
            try:
                form.save()
                messages.success(request, "Note updated successfully.")
                return redirect('note_detail', pk=note.pk)
            except ValidationError as e:
                messages.error(request, str(e))
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        form = NoteForm(instance=note, user=request.user)
    
    return render(request, 'notes/note_form.html', {
        'form': form, 
        'action': 'Update',
        'title': 'Update Note',
        'note': note
    })

@login_required
def note_delete(request, pk):
    """Delete a note"""
    note = get_object_or_404(Note, pk=pk, user=request.user)
    
    if request.method == 'POST':
        note_heading = note.heading
        
        # Delete associated file if exists
        if note.attachment:
            try:
                default_storage.delete(note.attachment.name)
            except:
                pass  # File might not exist
        
        note.delete()
        messages.success(request, f"Note '{note_heading}' has been deleted.")
        return redirect('note_list')
    
    return render(request, 'notes/note_confirm_delete.html', {'note': note})

@login_required
@require_POST
def note_toggle_complete(request, pk):
    """Toggle note completion status via AJAX"""
    note = get_object_or_404(Note, pk=pk, user=request.user)
    
    note.is_completed = not note.is_completed
    if note.is_completed:
        note.completed_at = timezone.now()
    else:
        note.completed_at = None
    note.save()
    
    return JsonResponse({
        'success': True,
        'is_completed': note.is_completed,
        'completed_at': note.completed_at.isoformat() if note.completed_at else None
    })
    
import logging
logger = logging.getLogger(__name__)


@login_required
@require_POST
def note_toggle_complete(request, pk):
    """Toggle note completion status via AJAX with enhanced error handling"""
    try:
        note = get_object_or_404(Note, pk=pk, user=request.user)
        
        # Handle both AJAX and form submissions
        if request.content_type == 'application/json':
            try:
                data = json.loads(request.body)
                force_status = data.get('is_completed')
                if force_status is not None:
                    note.is_completed = bool(force_status)
                else:
                    note.is_completed = not note.is_completed
            except (json.JSONDecodeError, KeyError):
                note.is_completed = not note.is_completed
        else:
            note.is_completed = not note.is_completed
        
        if note.is_completed:
            note.completed_at = timezone.now()
        else:
            note.completed_at = None
        
        note.save(update_fields=['is_completed', 'completed_at', 'updated_at'])
        
        response_data = {
            'success': True,
            'is_completed': note.is_completed,
            'completed_at': note.completed_at.isoformat() if note.completed_at else None,
            'message': 'Note marked as completed!' if note.is_completed else 'Note marked as incomplete!'
        }
        
        return JsonResponse(response_data)
    
    except Note.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Note not found or access denied',
            'message': 'Note not found or you do not have permission to modify it.'
        }, status=404)
    
    except Exception as e:
        logger.error(f"Error toggling completion for note {pk}, user {request.user.id}: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': 'Server error',
            'message': 'An error occurred while updating the note status.'
        }, status=500)
        
@login_required
def note_list_management(request):
    """Manage note lists"""
    user = request.user
    note_lists = NoteList.objects.filter(user=user)
    
    context = {
        'note_lists': note_lists,
    }
    
    return render(request, 'notes/note_list_management.html', context)

@login_required
def note_list_create(request):
    """Create a new note list"""
    if request.method == 'POST':
        form = NoteListForm(request.POST)
        if form.is_valid():
            note_list = form.save(commit=False)
            note_list.user = request.user
            note_list.save()
            messages.success(request, f"Note list '{note_list.name}' created successfully.")
            return redirect('note_list_management')
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        form = NoteListForm()
    
    return render(request, 'notes/note_list_form.html', {
        'form': form, 
        'action': 'Create',
        'title': 'Create Note List'
    })

@login_required
def note_list_update(request, pk):
    """Update a note list"""
    note_list = get_object_or_404(NoteList, pk=pk, user=request.user)
    
    if request.method == 'POST':
        form = NoteListForm(request.POST, instance=note_list)
        if form.is_valid():
            form.save()
            messages.success(request, f"Note list '{note_list.name}' updated successfully.")
            return redirect('note_list_management')
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        form = NoteListForm(instance=note_list)
    
    return render(request, 'notes/note_list_form.html', {
        'form': form, 
        'action': 'Update',
        'title': 'Update Note List',
        'note_list': note_list
    })

@login_required
def note_list_delete(request, pk):
    """Delete a note list"""
    note_list = get_object_or_404(NoteList, pk=pk, user=request.user)
    
    # Check if list has notes
    notes_count = note_list.notes.count()
    if notes_count > 0 and request.method == 'GET':
        messages.warning(request, f"This list contains {notes_count} notes. Deleting the list will also delete all notes in it.")
    
    if request.method == 'POST':
        list_name = note_list.name
        note_list.delete()  # This will cascade delete all notes in the list
        messages.success(request, f"Note list '{list_name}' and all its notes have been deleted.")
        return redirect('note_list_management')
    
    return render(request, 'notes/note_list_confirm_delete.html', {
        'note_list': note_list,
        'notes_count': notes_count
    })

# API endpoints for notes
@login_required
def get_notes_by_list(request, list_id):
    """AJAX endpoint to get notes by list"""
    note_list = get_object_or_404(NoteList, pk=list_id, user=request.user)
    notes = note_list.notes.all().values('id', 'heading', 'is_completed', 'due_date')
    
    return JsonResponse(list(notes), safe=False)

@login_required
def get_upcoming_reminders(request):
    """AJAX endpoint for upcoming reminders"""
    notes = Note.objects.filter(
        user=request.user,
        reminder_date__gte=timezone.now(),
        reminder_date__lte=timezone.now() + timezone.timedelta(days=1),
        is_completed=False
    ).values('id', 'heading', 'reminder_date')
    
    return JsonResponse(list(notes), safe=False)



# Helper decorators for role-based access
def operations_team_required(user):
    """Check if user is part of operations team"""
    return user.role in ['business_head_ops', 'ops_team_lead', 'ops_exec']

def ops_team_lead_required(user):
    """Check if user is operations team lead"""
    return user.role == 'ops_team_lead'

def business_head_ops_required(user):
    """Check if user is business head operations"""
    return user.role == 'business_head_ops'

def ops_management_required(user):
    """Check if user can manage operations"""
    return user.role in ['business_head_ops', 'ops_team_lead']

# Operations Team Lead Views
@login_required
@user_passes_test(ops_team_lead_required)
def ops_team_performance(request):
    """Operations Team Lead view for team performance metrics"""
    user = request.user
    team_members = user.get_team_members()
    
    # Get date range for filtering
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')
    
    if not date_from:
        date_from = timezone.now().date() - timedelta(days=30)
    else:
        date_from = datetime.strptime(date_from, '%Y-%m-%d').date()
    
    if not date_to:
        date_to = timezone.now().date()
    else:
        date_to = datetime.strptime(date_to, '%Y-%m-%d').date()
    
    # Team performance metrics
    team_stats = []
    for member in team_members:
        # Tasks metrics
        member_tasks = Task.objects.filter(
            assigned_to=member,
            created_at__date__range=[date_from, date_to]
        )
        
        # Service requests metrics
        member_requests = ServiceRequest.objects.filter(
            assigned_to=member,
            created_at__date__range=[date_from, date_to]
        )
        
        # Client profiles metrics
        member_profiles = ClientProfile.objects.filter(
            mapped_ops_exec=member,
            created_at__date__range=[date_from, date_to]
        )
        
        # Calculate completion rates
        total_tasks = member_tasks.count()
        completed_tasks = member_tasks.filter(completed=True).count()
        task_completion_rate = (completed_tasks / total_tasks * 100) if total_tasks > 0 else 0
        
        total_requests = member_requests.count()
        resolved_requests = member_requests.filter(status__in=['resolved', 'closed']).count()
        request_resolution_rate = (resolved_requests / total_requests * 100) if total_requests > 0 else 0
        
        # Average response time for service requests
        resolved_with_time = member_requests.filter(
            status__in=['resolved', 'closed'],
            resolved_at__isnull=False
        )
        
        if resolved_with_time.exists():
            avg_response_time = resolved_with_time.aggregate(
                avg_time=Avg(
                    Extract('epoch', F('resolved_at')) - Extract('epoch', F('created_at'))
                )
            )['avg_time']
            avg_response_hours = avg_response_time / 3600 if avg_response_time else 0
        else:
            avg_response_hours = 0
        
        team_stats.append({
            'member': member,
            'total_tasks': total_tasks,
            'completed_tasks': completed_tasks,
            'pending_tasks': total_tasks - completed_tasks,
            'task_completion_rate': round(task_completion_rate, 2),
            'total_requests': total_requests,
            'resolved_requests': resolved_requests,
            'request_resolution_rate': round(request_resolution_rate, 2),
            'avg_response_hours': round(avg_response_hours, 2),
            'client_profiles': member_profiles.count(),
            'performance_score': round((task_completion_rate + request_resolution_rate) / 2, 2)
        })
    
    # Overall team metrics
    team_totals = {
        'total_tasks': sum(stat['total_tasks'] for stat in team_stats),
        'completed_tasks': sum(stat['completed_tasks'] for stat in team_stats),
        'total_requests': sum(stat['total_requests'] for stat in team_stats),
        'resolved_requests': sum(stat['resolved_requests'] for stat in team_stats),
        'total_profiles': sum(stat['client_profiles'] for stat in team_stats),
    }
    
    context = {
        'team_members': team_members,
        'team_stats': team_stats,
        'team_totals': team_totals,
        'date_from': date_from,
        'date_to': date_to,
        'avg_team_performance': round(sum(stat['performance_score'] for stat in team_stats) / len(team_stats), 2) if team_stats else 0,
    }
    
    return render(request, 'operations/team_performance.html', context)


@login_required
@user_passes_test(ops_team_lead_required)
def ops_client_profiles(request):
    """Operations Team Lead view for managing client profiles"""
    user = request.user
    team_members = user.get_team_members()
    
    # Get client profiles assigned to team
    client_profiles = ClientProfile.objects.filter(
        mapped_ops_exec__in=team_members
    ).select_related('mapped_rm', 'mapped_ops_exec')
    
    # Apply filters
    search_form = ClientSearchForm(request.GET)
    if search_form.is_valid():
        search_query = search_form.cleaned_data.get('search_query')
        status = search_form.cleaned_data.get('status')
        ops_exec = search_form.cleaned_data.get('ops_exec')
        
        if search_query:
            client_profiles = client_profiles.filter(
                Q(client_full_name__icontains=search_query) |
                Q(email__icontains=search_query) |
                Q(mobile_number__icontains=search_query) |
                Q(pan_number__icontains=search_query)
            )
        
        if status:
            client_profiles = client_profiles.filter(status=status)
        
        if ops_exec:
            client_profiles = client_profiles.filter(mapped_ops_exec=ops_exec)
    
    # Pagination
    paginator = Paginator(client_profiles, 25)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    # Statistics
    stats = {
        'total_profiles': client_profiles.count(),
        'active_profiles': client_profiles.filter(status='active').count(),
        'muted_profiles': client_profiles.filter(status='muted').count(),
        'pending_kyc': client_profiles.filter(
            # Add your KYC pending logic here based on your business rules
        ).count() if hasattr(ClientProfile, 'kyc_status') else 0,
    }
    
    context = {
        'client_profiles': page_obj,
        'search_form': search_form,
        'team_members': team_members,
        'stats': stats,
        'page_obj': page_obj,
    }
    
    return render(request, 'operations/client_profiles.html', context)


@login_required
@user_passes_test(ops_team_lead_required)
def ops_task_assignment(request):
    """Operations Team Lead view for task assignment"""
    user = request.user
    team_members = user.get_team_members()
    
    if request.method == 'POST':
        form = OperationsTaskAssignmentForm(request.POST, current_user=user)
        if form.is_valid():
            task = form.save(commit=False)
            task.assigned_by = user
            task.save()
            messages.success(request, f"Task assigned to {task.assigned_to.get_full_name()}")
            return redirect('ops_task_assignment')
    else:
        form = OperationsTaskAssignmentForm(current_user=user)
    
    # Get team tasks
    team_tasks = Task.objects.filter(
        assigned_to__in=[user] + list(team_members)
    ).select_related('assigned_to', 'assigned_by').order_by('-created_at')
    
    # Task statistics
    task_stats = {
        'total_tasks': team_tasks.count(),
        'pending_tasks': team_tasks.filter(completed=False).count(),
        'completed_tasks': team_tasks.filter(completed=True).count(),
        'overdue_tasks': team_tasks.filter(
            completed=False,
            due_date__lt=timezone.now()
        ).count(),
        'high_priority': team_tasks.filter(
            completed=False,
            priority__in=['high', 'urgent']
        ).count(),
    }
    
    # Individual member task breakdown
    member_task_breakdown = []
    for member in [user] + list(team_members):
        member_tasks = team_tasks.filter(assigned_to=member)
        member_task_breakdown.append({
            'member': member,
            'total': member_tasks.count(),
            'pending': member_tasks.filter(completed=False).count(),
            'completed': member_tasks.filter(completed=True).count(),
            'overdue': member_tasks.filter(
                completed=False,
                due_date__lt=timezone.now()
            ).count(),
        })
    
    context = {
        'form': form,
        'team_tasks': team_tasks[:20],  # Show latest 20 tasks
        'task_stats': task_stats,
        'member_task_breakdown': member_task_breakdown,
        'team_members': team_members,
    }
    
    return render(request, 'operations/task_assignment.html', context)


# Operations Executive Views
@login_required
@user_passes_test(lambda u: u.role == 'ops_exec')
def ops_my_tasks(request):
    """Operations Executive view for personal tasks"""
    user = request.user
    
    # Get user's tasks
    my_tasks = Task.objects.filter(assigned_to=user).select_related('assigned_by')
    
    # Apply filters
    status_filter = request.GET.get('status', 'pending')
    priority_filter = request.GET.get('priority')
    
    if status_filter == 'pending':
        my_tasks = my_tasks.filter(completed=False)
    elif status_filter == 'completed':
        my_tasks = my_tasks.filter(completed=True)
    elif status_filter == 'overdue':
        my_tasks = my_tasks.filter(completed=False, due_date__lt=timezone.now())
    
    if priority_filter:
        my_tasks = my_tasks.filter(priority=priority_filter)
    
    my_tasks = my_tasks.order_by('-created_at')
    
    # Task statistics
    task_stats = {
        'total_tasks': Task.objects.filter(assigned_to=user).count(),
        'pending_tasks': Task.objects.filter(assigned_to=user, completed=False).count(),
        'completed_tasks': Task.objects.filter(assigned_to=user, completed=True).count(),
        'overdue_tasks': Task.objects.filter(
            assigned_to=user,
            completed=False,
            due_date__lt=timezone.now()
        ).count(),
        'due_today': Task.objects.filter(
            assigned_to=user,
            completed=False,
            due_date__date=timezone.now().date()
        ).count(),
        'due_this_week': Task.objects.filter(
            assigned_to=user,
            completed=False,
            due_date__date__range=[
                timezone.now().date(),
                timezone.now().date() + timedelta(days=7)
            ]
        ).count(),
    }
    
    # Performance metrics
    last_30_days = timezone.now() - timedelta(days=30)
    recent_tasks = Task.objects.filter(
        assigned_to=user,
        created_at__gte=last_30_days
    )
    
    performance_metrics = {
        'tasks_last_30_days': recent_tasks.count(),
        'completed_last_30_days': recent_tasks.filter(completed=True).count(),
        'avg_completion_time': 0,  # Calculate based on your business logic
        'completion_rate': 0,
    }
    
    if recent_tasks.exists():
        performance_metrics['completion_rate'] = round(
            (performance_metrics['completed_last_30_days'] / performance_metrics['tasks_last_30_days']) * 100, 2
        )
    
    context = {
        'my_tasks': my_tasks,
        'task_stats': task_stats,
        'performance_metrics': performance_metrics,
        'status_filter': status_filter,
        'priority_filter': priority_filter,
        'priority_choices': Task.PRIORITY_CHOICES,
    }
    
    return render(request, 'operations/my_tasks.html', context)


@login_required
@user_passes_test(lambda u: u.role == 'ops_exec')
def ops_my_clients(request):
    """Operations Executive view for assigned client profiles"""
    user = request.user
    
    # Get assigned client profiles
    my_clients = ClientProfile.objects.filter(
        mapped_ops_exec=user
    ).select_related('mapped_rm')
    
    # Apply filters
    status_filter = request.GET.get('status')
    search_query = request.GET.get('search')
    
    if status_filter:
        my_clients = my_clients.filter(status=status_filter)
    
    if search_query:
        my_clients = my_clients.filter(
            Q(client_full_name__icontains=search_query) |
            Q(email__icontains=search_query) |
            Q(mobile_number__icontains=search_query) |
            Q(pan_number__icontains=search_query)
        )
    
    my_clients = my_clients.order_by('-updated_at')
    
    # Pagination
    paginator = Paginator(my_clients, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    # Client statistics
    client_stats = {
        'total_clients': ClientProfile.objects.filter(mapped_ops_exec=user).count(),
        'active_clients': ClientProfile.objects.filter(mapped_ops_exec=user, status='active').count(),
        'muted_clients': ClientProfile.objects.filter(mapped_ops_exec=user, status='muted').count(),
        'new_this_month': ClientProfile.objects.filter(
            mapped_ops_exec=user,
            created_at__month=timezone.now().month,
            created_at__year=timezone.now().year
        ).count(),
        'updated_today': ClientProfile.objects.filter(
            mapped_ops_exec=user,
            updated_at__date=timezone.now().date()
        ).count(),
    }
    
    # Recent activities
    recent_updates = ClientProfile.objects.filter(
        mapped_ops_exec=user
    ).order_by('-updated_at')[:5]
    
    context = {
        'my_clients': page_obj,
        'client_stats': client_stats,
        'recent_updates': recent_updates,
        'status_filter': status_filter,
        'search_query': search_query,
        'page_obj': page_obj,
    }
    
    return render(request, 'operations/my_clients.html', context)


@login_required
@user_passes_test(lambda u: u.role == 'ops_exec')
def ops_service_requests(request):
    """Operations Executive view for service requests"""
    user = request.user
    
    # Get service requests assigned to user
    my_requests = ServiceRequest.objects.filter(
        assigned_to=user
    ).select_related('client', 'raised_by')
    
    # Apply filters
    status_filter = request.GET.get('status', 'open')
    priority_filter = request.GET.get('priority')
    
    if status_filter and status_filter != 'all':
        my_requests = my_requests.filter(status=status_filter)
    
    if priority_filter:
        my_requests = my_requests.filter(priority=priority_filter)
    
    my_requests = my_requests.order_by('-created_at')
    
    # Service request statistics
    request_stats = {
        'total_requests': ServiceRequest.objects.filter(assigned_to=user).count(),
        'open_requests': ServiceRequest.objects.filter(assigned_to=user, status='open').count(),
        'in_progress': ServiceRequest.objects.filter(assigned_to=user, status='in_progress').count(),
        'resolved_requests': ServiceRequest.objects.filter(assigned_to=user, status='resolved').count(),
        'urgent_requests': ServiceRequest.objects.filter(
            assigned_to=user,
            priority='urgent',
            status__in=['open', 'in_progress']
        ).count(),
    }
    
    # Performance metrics
    last_30_days = timezone.now() - timedelta(days=30)
    recent_requests = ServiceRequest.objects.filter(
        assigned_to=user,
        created_at__gte=last_30_days
    )
    
    resolved_requests = recent_requests.filter(
        status__in=['resolved', 'closed'],
        resolved_at__isnull=False
    )
    
    performance_metrics = {
        'requests_last_30_days': recent_requests.count(),
        'resolved_last_30_days': resolved_requests.count(),
        'resolution_rate': 0,
        'avg_resolution_time_hours': 0,
    }
    
    if recent_requests.exists():
        performance_metrics['resolution_rate'] = round(
            (performance_metrics['resolved_last_30_days'] / performance_metrics['requests_last_30_days']) * 100, 2
        )
    
    if resolved_requests.exists():
        avg_resolution_time = resolved_requests.aggregate(
            avg_time=Avg(
                Extract('epoch', F('resolved_at')) - Extract('epoch', F('created_at'))
            )
        )['avg_time']
        performance_metrics['avg_resolution_time_hours'] = round(avg_resolution_time / 3600, 2) if avg_resolution_time else 0
    
    context = {
        'my_requests': my_requests[:50],  # Limit to 50 for performance
        'request_stats': request_stats,
        'performance_metrics': performance_metrics,
        'status_filter': status_filter,
        'priority_filter': priority_filter,
        'status_choices': ServiceRequest.STATUS_CHOICES,
        'priority_choices': ServiceRequest.PRIORITY_CHOICES if hasattr(ServiceRequest, 'PRIORITY_CHOICES') else Task.PRIORITY_CHOICES,
    }
    
    return render(request, 'operations/service_requests.html', context)


# Business Head Operations Views
@login_required
@user_passes_test(business_head_ops_required)
def bh_ops_overview(request):
    """Business Head Operations overview dashboard"""
    user = request.user
    
    # Get all operations team members
    ops_team_leads = User.objects.filter(role='ops_team_lead')
    ops_executives = User.objects.filter(role='ops_exec')
    
    # Overall operations metrics
    total_client_profiles = ClientProfile.objects.count()
    active_profiles = ClientProfile.objects.filter(status='active').count()
    muted_profiles = ClientProfile.objects.filter(status='muted').count()
    
    # Task metrics
    ops_tasks = Task.objects.filter(assigned_to__role__in=['ops_team_lead', 'ops_exec'])
    pending_ops_tasks = ops_tasks.filter(completed=False).count()
    overdue_ops_tasks = ops_tasks.filter(
        completed=False,
        due_date__lt=timezone.now()
    ).count()
    
    # Service request metrics
    ops_service_requests = ServiceRequest.objects.filter(
        assigned_to__role__in=['ops_team_lead', 'ops_exec']
    )
    open_requests = ops_service_requests.filter(status='open').count()
    in_progress_requests = ops_service_requests.filter(status='in_progress').count()
    
    # Team performance summary
    team_performance = []
    for lead in ops_team_leads:
        team_members = lead.get_team_members()
        team_tasks = Task.objects.filter(assigned_to__in=team_members)
        team_requests = ServiceRequest.objects.filter(assigned_to__in=team_members)
        
        team_performance.append({
            'lead': lead,
            'team_size': team_members.count(),
            'pending_tasks': team_tasks.filter(completed=False).count(),
            'open_requests': team_requests.filter(status='open').count(),
            'client_profiles': ClientProfile.objects.filter(mapped_ops_exec__in=team_members).count(),
        })
    
    # Recent activities
    recent_profiles = ClientProfile.objects.order_by('-created_at')[:10]
    recent_requests = ServiceRequest.objects.filter(
        assigned_to__role__in=['ops_team_lead', 'ops_exec']
    ).order_by('-created_at')[:10]
    
    # Monthly trends (last 6 months)
    monthly_data = []
    for i in range(6):
        month_start = (timezone.now().replace(day=1) - timedelta(days=30*i)).replace(day=1)
        month_end = (month_start + timedelta(days=32)).replace(day=1) - timedelta(days=1)
        
        monthly_data.append({
            'month': month_start.strftime('%b %Y'),
            'profiles_created': ClientProfile.objects.filter(
                created_at__range=[month_start, month_end]
            ).count(),
            'requests_resolved': ServiceRequest.objects.filter(
                resolved_at__range=[month_start, month_end],
                assigned_to__role__in=['ops_team_lead', 'ops_exec']
            ).count(),
        })
    
    context = {
        'ops_team_leads': ops_team_leads,
        'ops_executives': ops_executives,
        'total_client_profiles': total_client_profiles,
        'active_profiles': active_profiles,
        'muted_profiles': muted_profiles,
        'pending_ops_tasks': pending_ops_tasks,
        'overdue_ops_tasks': overdue_ops_tasks,
        'open_requests': open_requests,
        'in_progress_requests': in_progress_requests,
        'team_performance': team_performance,
        'recent_profiles': recent_profiles,
        'recent_requests': recent_requests,
        'monthly_data': list(reversed(monthly_data)),
    }
    
    return render(request, 'operations/bh_ops_overview.html', context)


@login_required
@user_passes_test(business_head_ops_required)
def bh_ops_team_management(request):
    """Business Head Operations team management"""
    user = request.user
    
    # Get operations teams
    ops_teams = Team.objects.filter(is_ops_team=True).select_related('leader')
    ops_users = User.objects.filter(role__in=['ops_team_lead', 'ops_exec']).select_related('manager')
    
    # Team statistics
    team_stats = []
    for team in ops_teams:
        team_members = team.members.all()
        team_tasks = Task.objects.filter(assigned_to__in=team_members)
        team_requests = ServiceRequest.objects.filter(assigned_to__in=team_members)
        
        # Calculate team performance metrics
        total_tasks = team_tasks.count()
        completed_tasks = team_tasks.filter(completed=True).count()
        task_completion_rate = (completed_tasks / total_tasks * 100) if total_tasks > 0 else 0
        
        total_requests = team_requests.count()
        resolved_requests = team_requests.filter(status__in=['resolved', 'closed']).count()
        request_resolution_rate = (resolved_requests / total_requests * 100) if total_requests > 0 else 0
        
        team_stats.append({
            'team': team,
            'member_count': team_members.count(),
            'task_completion_rate': round(task_completion_rate, 2),
            'request_resolution_rate': round(request_resolution_rate, 2),
            'pending_tasks': team_tasks.filter(completed=False).count(),
            'open_requests': team_requests.filter(status='open').count(),
            'performance_score': round((task_completion_rate + request_resolution_rate) / 2, 2),
        })
    
    # Individual user performance
    user_performance = []
    for ops_user in ops_users:
        user_tasks = Task.objects.filter(assigned_to=ops_user)
        user_requests = ServiceRequest.objects.filter(assigned_to=ops_user)
        user_profiles = ClientProfile.objects.filter(mapped_ops_exec=ops_user)
        
        # Calculate individual metrics
        total_tasks = user_tasks.count()
        completed_tasks = user_tasks.filter(completed=True).count()
        task_completion_rate = (completed_tasks / total_tasks * 100) if total_tasks > 0 else 0
        
        total_requests = user_requests.count()
        resolved_requests = user_requests.filter(status__in=['resolved', 'closed']).count()
        request_resolution_rate = (resolved_requests / total_requests * 100) if total_requests > 0 else 0
        
        user_performance.append({
            'user': ops_user,
            'task_completion_rate': round(task_completion_rate, 2),
            'request_resolution_rate': round(request_resolution_rate, 2),
            'client_profiles': user_profiles.count(),
            'pending_tasks': user_tasks.filter(completed=False).count(),
            'open_requests': user_requests.filter(status='open').count(),
            'performance_score': round((task_completion_rate + request_resolution_rate) / 2, 2),
        })
    
    # Sort by performance score
    user_performance.sort(key=lambda x: x['performance_score'], reverse=True)
    
    context = {
        'ops_teams': ops_teams,
        'team_stats': team_stats,
        'user_performance': user_performance,
        'total_ops_users': ops_users.count(),
        'ops_team_leads_count': ops_users.filter(role='ops_team_lead').count(),
        'ops_executives_count': ops_users.filter(role='ops_exec').count(),
    }
    
    return render(request, 'operations/team_management.html', context)


@login_required
@user_passes_test(business_head_ops_required)
def bh_ops_performance_metrics(request):
    """Business Head Operations performance metrics and analytics"""
    user = request.user
    
    # Get date range for filtering
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')
    
    if not date_from:
        date_from = timezone.now().date() - timedelta(days=90)  # Last 3 months
    else:
        date_from = datetime.strptime(date_from, '%Y-%m-%d').date()
    
    if not date_to:
        date_to = timezone.now().date()
    else:
        date_to = datetime.strptime(date_to, '%Y-%m-%d').date()
    
    # Operations team members
    ops_users = User.objects.filter(role__in=['ops_team_lead', 'ops_exec'])
    
    # Task performance metrics
    ops_tasks = Task.objects.filter(
        assigned_to__in=ops_users,
        created_at__date__range=[date_from, date_to]
    )
    
    task_metrics = {
        'total_tasks': ops_tasks.count(),
        'completed_tasks': ops_tasks.filter(completed=True).count(),
        'pending_tasks': ops_tasks.filter(completed=False).count(),
        'overdue_tasks': ops_tasks.filter(
            completed=False,
            due_date__lt=timezone.now()
        ).count(),
        'high_priority_tasks': ops_tasks.filter(priority__in=['high', 'urgent']).count(),
    }
    
    # Service request performance metrics
    ops_requests = ServiceRequest.objects.filter(
        assigned_to__in=ops_users,
        created_at__date__range=[date_from, date_to]
    )
    
    request_metrics = {
        'total_requests': ops_requests.count(),
        'open_requests': ops_requests.filter(status='open').count(),
        'in_progress_requests': ops_requests.filter(status='in_progress').count(),
        'resolved_requests': ops_requests.filter(status__in=['resolved', 'closed']).count(),
        'urgent_requests': ops_requests.filter(priority='urgent').count(),
    }
    
    # Client profile metrics
    client_metrics = {
        'total_profiles': ClientProfile.objects.filter(
            created_at__date__range=[date_from, date_to]
        ).count(),
        'active_profiles': ClientProfile.objects.filter(
            created_at__date__range=[date_from, date_to],
            status='active'
        ).count(),
        'profiles_by_ops': ClientProfile.objects.filter(
            created_at__date__range=[date_from, date_to],
            mapped_ops_exec__in=ops_users
        ).count(),
    }
    
    # Calculate performance rates
    task_completion_rate = (task_metrics['completed_tasks'] / task_metrics['total_tasks'] * 100) if task_metrics['total_tasks'] > 0 else 0
    request_resolution_rate = (request_metrics['resolved_requests'] / request_metrics['total_requests'] * 100) if request_metrics['total_requests'] > 0 else 0
    
    # Weekly performance trends
    weekly_trends = []
    current_date = date_from
    while current_date <= date_to:
        week_end = min(current_date + timedelta(days=6), date_to)
        
        week_tasks = ops_tasks.filter(created_at__date__range=[current_date, week_end])
        week_requests = ops_requests.filter(created_at__date__range=[current_date, week_end])
        
        weekly_trends.append({
            'week_start': current_date,
            'tasks_created': week_tasks.count(),
            'tasks_completed': week_tasks.filter(completed=True).count(),
            'requests_created': week_requests.count(),
            'requests_resolved': week_requests.filter(status__in=['resolved', 'closed']).count(),
        })
        
        current_date = week_end + timedelta(days=1)
    
    # Top performers
    top_performers = []
    for ops_user in ops_users:
        user_tasks = ops_tasks.filter(assigned_to=ops_user)
        user_requests = ops_requests.filter(assigned_to=ops_user)
        
        user_task_rate = (user_tasks.filter(completed=True).count() / user_tasks.count() * 100) if user_tasks.count() > 0 else 0
        user_request_rate = (user_requests.filter(status__in=['resolved', 'closed']).count() / user_requests.count() * 100) if user_requests.count() > 0 else 0
        
        overall_score = (user_task_rate + user_request_rate) / 2
        
        top_performers.append({
            'user': ops_user,
            'task_completion_rate': round(user_task_rate, 2),
            'request_resolution_rate': round(user_request_rate, 2),
            'overall_score': round(overall_score, 2),
            'total_tasks': user_tasks.count(),
            'total_requests': user_requests.count(),
        })
    
    # Sort by overall score
    top_performers.sort(key=lambda x: x['overall_score'], reverse=True)
    
    context = {
        'date_from': date_from,
        'date_to': date_to,
        'task_metrics': task_metrics,
        'request_metrics': request_metrics,
        'client_metrics': client_metrics,
        'task_completion_rate': round(task_completion_rate, 2),
        'request_resolution_rate': round(request_resolution_rate, 2),
        'weekly_trends': weekly_trends,
        'top_performers': top_performers[:10],  # Top 10 performers
        'ops_users_count': ops_users.count(),
    }
    
    return render(request, 'operations/performance_metrics.html', context)


@login_required
@user_passes_test(business_head_ops_required)
def bh_ops_compliance(request):
    """Business Head Operations compliance monitoring"""
    user = request.user
    
    # Get operations team
    ops_users = User.objects.filter(role__in=['ops_team_lead', 'ops_exec'])
    
    # Compliance metrics
    compliance_metrics = {
        'total_client_profiles': ClientProfile.objects.count(),
        'complete_profiles': ClientProfile.objects.exclude(
            Q(client_full_name='') | Q(email='') | Q(mobile_number='') | Q(pan_number='')
        ).count(),
        'incomplete_profiles': ClientProfile.objects.filter(
            Q(client_full_name='') | Q(email='') | Q(mobile_number='') | Q(pan_number='')
        ).count(),
        'missing_ops_assignment': ClientProfile.objects.filter(mapped_ops_exec__isnull=True).count(),
        'missing_rm_assignment': ClientProfile.objects.filter(mapped_rm__isnull=True).count(),
    }
    
    # Calculate compliance rate
    compliance_rate = (compliance_metrics['complete_profiles'] / compliance_metrics['total_client_profiles'] * 100) if compliance_metrics['total_client_profiles'] > 0 else 0
    
    # Overdue tasks compliance
    overdue_tasks = Task.objects.filter(
        assigned_to__in=ops_users,
        completed=False,
        due_date__lt=timezone.now()
    ).select_related('assigned_to')
    
    # Service request SLA compliance
    sla_breached_requests = ServiceRequest.objects.filter(
        assigned_to__in=ops_users,
        status='open',
        created_at__lt=timezone.now() - timedelta(hours=24)  # Assuming 24-hour SLA
    ).select_related('assigned_to', 'client')
    
    # Data quality issues
    data_quality_issues = []
    
    # Check for duplicate PAN numbers
    duplicate_pans = ClientProfile.objects.values('pan_number').annotate(
        count=Count('pan_number')
    ).filter(count__gt=1)
    
    if duplicate_pans.exists():
        data_quality_issues.append({
            'type': 'Duplicate PAN Numbers',
            'count': duplicate_pans.count(),
            'severity': 'High',
            'details': f"{duplicate_pans.count()} PAN numbers have multiple entries"
        })
    
    # Check for missing email addresses
    missing_emails = ClientProfile.objects.filter(email='').count()
    if missing_emails > 0:
        data_quality_issues.append({
            'type': 'Missing Email Addresses',
            'count': missing_emails,
            'severity': 'Medium',
            'details': f"{missing_emails} client profiles missing email addresses"
        })
    
    # Check for invalid mobile numbers
    invalid_mobiles = ClientProfile.objects.exclude(
        mobile_number__regex=r'^[6-9]\d{9}$'
    ).exclude(mobile_number='').count()
    
    if invalid_mobiles > 0:
        data_quality_issues.append({
            'type': 'Invalid Mobile Numbers',
            'count': invalid_mobiles,
            'severity': 'Medium',
            'details': f"{invalid_mobiles} client profiles have invalid mobile numbers"
        })
    
    # Team compliance scores
    team_compliance = []
    for ops_user in ops_users:
        user_profiles = ClientProfile.objects.filter(mapped_ops_exec=ops_user)
        user_tasks = Task.objects.filter(assigned_to=ops_user)
        user_requests = ServiceRequest.objects.filter(assigned_to=ops_user)
        
        # Calculate individual compliance scores
        complete_profiles = user_profiles.exclude(
            Q(client_full_name='') | Q(email='') | Q(mobile_number='') | Q(pan_number='')
        ).count()
        
        profile_completion_rate = (complete_profiles / user_profiles.count() * 100) if user_profiles.count() > 0 else 100
        
        overdue_user_tasks = user_tasks.filter(
            completed=False,
            due_date__lt=timezone.now()
        ).count()
        
        task_compliance_rate = ((user_tasks.count() - overdue_user_tasks) / user_tasks.count() * 100) if user_tasks.count() > 0 else 100
        
        sla_breached_user_requests = user_requests.filter(
            status='open',
            created_at__lt=timezone.now() - timedelta(hours=24)
        ).count()
        
        request_compliance_rate = ((user_requests.count() - sla_breached_user_requests) / user_requests.count() * 100) if user_requests.count() > 0 else 100
        
        overall_compliance = (profile_completion_rate + task_compliance_rate + request_compliance_rate) / 3
        
        team_compliance.append({
            'user': ops_user,
            'profile_completion_rate': round(profile_completion_rate, 2),
            'task_compliance_rate': round(task_compliance_rate, 2),
            'request_compliance_rate': round(request_compliance_rate, 2),
            'overall_compliance': round(overall_compliance, 2),
            'assigned_profiles': user_profiles.count(),
            'overdue_tasks': overdue_user_tasks,
            'sla_breached_requests': sla_breached_user_requests,
        })
    
    # Sort by overall compliance
    team_compliance.sort(key=lambda x: x['overall_compliance'], reverse=True)
    
    context = {
        'compliance_metrics': compliance_metrics,
        'compliance_rate': round(compliance_rate, 2),
        'overdue_tasks': overdue_tasks,
        'sla_breached_requests': sla_breached_requests,
        'data_quality_issues': data_quality_issues,
        'team_compliance': team_compliance,
        'ops_users_count': ops_users.count(),
    }
    
    return render(request, 'operations/compliance.html', context)


# API Endpoints for AJAX calls
@login_required
@require_GET
def get_dashboard_stats(request):
    """API endpoint to get dashboard statistics"""
    user = request.user
    
    try:
        if user.role == 'top_management':
            stats = {
                'total_users': User.objects.count(),
                'total_clients': Client.objects.count(),
                'total_leads': Lead.objects.count(),
                'total_tasks': Task.objects.filter(completed=False).count(),
                'total_service_requests': ServiceRequest.objects.filter(status='open').count(),
            }
        elif user.role in ['business_head', 'business_head_ops']:
            stats = {
                'total_clients': Client.objects.count(),
                'total_leads': Lead.objects.count(),
                'pending_tasks': Task.objects.filter(completed=False).count(),
                'open_service_requests': ServiceRequest.objects.filter(status='open').count(),
            }
        elif user.role in ['rm_head', 'ops_team_lead']:
            accessible_users = user.get_accessible_users()
            stats = {
                'team_members': accessible_users.count(),
                'team_tasks': Task.objects.filter(assigned_to__in=accessible_users, completed=False).count(),
                'team_leads': Lead.objects.filter(assigned_to__in=accessible_users).count(),
                'team_clients': Client.objects.filter(user__in=accessible_users).count(),
            }
        else:  # RM, Ops Exec
            stats = {
                'my_tasks': Task.objects.filter(assigned_to=user, completed=False).count(),
                'my_leads': Lead.objects.filter(assigned_to=user).count(),
                'my_clients': Client.objects.filter(user=user).count(),
            }
        
        return JsonResponse({'success': True, 'stats': stats})
    
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


@login_required
@require_GET
def get_user_hierarchy(request):
    """API endpoint to get user hierarchy data"""
    user = request.user
    
    try:
        hierarchy_data = []
        
        if user.role in ['top_management', 'business_head', 'business_head_ops']:
            # Get all users with their hierarchy
            all_users = User.objects.select_related('manager').all()
            
            for u in all_users:
                hierarchy_data.append({
                    'id': u.id,
                    'name': u.get_full_name() or u.username,
                    'role': u.get_role_display(),
                    'manager_id': u.manager.id if u.manager else None,
                    'email': u.email,
                })
        
        elif user.role in ['rm_head', 'ops_team_lead']:
            # Get accessible users
            accessible_users = user.get_accessible_users()
            
            for u in accessible_users:
                hierarchy_data.append({
                    'id': u.id,
                    'name': u.get_full_name() or u.username,
                    'role': u.get_role_display(),
                    'manager_id': u.manager.id if u.manager else None,
                    'email': u.email,
                })
        
        return JsonResponse({'success': True, 'hierarchy': hierarchy_data})
    
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


@login_required
@require_GET
def get_team_performance(request):
    """API endpoint to get team performance data"""
    user = request.user
    
    try:
        if user.role in ['rm_head', 'ops_team_lead']:
            team_members = user.get_team_members()
            performance_data = []
            
            for member in team_members:
                if user.role == 'rm_head':
                    # RM team performance
                    member_leads = Lead.objects.filter(assigned_to=member)
                    member_clients = Client.objects.filter(user=member)
                    
                    performance_data.append({
                        'user_id': member.id,
                        'name': member.get_full_name() or member.username,
                        'leads': member_leads.count(),
                        'clients': member_clients.count(),
                        'aum': float(member_clients.aggregate(total=Sum('aum'))['total'] or 0),
                    })
                
                elif user.role == 'ops_team_lead':
                    # Operations team performance
                    member_tasks = Task.objects.filter(assigned_to=member)
                    member_requests = ServiceRequest.objects.filter(assigned_to=member)
                    member_profiles = ClientProfile.objects.filter(mapped_ops_exec=member)
                    
                    performance_data.append({
                        'user_id': member.id,
                        'name': member.get_full_name() or member.username,
                        'total_tasks': member_tasks.count(),
                        'completed_tasks': member_tasks.filter(completed=True).count(),
                        'service_requests': member_requests.count(),
                        'client_profiles': member_profiles.count(),
                    })
            
            return JsonResponse({'success': True, 'performance': performance_data})
        
        else:
            return JsonResponse({'success': False, 'error': 'Insufficient permissions'})
    
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


@login_required
@require_POST
def quick_create_note(request):
    """API endpoint for quick note creation"""
    try:
        data = json.loads(request.body)
        
        # Get or create default note list
        note_list, created = NoteList.objects.get_or_create(
            user=request.user,
            name='Quick Notes',
            defaults={'description': 'Quick notes created from dashboard'}
        )
        
        # Create note
        note = Note.objects.create(
            user=request.user,
            note_list=note_list,
            heading=data.get('heading', 'Quick Note'),
            content=data.get('content', ''),
            creation_date=timezone.now().date()
        )
        
        return JsonResponse({
            'success': True,
            'note_id': note.id,
            'message': 'Note created successfully'
        })
    
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


@login_required
@require_POST
def quick_assign_task(request):
    """API endpoint for quick task assignment"""
    try:
        data = json.loads(request.body)
        
        # Get assignee
        assignee_id = data.get('assignee_id')
        if not assignee_id:
            assignee = request.user
        else:
            assignee = User.objects.get(id=assignee_id)
            
            # Check if user can assign to this person
            if not request.user.can_access_user_data(assignee):
                return JsonResponse({'success': False, 'error': 'Permission denied'})
        
        # Create task
        task = Task.objects.create(
            assigned_to=assignee,
            assigned_by=request.user,
            title=data.get('title', 'Quick Task'),
            description=data.get('description', ''),
            priority=data.get('priority', 'medium'),
            due_date=data.get('due_date')
        )
        
        return JsonResponse({
            'success': True,
            'task_id': task.id,
            'message': f'Task assigned to {assignee.get_full_name()}'
        })
    
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


# Error handling views
def permission_denied(request, exception=None):
    """403 error handler"""
    return render(request, 'errors/403.html', status=403)


def not_found(request, exception=None):
    """404 error handler"""
    return render(request, 'errors/404.html', status=404)


def server_error(request):
    """500 error handler"""
    return render(request, 'errors/500.html', status=500)


# Quick access views
@login_required
def quick_note_create(request):
    """Quick note creation for modal/popup"""
    if request.method == 'POST':
        form = QuickNoteForm(request.POST, user=request.user)
        if form.is_valid():
            note = form.save()
            messages.success(request, 'Note created successfully')
            
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({
                    'success': True,
                    'note_id': note.id,
                    'redirect_url': reverse('note_detail', args=[note.id])
                })
            
            return redirect('note_detail', pk=note.id)
    else:
        form = QuickNoteForm(user=request.user)
    
    context = {'form': form}
    
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return render(request, 'notes/quick_note_form.html', context)
    
    return render(request, 'notes/note_form.html', context)


@login_required
def quick_task_create(request):
    """Quick task creation"""
    if request.method == 'POST':
        form = TaskForm(request.POST, current_user=request.user)
        if form.is_valid():
            task = form.save()
            messages.success(request, f'Task assigned to {task.assigned_to.get_full_name()}')
            
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({
                    'success': True,
                    'task_id': task.id,
                    'message': f'Task assigned to {task.assigned_to.get_full_name()}'
                })
            
            return redirect('task_list')
    else:
        form = TaskForm(current_user=request.user)
    
    context = {'form': form}
    
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return render(request, 'tasks/quick_task_form.html', context)
    
    return render(request, 'tasks/task_form.html', context)


@login_required
@require_GET
def quick_client_search(request):
    """Quick client search for autocomplete"""
    query = request.GET.get('q', '')
    
    if len(query) < 2:
        return JsonResponse({'results': []})
    
    # Filter clients based on user access
    if request.user.role in ['top_management', 'business_head', 'business_head_ops']:
        clients = ClientProfile.objects.all()
    elif request.user.role in ['rm_head', 'ops_team_lead']:
        accessible_users = request.user.get_accessible_users()
        clients = ClientProfile.objects.filter(
            Q(mapped_rm__in=accessible_users) | Q(mapped_ops_exec__in=accessible_users)
        )
    elif request.user.role == 'rm':
        clients = ClientProfile.objects.filter(mapped_rm=request.user)
    elif request.user.role == 'ops_exec':
        clients = ClientProfile.objects.filter(mapped_ops_exec=request.user)
    else:
        clients = ClientProfile.objects.none()
    
    # Search clients
    clients = clients.filter(
        Q(client_full_name__icontains=query) |
        Q(email__icontains=query) |
        Q(mobile_number__icontains=query) |
        Q(pan_number__icontains=query)
    )[:10]
    
    results = []
    for client in clients:
        results.append({
            'id': client.id,
            'text': client.client_full_name,
            'email': client.email,
            'mobile': client.mobile_number,
            'pan': client.pan_number,
            'status': client.get_status_display(),
        })
    
    return JsonResponse({'results': results})


@login_required

@require_GET
def quick_lead_search(request):
    """Quick lead search for autocomplete"""
    query = request.GET.get('q', '')
    
    if len(query) < 2:
        return JsonResponse({'results': []})
    
    # Filter leads based on user access
    if request.user.role in ['top_management', 'business_head']:
        leads = Lead.objects.all()
    elif request.user.role == 'rm_head':
        accessible_users = request.user.get_accessible_users()
        leads = Lead.objects.filter(assigned_to__in=accessible_users)
    elif request.user.role == 'rm':
        leads = Lead.objects.filter(assigned_to=request.user)
    else:
        leads = Lead.objects.none()
    
    # Search leads
    leads = leads.filter(
        Q(name__icontains=query) |
        Q(email__icontains=query) |
        Q(mobile__icontains=query) |
        Q(lead_id__icontains=query)
    )[:10]
    
    results = []
    for lead in leads:
        results.append({
            'id': lead.id,
            'text': lead.name,
            'email': lead.email or '',
            'mobile': lead.mobile or '',
            'status': lead.get_status_display(),
            'probability': lead.probability,
            'assigned_to': lead.assigned_to.get_full_name() if lead.assigned_to else '',
        })
    
    return JsonResponse({'results': results})


from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q
from django.core.exceptions import PermissionDenied
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.utils import timezone

from .models import Lead, LeadInteraction, ProductDiscussion, LeadStatusChange
from .forms import (
    LeadForm, 
    LeadInteractionForm, 
    ProductDiscussionForm,
    LeadConversionForm,
    LeadStatusChangeForm,
    LeadReassignmentForm
)
from .models import User

@login_required
def lead_list(request):
    user = request.user
    leads = get_user_accessible_data(user, Lead, 'assigned_to')
    
    # Filtering options
    status_filter = request.GET.get('status')
    if status_filter:
        leads = leads.filter(status=status_filter)
    
    # Search functionality
    search_query = request.GET.get('search')
    if search_query:
        leads = leads.filter(
            Q(name__icontains=search_query) | 
            Q(contact_info__icontains=search_query) |
            Q(source__icontains=search_query) |
            Q(lead_id__icontains=search_query)
        )

    # Filter by conversion status
    converted_filter = request.GET.get('converted')
    if converted_filter == 'true':
        leads = leads.filter(converted=True)
    elif converted_filter == 'false':
        leads = leads.filter(converted=False)

    context = {
        'leads': leads.order_by('-created_at'),
        'status_choices': Lead.STATUS_CHOICES,
        'current_status': status_filter,
        'search_query': search_query,
        'converted_filter': converted_filter,
    }
    
    return render(request, 'base/leads.html', context)

@login_required
def lead_detail(request, pk):
    lead = get_object_or_404(Lead, pk=pk)
    
    # Check permissions
    if not request.user.can_access_user_data(lead.assigned_to):
        raise PermissionDenied("You don't have permission to view this lead.")
    
    interactions = lead.interactions.all().order_by('-interaction_date')
    product_discussions = lead.product_discussions.all()
    status_changes = lead.status_changes.all().order_by('-changed_at')
    
    # Forms for interaction and status change
    interaction_form = LeadInteractionForm()
    status_change_form = LeadStatusChangeForm()
    product_discussion_form = ProductDiscussionForm()
    
    # Conversion form (only for managers)
    conversion_form = None
    if request.user.role in ['rm_head', 'business_head', 'top_management'] and not lead.converted:
        conversion_form = LeadConversionForm()
    
    # Reassignment form (only for managers)
    reassignment_form = None
    if request.user.role in ['rm_head', 'business_head', 'top_management']:
        reassignment_form = LeadReassignmentForm(user=request.user)
    
    product_choices = ProductDiscussion.PRODUCT_CHOICES
    context = {
        'lead': lead,
        'interactions': interactions,
        'product_choices': product_choices,
        'product_discussions': product_discussions,
        'status_changes': status_changes,
        'interaction_form': interaction_form,
        'status_change_form': status_change_form,
        'product_discussion_form': product_discussion_form,
        'conversion_form': conversion_form,
        'reassignment_form': reassignment_form,
    }
    
    return render(request, 'base/lead_detail.html', context)

@login_required
def lead_create(request):
    if not request.user.role in ['rm_head', 'business_head', 'top_management']:
        messages.error(request, "You don't have permission to create leads.")
        return redirect('lead_list')
        
    if request.method == 'POST':
        form = LeadForm(request.POST)
        if form.is_valid():
            lead = form.save(commit=False)
            lead.created_by = request.user
            lead.status = 'new'  # Default status
            lead.lead_id = generate_lead_id()  # Custom function to generate ID
            lead.save()
            
            # Create initial status change record
            LeadStatusChange.objects.create(
                lead=lead,
                changed_by=request.user,
                old_status='',
                new_status='new',
                notes='Lead created'
            )
            
            messages.success(request, "Lead created successfully.")
            return redirect('lead_detail', pk=lead.pk)
    else:
        form = LeadForm()
        
        # Limit assignee choices based on user's role and team
        if request.user.role == 'rm_head':
            accessible_users = request.user.get_accessible_users()
            form.fields['assigned_to'].queryset = User.objects.filter(
                id__in=[u.id for u in accessible_users],
                role__in=['rm', 'rm_head']
            )
    
    return render(request, 'base/lead_form.html', {'form': form, 'action': 'Create'})

@login_required
def lead_update(request, pk):
    lead = get_object_or_404(Lead, pk=pk)
    
    # Check permissions
    if not request.user.can_access_user_data(lead.assigned_to):
        raise PermissionDenied("You don't have permission to edit this lead.")
    
    if request.method == 'POST':
        form = LeadForm(request.POST, instance=lead)
        if form.is_valid():
            old_status = lead.status
            lead = form.save()
            
            # Record status change if it was modified
            if old_status != lead.status:
                LeadStatusChange.objects.create(
                    lead=lead,
                    changed_by=request.user,
                    old_status=old_status,
                    new_status=lead.status,
                    notes='Status updated via lead edit'
                )
                
            messages.success(request, "Lead updated successfully.")
            return redirect('lead_detail', pk=lead.pk)
    else:
        form = LeadForm(instance=lead)
        
        # Limit assignee choices based on user's role
        if request.user.role == 'rm_head':
            accessible_users = request.user.get_accessible_users()
            form.fields['assigned_to'].queryset = User.objects.filter(
                id__in=[u.id for u in accessible_users],
                role__in=['rm', 'rm_head']
            )
    
    return render(request, 'base/lead_form.html', {'form': form, 'action': 'Update', 'lead': lead})

@login_required
def lead_delete(request, pk):
    lead = get_object_or_404(Lead, pk=pk)
    
    # Check permissions
    if not request.user.can_access_user_data(lead.assigned_to):
        raise PermissionDenied("You don't have permission to delete this lead.")
    
    if request.method == 'POST':
        lead.delete()
        messages.success(request, "Lead deleted successfully.")
        return redirect('lead_list')
    
    return render(request, 'base/lead_confirm_delete.html', {'lead': lead})

@login_required
@require_POST
def add_interaction(request, pk):
    lead = get_object_or_404(Lead, pk=pk)
    
    # Check permissions
    if not request.user.can_access_user_data(lead.assigned_to):
        raise PermissionDenied("You don't have permission to add interactions for this lead.")
    
    form = LeadInteractionForm(request.POST)
    
    if not form.is_valid():
        # Collect all form errors for display
        error_list = []
        for field, errors in form.errors.items():
            field_name = form.fields[field].label or field
            error_list.append(f"{field_name}: {' '.join(errors)}")
        
        messages.error(request, "Please correct the errors below: " + ", ".join(error_list))
        return redirect('lead_detail', pk=pk)
    
    try:
        with transaction.atomic():
            interaction = form.save(commit=False)
            interaction.lead = lead
            interaction.interacted_by = request.user
            interaction.save()
            
            # Handle first interaction logic
            if not lead.first_interaction_date:
                lead.first_interaction_date = interaction.interaction_date
                lead.status = 'contacted'
                lead.save()
                
                LeadStatusChange.objects.create(
                    lead=lead,
                    changed_by=request.user,
                    old_status=lead.status,
                    new_status='contacted',
                    notes='First interaction completed'
                )
            
            messages.success(request, f"{interaction.get_interaction_type_display()} interaction added successfully.")
    
    except Exception as e:
        messages.error(request, f"Failed to save interaction: {str(e)}")
    
    return redirect('lead_detail', pk=pk)

@login_required
@require_POST
def add_product_discussion(request, pk):
    lead = get_object_or_404(Lead, pk=pk)
    
    # Check permissions
    if not request.user.can_access_user_data(lead.assigned_to):
        raise PermissionDenied("You don't have permission to add product discussions for this lead.")
    
    # Check if this is the first interaction
    if not lead.interactions.exists():
        messages.error(request, "You must have at least one interaction before adding product discussions.")
        return redirect('lead_detail', pk=lead.pk)
    
    form = ProductDiscussionForm(request.POST)
    if form.is_valid():
        discussion = form.save(commit=False)
        discussion.lead = lead
        discussion.discussed_by = request.user
        discussion.save()
        messages.success(request, "Product discussion added successfully.")
    else:
        messages.error(request, "Error adding product discussion.")
    
    return redirect('lead_detail', pk=lead.pk)

@login_required
@require_POST
def change_lead_status(request, pk):
    lead = get_object_or_404(Lead, pk=pk)
    
    # Check permissions
    if not request.user.can_access_user_data(lead.assigned_to):
        raise PermissionDenied("You don't have permission to change status for this lead.")
    
    form = LeadStatusChangeForm(request.POST)
    if form.is_valid():
        new_status = form.cleaned_data['new_status']
        notes = form.cleaned_data['notes']
        
        # Record status change
        LeadStatusChange.objects.create(
            lead=lead,
            changed_by=request.user,
            old_status=lead.status,
            new_status=new_status,
            notes=notes
        )
        
        # Update lead status
        lead.status = new_status
        lead.save()
        
        messages.success(request, f"Lead status changed to {new_status}.")
    else:
        messages.error(request, "Error changing lead status.")
    
    return redirect('lead_detail', pk=lead.pk)

@login_required
@require_POST
def request_conversion(request, pk):
    lead = get_object_or_404(Lead, pk=pk)
    
    # Check permissions
    if not request.user.can_access_user_data(lead.assigned_to):
        raise PermissionDenied("You don't have permission to request conversion for this lead.")
    
    if lead.converted:
        messages.error(request, "This lead is already converted.")
        return redirect('lead_detail', pk=lead.pk)
    
    # Check if conversion is already requested
    if lead.status == 'conversion_requested':
        messages.warning(request, "Conversion request is already pending approval.")
        return redirect('lead_detail', pk=lead.pk)
    
    # Find the appropriate manager for approval
    approval_manager = lead.assigned_to.get_approval_manager()  # Use the new method
    
    if not approval_manager:
        messages.error(request, 
            f"No manager found to approve conversion for {lead.assigned_to.get_full_name()}. "
            "Please contact your administrator to set up the reporting hierarchy."
        )
        return redirect('lead_detail', pk=lead.pk)
    
    # Create a status change record as conversion request
    LeadStatusChange.objects.create(
        lead=lead,
        changed_by=request.user,
        old_status=lead.status,
        new_status='conversion_requested',
        notes=f'Conversion requested by {request.user.get_full_name()} - pending approval from {approval_manager.get_full_name()}',
        needs_approval=True,
        approval_by=approval_manager
    )
    
    # Update lead status
    lead.status = 'conversion_requested'
    lead.save()
    
    # TODO: Send notification to approval manager
    # You might want to add notification logic here
    
    messages.success(request, 
        f"Conversion request sent to {approval_manager.get_full_name()} for approval."
    )
    return redirect('lead_detail', pk=lead.pk)

@login_required
@require_POST
def convert_lead(request, pk):
    if not request.user.role in ['rm_head', 'business_head', 'top_management']:
        messages.error(request, "You don't have permission to convert leads.")
        return redirect('lead_detail', pk=pk)
    
    lead = get_object_or_404(Lead, pk=pk)
    form = LeadConversionForm(request.POST)
    
    if form.is_valid():
        # Update lead as converted
        lead.converted = True
        lead.converted_at = timezone.now()
        lead.converted_by = request.user
        lead.client_id = generate_client_id()  # Custom function
        lead.save()
        
        # Record status change
        LeadStatusChange.objects.create(
            lead=lead,
            changed_by=request.user,
            old_status=lead.status,
            new_status='converted',
            notes=f"Lead converted to client {lead.client_id}"
        )
        
        messages.success(request, f"Lead successfully converted to client {lead.client_id}.")
    else:
        messages.error(request, "Error converting lead.")
    
    return redirect('lead_detail', pk=lead.pk)

@login_required
@require_POST
def reassign_lead(request, pk):
    if not request.user.role in ['rm_head', 'business_head', 'top_management']:
        messages.error(request, "You don't have permission to reassign leads.")
        return redirect('lead_detail', pk=pk)
    
    lead = get_object_or_404(Lead, pk=pk)
    form = LeadReassignmentForm(request.user, request.POST)
    
    if form.is_valid():
        new_rm = form.cleaned_data['assigned_to']
        old_rm = lead.assigned_to
        
        # Record reassignment
        LeadStatusChange.objects.create(
            lead=lead,
            changed_by=request.user,
            old_status=f"assigned_to:{old_rm.id}",
            new_status=f"assigned_to:{new_rm.id}",
            notes=f"Lead reassigned from {old_rm.get_full_name()} to {new_rm.get_full_name()}"
        )
        
        # Update lead
        lead.assigned_to = new_rm
        lead.save()
        
        # TODO: Send notification to new RM
        
        messages.success(request, f"Lead successfully reassigned to {new_rm.get_full_name()}.")
    else:
        messages.error(request, "Error reassigning lead.")
    
    return redirect('lead_detail', pk=lead.pk)

@login_required
@require_POST
def approve_conversion(request, pk):
    if not request.user.role in ['rm_head', 'business_head', 'top_management']:
        messages.error(request, "You don't have permission to approve conversions.")
        return redirect('rm_head_dashboard')
    
    lead = get_object_or_404(Lead, pk=pk)
    approval_id = request.POST.get('approval_id')
    
    try:
        approval = LeadStatusChange.objects.get(id=approval_id, lead=lead, needs_approval=True)
    except LeadStatusChange.DoesNotExist:
        messages.error(request, "Approval request not found or already processed.")
        return redirect('rm_head_dashboard')
    
    # Update the approval record
    approval.approved = True
    approval.approved_at = timezone.now()
    approval.approved_by = request.user
    approval.needs_approval = False
    approval.save()
    
    # Convert the lead
    lead.converted = True
    lead.converted_at = timezone.now()
    lead.converted_by = request.user
    lead.client_id = generate_client_id()
    lead.status = 'converted'
    lead.save()
    
    # Create a new status change record for the conversion
    LeadStatusChange.objects.create(
        lead=lead,
        changed_by=request.user,
        old_status=approval.new_status,
        new_status='converted',
        notes=f"Conversion approved by {request.user.get_full_name()}",
        approved=True,
        approved_by=request.user,
        approved_at=timezone.now()
    )
    
    messages.success(request, f"Lead successfully converted to client {lead.client_id}.")
    return redirect('rm_head_dashboard')

@login_required
@require_POST
def reject_conversion(request, pk):
    if not request.user.role in ['rm_head', 'business_head', 'top_management']:
        messages.error(request, "You don't have permission to reject conversions.")
        return redirect('rm_head_dashboard')
    
    lead = get_object_or_404(Lead, pk=pk)
    approval_id = request.POST.get('approval_id')
    
    try:
        approval = LeadStatusChange.objects.get(id=approval_id, lead=lead, needs_approval=True)
    except LeadStatusChange.DoesNotExist:
        messages.error(request, "Approval request not found or already processed.")
        return redirect('rm_head_dashboard')
    
    # Update the approval record
    approval.approved = False
    approval.approved_at = timezone.now()
    approval.approved_by = request.user
    approval.needs_approval = False
    approval.notes = f"Conversion rejected by {request.user.get_full_name()}. " + (request.POST.get('rejection_reason', '') or "No reason provided")
    approval.save()
    
    # Revert lead status to previous status
    lead.status = approval.old_status
    lead.save()
    
    # Create a new status change record for the rejection
    LeadStatusChange.objects.create(
        lead=lead,
        changed_by=request.user,
        old_status='conversion_requested',
        new_status=approval.old_status,
        notes=f"Conversion rejected by {request.user.get_full_name()}",
        approved=False,
        approved_by=request.user,
        approved_at=timezone.now()
    )
    
    messages.warning(request, "Conversion request has been rejected.")
    return redirect('rm_head_dashboard')

# Helper functions
def generate_lead_id():
    """Generate a unique lead ID"""
    from datetime import datetime
    prefix = "LD"
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    return f"{prefix}{timestamp}"

def generate_client_id():
    """Generate a unique client ID"""
    from datetime import datetime
    prefix = "CL"
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    return f"{prefix}{timestamp}"

@login_required
@require_POST
def delete_interaction(request, interaction_id):
    interaction = get_object_or_404(LeadInteraction, pk=interaction_id)
    lead_pk = interaction.lead.pk
    
    # Check permissions
    if not (request.user == interaction.interacted_by or 
            request.user.can_access_user_data(interaction.lead.assigned_to)):
        raise PermissionDenied("You don't have permission to delete this interaction.")
    
    interaction.delete()
    messages.success(request, "Interaction deleted successfully.")
    return redirect('leads:lead_detail', pk=lead_pk)

@login_required
@require_POST
def request_reassignment(request, pk):
    lead = get_object_or_404(Lead, pk=pk)
    
    # Check permissions
    if not request.user.can_access_user_data(lead.assigned_to):
        raise PermissionDenied("You don't have permission to request reassignment for this lead.")
    
    new_rm_id = request.POST.get('new_rm')
    try:
        new_rm = User.objects.get(pk=new_rm_id, role__in=['rm', 'rm_head'])
    except User.DoesNotExist:
        messages.error(request, "Invalid RM selected.")
        return redirect('leads:lead_detail', pk=pk)
    
    if lead.assigned_to == new_rm:
        messages.warning(request, "Lead is already assigned to this RM.")
        return redirect('leads:lead_detail', pk=pk)
    
    # Request reassignment
    lead.needs_reassignment_approval = True
    lead.reassignment_requested_to = request.user.get_line_manager()
    lead.save()
    
    # Create status change record
    LeadStatusChange.objects.create(
        lead=lead,
        changed_by=request.user,
        old_status=f"assigned_to:{lead.assigned_to.id}",
        new_status=f"assigned_to:{new_rm.id}",
        notes=f"Reassignment requested to {new_rm.get_full_name()}",
        needs_approval=True,
        approval_by=request.user.get_line_manager()
    )
    
    messages.success(request, "Reassignment request sent to your manager.")
    return redirect('leads:lead_detail', pk=pk)

@login_required
@require_POST
def approve_reassignment(request, pk):
    lead = get_object_or_404(Lead, pk=pk)
    
    # Check if current user is the approver
    if request.user != lead.reassignment_requested_to:
        raise PermissionDenied("You don't have permission to approve this reassignment.")
    
    # Get the latest reassignment request
    status_change = lead.status_changes.filter(needs_approval=True).latest('changed_at')
    
    # Extract new RM ID from status change
    new_rm_id = status_change.new_status.split(':')[-1]
    try:
        new_rm = User.objects.get(pk=new_rm_id)
    except User.DoesNotExist:
        messages.error(request, "The requested RM no longer exists.")
        return redirect('leads:lead_detail', pk=pk)
    
    # Approve the reassignment
    lead.assigned_to = new_rm
    lead.needs_reassignment_approval = False
    lead.reassignment_requested_to = None
    lead.save()
    
    # Update status change record
    status_change.approved = True
    status_change.approved_by = request.user
    status_change.approved_at = timezone.now()
    status_change.save()
    
    messages.success(request, f"Lead successfully reassigned to {new_rm.get_full_name()}.")
    return redirect('leads:lead_detail', pk=pk)

@login_required
def get_reference_clients(request):
    """AJAX view to get reference clients for autocomplete"""
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'Not authenticated'}, status=403)
    
    query = request.GET.get('q', '')
    clients = Lead.objects.filter(
        Q(converted=True),
        Q(name__icontains=query) | Q(client_id__icontains=query)
    ).values('id', 'name', 'client_id')[:10]
    
    return JsonResponse(list(clients), safe=False)

@login_required
def get_accessible_users(request):
    """AJAX view to get accessible users for current user"""
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'Not authenticated'}, status=403)
    
    query = request.GET.get('q', '')
    accessible_users = request.user.get_accessible_users()
    
    users = User.objects.filter(
        Q(id__in=[u.id for u in accessible_users]),
        Q(first_name__icontains=query) | Q(last_name__icontains=query) | Q(email__icontains=query)
    ).values('id', 'first_name', 'last_name', 'email', 'role')[:10]
    
    return JsonResponse(list(users), safe=False)


# Client Views with Hierarchy
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db.models import Q, Sum, Count, IntegerField
from django.db.models.functions import Coalesce
from django.forms import ModelForm
from django import forms
from .models import ClientProfile, User, MFUCANAccount, MotilalDematAccount, PrabhudasDematAccount
from .forms import ClientProfileForm  # Import the form

# Add this to your views.py

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.urls import reverse
from django import forms

# Form for converting client profile to full client
class ConvertToClientForm(forms.ModelForm):
    class Meta:
        model = Client
        fields = ['aum', 'sip_amount', 'demat_count', 'contact_info']
        widgets = {
            'aum': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter AUM amount',
                'step': '0.01'
            }),
            'sip_amount': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter SIP amount',
                'step': '0.01'
            }),
            'demat_count': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': 'Number of demat accounts',
                'min': '0'
            }),
            'contact_info': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Additional contact information'
            })
        }
        labels = {
            'aum': 'Assets Under Management (AUM)',
            'sip_amount': 'SIP Amount',
            'demat_count': 'Number of Demat Accounts',
            'contact_info': 'Additional Contact Information'
        }

@login_required
def convert_to_client(request, profile_id):
    """Convert a client profile to a full client"""
    profile = get_object_or_404(ClientProfile, id=profile_id)
    
    # Check if user has permission to convert
    if not request.user.role in ['rm', 'rm_head', 'business_head', 'top_management']:
        messages.error(request, "You don't have permission to convert client profiles.")
        return redirect('client_profile_list')
    
    # Check if profile is already converted
    if hasattr(profile, 'legacy_client') and profile.legacy_client:
        messages.warning(request, "This client profile is already converted to a full client.")
        return redirect('client_profile_detail', pk=profile.id)
    
    # Role-based access control
    if request.user.role == 'rm' and profile.mapped_rm != request.user:
        messages.error(request, "You can only convert your own client profiles.")
        return redirect('client_profile_list')
    
    if request.method == 'POST':
        form = ConvertToClientForm(request.POST)
        if form.is_valid():
            # Create new client instance
            client = form.save(commit=False)
            client.name = profile.client_full_name
            client.user = profile.mapped_rm
            client.client_profile = profile
            client.created_by = request.user
            client.save()
            
            messages.success(
                request, 
                f"Client profile '{profile.client_full_name}' has been successfully converted to a full client."
            )
            return redirect('client_profile_list')
    else:
        form = ConvertToClientForm()
    
    context = {
        'form': form,
        'profile': profile,
        'page_title': f'Convert {profile.client_full_name} to Full Client'
    }
    
    return render(request, 'base/convert_to_client.html', context)

# Update your client_profile_list view to include the convert permission and stats
@login_required
def client_profile_list(request):
    """List client profiles with hierarchy-based access control"""
    user = request.user
    
    # Get client profiles based on user role
    if user.role in ['top_management', 'business_head']:
        client_profiles = ClientProfile.objects.all()
    elif user.role == 'rm_head':
        # RM Head can see profiles of RMs in their team
        accessible_users = user.get_accessible_users()
        client_profiles = ClientProfile.objects.filter(
            Q(mapped_rm__in=accessible_users) | 
            Q(created_by=user)
        )
    elif user.role == 'rm':
        # RMs can only see their own client profiles
        client_profiles = ClientProfile.objects.filter(mapped_rm=user)
    elif user.role in ['ops_team_lead', 'ops_exec']:
        # Operations team can see all profiles for their work
        client_profiles = ClientProfile.objects.all()
    else:
        client_profiles = ClientProfile.objects.none()
    
    # Search functionality
    search_query = request.GET.get('search')
    if search_query:
        client_profiles = client_profiles.filter(
            Q(client_full_name__icontains=search_query) | 
            Q(email__icontains=search_query) |
            Q(mobile_number__icontains=search_query) |
            Q(pan_number__icontains=search_query)
        )

    # Filter by status
    status_filter = request.GET.get('status')
    if status_filter:
        client_profiles = client_profiles.filter(status=status_filter)

    # Filter by RM (for managers)
    rm_filter = request.GET.get('rm')
    if rm_filter and user.role in ['rm_head', 'business_head', 'top_management']:
        client_profiles = client_profiles.filter(mapped_rm_id=rm_filter)

    # Get statistics
    stats = client_profiles.aggregate(
        total_clients=Count('id'),
        active_clients=Count('id', filter=Q(status='active')),
        muted_clients=Count('id', filter=Q(status='muted')),
        converted_clients=Count('id', filter=Q(legacy_client__isnull=False)),
    )

    # Get RM list for filter dropdown
    if user.role in ['rm_head', 'business_head', 'top_management']:
        if user.role == 'rm_head':
            accessible_users = user.get_accessible_users()
            rm_list = User.objects.filter(
                id__in=[u.id for u in accessible_users],
                role='rm'
            )
        else:
            rm_list = User.objects.filter(role='rm')
    else:
        rm_list = None

    context = {
        'client_profiles': client_profiles.select_related('mapped_rm', 'mapped_ops_exec', 'legacy_client').order_by('-created_at'),
        'search_query': search_query,
        'status_filter': status_filter,
        'rm_filter': rm_filter,
        'stats': stats,
        'rm_list': rm_list,
        'can_create': user.role in ['rm', 'rm_head', 'business_head', 'top_management'],
        'can_modify': user.can_modify_client_profile(),
        'can_convert_to_client': user.role in ['rm', 'rm_head', 'business_head', 'top_management'],
    }
    
    return render(request, 'base/client_profiles.html', context)

@login_required
def client_profile_create(request):
    """Create a new client profile"""
    if not request.user.role in ['rm', 'rm_head', 'business_head', 'top_management']:
        messages.error(request, "You don't have permission to create client profiles.")
        return redirect('client_profile_list')
        
    if request.method == 'POST':
        form = ClientProfileForm(request.POST, current_user=request.user)
        if form.is_valid():
            client_profile = form.save(commit=False)
            client_profile.created_by = request.user
            
            # Auto-assign RM if user is an RM and no RM is mapped
            if request.user.role == 'rm' and not client_profile.mapped_rm:
                client_profile.mapped_rm = request.user
                
            client_profile.save()
            messages.success(request, "Client profile created successfully.")
            return redirect('client_profile_list')
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        form = ClientProfileForm(current_user=request.user)
    
    return render(request, 'base/client_profile_form.html', {
        'form': form, 
        'action': 'Create',
        'title': 'Create Client Profile'
    })

@login_required
def client_profile_detail(request, pk):
    """View client profile details"""
    client_profile = get_object_or_404(ClientProfile, pk=pk)
    
    # Check permissions
    if not request.user.can_view_client_profile():
        raise PermissionDenied("You don't have permission to view client profiles.")
    
    # Check if user can access this specific client's data
    if not request.user.can_access_user_data(client_profile.mapped_rm):
        raise PermissionDenied("You don't have permission to view this client's profile.")
    
    # Get related accounts using the correct related names from your models
    mfu_accounts = client_profile.mfu_accounts.all()
    motilal_accounts = client_profile.motilal_accounts.all()
    prabhudas_accounts = client_profile.prabhudas_accounts.all()
    
    # Get modification history if available
    try:
        modifications = client_profile.modifications.select_related('requested_by', 'approved_by').order_by('-requested_at')[:10]
    except AttributeError:
        modifications = []
    
    context = {
        'client_profile': client_profile,
        'mfu_accounts': mfu_accounts,
        'motilal_accounts': motilal_accounts,
        'prabhudas_accounts': prabhudas_accounts,
        'modifications': modifications,
        'can_modify': request.user.can_modify_client_profile(),
        'can_mute': request.user.role in ['business_head', 'top_management', 'ops_team_lead'],
    }
    
    return render(request, 'base/client_profile_detail.html', context)

@login_required
def client_profile_update(request, pk):
    """Update client profile"""
    client_profile = get_object_or_404(ClientProfile, pk=pk)
    
    # Check permissions
    if not request.user.can_modify_client_profile():
        messages.error(request, "You don't have permission to modify client profiles.")
        return redirect('client_profile_detail', pk=pk)
    
    # Check if user can access this specific client's data
    if not request.user.can_access_user_data(client_profile.mapped_rm):
        raise PermissionDenied("You don't have permission to edit this client's profile.")
    
    if request.method == 'POST':
        # FIXED: Use current_user instead of user
        form = ClientProfileForm(request.POST, instance=client_profile, current_user=request.user)
        if form.is_valid():
            # For critical fields, create modification request instead of direct update
            critical_fields = ['pan_number', 'client_full_name', 'date_of_birth']
            has_critical_changes = any(
                form.cleaned_data.get(field) != getattr(client_profile, field) 
                for field in critical_fields if field in form.cleaned_data
            )
            
            if has_critical_changes and request.user.role not in ['top_management']:
                # Create modification request
                try:
                    from .models import ClientProfileModification
                    import json
                    
                    modification_data = {}
                    for field in critical_fields:
                        if field in form.cleaned_data and form.cleaned_data.get(field) != getattr(client_profile, field):
                            modification_data[field] = form.cleaned_data.get(field)
                    
                    ClientProfileModification.objects.create(
                        client=client_profile,
                        requested_by=request.user,
                        modification_data=modification_data,
                        reason=request.POST.get('modification_reason', 'Profile update'),
                        requires_top_management=True
                    )
                    
                    messages.info(request, "Critical field changes require approval. Modification request submitted.")
                    return redirect('client_profile_detail', pk=pk)
                except ImportError:
                    # If ClientProfileModification model doesn't exist, proceed with direct update
                    form.save()
                    messages.success(request, "Client profile updated successfully.")
                    return redirect('client_profile_detail', pk=pk)
            else:
                form.save()
                messages.success(request, "Client profile updated successfully.")
                return redirect('client_profile_detail', pk=pk)
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        # FIXED: Use current_user instead of user
        form = ClientProfileForm(instance=client_profile, current_user=request.user)
    
    return render(request, 'base/client_profile_form.html', {
        'form': form, 
        'action': 'Update',
        'title': 'Update Client Profile',
        'client_profile': client_profile
    })

@login_required
def client_profile_mute(request, pk):
    """Mute/Unmute client profile"""
    client_profile = get_object_or_404(ClientProfile, pk=pk)
    
    # Check permissions
    if not request.user.role in ['business_head', 'top_management', 'ops_team_lead']:
        messages.error(request, "You don't have permission to mute/unmute clients.")
        return redirect('client_profile_detail', pk=pk)
    
    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'mute' and client_profile.status == 'active':
            reason = request.POST.get('mute_reason')
            if not reason:
                messages.error(request, "Mute reason is required.")
                return redirect('client_profile_detail', pk=pk)
            
            try:
                client_profile.mute_client(reason, request.user)
                messages.success(request, "Client has been muted successfully.")
            except AttributeError:
                # If mute_client method doesn't exist, update status directly
                client_profile.status = 'muted'
                client_profile.save()
                messages.success(request, "Client has been muted successfully.")
            
        elif action == 'unmute' and client_profile.status == 'muted':
            try:
                client_profile.unmute_client(request.user)
                messages.success(request, "Client has been unmuted successfully.")
            except AttributeError:
                # If unmute_client method doesn't exist, update status directly
                client_profile.status = 'active'
                client_profile.save()
                messages.success(request, "Client has been unmuted successfully.")
        
        return redirect('client_profile_detail', pk=pk)
    
    return render(request, 'base/client_profile_mute.html', {
        'client_profile': client_profile
    })

@login_required
def client_profile_delete(request, pk):
    """Delete client profile (restricted to top management)"""
    client_profile = get_object_or_404(ClientProfile, pk=pk)
    
    # Only top management can delete client profiles
    if request.user.role != 'top_management':
        messages.error(request, "You don't have permission to delete client profiles.")
        return redirect('client_profile_detail', pk=pk)
    
    if request.method == 'POST':
        client_name = client_profile.client_full_name
        client_profile.delete()
        messages.success(request, f"Client profile for {client_name} has been deleted.")
        return redirect('client_profile_list')
    
    return render(request, 'base/client_profile_confirm_delete.html', {
        'client_profile': client_profile
    })

@login_required
def modification_requests(request):
    """View pending modification requests"""
    if not request.user.role in ['top_management', 'business_head']:
        messages.error(request, "You don't have permission to view modification requests.")
        return redirect('client_profile_list')
    
    try:
        from .models import ClientProfileModification
        
        # Get pending modifications
        pending_modifications = ClientProfileModification.objects.filter(
            status='pending'
        ).select_related('client', 'requested_by').order_by('-requested_at')
        
        # Get recent approved/rejected modifications
        recent_modifications = ClientProfileModification.objects.filter(
            status__in=['approved', 'rejected']
        ).select_related('client', 'requested_by', 'approved_by').order_by('-approved_at')[:20]
        
        context = {
            'pending_modifications': pending_modifications,
            'recent_modifications': recent_modifications,
        }
        
        return render(request, 'base/client_modification_requests.html', context)
    except ImportError:
        messages.error(request, "Modification requests feature is not available.")
        return redirect('client_profile_list')

@login_required
def approve_modification(request, pk):
    """Approve or reject modification request"""
    if not request.user.role in ['top_management', 'business_head']:
        messages.error(request, "You don't have permission to approve modifications.")
        return redirect('client_profile_list')
    
    try:
        from .models import ClientProfileModification
        modification = get_object_or_404(ClientProfileModification, pk=pk)
        
        if request.method == 'POST':
            action = request.POST.get('action')
            
            if action == 'approve':
                if modification.approve(request.user):
                    messages.success(request, "Modification approved and applied successfully.")
                else:
                    messages.error(request, "Failed to approve modification.")
            elif action == 'reject':
                if modification.reject(request.user):
                    messages.success(request, "Modification rejected.")
                else:
                    messages.error(request, "Failed to reject modification.")
            
            return redirect('modification_requests')
        
        return render(request, 'base/client_approve_modification.html', {
            'modification': modification
        })
    except ImportError:
        messages.error(request, "Modification requests feature is not available.")
        return redirect('client_profile_list')

# Legacy Client Views (for backward compatibility)
@login_required
def client_list(request):
    """Legacy client list view - redirects to new client profile list"""
    messages.info(request, "Redirected to new Client Profile system.")
    return redirect('client_profile_list')

@login_required
def client_create(request):
    """Legacy client create view - redirects to new client profile create"""
    messages.info(request, "Redirected to new Client Profile system.")
    return redirect('client_profile_create')

@login_required
def client_update(request, pk):
    """Legacy client update view"""
    # Try to find corresponding client profile
    try:
        from .models import Client
        client = get_object_or_404(Client, pk=pk)
        if hasattr(client, 'client_profile') and client.client_profile:
            return redirect('client_profile_update', pk=client.client_profile.pk)
        else:
            messages.error(request, "No corresponding client profile found.")
            return redirect('client_profile_list')
    except ImportError:
        messages.error(request, "Legacy client system is not available.")
        return redirect('client_profile_list')

@login_required
def client_delete(request, pk):
    """Legacy client delete view"""
    try:
        from .models import Client
        client = get_object_or_404(Client, pk=pk)
        if hasattr(client, 'client_profile') and client.client_profile:
            return redirect('client_profile_delete', pk=client.client_profile.pk)
        else:
            # Handle legacy client without profile
            if request.user.role != 'top_management':
                messages.error(request, "You don't have permission to delete clients.")
                return redirect('client_profile_list')
            
            if request.method == 'POST':
                client_name = client.name
                client.delete()
                messages.success(request, f"Legacy client {client_name} has been deleted.")
                return redirect('client_profile_list')
            
            return render(request, 'base/client_confirm_delete.html', {'client': client})
    except ImportError:
        messages.error(request, "Legacy client system is not available.")
        return redirect('client_profile_list')

# Task Views with Hierarchy
@login_required
def task_list(request):
    user = request.user
    tasks = get_user_accessible_data(user, Task, 'assigned_to')
    
    # Add filtering options
    status_filter = request.GET.get('status')
    if status_filter == 'completed':
        tasks = tasks.filter(completed=True)
    elif status_filter == 'pending':
        tasks = tasks.filter(completed=False)
    elif status_filter == 'overdue':
        tasks = tasks.filter(completed=False, due_date__lt=timezone.now())
    
    # Add search functionality
    search_query = request.GET.get('search')
    if search_query:
        tasks = tasks.filter(
            Q(title__icontains=search_query) | 
            Q(description__icontains=search_query)
        )

    context = {
        'tasks': tasks.order_by('-created_at'),
        'current_status': status_filter,
        'search_query': search_query,
    }
    
    return render(request, 'base/tasks.html', context)

@login_required
def task_create(request):
    # Only RM Heads and above can assign tasks to others
    if not request.user.role in ['rm_head', 'business_head', 'top_management']:
        messages.error(request, "You don't have permission to create tasks for others.")
        return redirect('task_list')
        
    if request.method == 'POST':
        form = TaskForm(request.POST)
        if form.is_valid():
            task = form.save(commit=False)
            task.assigned_by = request.user
            task.save()
            messages.success(request, "Task created successfully.")
            return redirect('task_list')
    else:
        form = TaskForm()
        
        # Limit assignee choices based on user's role and hierarchy
        if request.user.role == 'rm_head':
            accessible_users = request.user.get_accessible_users()
            form.fields['assigned_to'].queryset = User.objects.filter(
                id__in=[u.id for u in accessible_users]
            )
        elif request.user.role in ['business_head', 'top_management']:
            # Can assign to anyone below them in hierarchy
            form.fields['assigned_to'].queryset = User.objects.exclude(role='top_management')
    
    return render(request, 'base/task_form.html', {'form': form, 'action': 'Create'})

@login_required
def task_update(request, pk):
    task = get_object_or_404(Task, pk=pk)
    
    # Check permissions - can edit if assigned to them or they can manage the assignee
    if not (task.assigned_to == request.user or request.user.can_access_user_data(task.assigned_to)):
        raise PermissionDenied("You don't have permission to edit this task.")
    
    if request.method == 'POST':
        form = TaskForm(request.POST, instance=task)
        if form.is_valid():
            form.save()
            messages.success(request, "Task updated successfully.")
            return redirect('task_list')
    else:
        form = TaskForm(instance=task)
        
        # Limit assignee choices based on user's role
        if request.user.role == 'rm_head':
            accessible_users = request.user.get_accessible_users()
            form.fields['assigned_to'].queryset = User.objects.filter(
                id__in=[u.id for u in accessible_users]
            )
        elif request.user.role == 'rm':
            # RMs can only see tasks assigned to them, so disable changing assignee
            form.fields['assigned_to'].widget.attrs['readonly'] = True
    
    return render(request, 'base/task_form.html', {'form': form, 'action': 'Update', 'task': task})

@login_required
def task_delete(request, pk):
    task = get_object_or_404(Task, pk=pk)
    
    # Check permissions
    if not (task.assigned_to == request.user or request.user.can_access_user_data(task.assigned_to)):
        raise PermissionDenied("You don't have permission to delete this task.")
    
    if request.method == 'POST':
        task.delete()
        messages.success(request, "Task deleted successfully.")
        return redirect('task_list')
    
    return render(request, 'base/task_confirm_delete.html', {'task': task})

@login_required
def task_toggle_complete(request, pk):
    """AJAX endpoint to toggle task completion"""
    if request.method == 'POST':
        task = get_object_or_404(Task, pk=pk)
        
        # Check permissions
        if not (task.assigned_to == request.user or request.user.can_access_user_data(task.assigned_to)):
            return JsonResponse({'error': 'Permission denied'}, status=403)
        
        task.completed = not task.completed
        if task.completed:
            task.completed_at = timezone.now()
        else:
            task.completed_at = None
        task.save()
        
        return JsonResponse({
            'success': True,
            'completed': task.completed,
            'completed_at': task.completed_at.isoformat() if task.completed_at else None
        })
    
    return JsonResponse({'error': 'Invalid request'}, status=400)

# Service Request Views with Hierarchy
@login_required
def service_request_list(request):
    user = request.user
    
    if user.role in ['top_management', 'business_head']:
        service_requests = ServiceRequest.objects.all()
    elif user.role == 'rm_head':
        accessible_users = user.get_accessible_users()
        service_requests = ServiceRequest.objects.filter(
            Q(raised_by__in=accessible_users) | 
            Q(client__user__in=accessible_users) |
            Q(assigned_to__in=accessible_users)
        ).distinct()
    else:  # RM
        service_requests = ServiceRequest.objects.filter(
            Q(raised_by=user) | 
            Q(client__user=user) |
            Q(assigned_to=user)
        ).distinct()
    
    # Add filtering options
    status_filter = request.GET.get('status')
    if status_filter:
        service_requests = service_requests.filter(status=status_filter)
    
    # Add search functionality
    search_query = request.GET.get('search')
    if search_query:
        service_requests = service_requests.filter(
            Q(description__icontains=search_query) |
            Q(client__name__icontains=search_query)
        )

    context = {
        'service_requests': service_requests.order_by('-created_at'),
        'status_choices': ServiceRequest.STATUS_CHOICES,
        'current_status': status_filter,
        'search_query': search_query,
    }
    
    return render(request, 'base/service_requests.html', context)

@login_required
def service_request_create(request):
    # Debug: Print user role and client count
    print(f"User: {request.user.username}, Role: {request.user.role}")
    print(f"Total clients in DB: {Client.objects.count()}")
    
    if request.method == 'POST':
        form = ServiceRequestForm(request.POST, current_user=request.user)
        if form.is_valid():
            service_request = form.save(commit=False)
            service_request.raised_by = request.user
            service_request.save()
            messages.success(request, "Service request created successfully.")
            return redirect('service_request_list')
    else:
        form = ServiceRequestForm(current_user=request.user)
        
        # Debug: Print client queryset count after form initialization
        print(f"Client queryset count: {form.fields['client'].queryset.count()}")
    
    return render(request, 'base/service_request_form.html', {'form': form, 'action': 'Create'})

@login_required
def service_request_update(request, pk):
    service_request = get_object_or_404(ServiceRequest, pk=pk)
    
    # Check permissions
    accessible_users = request.user.get_accessible_users()
    if not (service_request.raised_by in accessible_users or 
            service_request.client.user in accessible_users or
            service_request.assigned_to in accessible_users):
        raise PermissionDenied("You don't have permission to edit this service request.")
    
    if request.method == 'POST':
        form = ServiceRequestForm(request.POST, instance=service_request)
        if form.is_valid():
            updated_request = form.save()
            if updated_request.status in ['resolved', 'closed'] and not updated_request.resolved_at:
                updated_request.resolved_at = timezone.now()
                updated_request.save()
            messages.success(request, "Service request updated successfully.")
            return redirect('service_request_list')
    else:
        form = ServiceRequestForm(instance=service_request)
        
        # Limit client choices based on user's access
        if request.user.role == 'rm':
            form.fields['client'].queryset = Client.objects.filter(user=request.user)
        elif request.user.role == 'rm_head':
            accessible_users = request.user.get_accessible_users()
            form.fields['client'].queryset = Client.objects.filter(user__in=accessible_users)
    
    return render(request, 'base/service_request_form.html', {
        'form': form, 
        'action': 'Update', 
        'service_request': service_request
    })

@login_required
def service_request_delete(request, pk):
    service_request = get_object_or_404(ServiceRequest, pk=pk)
    
    # Check permissions
    accessible_users = request.user.get_accessible_users()
    if not (service_request.raised_by in accessible_users or 
            service_request.client.user in accessible_users):
        raise PermissionDenied("You don't have permission to delete this service request.")
    
    if request.method == 'POST':
        service_request.delete()
        messages.success(request, "Service request deleted successfully.")
        return redirect('service_request_list')
    
    return render(request, 'base/service_request_confirm_delete.html', {'service_request': service_request})

# Investment Plan Review Views with Hierarchy
@login_required
def investment_plan_review_list(request):
    user = request.user
    
    if user.role in ['top_management', 'business_head']:
        reviews = InvestmentPlanReview.objects.all()
    elif user.role == 'rm_head':
        accessible_users = user.get_accessible_users()
        reviews = InvestmentPlanReview.objects.filter(client__user__in=accessible_users)
    else:  # RM
        reviews = InvestmentPlanReview.objects.filter(client__user=user)

    # Add search functionality
    search_query = request.GET.get('search')
    if search_query:
        reviews = reviews.filter(
            Q(goal__icontains=search_query) |
            Q(client__name__icontains=search_query)
        )

    context = {
        'reviews': reviews.order_by('-created_at'),
        'search_query': search_query,
    }
    
    return render(request, 'base/investment_plans.html', context)

@login_required
def investment_plan_review_create(request):
    if request.user.role not in ['rm', 'rm_head']:
        messages.error(request, "You do not have permission to add investment plans.")
        return redirect('investment_plan_review_list')

    if request.method == 'POST':
        form = InvestmentPlanReviewForm(request.POST, user=request.user)
        if form.is_valid():
            review = form.save(commit=False)
            review.created_by = request.user
            review.save()
            messages.success(request, "Investment plan created successfully.")
            return redirect('investment_plan_review_list')
    else:
        form = InvestmentPlanReviewForm(user=request.user)

    return render(request, 'base/investment_plan_form.html', {'form': form, 'action': 'Create'})

@login_required
def investment_plan_review_update(request, pk):
    user = request.user
    review = get_object_or_404(InvestmentPlanReview, pk=pk)

    # Check permissions based on hierarchy
    if user.role == 'rm' and review.client.user != user:
        messages.error(request, "You cannot edit this investment plan.")
        return redirect('investment_plan_review_list')
    elif user.role == 'rm_head':
        accessible_users = user.get_accessible_users()
        if review.client.user not in accessible_users:
            messages.error(request, "You cannot edit this investment plan.")
            return redirect('investment_plan_review_list')
    elif user.role not in ['rm', 'rm_head', 'business_head', 'top_management']:
        messages.error(request, "You do not have permission to edit investment plans.")
        return redirect('investment_plan_review_list')

    if request.method == 'POST':
        form = InvestmentPlanReviewForm(request.POST, instance=review, user=user)
        if form.is_valid():
            form.save()
            messages.success(request, "Investment plan updated successfully.")
            return redirect('investment_plan_review_list')
    else:
        form = InvestmentPlanReviewForm(instance=review, user=user)

    return render(request, 'base/investment_plan_form.html', {
        'form': form, 
        'action': 'Update', 
        'review': review
    })

@login_required
def investment_plan_review_delete(request, pk):
    user = request.user
    review = get_object_or_404(InvestmentPlanReview, pk=pk)

    # Check permissions based on hierarchy
    if user.role == 'rm' and review.client.user != user:
        messages.error(request, "You cannot delete this investment plan.")
        return redirect('investment_plan_review_list')
    elif user.role == 'rm_head':
        accessible_users = user.get_accessible_users()
        if review.client.user not in accessible_users:
            messages.error(request, "You cannot delete this investment plan.")
            return redirect('investment_plan_review_list')
    elif user.role not in ['rm', 'rm_head', 'business_head', 'top_management']:
        messages.error(request, "You do not have permission to delete investment plans.")
        return redirect('investment_plan_review_list')

    if request.method == 'POST':
        review.delete()
        messages.success(request, "Investment plan deleted successfully.")
        return redirect('investment_plan_review_list')
    
    return render(request, 'base/investment_plan_confirm_delete.html', {'review': review})

# Team Management Views (for RM Heads and above)
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from .models import Team, User
from .forms import TeamForm, UserEditForm

@login_required
@user_passes_test(lambda u: u.role in ['rm_head', 'business_head', 'top_management'])
def team_management(request):
    user = request.user
    
    if user.role == 'top_management':
        teams = Team.objects.all()
        all_users = User.objects.all()
    elif user.role == 'business_head':
        teams = Team.objects.all()
        all_users = User.objects.all()
    else:  # rm_head
        teams = user.led_teams.all()
        all_users = user.get_accessible_users()
    
    context = {
        'teams': teams,
        'all_users': all_users,
        'user_role': user.role,
    }
    return render(request, 'base/team_management.html', context)

@login_required
@user_passes_test(lambda u: u.role in ['business_head', 'top_management'])
def create_team(request):
    if request.method == 'POST':
        form = TeamForm(request.POST)
        if form.is_valid():
            team = form.save()
            messages.success(request, f"Team '{team.name}' created successfully.")
            return redirect('team_detail', team_id=team.id)
    else:
        form = TeamForm(initial={'leader': request.user})
    
    context = {
        'form': form,
        'action': 'Create',
    }
    return render(request, 'base/team_form.html', context)

@login_required
@user_passes_test(lambda u: u.role in ['rm_head', 'business_head', 'top_management'])
def team_detail(request, team_id):
    team = get_object_or_404(Team, id=team_id)
    
    # Check if user has permission to view this team
    if (request.user.role not in ['business_head', 'top_management'] and 
        request.user not in team.members.all() and 
        request.user != team.leader):
        messages.error(request, "You don't have permission to view this team.")
        return redirect('team_management')
    
    context = {
        'team': team,
        'members': team.members.all(),
    }
    return render(request, 'base/team_detail.html', context)

@login_required
def edit_team(request, team_id):
    team = get_object_or_404(Team, id=team_id)
    
    # Check permissions - business_head/top_management or team leader
    if (request.user.role not in ['business_head', 'top_management'] and 
        request.user != team.leader):
        messages.error(request, "You don't have permission to edit this team.")
        return redirect('team_management')
    
    if request.method == 'POST':
        form = TeamForm(request.POST, instance=team)
        if form.is_valid():
            form.save()
            messages.success(request, f"Team '{team.name}' updated successfully.")
            return redirect('team_detail', team_id=team.id)
    else:
        form = TeamForm(instance=team)
    
    context = {
        'form': form,
        'team': team,
        'action': 'Edit',
    }
    return render(request, 'base/team_form.html', context)

@login_required
def user_profile(request, user_id):
    user = get_object_or_404(User, id=user_id)
    
    # Check if current user has permission to view this profile
    if (request.user.role not in ['business_head', 'top_management'] and 
        request.user != user and 
        not request.user.led_teams.filter(members=user).exists()):
        messages.error(request, "You don't have permission to view this profile.")
        return redirect('team_management')
    
    context = {
        'profile_user': user,
        'teams': user.teams.all(),
    }
    return render(request, 'base/user_profile.html', context)

@login_required
@user_passes_test(lambda u: u.role in ['business_head', 'top_management'])
def edit_user(request, user_id):
    user = get_object_or_404(User, id=user_id)
    
    if request.method == 'POST':
        form = UserEditForm(request.POST, instance=user)
        if form.is_valid():
            form.save()
            messages.success(request, f"User {user.get_full_name()} updated successfully.")
            return redirect('user_profile', user_id=user.id)
    else:
        form = UserEditForm(instance=user)
    
    context = {
        'form': form,
        'profile_user': user,
    }
    return render(request, 'base/user_form.html', context)


# Analytics and Reports (role-based access)
@login_required
def analytics_dashboard(request):
    user = request.user
    context = {}
    
    if user.role in ['top_management', 'business_head']:
        # System-wide analytics
        total_aum = Client.objects.aggregate(total=Sum('aum'))['total'] or 0
        total_sip = Client.objects.aggregate(total=Sum('sip_amount'))['total'] or 0
        total_clients = Client.objects.count()
        
        # Performance metrics
        total_leads = Lead.objects.count()
        converted_leads = Lead.objects.filter(status='converted').count()
        lead_conversion_rate = (converted_leads / max(total_leads, 1)) * 100
        
        # Team performance
        team_performance = User.objects.filter(role='rm').annotate(
            client_count=Count('clients'),
            total_aum=Sum('clients__aum'),
            total_sip=Sum('clients__sip_amount')
        ).order_by('-total_aum')
        
        context.update({
            'total_aum': total_aum,
            'total_sip': total_sip,
            'total_clients': total_clients,
            'lead_conversion_rate': round(lead_conversion_rate, 2),
            'team_performance': team_performance[:10],  # Top 10 performers
        })
        
    elif user.role == 'rm_head':
        # Team analytics
        accessible_users = user.get_accessible_users()
        team_clients = Client.objects.filter(user__in=accessible_users)
        
        team_aum = team_clients.aggregate(total=Sum('aum'))['total'] or 0
        team_sip = team_clients.aggregate(total=Sum('sip_amount'))['total'] or 0
        
        # Individual team member performance
        team_performance = accessible_users.filter(role='rm').annotate(
            client_count=Count('clients'),
            total_aum=Sum('clients__aum'),
            total_sip=Sum('clients__sip_amount')
        ).order_by('-total_aum')
        
        context.update({
            'team_aum': team_aum,
            'team_sip': team_sip,
            'team_clients_count': team_clients.count(),
            'team_performance': team_performance,
        })
        
    else:  # RM
        # Personal analytics
        my_clients = Client.objects.filter(user=user)
        my_aum = my_clients.aggregate(total=Sum('aum'))['total'] or 0
        my_sip = my_clients.aggregate(total=Sum('sip_amount'))['total'] or 0
        
        # Monthly performance
        from django.utils import timezone
        from datetime import timedelta
        
        last_30_days = timezone.now() - timedelta(days=30)
        recent_clients = my_clients.filter(created_at__gte=last_30_days).count()
        
        context.update({
            'my_aum': my_aum,
            'my_sip': my_sip,
            'my_clients_count': my_clients.count(),
            'recent_clients': recent_clients,
        })
    
    template_name = f'base/analytics_{user.role}.html'
    return render(request, template_name, context)