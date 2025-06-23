# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError
import requests
import json
import logging
from urllib.parse import urlencode, quote

_logger = logging.getLogger(__name__)


class CloudConnectSetupWizard(models.TransientModel):
    _name = 'cloudconnect.setup.wizard'
    _description = 'CloudConnect Setup Wizard'
    
    # Step management
    current_step = fields.Selection([
        ('credentials', 'OAuth Credentials'),
        ('authenticate', 'Authentication'),
        ('properties', 'Select Properties'),
        ('webhooks', 'Configure Webhooks'),
        ('complete', 'Complete'),
    ], string='Current Step', default='credentials')
    
    # Configuration
    config_id = fields.Many2one(
        'cloudconnect.config',
        string='Configuration',
        help='Leave empty to create new configuration'
    )
    
    config_name = fields.Char(
        string='Configuration Name',
        default='Cloudbeds Configuration'
    )
    
    # OAuth Credentials
    client_id = fields.Char(
        string='Client ID',
        help='OAuth2 Client ID from Cloudbeds'
    )
    
    client_secret = fields.Char(
        string='Client Secret',
        help='OAuth2 Client Secret from Cloudbeds'
    )
    
    # Authentication
    auth_url = fields.Char(
        string='Authorization URL',
        compute='_compute_auth_url'
    )
    
    auth_code = fields.Char(
        string='Authorization Code',
        help='Code received after OAuth authorization'
    )
    
    access_token_received = fields.Boolean(
        string='Access Token Received',
        default=False
    )
    
    # Properties
    property_ids = fields.Many2many(
        'cloudconnect.property',
        string='Properties to Sync',
        domain="[('config_id', '=', config_id)]"
    )
    
    available_properties = fields.Text(
        string='Available Properties',
        readonly=True
    )
    
    # Webhooks
    webhook_selection = fields.Text(
        string='Webhook Events',
        default='[]',
        help='JSON list of webhook events to configure'
    )
    
    setup_reservation_webhooks = fields.Boolean(
        string='Reservation Events',
        default=True,
        help='Setup webhooks for reservation events'
    )
    
    setup_guest_webhooks = fields.Boolean(
        string='Guest Events',
        default=True,
        help='Setup webhooks for guest events'
    )
    
    setup_payment_webhooks = fields.Boolean(
        string='Payment Events',
        default=True,
        help='Setup webhooks for payment events'
    )
    
    setup_housekeeping_webhooks = fields.Boolean(
        string='Housekeeping Events',
        default=False,
        help='Setup webhooks for housekeeping events'
    )
    
    # Status
    setup_log = fields.Text(
        string='Setup Log',
        readonly=True
    )
    
    @api.depends('client_id')
    def _compute_auth_url(self):
        """Compute OAuth authorization URL."""
        for wizard in self:
            if wizard.client_id and wizard.config_id:
                base_url = "https://hotels.cloudbeds.com/oauth"
                params = {
                    'client_id': wizard.client_id,
                    'redirect_uri': wizard.config_id.redirect_uri,
                    'response_type': 'code',
                    'scope': 'read:reservation write:reservation read:guest write:guest read:payment write:payment read:housekeeping read:item write:item read:rate write:rate read:appPropertySettings write:appPropertySettings',
                }
                wizard.auth_url = f"{base_url}?{urlencode(params)}"
            else:
                wizard.auth_url = False
    
    @api.onchange('config_id')
    def _onchange_config_id(self):
        """Load existing configuration if selected."""
        if self.config_id:
            self.config_name = self.config_id.name
            self.client_id = self.config_id.client_id
            # Don't load encrypted secret
            self.client_secret = False
    
    def _log_setup(self, message):
        """Add message to setup log."""
        if self.setup_log:
            self.setup_log += f"\n{message}"
        else:
            self.setup_log = message
    
    def action_previous(self):
        """Go to previous step."""
        self.ensure_one()
        
        steps = ['credentials', 'authenticate', 'properties', 'webhooks', 'complete']
        current_index = steps.index(self.current_step)
        
        if current_index > 0:
            self.current_step = steps[current_index - 1]
        
        return self._reopen_wizard()
    
    def action_next(self):
        """Go to next step."""
        self.ensure_one()
        
        # Validate current step
        if self.current_step == 'credentials':
            self._validate_credentials()
        elif self.current_step == 'authenticate':
            self._validate_authentication()
        elif self.current_step == 'properties':
            self._validate_properties()
        elif self.current_step == 'webhooks':
            self._setup_webhooks()
        
        # Move to next step
        steps = ['credentials', 'authenticate', 'properties', 'webhooks', 'complete']
        current_index = steps.index(self.current_step)
        
        if current_index < len(steps) - 1:
            self.current_step = steps[current_index + 1]
        
        return self._reopen_wizard()
    
    def _validate_credentials(self):
        """Validate OAuth credentials step."""
        if not self.client_id or not self.client_secret:
            raise ValidationError(_("Please provide both Client ID and Client Secret."))
        
        # Create or update configuration
        if not self.config_id:
            self.config_id = self.env['cloudconnect.config'].create({
                'name': self.config_name,
                'client_id': self.client_id,
                'client_secret': self.client_secret,
                'active': False,
            })
            self._log_setup(_("Configuration created successfully."))
        else:
            self.config_id.write({
                'name': self.config_name,
                'client_id': self.client_id,
                'client_secret': self.client_secret,
            })
            self._log_setup(_("Configuration updated successfully."))
    
    def _validate_authentication(self):
        """Validate authentication step."""
        if not self.auth_code:
            raise ValidationError(_("Please complete OAuth authorization and enter the authorization code."))
        
        # Exchange auth code for access token
        try:
            data = {
                'grant_type': 'authorization_code',
                'client_id': self.config_id.client_id,
                'client_secret': self.config_id.get_decrypted_secret(),
                'redirect_uri': self.config_id.redirect_uri,
                'code': self.auth_code,
            }
            
            response = requests.post(
                "https://hotels.cloudbeds.com/oauth/access_token",
                data=data,
                timeout=30
            )
            
            if response.status_code == 200:
                token_data = response.json()
                
                # Save tokens
                self.config_id.write({
                    'access_token': token_data.get('access_token'),
                    'refresh_token': token_data.get('refresh_token'),
                    'token_expires_at': fields.Datetime.now() + \
                        fields.Timedelta(seconds=token_data.get('expires_in', 3600))
                })
                
                self.access_token_received = True
                self._log_setup(_("Authentication successful! Access token received."))
                
                # Fetch available properties
                self._fetch_properties()
                
            else:
                raise ValidationError(_(
                    "Failed to exchange authorization code. Status: %s, Response: %s"
                ) % (response.status_code, response.text))
                
        except requests.exceptions.RequestException as e:
            raise ValidationError(_("Authentication error: %s") % str(e))
    
    def _fetch_properties(self):
        """Fetch available properties from Cloudbeds."""
        try:
            headers = {
                'Authorization': f'Bearer {self.config_id.get_decrypted_access_token()}',
                'Content-Type': 'application/json'
            }
            
            response = requests.get(
                f"{self.config_id.api_endpoint}/getHotels",
                headers=headers,
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                if data.get('success') and data.get('data'):
                    # Create/update properties
                    properties_info = []
                    for prop_data in data['data']:
                        property_obj = self.env['cloudconnect.property']._create_or_update_property(
                            self.config_id, prop_data
                        )
                        properties_info.append(f"- {property_obj.name} (ID: {property_obj.cloudbeds_id})")
                    
                    self.available_properties = "\n".join(properties_info)
                    self._log_setup(_("Found %d properties.") % len(properties_info))
                    
                    # Auto-select all properties
                    all_properties = self.env['cloudconnect.property'].search([
                        ('config_id', '=', self.config_id.id)
                    ])
                    self.property_ids = [(6, 0, all_properties.ids)]
                    
            else:
                _logger.error(f"Failed to fetch properties: {response.text}")
                
        except Exception as e:
            _logger.error(f"Error fetching properties: {str(e)}")
    
    def _validate_properties(self):
        """Validate properties selection."""
        if not self.property_ids:
            raise ValidationError(_("Please select at least one property to sync."))
        
        # Enable sync for selected properties
        self.property_ids.write({'sync_enabled': True})
        
        # Disable sync for unselected properties
        unselected = self.env['cloudconnect.property'].search([
            ('config_id', '=', self.config_id.id),
            ('id', 'not in', self.property_ids.ids)
        ])
        unselected.write({'sync_enabled': False})
        
        self._log_setup(_("Property selection saved."))
    
    def _setup_webhooks(self):
        """Setup selected webhooks."""
        webhook_model = self.env['cloudconnect.webhook']
        created_count = 0
        
        # Define webhook events by category
        webhook_events = {
            'reservation': [
                'reservation/created',
                'reservation/status_changed',
                'reservation/dates_changed',
                'reservation/accommodation_changed',
                'reservation/deleted',
            ] if self.setup_reservation_webhooks else [],
            'guest': [
                'guest/created',
                'guest/assigned',
                'guest/removed',
                'guest/details_changed',
            ] if self.setup_guest_webhooks else [],
            'payment': [
                'transaction/created',
            ] if self.setup_payment_webhooks else [],
            'housekeeping': [
                'housekeeping/room_condition_changed',
            ] if self.setup_housekeeping_webhooks else [],
        }
        
        # Create webhooks for each selected property
        for property_obj in self.property_ids:
            for category, events in webhook_events.items():
                for event in events:
                    # Check if webhook already exists
                    existing = webhook_model.search([
                        ('config_id', '=', self.config_id.id),
                        ('property_id', '=', property_obj.id),
                        ('event_type', '=', event),
                    ])
                    
                    if not existing:
                        webhook = webhook_model.create({
                            'config_id': self.config_id.id,
                            'property_id': property_obj.id,
                            'event_type': event,
                            'active': True,
                        })
                        
                        # Try to register with Cloudbeds
                        try:
                            webhook.register_with_cloudbeds()
                            created_count += 1
                        except Exception as e:
                            _logger.error(f"Failed to register webhook {event}: {str(e)}")
        
        self._log_setup(_("Created and registered %d webhooks.") % created_count)
        
        # Activate configuration
        self.config_id.active = True
        self._log_setup(_("Configuration activated successfully!"))
    
    def action_open_auth_url(self):
        """Open OAuth authorization URL in browser."""
        self.ensure_one()
        
        if not self.auth_url:
            raise ValidationError(_("Please save credentials first."))
        
        return {
            'type': 'ir.actions.act_url',
            'url': self.auth_url,
            'target': 'new',
        }
    
    def action_complete(self):
        """Complete the setup wizard."""
        self.ensure_one()
        
        # Show success message
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Setup Complete'),
                'message': _('CloudConnect has been configured successfully! You can now start synchronizing data with Cloudbeds.'),
                'type': 'success',
                'sticky': True,
                'next': {
                    'type': 'ir.actions.act_window',
                    'res_model': 'cloudconnect.config',
                    'res_id': self.config_id.id,
                    'view_mode': 'form',
                }
            }
        }
    
    def _reopen_wizard(self):
        """Reopen wizard at current step."""
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
            'context': self.env.context,
        }