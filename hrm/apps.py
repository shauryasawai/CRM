# hrm/apps.py
from django.apps import AppConfig

class HrmConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'hrm'
    verbose_name = 'Human Resource Management'
