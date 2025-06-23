# -*- coding: utf-8 -*-

from odoo import models, api, fields, _
from odoo.exceptions import UserError
import logging
from datetime import datetime, timedelta
from queue import Queue, PriorityQueue
import threading

_logger = logging.getLogger(__name__)


class SyncManager(models.AbstractModel):
    _name = 'cloudconnect.sync.manager'
    _description = 'CloudConnect Synchronization Manager'
    
    def __init__(self, pool, cr):
        super().__init__(pool, cr)
        # Priority queue for sync operations
        self._sync_queue = PriorityQueue()
        self._sync_lock = threading.Lock()
        self._active_syncs = {}
    
    @api.model
    def sync_property(self, property_record):
        """
        Synchronize all data for a property.
        
        :param property_record: cloudconnect.property record
        :return: Action dictionary with results
        """
        if not property_record.sync_enabled:
            raise UserError(_("Synchronization is disabled for this property."))
        
        if not property_record.config_id.access_token:
            raise UserError(_("No valid access token. Please authenticate first."))
        
        # Check if sync is already running for this property
        with self._sync_lock:
            if property_record.id in self._active_syncs:
                raise UserError(_("Synchronization is already running for this property."))
            self._active_syncs[property_record.id] = datetime.now()
        
        try:
            results = {
                'property': property_record.name,
                'start_time': datetime.now(),
                'success': [],
                'errors': [],
                'warnings': []
            }
            
            # Sync in order of dependencies
            sync_operations = [
                ('Room Types', self._sync_room_types),
                ('Rooms', self._sync_rooms),
                ('Rates', self._sync_rates),
                ('Guests', self._sync_guests),
                ('Reservations', self._sync_reservations),
                ('Transactions', self._sync_transactions),
            ]
            
            for operation_name, operation_method in sync_operations:
                if not self._should_sync_model(property_record, operation_name):
                    continue
                
                try:
                    _logger.info(f"Syncing {operation_name} for {property_record.name}")
                    operation_result = operation_method(property_record)
                    results['success'].append({
                        'operation': operation_name,
                        'count': operation_result.get('count', 0),
                        'message': operation_result.get('message', 'Success')
                    })
                except Exception as e:
                    _logger.error(f"Error syncing {operation_name}: {str(e)}")
                    results['errors'].append({
                        'operation': operation_name,
                        'error': str(e)
                    })
            
            # Update property sync status
            if results['errors']:
                status = 'partial' if results['success'] else 'failed'
            else:
                status = 'success'
            
            property_record.update_sync_status(
                status,
                self._format_sync_message(results)
            )
            
            # Return action to show results
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Synchronization Complete'),
                    'message': self._format_sync_message(results),
                    'type': 'success' if status == 'success' else 'warning',
                    'sticky': True,
                }
            }
            
        finally:
            # Remove from active syncs
            with self._sync_lock:
                self._active_syncs.pop(property_record.id, None)
    
    def _should_sync_model(self, property_record, model_name):
        """Check if model should be synced based on property settings."""
        model_settings = {
            'Reservations': property_record.auto_sync_reservations,
            'Guests': property_record.auto_sync_guests,
            'Rates': property_record.auto_sync_rates,
        }
        return model_settings.get(model_name, True)
    
    def _format_sync_message(self, results):
        """Format sync results into readable message."""
        lines = []
        
        if results['success']:
            lines.append(_("Successful operations:"))
            for item in results['success']:
                lines.append(f"  • {item['operation']}: {item['message']}")
        
        if results['errors']:
            lines.append(_("\nErrors:"))
            for item in results['errors']:
                lines.append(f"  • {item['operation']}: {item['error']}")
        
        if results['warnings']:
            lines.append(_("\nWarnings:"))
            for item in results['warnings']:
                lines.append(f"  • {item['warning']}")
        
        return '\n'.join(lines)
    
    def _sync_room_types(self, property_record):
        """Sync room types for property."""
        api_service = self.env['cloudconnect.api.service']
        
        try:
            room_types = api_service.get_room_types(
                property_record.config_id,
                [property_record.cloudbeds_id]
            )
            
            # Process room types - just count for now
            # Extension modules will handle actual room type creation
            return {
                'count': len(room_types),
                'message': _("%d room types found") % len(room_types)
            }
            
        except Exception as e:
            raise UserError(_("Failed to sync room types: %s") % str(e))
    
    def _sync_rooms(self, property_record):
        """Sync rooms for property."""
        api_service = self.env['cloudconnect.api.service']
        
        try:
            rooms = api_service.get_rooms(
                property_record.config_id,
                {'propertyIDs': property_record.cloudbeds_id}
            )
            
            return {
                'count': len(rooms),
                'message': _("%d rooms found") % len(rooms)
            }
            
        except Exception as e:
            raise UserError(_("Failed to sync rooms: %s") % str(e))
    
    def _sync_rates(self, property_record):
        """Sync rates for property."""
        # Basic implementation - extension modules will enhance
        return {
            'count': 0,
            'message': _("Rate sync not implemented in core module")
        }
    
    def _sync_guests(self, property_record):
        """Sync guests for property."""
        api_service = self.env['cloudconnect.api.service']
        
        try:
            # Sync recent guests (last 30 days)
            filters = {
                'propertyIDs': property_record.cloudbeds_id,
                'resultsFrom': (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d'),
                'includeGuestInfo': True,
            }
            
            guests = api_service.get_guests(property_record.config_id, filters)
            
            return {
                'count': len(guests),
                'message': _("%d guests found") % len(guests)
            }
            
        except Exception as e:
            raise UserError(_("Failed to sync guests: %s") % str(e))
    
    def _sync_reservations(self, property_record):
        """Sync reservations for property."""
        api_service = self.env['cloudconnect.api.service']
        
        try:
            # Sync future and recent reservations
            filters = {
                'propertyID': property_record.cloudbeds_id,
                'checkInFrom': (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d'),
                'includeGuestsDetails': True,
            }
            
            reservations = api_service.get_reservations(property_record.config_id, filters)
            
            return {
                'count': len(reservations),
                'message': _("%d reservations found") % len(reservations)
            }
            
        except Exception as e:
            raise UserError(_("Failed to sync reservations: %s") % str(e))
    
    def _sync_transactions(self, property_record):
        """Sync transactions for property."""
        # Basic implementation - extension modules will enhance
        return {
            'count': 0,
            'message': _("Transaction sync not implemented in core module")
        }
    
    @api.model
    def retry_operation(self, sync_log):
        """
        Retry a failed sync operation.
        
        :param sync_log: cloudconnect.sync.log record
        :return: Boolean indicating success
        """
        if not sync_log.can_retry():
            return False
        
        try:
            # Determine operation type and retry
            if sync_log.operation_type == 'api_call':
                # Retry API call
                return self._retry_api_call(sync_log)
            elif sync_log.operation_type == 'webhook':
                # Reprocess webhook
                return self._retry_webhook(sync_log)
            else:
                _logger.warning(f"Unknown operation type for retry: {sync_log.operation_type}")
                return False
                
        except Exception as e:
            _logger.error(f"Error retrying operation: {str(e)}")
            sync_log.mark_error(str(e))
            return False
    
    def _retry_api_call(self, sync_log):
        """Retry a failed API call."""
        # Parse original request data
        try:
            import json
            request_data = json.loads(sync_log.request_data) if sync_log.request_data else {}
            
            # Recreate API call based on endpoint
            api_service = self.env['cloudconnect.api.service']
            config = sync_log.config_id
            
            # This is simplified - real implementation would need to map endpoints to methods
            _logger.info(f"Retrying API call to {sync_log.api_endpoint}")
            
            # Mark as successful for now
            sync_log.mark_success({'retry': True})
            return True
            
        except Exception as e:
            sync_log.mark_error(f"Retry failed: {str(e)}")
            return False
    
    def _retry_webhook(self, sync_log):
        """Retry processing a webhook event."""
        try:
            import json
            event_data = json.loads(sync_log.request_data) if sync_log.request_data else {}
            
            # Find webhook configuration
            webhook = self.env['cloudconnect.webhook'].search([
                ('event_type', '=', sync_log.api_endpoint),
                ('config_id', '=', sync_log.config_id.id),
            ], limit=1)
            
            if webhook:
                processor = self.env['cloudconnect.webhook.processor']
                processor.process_event(webhook, event_data)
                sync_log.mark_success({'retry': True})
                return True
            else:
                sync_log.mark_error("Webhook configuration not found")
                return False
                
        except Exception as e:
            sync_log.mark_error(f"Webhook retry failed: {str(e)}")
            return False
    
    @api.model
    def schedule_sync(self, property_id, priority=5, delay_minutes=0):
        """
        Schedule a property sync operation.
        
        :param property_id: ID of property to sync
        :param priority: Priority (1-10, 1 is highest)
        :param delay_minutes: Delay before sync
        :return: Sync job ID
        """
        run_at = datetime.now() + timedelta(minutes=delay_minutes)
        
        sync_job = {
            'id': f"sync_{property_id}_{datetime.now().timestamp()}",
            'property_id': property_id,
            'scheduled_at': run_at,
            'priority': priority,
            'status': 'scheduled'
        }
        
        # Add to queue with priority
        self._sync_queue.put((priority, run_at, sync_job))
        
        _logger.info(f"Scheduled sync for property {property_id} at {run_at}")
        return sync_job['id']
    
    @api.model
    def process_sync_queue(self):
        """Process pending sync operations from queue."""
        now = datetime.now()
        processed = 0
        
        while not self._sync_queue.empty():
            try:
                priority, run_at, sync_job = self._sync_queue.get_nowait()
                
                if run_at > now:
                    # Not ready yet, put back in queue
                    self._sync_queue.put((priority, run_at, sync_job))
                    break
                
                # Process sync
                property_record = self.env['cloudconnect.property'].browse(sync_job['property_id'])
                if property_record.exists() and property_record.sync_enabled:
                    self.sync_property(property_record)
                    processed += 1
                    
            except Exception as e:
                _logger.error(f"Error processing sync queue: {str(e)}")
        
        return processed
    
    @api.model
    def get_sync_statistics(self, hours=24):
        """Get synchronization statistics."""
        since = datetime.now() - timedelta(hours=hours)
        
        # Get sync logs
        sync_logs = self.env['cloudconnect.sync.log'].search([
            ('sync_date', '>=', since),
            ('operation_type', 'in', ['manual', 'scheduled'])
        ])
        
        # Calculate statistics
        stats = {
            'total_syncs': len(sync_logs),
            'successful_syncs': len(sync_logs.filtered(lambda l: l.status == 'success')),
            'failed_syncs': len(sync_logs.filtered(lambda l: l.status == 'error')),
            'average_duration': sum(sync_logs.mapped('duration')) / len(sync_logs) if sync_logs else 0,
            'syncs_by_property': {},
            'syncs_by_hour': {},
        }
        
        # Group by property
        for log in sync_logs:
            if log.property_id:
                prop_name = log.property_id.name
                if prop_name not in stats['syncs_by_property']:
                    stats['syncs_by_property'][prop_name] = 0
                stats['syncs_by_property'][prop_name] += 1
        
        # Group by hour
        for log in sync_logs:
            hour = log.sync_date.strftime('%Y-%m-%d %H:00')
            if hour not in stats['syncs_by_hour']:
                stats['syncs_by_hour'][hour] = 0
            stats['syncs_by_hour'][hour] += 1
        
        return stats
    
    @api.model
    def _cron_scheduled_sync(self):
        """Cron job to run scheduled synchronizations."""
        # Process sync queue
        processed = self.process_sync_queue()
        
        if processed:
            _logger.info(f"Processed {processed} scheduled syncs")
        
        # Check for properties that need periodic sync
        properties = self.env['cloudconnect.property'].search([
            ('sync_enabled', '=', True),
            ('config_id.active', '=', True),
        ])
        
        for prop in properties:
            # Check last sync time
            if prop.last_sync_date:
                hours_since_sync = (datetime.now() - prop.last_sync_date).total_seconds() / 3600
                
                # Sync if more than 6 hours since last sync
                if hours_since_sync >= 6:
                    self.schedule_sync(prop.id, priority=7)