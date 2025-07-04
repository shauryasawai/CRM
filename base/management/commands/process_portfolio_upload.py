# management/commands/process_portfolio_upload.py
# Create this file in: your_app/management/commands/process_portfolio_upload.py

import os
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from django.db import transaction
from django.conf import settings

# Adjust these imports based on your app structure
try:
    from base.models import PortfolioUpload, ClientPortfolio, PortfolioUploadLog
except ImportError:
    # Try alternative import paths
    try:
        from base.models import PortfolioUpload, ClientPortfolio, PortfolioUploadLog
    except ImportError:
        # If models are in a different app, adjust accordingly
        from base.models import PortfolioUpload, ClientPortfolio, PortfolioUploadLog

class Command(BaseCommand):
    help = 'Process portfolio Excel upload and map to client profiles'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--upload-id',
            type=str,
            help='Process specific upload by ID',
            dest='upload_id'
        )
        parser.add_argument(
            '--file-path',
            type=str,
            help='Process Excel file directly from path',
            dest='file_path'
        )
        parser.add_argument(
            '--auto-map',
            action='store_true',
            help='Automatically map to client profiles based on PAN',
            dest='auto_map'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be processed without making changes',
            dest='dry_run'
        )
    
    def handle(self, *args, **options):
        upload_id = options.get('upload_id')
        file_path = options.get('file_path')
        auto_map = options.get('auto_map', False)
        dry_run = options.get('dry_run', False)
        
        try:
            if upload_id:
                self.process_upload_by_id(upload_id, auto_map, dry_run)
            elif file_path:
                self.process_file_directly(file_path, auto_map, dry_run)
            else:
                self.process_pending_uploads(auto_map, dry_run)
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Command failed: {str(e)}'))
            raise CommandError(f'Processing failed: {str(e)}')
    
    def process_upload_by_id(self, upload_id, auto_map, dry_run):
        """Process specific upload by ID"""
        try:
            upload = PortfolioUpload.objects.get(upload_id=upload_id)
            self.stdout.write(f"Processing upload: {upload}")
            
            if dry_run:
                self.stdout.write(self.style.WARNING("DRY RUN MODE - No changes will be made"))
                results = self.analyze_file(upload.file.path)
                self.display_results(results)
                return
            
            results = self.process_upload(upload, auto_map)
            self.display_results(results)
            
        except PortfolioUpload.DoesNotExist:
            raise CommandError(f"Upload with ID {upload_id} not found")
    
    def process_file_directly(self, file_path, auto_map, dry_run):
        """Process Excel file directly without upload record"""
        if not os.path.exists(file_path):
            raise CommandError(f"File not found: {file_path}")
        
        if not file_path.endswith(('.xlsx', '.xls')):
            raise CommandError("File must be an Excel file (.xlsx or .xls)")
        
        self.stdout.write(f"Processing file directly: {file_path}")
        
        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN MODE - No changes will be made"))
            results = self.analyze_file(file_path)
            self.display_results(results)
            return
        
        # Create temporary upload record
        from django.contrib.auth import get_user_model
        User = get_user_model()
        admin_user = User.objects.filter(is_superuser=True).first()
        
        if not admin_user:
            raise CommandError("No admin user found to assign upload to")
        
        upload = PortfolioUpload.objects.create(
            file=file_path,
            uploaded_by=admin_user,
            status='processing'
        )
        
        results = self.process_upload(upload, auto_map)
        self.display_results(results)
    
    def process_pending_uploads(self, auto_map, dry_run):
        """Process all pending uploads"""
        pending_uploads = PortfolioUpload.objects.filter(status='pending')
        
        if not pending_uploads.exists():
            self.stdout.write(self.style.SUCCESS("No pending uploads to process"))
            return
        
        self.stdout.write(f"Found {pending_uploads.count()} pending uploads")
        
        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN MODE - No changes will be made"))
            for upload in pending_uploads:
                self.stdout.write(f"\nWould process: {upload}")
                results = self.analyze_file(upload.file.path)
                self.display_results(results)
            return
        
        for upload in pending_uploads:
            self.stdout.write(f"\nProcessing upload: {upload}")
            try:
                results = self.process_upload(upload, auto_map)
                self.display_results(results)
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"Failed to process {upload}: {str(e)}"))
                continue
    
    def process_upload(self, upload, auto_map):
        """Process a single upload"""
        try:
            upload.status = 'processing'
            upload.processing_log = f"Started processing at {timezone.now()}"
            upload.save()
            
            # Process the Excel file using the model method
            results = ClientPortfolio.process_excel_file(upload.file.path, upload)
            
            # Update upload status
            upload.total_rows = results['total_rows']
            upload.processed_rows = results['processed_rows']
            upload.successful_rows = results['successful_rows']
            upload.failed_rows = results['failed_rows']
            upload.processing_summary = results['summary']
            upload.error_details = {'errors': results['errors']}
            upload.processed_at = timezone.now()
            
            # Set final status
            if results['failed_rows'] == 0:
                upload.status = 'completed'
                upload.processing_log += f"\nCompleted successfully at {timezone.now()}"
            elif results['successful_rows'] > 0:
                upload.status = 'partial'
                upload.processing_log += f"\nPartially completed at {timezone.now()}"
            else:
                upload.status = 'failed'
                upload.processing_log += f"\nFailed at {timezone.now()}"
            
            upload.save()
            
            # Auto-map to client profiles if requested
            if auto_map and results['successful_rows'] > 0:
                mapping_results = self.auto_map_portfolios(upload)
                results.update(mapping_results)
            
            return results
            
        except Exception as e:
            upload.status = 'failed'
            upload.error_details = {'error': str(e)}
            upload.processing_log += f"\nFailed with error: {str(e)} at {timezone.now()}"
            upload.processed_at = timezone.now()
            upload.save()
            raise CommandError(f"Failed to process upload: {e}")
    
    def analyze_file(self, file_path):
        """Analyze Excel file without processing (for dry run)"""
        try:
            import pandas as pd
            
            df = pd.read_excel(file_path)
            
            # Column mapping
            expected_columns = [
                'CLIENT', 'CLIENT PAN', 'SCHEME', ' DEBT', ' EQUITY', 
                ' HYBRID', ' LIQUID AND  ULTRA  SHORT', ' OTHER', 
                ' ARBITRAGE', 'TOTAL', 'ALLOCATION', 'UNITS'
            ]
            
            df_columns = [col.strip() for col in df.columns]
            missing_columns = []
            
            for col in expected_columns:
                if col.strip() not in df_columns:
                    missing_columns.append(col.strip())
            
            extra_columns = [col for col in df_columns if col not in [c.strip() for c in expected_columns]]
            
            # Basic statistics
            unique_clients = df['CLIENT PAN'].nunique() if 'CLIENT PAN' in df.columns else 0
            unique_schemes = df['SCHEME'].nunique() if 'SCHEME' in df.columns else 0
            total_aum = df['TOTAL'].sum() if 'TOTAL' in df.columns else 0
            
            results = {
                'total_rows': len(df),
                'unique_clients': unique_clients,
                'unique_schemes': unique_schemes,
                'total_aum': total_aum,
                'missing_columns': missing_columns,
                'extra_columns': extra_columns[:10],  # Limit to first 10
                'sample_data': df.head(3).to_dict('records') if not df.empty else []
            }
            
            return results
            
        except Exception as e:
            raise CommandError(f"Failed to analyze file: {e}")
    
    def auto_map_portfolios(self, upload):
        """Auto-map portfolio entries to client profiles"""
        portfolio_entries = ClientPortfolio.objects.filter(upload_batch=upload, is_mapped=False)
        
        mapping_results = {
            'mapping_attempted': portfolio_entries.count(),
            'mapping_successful': 0,
            'mapping_failed': 0,
            'mapping_errors': []
        }
        
        for portfolio in portfolio_entries:
            try:
                mapped, message = portfolio.map_to_client_profile()
                if mapped:
                    mapping_results['mapping_successful'] += 1
                    
                    # Also try to map personnel
                    personnel_mapped = portfolio.map_personnel()
                    
                    # Log successful mapping
                    try:
                        PortfolioUploadLog.objects.create(
                            upload=upload,
                            row_number=0,
                            client_name=portfolio.client_name,
                            client_pan=portfolio.client_pan,
                            scheme_name=portfolio.scheme_name,
                            status='success',
                            message=f"Mapped to client profile: {message}. Personnel mapped: {personnel_mapped}",
                            portfolio_entry=portfolio
                        )
                    except:
                        pass  # Continue if logging fails
                else:
                    mapping_results['mapping_failed'] += 1
                    mapping_results['mapping_errors'].append(f"{portfolio.client_pan}: {message}")
                    
                    # Log failed mapping
                    try:
                        PortfolioUploadLog.objects.create(
                            upload=upload,
                            row_number=0,
                            client_name=portfolio.client_name,
                            client_pan=portfolio.client_pan,
                            scheme_name=portfolio.scheme_name,
                            status='warning',
                            message=f"Mapping failed: {message}",
                            portfolio_entry=portfolio
                        )
                    except:
                        pass  # Continue if logging fails
                    
            except Exception as e:
                mapping_results['mapping_failed'] += 1
                mapping_results['mapping_errors'].append(f"{portfolio.client_pan}: {str(e)}")
                
                # Log error
                try:
                    PortfolioUploadLog.objects.create(
                        upload=upload,
                        row_number=0,
                        client_name=portfolio.client_name,
                        client_pan=portfolio.client_pan,
                        scheme_name=portfolio.scheme_name,
                        status='error',
                        message=f"Mapping error: {str(e)}",
                        portfolio_entry=portfolio
                    )
                except:
                    pass  # Continue if logging fails
        
        return mapping_results
    
    def display_results(self, results):
        """Display processing results"""
        self.stdout.write(self.style.SUCCESS("\n" + "="*50))
        self.stdout.write(self.style.SUCCESS("PROCESSING RESULTS"))
        self.stdout.write(self.style.SUCCESS("="*50))
        
        # Basic statistics
        if 'total_rows' in results:
            self.stdout.write(f"Total rows: {results['total_rows']}")
        
        if 'processed_rows' in results:
            self.stdout.write(f"Processed rows: {results['processed_rows']}")
            self.stdout.write(f"Successful rows: {results.get('successful_rows', 0)}")
            self.stdout.write(f"Failed rows: {results.get('failed_rows', 0)}")
        
        if 'unique_clients' in results:
            self.stdout.write(f"Unique clients: {results['unique_clients']}")
        
        if 'unique_schemes' in results:
            self.stdout.write(f"Unique schemes: {results['unique_schemes']}")
        
        if 'total_aum' in results:
            self.stdout.write(f"Total AUM: ₹{results['total_aum']:,.2f}")
        
        # Mapping results
        if 'mapping_attempted' in results:
            self.stdout.write(f"\nClient Mapping Results:")
            self.stdout.write(f"Attempted: {results['mapping_attempted']}")
            self.stdout.write(f"Successful: {results['mapping_successful']}")
            self.stdout.write(f"Failed: {results['mapping_failed']}")
        
        # Column analysis (for dry run)
        if 'missing_columns' in results:
            if results['missing_columns']:
                self.stdout.write(self.style.WARNING(f"\nMissing expected columns: {results['missing_columns']}"))
            else:
                self.stdout.write(self.style.SUCCESS("\nAll expected columns found"))
        
        if 'extra_columns' in results and results['extra_columns']:
            self.stdout.write(f"Additional columns found: {results['extra_columns']}")
        
        # Errors
        if 'errors' in results and results['errors']:
            self.stdout.write(self.style.ERROR(f"\nErrors encountered:"))
            for error in results['errors'][:10]:  # Show first 10 errors
                self.stdout.write(self.style.ERROR(f"  - {error}"))
            
            if len(results['errors']) > 10:
                self.stdout.write(self.style.ERROR(f"  ... and {len(results['errors']) - 10} more errors"))
        
        # Mapping errors
        if 'mapping_errors' in results and results['mapping_errors']:
            self.stdout.write(self.style.WARNING(f"\nMapping errors:"))
            for error in results['mapping_errors'][:10]:
                self.stdout.write(self.style.WARNING(f"  - {error}"))
            
            if len(results['mapping_errors']) > 10:
                self.stdout.write(self.style.WARNING(f"  ... and {len(results['mapping_errors']) - 10} more errors"))
        
        # Summary
        if 'summary' in results:
            summary = results['summary']
            self.stdout.write(self.style.SUCCESS(f"\nSummary:"))
            for key, value in summary.items():
                self.stdout.write(f"  {key.replace('_', ' ').title()}: {value}")


# management/commands/__init__.py
# Create this empty file to make the directory a Python package