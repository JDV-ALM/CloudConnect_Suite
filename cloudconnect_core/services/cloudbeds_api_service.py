# -*- coding: utf-8 -*-

import logging
import requests
import time
import json
from datetime import datetime, timedelta
from threading import Lock
from odoo import models, api, _
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class CloudbedsAPIService(models.AbstractModel):
    _name = 'cloudconnect.api.service'
    _description = 'Cloudbeds API Service'

    # Rate limiting storage (class-level to persist across instances)
    _rate_limiters = {}
    _rate_limiter_lock = Lock()

    def __init__(self, pool, cr):
        super().__init__(pool, cr)
        self._session = None

    def _get_session(self):
        """Get or create a requests session with proper configuration."""
        if not self._session:
            self._session = requests.Session()
            self._session.headers.update({
                'User-Agent': 'CloudConnect-Odoo/1.0',
                'Accept': 'application/json',
                'Content-Type': 'application/x-www-form-urlencoded',
            })
        return self._session

    def _get_rate_limiter(self, config_id):
        """Get or create rate limiter for a configuration."""
        with self._rate_limiter_lock:
            if config_id not in self._rate_limiters:
                config = self.env['cloudconnect.config'].browse(config_id)
                self._rate_limiters[config_id] = {
                    'requests_per_second': config.rate_limit_requests,
                    'burst_tolerance': config.rate_limit_burst,
                    'tokens': config.rate_limit_burst,
                    'last_refill': time.time(),
                    'lock': Lock(),
                }
            return self._rate_limiters[config_id]

    def _wait_for_rate_limit(self, config_id):
        """Implement token bucket rate limiting."""
        limiter = self._get_rate_limiter(config_id)
        
        with limiter['lock']:
            now = time.time()
            time_passed = now - limiter['last_refill']
            
            # Refill tokens based on time passed
            tokens_to_add = time_passed * limiter['requests_per_second']
            limiter['tokens'] = min(
                limiter['burst_tolerance'],
                limiter['tokens'] + tokens_to_add
            )
            limiter['last_refill'] = now
            
            # Check if we have tokens available
            if limiter['tokens'] >= 1:
                limiter['tokens'] -= 1
                return  # We can proceed
            
            # Calculate wait time
            wait_time = (1 - limiter['tokens']) / limiter['requests_per_second']
            _logger.info(f"Rate limiting: waiting {wait_time:.2f} seconds")
            time.sleep(wait_time)
            
            # After waiting, we should have a token
            limiter['tokens'] = 0
            limiter['last_refill'] = time.time()

    def _make_request(self, config, method, endpoint, data=None, params=None, 
                     property_id=None, timeout=30, retries=3):
        """Make a request to Cloudbeds API with error handling and retries."""
        
        # Ensure we have a valid access token
        if config.is_token_expired():
            if not config.refresh_access_token():
                raise UserError(_("Failed to refresh access token"))
        
        access_token = config.get_access_token()
        if not access_token:
            raise UserError(_("No valid access token available"))
        
        # Apply rate limiting
        self._wait_for_rate_limit(config.id)
        
        # Prepare request
        url = f"{config.api_endpoint.rstrip('/')}/{endpoint.lstrip('/')}"
        headers = {
            'Authorization': f'Bearer {access_token}',
        }
        
        # Add property ID to params if specified
        if property_id and params is None:
            params = {}
        if property_id:
            params['propertyID'] = property_id
        
        session = self._get_session()
        
        # Generate request ID for tracking
        request_id = f"odoo_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{id(self)}"
        headers['X-Request-ID'] = request_id
        
        # Create sync log entry
        sync_log = None
        if property_id:
            property_obj = self.env['cloudconnect.property'].search([
                ('cloudbeds_id', '=', str(property_id))
            ], limit=1)
            if property_obj:
                sync_log = self.env['cloudconnect.sync_log'].create({
                    'property_id': property_obj.id,
                    'operation_type': 'api_call',
                    'model_name': 'api.request',
                    'cloudbeds_id': endpoint,
                    'status': 'processing',
                    'request_id': request_id,
                    'api_endpoint': endpoint,
                    'request_method': method.upper(),
                    'request_data': json.dumps(data) if data else None,
                })
                sync_log.mark_as_started()
        
        last_exception = None
        
        for attempt in range(retries + 1):
            try:
                _logger.debug(f"API Request [{request_id}]: {method.upper()} {url}")
                
                # Make the request
                if method.upper() == 'GET':
                    response = session.get(url, params=params, headers=headers, timeout=timeout)
                elif method.upper() == 'POST':
                    response = session.post(url, data=data, params=params, headers=headers, timeout=timeout)
                elif method.upper() == 'PUT':
                    response = session.put(url, data=data, params=params, headers=headers, timeout=timeout)
                elif method.upper() == 'PATCH':
                    response = session.patch(url, data=data, params=params, headers=headers, timeout=timeout)
                elif method.upper() == 'DELETE':
                    response = session.delete(url, params=params, headers=headers, timeout=timeout)
                else:
                    raise ValueError(f"Unsupported HTTP method: {method}")
                
                # Log response details
                if sync_log:
                    sync_log.http_status_code = response.status_code
                
                # Handle response
                if response.status_code == 200:
                    try:
                        response_data = response.json()
                        if sync_log:
                            sync_log.mark_as_success(response_data)
                        return response_data
                    except json.JSONDecodeError as e:
                        error_msg = f"Invalid JSON response: {e}"
                        _logger.error(f"API Error [{request_id}]: {error_msg}")
                        if sync_log:
                            sync_log.mark_as_error(error_msg, response_data=response.text)
                        raise UserError(error_msg)
                
                elif response.status_code == 401:
                    # Token expired, try to refresh
                    if attempt == 0 and config.refresh_access_token():
                        access_token = config.get_access_token()
                        headers['Authorization'] = f'Bearer {access_token}'
                        continue
                    else:
                        error_msg = "Authentication failed - invalid or expired token"
                        if sync_log:
                            sync_log.mark_as_error(error_msg, 'AUTH_FAILED', response.status_code, response.text)
                        raise UserError(error_msg)
                
                elif response.status_code == 429:
                    # Rate limited by server
                    wait_time = 60  # Wait 1 minute for server rate limiting
                    _logger.warning(f"Server rate limiting [{request_id}]: waiting {wait_time} seconds")
                    time.sleep(wait_time)
                    continue
                
                elif response.status_code >= 500:
                    # Server error - retry
                    if attempt < retries:
                        wait_time = 2 ** attempt  # Exponential backoff
                        _logger.warning(f"Server error [{request_id}]: HTTP {response.status_code}, retrying in {wait_time} seconds")
                        time.sleep(wait_time)
                        continue
                    else:
                        error_msg = f"Server error: HTTP {response.status_code}"
                        if sync_log:
                            sync_log.mark_as_error(error_msg, 'SERVER_ERROR', response.status_code, response.text)
                        raise UserError(error_msg)
                
                else:
                    # Other client errors
                    try:
                        error_data = response.json()
                        error_msg = error_data.get('message', f"HTTP {response.status_code}")
                    except:
                        error_msg = f"HTTP {response.status_code}: {response.text}"
                    
                    if sync_log:
                        sync_log.mark_as_error(error_msg, 'CLIENT_ERROR', response.status_code, response.text)
                    raise UserError(error_msg)
                
            except requests.exceptions.Timeout:
                last_exception = UserError(f"Request timeout after {timeout} seconds")
                if attempt < retries:
                    _logger.warning(f"Timeout [{request_id}]: retrying ({attempt + 1}/{retries})")
                    continue
                    
            except requests.exceptions.ConnectionError as e:
                last_exception = UserError(f"Connection error: {e}")
                if attempt < retries:
                    _logger.warning(f"Connection error [{request_id}]: retrying ({attempt + 1}/{retries})")
                    time.sleep(2 ** attempt)
                    continue
                    
            except requests.exceptions.RequestException as e:
                last_exception = UserError(f"Request error: {e}")
                break  # Don't retry for other request exceptions
        
        # If we get here, all retries failed
        if sync_log:
            sync_log.mark_as_error(str(last_exception), 'REQUEST_FAILED')
        raise last_exception

    # Convenience methods for different HTTP verbs
    def get(self, config, endpoint, params=None, property_id=None, **kwargs):
        """Make a GET request to Cloudbeds API."""
        return self._make_request(config, 'GET', endpoint, params=params, 
                                 property_id=property_id, **kwargs)

    def post(self, config, endpoint, data=None, params=None, property_id=None, **kwargs):
        """Make a POST request to Cloudbeds API."""
        return self._make_request(config, 'POST', endpoint, data=data, params=params,
                                 property_id=property_id, **kwargs)

    def put(self, config, endpoint, data=None, params=None, property_id=None, **kwargs):
        """Make a PUT request to Cloudbeds API."""
        return self._make_request(config, 'PUT', endpoint, data=data, params=params,
                                 property_id=property_id, **kwargs)

    def patch(self, config, endpoint, data=None, params=None, property_id=None, **kwargs):
        """Make a PATCH request to Cloudbeds API."""
        return self._make_request(config, 'PATCH', endpoint, data=data, params=params,
                                 property_id=property_id, **kwargs)

    def delete(self, config, endpoint, params=None, property_id=None, **kwargs):
        """Make a DELETE request to Cloudbeds API."""
        return self._make_request(config, 'DELETE', endpoint, params=params,
                                 property_id=property_id, **kwargs)

    # High-level API methods
    def get_hotels(self, config):
        """Get list of hotels/properties."""
        return self.get(config, 'getHotels')

    def get_hotel_details(self, config, property_id):
        """Get detailed information about a specific property."""
        return self.get(config, 'getHotelDetails', property_id=property_id)

    def get_reservations(self, config, property_id, date_from=None, date_to=None, **filters):
        """Get reservations for a property."""
        params = {}
        if date_from:
            params['checkInFrom'] = date_from
        if date_to:
            params['checkInTo'] = date_to
        params.update(filters)
        
        return self.get(config, 'getReservations', params=params, property_id=property_id)

    def get_reservation(self, config, property_id, reservation_id):
        """Get specific reservation details."""
        params = {'reservationID': reservation_id}
        return self.get(config, 'getReservation', params=params, property_id=property_id)

    def get_guests(self, config, property_id, **filters):
        """Get guests for a property."""
        return self.get(config, 'getGuestList', params=filters, property_id=property_id)

    def get_guest(self, config, property_id, guest_id=None, reservation_id=None):
        """Get specific guest details."""
        params = {}
        if guest_id:
            params['guestID'] = guest_id
        if reservation_id:
            params['reservationID'] = reservation_id
        return self.get(config, 'getGuest', params=params, property_id=property_id)

    def get_payments(self, config, property_id, reservation_id=None, **filters):
        """Get payments for a property."""
        params = filters.copy()
        if reservation_id:
            params['reservationID'] = reservation_id
        return self.get(config, 'getPayments', params=params, property_id=property_id)

    def get_transactions(self, config, property_id, **filters):
        """Get transactions for a property."""
        return self.get(config, 'getTransactions', params=filters, property_id=property_id)

    def get_items(self, config, property_id, category_id=None):
        """Get items/products for a property."""
        params = {}
        if category_id:
            params['itemCategoryID'] = category_id
        return self.get(config, 'getItems', params=params, property_id=property_id)

    def get_item_categories(self, config, property_id):
        """Get item categories for a property."""
        return self.get(config, 'getItemCategories', property_id=property_id)

    def get_room_types(self, config, property_id):
        """Get room types for a property."""
        return self.get(config, 'getRoomTypes', property_id=property_id)

    def get_rooms(self, config, property_id, room_type_id=None):
        """Get rooms for a property."""
        params = {}
        if room_type_id:
            params['roomTypeID'] = room_type_id
        return self.get(config, 'getRooms', params=params, property_id=property_id)

    def post_webhook(self, config, property_id, object_type, action, endpoint_url):
        """Register a webhook with Cloudbeds."""
        data = {
            'propertyID': property_id,
            'object': object_type,
            'action': action,
            'endpointUrl': endpoint_url
        }
        return self.post(config, 'postWebhook', data=data)

    def delete_webhook(self, config, subscription_id):
        """Unregister a webhook from Cloudbeds."""
        params = {'subscriptionID': subscription_id}
        return self.delete(config, 'deleteWebhook', params=params)

    def get_webhooks(self, config, property_id):
        """Get registered webhooks for a property."""
        return self.get(config, 'getWebhooks', property_id=property_id)

    @api.model
    def test_api_connection(self, config_id):
        """Test API connection for a configuration."""
        config = self.env['cloudconnect.config'].browse(config_id)
        try:
            result = self.get_hotels(config)
            return {
                'success': True,
                'message': _("API connection test successful"),
                'data': result
            }
        except Exception as e:
            return {
                'success': False,
                'message': str(e),
                'data': None
            }

    @api.model
    def sync_properties(self, config_id):
        """Sync properties from Cloudbeds to update local property list."""
        config = self.env['cloudconnect.config'].browse(config_id)
        
        try:
            hotels_data = self.get_hotels(config)
            
            if not hotels_data.get('success'):
                raise UserError(_("Failed to fetch hotels from Cloudbeds"))
            
            properties = hotels_data.get('data', [])
            synced_count = 0
            
            for hotel_data in properties:
                cloudbeds_id = str(hotel_data.get('propertyID'))
                
                # Check if property already exists
                existing_property = self.env['cloudconnect.property'].search([
                    ('cloudbeds_id', '=', cloudbeds_id),
                    ('config_id', '=', config_id)
                ], limit=1)
                
                property_vals = {
                    'cloudbeds_id': cloudbeds_id,
                    'name': hotel_data.get('propertyName', 'Unknown'),
                    'config_id': config_id,
                    'city': hotel_data.get('propertyCity'),
                    'country_id': self._get_country_id(hotel_data.get('propertyCountry')),
                    'timezone': hotel_data.get('propertyTimezone', 'UTC'),
                    'phone': hotel_data.get('propertyPhone'),
                    'email': hotel_data.get('propertyEmail'),
                }
                
                if existing_property:
                    existing_property.write(property_vals)
                else:
                    self.env['cloudconnect.property'].create(property_vals)
                
                synced_count += 1
            
            return {
                'success': True,
                'message': _("Synced %d properties") % synced_count,
                'count': synced_count
            }
            
        except Exception as e:
            _logger.error(f"Property sync failed: {e}")
            return {
                'success': False,
                'message': str(e),
                'count': 0
            }

    def _get_country_id(self, country_code):
        """Get country ID from country code."""
        if not country_code:
            return False
        
        country = self.env['res.country'].search([
            ('code', '=', country_code.upper())
        ], limit=1)
        
        return country.id if country else False