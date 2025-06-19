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
from django.db import transaction
from .models import User, Lead, Client, Task, ServiceRequest, BusinessTracker, InvestmentPlanReview, Team,ProductDiscussion
from .forms import LeadForm, ClientForm, TaskForm, ServiceRequestForm, InvestmentPlanReviewForm
from .models import Lead, ProductDiscussion, LeadInteraction, LeadStatusChange

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
                'performance_score': getattr(member, 'performance_score', 0)  # Safe getattr with default
            })

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
            'team_members_data': team_members_data,  # Add this to context
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
@login_required
def client_list(request):
    user = request.user
    
    # Get clients based on user role
    if user.role in ['top_management', 'business_head']:
        clients = Client.objects.all()
    elif user.role == 'rm_head':
        accessible_users = user.get_accessible_users()
        clients = Client.objects.filter(
            Q(user__in=accessible_users) | 
            Q(created_by=user))
    else:  # RM
        clients = Client.objects.filter(user=user)
    
    # Search functionality
    search_query = request.GET.get('search')
    if search_query:
        clients = clients.filter(
            Q(name__icontains=search_query) | 
            Q(contact_info__icontains=search_query)
        )

    from django.db.models import Sum, Count, IntegerField
    from django.db.models.functions import Coalesce

    stats = clients.aggregate(
        total_aum=Coalesce(Sum('aum', output_field=IntegerField()), 0),
        total_sip=Coalesce(Sum('sip_amount', output_field=IntegerField()), 0),
        total_demat=Coalesce(Sum('demat_count', output_field=IntegerField()), 0),
        client_count=Count('id')
    )

    context = {
        'clients': clients.order_by('-created_at'),
        'search_query': search_query,
        'clients_count': stats['client_count'],
        'total_aum': stats['total_aum'],
        'total_sip': stats['total_sip'],
        'total_demat': stats['total_demat'],
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