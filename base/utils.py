from django.shortcuts import redirect
import pandas as pd
from datetime import datetime, date
from django.utils import timezone
from django.core.exceptions import ValidationError
import logging
from django.contrib import messages  # ADD THIS IMPORT
from decimal import Decimal
from base import models
import json

logger = logging.getLogger(__name__)

class DecimalEncoder(json.JSONEncoder):
    """Custom JSON encoder to handle Decimal objects"""
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        return super().default(obj)

def decimal_to_float(obj):
    """Convert Decimal objects to float for JSON serialization"""
    if isinstance(obj, dict):
        return {key: decimal_to_float(value) for key, value in obj.items()}
    elif isinstance(obj, list):
        return [decimal_to_float(item) for item in obj]
    elif isinstance(obj, Decimal):
        return float(obj)
    else:
        return obj

def safe_datetime_convert(value):
    """
    Safely convert various datetime formats to Django-compatible datetime
    """
    if value is None or pd.isna(value):
        return None
    
    # If it's already a datetime object
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return timezone.make_aware(value)
        return value
    
    # If it's a date object
    if isinstance(value, date):
        return timezone.make_aware(datetime.combine(value, datetime.min.time()))
    
    # If it's a pandas Timestamp
    if isinstance(value, pd.Timestamp):
        return timezone.make_aware(value.to_pydatetime())
    
    # If it's a string
    if isinstance(value, str):
        # Try different date formats
        date_formats = [
            '%Y-%m-%d %H:%M:%S',
            '%Y-%m-%d',
            '%d/%m/%Y',
            '%d-%m-%Y',
            '%m/%d/%Y',
            '%Y-%m-%d %H:%M:%S.%f',
            '%d/%m/%Y %H:%M:%S',
        ]
        
        for fmt in date_formats:
            try:
                dt = datetime.strptime(value.strip(), fmt)
                return timezone.make_aware(dt)
            except ValueError:
                continue
        
        # If no format works, try pandas to_datetime
        try:
            dt = pd.to_datetime(value)
            if pd.notna(dt):
                return timezone.make_aware(dt.to_pydatetime())
        except:
            pass
    
    # If it's a number (Excel date serial)
    if isinstance(value, (int, float)):
        try:
            # Excel date serial conversion
            dt = pd.to_datetime(value, origin='1899-12-30', unit='D')
            return timezone.make_aware(dt.to_pydatetime())
        except:
            pass
    
    logger.warning(f"Could not convert datetime value: {value} (type: {type(value)})")
    return None

def safe_date_convert(value):
    """
    Safely convert various date formats to Django-compatible date
    """
    if value is None or pd.isna(value):
        return None
    
    # If it's already a date object
    if isinstance(value, date):
        return value
    
    # If it's a datetime object
    if isinstance(value, datetime):
        return value.date()
    
    # If it's a pandas Timestamp
    if isinstance(value, pd.Timestamp):
        return value.date()
    
    # If it's a string
    if isinstance(value, str):
        date_formats = [
            '%Y-%m-%d',
            '%d/%m/%Y',
            '%d-%m-%Y',
            '%m/%d/%Y',
            '%Y-%m-%d %H:%M:%S',
            '%d/%m/%Y %H:%M:%S',
        ]
        
        for fmt in date_formats:
            try:
                dt = datetime.strptime(value.strip(), fmt)
                return dt.date()
            except ValueError:
                continue
        
        # Try pandas to_datetime
        try:
            dt = pd.to_datetime(value)
            if pd.notna(dt):
                return dt.date()
        except:
            pass
    
    # If it's a number (Excel date serial)
    if isinstance(value, (int, float)):
        try:
            dt = pd.to_datetime(value, origin='1899-12-30', unit='D')
            return dt.date()
        except:
            pass
    
    logger.warning(f"Could not convert date value: {value} (type: {type(value)})")
    return None

def safe_decimal_convert(value, default=0):
    """
    Safely convert values to Decimal for Django DecimalField
    """
    from decimal import Decimal, InvalidOperation
    
    if value is None or pd.isna(value):
        return Decimal(str(default))
    
    # Handle string values
    if isinstance(value, str):
        # Remove common formatting characters
        value = value.replace(',', '').replace('₹', '').replace('$', '').strip()
        if not value:
            return Decimal(str(default))
    
    try:
        return Decimal(str(float(value)))
    except (ValueError, InvalidOperation, TypeError):
        logger.warning(f"Could not convert decimal value: {value} (type: {type(value)})")
        return Decimal(str(default))

