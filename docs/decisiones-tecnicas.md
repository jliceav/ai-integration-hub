# Decisiones técnicas

Por qué el proyecto está hecho así. Cada punto responde a la pregunta "¿por qué no lo hiciste de otra forma?".

## 1. FastAPI en lugar de Flask o Django

- Valida automáticamente la entrada con Pydantic: si falta un campo o el correo es inválido, responde 422 sin escribir código extra.
- Genera la documentación OpenAPI (`/docs`) sola. API Management la importa directamente.
- Django sería excesivo para un servicio de integración sin panel de administración ni plantillas.

## 2. REST y GraphQL a la vez

- **REST** para sistemas que solo empujan datos (WooCommerce, formularios, WhatsApp): simple, universal y fácil de probar con `curl`.
- **GraphQL** para quien consulta (dashboards, CRM): pide exactamente los campos que necesita en una sola petición.
- Ambos llaman al **mismo servicio** (`services/leads.py`), así que la lógica no se duplica.

## 3. Adaptador para la IA

- El negocio solo conoce `ai.analyze(mensaje)`. Cambiar Anthropic por OpenAI es cambiar una variable de entorno.
- Se exige a la IA una **respuesta JSON** que se valida contra un esquema. Si la IA inventa un valor, se descarta.
- **La IA nunca tumba la integración**: si falla, el lead se guarda con valores neutros y no se pierde.
- **Reintentos solo en errores temporales** (429 y 5xx) con espera exponencial. Un 401 (llave mala) no se reintenta porque no se va a arreglar solo.

## 4. Idempotencia

WooCommerce y otros sistemas **reenvían** un webhook si no reciben respuesta a tiempo. Una restricción única `(source, external_id)` garantiza que el mismo pedido no se duplique ni se cobre dos veces el análisis de IA.

## 5. Seguridad

- **Webhooks**: se verifica la firma HMAC-SHA256 que envía WooCommerce, calculada sobre el cuerpo crudo. Sin firma válida, 401.
- **API interna**: header `X-API-Key`, comparado con `hmac.compare_digest` para evitar ataques de tiempo.
- **Secretos** solo por variables de entorno. `.env` está en `.gitignore`, y en Azure se usan secretos de Container Apps.
- **Contenedor** sin usuario root e imagen multi-stage más pequeña (menos superficie de ataque).

## 6. Disponibilidad y operación

- `/health` revisa la base de datos. Docker (`HEALTHCHECK`) y Azure lo usan para reiniciar réplicas enfermas.
- `pool_pre_ping` reconecta solo si la base de datos cerró la conexión.
- **Request ID** en cada respuesta y en los logs: permite seguir una petición de punta a punta al depurar una integración.
- Container Apps escala de 1 a 3 réplicas según la carga.

## 7. Qué mejoraría para producción

- Procesar la IA **en segundo plano** (cola con Azure Service Bus) para responder al webhook en milisegundos.
- **Alembic** para migraciones de base de datos en lugar de `create_all`.
- **Azure Key Vault** y Managed Identity en lugar de secretos en variables.
- **OAuth2 / Entra ID** en lugar de una sola API key compartida.
- Métricas y trazas con **Application Insights / OpenTelemetry**.
