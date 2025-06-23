# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError
from datetime import datetime, timedelta
from cryptography.fernet import Fernet
import requests
import logging
import base64
import json

_logger = logging.getLogger(__name__)


class CloudConnectConfig(models.Model):
    _name = 'cloudconnect.config'
    _description = 'CloudConnect Configuration'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _rec_name = 'name'
    
    name = fields.Char(
        string='Configuration Name',
        required=True,
        tracking=True
    )
    
    api_endpoint = fields.Char(
        string='API Endpoint',
        default='https://hotels.cloudbeds.com/api/v1.2',
        required=True,
        help='Base URL for Cloudbeds API'
    )
    
    client_id = fields.Char(
        string='Client ID',
        required=True,
        tracking=True,
        help='OAuth2 Client ID provided by Cloudbeds'
    )
    
    client_secret = fields.Char(
        string='Client Secret',
        help='OAuth2 Client Secret provided by Cloudbeds'
    )
    
    access_token = fields.Char(
        string='Access Token',
        help='Current OAuth2 access token'
    )
    
    refresh_token = fields.Char(
        string='Refresh Token',
        help='OAuth2 refresh token for renewing access'
    )
    
    token_expires_at = fields.Datetime(
        string='Token Expires At',
        help='Expiration time of the current access token'
    )
    
    redirect_uri = fields.Char(
        string='Redirect URI',
        compute='_compute_redirect_uri',
        help='OAuth2 redirect URI for this instance'
    )
    
    active = fields.Boolean(
        string='Active',
        default=True,
        tracking=True
    )
    
    rate_limit = fields.Integer(
        string='Rate Limit (req/sec)',
        default=5,
        required=True,
        help='Maximum requests per second (5 for standard, 10 for tech partners)'
    )
    
    connection_status = fields.Selection([
        ('disconnected', 'Disconnected'),
        ('connected', 'Connected'),
        ('error', 'Error')
    ], string='Connection Status', default='disconnected', compute='_compute_connection_status', store=True)
    
    last_connection_check = fields.Datetime(
        string='Last Connection Check'
    )
    
    property_ids = fields.One2many(
        'cloudconnect.property', 
        'config_id', 
        string='Properties'
    )
    
    webhook_ids = fields.One2many(
        'cloudconnect.webhook',
        'config_id',
        string='Webhooks'
    )
    
    # Encryption key for sensitive data
    encryption_key = fields.Char(
        string='Encryption Key',
        compute='_compute_encryption_key'
    )
    
    @api.depends('name')
    def _compute_redirect_uri(self):
        """Compute OAuth redirect URI based on instance URL."""
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        for record in self:
            record.redirect_uri = f"{base_url}/cloudconnect/oauth/callback"
    
    @api.depends('name')
    def _compute_encryption_key(self):
        """Generate or retrieve encryption key for sensitive data."""
        ICP = self.env['ir.config_parameter'].sudo()
        for record in self:
            key = ICP.get_param('cloudconnect.encryption_key')
            if not key:
                key = Fernet.generate_key().decode()
                ICP.set_param('cloudconnect.encryption_key', key)
            record.encryption_key = key
    
    @api.depends('access_token', 'token_expires_at')
    def _compute_connection_status(self):
        """Check connection status based on token validity."""
        for record in self:
            if not record.access_token:
                record.connection_status = 'disconnected'
            elif record.token_expires_at and fields.Datetime.now() > record.token_expires_at:
                record.connection_status = 'error'
            else:
                record.connection_status = 'connected'
    
    @api.model
    def create(self, vals):
        """Encrypt sensitive fields on create."""
        if 'client_secret' in vals and vals['client_secret']:
            vals['client_secret'] = self._encrypt_value(vals['client_secret'])
        if 'access_token' in vals and vals['access_token']:
            vals['access_token'] = self._encrypt_value(vals['access_token'])
        if 'refresh_token' in vals and vals['refresh_token']:
            vals['refresh_token'] = self._encrypt_value(vals['refresh_token'])
        return super().create(vals)
    
    def write(self, vals):
        """Encrypt sensitive fields on write."""
        if 'client_secret' in vals and vals['client_secret']:
            vals['client_secret'] = self._encrypt_value(vals['client_secret'])
        if 'access_token' in vals and vals['access_token']:
            vals['access_token'] = self._encrypt_value(vals['access_token'])
        if 'refresh_token' in vals and vals['refresh_token']:
            vals['refresh_token'] = self._encrypt_value(vals['refresh_token'])
        return super().write(vals)
    
    def _encrypt_value(self, value):
        """Encrypt a value using Fernet symmetric encryption."""
        if not value:
            return value
        
        key = self.env['ir.config_parameter'].sudo().get_param('cloudconnect.encryption_key')
        if not key:
            key = Fernet.generate_key().decode()
            self.env['ir.config_parameter'].sudo().set_param('cloudconnect.encryption_key', key)
        
        f = Fernet(key.encode())
        return f.encrypt(value.encode()).decode()
    
    def _decrypt_value(self, encrypted_value):
        """Decrypt a value using Fernet symmetric encryption."""
        if not encrypted_value:
            return encrypted_value
        
        try:
            key = self.env['ir.config_parameter'].sudo().get_param('cloudconnect.encryption_key')
            f = Fernet(key.encode())
            return f.decrypt(encrypted_value.encode()).decode()
        except Exception as e:
            _logger.error(f"Decryption error: {str(e)}")
            return encrypted_value
    
    def get_decrypted_secret(self):
        """Get decrypted client secret."""
        self.ensure_one()
        return self._decrypt_value(self.client_secret)
    
    def get_decrypted_access_token(self):
        """Get decrypted access token."""
        self.ensure_one()
        return self._decrypt_value(self.access_token)
    
    def get_decrypted_refresh_token(self):
        """Get decrypted refresh token."""
        self.ensure_one()
        return self._decrypt_value(self.refresh_token)
    
    @api.constrains('rate_limit')
    def _check_rate_limit(self):
        """Validate rate limit is within acceptable range."""
        for record in self:
            if record.rate_limit < 1 or record.rate_limit > 10:
                raise ValidationError(_("Rate limit must be between 1 and 10 requests per second."))
    
    def action_test_connection(self):
        """Test connection to Cloudbeds API."""
        self.ensure_one()
        
        if not self.access_token:
            raise UserError(_("No access token configured. Please complete OAuth authentication first."))
        
        try:
            # Test API call to check connection
            headers = {
                'Authorization': f'Bearer {self.get_decrypted_access_token()}',
                'Content-Type': 'application/json'
            }
            
            response = requests.get(
                f"{self.api_endpoint}/userinfo",
                headers=headers,
                timeout=10
            )
            
            self.last_connection_check = fields.Datetime.now()
            
            if response.status_code == 200:
                self.message_post(
                    body=_("Connection test successful!"),
                    message_type='notification'
                )
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Success'),
                        'message': _('Connection to Cloudbeds API successful!'),
                        'type': 'success',
                        'sticky': False,
                    }
                }
            else:
                raise UserError(_(
                    "Connection test failed. Status: %s, Response: %s"
                ) % (response.status_code, response.text))
                
        except requests.exceptions.RequestException as e:
            raise UserError(_("Connection error: %s") % str(e))
    
    def action_refresh_token(self):
        """Manually refresh the access token."""
        self.ensure_one()
        return self.refresh_access_token()
    
    def refresh_access_token(self):
        """Refresh access token using refresh token."""
        self.ensure_one()
        
        if not self.refresh_token:
            raise UserError(_("No refresh token available. Please re-authenticate."))
        
        try:
            data = {
                'grant_type': 'refresh_token',
                'client_id': self.client_id,
                'client_secret': self.get_decrypted_secret(),
                'refresh_token': self.get_decrypted_refresh_token(),
            }
            
            response = requests.post(
                f"{self.api_endpoint.replace('/api/v1.2', '')}/oauth/access_token",
                data=data,
                timeout=10
            )
            
            if response.status_code == 200:
                token_data = response.json()
                self.write({
                    'access_token': token_data.get('access_token'),
                    'refresh_token': token_data.get('refresh_token'),
                    'token_expires_at': datetime.now() + timedelta(
                        seconds=token_data.get('expires_in', 3600)
                    )
                })
                
                self.message_post(
                    body=_("Access token refreshed successfully"),
                    message_type='notification'
                )
                
                return True
            else:
                raise UserError(_(
                    "Token refresh failed. Status: %s, Response: %s"
                ) % (response.status_code, response.text))
                
        except requests.exceptions.RequestException as e:
            raise UserError(_("Token refresh error: %s") % str(e))
    
    @api.model
    def _cron_refresh_tokens(self):
        """Cron job to refresh tokens before expiration."""
        configs = self.search([
            ('active', '=', True),
            ('refresh_token', '!=', False)
        ])
        
        for config in configs:
            # Refresh if token expires in less than 30 minutes
            if config.token_expires_at:
                time_until_expiry = config.token_expires_at - datetime.now()
                if time_until_expiry.total_seconds() < 1800:  # 30 minutes
                    try:
                        config.refresh_access_token()
                    except Exception as e:
                        _logger.error(f"Auto token refresh failed for {config.name}: {str(e)}")
    
    def action_open_setup_wizard(self):
        """Open the setup wizard."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('CloudConnect Setup'),
            'res_model': 'cloudconnect.setup.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_config_id': self.id,
            }
        }