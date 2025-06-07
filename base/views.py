from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth import authenticate, login, logout
from django.urls import reverse
from django.contrib import messages
from django.utils import timezone
from django.db.models import Sum, Count, Q, Avg
from django.http import JsonResponse, HttpResponseForbidden
from django.core.exceptions import PermissionDenied
from django.db.models import Sum, Avg, F, Q
from django.db.models.functions import Extract
from django.utils import timezone

from .models import User, Lead, Client, Task, ServiceRequest, BusinessTracker, InvestmentPlanReview, Team
from .forms import LeadForm, ClientForm, TaskForm, ServiceRequestForm, InvestmentPlanReviewForm

# Helper functions for role checks
def is_top_management(user):
    return user.role == 'top_management'

def is_business_head(user):
    return user.role == 'business_head'

def is_rm_head(user):
    return user.role == 'rm_head'

def is_rm(user):
    return user.role == 'rm'

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

# Dashboard View (role-based with hierarchy)
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
        rm_heads_count = User.objects.filter(role='rm_head').count()
        rms_count = User.objects.filter(role='rm').count()

        # Recent activities
        recent_leads = Lead.objects.order_by('-created_at')[:5]
        recent_service_requests = ServiceRequest.objects.order_by('-created_at')[:5]

        context.update({
            'total_aum': total_aum,
            'total_sip': total_sip,
            'total_clients': total_clients,
            'total_leads': total_leads,
            'total_tasks': total_tasks,
            'open_service_requests': open_service_requests,
            'business_heads_count': business_heads_count,
            'rm_heads_count': rm_heads_count,
            'rms_count': rms_count,
            'recent_leads': recent_leads,
            'recent_service_requests': recent_service_requests,
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
        
        # Calculate average response time properly
        resolved_requests = ServiceRequest.objects.filter(
            status__in=['resolved', 'closed'],
            resolved_at__isnull=False
        ).annotate(
            response_time=F('resolved_at') - F('created_at')
        )
        
        if resolved_requests.exists():
            # Calculate average response time in days
            total_response_time = resolved_requests.aggregate(
                avg_seconds=Avg(
                    Extract('epoch', F('resolved_at')) - Extract('epoch', F('created_at'))
                )
            )['avg_seconds']
            avg_response_time_days = total_response_time / (24 * 60 * 60) if total_response_time else 0
        else:
            avg_response_time_days = 0

        context.update({
            'rm_heads': rm_heads,
            'all_rms': all_rms,
            'total_leads': total_leads,
            'converted_leads': converted_leads,
            'lead_conversion_rate': round(lead_conversion_rate, 2),
            'open_service_requests': open_service_requests,
            'avg_response_time': round(avg_response_time_days, 2),
        })
        template_name = 'base/dashboard_business_head.html'

    elif user.role == 'rm_head':
        # Manage team and monitor performance
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
        })
        template_name = 'base/dashboard_rm_head.html'

    else:  # Relationship Manager
        # Personal dashboard
        leads = Lead.objects.filter(assigned_to=user)
        clients = Client.objects.filter(user=user)
        tasks = Task.objects.filter(assigned_to=user)
        reminders = user.reminders.filter(is_done=False, remind_at__gte=timezone.now())
        service_requests = ServiceRequest.objects.filter(raised_by=user)
        
        # Personal metrics
        pending_tasks = tasks.filter(completed=False).count()
        overdue_tasks = tasks.filter(completed=False, due_date__lt=timezone.now()).count()
        my_aum = clients.aggregate(total=Sum('aum'))['total'] or 0
        my_sip = clients.aggregate(total=Sum('sip_amount'))['total'] or 0
        
        # Recent activities
        recent_clients = clients.order_by('-created_at')[:3]
        upcoming_reminders = reminders.order_by('remind_at')[:5]

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
            'upcoming_reminders': upcoming_reminders,
            'leads_count': leads.count(),
            'clients_count': clients.count(),
        })
        template_name = 'base/dashboard_rm.html'

    return render(request, template_name, context)

# Lead Views with Hierarchy
@login_required
def lead_list(request):
    user = request.user
    leads = get_user_accessible_data(user, Lead, 'assigned_to')
    
    # Add filtering options
    status_filter = request.GET.get('status')
    if status_filter:
        leads = leads.filter(status=status_filter)
    
    # Add search functionality
    search_query = request.GET.get('search')
    if search_query:
        leads = leads.filter(
            Q(name__icontains=search_query) | 
            Q(contact_info__icontains=search_query) |
            Q(source__icontains=search_query)
        )

    context = {
        'leads': leads.order_by('-created_at'),
        'status_choices': Lead.STATUS_CHOICES,
        'current_status': status_filter,
        'search_query': search_query,
    }
    
    return render(request, 'base/leads.html', context)

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
            lead.save()
            messages.success(request, "Lead created successfully.")
            return redirect('lead_list')
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
            form.save()
            messages.success(request, "Lead updated successfully.")
            return redirect('lead_list')
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

