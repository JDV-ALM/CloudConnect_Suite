# -*- coding: utf-8 -*-

import logging
import hmac
import hashlib
import json
from datetime import datetime, timedelta
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError

_logger = logging.getLogger(__name__)


class CloudconnectWebhook(models.Model):
    _name = 'cloudconnect.webhook'
    _description = 'CloudConnect Webhook Configuration'
    _rec_name = 'display_name'
    _order = 'event_type, property_id'

    # Basic Information
    display_name = fields.Char(
        string='Display Name',
        compute='_compute_display_name',
        store=True
    )
    active = fields.Boolean(
        string='Active',
        default=True,
        help='Set to false to disable this webhook'
    )
    
    # Configuration
    config_id = fields.Many2one(
        'cloudconnect.config',
        string='Configuration',
        required=True,
        ondelete='cascade'
    )
    property_id = fields.Many2one(
        'cloudconnect.property',
        string='Property',
        required=True,
        ondelete='cascade'
    )
    
    # Webhook Details
    event_type = fields.Selection([
        # Reservations
        ('reservation_created', 'Reservation Created'),
        ('reservation_status_changed', 'Reservation Status Changed'),
        ('reservation_dates_changed', 'Reservation Dates Changed'),
        ('reservation_accommodation_changed', 'Reservation Accommodation Changed'),
        ('reservation_deleted', 'Reservation Deleted'),
        ('reservation_notes_changed', 'Reservation Notes Changed'),
        
        # Guests
        ('guest_created', 'Guest Created'),
        ('guest_assigned', 'Guest Assigned'),
        ('guest_removed', 'Guest Removed'),
        ('guest_details_changed', 'Guest Details Changed'),
        ('guest_accommodation_changed', 'Guest Accommodation Changed'),
        
        # Payments/Transactions
        ('transaction_created', 'Transaction Created'),
        ('payment_created', 'Payment Created'),
        ('payment_updated', 'Payment Updated'),
        ('payment_voided', 'Payment Voided'),
        
        # Items
        ('item_sold', 'Item Sold'),
        ('item_voided', 'Item Voided'),
        ('item_updated', 'Item Updated'),
        
        # Room Management
        ('room_checkin', 'Room Check-in'),
        ('room_checkout', 'Room Check-out'),
        ('roomblock_created', 'Room Block Created'),
        ('roomblock_removed', 'Room Block Removed'),
        
        # Housekeeping
        ('housekeeping_status_changed', 'Housekeeping Status Changed'),
        ('room_condition_changed', 'Room Condition Changed'),
        
        # Integration
        ('integration_appstate_changed', 'App State Changed'),
        ('integration_appsettings_changed', 'App Settings Changed'),
    ], string='Event Type', required=True, help='Type of event to listen for')
    
    endpoint_url = fields.Char(
        string='Endpoint URL',
        compute='_compute_endpoint_url',
        help='Generated webhook endpoint URL'
    )
    secret_key = fields.Char(
        string='Secret Key',
        default=lambda self: self._generate_secret_key(),
        help='Secret key for HMAC validation'
    )
    
    # Status and Statistics
    status = fields.Selection([
        ('active', 'Active'),
        ('inactive', 'Inactive'),
        ('error', 'Error')
    ], string='Status', default='active')
    
    last_received = fields.Datetime(
        string='Last Event Received',
        readonly=True
    )
    total_events_received = fields.Integer(
        string='Total Events Received',
        readonly=True,
        default=0
    )
    total_events_processed = fields.Integer(
        string='Total Events Processed',
        readonly=True,
        default=0
    )
    total_events_failed = fields.Integer(
        string='Total Events Failed',
        readonly=True,
        default=0
    )
    
    # Error Handling
    max_retries = fields.Integer(
        string='Max Retries',
        default=5,
        help='Maximum number of retry attempts for failed events'
    )
    retry_delay = fields.Integer(
        string='Retry Delay (seconds)',
        default=60,
        help='Base delay between retry attempts'
    )
    last_error = fields.Text(
        string='Last Error',
        readonly=True
    )
    error_count = fields.Integer(
        string='Error Count',
        readonly=True,
        default=0
    )
    
    # Cloudbeds Integration
    cloudbeds_subscription_id = fields.Char(
        string='Cloudbeds Subscription ID',
        readonly=True,
        help='Subscription ID returned by Cloudbeds API'
    )
    registered_at = fields.Datetime(
        string='Registered At',
        readonly=True,
        help='When this webhook was registered with Cloudbeds'
    )
    
    @api.depends('event_type', 'property_id')
    def _compute_display_name(self):
        for webhook in self:
            if webhook.event_type and webhook.property_id:
                event_label = dict(webhook._fields['event_type'].selection).get(webhook.event_type, webhook.event_type)
                webhook.display_name = f"{webhook.property_id.name} - {event_label}"
            else:
                webhook.display_name = _("New Webhook")
    
    @api.depends('property_id', 'event_type')
    def _compute_endpoint_url(self):
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        for webhook in self:
            if webhook.property_id and webhook.event_type:
                webhook.endpoint_url = f"{base_url}/cloudconnect/webhook/{webhook.property_id.cloudbeds_id}/{webhook.event_type}"
            else:
                webhook.endpoint_url = False
    
    @api.model
    def _generate_secret_key(self):
        """Generate a random secret key for webhook validation."""
        import secrets
        return secrets.token_urlsafe(32)
    
    def validate_webhook_signature(self, payload, signature):
        """Validate webhook HMAC signature."""
        if not self.secret_key or not signature:
            return False
        
        try:
            expected_signature = hmac.new(
                self.secret_key.encode('utf-8'),
                payload.encode('utf-8') if isinstance(payload, str) else payload,
                hashlib.sha256
            ).hexdigest()
            
            # Compare signatures securely
            return hmac.compare_digest(signature, expected_signature)
        except Exception as e:
            _logger.error(f"Webhook signature validation error: {e}")
            return False
    
    def process_webhook_event(self, payload, headers=None):
        """Process incoming webhook event."""
        try:
            # Validate signature if provided
            signature = headers.get('X-Signature') if headers else None
            if signature and not self.validate_webhook_signature(payload, signature):
                _logger.warning(f"Invalid webhook signature for {self.event_type}")
                self.error_count += 1
                self.last_error = "Invalid webhook signature"
                return False
            
            # Parse payload
            if isinstance(payload, str):
                event_data = json.loads(payload)
            else:
                event_data = payload
            
            # Update statistics
            self.total_events_received += 1
            self.last_received = fields.Datetime.now()
            
            # Process based on event type
            result = self._process_event_by_type(event_data)
            
            if result:
                self.total_events_processed += 1
                self.error_count = 0
                self.last_error = False
            else:
                self.total_events_failed += 1
                self.error_count += 1
            
            return result
            
        except json.JSONDecodeError as e:
            error_msg = f"Invalid JSON payload: {e}"
            _logger.error(error_msg)
            self.last_error = error_msg
            self.error_count += 1
            return False
        except Exception as e:
            error_msg = f"Webhook processing error: {e}"
            _logger.error(error_msg)
            self.last_error = error_msg
            self.error_count += 1
            return False
    
    def _process_event_by_type(self, event_data):
        """Process event based on its type."""
        try:
            # Log the event
            log_vals = {
                'property_id': self.property_id.id,
                'operation_type': 'webhook',
                'model_name': self._get_target_model_for_event(),
                'cloudbeds_id': self._extract_object_id(event_data),
                'status': 'pending',
                'sync_date': fields.Datetime.now(),
                'request_id': event_data.get('timestamp', str(datetime.now().timestamp())),
                'webhook_id': self.id,
                'event_data': json.dumps(event_data)
            }
            
            sync_log = self.env['cloudconnect.sync_log'].create(log_vals)
            
            # Process the event based on type
            processor_method = getattr(self, f'_process_{self.event_type}', None)
            if processor_method:
                result = processor_method(event_data, sync_log)
            else:
                # Generic processing - just log the event
                sync_log.status = 'success'
                sync_log.error_message = False
                result = True
            
            return result
            
        except Exception as e:
            _logger.error(f"Event processing error for {self.event_type}: {e}")
            if 'sync_log' in locals():
                sync_log.status = 'error'
                sync_log.error_message = str(e)
            return False
    
    def _get_target_model_for_event(self):
        """Get target model name based on event type."""
        event_model_map = {
            'reservation_created': 'sale.order',
            'reservation_status_changed': 'sale.order',
            'reservation_dates_changed': 'sale.order',
            'reservation_accommodation_changed': 'sale.order',
            'reservation_deleted': 'sale.order',
            'reservation_notes_changed': 'sale.order',
            'guest_created': 'res.partner',
            'guest_assigned': 'res.partner',
            'guest_removed': 'res.partner',
            'guest_details_changed': 'res.partner',
            'guest_accommodation_changed': 'res.partner',
            'transaction_created': 'account.payment',
            'payment_created': 'account.payment',
            'payment_updated': 'account.payment',
            'payment_voided': 'account.payment',
            'item_sold': 'product.template',
            'item_voided': 'product.template',
            'item_updated': 'product.template',
        }
        return event_model_map.get(self.event_type, 'unknown')
    
    def _extract_object_id(self, event_data):
        """Extract object ID from event data."""
        id_fields = ['reservationID', 'reservationId', 'guestID', 'guestId', 
                    'transactionID', 'transactionId', 'itemID', 'itemId',
                    'roomID', 'roomId', 'propertyID', 'propertyId']
        
        for field in id_fields:
            if field in event_data:
                return str(event_data[field])
        
        return 'unknown'
    
    def register_with_cloudbeds(self):
        """Register this webhook with Cloudbeds API."""
        try:
            config = self.config_id
            access_token = config.get_access_token()
            
            if not access_token:
                raise UserError(_("No access token available for configuration"))
            
            # Prepare webhook registration data
            data = {
                'propertyID': self.property_id.cloudbeds_id,
                'object': self._get_cloudbeds_object(),
                'action': self._get_cloudbeds_action(),
                'endpointUrl': self.endpoint_url
            }
            
            headers = {
                'Authorization': f'Bearer {access_token}',
                'Content-Type': 'application/x-www-form-urlencoded'
            }
            
            import requests
            response = requests.post(
                f"{config.api_endpoint}/postWebhook",
                data=data,
                headers=headers,
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                if result.get('success'):
                    # Cloudbeds doesn't return subscription ID in postWebhook
                    # We'll generate one based on response or use our own
                    self.cloudbeds_subscription_id = f"cb_{self.id}_{datetime.now().timestamp()}"
                    self.registered_at = fields.Datetime.now()
                    self.status = 'active'
                    self.last_error = False
                    return True
                else:
                    error_msg = result.get('message', 'Unknown error')
                    self.last_error = error_msg
                    self.status = 'error'
                    return False
            else:
                error_msg = f"HTTP {response.status_code}: {response.text}"
                self.last_error = error_msg
                self.status = 'error'
                return False
                
        except Exception as e:
            error_msg = f"Webhook registration error: {e}"
            _logger.error(error_msg)
            self.last_error = error_msg
            self.status = 'error'
            return False
    
    def unregister_from_cloudbeds(self):
        """Unregister this webhook from Cloudbeds API."""
        try:
            if not self.cloudbeds_subscription_id:
                return True  # Already unregistered
            
            config = self.config_id
            access_token = config.get_access_token()
            
            if not access_token:
                _logger.warning("No access token available for webhook unregistration")
                return True  # Can't unregister, but that's ok
            
            headers = {
                'Authorization': f'Bearer {access_token}',
            }
            
            import requests
            response = requests.delete(
                f"{config.api_endpoint}/deleteWebhook",
                params={'subscriptionID': self.cloudbeds_subscription_id},
                headers=headers,
                timeout=30
            )
            
            if response.status_code == 200:
                self.cloudbeds_subscription_id = False
                self.status = 'inactive'
                return True
            else:
                _logger.warning(f"Failed to unregister webhook: HTTP {response.status_code}")
                return True  # Don't block deletion
                
        except Exception as e:
            _logger.error(f"Webhook unregistration error: {e}")
            return True  # Don't block deletion
    
    def _get_cloudbeds_object(self):
        """Get Cloudbeds object type from event type."""
        if self.event_type.startswith('reservation_'):
            return 'reservation'
        elif self.event_type.startswith('guest_'):
            return 'guest'
        elif self.event_type.startswith('transaction_') or self.event_type.startswith('payment_'):
            return 'transaction'
        elif self.event_type.startswith('item_'):
            return 'item'
        elif self.event_type.startswith('room'):
            return 'room'
        elif self.event_type.startswith('housekeeping_'):
            return 'housekeeping'
        elif self.event_type.startswith('integration_'):
            return 'integration'
        else:
            return 'unknown'
    
    def _get_cloudbeds_action(self):
        """Get Cloudbeds action from event type."""
        action_map = {
            'reservation_created': 'created',
            'reservation_status_changed': 'status_changed',
            'reservation_dates_changed': 'dates_changed',
            'reservation_accommodation_changed': 'accommodation_changed',
            'reservation_deleted': 'deleted',
            'reservation_notes_changed': 'notes_changed',
            'guest_created': 'created',
            'guest_assigned': 'assigned',
            'guest_removed': 'removed',
            'guest_details_changed': 'details_changed',
            'guest_accommodation_changed': 'accommodation_changed',
            'transaction_created': 'created',
            'payment_created': 'created',
            'payment_updated': 'updated',
            'payment_voided': 'voided',
            'item_sold': 'sold',
            'item_voided': 'voided',
            'item_updated': 'updated',
        }
        return action_map.get(self.event_type, 'unknown')
    
    def action_register_webhook(self):
        """Action to register webhook with Cloudbeds."""
        if self.register_with_cloudbeds():
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _("Webhook Registered"),
                    'message': _("Webhook has been successfully registered with Cloudbeds"),
                    'type': 'success',
                }
            }
        else:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _("Registration Failed"),
                    'message': self.last_error or _("Failed to register webhook"),
                    'type': 'danger',
                }
            }
    
    def action_test_webhook(self):
        """Action to test webhook endpoint."""
        # Create a test event
        test_event = {
            'version': '1.0',
            'timestamp': datetime.now().timestamp(),
            'event': f'{self._get_cloudbeds_object()}/{self._get_cloudbeds_action()}',
            'propertyID': int(self.property_id.cloudbeds_id),
            'test': True
        }
        
        result = self.process_webhook_event(test_event)
        
        if result:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _("Test Successful"),
                    'message': _("Webhook test completed successfully"),
                    'type': 'success',
                }
            }
        else:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _("Test Failed"),
                    'message': self.last_error or _("Webhook test failed"),
                    'type': 'danger',
                }
            }
    
    @api.constrains('event_type', 'property_id')
    def _check_unique_webhook(self):
        """Ensure one webhook per event type per property."""
        for webhook in self:
            duplicate = self.search([
                ('event_type', '=', webhook.event_type),
                ('property_id', '=', webhook.property_id.id),
                ('id', '!=', webhook.id),
                ('active', '=', True)
            ])
            if duplicate:
                raise ValidationError(_(
                    "An active webhook for event '%s' already exists for property '%s'"
                ) % (webhook.event_type, webhook.property_id.name))
    
    @api.model_create_multi
    def create(self, vals_list):
        """Override create to auto-register webhook."""
        webhooks = super().create(vals_list)
        for webhook in webhooks:
            if webhook.active:
                webhook.register_with_cloudbeds()
        return webhooks
    
    def write(self, vals):
        """Override write to handle activation/deactivation."""
        if 'active' in vals:
            for webhook in self:
                if vals['active'] and not webhook.active:
                    # Being activated
                    webhook.register_with_cloudbeds()
                elif not vals['active'] and webhook.active:
                    # Being deactivated
                    webhook.unregister_from_cloudbeds()
        
        return super().write(vals)
    
    def unlink(self):
        """Override unlink to unregister webhooks."""
        for webhook in self:
            webhook.unregister_from_cloudbeds()
        return super().unlink()