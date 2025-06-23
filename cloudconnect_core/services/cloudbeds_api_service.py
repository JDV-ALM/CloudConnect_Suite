# -*- coding: utf-8 -*-

from odoo import models, api, _
from odoo.exceptions import UserError
import requests
import json
import time
import logging
from datetime import datetime
from functools import wraps

_logger = logging.getLogger(__name__)


def rate_limit(calls_per_second):
    """Decorator to implement rate limiting."""
    min_interval = 1.0 / calls_per_second
    last_called = [0.0]
    
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            elapsed = time.time() - last_called[0]
            left_to_wait = min_interval - elapsed
            if left_to_wait > 0:
                time.sleep(left_to_wait)
            ret = func(*args, **kwargs)
            last_called[0] = time.time()
            return ret
        return wrapper
    return decorator


class CloudbedsAPIService(models.AbstractModel):
    _name = 'cloudconnect.api.service'
    _description = 'Cloudbeds API Service'
    
    def _get_headers(self, config):
        """Get headers for API request."""
        return {
            'Authorization': f'Bearer {config.get_decrypted_access_token()}',
            'Content-Type': 'application/json',
            'Accept': 'application/json',
        }
    
    def _make_request(self, config, method, endpoint, params=None, data=None, retry_count=0):
        """
        Make HTTP request to Cloudbeds API with retry logic.
        
        :param config: cloudconnect.config record
        :param method: HTTP method (GET, POST, PUT, DELETE)
        :param endpoint: API endpoint (e.g., 'getReservation')
        :param params: Query parameters
        :param data: Request body data
        :param retry_count: Current retry attempt
        :return: Response data
        """
        max_retries = 3
        
        # Create sync log
        sync_log = self.env['cloudconnect.sync.log'].create({
            'operation_type': 'api_call',
            'model_name': 'cloudconnect.api.service',
            'action': 'fetch',
            'config_id': config.id,
            'api_endpoint': endpoint,
            'request_data': json.dumps(data or params or {}, indent=2),
            'status': 'pending',
        })
        
        start_time = time.time()
        
        try:
            # Check token expiration
            if config.token_expires_at and datetime.now() > config.token_expires_at:
                _logger.info("Token expired, refreshing...")
                config.refresh_access_token()
            
            # Apply rate limiting based on config
            rate_limiter = rate_limit(config.rate_limit)
            
            @rate_limiter
            def make_request():
                url = f"{config.api_endpoint}/{endpoint}"
                headers = self._get_headers(config)
                
                _logger.info(f"API Request: {method} {url}")
                
                if method == 'GET':
                    return requests.get(url, headers=headers, params=params, timeout=30)
                elif method == 'POST':
                    # For POST, use form data instead of JSON for Cloudbeds API
                    headers['Content-Type'] = 'application/x-www-form-urlencoded'
                    return requests.post(url, headers=headers, data=data or params, timeout=30)
                elif method == 'PUT':
                    headers['Content-Type'] = 'application/x-www-form-urlencoded'
                    return requests.put(url, headers=headers, data=data or params, timeout=30)
                elif method == 'DELETE':
                    return requests.delete(url, headers=headers, params=params, timeout=30)
                else:
                    raise ValueError(f"Unsupported HTTP method: {method}")
            
            response = make_request()
            duration = time.time() - start_time
            
            # Extract request ID for tracking
            request_id = response.headers.get('X-Request-ID', '')
            sync_log.request_id = request_id
            sync_log.http_status = response.status_code
            
            # Handle response
            if response.status_code == 200:
                response_data = response.json()
                
                # Check Cloudbeds API success flag
                if response_data.get('success', True):
                    sync_log.mark_success(response_data, duration)
                    return response_data
                else:
                    # API returned success=false
                    error_msg = response_data.get('message', 'Unknown API error')
                    sync_log.mark_error(error_msg, response.status_code, response_data)
                    raise UserError(_("Cloudbeds API Error: %s") % error_msg)
            
            elif response.status_code == 401:
                # Unauthorized - try refreshing token
                if retry_count == 0:
                    _logger.info("Got 401, attempting token refresh...")
                    config.refresh_access_token()
                    return self._make_request(config, method, endpoint, params, data, retry_count + 1)
                else:
                    sync_log.mark_error("Authentication failed after token refresh", 401)
                    raise UserError(_("Authentication failed. Please re-authenticate."))
            
            elif response.status_code == 429:
                # Rate limit exceeded
                retry_after = int(response.headers.get('Retry-After', 60))
                sync_log.mark_error(f"Rate limit exceeded. Retry after {retry_after} seconds", 429)
                
                if retry_count < max_retries:
                    _logger.warning(f"Rate limit hit, waiting {retry_after} seconds...")
                    time.sleep(retry_after)
                    return self._make_request(config, method, endpoint, params, data, retry_count + 1)
                else:
                    raise UserError(_("Rate limit exceeded. Please try again later."))
            
            else:
                # Other error
                error_text = response.text
                sync_log.mark_error(f"HTTP {response.status_code}: {error_text}", response.status_code)
                
                if retry_count < max_retries and response.status_code >= 500:
                    # Retry on server errors
                    wait_time = 2 ** retry_count  # Exponential backoff
                    _logger.warning(f"Server error, retrying in {wait_time} seconds...")
                    time.sleep(wait_time)
                    return self._make_request(config, method, endpoint, params, data, retry_count + 1)
                else:
                    raise UserError(_(
                        "API request failed.\nStatus: %s\nResponse: %s\nRequest ID: %s"
                    ) % (response.status_code, error_text, request_id))
        
        except requests.exceptions.Timeout:
            sync_log.mark_error("Request timeout", 0)
            if retry_count < max_retries:
                wait_time = 2 ** retry_count
                time.sleep(wait_time)
                return self._make_request(config, method, endpoint, params, data, retry_count + 1)
            else:
                raise UserError(_("Request timeout. Please try again."))
        
        except requests.exceptions.ConnectionError as e:
            sync_log.mark_error(f"Connection error: {str(e)}", 0)
            raise UserError(_("Connection error. Please check your internet connection."))
        
        except Exception as e:
            sync_log.mark_error(f"Unexpected error: {str(e)}", 0)
            raise
    
    # Property Management
    def get_properties(self, config):
        """Get list of properties."""
        response = self._make_request(config, 'GET', 'getHotels')
        return response.get('data', [])
    
    def get_property_details(self, config, property_id=None):
        """Get detailed property information."""
        params = {}
        if property_id:
            params['propertyID'] = property_id
        response = self._make_request(config, 'GET', 'getHotelDetails', params=params)
        return response.get('data', {})
    
    # Reservation Management
    def get_reservation(self, config, reservation_id):
        """Get single reservation."""
        params = {'reservationID': reservation_id}
        response = self._make_request(config, 'GET', 'getReservation', params=params)
        return response.get('data', {})
    
    def get_reservations(self, config, filters=None):
        """Get list of reservations with filters."""
        params = filters or {}
        # Add pagination if not specified
        if 'pageSize' not in params:
            params['pageSize'] = 100
        if 'pageNumber' not in params:
            params['pageNumber'] = 1
            
        response = self._make_request(config, 'GET', 'getReservations', params=params)
        return response.get('data', [])
    
    def create_reservation(self, config, reservation_data):
        """Create new reservation."""
        response = self._make_request(config, 'POST', 'postReservation', data=reservation_data)
        return response.get('data', {})
    
    def update_reservation(self, config, reservation_id, update_data):
        """Update existing reservation."""
        update_data['reservationID'] = reservation_id
        response = self._make_request(config, 'PUT', 'putReservation', data=update_data)
        return response.get('data', {})
    
    # Guest Management
    def get_guest(self, config, guest_id=None, reservation_id=None):
        """Get guest information."""
        params = {}
        if guest_id:
            params['guestID'] = guest_id
        if reservation_id:
            params['reservationID'] = reservation_id
            
        response = self._make_request(config, 'GET', 'getGuest', params=params)
        return response.get('data', {})
    
    def get_guests(self, config, filters=None):
        """Get list of guests."""
        params = filters or {}
        if 'pageSize' not in params:
            params['pageSize'] = 100
            
        response = self._make_request(config, 'GET', 'getGuestList', params=params)
        return response.get('data', [])
    
    def create_guest(self, config, guest_data):
        """Create new guest."""
        response = self._make_request(config, 'POST', 'postGuest', data=guest_data)
        return response.get('data', {})
    
    def update_guest(self, config, guest_id, update_data):
        """Update guest information."""
        update_data['guestID'] = guest_id
        response = self._make_request(config, 'PUT', 'putGuest', data=update_data)
        return response.get('data', {})
    
    # Room Management
    def get_room_types(self, config, property_ids=None):
        """Get room types."""
        params = {}
        if property_ids:
            params['propertyIDs'] = ','.join(map(str, property_ids))
            
        response = self._make_request(config, 'GET', 'getRoomTypes', params=params)
        return response.get('data', [])
    
    def get_rooms(self, config, filters=None):
        """Get list of rooms."""
        params = filters or {}
        response = self._make_request(config, 'GET', 'getRooms', params=params)
        return response.get('data', [])
    
    def get_available_room_types(self, config, start_date, end_date, adults, children, rooms=1):
        """Get available room types for dates."""
        params = {
            'startDate': start_date,
            'endDate': end_date,
            'adults': adults,
            'children': children,
            'rooms': rooms,
        }
        response = self._make_request(config, 'GET', 'getAvailableRoomTypes', params=params)
        return response.get('data', [])
    
    # Rate Management
    def get_rates(self, config, room_type_id, start_date, end_date, adults=1, children=0):
        """Get rates for room type and dates."""
        params = {
            'roomTypeID': room_type_id,
            'startDate': start_date,
            'endDate': end_date,
            'adults': adults,
            'children': children,
            'detailedRates': True,
        }
        response = self._make_request(config, 'GET', 'getRate', params=params)
        return response.get('data', {})
    
    def update_rates(self, config, rate_updates):
        """Update rates (batch operation)."""
        response = self._make_request(config, 'PATCH', 'patchRate', data={'rates': rate_updates})
        return response.get('data', {})
    
    # Payment Management
    def get_payments(self, config, reservation_id=None, guest_id=None):
        """Get payments."""
        params = {}
        if reservation_id:
            params['reservationID'] = reservation_id
        if guest_id:
            params['guestID'] = guest_id
            
        response = self._make_request(config, 'GET', 'getPayments', params=params)
        return response.get('data', [])
    
    def create_payment(self, config, payment_data):
        """Create payment."""
        response = self._make_request(config, 'POST', 'postPayment', data=payment_data)
        return response.get('data', {})
    
    # Webhook Management
    def get_webhooks(self, config):
        """Get list of registered webhooks."""
        response = self._make_request(config, 'GET', 'getWebhooks')
        return response.get('data', [])
    
    def post_webhook(self, config, webhook_data):
        """Register new webhook."""
        response = self._make_request(config, 'POST', 'postWebhook', data=webhook_data)
        return response.get('data', {})
    
    def delete_webhook(self, config, subscription_id):
        """Delete webhook subscription."""
        params = {'subscriptionID': subscription_id}
        response = self._make_request(config, 'DELETE', 'deleteWebhook', params=params)
        return response.get('data', {})
    
    # Housekeeping
    def get_housekeeping_status(self, config, filters=None):
        """Get housekeeping status."""
        params = filters or {}
        response = self._make_request(config, 'GET', 'getHousekeepingStatus', params=params)
        return response.get('data', [])
    
    def update_housekeeping_status(self, config, room_id, status_data):
        """Update housekeeping status."""
        status_data['roomID'] = room_id
        response = self._make_request(config, 'POST', 'postHousekeepingStatus', data=status_data)
        return response.get('data', {})
    
    # Dashboard
    def get_dashboard(self, config, date=None):
        """Get dashboard data."""
        params = {}
        if date:
            params['date'] = date
            
        response = self._make_request(config, 'GET', 'getDashboard', params=params)
        return response.get('data', {})