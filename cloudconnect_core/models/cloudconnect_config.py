# -*- coding: utf-8 -*-

import logging
import requests
from datetime import datetime, timedelta
from cryptography.fernet import Fernet
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError

_logger = logging.getLogger(__name__)


class CloudconnectConfig(models.Model):
    _name = 'cloudconnect.config'
    _description = 'CloudConnect Configuration'
    _rec_name = 'name'
    _order = 'sequence, id'

    name = fields.Char(
        string='Configuration Name',
        required=True,
        help='Descriptive name for this configuration'
    )
    sequence = fields.Integer(
        string='Sequence',
        default=10,
        help='Sequence for ordering configurations'
    )
    active = fields.Boolean(
        string='Active',
        default=True,
        help='Set to false to disable this configuration'
    )
    
    # API Configuration
    api_endpoint = fields.Char(
        string='API Endpoint',
        default='https://hotels.cloudbeds.com/api/v1.2',
        required=True,
        help='Cloudbeds API base URL'
    )
    client_id = fields.Char(
        string='Client ID',
        required=True,
        help='OAuth Client ID provided by Cloudbeds'
    )
    client_secret_encrypted = fields.Text(
        string='Client Secret (Encrypted)',
        help='OAuth Client Secret (encrypted)'
    )
    
    # Token Management
    access_token_encrypted = fields.Text(
        string='Access Token (Encrypted)',
        help='Current OAuth access token (encrypted)'
    )
    refresh_token_encrypted = fields.Text(
        string='Refresh Token (Encrypted)',
        help='OAuth refresh token (encrypted)'
    )
    token_expires_at = fields.Datetime(
        string='Token Expires At',
        help='When the current access token expires'
    )
    
    # Rate Limiting
    rate_limit_requests = fields.Integer(
        string='Rate Limit (req/sec)',
        default=5,
        help='Maximum requests per second (5 for properties, 10 for tech partners)'
    )
    rate_limit_burst = fields.Integer(
        string='Burst Tolerance',
        default=10,
        help='Number of requests allowed in burst'
    )
    
    # Sync Configuration
    sync_enabled = fields.Boolean(
        string='Sync Enabled',
        default=True,
        help='Enable automatic synchronization'
    )
    sync_interval_minutes = fields.Integer(
        string='Sync Interval (minutes)',
        default=15,
        help='Interval between automatic synchronizations'
    )
    
    # Connection Status
    connection_status = fields.Selection([
        ('disconnected', 'Disconnected'),
        ('connected', 'Connected'),
        ('error', 'Error'),
        ('expired', 'Token Expired')
    ], string='Connection Status', default='disconnected', readonly=True)
    
    last_connection_test = fields.Datetime(
        string='Last Connection Test',
        readonly=True
    )
    connection_error = fields.Text(
        string='Connection Error',
        readonly=True
    )
    
    # Properties
    property_ids = fields.One2many(
        'cloudconnect.property',
        'config_id',
        string='Properties'
    )
    property_count = fields.Integer(
        string='Properties Count',
        compute='_compute_property_count'
    )
    
    # Webhooks
    webhook_ids = fields.One2many(
        'cloudconnect.webhook',
        'config_id',
        string='Webhooks'
    )
    
    @api.depends('property_ids')
    def _compute_property_count(self):
        for config in self:
            config.property_count = len(config.property_ids)
    
    @api.model
    def _get_encryption_key(self):
        """Get or create encryption key for sensitive data."""
        key_param = self.env['ir.config_parameter'].sudo().get_param('cloudconnect.encryption_key')
        if not key_param:
            key = Fernet.generate_key()
            self.env['ir.config_parameter'].sudo().set_param('cloudconnect.encryption_key', key.decode())
            return key
        return key_param.encode()
    
    def _encrypt_data(self, data):
        """Encrypt sensitive data."""
        if not data:
            return False
        try:
            key = self._get_encryption_key()
            f = Fernet(key)
            return f.encrypt(data.encode()).decode()
        except Exception as e:
            _logger.error(f"Encryption error: {e}")
            raise UserError(_("Failed to encrypt sensitive data"))
    
    def _decrypt_data(self, encrypted_data):
        """Decrypt sensitive data."""
        if not encrypted_data:
            return False
        try:
            key = self._get_encryption_key()
            f = Fernet(key)
            return f.decrypt(encrypted_data.encode()).decode()
        except Exception as e:
            _logger.error(f"Decryption error: {e}")
            return False
    
    def set_client_secret(self, secret):
        """Set client secret (encrypted)."""
        self.client_secret_encrypted = self._encrypt_data(secret)
    
    def get_client_secret(self):
        """Get decrypted client secret."""
        return self._decrypt_data(self.client_secret_encrypted)
    
    def set_access_token(self, token):
        """Set access token (encrypted)."""
        self.access_token_encrypted = self._encrypt_data(token)
    
    def get_access_token(self):
        """Get decrypted access token."""
        return self._decrypt_data(self.access_token_encrypted)
    
    def set_refresh_token(self, token):
        """Set refresh token (encrypted)."""
        self.refresh_token_encrypted = self._encrypt_data(token)
    
    def get_refresh_token(self):
        """Get decrypted refresh token."""
        return self._decrypt_data(self.refresh_token_encrypted)
    
    def is_token_expired(self):
        """Check if access token is expired or about to expire."""
        if not self.token_expires_at:
            return True
        # Consider token expired if it expires in the next 5 minutes
        expiry_buffer = datetime.now() + timedelta(minutes=5)
        return self.token_expires_at <= expiry_buffer
    
    def test_connection(self):
        """Test connection to Cloudbeds API."""
        try:
            access_token = self.get_access_token()
            if not access_token:
                raise ValidationError(_("No access token configured"))
            
            headers = {
                'Authorization': f'Bearer {access_token}',
                'Content-Type': 'application/json',
                'User-Agent': 'CloudConnect-Odoo/1.0'
            }
            
            response = requests.get(
                f"{self.api_endpoint}/getHotels",
                headers=headers,
                timeout=30
            )
            
            if response.status_code == 200:
                self.connection_status = 'connected'
                self.connection_error = False
                self.last_connection_test = fields.Datetime.now()
                return True
            elif response.status_code == 401:
                self.connection_status = 'expired'
                self.connection_error = 'Access token expired'
                return False
            else:
                self.connection_status = 'error'
                self.connection_error = f"HTTP {response.status_code}: {response.text}"
                return False
                
        except requests.exceptions.RequestException as e:
            self.connection_status = 'error'
            self.connection_error = str(e)
            self.last_connection_test = fields.Datetime.now()
            _logger.error(f"Connection test failed: {e}")
            return False
        except Exception as e:
            self.connection_status = 'error'
            self.connection_error = str(e)
            self.last_connection_test = fields.Datetime.now()
            _logger.error(f"Unexpected error in connection test: {e}")
            return False
    
    def refresh_access_token(self):
        """Refresh the access token using refresh token."""
        refresh_token = self.get_refresh_token()
        client_secret = self.get_client_secret()
        
        if not refresh_token or not client_secret:
            raise UserError(_("Missing refresh token or client secret"))
        
        try:
            data = {
                'grant_type': 'refresh_token',
                'client_id': self.client_id,
                'client_secret': client_secret,
                'refresh_token': refresh_token
            }
            
            response = requests.post(
                f"{self.api_endpoint.replace('/api/v1.2', '')}/access_token",
                data=data,
                timeout=30
            )
            
            if response.status_code == 200:
                token_data = response.json()
                self.set_access_token(token_data['access_token'])
                if 'refresh_token' in token_data:
                    self.set_refresh_token(token_data['refresh_token'])
                
                # Calculate expiry time (usually 3600 seconds)
                expires_in = token_data.get('expires_in', 3600)
                self.token_expires_at = datetime.now() + timedelta(seconds=expires_in)
                
                self.connection_status = 'connected'
                self.connection_error = False
                
                _logger.info(f"Access token refreshed for config {self.name}")
                return True
            else:
                error_msg = f"Failed to refresh token: HTTP {response.status_code}"
                self.connection_status = 'error'
                self.connection_error = error_msg
                _logger.error(error_msg)
                return False
                
        except Exception as e:
            error_msg = f"Token refresh error: {e}"
            self.connection_status = 'error'
            self.connection_error = error_msg
            _logger.error(error_msg)
            return False
    
    @api.model
    def refresh_all_tokens(self):
        """Cron job method to refresh all expired tokens."""
        configs = self.search([
            ('active', '=', True),
            ('access_token_encrypted', '!=', False)
        ])
        
        for config in configs:
            if config.is_token_expired():
                try:
                    config.refresh_access_token()
                except Exception as e:
                    _logger.error(f"Failed to refresh token for config {config.name}: {e}")
    
    def action_test_connection(self):
        """Action to test connection from UI."""
        if self.test_connection():
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _("Connection Successful"),
                    'message': _("Successfully connected to Cloudbeds API"),
                    'type': 'success',
                }
            }
        else:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _("Connection Failed"),
                    'message': self.connection_error or _("Failed to connect to Cloudbeds API"),
                    'type': 'danger',
                }
            }
    
    def action_refresh_token(self):
        """Action to manually refresh token from UI."""
        if self.refresh_access_token():
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _("Token Refreshed"),
                    'message': _("Access token has been successfully refreshed"),
                    'type': 'success',
                }
            }
        else:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _("Refresh Failed"),
                    'message': self.connection_error or _("Failed to refresh access token"),
                    'type': 'danger',
                }
            }
    
    @api.constrains('rate_limit_requests')
    def _check_rate_limit(self):
        for config in self:
            if config.rate_limit_requests < 1 or config.rate_limit_requests > 100:
                raise ValidationError(_("Rate limit must be between 1 and 100 requests per second"))
    
    @api.constrains('api_endpoint')
    def _check_api_endpoint(self):
        for config in self:
            if not config.api_endpoint.startswith(('http://', 'https://')):
                raise ValidationError(_("API endpoint must be a valid URL starting with http:// or https://"))