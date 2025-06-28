# management/commands/reset_and_load_data.py

from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.db import transaction
from django.utils import timezone
from datetime import datetime, timedelta
import random

from base.models import (
    User, Team, TeamMembership, ClientProfile, Note, NoteList, 
    Task, ServiceRequest, Lead, Client, BusinessTracker, 
    InvestmentPlanReview, LeadInteraction, ProductDiscussion, 
    LeadStatusChange, MFUCANAccount, MotilalDematAccount, 
    PrabhudasDematAccount, ClientProfileModification
)

User = get_user_model()

class Command(BaseCommand):
    help = 'Delete all existing data and load fresh sample data'

    def add_arguments(self, parser):
        parser.add_argument(
            '--confirm',
            action='store_true',
            help='Confirm deletion of all existing data',
        )

    def handle(self, *args, **options):
        if not options['confirm']:
            self.stdout.write(
                self.style.WARNING(
                    'This will delete ALL existing data! Use --confirm to proceed.'
                )
            )
            return

        self.stdout.write('Starting data reset and reload...')
        
        with transaction.atomic():
            # Step 1: Delete all existing data
            self.delete_all_data()
            
            # Step 2: Create fresh sample data
            self.create_sample_data()

        self.stdout.write(
            self.style.SUCCESS('Successfully reset and loaded fresh data!')
        )

    def delete_all_data(self):
        """Delete all existing data in proper order to handle foreign key constraints"""
        self.stdout.write('Deleting existing data...')
        
        # Delete in reverse dependency order
        models_to_delete = [
            # Notes system
            Note,
            NoteList,
            
            # Business tracking and analytics
            BusinessTracker,
            InvestmentPlanReview,
            
            # Service requests and tasks
            ServiceRequest,
            Task,
            
            # Lead interactions and status changes
            ProductDiscussion,
            LeadInteraction,
            LeadStatusChange,
            
            # Client accounts
            MFUCANAccount,
            MotilalDematAccount,
            PrabhudasDematAccount,
            
            # Client profile modifications
            ClientProfileModification,
            
            # Clients and leads
            Client,
            Lead,
            ClientProfile,
            
            # Team memberships
            TeamMembership,
            Team,
            
            # Users (except superusers)
        ]
        
        for model in models_to_delete:
            count = model.objects.count()
            if count > 0:
                model.objects.all().delete()
                self.stdout.write(f'  Deleted {count} {model.__name__} records')
        
        # Delete users except superusers
        regular_users = User.objects.filter(is_superuser=False)
        user_count = regular_users.count()
        if user_count > 0:
            regular_users.delete()
            self.stdout.write(f'  Deleted {user_count} User records (kept superusers)')
        
        # Clear groups
        Group.objects.all().delete()
        self.stdout.write('  Deleted all Groups')

    def create_sample_data(self):
        """Create comprehensive sample data"""
        self.stdout.write('Creating fresh sample data...')
        
        # Create sample data in proper order
        self.create_sample_users()
        self.create_sample_teams()
        self.create_sample_client_profiles()
        self.create_sample_leads()
        self.create_sample_clients()
        self.create_sample_tasks()
        self.create_sample_service_requests()
        self.create_sample_notes()
        self.create_sample_business_data()

    def create_sample_users(self):
        """Create sample users for all roles"""
        users_data = [
            # Top Management
            {
                'username': 'ceo_admin',
                'email': 'ceo@company.com',
                'first_name': 'John',
                'last_name': 'CEO',
                'role': 'top_management',
                'manager': None,
                'password': 'admin123'
            },
            
            # Business Heads
            {
                'username': 'bh_sales',
                'email': 'bh.sales@company.com',
                'first_name': 'Sarah',
                'last_name': 'Sales',
                'role': 'business_head',
                'manager': 'ceo_admin',
                'password': 'admin123'
            },
            {
                'username': 'bh_operations',
                'email': 'bh.ops@company.com',
                'first_name': 'Michael',
                'last_name': 'Operations',
                'role': 'business_head_ops',
                'manager': 'ceo_admin',
                'password': 'admin123'
            },
            
            # RM Heads
            {
                'username': 'rmh_north',
                'email': 'rmh.north@company.com',
                'first_name': 'David',
                'last_name': 'North',
                'role': 'rm_head',
                'manager': 'bh_sales',
                'password': 'admin123'
            },
            {
                'username': 'rmh_south',
                'email': 'rmh.south@company.com',
                'first_name': 'Lisa',
                'last_name': 'South',
                'role': 'rm_head',
                'manager': 'bh_sales',
                'password': 'admin123'
            },
            
            # Operations Team Leads
            {
                'username': 'otl_mumbai',
                'email': 'otl.mumbai@company.com',
                'first_name': 'Priya',
                'last_name': 'Mumbai',
                'role': 'ops_team_lead',
                'manager': 'bh_operations',
                'password': 'admin123'
            },
            {
                'username': 'otl_delhi',
                'email': 'otl.delhi@company.com',
                'first_name': 'Raj',
                'last_name': 'Delhi',
                'role': 'ops_team_lead',
                'manager': 'bh_operations',
                'password': 'admin123'
            },
            
            # Relationship Managers
            {
                'username': 'rm_alice',
                'email': 'alice@company.com',
                'first_name': 'Alice',
                'last_name': 'Johnson',
                'role': 'rm',
                'manager': 'rmh_north',
                'password': 'admin123'
            },
            {
                'username': 'rm_bob',
                'email': 'bob@company.com',
                'first_name': 'Bob',
                'last_name': 'Smith',
                'role': 'rm',
                'manager': 'rmh_north',
                'password': 'admin123'
            },
            {
                'username': 'rm_carol',
                'email': 'carol@company.com',
                'first_name': 'Carol',
                'last_name': 'Brown',
                'role': 'rm',
                'manager': 'rmh_south',
                'password': 'admin123'
            },
            {
                'username': 'rm_diana',
                'email': 'diana@company.com',
                'first_name': 'Diana',
                'last_name': 'Wilson',
                'role': 'rm',
                'manager': 'rmh_south',
                'password': 'admin123'
            },
            
            # Operations Executives
            {
                'username': 'ops_amit',
                'email': 'amit@company.com',
                'first_name': 'Amit',
                'last_name': 'Sharma',
                'role': 'ops_exec',
                'manager': 'otl_mumbai',
                'password': 'admin123'
            },
            {
                'username': 'ops_sneha',
                'email': 'sneha@company.com',
                'first_name': 'Sneha',
                'last_name': 'Patel',
                'role': 'ops_exec',
                'manager': 'otl_mumbai',
                'password': 'admin123'
            },
            {
                'username': 'ops_rahul',
                'email': 'rahul@company.com',
                'first_name': 'Rahul',
                'last_name': 'Gupta',
                'role': 'ops_exec',
                'manager': 'otl_delhi',
                'password': 'admin123'
            },
            {
                'username': 'ops_kavya',
                'email': 'kavya@company.com',
                'first_name': 'Kavya',
                'last_name': 'Singh',
                'role': 'ops_exec',
                'manager': 'otl_delhi',
                'password': 'admin123'
            },
        ]

        created_users = {}
        
        # First pass: create users without managers
        for user_data in users_data:
            manager_username = user_data.pop('manager', None)
            password = user_data.pop('password', 'admin123')
            
            user = User.objects.create_user(
                password=password,
                **user_data
            )
            created_users[user.username] = {
                'user': user,
                'manager_username': manager_username
            }
            self.stdout.write(f'  Created user: {user.username} ({user.get_role_display()})')

        # Second pass: set managers
        for username, data in created_users.items():
            if data['manager_username']:
                manager = created_users[data['manager_username']]['user']
                data['user'].manager = manager
                data['user'].save()

    def create_sample_teams(self):
        """Create sample teams"""
        teams_data = [
            {
                'name': 'North Sales Team',
                'description': 'Sales team covering northern regions',
                'is_ops_team': False,
                'leader_username': 'rmh_north',
                'members': ['rm_alice', 'rm_bob']
            },
            {
                'name': 'South Sales Team',
                'description': 'Sales team covering southern regions',
                'is_ops_team': False,
                'leader_username': 'rmh_south',
                'members': ['rm_carol', 'rm_diana']
            },
            {
                'name': 'Mumbai Operations',
                'description': 'Operations team in Mumbai',
                'is_ops_team': True,
                'leader_username': 'otl_mumbai',
                'members': ['ops_amit', 'ops_sneha']
            },
            {
                'name': 'Delhi Operations',
                'description': 'Operations team in Delhi',
                'is_ops_team': True,
                'leader_username': 'otl_delhi',
                'members': ['ops_rahul', 'ops_kavya']
            },
        ]

        for team_data in teams_data:
            leader_username = team_data.pop('leader_username')
            member_usernames = team_data.pop('members')
            
            leader = User.objects.get(username=leader_username)
            
            team = Team.objects.create(
                leader=leader,
                **team_data
            )
            
            # Add team members
            for member_username in member_usernames:
                member = User.objects.get(username=member_username)
                TeamMembership.objects.create(
                    user=member,
                    team=team
                )
            
            self.stdout.write(f'  Created team: {team.name} with {len(member_usernames)} members')

    def create_sample_client_profiles(self):
        """Create sample client profiles"""
        rms = User.objects.filter(role='rm')
        ops_execs = User.objects.filter(role='ops_exec')
        
        sample_clients = [
            {
                'client_full_name': 'Rajesh Kumar Sharma',
                'address_kyc': '123 MG Road, Mumbai, Maharashtra 400001',
                'date_of_birth': '1980-05-15',
                'pan_number': 'ABCDE1234F',
                'email': 'rajesh.sharma@email.com',
                'mobile_number': '9876543210',
            },
            {
                'client_full_name': 'Priya Desai',
                'address_kyc': '456 Ring Road, Delhi, Delhi 110001',
                'date_of_birth': '1985-08-22',
                'pan_number': 'FGHIJ5678K',
                'email': 'priya.desai@email.com',
                'mobile_number': '8765432109',
            },
            {
                'client_full_name': 'Amit Patel',
                'address_kyc': '789 Civil Lines, Pune, Maharashtra 411001',
                'date_of_birth': '1975-12-10',
                'pan_number': 'KLMNO9012P',
                'email': 'amit.patel@email.com',
                'mobile_number': '7654321098',
            },
            {
                'client_full_name': 'Sunita Agarwal',
                'address_kyc': '321 Park Street, Bangalore, Karnataka 560001',
                'date_of_birth': '1978-03-28',
                'pan_number': 'QRSTU3456V',
                'email': 'sunita.agarwal@email.com',
                'mobile_number': '6543210987',
            },
            {
                'client_full_name': 'Vikram Singh',
                'address_kyc': '654 Mall Road, Chennai, Tamil Nadu 600001',
                'date_of_birth': '1982-11-05',
                'pan_number': 'WXYZ7890A',
                'email': 'vikram.singh@email.com',
                'mobile_number': '5432109876',
            },
            {
                'client_full_name': 'Meera Reddy',
                'address_kyc': '987 Cyber City, Gurgaon, Haryana 122001',
                'date_of_birth': '1990-07-14',
                'pan_number': 'BCDEF2345G',
                'email': 'meera.reddy@email.com',
                'mobile_number': '9123456780',
            },
            {
                'client_full_name': 'Ravi Krishnan',
                'address_kyc': '234 IT Park, Hyderabad, Telangana 500001',
                'date_of_birth': '1979-12-20',
                'pan_number': 'HIJKL6789M',
                'email': 'ravi.krishnan@email.com',
                'mobile_number': '8234567901',
            },
            {
                'client_full_name': 'Anjali Gupta',
                'address_kyc': '567 Sector 18, Noida, Uttar Pradesh 201301',
                'date_of_birth': '1987-04-03',
                'pan_number': 'NOPQR1234S',
                'email': 'anjali.gupta@email.com',
                'mobile_number': '7345678012',
            },
        ]

        for i, client_data in enumerate(sample_clients):
            rm = rms[i % rms.count()]
            ops_exec = ops_execs[i % ops_execs.count()]
            
            # Convert date string to date object
            client_data['date_of_birth'] = datetime.strptime(
                client_data['date_of_birth'], '%Y-%m-%d'
            ).date()
            
            client_profile = ClientProfile.objects.create(
                mapped_rm=rm,
                mapped_ops_exec=ops_exec,
                created_by=random.choice(list(rms) + list(ops_execs)),
                first_investment_date=timezone.now().date() - timedelta(days=random.randint(30, 365)),
                **client_data
            )
            
            self.stdout.write(f'  Created client profile: {client_profile.client_full_name}')

    def create_sample_leads(self):
        """Create sample leads"""
        rms = User.objects.filter(role='rm')
        rm_heads = User.objects.filter(role='rm_head')
        
        lead_templates = [
            {
                'name': 'Arjun Mehta',
                'email': 'arjun.mehta@email.com',
                'mobile': '9876543210',
                'source': 'existing_client',
                'source_details': 'Referred by existing client',
                'probability': 70,
                'status': 'warm'
            },
            {
                'name': 'Kavitha Rao',
                'email': 'kavitha.rao@email.com',
                'mobile': '8765432109',
                'source': 'social_media',
                'source_details': 'LinkedIn campaign',
                'probability': 45,
                'status': 'contacted'
            },
            {
                'name': 'Deepak Joshi',
                'email': 'deepak.joshi@email.com',
                'mobile': '7654321098',
                'source': 'own_circle',
                'source_details': 'Personal network',
                'probability': 80,
                'status': 'hot'
            },
            {
                'name': 'Meera Saxena',
                'email': 'meera.saxena@email.com',
                'mobile': '6543210987',
                'source': 'referral',
                'source_details': 'Business partner referral',
                'probability': 60,
                'status': 'follow_up'
            },
            {
                'name': 'Rohit Verma',
                'email': 'rohit.verma@email.com',
                'mobile': '5432109876',
                'source': 'other',
                'source_details': 'Trade show contact',
                'probability': 30,
                'status': 'cold'
            },
            {
                'name': 'Neha Shah',
                'email': 'neha.shah@email.com',
                'mobile': '9123456789',
                'source': 'existing_client',
                'source_details': 'Family member referral',
                'probability': 65,
                'status': 'warm'
            },
        ]

        for template in lead_templates:
            assigned_to = random.choice(rms)
            created_by = random.choice(list(rms) + list(rm_heads))
            
            lead = Lead.objects.create(
                assigned_to=assigned_to,
                created_by=created_by,
                notes=f'Initial contact made. Interested in investment options.',
                **template
            )
            
            # Create some interactions for leads that have been contacted
            if template['status'] in ['contacted', 'warm', 'hot', 'follow_up']:
                LeadInteraction.objects.create(
                    lead=lead,
                    interaction_type='call',
                    interaction_date=timezone.now() - timedelta(days=random.randint(1, 7)),
                    notes='Initial discussion about investment goals and risk appetite.',
                    interacted_by=assigned_to,
                    next_step='Send investment proposal',
                    next_date=(timezone.now() + timedelta(days=random.randint(2, 5))).date()
                )
            
            self.stdout.write(f'  Created lead: {lead.name}')

    def create_sample_clients(self):
        """Create sample clients from client profiles"""
        client_profiles = ClientProfile.objects.all()[:4]  # Convert first 4 profiles to clients
        
        for profile in client_profiles:
            client = Client.objects.create(
                name=profile.client_full_name,
                contact_info=f"{profile.email}, {profile.mobile_number}",
                user=profile.mapped_rm,
                client_profile=profile,
                created_by=profile.mapped_rm,
                aum=random.randint(100000, 2000000),
                sip_amount=random.randint(5000, 50000),
                demat_count=random.randint(1, 3)
            )
            
            self.stdout.write(f'  Created client: {client.name}')

    def create_sample_tasks(self):
        """Create sample tasks"""
        users = User.objects.all()
        ops_users = users.filter(role__in=['ops_team_lead', 'ops_exec'])
        rm_users = users.filter(role='rm')
        
        task_templates = [
            {
                'title': 'Process KYC Documents',
                'description': 'Review and process pending KYC documentation for new clients.',
                'priority': 'high',
                'days_due': 2,
                'for_ops': True
            },
            {
                'title': 'Client Onboarding',
                'description': 'Complete onboarding process for new client accounts.',
                'priority': 'medium',
                'days_due': 5,
                'for_ops': True
            },
            {
                'title': 'Monthly Portfolio Review',
                'description': 'Conduct monthly portfolio review with assigned clients.',
                'priority': 'medium',
                'days_due': 7,
                'for_ops': False
            },
            {
                'title': 'Lead Follow-up',
                'description': 'Follow up with warm leads from last week.',
                'priority': 'high',
                'days_due': 1,
                'for_ops': False
            },
            {
                'title': 'Compliance Report',
                'description': 'Prepare and submit monthly compliance report.',
                'priority': 'urgent',
                'days_due': 3,
                'for_ops': True
            },
            {
                'title': 'Client Meeting Preparation',
                'description': 'Prepare presentation materials for upcoming client meetings.',
                'priority': 'medium',
                'days_due': 4,
                'for_ops': False
            },
        ]

        # Create tasks for different roles
        for task_template in task_templates:
            target_users = ops_users if task_template['for_ops'] else rm_users
            
            for user in target_users:
                # Some tasks are assigned by managers
                if user.manager:
                    assigned_by = user.manager
                else:
                    assigned_by = random.choice(users.filter(
                        role__in=['business_head', 'business_head_ops', 'rm_head', 'ops_team_lead']
                    ))
                
                due_date = timezone.now() + timedelta(days=task_template['days_due'])
                
                Task.objects.create(
                    assigned_to=user,
                    assigned_by=assigned_by,
                    title=task_template['title'],
                    description=task_template['description'],
                    priority=task_template['priority'],
                    due_date=due_date,
                    completed=random.choice([True, False]) if task_template['days_due'] > 3 else False
                )
        
        self.stdout.write(f'  Created tasks for operations and RM users')

    def create_sample_service_requests(self):
        """Create sample service requests"""
        clients = Client.objects.all()
        ops_users = User.objects.filter(role__in=['ops_team_lead', 'ops_exec'])
        
        service_request_templates = [
            {
                'description': 'Client requesting change in bank account details for SIP transactions.',
                'priority': 'medium',
                'status': 'open'
            },
            {
                'description': 'Update client contact information and communication preferences.',
                'priority': 'low',
                'status': 'in_progress'
            },
            {
                'description': 'Client wants to redeem partial units from equity mutual fund.',
                'priority': 'high',
                'status': 'open'
            },
            {
                'description': 'Generate and send quarterly portfolio statement to client.',
                'priority': 'medium',
                'status': 'resolved'
            },
            {
                'description': 'Process new SIP registration for diversified equity fund.',
                'priority': 'high',
                'status': 'open'
            },
            {
                'description': 'Client complaint regarding delayed fund transfer.',
                'priority': 'urgent',
                'status': 'in_progress'
            },
        ]

        for template in service_request_templates:
            client = random.choice(clients)
            raised_by = client.user  # RM who manages the client
            assigned_to = random.choice(ops_users)  # Assign to operations team
            
            service_request = ServiceRequest.objects.create(
                client=client,
                raised_by=raised_by,
                assigned_to=assigned_to,
                **template
            )
            
            # Set resolved_at for resolved requests
            if template['status'] in ['resolved', 'closed']:
                service_request.resolved_at = timezone.now() - timedelta(days=random.randint(1, 5))
                service_request.save()
        
        self.stdout.write(f'  Created {len(service_request_templates)} sample service requests')

    def create_sample_notes(self):
        """Create sample notes for users"""
        users = User.objects.all()
        
        note_list_templates = [
            {'name': 'General', 'description': 'General notes and reminders'},
            {'name': 'Client Follow-ups', 'description': 'Client related follow-up tasks'},
            {'name': 'Team Tasks', 'description': 'Team coordination and tasks'},
            {'name': 'Personal', 'description': 'Personal notes and ideas'},
            {'name': 'Meeting Notes', 'description': 'Notes from meetings and discussions'},
        ]
        
        note_templates = [
            {
                'heading': 'Weekly Team Meeting',
                'content': 'Discuss weekly targets and performance metrics with team members.\n\nAgenda:\n- Review last week performance\n- Set new targets\n- Address team concerns',
                'days_ahead': 2,
                'due_days': 7
            },
            {
                'heading': 'Client Portfolio Review',
                'content': 'Review client portfolios and suggest rebalancing if needed.\n\nClients to review:\n- Rajesh Kumar\n- Priya Desai\n- Amit Patel',
                'days_ahead': 1,
                'due_days': 3
            },
            {
                'heading': 'Compliance Training',
                'content': 'Complete mandatory compliance training modules before deadline.\n\nModules pending:\n- Anti-money laundering\n- Data protection\n- Investment regulations',
                'days_ahead': 5,
                'due_days': 30
            },
            {
                'heading': 'Market Analysis Report',
                'content': 'Prepare monthly market analysis report for management review.\n\nKey points to cover:\n- Market trends\n- Performance analysis\n- Future outlook',
                'days_ahead': 3,
                'due_days': 15
            },
            {
                'heading': 'Follow up with new leads',
                'content': 'Contact new leads generated from recent marketing campaign.\n\nHot leads to prioritize:\n- Deepak Joshi (80% probability)\n- Neha Shah (65% probability)',
                'days_ahead': 1,
                'due_days': 2
            },
        ]

        for user in users:
            # Create note lists for each user
            user_lists = []
            for list_template in note_list_templates:
                note_list = NoteList.objects.create(
                    user=user,
                    **list_template
                )
                user_lists.append(note_list)
            
            # Create sample notes
            for i, note_template in enumerate(note_templates):
                note_list = user_lists[i % len(user_lists)]
                
                # Calculate dates
                reminder_date = timezone.now() + timedelta(days=note_template['days_ahead'])
                due_date = timezone.now().date() + timedelta(days=note_template['due_days'])
                
                Note.objects.create(
                    user=user,
                    note_list=note_list,
                    heading=note_template['heading'],
                    content=note_template['content'],
                    reminder_date=reminder_date,
                    due_date=due_date,
                    is_completed=random.choice([True, False]) if i > 2 else False  # Some completed notes
                )
            
            self.stdout.write(f'  Created notes for user: {user.username}')

    def create_sample_business_data(self):
        """Create sample business tracking data"""
        rms = User.objects.filter(role='rm')
        
        # Create monthly business data for last 6 months
        for user in rms:
            for i in range(6):
                month_date = timezone.now().date() - timedelta(days=30*i)
                month_date = month_date.replace(day=1)  # First day of month
                
                BusinessTracker.objects.create(
                    month=month_date,
                    user=user,
                    total_sip=random.randint(50000, 200000),
                    total_demat=random.randint(2, 8),
                    total_aum=random.randint(1000000, 5000000)
                )
        
        self.stdout.write('  Created sample business tracker data')
        
        # Create some investment plans
        clients = Client.objects.all()
        for client in clients:
            InvestmentPlanReview.objects.create(
                client=client,
                created_by=client.user,
                goal=random.choice(['Retirement', 'Child Education', 'House Purchase', 'Vacation', 'Emergency Fund']),
                principal_amount=random.randint(100000, 500000),
                monthly_investment=random.randint(5000, 25000),
                tenure_years=random.randint(5, 20),
                expected_return_rate=random.uniform(8.0, 15.0)
            )
        
        self.stdout.write('  Created sample investment plans')

        self.stdout.write('Sample data creation completed!')