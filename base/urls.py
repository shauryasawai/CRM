# urls.py - Enhanced with email integration for execution plans

from django.urls import path, include
from . import views

urlpatterns = [
    # Authentication
    path('', views.user_login, name='login'),
    path('logout/', views.user_logout, name='logout'),
    
    # Dashboard
    path('dashboard/', views.dashboard, name='dashboard'),
    
    # Portfolio Management
    path('portfolio/', include([
        # Dashboard and main views
        path('', views.portfolio_dashboard, name='portfolio_dashboard'),
        path('list/', views.portfolio_list, name='portfolio_list'),
        path('analytics/', views.portfolio_analytics, name='portfolio_analytics'),
        path('unmapped/', views.unmapped_portfolios, name='unmapped_portfolios'),
        
        # Upload management
        path('upload/', views.upload_portfolio, name='upload_portfolio'),
        path('upload/<str:upload_id>/', views.upload_detail, name='upload_detail'),
        
        # Portfolio details
        path('detail/<int:portfolio_id>/', views.portfolio_detail, name='portfolio_detail'),
        
        # AJAX endpoints
        path('api/map-portfolio/<int:portfolio_id>/', views.map_portfolio_to_client, name='map_portfolio_to_client'),
        
        # Management actions
        path('bulk-map/', views.bulk_map_portfolios, name='bulk_map_portfolios'),
        path('export-csv/', views.export_portfolios_csv, name='export_portfolios_csv'),
    ])),
    
    # Notes System
    path('notes/', include([
        path('', views.notes_dashboard, name='notes_dashboard'),
        path('list/', views.note_list_view, name='note_list'),
        path('create/', views.note_create, name='note_create'),
        path('<int:pk>/', views.note_detail, name='note_detail'),
        path('<int:pk>/edit/', views.note_update, name='note_update'),
        path('<int:pk>/delete/', views.note_delete, name='note_delete'),
        path('<int:pk>/toggle-complete/', views.note_toggle_complete, name='note_toggle_complete'),
        
        # Note Lists
        path('lists/', views.note_list_management, name='note_list_management'),
        path('lists/create/', views.note_list_create, name='note_list_create'),
        path('lists/<int:pk>/edit/', views.note_list_update, name='note_list_update'),
        path('lists/<int:pk>/delete/', views.note_list_delete, name='note_list_delete'),
        
        # API endpoints
        path('api/lists/<int:list_id>/notes/', views.get_notes_by_list, name='get_notes_by_list'),
        path('api/reminders/upcoming/', views.get_upcoming_reminders, name='get_upcoming_reminders'),
    ])),
    
    # Client Profiles
    path('client-profiles/', include([
        path('', views.client_profile_list, name='client_profile_list'),
        path('create/', views.client_profile_create, name='client_profile_create'),
        path('<int:pk>/', views.client_profile_detail, name='client_profile_detail'),
        path('<int:pk>/edit/', views.client_profile_update, name='client_profile_update'),
        path('<int:pk>/mute/', views.client_profile_mute, name='client_profile_mute'),
        path('<int:pk>/delete/', views.client_profile_delete, name='client_profile_delete'),
        path('<int:profile_id>/convert-to-client/', views.convert_to_client, name='convert_to_client'),
        
        # Client Interactions
        path('<int:profile_id>/interactions/', views.client_interaction_list, name='client_interaction_list'),
        path('<int:profile_id>/interactions/create/', views.client_interaction_create, name='client_interaction_create'),
        path('<int:profile_id>/interactions/<int:interaction_id>/', views.client_interaction_detail, name='client_interaction_detail'),
        path('<int:profile_id>/interactions/<int:interaction_id>/edit/', views.client_interaction_update, name='client_interaction_update'),
        path('<int:profile_id>/interactions/<int:interaction_id>/delete/', views.client_interaction_delete, name='client_interaction_delete'),
        
        # Modification requests
        path('modification-requests/', views.modification_requests, name='modification_requests'),
        path('modifications/<int:pk>/approve/', views.approve_modification, name='approve_modification'),
    ])),

    # Legacy clients (for backward compatibility)
    path('clients/', include([
        path('', views.client_list, name='client_list'),
        path('create/', views.client_create, name='client_create'),
        path('<int:pk>/edit/', views.client_update, name='client_update'),
        path('<int:pk>/delete/', views.client_delete, name='client_delete'),
    ])),
    
    # Leads
    path('leads/', include([
        path('', views.lead_list, name='lead_list'),
        path('create/', views.lead_create, name='lead_create'),
        path('<int:pk>/', views.lead_detail, name='lead_detail'),
        path('<int:pk>/edit/', views.lead_update, name='lead_update'),
        path('<int:pk>/delete/', views.lead_delete, name='lead_delete'),
        
        # Lead actions
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
        
        path('interactions/<int:interaction_id>/delete/', views.delete_interaction, name='delete_interaction'),
        
        # API endpoints
        path('api/reference-clients/', views.get_reference_clients, name='get_reference_clients'),
        path('api/accessible-users/', views.get_accessible_users, name='get_accessible_users'),
    ])),
    
    # Tasks
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
    
    # Service Requests
    path('service-requests/', include([
        path('', views.service_request_list, name='service_request_list'),
        path('create/', views.service_request_create, name='service_request_create'),
        path('<int:pk>/', views.service_request_detail, name='service_request_detail'),
        path('<int:pk>/edit/', views.service_request_update, name='service_request_update'),
        path('<int:pk>/delete/', views.service_request_delete, name='service_request_delete'),
        
        # Workflow actions
        path('<int:pk>/submit/', views.service_request_submit, name='service_request_submit'),
        path('<int:pk>/action/<str:action>/', views.service_request_action, name='service_request_action'),
        
        # Documents and comments
        path('<int:pk>/upload-document/', views.service_request_upload_document, name='service_request_upload_document'),
        path('document/<int:doc_id>/delete/', views.service_request_delete_document, name='service_request_delete_document'),
        path('<int:pk>/add-comment/', views.service_request_add_comment, name='service_request_add_comment'),
        
        # API endpoint
        path('api/<str:request_id>/update-status/', views.update_service_request_status, name='update_service_request_status'),
    ])),
    
    # Role-specific service request views
    path('operations/service-requests/', views.ops_service_requests, name='ops_service_requests'),
    path('rm/service-requests/', views.rm_service_requests, name='rm_service_requests'),
    
    # Team Management
    path('teams/', include([
        path('', views.team_management, name='team_management'),
        path('create/', views.create_team, name='create_team'),
        path('<int:team_id>/', views.team_detail, name='team_detail'),
        path('<int:team_id>/edit/', views.edit_team, name='edit_team'),
        path('users/<int:user_id>/', views.user_profile, name='user_profile'),
        path('users/<int:user_id>/edit/', views.edit_user, name='edit_user'),
    ])),
    
    # Operations Team Views
    path('ops/', include([
        path('team-performance/', views.ops_team_performance, name='ops_team_performance'),
        path('client-profiles/', views.ops_client_profiles, name='ops_client_profiles'),
        path('task-assignment/', views.ops_task_assignment, name='ops_task_assignment'),
        path('my-tasks/', views.ops_my_tasks, name='ops_my_tasks'),
        path('my-clients/', views.ops_my_clients, name='ops_my_clients'),
    ])),

    # Business Head Operations Views
    path('bh-ops/', include([
        path('overview/', views.bh_ops_overview, name='bh_ops_overview'),
        path('team-management/', views.bh_ops_team_management, name='bh_ops_team_management'),
        path('performance-metrics/', views.bh_ops_performance_metrics, name='bh_ops_performance_metrics'),
        path('compliance/', views.bh_ops_compliance, name='bh_ops_compliance'),
    ])),

    # ===== ENHANCED EXECUTION PLANS WITH EMAIL INTEGRATION =====
    path('execution-plans/', include([
        # Main execution plan views
        path('', views.ongoing_plans, name='ongoing_plans'),
        path('create/', views.create_plan, name='create_plan'),
        path('create/<str:client_id>/', views.create_plan_step2, name='create_plan_step2'),
        path('save/', views.save_execution_plan, name='save_execution_plan'),
        path('<int:plan_id>/', views.execution_plan_detail, name='execution_plan_detail'),
        path('completed/', views.completed_plans, name='completed_plans'),
        path('reports/', views.execution_reports, name='execution_reports'),
        path('templates/', views.plan_templates, name='plan_templates'),
        path('<int:plan_id>/analytics/', views.plan_analytics, name='plan_analytics'),
        
        # ===== ENHANCED WORKFLOW ACTIONS WITH EMAIL =====
        # Original workflow actions (kept for backward compatibility)
        path('<int:plan_id>/submit/', views.submit_for_approval, name='submit_for_approval'),
        path('<int:plan_id>/approve/', views.approve_plan, name='approve_plan'),
        path('<int:plan_id>/reject/', views.reject_plan, name='reject_plan'),
        path('<int:plan_id>/mark-client-approved/', views.mark_client_approved, name='mark_client_approved'),
        path('<int:plan_id>/start-execution/', views.start_execution, name='start_execution'),
        path('<int:plan_id>/send-to-client/', views.send_to_client, name='send_to_client'),
        
        # ===== NEW EMAIL-ENHANCED WORKFLOW ACTIONS =====
        path('<int:plan_id>/submit-with-email/', views.submit_for_approval_with_email, name='submit_for_approval_with_email'),
        path('<int:plan_id>/approve-with-email/', views.approve_plan_with_email, name='approve_plan_with_email'),
        path('<int:plan_id>/mark-client-approved-with-email/', views.mark_client_approved_with_email, name='mark_client_approved_with_email'),
        path('<int:plan_id>/complete-with-email/', views.complete_execution_with_email, name='complete_execution_with_email'),
        
        path('<int:plan_id>/send-to-client-enhanced/', views.send_to_client_enhanced, name='send_to_client_enhanced'),

        
        # ===== ACTION MANAGEMENT =====
        path('actions/<int:action_id>/details/', views.get_action_details, name='get_action_details'),
        path('actions/<int:action_id>/execute/', views.execute_action, name='execute_action'),
        path('actions/<int:action_id>/mark-failed/', views.mark_action_failed, name='mark_action_failed'),
        
        # ===== WORKFLOW TRACKING =====
        path('<int:plan_id>/track-workflow/', views.track_workflow, name='track_workflow'),
        
        # ===== COMMENTS AND COMMUNICATION =====
        path('<int:plan_id>/add-comment/', views.add_comment, name='add_comment'),
        path('<int:plan_id>/comments/add/', views.add_comment, name='add_comment_alt'),
        
        # ===== FILE OPERATIONS =====
        path('<int:plan_id>/download-excel/', views.download_excel, name='download_excel'),
        path('<int:plan_id>/generate-excel/', views.generate_excel, name='generate_excel'),
        path('<int:plan_id>/email-plan/', views.email_plan, name='email_plan'),
        
        # ===== TEMPLATE MANAGEMENT =====
        path('templates/save/', views.save_template, name='save_template'),
        path('templates/<int:template_id>/load/', views.load_template_ajax, name='load_template_ajax'),
        
        # ===== BULK OPERATIONS =====
        path('bulk-action/', views.bulk_action_plans, name='bulk_action_plans'),
        
        # ===== API ENDPOINTS =====
        path('api/client/<str:client_id>/portfolio/', views.client_portfolio_ajax, name='client_portfolio_ajax'),
        path('api/schemes/search/', views.search_schemes_ajax, name='search_schemes_ajax'),
        path('api/execution-plans/save/', views.save_execution_plan, name='save_execution_plan_api'),
        path('api/templates/<int:template_id>/', views.load_template_ajax, name='load_template_ajax_api'),
        path('api/templates/save/', views.save_template, name='save_template_api'),
    ])),

    # API endpoints
    path('api/', include([
        path('dashboard-stats/', views.get_dashboard_stats, name='get_dashboard_stats'),
        path('user-hierarchy/', views.get_user_hierarchy, name='get_user_hierarchy'),
        path('team-performance/', views.get_team_performance, name='get_team_performance'),
        path('notes/quick-create/', views.quick_create_note, name='quick_create_note'),
        path('tasks/quick-assign/', views.quick_assign_task, name='quick_assign_task'),
    ])),

    # Quick access
    path('quick/', include([
        path('note/', views.quick_note_create, name='quick_note_create'),
        path('task/', views.quick_task_create, name='quick_task_create'),
        path('client-search/', views.quick_client_search, name='quick_client_search'),
        path('lead-search/', views.quick_lead_search, name='quick_lead_search'),
    ])),
    
    # Password Reset
    path('password-reset/', views.password_reset_request, name='password_reset_request'),
    path('password-reset/confirm/<uidb64>/<token>/', views.password_reset_confirm, name='password_reset_confirm'),
    
    # Analytics
    path('analytics/', views.analytics_dashboard, name='analytics_dashboard'),
]