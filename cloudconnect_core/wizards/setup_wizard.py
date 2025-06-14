# -*- coding: utf-8 -*-

import logging
import requests
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class CloudconnectSetupWizard(models.TransientModel):
    _name = 'cloudconnect.setup.wizard'
    _description = 'CloudConnect Setup Wizard'

    # Wizard Steps
    step = fields.Selection([
        ('welcome', 'Welcome'),
        ('credentials', 'API Credentials'),
        ('properties', 'Properties'),
        ('webhooks', 'Webhooks'),
        ('complete', 'Complete')
    ], string='Step', default='welcome', required=True)

    # Welcome Step
    welcome_message = fields.Html(
        string='Welcome Message',
        default="""
        <h3>Welcome to CloudConnect</h3>
        <p>This wizard will guide you through setting up your Cloudbeds integration.</p>
        <p>You will need:</p>
        <ul>
            <li>Your Cloudbeds API credentials (Client ID and Client Secret)</li>
            <li>Access to your Cloudbeds property management system</li>
            <li>Admin access to configure webhooks</li>
        </ul>
        <p>The setup process will take approximately 5-10 minutes.</p>
        """,
        readonly=True
    )

    # Credentials Step
    config_name = fields.Char(
        string='Configuration Name',
        default='Default CloudConnect Configuration',
        required=True,
        help='A descriptive name for this configuration'
    )
    api_endpoint = fields.Char(
        string='API Endpoint',
        default='https://hotels.cloudbeds.com/api/v1.2',
        required=True,
        help='Cloudbeds API base URL'
    )
    client_id = fields.Char(
        string='Client ID',
        required=True,
        help='OAuth Client ID from Cloudbeds API credentials'
    )
    client_secret = fields.Char(
        string='Client Secret',
        required=True,
        help='OAuth Client Secret from Cloudbeds API credentials'
    )
    redirect_uri = fields.Char(
        string='Redirect URI',
        help='OAuth redirect URI (for manual token generation)'
    )
    
    # Rate Limiting
    is_tech_partner = fields.Boolean(
        string='Tech Partner Account',
        default=False,
        help='Check if you have a Cloudbeds Tech Partner account (higher rate limits)'
    )
    rate_limit_requests = fields.Integer(
        string='Rate Limit (req/sec)',
        compute='_compute_rate_limit',
        help='Requests per second limit'
    )

    # Token Management
    access_token = fields.Char(
        string='Access Token',
        help='OAuth access token (if you have one)'
    )
    refresh_token = fields.Char(
        string='Refresh Token',
        help='OAuth refresh token (if you have one)'
    )
    token_expires_in = fields.Integer(
        string='Token Expires In (seconds)',
        default=3600,
        help='Token expiration time in seconds'
    )

    # Connection Status
    connection_status = fields.Selection([
        ('not_tested', 'Not Tested'),
        ('testing', 'Testing...'),
        ('success', 'Connected'),
        ('error', 'Error')
    ], string='Connection Status', default='not_tested', readonly=True)
    
    connection_message = fields.Text(
        string='Connection Message',
        readonly=True
    )

    # Properties Step
    available_properties = fields.Text(
        string='Available Properties',
        readonly=True,
        help='Properties found in your Cloudbeds account'
    )
    selected_property_ids = fields.Char(
        string='Selected Properties',
        help='Comma-separated list of property IDs to sync'
    )
    auto_sync_enabled = fields.Boolean(
        string='Enable Auto-Sync',
        default=True,
        help='Automatically sync data from Cloudbeds'
    )
    sync_interval_minutes = fields.Integer(
        string='Sync Interval (minutes)',
        default=15,
        help='How often to sync data automatically'
    )

    # Webhooks Step
    enable_webhooks = fields.Boolean(
        string='Enable Webhooks',
        default=True,
        help='Enable real-time webhooks for instant updates'
    )
    webhook_events = fields.Many2many(
        'cloudconnect.webhook.event',
        string='Webhook Events',
        help='Select which events to listen for'
    )
    webhook_base_url = fields.Char(
        string='Webhook Base URL',
        compute='_compute_webhook_base_url',
        help='Base URL for webhook endpoints'
    )

    # Results
    created_config_id = fields.Many2one(
        'cloudconnect.config',
        string='Created Configuration',
        readonly=True
    )
    created_property_ids = fields.Many2many(
        'cloudconnect.property',
        string='Created Properties',
        readonly=True
    )
    setup_summary = fields.Html(
        string='Setup Summary',
        readonly=True
    )

    @api.depends('is_tech_partner')
    def _compute_rate_limit(self):
        for wizard in self:
            wizard.rate_limit_requests = 10 if wizard.is_tech_partner else 5

    @api.depends()
    def _compute_webhook_base_url(self):
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        for wizard in self:
            wizard.webhook_base_url = f"{base_url}/cloudconnect/webhook"

    def action_next_step(self):
        """Move to the next step in the wizard."""
        self.ensure_one()
        
        if self.step == 'welcome':
            self.step = 'credentials'
        elif self.step == 'credentials':
            # Validate credentials before proceeding
            if not self._validate_credentials():
                return self._reload_wizard()
            self.step = 'properties'
            self._load_properties()
        elif self.step == 'properties':
            self.step = 'webhooks'
        elif self.step == 'webhooks':
            self.step = 'complete'
            self._complete_setup()
        
        return self._reload_wizard()

    def action_previous_step(self):
        """Move to the previous step in the wizard."""
        self.ensure_one()
        
        if self.step == 'complete':
            self.step = 'webhooks'
        elif self.step == 'webhooks':
            self.step = 'properties'
        elif self.step == 'properties':
            self.step = 'credentials'
        elif self.step == 'credentials':
            self.step = 'welcome'
        
        return self._reload_wizard()

    def action_test_connection(self):
        """Test connection with the provided credentials."""
        self.ensure_one()
        
        if not self.client_id or not self.client_secret:
            raise UserError(_("Please provide both Client ID and Client Secret"))
        
        self.connection_status = 'testing'
        self.connection_message = _("Testing connection...")
        
        try:
            # Create temporary config for testing
            temp_config = self.env['cloudconnect.config'].create({
                'name': 'temp_test_config',
                'api_endpoint': self.api_endpoint,
                'client_id': self.client_id,
                'active': False,  # Don't activate until setup is complete
            })
            
            # Set encrypted client secret
            temp_config.set_client_secret(self.client_secret)
            
            # If we have tokens, set them
            if self.access_token:
                temp_config.set_access_token(self.access_token)
                if self.refresh_token:
                    temp_config.set_refresh_token(self.refresh_token)
                
                # Set expiry time
                from datetime import datetime, timedelta
                temp_config.token_expires_at = datetime.now() + timedelta(seconds=self.token_expires_in)
            
            # Test connection
            api_service = self.env['cloudconnect.api.service']
            result = api_service.test_api_connection(temp_config.id)
            
            if result['success']:
                self.connection_status = 'success'
                self.connection_message = _("Connection successful! Found access to Cloudbeds API.")
                
                # Store tokens if test was successful and we didn't have them
                if not self.access_token:
                    self.access_token = temp_config.get_access_token()
                    self.refresh_token = temp_config.get_refresh_token()
                
            else:
                self.connection_status = 'error'
                self.connection_message = result['message']
            
            # Clean up temp config
            temp_config.unlink()
            
        except Exception as e:
            self.connection_status = 'error'
            self.connection_message = str(e)
            _logger.error(f"Connection test failed: {e}")
            
            # Clean up temp config if it exists
            try:
                temp_config.unlink()
            except:
                pass
        
        return self._reload_wizard()

    def action_generate_oauth_url(self):
        """Generate OAuth authorization URL."""
        self.ensure_one()
        
        if not self.client_id:
            raise UserError(_("Please provide Client ID first"))
        
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        redirect_uri = self.redirect_uri or f"{base_url}/cloudconnect/oauth/callback"
        
        oauth_url = (
            f"{self.api_endpoint.replace('/api/v1.2', '')}/oauth?"
            f"client_id={self.client_id}&"
            f"redirect_uri={redirect_uri}&"
            f"response_type=code&"
            f"state=setup_wizard"
        )
        
        return {
            'type': 'ir.actions.act_url',
            'url': oauth_url,
            'target': 'new',
        }

    def _validate_credentials(self):
        """Validate the provided credentials."""
        if not self.client_id:
            raise UserError(_("Client ID is required"))
        if not self.client_secret:
            raise UserError(_("Client Secret is required"))
        if not self.api_endpoint:
            raise UserError(_("API Endpoint is required"))
        
        # Test connection if not already tested
        if self.connection_status != 'success':
            self.action_test_connection()
            return self.connection_status == 'success'
        
        return True

    def _load_properties(self):
        """Load available properties from Cloudbeds."""
        self.ensure_one()
        
        try:
            # Create temporary config
            temp_config = self.env['cloudconnect.config'].create({
                'name': 'temp_load_properties',
                'api_endpoint': self.api_endpoint,
                'client_id': self.client_id,
                'active': False,
            })
            
            temp_config.set_client_secret(self.client_secret)
            temp_config.set_access_token(self.access_token)
            temp_config.set_refresh_token(self.refresh_token)
            
            # Get properties
            api_service = self.env['cloudconnect.api.service']
            hotels_data = api_service.get_hotels(temp_config)
            
            if hotels_data.get('success'):
                properties = hotels_data.get('data', [])
                
                # Format properties list
                property_list = []
                for prop in properties:
                    prop_info = (
                        f"• {prop.get('propertyName', 'Unknown')} "
                        f"(ID: {prop.get('propertyID')}) - "
                        f"{prop.get('propertyCity', 'Unknown City')}"
                    )
                    property_list.append(prop_info)
                
                self.available_properties = '\n'.join(property_list)
                
                # Auto-select all properties
                property_ids = [str(prop.get('propertyID')) for prop in properties if prop.get('propertyID')]
                self.selected_property_ids = ','.join(property_ids)
                
            else:
                raise UserError(_("Failed to load properties: %s") % hotels_data.get('message', 'Unknown error'))
            
            # Clean up temp config
            temp_config.unlink()
            
        except Exception as e:
            _logger.error(f"Failed to load properties: {e}")
            raise UserError(_("Failed to load properties: %s") % str(e))

    def _complete_setup(self):
        """Complete the setup process."""
        self.ensure_one()
        
        try:
            # Create the configuration
            config_vals = {
                'name': self.config_name,
                'api_endpoint': self.api_endpoint,
                'client_id': self.client_id,
                'rate_limit_requests': self.rate_limit_requests,
                'sync_enabled': self.auto_sync_enabled,
                'sync_interval_minutes': self.sync_interval_minutes,
                'active': True,
            }
            
            config = self.env['cloudconnect.config'].create(config_vals)
            self.created_config_id = config.id
            
            # Set encrypted credentials
            config.set_client_secret(self.client_secret)
            if self.access_token:
                config.set_access_token(self.access_token)
            if self.refresh_token:
                config.set_refresh_token(self.refresh_token)
            
            # Create properties
            created_properties = []
            if self.selected_property_ids:
                property_ids = [pid.strip() for pid in self.selected_property_ids.split(',') if pid.strip()]
                
                # Get property details
                api_service = self.env['cloudconnect.api.service']
                for prop_id in property_ids:
                    try:
                        hotel_data = api_service.get_hotel_details(config, prop_id)
                        if hotel_data.get('success'):
                            hotel_info = hotel_data.get('data', {})
                            
                            property_vals = {
                                'cloudbeds_id': prop_id,
                                'name': hotel_info.get('propertyName', f'Property {prop_id}'),
                                'config_id': config.id,
                                'sync_enabled': self.auto_sync_enabled,
                                'city': hotel_info.get('propertyCity'),
                                'phone': hotel_info.get('propertyPhone'),
                                'email': hotel_info.get('propertyEmail'),
                                'timezone': hotel_info.get('propertyTimezone', 'UTC'),
                            }
                            
                            # Get country
                            if hotel_info.get('propertyCountry'):
                                country = self.env['res.country'].search([
                                    ('code', '=', hotel_info['propertyCountry'].upper())
                                ], limit=1)
                                if country:
                                    property_vals['country_id'] = country.id
                            
                            property_obj = self.env['cloudconnect.property'].create(property_vals)
                            created_properties.append(property_obj.id)
                            
                    except Exception as e:
                        _logger.error(f"Failed to create property {prop_id}: {e}")
            
            self.created_property_ids = [(6, 0, created_properties)]
            
            # Setup webhooks if enabled
            webhook_count = 0
            if self.enable_webhooks and created_properties:
                webhook_count = self._setup_webhooks(created_properties)
            
            # Generate setup summary
            self._generate_setup_summary(config, len(created_properties), webhook_count)
            
        except Exception as e:
            _logger.error(f"Setup completion failed: {e}")
            raise UserError(_("Setup failed: %s") % str(e))

    def _setup_webhooks(self, property_ids):
        """Setup basic webhooks for properties."""
        webhook_count = 0
        
        # Default webhook events to setup
        default_events = [
            'reservation_created',
            'reservation_status_changed',
            'guest_created',
            'guest_details_changed',
            'transaction_created',
        ]
        
        for property_id in property_ids:
            property_obj = self.env['cloudconnect.property'].browse(property_id)
            
            for event_type in default_events:
                try:
                    webhook_vals = {
                        'property_id': property_id,
                        'config_id': property_obj.config_id.id,
                        'event_type': event_type,
                        'active': True,
                    }
                    
                    webhook = self.env['cloudconnect.webhook'].create(webhook_vals)
                    # The webhook will auto-register with Cloudbeds on creation
                    webhook_count += 1
                    
                except Exception as e:
                    _logger.error(f"Failed to create webhook {event_type} for property {property_id}: {e}")
        
        return webhook_count

    def _generate_setup_summary(self, config, property_count, webhook_count):
        """Generate setup completion summary."""
        summary = f"""
        <h3>🎉 Setup Complete!</h3>
        <p>Your CloudConnect integration has been successfully configured:</p>
        
        <h4>Configuration Details:</h4>
        <ul>
            <li><strong>Configuration:</strong> {config.name}</li>
            <li><strong>API Endpoint:</strong> {config.api_endpoint}</li>
            <li><strong>Rate Limit:</strong> {config.rate_limit_requests} requests/second</li>
            <li><strong>Connection Status:</strong> ✅ Connected</li>
        </ul>
        
        <h4>Properties Configured:</h4>
        <ul>
            <li><strong>Properties:</strong> {property_count} property(ies) configured</li>
            <li><strong>Auto-Sync:</strong> {'✅ Enabled' if self.auto_sync_enabled else '❌ Disabled'}</li>
            <li><strong>Sync Interval:</strong> {self.sync_interval_minutes} minutes</li>
        </ul>
        
        <h4>Webhooks:</h4>
        <ul>
            <li><strong>Webhooks:</strong> {webhook_count} webhook(s) configured</li>
            <li><strong>Real-time Updates:</strong> {'✅ Enabled' if webhook_count > 0 else '❌ Disabled'}</li>
        </ul>
        
        <h4>Next Steps:</h4>
        <ol>
            <li>Review the CloudConnect dashboard for connection status</li>
            <li>Configure additional modules (Guests, Reservations, Payments, etc.)</li>
            <li>Perform an initial sync to import existing data</li>
            <li>Monitor sync logs for any issues</li>
        </ol>
        
        <p><em>You can access CloudConnect from the main menu under Hospitality → CloudConnect.</em></p>
        """
        
        self.setup_summary = summary

    def _reload_wizard(self):
        """Reload the wizard to show updated step."""
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'cloudconnect.setup.wizard',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
            'context': self.env.context,
        }

    def action_finish_setup(self):
        """Finish setup and go to CloudConnect dashboard."""
        self.ensure_one()
        
        return {
            'type': 'ir.actions.act_window',
            'name': _('CloudConnect Dashboard'),
            'res_model': 'cloudconnect.config',
            'view_mode': 'tree,form',
            'target': 'current',
            'domain': [('id', '=', self.created_config_id.id)] if self.created_config_id else [],
        }

    def action_open_dashboard(self):
        """Open CloudConnect dashboard."""
        return {
            'type': 'ir.actions.act_window',
            'name': _('CloudConnect Dashboard'),
            'res_model': 'cloudconnect.dashboard',
            'view_mode': 'form',
            'target': 'current',
            'context': {'default_config_id': self.created_config_id.id if self.created_config_id else False},
        }


