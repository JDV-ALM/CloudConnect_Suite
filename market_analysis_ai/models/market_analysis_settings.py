from odoo import models, fields, api
from odoo.exceptions import ValidationError
import logging

_logger = logging.getLogger(__name__)


class MarketAnalysisSettings(models.Model):
    _name = 'market.analysis.settings'
    _description = 'Configuración de Market Analysis AI'
    _rec_name = 'create_date'
    
    ai_provider = fields.Selection([
        ('openai', 'OpenAI'),
        ('claude', 'Claude (Anthropic)')
    ], string='Proveedor de AI', default='openai', required=True)
    
    openai_api_key = fields.Char(
        string='OpenAI API Key',
        help='Ingrese su API Key de OpenAI'
    )
    
    claude_api_key = fields.Char(
        string='Claude API Key',
        help='Ingrese su API Key de Claude (Anthropic)'
    )
    
    openai_model = fields.Selection([
        ('gpt-3.5-turbo', 'GPT-3.5 Turbo'),
        ('gpt-4', 'GPT-4'),
        ('gpt-4-turbo-preview', 'GPT-4 Turbo'),
    ], string='Modelo OpenAI', 
       default='gpt-3.5-turbo',
       help='Seleccione el modelo de OpenAI a utilizar')
    
    claude_model = fields.Selection([
        ('claude-3-haiku-20240307', 'Claude 3 Haiku'),
        ('claude-3-sonnet-20240229', 'Claude 3 Sonnet'),
        ('claude-3-opus-20240229', 'Claude 3 Opus'),
    ], string='Modelo Claude', 
       default='claude-3-sonnet-20240229',
       help='Seleccione el modelo de Claude a utilizar')
    
    # Campo computado para obtener el modelo activo
    ai_model = fields.Char(
        string='Modelo de AI',
        compute='_compute_ai_model',
        store=True
    )
    
    @api.depends('ai_provider', 'openai_model', 'claude_model')
    def _compute_ai_model(self):
        for record in self:
            if record.ai_provider == 'openai':
                record.ai_model = record.openai_model
            elif record.ai_provider == 'claude':
                record.ai_model = record.claude_model
            else:
                record.ai_model = False
    
    telegram_bot_token = fields.Char(
        string='Token del Bot de Telegram',
        required=True,
        help='Token del bot de Telegram'
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
    
    @api.constrains('ai_provider', 'openai_api_key', 'claude_api_key')
    def _check_api_keys(self):
        """Valida que esté configurada la API key correspondiente al proveedor seleccionado"""
        if self.ai_provider == 'openai' and not self.openai_api_key:
            raise ValidationError('Debe proporcionar una API Key de OpenAI')
        elif self.ai_provider == 'claude' and not self.claude_api_key:
            raise ValidationError('Debe proporcionar una API Key de Claude')
    
    @api.onchange('ai_provider')
    def _onchange_ai_provider(self):
        """Actualiza el modelo por defecto según el proveedor"""
        if self.ai_provider == 'openai':
            self.openai_model = self.openai_model or 'gpt-3.5-turbo'
        elif self.ai_provider == 'claude':
            self.claude_model = self.claude_model or 'claude-3-sonnet-20240229'
    
    def action_test_connection(self):
        """Prueba la conexión con el proveedor de AI y Telegram"""
        self.ensure_one()
        
        messages = []
        
        # Test AI Provider
        try:
            if self.ai_provider == 'openai':
                from ..services.openai_service import OpenAIService
                service = OpenAIService(self.openai_api_key)
                service.model = self.ai_model
                response = service.test_connection()
                if response:
                    messages.append("✓ Conexión con OpenAI exitosa")
                else:
                    messages.append("✗ Error al conectar con OpenAI: Sin respuesta")
            
            elif self.ai_provider == 'claude':
                from ..services.claude_service import ClaudeService
                service = ClaudeService(self.claude_api_key)
                service.model = self.ai_model
                response = service.test_connection()
                if response:
                    messages.append("✓ Conexión con Claude exitosa")
                else:
                    messages.append("✗ Error al conectar con Claude: Sin respuesta")
                    
        except ImportError as e:
            if 'openai' in str(e):
                messages.append(f"✗ Error: Librería OpenAI no instalada. Ejecute: pip install openai")
            elif 'anthropic' in str(e):
                messages.append(f"✗ Error: Librería Anthropic no instalada. Ejecute: pip install anthropic")
            else:
                messages.append(f"✗ Error: {str(e)}")
        except Exception as e:
            messages.append(f"✗ Error {self.ai_provider}: {str(e)}")
        
        # Test Telegram
        try:
            from ..services.telegram_service import TelegramService
            telegram = TelegramService(self.telegram_bot_token)
            if telegram.test_connection():
                messages.append("✓ Conexión con Telegram exitosa")
            else:
                messages.append("✗ Error al conectar con Telegram")
        except ImportError as e:
            messages.append(f"✗ Error: Librería requests no instalada. Ejecute: pip install requests")
        except Exception as e:
            messages.append(f"✗ Error Telegram: {str(e)}")
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Test de Conexión',
                'message': '\n'.join(messages),
                'sticky': True,
                'type': 'warning' if any('✗' in m for m in messages) else 'success',
            }
        }
    
    def get_ai_service(self):
        """Retorna el servicio de AI configurado"""
        self.ensure_one()
        
        if self.ai_provider == 'openai':
            from ..services.openai_service import OpenAIService
            service = OpenAIService(self.openai_api_key)
            service.model = self.ai_model
            return service
        
        elif self.ai_provider == 'claude':
            from ..services.claude_service import ClaudeService
            service = ClaudeService(self.claude_api_key)
            service.model = self.ai_model
            return service
        
        else:
            raise ValidationError(f'Proveedor de AI no válido: {self.ai_provider}')
    
    @api.model
    def process_telegram_messages(self):
        """Procesa los mensajes pendientes de Telegram"""
        settings = self.get_active_settings()
        if not settings:
            _logger.warning("No hay configuración activa para procesar mensajes de Telegram")
            return
        
        try:
            from ..services.telegram_service import TelegramService
            
            # Inicializar servicios
            telegram = TelegramService(settings.telegram_bot_token)
            ai_service = settings.get_ai_service()
            
            # Obtener mensajes nuevos
            updates = telegram.get_updates(offset=settings.last_telegram_offset + 1)
            
            for update in updates:
                try:
                    # Procesar mensaje
                    message_data = telegram.process_message(update)
                    
                    if message_data and message_data.get("text"):
                        _logger.info(f"Procesando mensaje de {message_data.get('username', 'Unknown')}: {message_data['text']}")
                        
                        # Procesar con AI
                        ai_result = ai_service.process_price_report(message_data["text"])
                        
                        if ai_result.get("products"):
                            # Crear reportes
                            report_data = {
                                "original_message": message_data["text"],
                                "telegram_user": message_data.get("username", "") or message_data.get("first_name", "Usuario"),
                                "chat_id": message_data["chat_id"],
                                "products": ai_result["products"]
                            }
                            
                            self.env['market.analysis.report'].create_from_telegram(report_data)
                            
                            # Enviar confirmación
                            response_text = telegram.format_price_report(ai_result["products"])
                            telegram.send_message(response_text, message_data["chat_id"])
                            
                        else:
                            # Enviar mensaje de error
                            error_msg = ai_result.get("error", "No se pudieron identificar productos en el mensaje")
                            telegram.send_error_message(error_msg, message_data["chat_id"])
                    
                    # Actualizar offset
                    if message_data:
                        settings.last_telegram_offset = message_data["update_id"]
                        
                except Exception as e:
                    _logger.error(f"Error procesando update individual: {str(e)}")
                    continue
                    
        except Exception as e:
            _logger.error(f"Error en process_telegram_messages: {str(e)}")