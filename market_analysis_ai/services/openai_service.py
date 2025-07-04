from openai import OpenAI
import logging
import json
import re

_logger = logging.getLogger(__name__)


class OpenAIService:
    def __init__(self, api_key):
        self.client = OpenAI(api_key=api_key)
        self.model = "gpt-3.5-turbo"  # Puedes cambiar a gpt-4 si lo prefieres
    
    def process_price_report(self, message):
        """Procesa un mensaje de reporte de precios usando OpenAI"""
        try:
            system_prompt = """
            Eres un asistente especializado en extraer información de reportes de precios de productos.
            Tu tarea es identificar productos y sus precios desde mensajes en lenguaje natural.
            
            Debes extraer:
            - Nombre del producto
            - Precio (número)
            - Cualquier nota adicional relevante
            
            Responde SIEMPRE en formato JSON con la siguiente estructura:
            {
                "products": [
                    {
                        "name": "nombre del producto",
                        "price": precio_numerico,
                        "notes": "notas adicionales si las hay"
                    }
                ]
            }
            
            Si no puedes identificar productos o precios, responde con:
            {"products": [], "error": "descripción del problema"}
            
            Ejemplos de entrada:
            - "El arroz está a 2.50"
            - "Vi que el aceite subió a $4.20"
            - "Tomates 1.80, papas 2.30"
            """
            
            user_prompt = f"Extrae los productos y precios del siguiente mensaje:\n\n{message}"
            
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                max_tokens=500,
                temperature=0.1
            )
            
            content = response.choices[0].message.content.strip()
            _logger.info(f"Respuesta de OpenAI: {content}")
            
            # Intentar parsear el JSON
            try:
                result = json.loads(content)
                
                # Validar y limpiar los datos
                if "products" in result:
                    for product in result["products"]:
                        # Asegurar que el precio sea numérico
                        price = product.get("price", 0)
                        if isinstance(price, str):
                            # Intentar extraer número del string
                            price_match = re.search(r'[\d.]+', price)
                            if price_match:
                                product["price"] = float(price_match.group())
                            else:
                                product["price"] = 0.0
                        else:
                            product["price"] = float(price)
                        
                        # Asegurar que el nombre no esté vacío
                        if not product.get("name"):
                            product["name"] = "Producto sin nombre"
                
                return result
                
            except json.JSONDecodeError:
                _logger.error(f"Error al parsear JSON de OpenAI: {content}")
                
                # Intentar extraer información manualmente si falla el JSON
                products = self._extract_manually(message)
                return {"products": products}
                
        except Exception as e:
            _logger.error(f"Error en OpenAI process_price_report: {str(e)}")
            return {"products": [], "error": str(e)}
    
    def _extract_manually(self, message):
        """Extracción manual de productos y precios como fallback"""
        products = []
        
        try:
            # Patrones comunes para productos y precios
            patterns = [
                r'(\w+[\w\s]*?)\s*[:=]\s*\$?([\d.]+)',  # Producto: 2.50
                r'(\w+[\w\s]*?)\s+(?:a|está|cuesta)\s+\$?([\d.]+)',  # Producto está a 2.50
                r'(\w+[\w\s]*?)\s+\$?([\d.]+)',  # Producto 2.50
            ]
            
            for pattern in patterns:
                matches = re.findall(pattern, message, re.IGNORECASE)
                for match in matches:
                    product_name = match[0].strip()
                    price = float(match[1])
                    
                    products.append({
                        "name": product_name,
                        "price": price,
                        "notes": "Extraído automáticamente"
                    })
            
        except Exception as e:
            _logger.error(f"Error en extracción manual: {str(e)}")
        
        return products
    
    def test_connection(self):
        """Prueba la conexión con OpenAI"""
        try:
            # Validar formato de API key
            if not self.client.api_key:
                _logger.error("API Key de OpenAI vacía")
                return False
                
            if not self.client.api_key.startswith(('sk-', 'sk-proj-')):
                _logger.error("API Key de OpenAI con formato inválido")
                return False
            
            # Intentar hacer una llamada simple
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "user", "content": "Test"}
                ],
                max_tokens=10
            )
            
            # Verificar que la respuesta tenga contenido
            if response and response.choices and response.choices[0].message.content:
                _logger.info("Conexión con OpenAI exitosa")
                return True
            else:
                _logger.error("Respuesta vacía de OpenAI")
                return False
                
        except Exception as e:
            error_msg = str(e)
            
            # Mensajes de error más descriptivos
            if "401" in error_msg or "Incorrect API key" in error_msg:
                _logger.error("API Key de OpenAI inválida o expirada")
            elif "429" in error_msg:
                _logger.error("Límite de tasa excedido en OpenAI")
            elif "model" in error_msg:
                _logger.error(f"Modelo {self.model} no disponible. Considere usar gpt-3.5-turbo")
            else:
                _logger.error(f"Error al probar conexión con OpenAI: {error_msg}")
            
            return False
    
    def analyze_price_trends(self, products_data):
        """Analiza tendencias de precios usando OpenAI"""
        try:
            system_prompt = """
            Eres un analista de mercado. Analiza los siguientes datos de precios 
            y proporciona insights sobre tendencias, productos más caros/baratos, 
            y recomendaciones.
            """
            
            user_prompt = f"Analiza estos datos de precios:\n{json.dumps(products_data, indent=2)}"
            
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                max_tokens=500,
                temperature=0.3
            )
            
            return response.choices[0].message.content.strip()
            
        except Exception as e:
            _logger.error(f"Error en analyze_price_trends: {str(e)}")
            return "No se pudo realizar el análisis de tendencias."