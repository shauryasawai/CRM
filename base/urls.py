from django.urls import path
from . import views

urlpatterns = [
    # Dashboard
    path('dashboard/', views.dashboard, name='dashboard'),
    
    path('login/', views.user_login, name='login'),
    path('logout/', views.user_logout, name='logout'),


    # Lead URLs
    path('leads/', views.lead_list, name='lead_list'),
    path('leads/create/', views.lead_create, name='lead_create'),
    path('leads/<int:pk>/update/', views.lead_update, name='lead_update'),
    path('leads/<int:pk>/delete/', views.lead_delete, name='lead_delete'),

    # Client URLs
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
]