def safe_string_convert(value):
    """
    Safely convert values to string, handling NaN and None
    """
    if value is None or pd.isna(value):
        return ''
    
    if isinstance(value, (int, float)):
        if pd.isna(value):
            return ''
        return str(value)
    
    return str(value).strip()

# Updated ClientPortfolio.process_excel_file method
def process_excel_file_safe(cls, file_path, upload_instance):
    """
    Enhanced process_excel_file method with better datetime and data handling
    """
    results = {
        'total_rows': 0,
        'processed_rows': 0,
        'successful_rows': 0,
        'failed_rows': 0,
        'errors': [],
        'summary': {}
    }
    
    try:
        # Read Excel file with better handling
        df = pd.read_excel(file_path, engine='openpyxl')
        results['total_rows'] = len(df)
        
        # Clean column names (remove extra spaces)
        df.columns = df.columns.str.strip()
        
        # Column mapping based on the Excel structure
        column_mapping = {
            'CLIENT': 'client_name',
            'CLIENT PAN': 'client_pan',
            'SCHEME': 'scheme_name',
            'DEBT': 'debt_value',
            'EQUITY': 'equity_value',
            'HYBRID': 'hybrid_value',
            'LIQUID AND ULTRA SHORT': 'liquid_ultra_short_value',
            'OTHER': 'other_value',
            'ARBITRAGE': 'arbitrage_value',
            'TOTAL': 'total_value',
            'ALLOCATION': 'allocation_percentage',
            'UNITS': 'units',
            'FAMILY HEAD': 'family_head',
            'APP CODE': 'app_code',
            'EQUITY CODE': 'equity_code',
            'OPERATIONS': 'operations_personnel',
            'OPERATIONS CODE': 'operations_code',
            'RELATIONSHIP MANAGER': 'relationship_manager',
            'RELATIONSHIP MANAGER CODE': 'rm_code',
            'SUB BROKER': 'sub_broker',
            'SUB BROKER CODE': 'sub_broker_code',
            'ISIN NO': 'isin_number',
            'CLIENT IWELL CODE': 'client_iwell_code',
            'FAMILY HEAD IWELL CODE': 'family_head_iwell_code'
        }
        
        # Also handle columns with extra spaces
        space_variations = {
            ' DEBT': 'debt_value',
            ' EQUITY': 'equity_value',
            ' HYBRID': 'hybrid_value',
            ' LIQUID AND  ULTRA  SHORT': 'liquid_ultra_short_value',
            ' OTHER': 'other_value',
            ' ARBITRAGE': 'arbitrage_value',
            ' OPERATIONS': 'operations_personnel',
            ' OPERATIONS CODE': 'operations_code',
            ' RELATIONSHIP  MANAGER': 'relationship_manager',
            ' RELATIONSHIP  MANAGER CODE': 'rm_code',
            ' SUB  BROKER': 'sub_broker',
            ' SUB  BROKER CODE': 'sub_broker_code',
        }
        
        # Combine mappings
        full_column_mapping = {**column_mapping, **space_variations}
        
        # Process each row with transaction
        from django.db import transaction
        
        with transaction.atomic():
            for index, row in df.iterrows():
                try:
                    results['processed_rows'] += 1
                    
                    # Prepare data for portfolio entry
                    portfolio_data = {
                        'upload_batch': upload_instance,
                        'data_as_of_date': safe_date_convert(timezone.now().date()),
                        'is_active': True,
                        'is_mapped': False
                    }
                    
                    # Map columns with safe conversion
                    for excel_col, model_field in full_column_mapping.items():
                        if excel_col in row and pd.notna(row[excel_col]):
                            value = row[excel_col]
                            
                            # Handle different data types
                            if model_field in [
                                'debt_value', 'equity_value', 'hybrid_value', 
                                'liquid_ultra_short_value', 'other_value', 'arbitrage_value',
                                'total_value', 'allocation_percentage', 'units'
                            ]:
                                portfolio_data[model_field] = safe_decimal_convert(value)
                            elif model_field in ['data_as_of_date']:
                                portfolio_data[model_field] = safe_date_convert(value)
                            else:
                                portfolio_data[model_field] = safe_string_convert(value)
                    
                    # Validate required fields
                    if not portfolio_data.get('client_name') or not portfolio_data.get('scheme_name'):
                        results['failed_rows'] += 1
                        results['errors'].append(f"Row {index + 2}: Missing client name or scheme name")
                        continue
                    
                    # Create portfolio entry
                    portfolio_entry = cls.objects.create(**portfolio_data)
                    
                    # Try to map to client profile
                    try:
                        mapped, message = portfolio_entry.map_to_client_profile()
                        
                        # Try to map personnel
                        personnel_mapped = portfolio_entry.map_personnel()
                        
                    except Exception as mapping_error:
                        logger.warning(f"Mapping failed for row {index + 2}: {mapping_error}")
                    
                    results['successful_rows'] += 1
                    
                except Exception as e:
                    results['failed_rows'] += 1
                    error_msg = f"Row {index + 2}: {str(e)}"
                    results['errors'].append(error_msg)
                    logger.error(f"Error processing row {index + 2}: {e}")
        
        # Update summary
        results['summary'] = {
            'unique_clients': cls.objects.filter(upload_batch=upload_instance).values('client_pan').distinct().count(),
            'unique_schemes': cls.objects.filter(upload_batch=upload_instance).values('scheme_name').distinct().count(),
            'mapped_clients': cls.objects.filter(upload_batch=upload_instance, is_mapped=True).count(),
            'total_aum': cls.objects.filter(upload_batch=upload_instance).aggregate(
                total=models.Sum('total_value')
            )['total'] or 0
        }
        
    except Exception as e:
        results['errors'].append(f"File processing error: {str(e)}")
        results['failed_rows'] = results['total_rows']
        logger.error(f"File processing failed: {e}")
    
    return results

