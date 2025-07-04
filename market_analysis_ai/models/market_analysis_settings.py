from odoo import models, fields, api
from odoo.exceptions import ValidationError
import logging

_logger = logging.getLogger(__name__)


class MarketAnalysisSettings(models.Model):
    _name = 'market.analysis.settings'
    _description = 'Configuración de Market Analysis AI'
    _rec_name = 'create_date'
    
    openai_api_key = fields.Char(
        string='OpenAI API Key',
        required=True,
        help='Ingrese su API Key de OpenAI'
    )
    
    telegram_bot_token = fields.Char(
        string='Token del Bot de Telegram',
        required=True,
        help='Token del bot de Telegram'
    )
    
    telegram_chat_id = fields.Char(
        string='Chat ID de Telegram',
        required=True,
        help='ID del chat donde el bot recibirá mensajes'
    )
    
    active = fields.Boolean(
        string='Activo',
        default=True
    )
    
    last_telegram_offset = fields.Integer(
        string='Último Offset de Telegram',
        default=0,
        help='Último update_id procesado de Telegram'
    )
    
    @api.model
    def get_active_settings(self):
        """Obtiene la configuración activa"""
        settings = self.search([('active', '=', True)], limit=1)
        if not settings:
            raise ValidationError('No hay configuración activa. Por favor configure las API keys.')
        return settings
    
    @api.constrains('active')
    def _check_single_active(self):
        """Asegura que solo haya una configuración activa"""
        if self.active:
            active_count = self.search_count([('active', '=', True)])
            if active_count > 1:
                raise ValidationError('Solo puede haber una configuración activa a la vez.')
    
    def action_test_connection(self):
        """Prueba la conexión con OpenAI y Telegram"""
        self.ensure_one()
        
        # Test OpenAI
        try:
            from ..services.openai_service import OpenAIService
            service = OpenAIService(self.openai_api_key)
            response = service.test_connection()
            if response:
                message = "✓ Conexión con OpenAI exitosa"
            else:
                message = "✗ Error al conectar con OpenAI"
        except Exception as e:
            message = f"✗ Error OpenAI: {str(e)}"
        
        # Test Telegram
        try:
            from ..services.telegram_service import TelegramService
            telegram = TelegramService(self.telegram_bot_token, self.telegram_chat_id)
            if telegram.test_connection():
                message += "\n✓ Conexión con Telegram exitosa"
            else:
                message += "\n✗ Error al conectar con Telegram"
        except Exception as e:
            message += f"\n✗ Error Telegram: {str(e)}"
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Test de Conexión',
                'message': message,
                'sticky': False,
            }
        }
    
    @api.model
    def process_telegram_messages(self):
        """Procesa los mensajes pendientes de Telegram"""
        settings = self.get_active_settings()
        if not settings:
            _logger.warning("No hay configuración activa para procesar mensajes de Telegram")
            return
        
        try:
            from ..services.telegram_service import TelegramService
            from ..services.openai_service import OpenAIService
            
            # Inicializar servicios
            telegram = TelegramService(settings.telegram_bot_token, settings.telegram_chat_id)
            openai_service = OpenAIService(settings.openai_api_key)
            
            # Obtener mensajes nuevos
            updates = telegram.get_updates(offset=settings.last_telegram_offset + 1)
            
            for update in updates:
                try:
                    # Procesar mensaje
                    message_data = telegram.process_message(update)
                    
                    if message_data and message_data.get("text"):
                        _logger.info(f"Procesando mensaje de {message_data.get('username', 'Unknown')}: {message_data['text']}")
                        
                        # Procesar con OpenAI
                        ai_result = openai_service.process_price_report(message_data["text"])
                        
                        if ai_result.get("products"):
                            # Crear reportes
                            report_data = {
                                "original_message": message_data["text"],
                                "telegram_user": message_data.get("username", "") or message_data.get("first_name", "Usuario"),
                                "products": ai_result["products"]
                            }
                            
                            self.env['market.analysis.report'].create_from_telegram(report_data)
                            
                            # Enviar confirmación
                            response_text = telegram.format_price_report(ai_result["products"])
                            telegram.send_message(response_text, message_data["chat_id"])
                            
                        else:
                            # Enviar mensaje de error
                            error_msg = ai_result.get("error", "No se pudieron identificar productos en el mensaje")
                            telegram.send_error_message(error_msg)
                    
                    # Actualizar offset
                    if message_data:
                        settings.last_telegram_offset = message_data["update_id"]
                        
                except Exception as e:
                    _logger.error(f"Error procesando update individual: {str(e)}")
                    continue
                    
        except Exception as e:
            _logger.error(f"Error en process_telegram_messages: {str(e)}")