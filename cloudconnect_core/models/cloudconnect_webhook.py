# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
import hashlib
import hmac
import secrets
import logging

_logger = logging.getLogger(__name__)


class CloudConnectWebhook(models.Model):
    _name = 'cloudconnect.webhook'
    _description = 'CloudConnect Webhook Configuration'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _rec_name = 'display_name'
    _order = 'event_type, property_id'
    
    config_id = fields.Many2one(
        'cloudconnect.config',
        string='Configuration',
        required=True,
        ondelete='cascade'
    )
    
    property_id = fields.Many2one(
        'cloudconnect.property',
        string='Property',
        domain="[('config_id', '=', config_id)]",
        help='Property this webhook applies to (optional, leave empty for all properties)'
    )
    
    event_type = fields.Selection([
        # Reservation events
        ('reservation/created', 'Reservation Created'),
        ('reservation/status_changed', 'Reservation Status Changed'),
        ('reservation/dates_changed', 'Reservation Dates Changed'),
        ('reservation/accommodation_status_changed', 'Room Status Changed'),
        ('reservation/accommodation_type_changed', 'Room Type Changed'),
        ('reservation/accommodation_changed', 'Room Assignment Changed'),
        ('reservation/deleted', 'Reservation Deleted'),
        ('reservation/notes_changed', 'Reservation Notes Changed'),
        ('reservation/custom_fields_changed', 'Reservation Custom Fields Changed'),
        ('reservation/invoice_requested', 'Invoice Requested'),
        ('reservation/invoice_void_requested', 'Invoice Void Requested'),
        
        # Guest events
        ('guest/created', 'Guest Created'),
        ('guest/assigned', 'Guest Assigned'),
        ('guest/removed', 'Guest Removed'),
        ('guest/details_changed', 'Guest Details Changed'),
        ('guest/accommodation_changed', 'Guest Room Changed'),
        
        # Payment events
        ('transaction/created', 'Transaction Created'),
        
        # Housekeeping events
        ('housekeeping/housekeeping_reservation_status_changed', 'Housekeeping Status Changed'),
        ('housekeeping/housekeeping_room_occupancy_status_changed', 'Room Occupancy Changed'),
        ('housekeeping/room_condition_changed', 'Room Condition Changed'),
        
        # Room block events
        ('roomblock/created', 'Room Block Created'),
        ('roomblock/removed', 'Room Block Removed'),
        ('roomblock/details_changed', 'Room Block Changed'),
        
        # Allotment events
        ('allotmentBlock/created', 'Allotment Block Created'),
        ('allotmentBlock/updated', 'Allotment Block Updated'),
        ('allotmentBlock/deleted', 'Allotment Block Deleted'),
        ('allotmentBlock/capacity_changed_for_reservation', 'Allotment Capacity Changed'),
        
        # Integration events
        ('integration/appstate_changed', 'App State Changed'),
        ('integration/appsettings_changed', 'App Settings Changed'),
        
        # Rate events
        ('api_queue_task/rate_status_changed', 'Rate Update Status Changed'),
        
        # Night audit
        ('night_audit/completed', 'Night Audit Completed'),
    ], string='Event Type', required=True, tracking=True)
    
    event_object = fields.Char(
        string='Event Object',
        compute='_compute_event_details',
        store=True
    )
    
    event_action = fields.Char(
        string='Event Action',
        compute='_compute_event_details',
        store=True
    )
    
    endpoint_url = fields.Char(
        string='Endpoint URL',
        compute='_compute_endpoint_url',
        store=True,
        help='The URL where webhook notifications will be sent'
    )
    
    secret_key = fields.Char(
        string='Secret Key',
        default=lambda self: self._generate_secret_key(),
        help='Secret key for webhook validation',
        groups='cloudconnect_core.group_cloudconnect_manager'
    )
    
    active = fields.Boolean(
        string='Active',
        default=True,
        tracking=True
    )
    
    # Cloudbeds webhook info
    cloudbeds_webhook_id = fields.Char(
        string='Cloudbeds Webhook ID',
        readonly=True,
        help='ID of the webhook subscription in Cloudbeds'
    )
    
    # Statistics
    last_received = fields.Datetime(
        string='Last Event Received',
        readonly=True
    )
    
    total_received = fields.Integer(
        string='Total Events',
        readonly=True,
        default=0
    )
    
    total_errors = fields.Integer(
        string='Total Errors',
        readonly=True,
        default=0
    )
    
    last_error = fields.Text(
        string='Last Error',
        readonly=True
    )
    
    display_name = fields.Char(
        string='Display Name',
        compute='_compute_display_name',
        store=True
    )
    
    @api.depends('event_type')
    def _compute_event_details(self):
        """Extract object and action from event type."""
        for record in self:
            if record.event_type and '/' in record.event_type:
                parts = record.event_type.split('/')
                record.event_object = parts[0]
                record.event_action = parts[1]
            else:
                record.event_object = False
                record.event_action = False
    
    @api.depends('config_id', 'property_id', 'event_type')
    def _compute_endpoint_url(self):
        """Compute the endpoint URL for this webhook."""
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        for record in self:
            if record.property_id:
                record.endpoint_url = f"{base_url}/cloudconnect/webhook/{record.property_id.cloudbeds_id}/{record.event_type}"
            else:
                record.endpoint_url = f"{base_url}/cloudconnect/webhook/all/{record.event_type}"
    
    @api.depends('event_type', 'property_id')
    def _compute_display_name(self):
        """Compute display name for webhook."""
        for record in self:
            event_name = dict(self._fields['event_type'].selection).get(record.event_type, record.event_type)
            if record.property_id:
                record.display_name = f"{event_name} - {record.property_id.name}"
            else:
                record.display_name = f"{event_name} - All Properties"
    
    def _generate_secret_key(self):
        """Generate a secure random secret key."""
        return secrets.token_urlsafe(32)
    
    @api.constrains('event_type', 'property_id', 'config_id')
    def _check_unique_webhook(self):
        """Ensure webhook is unique per event type and property."""
        for record in self:
            domain = [
                ('event_type', '=', record.event_type),
                ('config_id', '=', record.config_id.id),
                ('id', '!=', record.id)
            ]
            
            if record.property_id:
                domain.append(('property_id', '=', record.property_id.id))
            else:
                domain.append(('property_id', '=', False))
            
            duplicate = self.search(domain)
            if duplicate:
                raise ValidationError(_(
                    "A webhook for event '%s' already exists for this property/configuration."
                ) % record.event_type)
    
    def validate_webhook_signature(self, payload, signature):
        """Validate webhook signature using HMAC."""
        self.ensure_one()
        
        if not self.secret_key:
            _logger.warning(f"No secret key configured for webhook {self.id}")
            return False
        
        expected_signature = hmac.new(
            self.secret_key.encode(),
            payload.encode(),
            hashlib.sha256
        ).hexdigest()
        
        return hmac.compare_digest(signature, expected_signature)
    
    def register_with_cloudbeds(self):
        """Register this webhook with Cloudbeds."""
        self.ensure_one()
        
        if not self.config_id.access_token:
            raise ValidationError(_("No valid access token. Please authenticate first."))
        
        if not self.event_object or not self.event_action:
            raise ValidationError(_("Invalid event type configuration."))
        
        # Call API service to register webhook
        api_service = self.env['cloudconnect.api.service']
        
        params = {
            'object': self.event_object,
            'action': self.event_action,
            'endpointUrl': self.endpoint_url,
        }
        
        if self.property_id:
            params['propertyID'] = self.property_id.cloudbeds_id
        
        try:
            result = api_service.post_webhook(self.config_id, params)
            
            if result.get('success') and result.get('data'):
                self.cloudbeds_webhook_id = result['data'].get('id')
                self.message_post(
                    body=_("Webhook registered successfully with Cloudbeds"),
                    message_type='notification'
                )
                return True
            else:
                raise ValidationError(_("Failed to register webhook: %s") % result.get('message', 'Unknown error'))
                
        except Exception as e:
            raise ValidationError(_("Error registering webhook: %s") % str(e))
    
    def unregister_from_cloudbeds(self):
        """Unregister this webhook from Cloudbeds."""
        self.ensure_one()
        
        if not self.cloudbeds_webhook_id:
            return True
        
        # Call API service to delete webhook
        api_service = self.env['cloudconnect.api.service']
        
        try:
            result = api_service.delete_webhook(self.config_id, self.cloudbeds_webhook_id)
            
            if result.get('success'):
                self.cloudbeds_webhook_id = False
                self.message_post(
                    body=_("Webhook unregistered from Cloudbeds"),
                    message_type='notification'
                )
                return True
            else:
                _logger.error(f"Failed to unregister webhook: {result.get('message', 'Unknown error')}")
                return False
                
        except Exception as e:
            _logger.error(f"Error unregistering webhook: {str(e)}")
            return False
    
    def action_register(self):
        """Action to register webhook."""
        self.ensure_one()
        return self.register_with_cloudbeds()
    
    def action_unregister(self):
        """Action to unregister webhook."""
        self.ensure_one()
        return self.unregister_from_cloudbeds()
    
    def action_regenerate_secret(self):
        """Regenerate the secret key."""
        self.ensure_one()
        self.secret_key = self._generate_secret_key()
        self.message_post(
            body=_("Secret key regenerated"),
            message_type='notification'
        )
    
    def record_event_received(self, success=True, error_message=None):
        """Record that an event was received."""
        self.ensure_one()
        
        vals = {
            'last_received': fields.Datetime.now(),
            'total_received': self.total_received + 1,
        }
        
        if not success:
            vals['total_errors'] = self.total_errors + 1
            vals['last_error'] = error_message or 'Unknown error'
        
        self.write(vals)
    
    @api.model
    def process_webhook_event(self, event_type, property_id, data):
        """Process incoming webhook event."""
        # Find matching webhook configuration
        domain = [
            ('event_type', '=', event_type),
            ('active', '=', True)
        ]
        
        if property_id and property_id != 'all':
            property = self.env['cloudconnect.property'].search([
                ('cloudbeds_id', '=', property_id)
            ], limit=1)
            if property:
                domain.append(('property_id', '=', property.id))
        else:
            domain.append(('property_id', '=', False))
        
        webhook = self.search(domain, limit=1)
        
        if not webhook:
            _logger.warning(f"No active webhook found for event {event_type}, property {property_id}")
            return False
        
        try:
            # Process through webhook processor service
            processor = self.env['cloudconnect.webhook.processor']
            processor.process_event(webhook, data)
            
            webhook.record_event_received(success=True)
            return True
            
        except Exception as e:
            _logger.error(f"Error processing webhook event: {str(e)}")
            webhook.record_event_received(success=False, error_message=str(e))
            return False
    
    def unlink(self):
        """Unregister webhooks before deletion."""
        for record in self:
            if record.cloudbeds_webhook_id:
                try:
                    record.unregister_from_cloudbeds()
                except Exception as e:
                    _logger.error(f"Error unregistering webhook on deletion: {str(e)}")
        
        return super().unlink()