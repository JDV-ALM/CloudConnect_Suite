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
    
    @api.model
    def create_from_telegram(self, message_data):
        """Crea un reporte desde un mensaje de Telegram procesado por OpenAI"""
        try:
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
                    'processing_notes': product.get('notes', '')
                }
                
                report = self.create(vals)
                _logger.info(f"Reporte creado: {report.name}")
                
                # Enviar notificación
                report.message_post(
                    body=f"Nuevo reporte de precio recibido vía Telegram: {product.get('name')} - ${product.get('price', 0)}"
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
        """Reprocesa el mensaje con OpenAI"""
        self.ensure_one()
        if self.message:
            try:
                settings = self.env['market.analysis.settings'].get_active_settings()
                from ..services.openai_service import OpenAIService
                
                service = OpenAIService(settings.openai_api_key)
                result = service.process_price_report(self.message)
                
                if result and result.get('products'):
                    product = result['products'][0]
                    self.write({
                        'product_name': product.get('name', ''),
                        'price': product.get('price', 0.0),
                        'state': 'processed',
                        'processing_notes': product.get('notes', '')
                    })
                    
                    self.message_post(body="Mensaje reprocesado exitosamente")
                    
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