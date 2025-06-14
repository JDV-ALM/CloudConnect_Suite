# -*- coding: utf-8 -*-

import logging
import uuid
from datetime import datetime, timedelta
from odoo import models, api, fields, _
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class SyncManager(models.AbstractModel):
    _name = 'cloudconnect.sync.manager'
    _description = 'CloudConnect Sync Manager'

    @api.model
    def sync_property(self, property_id, sync_type='manual', modules=None):
        """Sync all data for a specific property."""
        try:
            property_obj = self.env['cloudconnect.property'].browse(property_id)
            if not property_obj.exists():
                raise ValidationError(f"Property {property_id} not found")
            
            if not property_obj.sync_enabled:
                _logger.info(f"Sync disabled for property {property_obj.name}")
                return {'success': False, 'message': 'Sync disabled for this property'}
            
            batch_id = f"sync_{property_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{str(uuid.uuid4())[:8]}"
            
            _logger.info(f"Starting sync for property {property_obj.name} (batch: {batch_id})")
            
            # Mark sync as started
            property_obj.update_sync_status('pending')
            
            results = {
                'property_id': property_id,
                'property_name': property_obj.name,
                'batch_id': batch_id,
                'sync_type': sync_type,
                'started_at': datetime.now(),
                'modules': {},
                'total_success': 0,
                'total_errors': 0,
                'total_skipped': 0,
            }
            
            # Define sync modules in order of dependency
            sync_modules = modules or [
                'properties',  # Core property data
                'room_types',  # Room types and rooms
                'guests',      # Guests (if cloudconnect_guests installed)
                'reservations', # Reservations (if cloudconnect_reservations installed)
                'payments',    # Payments (if cloudconnect_payments installed)
                'items',       # Items/products (if cloudconnect_items installed)
            ]
            
            # Execute sync modules
            for module in sync_modules:
                try:
                    module_result = self._sync_module(property_obj, module, batch_id, sync_type)
                    results['modules'][module] = module_result
                    results['total_success'] += module_result.get('success_count', 0)
                    results['total_errors'] += module_result.get('error_count', 0)
                    results['total_skipped'] += module_result.get('skipped_count', 0)
                    
                except Exception as e:
                    _logger.error(f"Module sync failed for {module}: {e}")
                    results['modules'][module] = {
                        'success': False,
                        'error': str(e),
                        'success_count': 0,
                        'error_count': 1,
                        'skipped_count': 0,
                    }
                    results['total_errors'] += 1
            
            # Update final sync status
            results['completed_at'] = datetime.now()
            results['duration'] = (results['completed_at'] - results['started_at']).total_seconds()
            
            if results['total_errors'] == 0:
                property_obj.update_sync_status('success')
                results['overall_status'] = 'success'
            elif results['total_success'] > 0:
                property_obj.update_sync_status('partial', f"{results['total_errors']} errors occurred")
                results['overall_status'] = 'partial'
            else:
                property_obj.update_sync_status('error', f"All modules failed")
                results['overall_status'] = 'error'
            
            _logger.info(f"Sync completed for property {property_obj.name}: {results['overall_status']}")
            return results
            
        except Exception as e:
            _logger.error(f"Property sync failed: {e}")
            if 'property_obj' in locals():
                property_obj.update_sync_status('error', str(e))
            raise UserError(f"Sync failed: {e}")
    
    def _sync_module(self, property_obj, module_name, batch_id, sync_type):
        """Sync a specific module for a property."""
        _logger.info(f"Syncing module {module_name} for property {property_obj.name}")
        
        try:
            # Get the appropriate sync method
            sync_method = getattr(self, f'_sync_{module_name}', None)
            if not sync_method:
                _logger.warning(f"No sync method found for module {module_name}")
                return {
                    'success': False,
                    'error': f"Module {module_name} not implemented",
                    'success_count': 0,
                    'error_count': 0,
                    'skipped_count': 1,
                }
            
            # Execute the sync method
            result = sync_method(property_obj, batch_id, sync_type)
            
            return result
            
        except Exception as e:
            _logger.error(f"Module {module_name} sync failed: {e}")
            return {
                'success': False,
                'error': str(e),
                'success_count': 0,
                'error_count': 1,
                'skipped_count': 0,
            }
    
    def _sync_properties(self, property_obj, batch_id, sync_type):
        """Sync basic property information."""
        try:
            api_service = self.env['cloudconnect.api.service']
            config = property_obj.config_id
            
            # Get hotel details from Cloudbeds
            hotel_data = api_service.get_hotel_details(config, property_obj.cloudbeds_id)
            
            if not hotel_data.get('success'):
                raise UserError("Failed to fetch hotel details from Cloudbeds")
            
            hotel_info = hotel_data.get('data', {})
            
            # Update property information
            update_vals = {}
            if hotel_info.get('propertyName'):
                update_vals['name'] = hotel_info['propertyName']
            if hotel_info.get('propertyCity'):
                update_vals['city'] = hotel_info['propertyCity']
            if hotel_info.get('propertyCountry'):
                country = self.env['res.country'].search([
                    ('code', '=', hotel_info['propertyCountry'].upper())
                ], limit=1)
                if country:
                    update_vals['country_id'] = country.id
            if hotel_info.get('propertyTimezone'):
                update_vals['timezone'] = hotel_info['propertyTimezone']
            if hotel_info.get('propertyPhone'):
                update_vals['phone'] = hotel_info['propertyPhone']
            if hotel_info.get('propertyEmail'):
                update_vals['email'] = hotel_info['propertyEmail']
            
            if update_vals:
                property_obj.write(update_vals)
            
            # Create sync log
            self.env['cloudconnect.sync_log'].create({
                'property_id': property_obj.id,
                'operation_type': sync_type,
                'model_name': 'cloudconnect.property',
                'cloudbeds_id': property_obj.cloudbeds_id,
                'status': 'success',
                'batch_id': batch_id,
                'sync_date': datetime.now(),
                'odoo_record_id': property_obj.id,
            })
            
            return {
                'success': True,
                'success_count': 1,
                'error_count': 0,
                'skipped_count': 0,
                'message': 'Property information updated'
            }
            
        except Exception as e:
            # Create error log
            self.env['cloudconnect.sync_log'].create({
                'property_id': property_obj.id,
                'operation_type': sync_type,
                'model_name': 'cloudconnect.property',
                'cloudbeds_id': property_obj.cloudbeds_id,
                'status': 'error',
                'error_message': str(e),
                'batch_id': batch_id,
                'sync_date': datetime.now(),
            })
            
            return {
                'success': False,
                'error': str(e),
                'success_count': 0,
                'error_count': 1,
                'skipped_count': 0,
            }
    
    def _sync_room_types(self, property_obj, batch_id, sync_type):
        """Sync room types and rooms."""
        try:
            api_service = self.env['cloudconnect.api.service']
            config = property_obj.config_id
            
            # Get room types
            room_types_data = api_service.get_room_types(config, property_obj.cloudbeds_id)
            
            if not room_types_data.get('success'):
                raise UserError("Failed to fetch room types from Cloudbeds")
            
            room_types = room_types_data.get('data', [])
            success_count = 0
            error_count = 0
            
            for room_type_data in room_types:
                try:
                    # This would be implemented in cloudconnect_reservations module
                    # For now, just log the data
                    
                    self.env['cloudconnect.sync_log'].create({
                        'property_id': property_obj.id,
                        'operation_type': sync_type,
                        'model_name': 'room.type',
                        'cloudbeds_id': str(room_type_data.get('roomTypeID', 'unknown')),
                        'status': 'success',
                        'batch_id': batch_id,
                        'sync_date': datetime.now(),
                        'error_message': f"Room type: {room_type_data.get('roomTypeName', 'Unknown')}",
                    })
                    
                    success_count += 1
                    
                except Exception as e:
                    _logger.error(f"Error syncing room type {room_type_data.get('roomTypeID')}: {e}")
                    
                    self.env['cloudconnect.sync_log'].create({
                        'property_id': property_obj.id,
                        'operation_type': sync_type,
                        'model_name': 'room.type',
                        'cloudbeds_id': str(room_type_data.get('roomTypeID', 'unknown')),
                        'status': 'error',
                        'error_message': str(e),
                        'batch_id': batch_id,
                        'sync_date': datetime.now(),
                    })
                    
                    error_count += 1
            
            return {
                'success': error_count == 0,
                'success_count': success_count,
                'error_count': error_count,
                'skipped_count': 0,
                'message': f"Synced {success_count} room types"
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'success_count': 0,
                'error_count': 1,
                'skipped_count': 0,
            }
    
    def _sync_guests(self, property_obj, batch_id, sync_type):
        """Sync guests (placeholder - will be implemented in cloudconnect_guests)."""
        # Check if guests module is installed
        if 'cloudconnect_guests' not in self.env.registry._init_modules:
            return {
                'success': True,
                'success_count': 0,
                'error_count': 0,
                'skipped_count': 1,
                'message': 'Guests module not installed'
            }
        
        # This will be implemented in cloudconnect_guests module
        _logger.info(f"Guests sync placeholder for property {property_obj.name}")
        return {
            'success': True,
            'success_count': 0,
            'error_count': 0,
            'skipped_count': 1,
            'message': 'Guests sync not yet implemented'
        }
    
    def _sync_reservations(self, property_obj, batch_id, sync_type):
        """Sync reservations (placeholder - will be implemented in cloudconnect_reservations)."""
        # Check if reservations module is installed
        if 'cloudconnect_reservations' not in self.env.registry._init_modules:
            return {
                'success': True,
                'success_count': 0,
                'error_count': 0,
                'skipped_count': 1,
                'message': 'Reservations module not installed'
            }
        
        # This will be implemented in cloudconnect_reservations module
        _logger.info(f"Reservations sync placeholder for property {property_obj.name}")
        return {
            'success': True,
            'success_count': 0,
            'error_count': 0,
            'skipped_count': 1,
            'message': 'Reservations sync not yet implemented'
        }
    
    def _sync_payments(self, property_obj, batch_id, sync_type):
        """Sync payments (placeholder - will be implemented in cloudconnect_payments)."""
        # Check if payments module is installed
        if 'cloudconnect_payments' not in self.env.registry._init_modules:
            return {
                'success': True,
                'success_count': 0,
                'error_count': 0,
                'skipped_count': 1,
                'message': 'Payments module not installed'
            }
        
        # This will be implemented in cloudconnect_payments module
        _logger.info(f"Payments sync placeholder for property {property_obj.name}")
        return {
            'success': True,
            'success_count': 0,
            'error_count': 0,
            'skipped_count': 1,
            'message': 'Payments sync not yet implemented'
        }
    
    def _sync_items(self, property_obj, batch_id, sync_type):
        """Sync items/products (placeholder - will be implemented in cloudconnect_items)."""
        # Check if items module is installed
        if 'cloudconnect_items' not in self.env.registry._init_modules:
            return {
                'success': True,
                'success_count': 0,
                'error_count': 0,
                'skipped_count': 1,
                'message': 'Items module not installed'
            }
        
        # This will be implemented in cloudconnect_items module
        _logger.info(f"Items sync placeholder for property {property_obj.name}")
        return {
            'success': True,
            'success_count': 0,
            'error_count': 0,
            'skipped_count': 1,
            'message': 'Items sync not yet implemented'
        }
    
    @api.model
    def sync_all_properties(self, config_id=None, sync_type='automatic'):
        """Sync all enabled properties."""
        domain = [('sync_enabled', '=', True)]
        if config_id:
            domain.append(('config_id', '=', config_id))
        
        properties = self.env['cloudconnect.property'].search(domain)
        
        results = {
            'total_properties': len(properties),
            'successful': 0,
            'failed': 0,
            'properties': {}
        }
        
        for property_obj in properties:
            try:
                result = self.sync_property(property_obj.id, sync_type)
                results['properties'][property_obj.id] = result
                
                if result.get('overall_status') == 'success':
                    results['successful'] += 1
                else:
                    results['failed'] += 1
                    
            except Exception as e:
                _logger.error(f"Failed to sync property {property_obj.name}: {e}")
                results['properties'][property_obj.id] = {
                    'success': False,
                    'error': str(e)
                }
                results['failed'] += 1
        
        return results
    
    @api.model
    def sync_record(self, model_name, cloudbeds_id, property_id):
        """Sync a specific record."""
        try:
            property_obj = self.env['cloudconnect.property'].browse(property_id)
            if not property_obj.exists():
                raise ValidationError(f"Property {property_id} not found")
            
            # Create sync log
            sync_log = self.env['cloudconnect.sync_log'].create({
                'property_id': property_id,
                'operation_type': 'manual',
                'model_name': model_name,
                'cloudbeds_id': str(cloudbeds_id),
                'status': 'processing',
                'sync_date': datetime.now(),
            })
            
            sync_log.mark_as_started()
            
            # Get the appropriate sync method based on model
            if model_name == 'sale.order':
                result = self._sync_single_reservation(property_obj, cloudbeds_id, sync_log)
            elif model_name == 'res.partner':
                result = self._sync_single_guest(property_obj, cloudbeds_id, sync_log)
            elif model_name == 'account.payment':
                result = self._sync_single_payment(property_obj, cloudbeds_id, sync_log)
            else:
                sync_log.mark_as_error(f"Unsupported model: {model_name}")
                return False
            
            return result
            
        except Exception as e:
            _logger.error(f"Record sync failed: {e}")
            if 'sync_log' in locals():
                sync_log.mark_as_error(str(e))
            return False
    
    def _sync_single_reservation(self, property_obj, reservation_id, sync_log):
        """Sync a single reservation."""
        try:
            # This will be implemented in cloudconnect_reservations module
            sync_log.mark_as_success({'message': 'Reservation sync not yet implemented'})
            return True
        except Exception as e:
            sync_log.mark_as_error(str(e))
            return False
    
    def _sync_single_guest(self, property_obj, guest_id, sync_log):
        """Sync a single guest."""
        try:
            # This will be implemented in cloudconnect_guests module
            sync_log.mark_as_success({'message': 'Guest sync not yet implemented'})
            return True
        except Exception as e:
            sync_log.mark_as_error(str(e))
            return False
    
    def _sync_single_payment(self, property_obj, payment_id, sync_log):
        """Sync a single payment."""
        try:
            # This will be implemented in cloudconnect_payments module
            sync_log.mark_as_success({'message': 'Payment sync not yet implemented'})
            return True
        except Exception as e:
            sync_log.mark_as_error(str(e))
            return False
    
    @api.model
    def schedule_sync(self, property_id, delay_minutes=0):
        """Schedule a sync operation."""
        if delay_minutes > 0:
            # Use queue_job if available for delayed execution
            if 'queue.job' in self.env:
                eta = datetime.now() + timedelta(minutes=delay_minutes)
                job = self.with_delay(eta=eta).sync_property(property_id, 'scheduled')
                _logger.info(f"Sync scheduled for property {property_id} in {delay_minutes} minutes: {job.uuid}")
                return {'success': True, 'job_id': job.uuid}
            else:
                # Fallback to immediate execution
                _logger.warning("queue_job not available, executing sync immediately")
                return self.sync_property(property_id, 'scheduled')
        else:
            # Immediate execution
            return self.sync_property(property_id, 'scheduled')
    
    @api.model
    def get_sync_status(self, property_id=None):
        """Get current sync status for properties."""
        domain = []
        if property_id:
            domain.append(('id', '=', property_id))
        
        properties = self.env['cloudconnect.property'].search(domain)
        
        status_data = {}
        for prop in properties:
            # Get recent sync logs
            recent_logs = self.env['cloudconnect.sync_log'].search([
                ('property_id', '=', prop.id),
                ('sync_date', '>=', datetime.now() - timedelta(hours=24))
            ], order='sync_date desc', limit=10)
            
            # Get statistics
            stats = self.env['cloudconnect.sync_log'].get_sync_statistics(prop.id, days=7)
            
            status_data[prop.id] = {
                'property_name': prop.name,
                'sync_enabled': prop.sync_enabled,
                'last_sync_date': prop.last_sync_date,
                'last_sync_status': prop.last_sync_status,
                'sync_error_count': prop.sync_error_count,
                'last_sync_error': prop.last_sync_error,
                'recent_logs': [{
                    'id': log.id,
                    'operation_type': log.operation_type,
                    'model_name': log.model_name,
                    'status': log.status,
                    'sync_date': log.sync_date,
                    'error_message': log.error_message,
                } for log in recent_logs],
                'statistics': stats,
            }
        
        return status_data
    
    @api.model
    def cleanup_sync_data(self, days=30):
        """Clean up old sync logs and temporary data."""
        try:
            # Clean up old sync logs
            cleanup_count = self.env['cloudconnect.sync_log'].cleanup_old_logs(days)
            
            # Reset error counts for properties that haven't had errors recently
            cutoff_date = datetime.now() - timedelta(days=7)
            properties_to_reset = self.env['cloudconnect.property'].search([
                ('sync_error_count', '>', 0),
                ('last_sync_date', '<', cutoff_date),
                ('last_sync_status', '=', 'success')
            ])
            
            for prop in properties_to_reset:
                prop.reset_sync_errors()
            
            return {
                'success': True,
                'logs_cleaned': cleanup_count,
                'properties_reset': len(properties_to_reset)
            }
            
        except Exception as e:
            _logger.error(f"Cleanup failed: {e}")
            return {'success': False, 'error': str(e)}
    
    @api.model
    def force_resync(self, property_id, modules=None):
        """Force a complete resync of a property, ignoring timestamps."""
        try:
            property_obj = self.env['cloudconnect.property'].browse(property_id)
            if not property_obj.exists():
                raise ValidationError(f"Property {property_id} not found")
            
            # Reset sync status
            property_obj.reset_sync_errors()
            
            # Perform sync
            result = self.sync_property(property_id, 'manual', modules)
            
            return result
            
        except Exception as e:
            _logger.error(f"Force resync failed: {e}")
            raise UserError(f"Force resync failed: {e}")
    
    @api.model
    def get_sync_dependencies(self):
        """Get the dependency order for sync modules."""
        return {
            'properties': [],  # No dependencies
            'room_types': ['properties'],
            'guests': ['properties'],
            'reservations': ['properties', 'room_types', 'guests'],
            'payments': ['properties', 'reservations'],
            'items': ['properties', 'reservations'],
        }
    
    @api.model
    def validate_sync_dependencies(self, modules):
        """Validate that sync modules are in correct dependency order."""
        dependencies = self.get_sync_dependencies()
        available_modules = set()
        
        for module in modules:
            required_deps = dependencies.get(module, [])
            missing_deps = set(required_deps) - available_modules
            
            if missing_deps:
                raise ValidationError(
                    f"Module '{module}' requires {missing_deps} to be synced first"
                )
            
            available_modules.add(module)
        
        return True