from odoo import models, fields, api
import logging
from datetime import datetime

_logger = logging.getLogger(__name__)


class MarketAnalysisReport(models.Model):
    _name = 'market.analysis.report'
    _description = 'Reporte de Análisis de Mercado'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date_received desc'
    
    name = fields.Char(
        string='Línea de Análisis',
        required=True,
        tracking=True
    )
    
    product_name = fields.Char(
        string='Producto',
        tracking=True
    )
    
    price = fields.Float(
        string='Precio',
        digits=(16, 2),
        tracking=True
    )
    
    currency_id = fields.Many2one(
        'res.currency',
        string='Moneda',
        default=lambda self: self.env.company.currency_id
    )
    
    message = fields.Text(
        string='Mensaje Original',
        help='Mensaje recibido desde Telegram'
    )
    
    date_received = fields.Datetime(
        string='Fecha de Recepción',
        default=fields.Datetime.now,
        required=True
    )
    
    active = fields.Boolean(
        string='Activo',
        default=True
    )
    
    state = fields.Selection([
        ('draft', 'Borrador'),
        ('processed', 'Procesado'),
        ('error', 'Error')
    ], string='Estado', default='draft', tracking=True)
    
    telegram_user = fields.Char(
        string='Usuario de Telegram',
        help='Usuario que envió el mensaje'
    )
    
    telegram_chat_id = fields.Char(
        string='Chat ID',
        help='ID del chat de Telegram'
    )
    
    processing_notes = fields.Text(
        string='Notas de Procesamiento',
        help='Información adicional del procesamiento con AI'
    )
    
    ai_provider = fields.Selection([
        ('openai', 'OpenAI'),
        ('claude', 'Claude')
    ], string='Procesado con', readonly=True)
    
    ai_model = fields.Char(
        string='Modelo AI',
        readonly=True,
        help='Modelo de AI utilizado para procesar este reporte'
    )
    
    @api.model
    def create_from_telegram(self, message_data):
        """Crea un reporte desde un mensaje de Telegram procesado por AI"""
        try:
            # Obtener configuración activa para saber qué proveedor se usó
            settings = self.env['market.analysis.settings'].get_active_settings()
            
            # Extrae la información procesada
            products_info = message_data.get('products', [])
            
            for product in products_info:
                vals = {
                    'name': f"Análisis - {product.get('name', 'Sin nombre')}",
                    'product_name': product.get('name', ''),
                    'price': product.get('price', 0.0),
                    'message': message_data.get('original_message', ''),
                    'telegram_user': message_data.get('telegram_user', ''),
                    'telegram_chat_id': str(message_data.get('chat_id', '')),
                    'date_received': datetime.now(),
                    'state': 'processed',
                    'processing_notes': product.get('notes', ''),
                    'ai_provider': settings.ai_provider,
                    'ai_model': settings.ai_model,
                }
                
                report = self.create(vals)
                _logger.info(f"Reporte creado: {report.name}")
                
                # Enviar notificación
                provider_name = "OpenAI" if settings.ai_provider == 'openai' else "Claude"
                report.message_post(
                    body=f"Nuevo reporte de precio recibido vía Telegram y procesado con {provider_name}: {product.get('name')} - ${product.get('price', 0)}"
                )
                
        except Exception as e:
            _logger.error(f"Error al crear reporte desde Telegram: {str(e)}")
            # Crear reporte de error
            error_vals = {
                'name': 'Error en procesamiento',
                'message': message_data.get('original_message', ''),
                'telegram_user': message_data.get('telegram_user', ''),
                'telegram_chat_id': str(message_data.get('chat_id', '')),
                'date_received': datetime.now(),
                'state': 'error',
                'processing_notes': f"Error: {str(e)}"
            }
            self.create(error_vals)
    
    def action_reprocess(self):
        """Reprocesa el mensaje con AI"""
        self.ensure_one()
        if self.message:
            try:
                settings = self.env['market.analysis.settings'].get_active_settings()
                ai_service = settings.get_ai_service()
                
                result = ai_service.process_price_report(self.message)
                
                if result and result.get('products'):
                    product = result['products'][0]
                    self.write({
                        'product_name': product.get('name', ''),
                        'price': product.get('price', 0.0),
                        'state': 'processed',
                        'processing_notes': product.get('notes', ''),
                        'ai_provider': settings.ai_provider,
                        'ai_model': settings.ai_model,
                    })
                    
                    provider_name = "OpenAI" if settings.ai_provider == 'openai' else "Claude"
                    self.message_post(body=f"Mensaje reprocesado exitosamente con {provider_name}")
                    
            except Exception as e:
                self.write({
                    'state': 'error',
                    'processing_notes': f"Error en reprocesamiento: {str(e)}"
                })
                
        return True
    
    @api.model
    def get_price_statistics(self):
        """Obtiene estadísticas de precios por producto"""
        self.env.cr.execute("""
            SELECT 
                product_name,
                COUNT(*) as count,
                AVG(price) as avg_price,
                MIN(price) as min_price,
                MAX(price) as max_price
            FROM market_analysis_report
            WHERE state = 'processed' AND active = true
            GROUP BY product_name
            ORDER BY count DESC
        """)
        
        return self.env.cr.dictfetchall()
    
    @api.model
    def get_ai_usage_statistics(self):
        """Obtiene estadísticas de uso por proveedor de AI"""
        self.env.cr.execute("""
            SELECT 
                ai_provider,
                ai_model,
                COUNT(*) as count,
                COUNT(CASE WHEN state = 'processed' THEN 1 END) as successful,
                COUNT(CASE WHEN state = 'error' THEN 1 END) as errors
            FROM market_analysis_report
            WHERE ai_provider IS NOT NULL
            GROUP BY ai_provider, ai_model
            ORDER BY count DESC
        """)
        
        return self.env.cr.dictfetchall()