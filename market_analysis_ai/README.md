# Market Analysis AI - Módulo de Odoo 18

## Descripción
Módulo de Odoo 18 para análisis de mercados que integra **OpenAI** o **Claude (Anthropic)** con Telegram para recibir y procesar reportes de precios de productos mediante lenguaje natural.

## Características
- ✅ **Doble soporte de AI**: OpenAI (GPT-3.5, GPT-4) y Claude (Haiku, Sonnet, Opus)
- ✅ Recepción automática de mensajes desde Telegram
- ✅ Procesamiento inteligente con AI para extraer productos y precios
- ✅ Interfaz simple con vista lista y formulario
- ✅ Configuración segura de API keys
- ✅ Notificaciones y seguimiento con chatter
- ✅ Estadísticas de precios por producto
- ✅ Estadísticas de uso por proveedor de AI

## Requisitos
- Odoo 18
- Python 3.8+
- Librerías Python:
  ```bash
  pip install openai anthropic requests
  ```

## Instalación

1. **Copiar el módulo**
   ```bash
   cp -r market_analysis_ai /path/to/odoo/addons/
   ```

2. **Instalar dependencias**
   ```bash
   pip install -r market_analysis_ai/requirements.txt
   ```

3. **Actualizar lista de aplicaciones**
   - Ir a Apps → Actualizar lista de aplicaciones
   - Buscar "Market Analysis AI"
   - Instalar

4. **Configurar APIs**
   - Ir a AI Analysis → Configuración → API Settings
   - Seleccionar el proveedor de AI (OpenAI o Claude)
   - Ingresar las credenciales correspondientes

## Configuración

### Proveedores de AI

#### OpenAI
1. Obtener API Key desde [OpenAI Platform](https://platform.openai.com/api-keys)
2. Copiar la key completa (formato: sk-proj-...)
3. Modelos disponibles:
   - **GPT-3.5 Turbo**: Más económico, ideal para tareas simples
   - **GPT-4**: Mayor precisión y capacidad
   - **GPT-4 Turbo**: Versión mejorada con contexto extendido

#### Claude (Anthropic)
1. Obtener API Key desde [Anthropic Console](https://console.anthropic.com/api-keys)
2. Copiar la key completa (formato: sk-ant-...)
3. Modelos disponibles:
   - **Claude 3 Haiku**: Más rápido y económico
   - **Claude 3 Sonnet**: Balance entre velocidad y capacidad
   - **Claude 3 Opus**: Máxima capacidad y precisión

### Telegram Bot
1. Crear un bot con [@BotFather](https://t.me/BotFather)
2. Guardar el token del bot
3. El bot responderá automáticamente a todos los usuarios

## Uso

### Enviar reportes de precios
Los usuarios pueden enviar mensajes en lenguaje natural al bot de Telegram:
- "El arroz está a 2.50"
- "Vi que el aceite subió a $4.20"
- "Tomates 1.80, papas 2.30"
- "Precio del pollo: 5.99"

### Ver reportes
- Ir a AI Analysis → Análisis de Mercados
- Los reportes muestran:
  - Producto y precio
  - Fecha de recepción
  - Usuario que envió
  - Proveedor de AI usado
  - Estado del procesamiento

### Funciones adicionales
- **Reprocesar**: En caso de error, se puede reprocesar con el proveedor actual
- **Filtros**: Por fecha, producto, usuario, proveedor AI, estado
- **Agrupación**: Por producto para ver tendencias
- **Cambiar proveedor**: Modificar en Configuración y los nuevos mensajes usarán el nuevo proveedor

## Comparación de Proveedores

| Característica | OpenAI | Claude (Anthropic) |
|----------------|--------|--------------------|
| **Precisión** | Excelente, especialmente GPT-4 | Excelente, especialmente Claude 3 Opus |
| **Velocidad** | Rápida con GPT-3.5 Turbo | Muy rápida con Claude 3 Haiku |
| **Costo** | Variable según modelo | Generalmente más económico |
| **Contexto** | Hasta 128k tokens (GPT-4 Turbo) | Hasta 200k tokens (todos los modelos) |
| **Idiomas** | Excelente soporte multilingüe | Excelente soporte multilingüe |

## Personalización

### Modificar el prompt de AI
Editar `services/openai_service.py` o `services/claude_service.py` en el método `process_price_report()` para ajustar cómo se extraen los productos y precios.

### Cambiar frecuencia de polling
Editar `data/cron_data.xml` y modificar `interval_number` (por defecto: 1 minuto).

### Añadir campos adicionales
1. Agregar campos en `models/market_analysis_report.py`
2. Actualizar las vistas en `views/market_analysis_report_views.xml`
3. Modificar los servicios de AI para extraer la información adicional

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
4. Verificar que el modelo de AI seleccionado esté disponible

### Cambiar de proveedor
1. Ir a Configuración
2. Seleccionar el nuevo proveedor
3. Configurar la API key correspondiente
4. Seleccionar el modelo deseado
5. Guardar y probar conexión

## Seguridad
- Las API keys se almacenan con widget password
- Solo administradores pueden ver/editar configuración
- Usuarios normales solo pueden crear y ver reportes
- Los tokens no se muestran en logs

## Versiones
- 1.0: Soporte inicial con OpenAI
- 1.1: Añadido soporte para Claude (Anthropic)

## Soporte
Para reportar problemas o sugerencias, contactar al equipo de desarrollo.