def process_portfolio_upload(upload_id=None, auto_map=True):
    """
    Process portfolio upload using utility function
    Returns results dictionary with processing details
    """
    from .models import PortfolioUpload, ClientPortfolio
    from django.utils import timezone
    import logging
    
    logger = logging.getLogger(__name__)
    
    try:
        # Get the upload object
        upload = PortfolioUpload.objects.get(upload_id=upload_id)
        
        # Update status to processing
        upload.status = 'processing'
        upload.processing_log = f"Started processing at {timezone.now()}"
        upload.save()
        
        # Process the Excel file using the model method
        results = ClientPortfolio.process_excel_file(upload.file.path, upload)
        
        # Update upload with results
        upload.total_rows = results['total_rows']
        upload.processed_rows = results['processed_rows']
        upload.successful_rows = results['successful_rows']
        upload.failed_rows = results['failed_rows']
        upload.processing_summary = results['summary']
        upload.error_details = {'errors': results['errors']}
        upload.processed_at = timezone.now()
        
        # Set final status based on results
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
        mapping_results = {}
        if auto_map and results['successful_rows'] > 0:
            try:
                mapping_results = auto_map_portfolios(upload)
                results.update(mapping_results)
                
                # Update processing log with mapping results
                upload.processing_log += f"\nMapping attempted: {mapping_results.get('mapping_attempted', 0)}"
                upload.processing_log += f"\nMapping successful: {mapping_results.get('mapping_successful', 0)}"
                upload.save()
                
            except Exception as e:
                logger.warning(f"Auto-mapping failed for upload {upload_id}: {e}")
                mapping_results = {'mapping_error': str(e)}
        
        # Combine results
        final_results = {
            'successful_uploads': 1,
            'processed_uploads': 1,
            'failed_uploads': 0,
            'upload_status': upload.status,
            **results,
            **mapping_results
        }
        
        return final_results
        
    except PortfolioUpload.DoesNotExist:
        raise Exception(f"Upload with ID {upload_id} not found")
    except Exception as e:
        # Update upload status on failure
        try:
            upload = PortfolioUpload.objects.get(upload_id=upload_id)
            upload.status = 'failed'
            upload.error_details = {'error': str(e)}
            upload.processing_log += f"\nFailed with error: {str(e)} at {timezone.now()}"
            upload.processed_at = timezone.now()
            upload.save()
        except:
            pass  # If we can't update the upload, continue with the exception
        
        logger.error(f"Portfolio processing failed for upload {upload_id}: {e}")
        raise Exception(f"Failed to process portfolio upload: {str(e)}")

