from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth import authenticate, login, logout
from django.urls import reverse
from .models import User, Lead, Client, Task, ServiceRequest, BusinessTracker, InvestmentPlanReview
from .forms import LeadForm, ClientForm, TaskForm, ServiceRequestForm, InvestmentPlanReviewForm
from django.utils import timezone
from django.db.models import Sum, Count, Q

# Helper functions for role checks
def is_top_management(user):
    return user.role == 'top_management'

def is_business_head(user):
    return user.role == 'business_head'

def is_rm_head(user):
    return user.role == 'rm_head'

def is_rm(user):
    return user.role == 'rm'

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


# Dashboard View (role-based)
@login_required
def dashboard(request):
    user = request.user
    context = {}

    if user.role == 'top_management':
        # Aggregate KPIs
        total_aum = Client.objects.aggregate(total=Sum('aum'))['total'] or 0
        total_sip = Client.objects.aggregate(total=Sum('sip_amount'))['total'] or 0
        total_clients = Client.objects.count()
        total_leads = Lead.objects.count()
        total_tasks = Task.objects.filter(completed=False).count()

        # Team metrics (counts per role)
        rm_heads_count = User.objects.filter(role='rm_head').count()
        rms_count = User.objects.filter(role='rm').count()

        context.update({
            'total_aum': total_aum,
            'total_sip': total_sip,
            'total_clients': total_clients,
            'total_leads': total_leads,
            'total_tasks': total_tasks,
            'rm_heads_count': rm_heads_count,
            'rms_count': rms_count,
        })
        template_name = 'base/dashboard_top_management.html'

    elif user.role == 'business_head':
        # Business Heads monitor RM Heads, leads, and service performance
        rm_heads = User.objects.filter(role='rm_head')
        leads = Lead.objects.filter(assigned_to__in=User.objects.filter(role='rm'))
        open_service_requests = ServiceRequest.objects.filter(status='Open')
        context.update({
            'rm_heads': rm_heads,
            'leads': leads,
            'open_service_requests': open_service_requests,
        })
        template_name = 'base/dashboard_business_head.html'

    elif user.role == 'rm_head':
        # RM Heads manage their team leads, tasks, and service requests
        team_rms = User.objects.filter(role='rm', groups__in=user.groups.all())
        leads = Lead.objects.filter(Q(assigned_to=user) | Q(assigned_to__in=team_rms))
        tasks = Task.objects.filter(assigned_to__in=[user] + list(team_rms))
        service_requests = ServiceRequest.objects.filter(
            Q(raised_by=user) | Q(client__user__in=[user] + list(team_rms))
        )
        context.update({
            'team_rms': team_rms,
            'leads': leads,
            'tasks': tasks,
            'service_requests': service_requests,
        })
        template_name = 'base/dashboard_rm_head.html'

    else:  # Relationship Manager
        leads = Lead.objects.filter(assigned_to=user)
        clients = Client.objects.filter(user=user)
        tasks = Task.objects.filter(assigned_to=user)
        reminders = user.reminders.filter(is_done=False, remind_at__gte=timezone.now())
        service_requests = ServiceRequest.objects.filter(raised_by=user)
        context.update({
            'leads': leads,
            'clients': clients,
            'tasks': tasks,
            'reminders': reminders,
            'service_requests': service_requests,
        })
        template_name = 'base/dashboard_rm.html'

    return render(request, template_name, context)


# Lead Views

@login_required
def lead_list(request):
    user = request.user

    if user.role in ['top_management', 'business_head']:
        leads = Lead.objects.all()

    elif user.role == 'rm_head':
        # Get groups that the RM Head belongs to
        user_groups = user.groups.all()

        # Get RMs who are in any of these groups
        team_rms = User.objects.filter(role='rm', groups__in=user_groups).distinct()

        # Leads assigned to this RM Head or any RM in their team
        leads = Lead.objects.filter(Q(assigned_to=user) | Q(assigned_to__in=team_rms)).distinct()

    else:  # RM
        leads = Lead.objects.filter(assigned_to=user)

    # Debug prints (remove in production)
    print(f"User: {user.username} Role: {user.role}")
    print(f"Leads count: {leads.count()}")
    for lead in leads:
        print(f"Lead: {lead.name} Assigned To: {lead.assigned_to}")

    return render(request, 'base/leads.html', {'leads': leads})


