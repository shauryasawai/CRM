from django import template
from django.db.models import QuerySet

register = template.Library()

@register.filter
def safe_count(obj, relation_name):
    """
    Safely get count of related objects, trying multiple possible relation names
    Usage: {{ user|safe_count:"tasks" }}
    """
    if not obj:
        return 0
    
    # Common variations for tasks
    task_relations = ['task_set', 'assigned_tasks', 'tasks', 'task_assigned']
    # Common variations for leads  
    lead_relations = ['lead_set', 'assigned_leads', 'leads', 'managed_leads']
    # Common variations for team members
    team_relations = ['subordinates', 'team_members', 'direct_reports']
    
    relations_to_try = []
    if relation_name.lower() in ['task', 'tasks']:
        relations_to_try = task_relations
    elif relation_name.lower() in ['lead', 'leads']:
        relations_to_try = lead_relations
    elif relation_name.lower() in ['team', 'members', 'subordinates']:
        relations_to_try = team_relations
    else:
        relations_to_try = [relation_name]
    
    for relation in relations_to_try:
        try:
            if hasattr(obj, relation):
                related_manager = getattr(obj, relation)
                if hasattr(related_manager, 'count'):
                    return related_manager.count()
                elif hasattr(related_manager, '__len__'):
                    return len(related_manager)
                elif isinstance(related_manager, QuerySet):
                    return related_manager.count()
        except Exception:
            continue
    
    return 0

@register.filter
def safe_relation(obj, relation_name):
    """
    Safely get related objects, trying multiple possible relation names
    Usage: {{ user|safe_relation:"tasks" }}
    """
    if not obj:
        return None
    
    # Same relation variations as above
    task_relations = ['task_set', 'assigned_tasks', 'tasks', 'task_assigned']
    lead_relations = ['lead_set', 'assigned_leads', 'leads', 'managed_leads']
    team_relations = ['subordinates', 'team_members', 'direct_reports']
    
    relations_to_try = []
    if relation_name.lower() in ['task', 'tasks']:
        relations_to_try = task_relations
    elif relation_name.lower() in ['lead', 'leads']:
        relations_to_try = lead_relations
    elif relation_name.lower() in ['team', 'members', 'subordinates']:
        relations_to_try = team_relations
    else:
        relations_to_try = [relation_name]
    
    for relation in relations_to_try:
        try:
            if hasattr(obj, relation):
                return getattr(obj, relation)
        except Exception:
            continue
    
    return None

@register.filter
def performance_score(user, max_score=100):
    """
    Calculate a performance score for a user based on their activity
    Usage: {{ user|performance_score }}
    """
    try:
        leads_count = safe_count(user, 'leads')
        tasks_count = safe_count(user, 'tasks')
        team_count = safe_count(user, 'team')
        
        # Weighted scoring
        score = (leads_count * 5) + (tasks_count * 2) + (team_count * 10)
        return min(score, max_score)
    except Exception:
        return 0

@register.simple_tag
def activity_status(user):
    """
    Get activity status based on user's workload
    Usage: {% activity_status user %}
    """
    try:
        total_activity = safe_count(user, 'leads') + safe_count(user, 'tasks')
        
        if total_activity >= 10:
            return 'status-excellent'
        elif total_activity >= 5:
            return 'status-good'
        else:
            return 'status-average'
    except Exception:
        return 'status-average'

@register.inclusion_tag('dashboard/user_badge.html')
def user_performance_badge(user, badge_type='leads'):
    """
    Render a performance badge for a user
    Usage: {% user_performance_badge user "leads" %}
    """
    count = safe_count(user, badge_type)
    return {
        'count': count,
        'badge_type': badge_type,
        'label': badge_type.title(),
        'plural_label': f"{badge_type.title()}{'s' if not badge_type.endswith('s') else ''}"
    }
    
    
