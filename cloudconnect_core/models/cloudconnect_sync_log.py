# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from datetime import datetime, timedelta
import json
import logging

_logger = logging.getLogger(__name__)


class CloudConnectSyncLog(models.Model):
    _name = 'cloudconnect.sync.log'
    _description = 'CloudConnect Synchronization Log'
    _order = 'sync_date desc'
    _rec_name = 'display_name'
    
    # Basic fields
    operation_type = fields.Selection([
        ('manual', 'Manual Sync'),
        ('scheduled', 'Scheduled Sync'),
        ('webhook', 'Webhook Triggered'),
        ('api_call', 'API Call'),
        ('token_refresh', 'Token Refresh'),
    ], string='Operation Type', required=True, index=True)
    
    model_name = fields.Char(
        string='Model',
        required=True,
        index=True,
        help='Odoo model that was synchronized'
    )
    
    action = fields.Selection([
        ('create', 'Create'),
        ('update', 'Update'),
        ('delete', 'Delete'),
        ('sync', 'Sync'),
        ('fetch', 'Fetch'),
    ], string='Action', required=True)
    
    cloudbeds_id = fields.Char(
        string='Cloudbeds ID',
        index=True,
        help='ID of the object in Cloudbeds'
    )
    
    odoo_id = fields.Integer(
        string='Odoo ID',
        help='ID of the object in Odoo'
    )
    
    status = fields.Selection([
        ('pending', 'Pending'),
        ('success', 'Success'),
        ('error', 'Error'),
        ('warning', 'Warning'),
    ], string='Status', required=True, default='pending', index=True)
    
    # Related records
    config_id = fields.Many2one(
        'cloudconnect.config',
        string='Configuration',
        required=True,
        ondelete='cascade'
    )
    
    property_id = fields.Many2one(
        'cloudconnect.property',
        string='Property',
        index=True
    )
    
    # Details
    error_message = fields.Text(
        string='Error Message'
    )
    
    warning_message = fields.Text(
        string='Warning Message'
    )
    
    request_data = fields.Text(
        string='Request Data',
        help='JSON data sent in the request'
    )
    
    response_data = fields.Text(
        string='Response Data',
        help='JSON data received in the response'
    )
    
    # API tracking
    request_id = fields.Char(
        string='X-Request-ID',
        index=True,
        help='Request ID for tracking with Cloudbeds support'
    )
    
    api_endpoint = fields.Char(
        string='API Endpoint',
        help='API endpoint that was called'
    )
    
    http_status = fields.Integer(
        string='HTTP Status Code'
    )
    
    # Timing
    sync_date = fields.Datetime(
        string='Sync Date',
        required=True,
        default=fields.Datetime.now,
        index=True
    )
    
    duration = fields.Float(
        string='Duration (sec)',
        help='Time taken to complete the operation'
    )
    
    # Retry information
    retry_count = fields.Integer(
        string='Retry Count',
        default=0
    )
    
    max_retries = fields.Integer(
        string='Max Retries',
        default=3
    )
    
    next_retry = fields.Datetime(
        string='Next Retry'
    )
    
    # Display
    display_name = fields.Char(
        string='Display Name',
        compute='_compute_display_name',
        store=True
    )
    
    # Summary for dashboard
    summary = fields.Text(
        string='Summary',
        compute='_compute_summary'
    )
    
    @api.depends('model_name', 'action', 'sync_date', 'status')
    def _compute_display_name(self):
        """Compute display name for log entry."""
        for record in self:
            date_str = fields.Datetime.to_string(record.sync_date)[:19]
            status_icon = {
                'success': '✓',
                'error': '✗',
                'warning': '⚠',
                'pending': '○'
            }.get(record.status, '')
            
            record.display_name = f"{status_icon} {record.model_name} - {record.action} - {date_str}"
    
    @api.depends('status', 'error_message', 'warning_message', 'model_name', 'action')
    def _compute_summary(self):
        """Compute summary for dashboard display."""
        for record in self:
            if record.status == 'success':
                record.summary = _("Successfully %s %s") % (record.action, record.model_name)
            elif record.status == 'error':
                record.summary = record.error_message or _("Error during %s") % record.action
            elif record.status == 'warning':
                record.summary = record.warning_message or _("Warning during %s") % record.action
            else:
                record.summary = _("Pending %s for %s") % (record.action, record.model_name)
    
    @api.model
    def create_log(self, operation_type, model_name, action, config_id, **kwargs):
        """Helper method to create a sync log entry."""
        vals = {
            'operation_type': operation_type,
            'model_name': model_name,
            'action': action,
            'config_id': config_id,
            'sync_date': fields.Datetime.now(),
        }
        vals.update(kwargs)
        
        return self.create(vals)
    
    def mark_success(self, response_data=None, duration=None):
        """Mark log entry as successful."""
        self.ensure_one()
        vals = {
            'status': 'success',
            'duration': duration,
        }
        
        if response_data:
            if isinstance(response_data, dict):
                vals['response_data'] = json.dumps(response_data, indent=2)
            else:
                vals['response_data'] = str(response_data)
        
        self.write(vals)
    
    def mark_error(self, error_message, http_status=None, response_data=None):
        """Mark log entry as error."""
        self.ensure_one()
        vals = {
            'status': 'error',
            'error_message': error_message,
        }
        
        if http_status:
            vals['http_status'] = http_status
        
        if response_data:
            if isinstance(response_data, dict):
                vals['response_data'] = json.dumps(response_data, indent=2)
            else:
                vals['response_data'] = str(response_data)
        
        # Calculate next retry time if retries remaining
        if self.retry_count < self.max_retries:
            # Exponential backoff: 1min, 2min, 4min...
            wait_minutes = 2 ** self.retry_count
            vals['next_retry'] = fields.Datetime.now() + timedelta(minutes=wait_minutes)
        
        self.write(vals)
    
    def mark_warning(self, warning_message):
        """Mark log entry with warning."""
        self.ensure_one()
        self.write({
            'status': 'warning',
            'warning_message': warning_message,
        })
    
    def can_retry(self):
        """Check if this operation can be retried."""
        self.ensure_one()
        return (
            self.status == 'error' and
            self.retry_count < self.max_retries and
            self.next_retry and
            fields.Datetime.now() >= self.next_retry
        )
    
    def retry_operation(self):
        """Retry the failed operation."""
        self.ensure_one()
        
        if not self.can_retry():
            return False
        
        # Increment retry count
        self.retry_count += 1
        
        # Create new log entry for retry
        retry_log = self.copy({
            'operation_type': self.operation_type,
            'status': 'pending',
            'retry_count': self.retry_count,
            'error_message': False,
            'response_data': False,
            'sync_date': fields.Datetime.now(),
        })
        
        # Trigger the retry through sync manager
        sync_manager = self.env['cloudconnect.sync.manager']
        return sync_manager.retry_operation(retry_log)
    
    @api.model
    def _cron_cleanup_old_logs(self):
        """Cron job to clean up old log entries."""
        # Get retention period from config
        ICP = self.env['ir.config_parameter'].sudo()
        retention_days = int(ICP.get_param('cloudconnect.log_retention_days', '30'))
        
        # Calculate cutoff date
        cutoff_date = fields.Datetime.now() - timedelta(days=retention_days)
        
        # Find old logs
        old_logs = self.search([
            ('sync_date', '<', cutoff_date),
            ('status', 'in', ['success', 'error']),  # Keep pending logs
        ])
        
        # Log deletion
        if old_logs:
            _logger.info(f"Deleting {len(old_logs)} old sync logs")
            old_logs.unlink()
    
    @api.model
    def _cron_retry_failed_operations(self):
        """Cron job to retry failed operations."""
        # Find operations ready for retry
        failed_logs = self.search([
            ('status', '=', 'error'),
            ('retry_count', '<', 3),
            ('next_retry', '<=', fields.Datetime.now()),
        ])
        
        for log in failed_logs:
            try:
                log.retry_operation()
            except Exception as e:
                _logger.error(f"Error retrying operation {log.id}: {str(e)}")
    
    def action_view_details(self):
        """Action to view detailed log information."""
        self.ensure_one()
        
        # Format JSON data for display
        request_formatted = False
        response_formatted = False
        
        if self.request_data:
            try:
                request_formatted = json.dumps(
                    json.loads(self.request_data),
                    indent=2
                )
            except:
                request_formatted = self.request_data
        
        if self.response_data:
            try:
                response_formatted = json.dumps(
                    json.loads(self.response_data),
                    indent=2
                )
            except:
                response_formatted = self.response_data
        
        return {
            'type': 'ir.actions.act_window',
            'name': _('Sync Log Details'),
            'res_model': 'cloudconnect.sync.log',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'form_view_initial_mode': 'readonly',
                'request_formatted': request_formatted,
                'response_formatted': response_formatted,
            }
        }
    
    @api.model
    def get_dashboard_stats(self, hours=24):
        """Get statistics for dashboard display."""
        since = fields.Datetime.now() - timedelta(hours=hours)
        
        logs = self.search([('sync_date', '>=', since)])
        
        stats = {
            'total': len(logs),
            'success': len(logs.filtered(lambda l: l.status == 'success')),
            'error': len(logs.filtered(lambda l: l.status == 'error')),
            'warning': len(logs.filtered(lambda l: l.status == 'warning')),
            'pending': len(logs.filtered(lambda l: l.status == 'pending')),
            'by_model': {},
            'recent_errors': [],
        }
        
        # Count by model
        for log in logs:
            if log.model_name not in stats['by_model']:
                stats['by_model'][log.model_name] = {
                    'total': 0,
                    'success': 0,
                    'error': 0,
                }
            
            stats['by_model'][log.model_name]['total'] += 1
            if log.status == 'success':
                stats['by_model'][log.model_name]['success'] += 1
            elif log.status == 'error':
                stats['by_model'][log.model_name]['error'] += 1
        
        # Recent errors
        error_logs = logs.filtered(lambda l: l.status == 'error').sorted('sync_date', reverse=True)[:5]
        for log in error_logs:
            stats['recent_errors'].append({
                'id': log.id,
                'model': log.model_name,
                'action': log.action,
                'error': log.error_message or 'Unknown error',
                'date': log.sync_date,
            })
        
        return stats