@login_required
def lead_create(request):
    if request.method == 'POST':
        form = LeadForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('lead_list')
    else:
        form = LeadForm()
    return render(request, 'base/lead_form.html', {'form': form})


@login_required
def lead_update(request, pk):
    lead = get_object_or_404(Lead, pk=pk)
    if request.method == 'POST':
        form = LeadForm(request.POST, instance=lead)
        if form.is_valid():
            form.save()
            return redirect('lead_list')
    else:
        form = LeadForm(instance=lead)
    return render(request, 'base/lead_form.html', {'form': form})


@login_required
def lead_delete(request, pk):
    lead = get_object_or_404(Lead, pk=pk)
    if request.method == 'POST':
        lead.delete()
        return redirect('lead_list')
    return render(request, 'base/lead_confirm_delete.html', {'lead': lead})

# Client Views

@login_required
def client_list(request):
    user = request.user
    if user.role in ['top_management', 'business_head']:
        clients = Client.objects.all()
    elif user.role == 'rm_head':
        team_rms = User.objects.filter(role='rm', groups__in=user.groups.all())
        clients = Client.objects.filter(Q(user=user) | Q(user__in=team_rms))
    else:  # RM
        clients = Client.objects.filter(user=user)
    return render(request, 'base/clients.html', {'clients': clients})


@login_required
def client_create(request):
    if request.method == 'POST':
        form = ClientForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('client_list')
    else:
        form = ClientForm()
    return render(request, 'base/client_form.html', {'form': form})


@login_required
def client_update(request, pk):
    client = get_object_or_404(Client, pk=pk)
    if request.method == 'POST':
        form = ClientForm(request.POST, instance=client)
        if form.is_valid():
            form.save()
            return redirect('client_list')
    else:
        form = ClientForm(instance=client)
    return render(request, 'base/client_form.html', {'form': form})


@login_required
def client_delete(request, pk):
    client = get_object_or_404(Client, pk=pk)
    if request.method == 'POST':
        client.delete()
        return redirect('client_list')
    return render(request, 'base/client_confirm_delete.html', {'client': client})


# Task Views

@login_required
def task_list(request):
    user = request.user
    if user.role in ['top_management', 'business_head']:
        tasks = Task.objects.all()
    elif user.role == 'rm_head':
        team_rms = User.objects.filter(role='rm', groups__in=user.groups.all())
        tasks = Task.objects.filter(Q(assigned_to=user) | Q(assigned_to__in=team_rms))
    else:  # RM
        tasks = Task.objects.filter(assigned_to=user)
    return render(request, 'base/tasks.html', {'tasks': tasks})


@login_required
def task_create(request):
    if request.method == 'POST':
        form = TaskForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('task_list')
    else:
        form = TaskForm()
    return render(request, 'base/task_form.html', {'form': form})


@login_required
def task_update(request, pk):
    task = get_object_or_404(Task, pk=pk)
    if request.method == 'POST':
        form = TaskForm(request.POST, instance=task)
        if form.is_valid():
            form.save()
            return redirect('task_list')
    else:
        form = TaskForm(instance=task)
    return render(request, 'base/task_form.html', {'form': form})


@login_required
def task_delete(request, pk):
    task = get_object_or_404(Task, pk=pk)
    if request.method == 'POST':
        task.delete()
        return redirect('task_list')
    return render(request, 'base/task_confirm_delete.html', {'task': task})


# Service Request Views

@login_required
def service_request_list(request):
    user = request.user
    if user.role in ['top_management', 'business_head']:
        service_requests = ServiceRequest.objects.all()
    elif user.role == 'rm_head':
        team_rms = User.objects.filter(role='rm', groups__in=user.groups.all())
        service_requests = ServiceRequest.objects.filter(
            Q(raised_by=user) | Q(client__user__in=[user] + list(team_rms))
        )
    else:  # RM
        service_requests = ServiceRequest.objects.filter(raised_by=user)
    return render(request, 'base/service_requests.html', {'service_requests': service_requests})