def auto_map_portfolios(upload):
    """Auto-map portfolio entries to client profiles"""
    from .models import ClientPortfolio
    import logging
    
    logger = logging.getLogger(__name__)
    
    # Get unmapped portfolios from this upload
    unmapped_portfolios = ClientPortfolio.objects.filter(
        upload_batch=upload, 
        is_mapped=False
    )
    
    mapping_results = {
        'mapping_attempted': unmapped_portfolios.count(),
        'mapping_successful': 0,
        'mapping_failed': 0,
        'mapping_errors': []
    }
    
    for portfolio in unmapped_portfolios:
        try:
            # Try to map to client profile
            mapped, message = portfolio.map_to_client_profile()
            
            if mapped:
                mapping_results['mapping_successful'] += 1
                
                # Also try to map personnel
                try:
                    personnel_mapped = portfolio.map_personnel()
                    if personnel_mapped > 0:
                        logger.info(f"Mapped {personnel_mapped} personnel for portfolio {portfolio.id}")
                except Exception as e:
                    logger.warning(f"Personnel mapping failed for portfolio {portfolio.id}: {e}")
                
            else:
                mapping_results['mapping_failed'] += 1
                mapping_results['mapping_errors'].append(f"{portfolio.client_pan}: {message}")
                
        except Exception as e:
            mapping_results['mapping_failed'] += 1
            error_msg = f"{portfolio.client_pan}: {str(e)}"
            mapping_results['mapping_errors'].append(error_msg)
            logger.error(f"Mapping error for portfolio {portfolio.id}: {e}")
    
    return mapping_results

# Also update your admin.py - Replace the process_upload_view method

def process_upload_view(self, request, upload_id):
    """Process a specific upload - Updated to use utility function"""
    upload = self.get_object(request, upload_id)
    if upload is None:
        self.message_user(request, "Upload not found", level=messages.ERROR)
        return redirect(f'admin:{self.model._meta.app_label}_portfolioupload_changelist')
    
    try:
        # CHANGED: Use utility function instead of management command
        from .utils import process_portfolio_upload
        
        results = process_portfolio_upload(upload_id=upload.upload_id, auto_map=True)
        
        if results.get('successful_uploads', 0) > 0:
            success_msg = f"Upload {upload.upload_id} processed successfully. "
            success_msg += f"{results.get('successful_rows', 0)} rows processed"
            if results.get('mapping_successful', 0) > 0:
                success_msg += f", {results.get('mapping_successful', 0)} clients mapped"
            
            self.message_user(request, success_msg, level=messages.SUCCESS)
        else:
            self.message_user(
                request, 
                f"Upload {upload.upload_id} processing failed", 
                level=messages.ERROR
            )
            
    except Exception as e:
        self.message_user(
            request, 
            f"Error processing upload: {str(e)}", 
            level=messages.ERROR
        )
    
    return redirect(f'admin:{self.model._meta.app_label}_portfolioupload_changelist')

# Bulk process view for admin - Also updated
def bulk_process_view(self, request):
    """Process all pending uploads - Updated to use utility function"""
    try:
        # CHANGED: Use utility function instead of management command
        from .utils import process_portfolio_upload
        from .models import PortfolioUpload
        
        pending_uploads = PortfolioUpload.objects.filter(status='pending')
        
        if not pending_uploads.exists():
            self.message_user(request, "No pending uploads to process", level=messages.INFO)
            return redirect(f'admin:{self.model._meta.app_label}_portfolioupload_changelist')
        
        processed_count = 0
        successful_count = 0
        
        for upload in pending_uploads:
            try:
                results = process_portfolio_upload(upload_id=upload.upload_id, auto_map=True)
                processed_count += 1
                if results.get('successful_uploads', 0) > 0:
                    successful_count += 1
            except Exception as e:
                processed_count += 1
                # Continue processing other uploads
                continue
        
        self.message_user(
            request,
            f"Processed {processed_count} uploads. {successful_count} completed successfully.",
            level=messages.SUCCESS if successful_count > 0 else messages.WARNING
        )
        
    except Exception as e:
        self.message_user(
            request,
            f"Error during bulk processing: {str(e)}",
            level=messages.ERROR
        )
    
    return redirect(f'admin:{self.model._meta.app_label}_portfolioupload_changelist')