# -*- coding: utf-8 -*-

import logging
import json
from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)


class CloudconnectWebhookController(http.Controller):
    
    @http.route('/cloudconnect/webhook/<string:property_id>/<string:event_type>', 
                type='http', auth='none', methods=['POST'], csrf=False)
    def receive_webhook(self, property_id, event_type, **kwargs):
        """
        Main webhook endpoint for receiving Cloudbeds events.
        
        URL format: /cloudconnect/webhook/{property_id}/{event_type}
        Example: /cloudconnect/webhook/12345/reservation_created
        """
        try:
            # Log the incoming webhook
            _logger.info(f"Webhook received: property_id={property_id}, event_type={event_type}")
            
            # Get request data
            payload = request.httprequest.get_data(as_text=True)
            headers = dict(request.httprequest.headers)
            
            # Basic validation
            if not payload:
                _logger.warning("Empty webhook payload received")
                return self._error_response("Empty payload", 400)
            
            # Validate property_id format
            try:
                int(property_id)  # Cloudbeds property IDs are integers
            except ValueError:
                _logger.warning(f"Invalid property_id format: {property_id}")
                return self._error_response("Invalid property ID", 400)
            
            # Validate event_type format
            if not self._is_valid_event_type(event_type):
                _logger.warning(f"Invalid event_type: {event_type}")
                return self._error_response("Invalid event type", 400)
            
            # Process the webhook
            webhook_processor = request.env['cloudconnect.webhook.processor'].sudo()
            result = webhook_processor.process_webhook(property_id, event_type, payload, headers)
            
            # Return appropriate response
            if result.get('success'):
                return self._success_response(result.get('message', 'Webhook processed'))
            else:
                error_msg = result.get('error', 'Unknown error')
                _logger.error(f"Webhook processing failed: {error_msg}")
                return self._error_response(error_msg, 500)
                
        except Exception as e:
            _logger.error(f"Webhook controller error: {e}", exc_info=True)
            return self._error_response("Internal server error", 500)
    
    @http.route('/cloudconnect/webhook/health', type='http', auth='none', methods=['GET'])
    def health_check(self, **kwargs):
        """Health check endpoint for webhook service."""
        return self._success_response("CloudConnect webhook service is healthy")
    
    @http.route('/cloudconnect/webhook/test/<string:property_id>/<string:event_type>', 
                type='http', auth='user', methods=['POST'])
    def test_webhook(self, property_id, event_type, **kwargs):
        """Test webhook endpoint (requires authentication)."""
        try:
            # Create test payload
            test_payload = {
                'version': '1.0',
                'timestamp': 1640995200.0,  # Test timestamp
                'event': f'{self._get_cloudbeds_object(event_type)}/{self._get_cloudbeds_action(event_type)}',
                'propertyID': int(property_id),
                'test': True,
                'message': 'This is a test webhook event'
            }
            
            # Add event-specific test data
            if 'reservation' in event_type:
                test_payload['reservationID'] = '999999999'
                test_payload['startDate'] = '2024-01-01'
                test_payload['endDate'] = '2024-01-02'
            elif 'guest' in event_type:
                test_payload['guestID'] = 999999
                test_payload['guestId_str'] = '999999'
            elif 'transaction' in event_type or 'payment' in event_type:
                test_payload['transactionID'] = '999999999'
                test_payload['amount'] = 100.00
            
            # Process test webhook
            webhook_processor = request.env['cloudconnect.webhook.processor']
            result = webhook_processor.process_webhook(
                property_id, event_type, json.dumps(test_payload)
            )
            
            if result.get('success'):
                return request.render('cloudconnect_core.webhook_test_success', {
                    'property_id': property_id,
                    'event_type': event_type,
                    'result': result,
                    'payload': test_payload
                })
            else:
                return request.render('cloudconnect_core.webhook_test_error', {
                    'property_id': property_id,
                    'event_type': event_type,
                    'error': result.get('error', 'Unknown error'),
                    'payload': test_payload
                })
                
        except Exception as e:
            _logger.error(f"Webhook test error: {e}")
            return request.render('cloudconnect_core.webhook_test_error', {
                'property_id': property_id,
                'event_type': event_type,
                'error': str(e),
                'payload': None
            })
    
    def _success_response(self, message):
        """Return a success HTTP response."""
        response = request.make_response(
            json.dumps({'success': True, 'message': message}),
            headers=[('Content-Type', 'application/json')]
        )
        response.status_code = 200
        return response
    
    def _error_response(self, message, status_code=400):
        """Return an error HTTP response."""
        response = request.make_response(
            json.dumps({'success': False, 'error': message}),
            headers=[('Content-Type', 'application/json')]
        )
        response.status_code = status_code
        return response
    
    def _is_valid_event_type(self, event_type):
        """Validate if event_type is supported."""
        valid_events = [
            # Reservations
            'reservation_created', 'reservation_status_changed', 'reservation_dates_changed',
            'reservation_accommodation_changed', 'reservation_deleted', 'reservation_notes_changed',
            
            # Guests
            'guest_created', 'guest_assigned', 'guest_removed', 
            'guest_details_changed', 'guest_accommodation_changed',
            
            # Payments/Transactions
            'transaction_created', 'payment_created', 'payment_updated', 'payment_voided',
            
            # Items
            'item_sold', 'item_voided', 'item_updated',
            
            # Room Management
            'room_checkin', 'room_checkout', 'roomblock_created', 'roomblock_removed',
            
            # Housekeeping
            'housekeeping_status_changed', 'room_condition_changed',
            
            # Integration
            'integration_appstate_changed', 'integration_appsettings_changed',
        ]
        
        return event_type in valid_events
    
    def _get_cloudbeds_object(self, event_type):
        """Get Cloudbeds object type from event type."""
        if event_type.startswith('reservation_'):
            return 'reservation'
        elif event_type.startswith('guest_'):
            return 'guest'
        elif event_type.startswith('transaction_') or event_type.startswith('payment_'):
            return 'transaction'
        elif event_type.startswith('item_'):
            return 'item'
        elif event_type.startswith('room'):
            return 'room'
        elif event_type.startswith('housekeeping_'):
            return 'housekeeping'
        elif event_type.startswith('integration_'):
            return 'integration'
        else:
            return 'unknown'
    
    def _get_cloudbeds_action(self, event_type):
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
            'room_checkin': 'checkin',
            'room_checkout': 'checkout',
            'roomblock_created': 'created',
            'roomblock_removed': 'removed',
            'housekeeping_status_changed': 'status_changed',
            'room_condition_changed': 'condition_changed',
            'integration_appstate_changed': 'appstate_changed',
            'integration_appsettings_changed': 'appsettings_changed',
        }
        return action_map.get(event_type, 'unknown')