class CloudconnectWebhookEvent(models.Model):
    """Helper model for webhook event selection in wizard."""
    _name = 'cloudconnect.webhook.event'
    _description = 'CloudConnect Webhook Event Types'

    name = fields.Char(string='Event Name', required=True)
    event_type = fields.Char(string='Event Type', required=True)
    description = fields.Text(string='Description')
    category = fields.Selection([
        ('reservation', 'Reservations'),
        ('guest', 'Guests'),
        ('payment', 'Payments'),
        ('item', 'Items'),
        ('room', 'Room Management'),
        ('housekeeping', 'Housekeeping'),
        ('integration', 'Integration'),
    ], string='Category')

    @api.model
    def _setup_default_events(self):
        """Setup default webhook events."""
        events = [
            ('Reservation Created', 'reservation_created', 'New reservation is created', 'reservation'),
            ('Reservation Status Changed', 'reservation_status_changed', 'Reservation status changes', 'reservation'),
            ('Guest Created', 'guest_created', 'New guest is created', 'guest'),
            ('Guest Details Changed', 'guest_details_changed', 'Guest information is updated', 'guest'),
            ('Transaction Created', 'transaction_created', 'New transaction is recorded', 'payment'),
            ('Room Check-in', 'room_checkin', 'Guest checks into room', 'room'),
            ('Room Check-out', 'room_checkout', 'Guest checks out of room', 'room'),
        ]
        
        for name, event_type, description, category in events:
            existing = self.search([('event_type', '=', event_type)], limit=1)
            if not existing:
                self.create({
                    'name': name,
                    'event_type': event_type,
                    'description': description,
                    'category': category,
                })