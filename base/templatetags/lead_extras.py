# Create this file: your_app/templatetags/lead_extras.py
# (Replace 'your_app' with your actual app name, like 'leads')

from django import template
from django.contrib.auth.models import User

register = template.Library()

@register.filter
def user_can_edit(user_permission, lead):
    """
    Check if user can edit the lead based on permissions and lead assignment
    Usage: {% if user.can_access_user_data|user_can_edit:lead %}
    """
    # If user doesn't have basic permission, return False
    if not user_permission:
        return False
    
    # Get the current user from the context (you might need to pass this differently)
    # This is a simplified version - adjust based on your actual permission logic
    
    # Example logic - adjust according to your business rules:
    # - User can edit if they are assigned to the lead
    # - OR if they have higher-level permissions
    # - OR based on other business rules
    
    return True  # Placeholder - implement your actual logic here

@register.filter
def lead_status_badge(status):
    """
    Return Bootstrap badge class based on lead status
    """
    status_classes = {
        'new': 'primary',
        'contacted': 'info',
        'qualified': 'warning',
        'proposal': 'secondary',
        'negotiation': 'dark',
        'closed_won': 'success',
        'closed_lost': 'danger',
        'conversion_requested': 'warning',
        'converted': 'success',
    }
    return status_classes.get(status, 'secondary')

@register.filter
def multiply(value, arg):
    """
    Multiply the value by the argument
    Usage: {{ value|multiply:10 }}
    """
    try:
        return float(value) * float(arg)
    except (ValueError, TypeError):
        return 0

@register.filter
def split(value, delimiter=','):
    """
    Split a string by delimiter
    Usage: {{ 'a,b,c'|split }}
    """
    if value:
        return value.split(delimiter)
    return []