# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
import logging

_logger = logging.getLogger(__name__)


class CloudConnectProperty(models.Model):
    _name = 'cloudconnect.property'
    _description = 'CloudConnect Property'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _rec_name = 'name'
    _order = 'name'
    
    cloudbeds_id = fields.Char(
        string='Cloudbeds Property ID',
        required=True,
        index=True,
        tracking=True,
        help='Unique identifier for this property in Cloudbeds'
    )
    
    name = fields.Char(
        string='Property Name',
        required=True,
        tracking=True
    )
    
    config_id = fields.Many2one(
        'cloudconnect.config',
        string='Configuration',
        required=True,
        ondelete='cascade'
    )
    
    currency_id = fields.Many2one(
        'res.currency',
        string='Default Currency',
        required=True,
        default=lambda self: self.env.company.currency_id
    )
    
    sync_enabled = fields.Boolean(
        string='Synchronization Enabled',
        default=True,
        tracking=True,
        help='Enable/disable synchronization for this property'
    )
    
    timezone = fields.Selection(
        selection='_get_timezone_selection',
        string='Property Timezone',
        default='UTC',
        required=True,
        help='Timezone of the property location'
    )
    
    # Property details from Cloudbeds
    property_type = fields.Char(string='Property Type')
    address = fields.Text(string='Address')
    city = fields.Char(string='City')
    state = fields.Char(string='State/Province')
    country_id = fields.Many2one('res.country', string='Country')
    postal_code = fields.Char(string='Postal Code')
    phone = fields.Char(string='Phone')
    email = fields.Char(string='Email')
    website = fields.Char(string='Website')
    
    # Sync status
    last_sync_date = fields.Datetime(
        string='Last Synchronization',
        readonly=True
    )
    
    last_sync_status = fields.Selection([
        ('success', 'Success'),
        ('partial', 'Partial Success'),
        ('failed', 'Failed')
    ], string='Last Sync Status', readonly=True)
    
    last_sync_message = fields.Text(
        string='Last Sync Message',
        readonly=True
    )
    
    # Related records counts
    sync_log_count = fields.Integer(
        string='Sync Logs',
        compute='_compute_sync_log_count'
    )
    
    webhook_count = fields.Integer(
        string='Active Webhooks',
        compute='_compute_webhook_count'
    )
    
    # Property settings
    auto_sync_reservations = fields.Boolean(
        string='Auto-sync Reservations',
        default=True,
        help='Automatically synchronize reservations'
    )
    
    auto_sync_guests = fields.Boolean(
        string='Auto-sync Guests',
        default=True,
        help='Automatically synchronize guest information'
    )
    
    auto_sync_rates = fields.Boolean(
        string='Auto-sync Rates',
        default=True,
        help='Automatically synchronize room rates'
    )
    
    def _get_timezone_selection(self):
        """Get timezone selection from pytz."""
        try:
            import pytz
            return [(tz, tz) for tz in pytz.all_timezones]
        except ImportError:
            _logger.warning("pytz not installed, using basic timezone list")
            return [
                ('UTC', 'UTC'),
                ('US/Eastern', 'US/Eastern'),
                ('US/Central', 'US/Central'),
                ('US/Mountain', 'US/Mountain'),
                ('US/Pacific', 'US/Pacific'),
                ('Europe/London', 'Europe/London'),
                ('Europe/Paris', 'Europe/Paris'),
                ('Asia/Tokyo', 'Asia/Tokyo'),
            ]
    
    def _compute_sync_log_count(self):
        """Compute number of sync logs for this property."""
        SyncLog = self.env['cloudconnect.sync.log']
        for record in self:
            record.sync_log_count = SyncLog.search_count([
                ('property_id', '=', record.id)
            ])
    
    def _compute_webhook_count(self):
        """Compute number of active webhooks for this property."""
        for record in self:
            record.webhook_count = len(record.config_id.webhook_ids.filtered(
                lambda w: w.active and w.property_id == record
            ))
    
    @api.constrains('cloudbeds_id', 'config_id')
    def _check_unique_cloudbeds_id(self):
        """Ensure Cloudbeds ID is unique per configuration."""
        for record in self:
            duplicate = self.search([
                ('cloudbeds_id', '=', record.cloudbeds_id),
                ('config_id', '=', record.config_id.id),
                ('id', '!=', record.id)
            ])
            if duplicate:
                raise ValidationError(_(
                    "Property with Cloudbeds ID %s already exists in this configuration."
                ) % record.cloudbeds_id)
    
    def action_sync_now(self):
        """Trigger immediate synchronization for this property."""
        self.ensure_one()
        
        if not self.sync_enabled:
            raise ValidationError(_("Synchronization is disabled for this property."))
        
        if not self.config_id.access_token:
            raise ValidationError(_("No valid access token. Please authenticate first."))
        
        # Trigger sync through sync manager
        sync_manager = self.env['cloudconnect.sync.manager']
        return sync_manager.sync_property(self)
    
    def action_view_sync_logs(self):
        """View sync logs for this property."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Sync Logs - %s') % self.name,
            'res_model': 'cloudconnect.sync.log',
            'view_mode': 'tree,form',
            'domain': [('property_id', '=', self.id)],
            'context': {
                'default_property_id': self.id,
            }
        }
    
    def action_configure_webhooks(self):
        """Open webhook configuration for this property."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Webhooks - %s') % self.name,
            'res_model': 'cloudconnect.webhook',
            'view_mode': 'tree,form',
            'domain': [
                ('config_id', '=', self.config_id.id),
                ('property_id', '=', self.id)
            ],
            'context': {
                'default_config_id': self.config_id.id,
                'default_property_id': self.id,
            }
        }
    
    def toggle_sync_enabled(self):
        """Toggle synchronization status."""
        for record in self:
            record.sync_enabled = not record.sync_enabled
            
            # Log the change
            if record.sync_enabled:
                record.message_post(
                    body=_("Synchronization enabled"),
                    message_type='notification'
                )
            else:
                record.message_post(
                    body=_("Synchronization disabled"),
                    message_type='notification'
                )
    
    def update_sync_status(self, status, message=None):
        """Update synchronization status and log."""
        self.ensure_one()
        self.write({
            'last_sync_date': fields.Datetime.now(),
            'last_sync_status': status,
            'last_sync_message': message or ''
        })
        
        # Post message about sync status
        status_label = dict(self._fields['last_sync_status'].selection).get(status)
        body = _("Synchronization completed: %s") % status_label
        if message:
            body += f"\n{message}"
        
        self.message_post(
            body=body,
            message_type='notification'
        )
    
    @api.model
    def sync_properties_from_cloudbeds(self, config_id=None):
        """Sync property list from Cloudbeds."""
        Config = self.env['cloudconnect.config']
        
        if config_id:
            configs = Config.browse(config_id)
        else:
            configs = Config.search([('active', '=', True)])
        
        for config in configs:
            try:
                # This would call the API service to get properties
                api_service = self.env['cloudconnect.api.service']
                properties = api_service.get_properties(config)
                
                for prop_data in properties:
                    self._create_or_update_property(config, prop_data)
                    
            except Exception as e:
                _logger.error(f"Error syncing properties: {str(e)}")
    
    def _create_or_update_property(self, config, property_data):
        """Create or update a property from Cloudbeds data."""
        existing = self.search([
            ('cloudbeds_id', '=', property_data['id']),
            ('config_id', '=', config.id)
        ])
        
        vals = {
            'cloudbeds_id': str(property_data['id']),
            'name': property_data['name'],
            'config_id': config.id,
            'property_type': property_data.get('type'),
            'address': property_data.get('address'),
            'city': property_data.get('city'),
            'state': property_data.get('state'),
            'postal_code': property_data.get('zip'),
            'phone': property_data.get('phone'),
            'email': property_data.get('email'),
            'website': property_data.get('website'),
        }
        
        # Try to match country
        if property_data.get('country'):
            country = self.env['res.country'].search([
                ('code', '=', property_data['country'])
            ], limit=1)
            if country:
                vals['country_id'] = country.id
        
        if existing:
            existing.write(vals)
            return existing
        else:
            return self.create(vals)