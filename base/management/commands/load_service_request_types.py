#!/usr/bin/env python
"""
Django Management Command to Load Service Request Types Data
Save this file as: your_app/management/commands/load_service_request_types.py

Usage:
python manage.py load_service_request_types
python manage.py load_service_request_types --clear  # Clear existing data first
"""

import os
import sys
import django
from django.core.management.base import BaseCommand
from django.db import transaction

# Add your project root to Python path if running as standalone script
# Uncomment and modify the path below if needed
# sys.path.append('/path/to/your/django/project')

# Setup Django environment if running as standalone script
# Uncomment the lines below if running as standalone script
# os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'your_project.settings')
# django.setup()

class Command(BaseCommand):
    help = 'Load Service Request Types data into the database'

    def add_arguments(self, parser):
        parser.add_argument(
            '--clear',
            action='store_true',
            help='Clear existing service request types before loading new ones',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be created without actually creating records',
        )

    def handle(self, *args, **options):
        from base.models import ServiceRequestType  # Replace 'your_app' with actual app name
        
        # Service Request Types Data
        request_types_data = [
            # Personal Details Modification – Add/Modify/Delete
            {
                'name': 'Email Update',
                'category': 'personal_details',
                'code': 'personal_email',
                'description': 'Add, modify, or delete email address in client records',
                'default_priority': 'medium',
                'sla_hours': 24,
                'requires_approval': False,
                'department': 'operations',
                'required_documents': ['identity_proof', 'signed_form'],
                'internal_instructions': 'Verify email format and update in all relevant systems. Send confirmation email to new address.'
            },
            {
                'name': 'Mobile Number Update',
                'category': 'personal_details',
                'code': 'personal_mobile',
                'description': 'Add, modify, or delete mobile number in client records',
                'default_priority': 'medium',
                'sla_hours': 24,
                'requires_approval': False,
                'department': 'operations',
                'required_documents': ['identity_proof', 'signed_form'],
                'internal_instructions': 'Verify mobile number format and update in all systems. Send SMS confirmation to new number.'
            },
            {
                'name': 'Address Change',
                'category': 'personal_details',
                'code': 'personal_address',
                'description': 'Add, modify, or delete address in client records',
                'default_priority': 'medium',
                'sla_hours': 48,
                'requires_approval': True,
                'department': 'operations',
                'required_documents': ['address_proof', 'identity_proof', 'signed_form'],
                'internal_instructions': 'Verify address proof documents. Update address in all systems and notify compliance team.'
            },
            {
                'name': 'Bank Details Update',
                'category': 'personal_details',
                'code': 'personal_bank_details',
                'description': 'Add, modify, or delete bank account details',
                'default_priority': 'high',
                'sla_hours': 24,
                'requires_approval': True,
                'department': 'operations',
                'required_documents': ['bank_statement', 'cancelled_cheque', 'signed_form'],
                'internal_instructions': 'Verify bank details thoroughly. Update in trading and settlement systems. Notify compliance.'
            },
            {
                'name': 'Nominee Update',
                'category': 'personal_details',
                'code': 'personal_nominee',
                'description': 'Add, modify, or delete nominee information',
                'default_priority': 'high',
                'sla_hours': 48,
                'requires_approval': True,
                'department': 'compliance',
                'required_documents': ['nominee_form', 'nominee_identity_proof', 'relationship_proof'],
                'internal_instructions': 'Verify nominee details and relationship. Update in all systems and maintain compliance records.'
            },
            {
                'name': 'Name Change',
                'category': 'personal_details',
                'code': 'personal_name_change',
                'description': 'Legal name change in client records',
                'default_priority': 'high',
                'sla_hours': 72,
                'requires_approval': True,
                'department': 'compliance',
                'required_documents': ['gazette_notification', 'affidavit', 'identity_proof', 'signed_form'],
                'internal_instructions': 'Verify legal name change documents. Update across all systems. Notify regulatory authorities if required.'
            },
            {
                'name': 'Re-KYC',
                'category': 'personal_details',
                'code': 'personal_re_kyc',
                'description': 'Re-verification of Know Your Customer documents',
                'default_priority': 'urgent',
                'sla_hours': 48,
                'requires_approval': True,
                'department': 'compliance',
                'required_documents': ['kyc_form', 'identity_proof', 'address_proof', 'income_proof'],
                'internal_instructions': 'Complete KYC verification process. Update compliance status. Ensure regulatory compliance.'
            },
            
            # Account Creation
            {
                'name': 'Mutual Fund CAN Creation',
                'category': 'account_creation',
                'code': 'account_mf_can',
                'description': 'Create new Mutual Fund Common Account Number',
                'default_priority': 'medium',
                'sla_hours': 48,
                'requires_approval': False,
                'department': 'operations',
                'required_documents': ['kyc_documents', 'bank_proof', 'signed_application'],
                'internal_instructions': 'Verify KYC status. Create CAN in AMC systems. Generate welcome kit.'
            },
            {
                'name': 'MOSL Demat Account',
                'category': 'account_creation',
                'code': 'account_mosl_demat',
                'description': 'Create new MOSL Demat account',
                'default_priority': 'medium',
                'sla_hours': 72,
                'requires_approval': True,
                'department': 'operations',
                'required_documents': ['demat_application', 'kyc_documents', 'bank_proof', 'income_proof'],
                'internal_instructions': 'Complete demat account opening process. Generate BOID. Setup trading access.'
            },
            {
                'name': 'PL Demat Account',
                'category': 'account_creation',
                'code': 'account_pl_demat',
                'description': 'Create new PL Demat account',
                'default_priority': 'medium',
                'sla_hours': 72,
                'requires_approval': True,
                'department': 'operations',
                'required_documents': ['demat_application', 'kyc_documents', 'bank_proof', 'income_proof'],
                'internal_instructions': 'Complete PL demat account opening. Generate BOID. Setup trading platform access.'
            },
            
            # Account Closure Request
            {
                'name': 'MOSL Demat Closure',
                'category': 'account_closure',
                'code': 'closure_mosl_demat',
                'description': 'Close MOSL Demat account',
                'default_priority': 'high',
                'sla_hours': 120,
                'requires_approval': True,
                'department': 'operations',
                'required_documents': ['closure_form', 'demat_statement', 'identity_proof'],
                'internal_instructions': 'Verify zero balance. Process closure. Generate closure confirmation.'
            },
            {
                'name': 'PL Demat Closure',
                'category': 'account_closure',
                'code': 'closure_pl_demat',
                'description': 'Close PL Demat account',
                'default_priority': 'high',
                'sla_hours': 120,
                'requires_approval': True,
                'department': 'operations',
                'required_documents': ['closure_form', 'demat_statement', 'identity_proof'],
                'internal_instructions': 'Verify zero balance. Process PL closure. Generate closure confirmation.'
            },
            
            # Adhoc Requests – Mutual Fund
            {
                'name': 'ARN Change',
                'category': 'adhoc_mf',
                'code': 'adhoc_mf_arn_change',
                'description': 'Change Agent Registration Number for mutual fund transactions',
                'default_priority': 'medium',
                'sla_hours': 48,
                'requires_approval': True,
                'department': 'operations',
                'required_documents': ['arn_change_form', 'new_arn_certificate'],
                'internal_instructions': 'Verify new ARN validity. Update in AMC systems. Confirm commission structure.'
            },
            {
                'name': 'RI to NRI Conversion',
                'category': 'adhoc_mf',
                'code': 'adhoc_mf_ri_to_nri',
                'description': 'Convert Resident Indian account to Non-Resident Indian status',
                'default_priority': 'high',
                'sla_hours': 72,
                'requires_approval': True,
                'department': 'compliance',
                'required_documents': ['nri_documents', 'overseas_address_proof', 'nre_account_proof'],
                'internal_instructions': 'Verify NRI status documents. Update account classification. Ensure FEMA compliance.'
            },
            {
                'name': 'NRI to RI Conversion',
                'category': 'adhoc_mf',
                'code': 'adhoc_mf_nri_to_ri',
                'description': 'Convert Non-Resident Indian account to Resident Indian status',
                'default_priority': 'high',
                'sla_hours': 72,
                'requires_approval': True,
                'department': 'compliance',
                'required_documents': ['ri_documents', 'indian_address_proof', 'resident_bank_proof'],
                'internal_instructions': 'Verify resident status. Update account classification. Ensure regulatory compliance.'
            },
            {
                'name': 'Physical Mandate Request',
                'category': 'adhoc_mf',
                'code': 'adhoc_mf_mandate_physical',
                'description': 'Setup physical mandate for mutual fund transactions',
                'default_priority': 'medium',
                'sla_hours': 48,
                'requires_approval': False,
                'department': 'operations',
                'required_documents': ['signed_mandate_form', 'bank_verification'],
                'internal_instructions': 'Process physical mandate setup. Update in payment systems.'
            },
            {
                'name': 'Online Mandate Request',
                'category': 'adhoc_mf',
                'code': 'adhoc_mf_mandate_online',
                'description': 'Setup online mandate for mutual fund transactions',
                'default_priority': 'low',
                'sla_hours': 24,
                'requires_approval': False,
                'department': 'operations',
                'required_documents': ['online_mandate_authorization'],
                'internal_instructions': 'Process online mandate through NPCI. Verify bank authorization.'
            },
            {
                'name': 'Change of Mapping',
                'category': 'adhoc_mf',
                'code': 'adhoc_mf_change_mapping',
                'description': 'Change mutual fund scheme mapping or category',
                'default_priority': 'medium',
                'sla_hours': 48,
                'requires_approval': True,
                'department': 'operations',
                'required_documents': ['mapping_change_form', 'scheme_details'],
                'internal_instructions': 'Verify new mapping requirements. Update in AMC systems.'
            },
            
            # Adhoc Requests - Demat
            {
                'name': 'Brokerage Change',
                'category': 'adhoc_demat',
                'code': 'adhoc_demat_brokerage_change',
                'description': 'Modify brokerage rates or structure',
                'default_priority': 'high',
                'sla_hours': 48,
                'requires_approval': True,
                'department': 'relationship',
                'required_documents': ['brokerage_change_form', 'approval_letter'],
                'internal_instructions': 'Verify approval authority. Update brokerage structure. Notify trading systems.'
            },
            {
                'name': 'DP Scheme Modification',
                'category': 'adhoc_demat',
                'code': 'adhoc_demat_dp_scheme',
                'description': 'Modify Depository Participant scheme or charges',
                'default_priority': 'medium',
                'sla_hours': 48,
                'requires_approval': True,
                'department': 'operations',
                'required_documents': ['scheme_change_form', 'tariff_sheet'],
                'internal_instructions': 'Update DP charges. Modify billing parameters. Send confirmation to client.'
            },
            {
                'name': 'Stock Transfer',
                'category': 'adhoc_demat',
                'code': 'adhoc_demat_stock_transfer',
                'description': 'Transfer stocks between demat accounts',
                'default_priority': 'high',
                'sla_hours': 24,
                'requires_approval': True,
                'department': 'operations',
                'required_documents': ['transfer_form', 'target_account_details', 'authorization_letter'],
                'internal_instructions': 'Verify transfer instructions. Process through depository. Confirm completion.'
            },
            
            # Report Request
            {
                'name': 'Capital Gain Statement - MF',
                'category': 'report_request',
                'code': 'report_capital_gain_mf',
                'description': 'Generate capital gains statement for mutual fund investments',
                'default_priority': 'low',
                'sla_hours': 48,
                'requires_approval': False,
                'department': 'operations',
                'required_documents': ['report_request_form'],
                'internal_instructions': 'Generate comprehensive capital gains report from MF transactions.'
            },
            {
                'name': 'Capital Gain Statement - MOSL',
                'category': 'report_request',
                'code': 'report_capital_gain_mosl',
                'description': 'Generate capital gains statement for MOSL trading account',
                'default_priority': 'low',
                'sla_hours': 48,
                'requires_approval': False,
                'department': 'operations',
                'required_documents': ['report_request_form'],
                'internal_instructions': 'Generate capital gains report from MOSL trading data.'
            },
            {
                'name': 'Capital Gain Statement - PL',
                'category': 'report_request',
                'code': 'report_capital_gain_pl',
                'description': 'Generate capital gains statement for PL trading account',
                'default_priority': 'low',
                'sla_hours': 48,
                'requires_approval': False,
                'department': 'operations',
                'required_documents': ['report_request_form'],
                'internal_instructions': 'Generate capital gains report from PL trading data.'
            },
            {
                'name': 'MF Statement of Account',
                'category': 'report_request',
                'code': 'report_mf_soa',
                'description': 'Generate mutual fund statement of account',
                'default_priority': 'low',
                'sla_hours': 24,
                'requires_approval': False,
                'department': 'operations',
                'required_documents': ['soa_request_form'],
                'internal_instructions': 'Generate detailed MF portfolio statement.'
            },
            {
                'name': 'CAS Upload',
                'category': 'report_request',
                'code': 'report_cas_upload',
                'description': 'Upload and process Consolidated Account Statement',
                'default_priority': 'medium',
                'sla_hours': 48,
                'requires_approval': False,
                'department': 'operations',
                'required_documents': ['cas_file', 'upload_authorization'],
                'internal_instructions': 'Process CAS file upload. Validate data integrity. Update portfolio records.'
            },
        ]

        if options['clear']:
            if options['dry_run']:
                self.stdout.write(
                    self.style.WARNING('DRY RUN: Would delete all existing ServiceRequestType records')
                )
            else:
                count = ServiceRequestType.objects.count()
                ServiceRequestType.objects.all().delete()
                self.stdout.write(
                    self.style.SUCCESS(f'Deleted {count} existing ServiceRequestType records')
                )

        created_count = 0
        updated_count = 0
        
        with transaction.atomic():
            for data in request_types_data:
                if options['dry_run']:
                    existing = ServiceRequestType.objects.filter(code=data['code']).exists()
                    if existing:
                        self.stdout.write(f"DRY RUN: Would update {data['name']} ({data['code']})")
                    else:
                        self.stdout.write(f"DRY RUN: Would create {data['name']} ({data['code']})")
                    continue
                
                obj, created = ServiceRequestType.objects.get_or_create(
                    code=data['code'],
                    defaults=data
                )
                
                if created:
                    created_count += 1
                    self.stdout.write(
                        self.style.SUCCESS(f'✓ Created: {obj.name} ({obj.code})')
                    )
                else:
                    # Update existing record
                    for key, value in data.items():
                        setattr(obj, key, value)
                    obj.save()
                    updated_count += 1
                    self.stdout.write(
                        self.style.WARNING(f'↻ Updated: {obj.name} ({obj.code})')
                    )

        if not options['dry_run']:
            self.stdout.write('\n' + '='*60)
            self.stdout.write(
                self.style.SUCCESS(
                    f'Successfully loaded {created_count} new and updated {updated_count} existing service request types'
                )
            )
            
            # Summary by category
            self.stdout.write('\nSummary by category:')
            for category_code, category_name in ServiceRequestType.CATEGORY_CHOICES:
                count = ServiceRequestType.objects.filter(category=category_code).count()
                self.stdout.write(f'  {category_name}: {count} types')
        else:
            self.stdout.write('\n' + '='*60)
            self.stdout.write(
                self.style.WARNING('DRY RUN COMPLETED - No changes were made to the database')
            )


# Standalone script functionality
def load_data_standalone():
    """
    Function to run this script standalone (outside Django management command)
    """
    # Uncomment and configure these lines if running as standalone script
    # import os
    # import django
    # os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'your_project.settings')
    # django.setup()
    
    from base.models import ServiceRequestType  # Replace 'your_app' with actual app name
    
    print("Loading Service Request Types data...")
    
    # Your data loading logic here (copy from handle method above)
    # This is a simplified version for standalone use
    request_types_data = [
        # Add your data here (same as in the handle method)
        # ... 
    ]
    
    created_count = 0
    for data in request_types_data:
        obj, created = ServiceRequestType.objects.get_or_create(
            code=data['code'],
            defaults=data
        )
        if created:
            created_count += 1
            print(f'Created: {obj.name}')
    
    print(f'Successfully loaded {created_count} service request types')


if __name__ == '__main__':
    # If running as standalone script
    load_data_standalone()