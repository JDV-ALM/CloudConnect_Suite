# -*- coding: utf-8 -*-

import logging
import pytz
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class CloudconnectProperty(models.Model):
    _name = 'cloudconnect.property'
    _description = 'CloudConnect Property (Hotel)'
    _rec_name = 'display_name'
    _order = 'name'

    # Basic Information
    cloudbeds_id = fields.Char(
        string='Cloudbeds Property ID',
        required=True,
        index=True,
        help='Unique identifier of the property in Cloudbeds'
    )
    name = fields.Char(
        string='Property Name',
        required=True,
        help='Name of the hotel/property'
    )
    display_name = fields.Char(
        string='Display Name',
        compute='_compute_display_name',
        store=True
    )
    short_name = fields.Char(
        string='Short Name',
        help='Short name for the property'
    )
    
    # Configuration
    config_id = fields.Many2one(
        'cloudconnect.config',
        string='Configuration',
        required=True,
        ondelete='cascade',
        help='CloudConnect configuration for this property'
    )
    active = fields.Boolean(
        string='Active',
        default=True,
        help='Set to false to disable sync for this property'
    )
    sync_enabled = fields.Boolean(
        string='Sync Enabled',
        default=True,
        help='Enable automatic synchronization for this property'
    )
    
    # Location Information
    address_line1 = fields.Char(string='Address Line 1')
    address_line2 = fields.Char(string='Address Line 2')
    city = fields.Char(string='City')
    state = fields.Char(string='State/Province')
    zip_code = fields.Char(string='ZIP Code')
    country_id = fields.Many2one(
        'res.country',
        string='Country'
    )
    
    # Regional Settings
    timezone = fields.Selection(
        selection='_get_timezone_selection',
        string='Timezone',
        default=lambda self: self._context.get('tz') or 'UTC',
        help='Timezone for this property'
    )
    currency_id = fields.Many2one(
        'res.currency',
        string='Currency',
        default=lambda self: self.env.company.currency_id,
        help='Default currency for this property'
    )
    
    # Contact Information
    phone = fields.Char(string='Phone')
    email = fields.Char(string='Email')
    website = fields.Char(string='Website')
    
    # Cloudbeds Specific
    property_type = fields.Char(
        string='Property Type',
        help='Type of property (Hotel, B&B, etc.)'
    )
    room_count = fields.Integer(
        string='Room Count',
        help='Total number of rooms in the property'
    )
    max_occupancy = fields.Integer(
        string='Max Occupancy',
        help='Maximum occupancy of the property'
    )
    
    # Sync Settings
    last_sync_date = fields.Datetime(
        string='Last Sync Date',
        readonly=True,
        help='Last successful synchronization with Cloudbeds'
    )
    last_sync_status = fields.Selection([
        ('success', 'Success'),
        ('error', 'Error'),
        ('partial', 'Partial'),
        ('pending', 'Pending')
    ], string='Last Sync Status', readonly=True)
    
    sync_error_count = fields.Integer(
        string='Sync Error Count',
        default=0,
        help='Number of consecutive sync errors'
    )
    last_sync_error = fields.Text(
        string='Last Sync Error',
        readonly=True
    )
    
    # Statistics
    total_reservations = fields.Integer(
        string='Total Reservations',
        readonly=True,
        help='Total number of synced reservations'
    )
    total_guests = fields.Integer(
        string='Total Guests',
        readonly=True,
        help='Total number of synced guests'
    )
    total_payments = fields.Integer(
        string='Total Payments',
        readonly=True,
        help='Total number of synced payments'
    )
    
    # Relationships
    webhook_ids = fields.One2many(
        'cloudconnect.webhook',
        'property_id',
        string='Webhooks'
    )
    sync_log_ids = fields.One2many(
        'cloudconnect.sync_log',
        'property_id',
        string='Sync Logs'
    )
    
    @api.depends('name', 'cloudbeds_id')
    def _compute_display_name(self):
        for property_rec in self:
            if property_rec.name and property_rec.cloudbeds_id:
                property_rec.display_name = f"{property_rec.name} ({property_rec.cloudbeds_id})"
            elif property_rec.name:
                property_rec.display_name = property_rec.name
            else:
                property_rec.display_name = property_rec.cloudbeds_id or _("New Property")
    
    @api.model
    def _get_timezone_selection(self):
        """Get list of available timezones."""
        return [(tz, tz) for tz in pytz.all_timezones]
    
    def get_timezone_object(self):
        """Get timezone object for this property."""
        return pytz.timezone(self.timezone or 'UTC')
    
    def convert_to_property_timezone(self, dt):
        """Convert datetime to property timezone."""
        if not dt:
            return dt
        
        if dt.tzinfo is None:
            # Assume UTC if no timezone info
            dt = pytz.UTC.localize(dt)
        
        property_tz = self.get_timezone_object()
        return dt.astimezone(property_tz)
    
    def convert_from_property_timezone(self, dt):
        """Convert datetime from property timezone to UTC."""
        if not dt:
            return dt
        
        property_tz = self.get_timezone_object()
        if dt.tzinfo is None:
            dt = property_tz.localize(dt)
        
        return dt.astimezone(pytz.UTC).replace(tzinfo=None)
    
    def update_sync_status(self, status, error_message=None):
        """Update sync status for this property."""
        self.last_sync_date = fields.Datetime.now()
        self.last_sync_status = status
        
        if status == 'error':
            self.sync_error_count += 1
            self.last_sync_error = error_message
        else:
            self.sync_error_count = 0
            self.last_sync_error = False
    
    def reset_sync_errors(self):
        """Reset sync error count and message."""
        self.sync_error_count = 0
        self.last_sync_error = False
    
    def action_sync_now(self):
        """Manual sync action for this property."""
        try:
            # This will be implemented when we have the sync service
            sync_service = self.env['cloudconnect.sync.manager']
            sync_service.sync_property(self.id)
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _("Sync Started"),
                    'message': _("Synchronization has been started for %s") % self.name,
                    'type': 'info',
                }
            }
        except Exception as e:
            _logger.error(f"Manual sync failed for property {self.id}: {e}")
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _("Sync Failed"),
                    'message': str(e),
                    'type': 'danger',
                }
            }
    
    def action_reset_sync_errors(self):
        """Action to reset sync errors."""
        self.reset_sync_errors()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _("Errors Reset"),
                'message': _("Sync errors have been reset for %s") % self.name,
                'type': 'success',
            }
        }
    
    def action_view_sync_logs(self):
        """Action to view sync logs for this property."""
        return {
            'name': _('Sync Logs - %s') % self.name,
            'type': 'ir.actions.act_window',
            'res_model': 'cloudconnect.sync_log',
            'view_mode': 'tree,form',
            'domain': [('property_id', '=', self.id)],
            'context': {'default_property_id': self.id},
        }
    
    def action_view_webhooks(self):
        """Action to view webhooks for this property."""
        return {
            'name': _('Webhooks - %s') % self.name,
            'type': 'ir.actions.act_window',
            'res_model': 'cloudconnect.webhook',
            'view_mode': 'tree,form',
            'domain': [('property_id', '=', self.id)],
            'context': {'default_property_id': self.id},
        }
    
    @api.constrains('cloudbeds_id')
    def _check_cloudbeds_id_unique(self):
        """Ensure Cloudbeds ID is unique per configuration."""
        for property_rec in self:
            duplicate = self.search([
                ('cloudbeds_id', '=', property_rec.cloudbeds_id),
                ('config_id', '=', property_rec.config_id.id),
                ('id', '!=', property_rec.id)
            ])
            if duplicate:
                raise ValidationError(_(
                    "Property with Cloudbeds ID '%s' already exists in this configuration"
                ) % property_rec.cloudbeds_id)
    
    @api.constrains('timezone')
    def _check_timezone(self):
        """Validate timezone."""
        for property_rec in self:
            if property_rec.timezone and property_rec.timezone not in pytz.all_timezones:
                raise ValidationError(_("Invalid timezone: %s") % property_rec.timezone)
    
    @api.model_create_multi
    def create(self, vals_list):
        """Override create to set default values."""
        for vals in vals_list:
            if 'timezone' not in vals and self._context.get('tz'):
                vals['timezone'] = self._context.get('tz')
        return super().create(vals_list)
    
    def write(self, vals):
        """Override write to handle timezone changes."""
        result = super().write(vals)
        
        # If timezone changed, we might need to adjust existing data
        if 'timezone' in vals:
            _logger.info(f"Timezone changed for property {self.id} to {vals['timezone']}")
            # TODO: Implement timezone conversion for existing records if needed
        
        return result