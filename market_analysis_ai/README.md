# Market Analysis AI - Módulo de Odoo 18

## Descripción
Módulo de Odoo 18 para análisis de mercados que integra OpenAI y Telegram para recibir y procesar reportes de precios de productos mediante lenguaje natural.

## Características
- ✅ Recepción automática de mensajes desde Telegram
- ✅ Procesamiento con OpenAI para extraer productos y precios
- ✅ Interfaz simple con vista lista y formulario
- ✅ Configuración segura de API keys
- ✅ Notificaciones y seguimiento con chatter
- ✅ Estadísticas de precios por producto

## Requisitos
- Odoo 18
- Python 3.8+
- Librerías Python:
  ```bash
  pip install openai requests
  ```

## Instalación

1. **Copiar el módulo**
   ```bash
   cp -r market_analysis_ai /path/to/odoo/addons/
   ```

2. **Actualizar lista de aplicaciones**
   - Ir a Apps → Actualizar lista de aplicaciones
   - Buscar "Market Analysis AI"
   - Instalar

3. **Configurar APIs**
   - Ir a AI Analysis → Configuración → API Settings
   - Ingresar las credenciales:
     - OpenAI API Key
     - Token del Bot de Telegram
     - Chat ID de Telegram

## Configuración

### OpenAI
1. Obtener API Key desde [OpenAI Platform](https://platform.openai.com/api-keys)
2. Copiar la key completa (formato: sk-proj-...)

### Telegram Bot
1. Crear un bot con [@BotFather](https://t.me/BotFather)
2. Guardar el token del bot
3. Obtener el Chat ID:
   - Añadir el bot a un grupo o iniciar chat privado
   - Enviar un mensaje de prueba
   - Visitar: `https://api.telegram.org/bot[TU_TOKEN]/getUpdates`
   - Buscar `"chat":{"id":` y copiar el número

## Uso

### Enviar reportes de precios
Los usuarios pueden enviar mensajes en lenguaje natural al bot de Telegram:
- "El arroz está a 2.50"
- "Vi que el aceite subió a $4.20"
- "Tomates 1.80, papas 2.30"
- "Precio del pollo: 5.99"

### Ver reportes
- Ir a AI Analysis → Análisis de Mercados
- Los reportes se muestran con:
  - Producto
  - Precio
  - Fecha de recepción
  - Usuario que envió
  - Estado del procesamiento

### Funciones adicionales
- **Reprocesar**: En caso de error, se puede reprocesar el mensaje
- **Filtros**: Por fecha, producto, usuario, estado
- **Agrupación**: Por producto para ver tendencias


## Personalización

### Modificar el prompt de OpenAI
Editar `services/openai_service.py` en el método `process_price_report()` para ajustar cómo se extraen los productos y precios.

### Cambiar frecuencia de polling
Editar `data/cron_data.xml` y modificar `interval_number` (por defecto: 1 minuto).

### Añadir campos adicionales
1. Agregar campos en `models/market_analysis_report.py`
2. Actualizar las vistas en `views/market_analysis_report_views.xml`
3. Modificar el servicio de OpenAI para extraer la información adicional

## Solución de problemas

### El bot no responde
1. Verificar que el cron job esté activo
2. Revisar las credenciales en Configuración
3. Usar el botón "Probar Conexión"
4. Revisar los logs del servidor

### Errores de procesamiento
1. Verificar el formato del mensaje
2. Revisar el campo "Notas de Procesamiento" en el reporte
3. Usar el botón "Reprocesar" si es necesario

## Seguridad
- Las API keys se almacenan con widget password
- Solo administradores pueden ver/editar configuración
- Usuarios normales solo pueden crear y ver reportes

## Soporte
Para reportar problemas o sugerencias, contactar al equipo de desarrollo.