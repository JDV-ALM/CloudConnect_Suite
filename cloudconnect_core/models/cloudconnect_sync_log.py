# -*- coding: utf-8 -*-

import logging
import json
from datetime import datetime, timedelta
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class CloudconnectSyncLog(models.Model):
    _name = 'cloudconnect.sync_log'
    _description = 'CloudConnect Synchronization Log'
    _rec_name = 'display_name'
    _order = 'sync_date desc, id desc'

    # Basic Information
    display_name = fields.Char(
        string='Display Name',
        compute='_compute_display_name',
        store=True
    )
    
    # Configuration References
    property_id = fields.Many2one(
        'cloudconnect.property',
        string='Property',
        required=True,
        ondelete='cascade',
        index=True
    )
    config_id = fields.Many2one(
        'cloudconnect.config',
        string='Configuration',
        related='property_id.config_id',
        store=True
    )
    
    # Sync Operation Details
    operation_type = fields.Selection([
        ('manual', 'Manual Sync'),
        ('automatic', 'Automatic Sync'),
        ('webhook', 'Webhook Event'),
        ('cron', 'Scheduled Job'),
        ('api_call', 'Direct API Call'),
        ('import', 'Data Import'),
        ('export', 'Data Export'),
    ], string='Operation Type', required=True, index=True)
    
    model_name = fields.Char(
        string='Model Name',
        required=True,
        index=True,
        help='Odoo model that was synchronized'
    )
    cloudbeds_id = fields.Char(
        string='Cloudbeds ID',
        index=True,
        help='ID of the object in Cloudbeds system'
    )
    odoo_record_id = fields.Integer(
        string='Odoo Record ID',
        help='ID of the corresponding record in Odoo'
    )
    
    # Status and Timing
    status = fields.Selection([
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('success', 'Success'),
        ('error', 'Error'),
        ('partial', 'Partial Success'),
        ('skipped', 'Skipped'),
        ('retry', 'Retry Scheduled'),
    ], string='Status', required=True, default='pending', index=True)
    
    sync_date = fields.Datetime(
        string='Sync Date',
        required=True,
        default=fields.Datetime.now,
        index=True
    )
    started_at = fields.Datetime(
        string='Started At',
        help='When the sync operation started'
    )
    completed_at = fields.Datetime(
        string='Completed At',
        help='When the sync operation completed'
    )
    duration_ms = fields.Integer(
        string='Duration (ms)',
        compute='_compute_duration',
        store=True,
        help='Duration of the sync operation in milliseconds'
    )
    
    # Error Handling
    error_message = fields.Text(
        string='Error Message',
        help='Detailed error message if sync failed'
    )
    error_code = fields.Char(
        string='Error Code',
        help='Error code from Cloudbeds API'
    )
    retry_count = fields.Integer(
        string='Retry Count',
        default=0,
        help='Number of retry attempts'
    )
    max_retries = fields.Integer(
        string='Max Retries',
        default=3,
        help='Maximum number of retry attempts'
    )
    next_retry_at = fields.Datetime(
        string='Next Retry At',
        help='When the next retry is scheduled'
    )
    
    # Request/Response Details
    request_id = fields.Char(
        string='Request ID',
        help='X-Request-ID for tracking with Cloudbeds support'
    )
    http_status_code = fields.Integer(
        string='HTTP Status Code',
        help='HTTP status code from API response'
    )
    api_endpoint = fields.Char(
        string='API Endpoint',
        help='Cloudbeds API endpoint that was called'
    )
    request_method = fields.Selection([
        ('GET', 'GET'),
        ('POST', 'POST'),
        ('PUT', 'PUT'),
        ('PATCH', 'PATCH'),
        ('DELETE', 'DELETE'),
    ], string='Request Method')
    
    # Data Payload (for debugging)
    request_data = fields.Text(
        string='Request Data',
        help='JSON data sent to Cloudbeds (for debugging)'
    )
    response_data = fields.Text(
        string='Response Data',
        help='JSON response from Cloudbeds (for debugging)'
    )
    
    # Webhook Specific
    webhook_id = fields.Many2one(
        'cloudconnect.webhook',
        string='Webhook',
        help='Webhook that triggered this sync (if applicable)'
    )
    event_type = fields.Char(
        string='Event Type',
        help='Type of webhook event (if applicable)'
    )
    event_data = fields.Text(
        string='Event Data',
        help='Original webhook event data'
    )
    
    # Batch Processing
    batch_id = fields.Char(
        string='Batch ID',
        index=True,
        help='Group multiple related sync operations'
    )
    batch_size = fields.Integer(
        string='Batch Size',
        help='Total number of records in this batch'
    )
    batch_sequence = fields.Integer(
        string='Batch Sequence',
        help='Position of this record in the batch'
    )
    
    # Additional Metadata
    user_id = fields.Many2one(
        'res.users',
        string='User',
        default=lambda self: self.env.user,
        help='User who initiated the sync operation'
    )
    source_system = fields.Selection([
        ('odoo', 'Odoo'),
        ('cloudbeds', 'Cloudbeds'),
        ('webhook', 'Webhook'),
        ('api', 'External API'),
    ], string='Source System', default='odoo')
    
    sync_direction = fields.Selection([
        ('import', 'Import (Cloudbeds → Odoo)'),
        ('export', 'Export (Odoo → Cloudbeds)'),
        ('bidirectional', 'Bidirectional'),
    ], string='Sync Direction', default='import')
    
    # Computed Fields
    is_retriable = fields.Boolean(
        string='Is Retriable',
        compute='_compute_is_retriable',
        help='Whether this sync operation can be retried'
    )
    status_color = fields.Integer(
        string='Status Color',
        compute='_compute_status_color'
    )
    
    @api.depends('operation_type', 'model_name', 'cloudbeds_id', 'status')
    def _compute_display_name(self):
        for log in self:
            parts = []
            if log.model_name:
                parts.append(log.model_name)
            if log.cloudbeds_id:
                parts.append(f"({log.cloudbeds_id})")
            if log.operation_type:
                parts.append(f"[{log.operation_type}]")
            if log.status:
                parts.append(f"- {log.status}")
            
            log.display_name = " ".join(parts) if parts else _("Sync Log")
    
    @api.depends('started_at', 'completed_at')
    def _compute_duration(self):
        for log in self:
            if log.started_at and log.completed_at:
                delta = log.completed_at - log.started_at
                log.duration_ms = int(delta.total_seconds() * 1000)
            else:
                log.duration_ms = 0
    
    @api.depends('status', 'retry_count', 'max_retries')
    def _compute_is_retriable(self):
        for log in self:
            log.is_retriable = (
                log.status == 'error' and 
                log.retry_count < log.max_retries and
                log.operation_type in ('automatic', 'webhook', 'api_call')
            )
    
    @api.depends('status')
    def _compute_status_color(self):
        color_map = {
            'pending': 4,    # Blue
            'processing': 5, # Yellow
            'success': 10,   # Green
            'error': 1,      # Red
            'partial': 3,    # Orange
            'skipped': 7,    # Gray
            'retry': 8,      # Purple
        }
        for log in self:
            log.status_color = color_map.get(log.status, 0)
    
    def mark_as_started(self):
        """Mark the sync operation as started."""
        self.ensure_one()
        self.write({
            'status': 'processing',
            'started_at': fields.Datetime.now()
        })
    
    def mark_as_success(self, response_data=None, odoo_record_id=None):
        """Mark the sync operation as successful."""
        self.ensure_one()
        vals = {
            'status': 'success',
            'completed_at': fields.Datetime.now(),
            'error_message': False,
            'error_code': False,
        }
        if response_data:
            vals['response_data'] = json.dumps(response_data) if isinstance(response_data, dict) else response_data
        if odoo_record_id:
            vals['odoo_record_id'] = odoo_record_id
        
        self.write(vals)
    
    def mark_as_error(self, error_message, error_code=None, http_status=None, response_data=None):
        """Mark the sync operation as failed."""
        self.ensure_one()
        vals = {
            'status': 'error',
            'completed_at': fields.Datetime.now(),
            'error_message': error_message,
        }
        if error_code:
            vals['error_code'] = error_code
        if http_status:
            vals['http_status_code'] = http_status
        if response_data:
            vals['response_data'] = json.dumps(response_data) if isinstance(response_data, dict) else response_data
        
        self.write(vals)
    
    def mark_as_partial(self, message, response_data=None):
        """Mark the sync operation as partially successful."""
        self.ensure_one()
        vals = {
            'status': 'partial',
            'completed_at': fields.Datetime.now(),
            'error_message': message,
        }
        if response_data:
            vals['response_data'] = json.dumps(response_data) if isinstance(response_data, dict) else response_data
        
        self.write(vals)
    
    def mark_as_skipped(self, reason):
        """Mark the sync operation as skipped."""
        self.ensure_one()
        self.write({
            'status': 'skipped',
            'completed_at': fields.Datetime.now(),
            'error_message': reason,
        })
    
    def schedule_retry(self, delay_minutes=None):
        """Schedule a retry for this sync operation."""
        self.ensure_one()
        if not self.is_retriable:
            return False
        
        if delay_minutes is None:
            # Exponential backoff: 1, 2, 4, 8, 16 minutes
            delay_minutes = 2 ** self.retry_count
        
        next_retry = datetime.now() + timedelta(minutes=delay_minutes)
        
        self.write({
            'status': 'retry',
            'retry_count': self.retry_count + 1,
            'next_retry_at': next_retry,
        })
        return True
    
    def retry_sync(self):
        """Retry the sync operation."""
        self.ensure_one()
        if not self.is_retriable:
            raise ValidationError(_("This sync operation cannot be retried"))
        
        # Reset status and timestamps
        self.write({
            'status': 'pending',
            'started_at': False,
            'completed_at': False,
            'next_retry_at': False,
        })
        
        # Trigger the appropriate sync based on operation type
        if self.operation_type == 'webhook' and self.webhook_id:
            # Re-process webhook event
            if self.event_data:
                event_data = json.loads(self.event_data)
                return self.webhook_id.process_webhook_event(event_data)
        else:
            # Trigger general sync for this model/record
            sync_manager = self.env['cloudconnect.sync.manager']
            return sync_manager.sync_record(
                self.model_name,
                self.cloudbeds_id,
                self.property_id.id
            )
        
        return False
    
    def get_related_record(self):
        """Get the related Odoo record if it exists."""
        self.ensure_one()
        if not self.model_name or not self.odoo_record_id:
            return False
        
        try:
            Model = self.env[self.model_name]
            return Model.browse(self.odoo_record_id).exists()
        except Exception:
            return False
    
    def action_view_related_record(self):
        """Action to view the related Odoo record."""
        self.ensure_one()
        record = self.get_related_record()
        if not record:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _("Record Not Found"),
                    'message': _("The related record could not be found"),
                    'type': 'warning',
                }
            }
        
        return {
            'name': _('Related Record'),
            'type': 'ir.actions.act_window',
            'res_model': self.model_name,
            'res_id': record.id,
            'view_mode': 'form',
            'target': 'current',
        }
    
    def action_retry_sync(self):
        """Action to retry the sync operation."""
        self.ensure_one()
        if self.retry_sync():
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _("Retry Started"),
                    'message': _("Sync retry has been initiated"),
                    'type': 'success',
                }
            }
        else:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _("Retry Failed"),
                    'message': _("Unable to retry this sync operation"),
                    'type': 'danger',
                }
            }
    
    def action_view_request_details(self):
        """Action to view detailed request/response data."""
        self.ensure_one()
        return {
            'name': _('Sync Details'),
            'type': 'ir.actions.act_window',
            'res_model': 'cloudconnect.sync_log',
            'res_id': self.id,
            'view_mode': 'form',
            'views': [(False, 'form')],
            'target': 'new',
            'context': {'show_details': True},
        }
    
    @api.model
    def cleanup_old_logs(self, days=30):
        """Cleanup old sync logs to prevent database bloat."""
        cutoff_date = datetime.now() - timedelta(days=days)
        old_logs = self.search([
            ('sync_date', '<', cutoff_date),
            ('status', 'in', ['success', 'skipped'])
        ])
        
        count = len(old_logs)
        old_logs.unlink()
        _logger.info(f"Cleaned up {count} old sync logs older than {days} days")
        return count
    
    @api.model
    def get_sync_statistics(self, property_id=None, days=7):
        """Get sync statistics for dashboard."""
        domain = [('sync_date', '>=', datetime.now() - timedelta(days=days))]
        if property_id:
            domain.append(('property_id', '=', property_id))
        
        logs = self.search(domain)
        
        stats = {
            'total': len(logs),
            'success': len(logs.filtered(lambda l: l.status == 'success')),
            'error': len(logs.filtered(lambda l: l.status == 'error')),
            'pending': len(logs.filtered(lambda l: l.status in ['pending', 'processing'])),
            'partial': len(logs.filtered(lambda l: l.status == 'partial')),
            'avg_duration': 0,
            'by_model': {},
            'by_operation': {},
            'recent_errors': [],
        }
        
        # Calculate success rate
        stats['success_rate'] = (stats['success'] / stats['total'] * 100) if stats['total'] > 0 else 0
        
        # Calculate average duration
        completed_logs = logs.filtered(lambda l: l.duration_ms > 0)
        if completed_logs:
            stats['avg_duration'] = sum(completed_logs.mapped('duration_ms')) / len(completed_logs)
        
        # Group by model
        for model in logs.mapped('model_name'):
            model_logs = logs.filtered(lambda l: l.model_name == model)
            stats['by_model'][model] = {
                'total': len(model_logs),
                'success': len(model_logs.filtered(lambda l: l.status == 'success')),
                'error': len(model_logs.filtered(lambda l: l.status == 'error')),
            }
        
        # Group by operation type
        for operation in logs.mapped('operation_type'):
            op_logs = logs.filtered(lambda l: l.operation_type == operation)
            stats['by_operation'][operation] = {
                'total': len(op_logs),
                'success': len(op_logs.filtered(lambda l: l.status == 'success')),
                'error': len(op_logs.filtered(lambda l: l.status == 'error')),
            }
        
        # Get recent errors
        error_logs = logs.filtered(lambda l: l.status == 'error').sorted('sync_date', reverse=True)[:5]
        stats['recent_errors'] = [{
            'id': log.id,
            'model': log.model_name,
            'cloudbeds_id': log.cloudbeds_id,
            'error': log.error_message,
            'date': log.sync_date,
        } for log in error_logs]
        
        return stats
    
    @api.model
    def process_retry_queue(self):
        """Process scheduled retries (called by cron)."""
        retry_logs = self.search([
            ('status', '=', 'retry'),
            ('next_retry_at', '<=', fields.Datetime.now()),
            ('retry_count', '<', self._fields['max_retries'].default),
        ])
        
        processed = 0
        for log in retry_logs:
            try:
                if log.retry_sync():
                    processed += 1
            except Exception as e:
                _logger.error(f"Failed to retry sync log {log.id}: {e}")
                log.mark_as_error(f"Retry failed: {e}")
        
        _logger.info(f"Processed {processed} retry operations")
        return processed
    
    @api.model
    def create_batch_logs(self, batch_id, operations):
        """Create multiple sync logs for batch operations."""
        log_vals = []
        for i, operation in enumerate(operations):
            vals = operation.copy()
            vals.update({
                'batch_id': batch_id,
                'batch_size': len(operations),
                'batch_sequence': i + 1,
            })
            log_vals.append(vals)
        
        return self.create(log_vals)
    
    @api.constrains('retry_count', 'max_retries')
    def _check_retry_limits(self):
        for log in self:
            if log.retry_count < 0:
                raise ValidationError(_("Retry count cannot be negative"))
            if log.max_retries < 0:
                raise ValidationError(_("Max retries cannot be negative"))