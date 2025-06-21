from django.urls import path
from . import views

urlpatterns = [
    # Dashboard
    path('dashboard/', views.dashboard, name='dashboard'),
    
    path('', views.user_login, name='login'),
    path('logout/', views.user_logout, name='logout'),
    
    # Lead URLs
    path('leads/', views.lead_list, name='lead_list'),
    path('leads/create/', views.lead_create, name='lead_create'),
    path('leads/<int:pk>/', views.lead_detail, name='lead_detail'),
    path('leads/<int:pk>/update/', views.lead_update, name='lead_update'),
    path('leads/<int:pk>/delete/', views.lead_delete, name='lead_delete'),

    # Lead Interaction URLs
    path('leads/<int:pk>/add-interaction/', views.add_interaction, name='add_interaction'),
    path('leads/interaction/<int:pk>/delete/', views.delete_interaction, name='delete_interaction'),

    # Product Discussion URLs
    path('leads/<int:pk>/add-product-discussion/', views.add_product_discussion, name='add_product_discussion'),

    # Status Management URLs
    path('leads/<int:pk>/change-status/', views.change_lead_status, name='change_lead_status'),
    path('leads/<int:pk>/request-conversion/', views.request_conversion, name='request_conversion'),
    path('leads/<int:pk>/convert/', views.convert_lead, name='convert_lead'),

    # Conversion Approval URLs
    path('leads/<int:pk>/approve-conversion/', views.approve_conversion, name='approve_conversion'),
    path('leads/<int:pk>/reject-conversion/', views.reject_conversion, name='reject_conversion'),

    # Reassignment URLs
    path('leads/<int:pk>/request-reassignment/', views.request_reassignment, name='request_reassignment'),
    path('leads/<int:pk>/approve-reassignment/', views.approve_reassignment, name='approve_reassignment'),
    path('leads/<int:pk>/reassign/', views.reassign_lead, name='reassign_lead'),

    # AJAX/API URLs
    path('leads/get-reference-clients/', views.get_reference_clients, name='get_reference_clients'),
    path('leads/get-accessible-users/', views.get_accessible_users, name='get_accessible_users'),

    # Client Profile URLs (New System)
    path('client-profiles/', views.client_profile_list, name='client_profile_list'),
    path('client-profiles/create/', views.client_profile_create, name='client_profile_create'),
    path('client-profiles/<int:pk>/', views.client_profile_detail, name='client_profile_detail'),
    path('client-profiles/<int:pk>/update/', views.client_profile_update, name='client_profile_update'),
    path('client-profiles/<int:pk>/mute/', views.client_profile_mute, name='client_profile_mute'),
    path('client-profiles/<int:pk>/delete/', views.client_profile_delete, name='client_profile_delete'),
    
    # Client Profile Modification URLs
    path('client-profiles/modification-requests/', views.modification_requests, name='modification_requests'),
    path('client-profiles/modifications/<int:pk>/approve/', views.approve_modification, name='approve_modification'),

    # Legacy Client URLs (for backward compatibility)
    path('clients/', views.client_list, name='client_list'),
    path('clients/create/', views.client_create, name='client_create'),
    path('clients/<int:pk>/update/', views.client_update, name='client_update'),
    path('clients/<int:pk>/delete/', views.client_delete, name='client_delete'),

    # Task URLs
    path('tasks/', views.task_list, name='task_list'),
    path('tasks/create/', views.task_create, name='task_create'),
    path('tasks/<int:pk>/update/', views.task_update, name='task_update'),
    path('tasks/<int:pk>/delete/', views.task_delete, name='task_delete'),

    # Service Request URLs
    path('service-requests/', views.service_request_list, name='service_request_list'),
    path('service-requests/create/', views.service_request_create, name='service_request_create'),
    path('service-requests/<int:pk>/update/', views.service_request_update, name='service_request_update'),
    path('service-requests/<int:pk>/delete/', views.service_request_delete, name='service_request_delete'),

    # Investment Plan Review URLs
    path('investment-plans/', views.investment_plan_review_list, name='investment_plan_review_list'),
    path('investment-plans/create/', views.investment_plan_review_create, name='investment_plan_review_create'),
    path('investment-plans/<int:pk>/update/', views.investment_plan_review_update, name='investment_plan_review_update'),
    path('investment-plans/<int:pk>/delete/', views.investment_plan_review_delete, name='investment_plan_review_delete'),
    
    # Team Management URLs
    path('teams/', views.team_management, name='team_management'),
    path('teams/create/', views.create_team, name='create_team'),
    path('teams/<int:team_id>/', views.team_detail, name='team_detail'),
    path('teams/<int:team_id>/edit/', views.edit_team, name='edit_team'),
    
    # User Management URLs
    path('users/<int:user_id>/', views.user_profile, name='user_profile'),
    path('users/<int:user_id>/edit/', views.edit_user, name='edit_user'),
]