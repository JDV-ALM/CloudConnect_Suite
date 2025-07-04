import requests
import logging
import time

_logger = logging.getLogger(__name__)


class TelegramService:
    def __init__(self, token, chat_id):
        self.token = token
        self.chat_id = chat_id
        self.base_url = f"https://api.telegram.org/bot{token}"
    
    def get_updates(self, offset=0):
        """Obtiene los mensajes nuevos desde Telegram"""
        try:
            url = f"{self.base_url}/getUpdates"
            params = {
                "timeout": 100,
                "offset": offset
            }
            response = requests.get(url, params=params, timeout=110)
            
            if response.status_code == 200:
                data = response.json()
                if data.get("ok"):
                    return data.get("result", [])
            
            _logger.error(f"Error al obtener updates de Telegram: {response.text}")
            return []
            
        except Exception as e:
            _logger.error(f"Error en get_updates: {str(e)}")
            return []
    
    def send_message(self, text, chat_id=None):
        """Envía un mensaje a Telegram"""
        try:
            url = f"{self.base_url}/sendMessage"
            params = {
                "chat_id": chat_id or self.chat_id,
                "text": text,
                "parse_mode": "HTML"
            }
            response = requests.post(url, params=params)
            
            if response.status_code == 200:
                return response.json()
            
            _logger.error(f"Error al enviar mensaje a Telegram: {response.text}")
            return None
            
        except Exception as e:
            _logger.error(f"Error en send_message: {str(e)}")
            return None
    
    def test_connection(self):
        """Prueba la conexión con el bot de Telegram"""
        try:
            url = f"{self.base_url}/getMe"
            response = requests.get(url, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                if data.get("ok"):
                    bot_info = data.get("result", {})
                    _logger.info(f"Bot conectado: @{bot_info.get('username', 'Unknown')}")
                    return True
            
            return False
            
        except Exception as e:
            _logger.error(f"Error al probar conexión: {str(e)}")
            return False
    
    def process_message(self, update):
        """Procesa un mensaje individual de Telegram"""
        try:
            message = update.get("message", {})
            
            # Extraer información del mensaje
            message_data = {
                "update_id": update.get("update_id"),
                "text": message.get("text", ""),
                "chat_id": message.get("chat", {}).get("id"),
                "user_id": message.get("from", {}).get("id"),
                "username": message.get("from", {}).get("username", ""),
                "first_name": message.get("from", {}).get("first_name", ""),
                "date": message.get("date")
            }
            
            # Solo procesar mensajes del chat configurado o mensajes directos
            if str(message_data["chat_id"]) == str(self.chat_id) or message_data["chat_id"] == message_data["user_id"]:
                return message_data
            
            _logger.info(f"Mensaje ignorado de chat_id: {message_data['chat_id']}")
            return None
            
        except Exception as e:
            _logger.error(f"Error al procesar mensaje: {str(e)}")
            return None
    
    def format_price_report(self, products_info):
        """Formatea la respuesta de un reporte de precios"""
        if not products_info:
            return "❌ No se pudieron identificar productos en el mensaje."
        
        response = "📊 <b>Reporte de Precios Recibido</b>\n\n"
        
        for product in products_info:
            response += f"📦 <b>Producto:</b> {product.get('name', 'Sin nombre')}\n"
            response += f"💰 <b>Precio:</b> ${product.get('price', 0):.2f}\n"
            if product.get('notes'):
                response += f"📝 <b>Notas:</b> {product.get('notes')}\n"
            response += "\n"
        
        response += "✅ <i>Información registrada exitosamente</i>"
        
        return response
    
    def send_error_message(self, error_msg):
        """Envía un mensaje de error formateado"""
        message = f"❌ <b>Error al procesar mensaje</b>\n\n{error_msg}\n\n"
        message += "💡 <i>Por favor, envíe el reporte en formato:</i>\n"
        message += "<code>Producto: [nombre]\nPrecio: [valor]</code>"
        
        return self.send_message(message)