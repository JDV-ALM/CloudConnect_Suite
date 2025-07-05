import anthropic
import logging
import json
import re
import requests

_logger = logging.getLogger(__name__)


class ClaudeService:
    def __init__(self, api_key):
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = "claude-3-sonnet-20240229"  # Puedes cambiar a claude-3-opus-20240229 si lo prefieres
    
    def process_price_report(self, message):
        """Procesa un mensaje de reporte de precios usando Claude"""
        try:
            system_prompt = """
            Eres un asistente especializado en extraer información de precios de productos.
            Tu tarea es identificar productos y sus precios desde mensajes en lenguaje natural.
            
            Debes extraer:
            - Nombre de productos
            - Precio (número)
            - Notas adicionales si las hay
            
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
            - "La gente de Purolomo tiene el mejor precio, tiene el arroz a 2.50"
            """
            
            user_prompt = f"Identifica y extrae los productos y precios del siguiente mensaje, el mensaje puede ser un texto con mucha informacion que podria no ser relevante:\n\n{message}"
            
            response = self.client.messages.create(
                model=self.model,
                max_tokens=500,
                temperature=0.1,
                system=system_prompt,
                messages=[
                    {"role": "user", "content": user_prompt}
                ]
            )
            
            content = response.content[0].text.strip()
            _logger.info(f"Respuesta de Claude: {content}")
            
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
                _logger.error(f"Error al parsear JSON de Claude: {content}")
                
                # Intentar extraer información manualmente si falla el JSON
                products = self._extract_manually(message)
                return {"products": products}
                
        except Exception as e:
            _logger.error(f"Error en Claude process_price_report: {str(e)}")
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
        """Prueba la conexión con Claude"""
        try:
            # Validar formato de API key
            if not self.client.api_key:
                _logger.error("API Key de Claude vacía")
                return False
                
            # Claude API keys pueden tener diferentes formatos
            if not (self.client.api_key.startswith('sk-ant-') or 
                    self.client.api_key.startswith('sk-') or
                    len(self.client.api_key) > 20):
                _logger.error("API Key de Claude con formato inválido")
                return False
            
            # Intentar hacer una llamada simple
            response = self.client.messages.create(
                model=self.model,
                max_tokens=10,
                messages=[
                    {"role": "user", "content": "Test"}
                ]
            )
            
            # Verificar que la respuesta tenga contenido
            if response and response.content and len(response.content) > 0:
                _logger.info("Conexión con Claude exitosa")
                return True
            else:
                _logger.error("Respuesta vacía de Claude")
                return False
                
        except Exception as e:
            error_msg = str(e)
            
            # Mensajes de error más descriptivos
            if "401" in error_msg or "authentication" in error_msg.lower():
                _logger.error("API Key de Claude inválida o expirada")
            elif "429" in error_msg:
                _logger.error("Límite de tasa excedido en Claude")
            elif "model" in error_msg or "does not exist" in error_msg:
                _logger.error(f"Modelo {self.model} no disponible. Verifique que el modelo sea válido.")
            elif "api_key" in error_msg.lower():
                _logger.error("Problema con la API Key de Claude")
            else:
                _logger.error(f"Error al probar conexión con Claude: {error_msg}")
            
            return False
    
    @classmethod
    def get_available_models(cls, api_key):
        """Obtiene la lista de modelos disponibles desde la API de Claude"""
        try:
            headers = {
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json"
            }
            
            response = requests.get(
                "https://api.anthropic.com/v1/models",
                headers=headers,
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                models = []
                
                # Extraer los modelos de la respuesta
                for model in data.get('data', []):
                    model_info = {
                        'id': model.get('id'),
                        'name': model.get('display_name', model.get('id')),
                        'created_at': model.get('created_at')
                    }
                    models.append(model_info)
                
                _logger.info(f"Modelos Claude disponibles: {[m['id'] for m in models]}")
                return models
            else:
                _logger.error(f"Error al obtener modelos: {response.status_code} - {response.text}")
                return []
                
        except Exception as e:
            _logger.error(f"Error al consultar modelos disponibles: {str(e)}")
            return []
    
    def analyze_price_trends(self, products_data):
        """Analiza tendencias de precios usando Claude"""
        try:
            system_prompt = """
            Eres un analista de mercado. Analiza los siguientes datos de precios 
            y proporciona insights sobre tendencias, productos más caros/baratos, 
            y recomendaciones.
            """
            
            user_prompt = f"Analiza estos datos de precios:\n{json.dumps(products_data, indent=2)}"
            
            response = self.client.messages.create(
                model=self.model,
                max_tokens=500,
                temperature=0.3,
                system=system_prompt,
                messages=[
                    {"role": "user", "content": user_prompt}
                ]
            )
            
            return response.content[0].text.strip()
            
        except Exception as e:
            _logger.error(f"Error en analyze_price_trends: {str(e)}")
            return "No se pudo realizar el análisis de tendencias."