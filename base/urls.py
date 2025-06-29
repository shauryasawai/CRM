# urls.py - Main URL patterns for the CRM system

from django.urls import path, include
from django.contrib import admin
from . import views

# Main URL patterns
urlpatterns = [
    # Authentication
    path('', views.user_login, name='login'),
    path('login/', views.user_login, name='login'),
    path('logout/', views.user_logout, name='logout'),
    
    # Dashboard - role-based routing
    path('dashboard/', views.dashboard, name='dashboard'),
    
    # Notes System URLs
    path('notes/', include([
        path('', views.notes_dashboard, name='notes_dashboard'),
        path('list/', views.note_list_view, name='note_list'),
        path('create/', views.note_create, name='note_create'),
        path('<int:pk>/', views.note_detail, name='note_detail'),
        path('notes/<int:pk>/toggle-complete/', views.note_toggle_complete, name='note_toggle_complete'),
        path('<int:pk>/edit/', views.note_update, name='note_update'),
        path('<int:pk>/delete/', views.note_delete, name='note_delete'),
        path('<int:pk>/toggle-complete/', views.note_toggle_complete, name='note_toggle_complete'),
        
        # Note Lists Management
        path('lists/', views.note_list_management, name='note_list_management'),
        path('lists/create/', views.note_list_create, name='note_list_create'),
        path('lists/<int:pk>/edit/', views.note_list_update, name='note_list_update'),
        path('lists/<int:pk>/delete/', views.note_list_delete, name='note_list_delete'),
        
        # AJAX endpoints
        path('api/lists/<int:list_id>/notes/', views.get_notes_by_list, name='get_notes_by_list'),
        path('api/reminders/upcoming/', views.get_upcoming_reminders, name='get_upcoming_reminders'),
    ])),
    
    # Client Profile Management
    path('client-profiles/', include([
        path('', views.client_profile_list, name='client_profile_list'),
        path('create/', views.client_profile_create, name='client_profile_create'),
        path('<int:pk>/', views.client_profile_detail, name='client_profile_detail'),
        path('<int:pk>/edit/', views.client_profile_update, name='client_profile_update'),
        path('<int:pk>/mute/', views.client_profile_mute, name='client_profile_mute'),
        path('<int:pk>/delete/', views.client_profile_delete, name='client_profile_delete'),
        path('<int:profile_id>/convert-to-client/', views.convert_to_client, name='convert_to_client'),
        
        # Modification requests
        path('modification-requests/', views.modification_requests, name='modification_requests'),
        path('modifications/<int:pk>/approve/', views.approve_modification, name='approve_modification'),
    ])),
    
    # Legacy client URLs (for backward compatibility)
    path('clients/', include([
        path('', views.client_list, name='client_list'),
        path('create/', views.client_create, name='client_create'),
        path('<int:pk>/edit/', views.client_update, name='client_update'),
        path('<int:pk>/delete/', views.client_delete, name='client_delete'),
    ])),
    
    # Lead Management
    path('leads/', include([
        path('', views.lead_list, name='lead_list'),
        path('create/', views.lead_create, name='lead_create'),
        path('<int:pk>/', views.lead_detail, name='lead_detail'),
        path('<int:pk>/edit/', views.lead_update, name='lead_update'),
        path('<int:pk>/delete/', views.lead_delete, name='lead_delete'),
        
        # Lead interactions and actions
        path('<int:pk>/add-interaction/', views.add_interaction, name='add_interaction'),
        path('<int:pk>/add-product-discussion/', views.add_product_discussion, name='add_product_discussion'),
        path('<int:pk>/change-status/', views.change_lead_status, name='change_lead_status'),
        path('<int:pk>/request-conversion/', views.request_conversion, name='request_conversion'),
        path('<int:pk>/convert/', views.convert_lead, name='convert_lead'),
        path('<int:pk>/reassign/', views.reassign_lead, name='reassign_lead'),
        path('<int:pk>/approve-conversion/', views.approve_conversion, name='approve_conversion'),
        path('<int:pk>/reject-conversion/', views.reject_conversion, name='reject_conversion'),
        path('<int:pk>/request-reassignment/', views.request_reassignment, name='request_reassignment'),
        path('<int:pk>/approve-reassignment/', views.approve_reassignment, name='approve_reassignment'),
        
        # Interaction management
        path('interactions/<int:interaction_id>/delete/', views.delete_interaction, name='delete_interaction'),
        
        # AJAX endpoints
        path('api/reference-clients/', views.get_reference_clients, name='get_reference_clients'),
        path('api/accessible-users/', views.get_accessible_users, name='get_accessible_users'),
    ])),
    
    # Task Management
    path('tasks/', include([
        path('', views.task_list, name='task_list'),
        path('create/', views.task_create, name='task_create'),
        path('<int:pk>/update/', views.task_update, name='task_update'),
        path('<int:pk>/delete/', views.task_delete, name='task_delete'),
        path('<int:pk>/toggle-complete/', views.task_toggle_complete, name='task_toggle_complete'),
        path('<int:pk>/mark-done/', views.mark_task_done, name='mark_task_done'),
        path('<int:pk>/reopen/', views.reopen_task, name='reopen_task'),
        path('bulk-mark-done/', views.bulk_mark_tasks_done, name='bulk_mark_tasks_done'),
        path('stats/', views.task_stats, name='task_stats'),

    ])),
    
    # Service Request Management
    path('service-requests/', include([
        path('', views.service_request_list, name='service_request_list'),
        path('create/', views.service_request_create, name='service_request_create'),
        path('<int:pk>/edit/', views.service_request_update, name='service_request_update'),
        path('<int:pk>/delete/', views.service_request_delete, name='service_request_delete'),
    ])),
    
    # Investment Plan Reviews
    path('investment-plans/', include([
        path('', views.investment_plan_review_list, name='investment_plan_review_list'),
        path('create/', views.investment_plan_review_create, name='investment_plan_review_create'),
        path('<int:pk>/edit/', views.investment_plan_review_update, name='investment_plan_review_update'),
        path('<int:pk>/delete/', views.investment_plan_review_delete, name='investment_plan_review_delete'),
    ])),
    
    # Team Management
    path('teams/', include([
        path('', views.team_management, name='team_management'),
        path('create/', views.create_team, name='create_team'),
        path('<int:team_id>/', views.team_detail, name='team_detail'),
        path('<int:team_id>/edit/', views.edit_team, name='edit_team'),
        
        # User management within teams
        path('users/<int:user_id>/', views.user_profile, name='user_profile'),
        path('users/<int:user_id>/edit/', views.edit_user, name='edit_user'),
    ])),
    
    # Operations Team Lead specific views
    path('ops/', include([
        path('team-performance/', views.ops_team_performance, name='ops_team_performance'),
        path('client-profiles/', views.ops_client_profiles, name='ops_client_profiles'),
        path('task-assignment/', views.ops_task_assignment, name='ops_task_assignment'),
        path('my-tasks/', views.ops_my_tasks, name='ops_my_tasks'),
        path('my-clients/', views.ops_my_clients, name='ops_my_clients'),
        path('service-requests/', views.ops_service_requests, name='ops_service_requests'),
    ])),

    # Business Head Operations specific patterns
    path('bh-ops/', include([
        path('overview/', views.bh_ops_overview, name='bh_ops_overview'),
        path('team-management/', views.bh_ops_team_management, name='bh_ops_team_management'),
        path('performance-metrics/', views.bh_ops_performance_metrics, name='bh_ops_performance_metrics'),
        path('compliance/', views.bh_ops_compliance, name='bh_ops_compliance'),
    ])),

    # API endpoints for AJAX calls
    path('api/', include([
        path('dashboard-stats/', views.get_dashboard_stats, name='get_dashboard_stats'),
        path('user-hierarchy/', views.get_user_hierarchy, name='get_user_hierarchy'),
        path('team-performance/', views.get_team_performance, name='get_team_performance'),
        path('notes/quick-create/', views.quick_create_note, name='quick_create_note'),
        path('tasks/quick-assign/', views.quick_assign_task, name='quick_assign_task'),
    ])),

    # Quick access patterns for common actions
    path('quick/', include([
        path('note/', views.quick_note_create, name='quick_note_create'),
        path('task/', views.quick_task_create, name='quick_task_create'),
        path('client-search/', views.quick_client_search, name='quick_client_search'),
        path('lead-search/', views.quick_lead_search, name='quick_lead_search'),
    ])),
    
    # Analytics and Reports
    path('analytics/', views.analytics_dashboard, name='analytics_dashboard'),
    
    # Error handling URLs
    path('403/', views.permission_denied, name='permission_denied'),
    path('404/', views.not_found, name='not_found'),
    path('500/', views.server_error, name='server_error'),
]

