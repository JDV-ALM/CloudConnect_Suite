# -*- coding: utf-8 -*-

from odoo import http, _
from odoo.http import request
import json
import logging
import hmac
import hashlib
from werkzeug.exceptions import Forbidden, BadRequest

_logger = logging.getLogger(__name__)


class CloudConnectWebhookController(http.Controller):
    """Controller to handle incoming webhooks from Cloudbeds."""
    
    @http.route([
        '/cloudconnect/webhook/<string:property_id>/<path:event_type>',
        '/cloudconnect/webhook/all/<path:event_type>'
    ], type='json', auth='public', methods=['POST'], csrf=False)
    def webhook_endpoint(self, event_type=None, property_id=None, **kwargs):
        """
        Main webhook endpoint for Cloudbeds events.
        
        Routes:
        - /cloudconnect/webhook/<property_id>/<event_type> - For property-specific webhooks
        - /cloudconnect/webhook/all/<event_type> - For all properties webhooks
        """
        try:
            # Log incoming webhook
            _logger.info(f"Webhook received: event_type={event_type}, property_id={property_id}")
            
            # Get request data
            data = request.get_json_data()
            if not data:
                _logger.error("No JSON data in webhook request")
                return {'success': False, 'error': 'No data provided'}
            
            # Validate webhook signature if provided
            signature = request.httprequest.headers.get('X-Webhook-Signature')
            if signature and not self._validate_signature(event_type, property_id, data, signature):
                _logger.warning(f"Invalid webhook signature for event {event_type}")
                raise Forbidden("Invalid signature")
            
            # Process webhook
            webhook_model = request.env['cloudconnect.webhook'].sudo()
            success = webhook_model.process_webhook_event(event_type, property_id, data)
            
            if success:
                return {'success': True}
            else:
                return {'success': False, 'error': 'Webhook processing failed'}
                
        except Exception as e:
            _logger.error(f"Error processing webhook: {str(e)}", exc_info=True)
            return {'success': False, 'error': str(e)}
    
    @http.route('/cloudconnect/oauth/callback', type='http', auth='public', website=True)
    def oauth_callback(self, code=None, state=None, error=None, **kwargs):
        """OAuth2 callback endpoint."""
        if error:
            # OAuth error
            return request.render('cloudconnect_core.oauth_error', {
                'error': error,
                'error_description': kwargs.get('error_description', 'Unknown error')
            })
        
        if not code:
            return request.render('cloudconnect_core.oauth_error', {
                'error': 'missing_code',
                'error_description': 'Authorization code not provided'
            })
        
        # Display the authorization code for manual entry in wizard
        return request.render('cloudconnect_core.oauth_success', {
            'code': code,
            'state': state
        })
    
    @http.route('/cloudconnect/health', type='json', auth='public', methods=['GET'])
    def health_check(self, **kwargs):
        """Health check endpoint for monitoring."""
        try:
            # Check if module is installed
            module = request.env['ir.module.module'].sudo().search([
                ('name', '=', 'cloudconnect_core'),
                ('state', '=', 'installed')
            ], limit=1)
            
            if not module:
                return {
                    'status': 'error',
                    'message': 'CloudConnect Core module not installed'
                }
            
            # Check for active configurations
            config_count = request.env['cloudconnect.config'].sudo().search_count([
                ('active', '=', True)
            ])
            
            return {
                'status': 'ok',
                'module_version': module.installed_version,
                'active_configs': config_count,
                'webhook_endpoint': '/cloudconnect/webhook/{property_id}/{event_type}'
            }
            
        except Exception as e:
            return {
                'status': 'error',
                'message': str(e)
            }
    
    def _validate_signature(self, event_type, property_id, data, signature):
        """Validate webhook signature using HMAC."""
        try:
            # Find the webhook configuration
            webhook_model = request.env['cloudconnect.webhook'].sudo()
            
            domain = [
                ('event_type', '=', event_type),
                ('active', '=', True)
            ]
            
            if property_id and property_id != 'all':
                property = request.env['cloudconnect.property'].sudo().search([
                    ('cloudbeds_id', '=', property_id)
                ], limit=1)
                if property:
                    domain.append(('property_id', '=', property.id))
            else:
                domain.append(('property_id', '=', False))
            
            webhook = webhook_model.search(domain, limit=1)
            
            if not webhook:
                _logger.warning(f"No webhook configuration found for validation")
                return True  # Allow if no webhook configured
            
            # Validate signature
            payload = json.dumps(data, sort_keys=True)
            return webhook.validate_webhook_signature(payload, signature)
            
        except Exception as e:
            _logger.error(f"Error validating webhook signature: {str(e)}")
            return False
    
    @http.route('/cloudconnect/test/webhook', type='json', auth='user', methods=['POST'])
    def test_webhook(self, webhook_id=None, **kwargs):
        """Test endpoint for webhook configuration."""
        if not webhook_id:
            return {'success': False, 'error': 'webhook_id required'}
        
        webhook = request.env['cloudconnect.webhook'].browse(int(webhook_id))
        if not webhook.exists():
            return {'success': False, 'error': 'Webhook not found'}
        
        # Check access rights
        webhook.check_access_rights('write')
        webhook.check_access_rule('write')
        
        # Create test event
        test_event = {
            'version': '1.0',
            'timestamp': 1234567890.123456,
            'event': webhook.event_type,
            'propertyID': webhook.property_id.cloudbeds_id if webhook.property_id else 12345,
            'propertyID_str': str(webhook.property_id.cloudbeds_id if webhook.property_id else 12345),
            'test': True,
            'test_data': {
                'message': 'This is a test webhook event',
                'triggered_by': request.env.user.name,
                'webhook_id': webhook.id
            }
        }
        
        # Process test event
        try:
            success = webhook.process_webhook_event(
                webhook.event_type,
                webhook.property_id.cloudbeds_id if webhook.property_id else None,
                test_event
            )
            
            if success:
                return {
                    'success': True,
                    'message': 'Test webhook processed successfully'
                }
            else:
                return {
                    'success': False,
                    'error': 'Test webhook processing failed'
                }
                
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }