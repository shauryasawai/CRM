# templatetags/lead_filters.py
from django import template

register = template.Library()

@register.filter
def lead_status_badge(status):
    """
    Return Bootstrap badge class based on lead status
    """
    status_map = {
        'new': 'primary',
        'contacted': 'info', 
        'qualified': 'warning',
        'proposal': 'secondary',
        'negotiation': 'dark',
        'closed_won': 'success',
        'closed_lost': 'danger',
        'on_hold': 'light',
        # Add more status mappings as needed
    }
    return status_map.get(status, 'secondary')  # default to secondary if status not found

@register.filter
def user_can_edit(user_permissions, lead):
    """
    Check if user can edit the given lead based on permissions and lead assignment
    """
    # If user has full access, they can edit any lead
    if hasattr(user_permissions, 'role') and user_permissions.role in ['business_head', 'top_management']:
        return True
    
    # If user is assigned to the lead, they can edit it
    if hasattr(lead, 'assigned_to') and lead.assigned_to == user_permissions:
        return True
    
    # If user is the creator of the lead
    if hasattr(lead, 'created_by') and lead.created_by == user_permissions:
        return True
    
    # Add more permission logic as needed
    return False