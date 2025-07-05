from odoo import models, fields, api
from odoo.exceptions import ValidationError
import logging
import json

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
    
    # Modelos como Selection con valores predefinidos
    openai_model = fields.Selection([
        ('gpt-3.5-turbo', 'GPT-3.5 Turbo'),
        ('gpt-4', 'GPT-4'),
        ('gpt-4-turbo-preview', 'GPT-4 Turbo'),
        ('gpt-4o', 'GPT-4o'),
        ('gpt-4o-mini', 'GPT-4o Mini'),
    ], string='Modelo OpenAI', 
       default='gpt-3.5-turbo',
       help='Seleccione el modelo de OpenAI a utilizar')
    
    # Para Claude, usamos un campo Char para permitir cualquier modelo
    claude_model = fields.Char(
        string='Modelo Claude',
        default='claude-3-sonnet-20240229',
        help='ID del modelo Claude a utilizar'
    )
    
    # Campo para almacenar los modelos disponibles como JSON
    available_claude_models = fields.Text(
        string='Modelos Claude Disponibles',
        default='[]'
    )
    
    # Campo computado para mostrar modelos de forma legible
    claude_models_display = fields.Html(
        string='Modelos Disponibles',
        compute='_compute_claude_models_display'
    )
    
    # Campo computado para obtener el modelo activo
    ai_model = fields.Char(
        string='Modelo de AI',
        compute='_compute_ai_model',
        store=True
    )
    
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
    
    @api.depends('available_claude_models', 'claude_model')
    def _compute_claude_models_display(self):
        for record in self:
            try:
                if record.available_claude_models and record.available_claude_models != '[]':
                    models = json.loads(record.available_claude_models)
                    html = '<div style="font-family: monospace; font-size: 14px;">'
                    
                    for model in models:
                        # Resaltar el modelo actual
                        is_current = model.get("id") == record.claude_model
                        bg_color = '#d4edda' if is_current else '#f8f9fa'
                        border_color = '#28a745' if is_current else '#dee2e6'
                        
                        html += f'''
                        <div style="margin-bottom: 10px; padding: 10px; background-color: {bg_color}; 
                                    border: 1px solid {border_color}; border-radius: 5px;">
                            <div style="font-weight: bold; color: #333; margin-bottom: 5px;">
                                {model.get("name", "Sin nombre")}
                            </div>
                            <div style="color: #666; font-size: 12px; word-break: break-all;">
                                {model.get("id", "")}
                            </div>
                        '''
                        
                        if is_current:
                            html += '<div style="color: #28a745; font-size: 11px; margin-top: 5px;">✓ Modelo actual</div>'
                        
                        html += '</div>'
                    
                    html += '</div>'
                    record.claude_models_display = html
                else:
                    record.claude_models_display = '<p style="color: #666; font-style: italic;">No hay modelos cargados. Presione "Actualizar Modelos".</p>'
            except Exception as e:
                _logger.error(f"Error al mostrar modelos: {str(e)}")
                record.claude_models_display = '<p style="color: #dc3545; font-style: italic;">Error al mostrar modelos.</p>'
    
    @api.depends('ai_provider', 'openai_model', 'claude_model')
    def _compute_ai_model(self):
        for record in self:
            if record.ai_provider == 'openai':
                record.ai_model = record.openai_model
            elif record.ai_provider == 'claude':
                record.ai_model = record.claude_model
            else:
                record.ai_model = False
    
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
            if not self.openai_model:
                self.openai_model = 'gpt-3.5-turbo'
        elif self.ai_provider == 'claude':
            if not self.claude_model:
                self.claude_model = 'claude-3-sonnet-20240229'
            # Si es Claude y tenemos API key, actualizar modelos
            if self.claude_api_key:
                self._update_claude_models()
    
    @api.onchange('claude_api_key')
    def _onchange_claude_api_key(self):
        """Cuando se cambia la API key de Claude, actualizar modelos disponibles"""
        if self.ai_provider == 'claude' and self.claude_api_key:
            self._update_claude_models()
    
    def _update_claude_models(self):
        """Actualiza la lista de modelos disponibles de Claude"""
        try:
            from ..services.claude_service import ClaudeService
            models = ClaudeService.get_available_models(self.claude_api_key)
            if models:
                self.available_claude_models = json.dumps(models)
                # Si el modelo actual no está en la lista, usar el primero
                model_ids = [m['id'] for m in models]
                if self.claude_model not in model_ids and model_ids:
                    self.claude_model = model_ids[0]
                    
                # Log para información
                _logger.info(f"Modelos Claude disponibles: {', '.join([m['name'] for m in models])}")
                
        except Exception as e:
            _logger.error(f"Error al obtener modelos Claude: {str(e)}")
    
    def action_refresh_models(self):
        """Actualiza la lista de modelos disponibles desde las APIs"""
        self.ensure_one()
        
        messages = []
        
        if self.ai_provider == 'claude' and self.claude_api_key:
            try:
                from ..services.claude_service import ClaudeService
                models = ClaudeService.get_available_models(self.claude_api_key)
                
                if models:
                    self.available_claude_models = json.dumps(models)
                    
                    # Crear mensaje con lista de modelos
                    model_list = '\n'.join([f"  • {m['name']} ({m['id']})" for m in models])
                    messages.append(f"✓ Modelos Claude actualizados:\n{model_list}")
                    
                    # Si el modelo actual no está en la lista, seleccionar el primero
                    model_ids = [m['id'] for m in models]
                    if self.claude_model not in model_ids and model_ids:
                        self.claude_model = model_ids[0]
                        messages.append(f"ℹ Modelo seleccionado: {self.claude_model}")
                else:
                    messages.append("✗ No se pudieron obtener los modelos de Claude")
                    
            except ImportError:
                messages.append("✗ Error: Librería anthropic no instalada")
            except Exception as e:
                messages.append(f"✗ Error al actualizar modelos Claude: {str(e)}")
        
        elif self.ai_provider == 'openai':
            messages.append("ℹ Los modelos de OpenAI están predefinidos:")
            messages.append("  • GPT-3.5 Turbo\n  • GPT-4\n  • GPT-4 Turbo\n  • GPT-4o\n  • GPT-4o Mini")
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Actualización de Modelos',
                'message': '\n'.join(messages),
                'sticky': True,
                'type': 'warning' if any('✗' in m for m in messages) else 'success',
            }
        }
    
    def action_test_connection(self):
        """Prueba la conexión con el proveedor de AI y Telegram"""
        self.ensure_one()
        
        messages = []
        
        # Test AI Provider
        try:
            if self.ai_provider == 'openai':
                from ..services.openai_service import OpenAIService
                service = OpenAIService(self.openai_api_key)
                if self.openai_model:
                    service.model = self.openai_model
                response = service.test_connection()
                if response:
                    messages.append("✓ Conexión con OpenAI exitosa")
                    messages.append(f"  Modelo: {self.openai_model}")
                else:
                    messages.append("✗ Error al conectar con OpenAI: Sin respuesta")
            
            elif self.ai_provider == 'claude':
                from ..services.claude_service import ClaudeService
                service = ClaudeService(self.claude_api_key)
                if self.claude_model:
                    service.model = self.claude_model
                response = service.test_connection()
                if response:
                    messages.append("✓ Conexión con Claude exitosa")
                    messages.append(f"  Modelo: {self.claude_model}")
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
            if self.openai_model:
                service.model = self.openai_model
            return service
        
        elif self.ai_provider == 'claude':
            from ..services.claude_service import ClaudeService
            service = ClaudeService(self.claude_api_key)
            if self.claude_model:
                service.model = self.claude_model
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