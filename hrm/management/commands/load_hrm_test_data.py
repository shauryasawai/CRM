from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model

User = get_user_model()

from ...models import (
    Department, Employee, LeaveType, 
    LeaveRequest, Attendance, Notification
)
from django.utils import timezone
from datetime import datetime, timedelta
import random

class Command(BaseCommand):
    help = 'Loads test data for HRM module'

    def handle(self, *args, **options):
        self.stdout.write("Creating HRM test data...")
        
        # Create departments
        departments = self.create_departments()
        
        # Create leave types
        leave_types = self.create_leave_types()
        
        # Create users and employees
        employees = self.create_employees(departments)
        
        # Create leave requests
        self.create_leave_requests(employees, leave_types)
        
        # Create attendance records
        self.create_attendance_records(employees)
        
        # Create notifications
        self.create_notifications(employees)
        
        self.stdout.write(self.style.SUCCESS("Successfully created HRM test data!"))

    def create_departments(self):
        departments = [
            {"name": "Sales", "description": "Sales Department"},
            {"name": "Marketing", "description": "Marketing Department"},
            {"name": "IT", "description": "Information Technology"},
            {"name": "Finance", "description": "Finance and Accounting"},
            {"name": "HR", "description": "Human Resources"},
        ]
        
        created = []
        for dept in departments:
            obj, created_flag = Department.objects.get_or_create(
                name=dept['name'],
                defaults={'description': dept['description']}
            )
            if created_flag:
                created.append(obj)
        
        self.stdout.write(f"Created {len(created)} departments")
        return Department.objects.all()  # Return all departments, not just created ones

    def create_leave_types(self):
        leave_types = [
            {"name": "Casual Leave", "max_days": 12},
            {"name": "Sick Leave", "max_days": 15},
            {"name": "Earned Leave", "max_days": 30},
            {"name": "Maternity Leave", "max_days": 180},
            {"name": "Paternity Leave", "max_days": 30},
            {"name": "Comp-Off", "max_days": 5},
            {"name": "Special Leave", "max_days": 5},
        ]
        
        created = []
        for lt in leave_types:
            obj, created_flag = LeaveType.objects.get_or_create(
                name=lt['name'],
                defaults={'max_days': lt['max_days']}
            )
            if created_flag:
                created.append(obj)
        
        self.stdout.write(f"Created {len(created)} leave types")
        return LeaveType.objects.all()  # Return all leave types, not just created ones

    def get_or_create_user_and_employee(self, username, password, first_name, last_name, email, designation, department, date_of_joining, hierarchy_level, leave_balance, reporting_manager=None):
        """Helper method to get or create user and employee"""
        user, user_created = User.objects.get_or_create(
            username=username,
            defaults={
                'password': password,
                'first_name': first_name,
                'last_name': last_name,
                'email': email
            }
        )
        
        # Set password if user was created
        if user_created:
            user.set_password(password)
            user.save()
        
        employee, emp_created = Employee.objects.get_or_create(
            user=user,
            defaults={
                'designation': designation,
                'department': department,
                'date_of_joining': date_of_joining,
                'hierarchy_level': hierarchy_level,
                'leave_balance': leave_balance,
                'reporting_manager': reporting_manager
            }
        )
        
        return employee, emp_created

    def create_employees(self, departments):
        hierarchy_levels = ['TM', 'BH', 'RMH', 'RM']
        created_employees = []
        
        # First create top management
        tm_employee, tm_created = self.get_or_create_user_and_employee(
            username='tm1',
            password='test123',
            first_name='John',
            last_name='Smith',
            email='tm1@example.com',
            designation='CEO',
            department=random.choice(departments),
            date_of_joining=timezone.now() - timedelta(days=365*5),
            hierarchy_level='TM',
            leave_balance=30
        )
        if tm_created:
            created_employees.append(tm_employee)
        
        # Create business heads
        bh_employees = []
        for i in range(1, 3):
            employee, created = self.get_or_create_user_and_employee(
                username=f'bh{i}',
                password='test123',
                first_name=f'BusinessHead{i}',
                last_name='Doe',
                email=f'bh{i}@example.com',
                designation=f'Business Head {i}',
                department=random.choice(departments),
                date_of_joining=timezone.now() - timedelta(days=365*3),
                hierarchy_level='BH',
                leave_balance=25,
                reporting_manager=tm_employee
            )
            bh_employees.append(employee)
            if created:
                created_employees.append(employee)
        
        # Create RM Heads
        rmh_employees = []
        for i, bh in enumerate(bh_employees, 1):
            for j in range(1, 3):
                employee, created = self.get_or_create_user_and_employee(
                    username=f'rmh{i}{j}',
                    password='test123',
                    first_name=f'RMHead{i}{j}',
                    last_name='Johnson',
                    email=f'rmh{i}{j}@example.com',
                    designation=f'RM Head {i}-{j}',
                    department=random.choice(departments),
                    date_of_joining=timezone.now() - timedelta(days=365*2),
                    hierarchy_level='RMH',
                    leave_balance=20,
                    reporting_manager=bh
                )
                rmh_employees.append(employee)
                if created:
                    created_employees.append(employee)
        
        # Create RMs
        rm_employees = []
        for i, rmh in enumerate(rmh_employees, 1):
            for j in range(1, 4):
                employee, created = self.get_or_create_user_and_employee(
                    username=f'rm{i}{j}',
                    password='test123',
                    first_name=f'RM{i}{j}',
                    last_name='Williams',
                    email=f'rm{i}{j}@example.com',
                    designation=f'Relationship Manager {i}-{j}',
                    department=random.choice(departments),
                    date_of_joining=timezone.now() - timedelta(days=365),
                    hierarchy_level='RM',
                    leave_balance=15,
                    reporting_manager=rmh
                )
                rm_employees.append(employee)
                if created:
                    created_employees.append(employee)
        
        all_employees = [tm_employee] + bh_employees + rmh_employees + rm_employees
        self.stdout.write(f"Created {len(created_employees)} new employees (total: {len(all_employees)})")
        return all_employees

    def create_leave_requests(self, employees, leave_types):
        statuses = ['P', 'A', 'R']
        today = timezone.now().date()
        created_count = 0
        
        for emp in employees:
            # Create 2-5 leave requests per employee
            for _ in range(random.randint(2, 5)):
                start_date = today - timedelta(days=random.randint(1, 60))
                end_date = start_date + timedelta(days=random.randint(1, 5))
                
                status = random.choice(statuses)
                processed_by = emp.reporting_manager if status in ['A', 'R'] else None
                processed_on = timezone.now() - timedelta(days=random.randint(1, 30)) if processed_by else None
                
                # Check if similar leave request already exists
                existing = LeaveRequest.objects.filter(
                    employee=emp,
                    start_date=start_date,
                    end_date=end_date
                ).first()
                
                if not existing:
                    LeaveRequest.objects.create(
                        employee=emp,
                        leave_type=random.choice(leave_types),
                        start_date=start_date,
                        end_date=end_date,
                        reason=f"Sample leave reason for {emp.user.get_full_name()}",
                        status=status,
                        processed_by=processed_by,
                        processed_on=processed_on
                    )
                    created_count += 1
        
        self.stdout.write(f"Created {created_count} leave requests")

    def create_attendance_records(self, employees):
        today = timezone.now().date()
        created_count = 0
        
        for emp in employees:
            # Create attendance for last 30 days
            for day in range(1, 31):
                date = today - timedelta(days=day)
                
                # Skip weekends (5=Saturday, 6=Sunday)
                if date.weekday() >= 5:
                    continue
                
                # Check if attendance record already exists
                existing = Attendance.objects.filter(employee=emp, date=date).first()
                if existing:
                    continue
                
                login_time = datetime.combine(
                    date,
                    datetime.strptime(f"{random.randint(8, 10)}:{random.randint(0, 59)}", "%H:%M").time()
                )
                
                # 90% chance of having logout time
                has_logout = random.random() < 0.9
                logout_time = None
                if has_logout:
                    logout_time = datetime.combine(
                        date,
                        datetime.strptime(f"{random.randint(16, 19)}:{random.randint(0, 59)}", "%H:%M").time()
                    )
                
                # 10% chance of remote login
                is_remote = random.random() < 0.1
                
                Attendance.objects.create(
                    employee=emp,
                    date=date,
                    login_time=login_time,
                    logout_time=logout_time,
                    is_late=login_time.time() > datetime.strptime("09:30", "%H:%M").time(),
                    is_remote=is_remote,
                    login_location=f"Sample location {random.randint(1, 100)}"
                )
                created_count += 1
        
        self.stdout.write(f"Created {created_count} attendance records")

    def create_notifications(self, employees):
        created_count = 0
        for emp in employees:
            # Create 3-8 notifications per employee
            for i in range(random.randint(3, 8)):
                days_ago = random.randint(1, 30)
                created_at = timezone.now() - timedelta(days=days_ago)
                
                # Check if similar notification already exists
                existing = Notification.objects.filter(
                    recipient=emp,
                    created_at__date=created_at.date()
                ).count()
                
                # Limit notifications per day per employee
                if existing < 2:
                    Notification.objects.create(
                        recipient=emp,
                        message=f"Sample notification for {emp.user.get_full_name()}",
                        is_read=random.choice([True, False]),
                        created_at=created_at,
                        link=f"/hrm/leave/{random.randint(1, 100)}/"
                    )
                    created_count += 1
        
        self.stdout.write(f"Created {created_count} notifications")