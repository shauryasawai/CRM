from django import forms
from django.contrib.auth.forms import UserCreationForm, UserChangeForm
from .models import User, Lead, Client, Task, Reminder, ServiceRequest, InvestmentPlanReview

class CustomUserCreationForm(UserCreationForm):
    role = forms.ChoiceField(choices=User._meta.get_field('role').choices)

    class Meta:
        model = User
        fields = ('username', 'email', 'role', 'password1', 'password2')


class CustomUserChangeForm(UserChangeForm):
    role = forms.ChoiceField(choices=User._meta.get_field('role').choices)

    class Meta:
        model = User
        fields = ('username', 'email', 'role')


class LeadForm(forms.ModelForm):
    class Meta:
        model = Lead
        fields = ['name', 'contact_info', 'source', 'status', 'assigned_to', 'notes']

        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Enter lead name'}),
            'contact_info': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Phone, Email, etc.'}),
            'source': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Where did the lead come from?'}),
            'status': forms.Select(attrs={'class': 'form-select'}),
            'assigned_to': forms.Select(attrs={'class': 'form-select'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 4, 'placeholder': 'Additional notes...'}),
        }

class ClientForm(forms.ModelForm):
    class Meta:
        model = Client
        fields = ['name', 'contact_info', 'user', 'lead', 'aum', 'sip_amount', 'demat_count']


class TaskForm(forms.ModelForm):
    class Meta:
        model = Task
        fields = ['title', 'description', 'due_date', 'completed', 'assigned_to']
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3}),
            'due_date': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
        }


class ReminderForm(forms.ModelForm):
    class Meta:
        model = Reminder
        fields = ['message', 'remind_at', 'is_done']
        widgets = {
            'remind_at': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
        }


class ServiceRequestForm(forms.ModelForm):
    class Meta:
        model = ServiceRequest
        fields = ['client', 'description', 'status']
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3}),
            'status': forms.Select(choices=[
                ('Open', 'Open'),
                ('In Progress', 'In Progress'),
                ('Closed', 'Closed')
            ])
        }


class InvestmentPlanReviewForm(forms.ModelForm):
    class Meta:
        model = InvestmentPlanReview
        fields = ['client', 'goal', 'principal_amount', 'tenure_years', 'monthly_investment']

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)

        if user:
            if user.role == 'rm':
                self.fields['client'].queryset = Client.objects.filter(user=user)
            elif user.role == 'rm_head':
                team_rms = User.objects.filter(role='rm', groups__in=user.groups.all())
                self.fields['client'].queryset = Client.objects.filter(user__in=team_rms)
            else:
                self.fields['client'].queryset = Client.objects.none()