# Client Views with Hierarchy
@login_required
def client_list(request):
    user = request.user
    clients = get_user_accessible_data(user, Client, 'user')
    
    # Add search functionality
    search_query = request.GET.get('search')
    if search_query:
        clients = clients.filter(
            Q(name__icontains=search_query) | 
            Q(contact_info__icontains=search_query)
        )

    context = {
        'clients': clients.order_by('-created_at'),
        'search_query': search_query,
    }
    
    return render(request, 'base/clients.html', context)

@login_required
def client_create(request):
    if not request.user.role in ['rm', 'rm_head']:
        messages.error(request, "You don't have permission to create clients.")
        return redirect('client_list')
        
    if request.method == 'POST':
        form = ClientForm(request.POST)
        if form.is_valid():
            client = form.save()
            messages.success(request, "Client created successfully.")
            return redirect('client_list')
    else:
        form = ClientForm()
        
        # Limit user choices for RM Head
        if request.user.role == 'rm_head':
            accessible_users = request.user.get_accessible_users()
            form.fields['user'].queryset = User.objects.filter(
                id__in=[u.id for u in accessible_users],
                role='rm'
            )
        elif request.user.role == 'rm':
            # RMs can only assign to themselves
            form.fields['user'].queryset = User.objects.filter(id=request.user.id)
            form.fields['user'].initial = request.user
    
    return render(request, 'base/client_form.html', {'form': form, 'action': 'Create'})

@login_required
def client_update(request, pk):
    client = get_object_or_404(Client, pk=pk)
    
    # Check permissions
    if not request.user.can_access_user_data(client.user):
        raise PermissionDenied("You don't have permission to edit this client.")
    
    if request.method == 'POST':
        form = ClientForm(request.POST, instance=client)
        if form.is_valid():
            form.save()
            messages.success(request, "Client updated successfully.")
            return redirect('client_list')
    else:
        form = ClientForm(instance=client)
        
        # Limit user choices based on role
        if request.user.role == 'rm_head':
            accessible_users = request.user.get_accessible_users()
            form.fields['user'].queryset = User.objects.filter(
                id__in=[u.id for u in accessible_users],
                role='rm'
            )
        elif request.user.role == 'rm':
            form.fields['user'].queryset = User.objects.filter(id=request.user.id)
    
    return render(request, 'base/client_form.html', {'form': form, 'action': 'Update', 'client': client})

@login_required
def client_delete(request, pk):
    client = get_object_or_404(Client, pk=pk)
    
    # Check permissions
    if not request.user.can_access_user_data(client.user):
        raise PermissionDenied("You don't have permission to delete this client.")
    
    if request.method == 'POST':
        client.delete()
        messages.success(request, "Client deleted successfully.")
        return redirect('client_list')
    
    return render(request, 'base/client_confirm_delete.html', {'client': client})

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
    if request.method == 'POST':
        form = ServiceRequestForm(request.POST)
        if form.is_valid():
            service_request = form.save(commit=False)
            service_request.raised_by = request.user
            service_request.save()
            messages.success(request, "Service request created successfully.")
            return redirect('service_request_list')
    else:
        form = ServiceRequestForm()
        
        # Limit client choices based on user's access
        if request.user.role == 'rm':
            form.fields['client'].queryset = Client.objects.filter(user=request.user)
        elif request.user.role == 'rm_head':
            accessible_users = request.user.get_accessible_users()
            form.fields['client'].queryset = Client.objects.filter(user__in=accessible_users)
    
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
@login_required
@user_passes_test(lambda u: u.role in ['rm_head', 'business_head', 'top_management'])
def team_management(request):
    user = request.user
    
    if user.role == 'top_management':
        # Can see all teams and users
        teams = Team.objects.all()
        all_users = User.objects.all()
    elif user.role == 'business_head':
        # Can see all teams and users
        teams = Team.objects.all()
        all_users = User.objects.all()
    else:  # rm_head
        # Can see their own teams
        teams = user.led_teams.all()
        all_users = user.get_accessible_users()
    
    context = {
        'teams': teams,
        'all_users': all_users,
        'user_role': user.role,
    }
    
    return render(request, 'base/team_management.html', context)

# Analytics and Reports (role-based access)
@login_required
def analytics_dashboard(request):
    user = request.user
    context = {}
    
    if user.role in ['top_management', 'business_head']:
        # System-wide analytics
        total_aum = Client.objects.aggregate(Sum('aum'))['total'] or 0
        total_sip = Client.objects.aggregate(Sum('sip_amount'))['total'] or 0
        total_clients = Client.objects.count()
        
        # Performance metrics
        lead_conversion_rate = Lead.objects.filter(status='converted').count() / max(Lead.objects.count(), 1) * 100
        
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
        
        team_aum = team_clients.aggregate(Sum('aum'))['total'] or 0
        team_sip = team_clients.aggregate(Sum('sip_amount'))['total'] or 0
        
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
        my_aum = my_clients.aggregate(Sum('aum'))['total'] or 0
        my_sip = my_clients.aggregate(Sum('sip_amount'))['total'] or 0
        
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