# -*- coding: utf-8 -*-

from odoo import models, api, _
import json
import logging
from datetime import datetime

_logger = logging.getLogger(__name__)


class WebhookProcessor(models.AbstractModel):
    _name = 'cloudconnect.webhook.processor'
    _description = 'CloudConnect Webhook Processor'
    
    def process_event(self, webhook, event_data):
        """
        Process incoming webhook event.
        
        :param webhook: cloudconnect.webhook record
        :param event_data: Dictionary with event data
        :return: Boolean indicating success
        """
        # Create sync log for tracking
        sync_log = self.env['cloudconnect.sync.log'].create({
            'operation_type': 'webhook',
            'model_name': webhook.event_object or 'unknown',
            'action': webhook.event_action or 'process',
            'config_id': webhook.config_id.id,
            'property_id': webhook.property_id.id if webhook.property_id else False,
            'request_data': json.dumps(event_data, indent=2),
            'api_endpoint': webhook.event_type,
            'status': 'pending',
        })
        
        try:
            # Extract common event data
            version = event_data.get('version', '1.0')
            timestamp = event_data.get('timestamp')
            property_id = event_data.get('propertyID') or event_data.get('propertyId')
            
            # Log event details
            _logger.info(f"Processing webhook event: {webhook.event_type} for property {property_id}")
            
            # Validate property if specified
            if webhook.property_id and str(property_id) != webhook.property_id.cloudbeds_id:
                raise ValueError(f"Property mismatch: expected {webhook.property_id.cloudbeds_id}, got {property_id}")
            
            # Route to specific processor based on event type
            processor_method = self._get_processor_method(webhook.event_type)
            if processor_method:
                result = processor_method(webhook, event_data, sync_log)
                sync_log.mark_success(response_data={'processed': True, 'result': result})
                return True
            else:
                # No specific processor, just log the event
                _logger.warning(f"No specific processor for event type: {webhook.event_type}")
                sync_log.mark_warning(f"Event type {webhook.event_type} has no specific processor")
                
                # Notify subscribed modules through bus
                self._notify_event(webhook, event_data)
                return True
                
        except Exception as e:
            _logger.error(f"Error processing webhook event: {str(e)}", exc_info=True)
            sync_log.mark_error(str(e))
            raise
    
    def _get_processor_method(self, event_type):
        """Get the appropriate processor method for event type."""
        # Map event types to processor methods
        processors = {
            # Reservation events
            'reservation/created': self._process_reservation_created,
            'reservation/status_changed': self._process_reservation_status_changed,
            'reservation/dates_changed': self._process_reservation_dates_changed,
            'reservation/accommodation_changed': self._process_reservation_accommodation_changed,
            'reservation/deleted': self._process_reservation_deleted,
            'reservation/notes_changed': self._process_reservation_notes_changed,
            'reservation/custom_fields_changed': self._process_reservation_custom_fields_changed,
            
            # Guest events
            'guest/created': self._process_guest_created,
            'guest/assigned': self._process_guest_assigned,
            'guest/removed': self._process_guest_removed,
            'guest/details_changed': self._process_guest_details_changed,
            
            # Payment events
            'transaction/created': self._process_transaction_created,
            
            # Housekeeping events
            'housekeeping/room_condition_changed': self._process_room_condition_changed,
            
            # Integration events
            'integration/appstate_changed': self._process_appstate_changed,
            'integration/appsettings_changed': self._process_appsettings_changed,
        }
        
        return processors.get(event_type)
    
    def _notify_event(self, webhook, event_data):
        """Notify other modules about the event through the bus."""
        # This allows extension modules to subscribe to events
        self.env['bus.bus']._sendone(
            f'cloudconnect.webhook.{webhook.event_type}',
            {
                'webhook_id': webhook.id,
                'event_type': webhook.event_type,
                'property_id': webhook.property_id.id if webhook.property_id else False,
                'data': event_data,
            }
        )
    
    # Reservation Event Processors
    
    def _process_reservation_created(self, webhook, event_data, sync_log):
        """Process reservation created event."""
        reservation_id = event_data.get('reservationID')
        if not reservation_id:
            raise ValueError("Missing reservationID in event data")
        
        # Store in sync log for processing
        sync_log.cloudbeds_id = reservation_id
        
        # Notify extension modules
        self._notify_event(webhook, event_data)
        
        _logger.info(f"Reservation created: {reservation_id}")
        return {'reservation_id': reservation_id}
    
    def _process_reservation_status_changed(self, webhook, event_data, sync_log):
        """Process reservation status changed event."""
        reservation_id = event_data.get('reservationID')
        status = event_data.get('status')
        
        if not reservation_id or not status:
            raise ValueError("Missing reservationID or status in event data")
        
        sync_log.cloudbeds_id = reservation_id
        
        # Notify extension modules
        self._notify_event(webhook, event_data)
        
        _logger.info(f"Reservation {reservation_id} status changed to: {status}")
        return {'reservation_id': reservation_id, 'status': status}
    
    def _process_reservation_dates_changed(self, webhook, event_data, sync_log):
        """Process reservation dates changed event."""
        reservation_id = event_data.get('reservationId') or event_data.get('reservationID')
        start_date = event_data.get('startDate')
        end_date = event_data.get('endDate')
        
        if not reservation_id:
            raise ValueError("Missing reservationID in event data")
        
        sync_log.cloudbeds_id = reservation_id
        
        # Notify extension modules
        self._notify_event(webhook, event_data)
        
        _logger.info(f"Reservation {reservation_id} dates changed: {start_date} to {end_date}")
        return {'reservation_id': reservation_id, 'dates': f"{start_date} to {end_date}"}
    
    def _process_reservation_accommodation_changed(self, webhook, event_data, sync_log):
        """Process reservation accommodation changed event."""
        reservation_id = event_data.get('reservationId') or event_data.get('reservationID')
        room_id = event_data.get('roomId') or event_data.get('roomID')
        
        if not reservation_id:
            raise ValueError("Missing reservationID in event data")
        
        sync_log.cloudbeds_id = reservation_id
        
        # Notify extension modules
        self._notify_event(webhook, event_data)
        
        _logger.info(f"Reservation {reservation_id} room changed to: {room_id}")
        return {'reservation_id': reservation_id, 'room_id': room_id}
    
    def _process_reservation_deleted(self, webhook, event_data, sync_log):
        """Process reservation deleted event."""
        reservation_id = event_data.get('reservationId') or event_data.get('reservationID')
        
        if not reservation_id:
            raise ValueError("Missing reservationID in event data")
        
        sync_log.cloudbeds_id = reservation_id
        
        # Notify extension modules
        self._notify_event(webhook, event_data)
        
        _logger.info(f"Reservation deleted: {reservation_id}")
        return {'reservation_id': reservation_id, 'deleted': True}
    
    def _process_reservation_notes_changed(self, webhook, event_data, sync_log):
        """Process reservation notes changed event."""
        reservation_id = event_data.get('reservationId') or event_data.get('reservationID')
        notes = event_data.get('notes', '')
        
        if not reservation_id:
            raise ValueError("Missing reservationID in event data")
        
        sync_log.cloudbeds_id = reservation_id
        
        # Notify extension modules
        self._notify_event(webhook, event_data)
        
        _logger.info(f"Reservation {reservation_id} notes updated")
        return {'reservation_id': reservation_id, 'has_notes': bool(notes)}
    
    def _process_reservation_custom_fields_changed(self, webhook, event_data, sync_log):
        """Process reservation custom fields changed event."""
        reservation_id = event_data.get('reservationID')
        
        if not reservation_id:
            raise ValueError("Missing reservationID in event data")
        
        sync_log.cloudbeds_id = reservation_id
        
        # Notify extension modules
        self._notify_event(webhook, event_data)
        
        _logger.info(f"Reservation {reservation_id} custom fields updated")
        return {'reservation_id': reservation_id}
    
    # Guest Event Processors
    
    def _process_guest_created(self, webhook, event_data, sync_log):
        """Process guest created event."""
        guest_id = event_data.get('guestId') or event_data.get('guestID')
        
        if not guest_id:
            raise ValueError("Missing guestID in event data")
        
        sync_log.cloudbeds_id = str(guest_id)
        
        # Notify extension modules
        self._notify_event(webhook, event_data)
        
        _logger.info(f"Guest created: {guest_id}")
        return {'guest_id': guest_id}
    
    def _process_guest_assigned(self, webhook, event_data, sync_log):
        """Process guest assigned event."""
        guest_id = event_data.get('guestId') or event_data.get('guestID')
        reservation_id = event_data.get('reservationId') or event_data.get('reservationID')
        
        if not guest_id:
            raise ValueError("Missing guestID in event data")
        
        sync_log.cloudbeds_id = str(guest_id)
        
        # Notify extension modules
        self._notify_event(webhook, event_data)
        
        _logger.info(f"Guest {guest_id} assigned to reservation {reservation_id}")
        return {'guest_id': guest_id, 'reservation_id': reservation_id}
    
    def _process_guest_removed(self, webhook, event_data, sync_log):
        """Process guest removed event."""
        guest_id = event_data.get('guestId') or event_data.get('guestID')
        reservation_id = event_data.get('reservationId') or event_data.get('reservationID')
        
        if not guest_id:
            raise ValueError("Missing guestID in event data")
        
        sync_log.cloudbeds_id = str(guest_id)
        
        # Notify extension modules
        self._notify_event(webhook, event_data)
        
        _logger.info(f"Guest {guest_id} removed from reservation {reservation_id}")
        return {'guest_id': guest_id, 'reservation_id': reservation_id}
    
    def _process_guest_details_changed(self, webhook, event_data, sync_log):
        """Process guest details changed event."""
        guest_id = event_data.get('guestId') or event_data.get('guestID')
        
        if not guest_id:
            raise ValueError("Missing guestID in event data")
        
        sync_log.cloudbeds_id = str(guest_id)
        
        # Notify extension modules
        self._notify_event(webhook, event_data)
        
        _logger.info(f"Guest {guest_id} details updated")
        return {'guest_id': guest_id}
    
    # Payment Event Processors
    
    def _process_transaction_created(self, webhook, event_data, sync_log):
        """Process transaction created event."""
        transaction_id = event_data.get('transactionID')
        category = event_data.get('transactionCategory')
        
        if not transaction_id:
            raise ValueError("Missing transactionID in event data")
        
        sync_log.cloudbeds_id = transaction_id
        
        # Notify extension modules
        self._notify_event(webhook, event_data)
        
        _logger.info(f"Transaction created: {transaction_id} (category: {category})")
        return {'transaction_id': transaction_id, 'category': category}
    
    # Housekeeping Event Processors
    
    def _process_room_condition_changed(self, webhook, event_data, sync_log):
        """Process room condition changed event."""
        room_id = event_data.get('roomId') or event_data.get('roomID')
        condition = event_data.get('condition')
        
        if not room_id:
            raise ValueError("Missing roomID in event data")
        
        sync_log.cloudbeds_id = room_id
        
        # Notify extension modules
        self._notify_event(webhook, event_data)
        
        _logger.info(f"Room {room_id} condition changed to: {condition}")
        return {'room_id': room_id, 'condition': condition}
    
    # Integration Event Processors
    
    def _process_appstate_changed(self, webhook, event_data, sync_log):
        """Process app state changed event."""
        old_state = event_data.get('oldState')
        new_state = event_data.get('newState')
        
        # Notify extension modules
        self._notify_event(webhook, event_data)
        
        _logger.info(f"App state changed from {old_state} to {new_state}")
        return {'old_state': old_state, 'new_state': new_state}
    
    def _process_appsettings_changed(self, webhook, event_data, sync_log):
        """Process app settings changed event."""
        # Notify extension modules
        self._notify_event(webhook, event_data)
        
        _logger.info("App settings changed")
        return {'settings_changed': True}