@login_required
def service_request_create(request):
    if request.method == 'POST':
        form = ServiceRequestForm(request.POST)
        if form.is_valid():
            service_request = form.save(commit=False)
            service_request.raised_by = request.user
            service_request.save()
            return redirect('service_request_list')
    else:
        form = ServiceRequestForm()
    return render(request, 'base/service_request_form.html', {'form': form})


@login_required
def service_request_update(request, pk):
    service_request = get_object_or_404(ServiceRequest, pk=pk)
    if request.method == 'POST':
        form = ServiceRequestForm(request.POST, instance=service_request)
        if form.is_valid():
            form.save()
            return redirect('service_request_list')
    else:
        form = ServiceRequestForm(instance=service_request)
    return render(request, 'base/service_request_form.html', {'form': form})


@login_required
def service_request_delete(request, pk):
    service_request = get_object_or_404(ServiceRequest, pk=pk)
    if request.method == 'POST':
        service_request.delete()
        return redirect('service_request_list')
    return render(request, 'base/service_request_confirm_delete.html', {'service_request': service_request})


# Investment Plan Review Views

# views.py

from django.contrib import messages

@login_required
def investment_plan_review_list(request):
    user = request.user
    if user.role in ['top_management', 'business_head']:
        reviews = InvestmentPlanReview.objects.all()
    elif user.role == 'rm_head':
        team_rms = User.objects.filter(role='rm', groups__in=user.groups.all())
        reviews = InvestmentPlanReview.objects.filter(client__user__in=team_rms)
    else:  # RM
        reviews = InvestmentPlanReview.objects.filter(client__user=user)

    return render(request, 'base/investment_plans.html', {'reviews': reviews})


@login_required
def investment_plan_review_create(request):
    user = request.user
    if user.role not in ['rm', 'rm_head']:
        messages.error(request, "You do not have permission to add investment plans.")
        return redirect('investment_plan_review_list')

    if request.method == 'POST':
        form = InvestmentPlanReviewForm(request.POST, user=user)
        if form.is_valid():
            form.save()
            return redirect('investment_plan_review_list')
    else:
        form = InvestmentPlanReviewForm(user=user)

    return render(request, 'base/investment_plan_form.html', {'form': form})


@login_required
def investment_plan_review_update(request, pk):
    user = request.user
    review = get_object_or_404(InvestmentPlanReview, pk=pk)

    # Restrict editing to only RMs/RM Heads for their team
    if user.role == 'rm' and review.client.user != user:
        messages.error(request, "You cannot edit this investment plan.")
        return redirect('investment_plan_review_list')
    elif user.role == 'rm_head':
        team_rms = User.objects.filter(role='rm', groups__in=user.groups.all())
        if review.client.user not in team_rms:
            messages.error(request, "You cannot edit this investment plan.")
            return redirect('investment_plan_review_list')
    elif user.role not in ['rm', 'rm_head']:
        messages.error(request, "You do not have permission to edit investment plans.")
        return redirect('investment_plan_review_list')

    if request.method == 'POST':
        form = InvestmentPlanReviewForm(request.POST, instance=review, user=user)
        if form.is_valid():
            form.save()
            return redirect('investment_plan_review_list')
    else:
        form = InvestmentPlanReviewForm(instance=review, user=user)

    return render(request, 'base/investment_plan_form.html', {'form': form})


@login_required
def investment_plan_review_delete(request, pk):
    user = request.user
    review = get_object_or_404(InvestmentPlanReview, pk=pk)

    # Allow deletion only for RMs and RM Heads
    if user.role == 'rm' and review.client.user != user:
        messages.error(request, "You cannot delete this investment plan.")
        return redirect('investment_plan_review_list')
    elif user.role == 'rm_head':
        team_rms = User.objects.filter(role='rm', groups__in=user.groups.all())
        if review.client.user not in team_rms:
            messages.error(request, "You cannot delete this investment plan.")
            return redirect('investment_plan_review_list')
    elif user.role not in ['rm', 'rm_head']:
        messages.error(request, "You do not have permission to delete investment plans.")
        return redirect('investment_plan_review_list')

    if request.method == 'POST':
        review.delete()
        return redirect('investment_plan_review_list')
    return render(request, 'base/investment_plan_confirm_delete.html', {'review': review})
