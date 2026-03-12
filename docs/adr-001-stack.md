# ADR-001 — Stack Tecnológico: Cospec Telecomunicaciones

**Fecha**: 2026-03-11
**Estado**: ACEPTADO
**Autores**: Equipo Cospec / Claude Code

---

## Contexto

Se necesita elegir el stack completo para implementar la plataforma de reclamos y operaciones de campo de Cospec Telecomunicaciones. Restricciones:

- **Budget**: Minimizar costos de infraestructura — preferir tiers gratuitos para v1.
- **Equipo**: Desarrolladores Python + Angular.
- **Escala v1**: < 50 técnicos, < 500 tickets/día, < 100 usuarios concurrentes.
- **Timeline**: Implementación por fases, comenzando por backend core.
- **Operaciones de campo**: Acceso desde móvil vía browser (PWA), no app nativa.

---

## Decisiones

### Backend: Python 3.12 + FastAPI 0.115

**Alternativas consideradas**: Django REST Framework, Node.js/Express, Go/Gin.

**Justificación**:
- FastAPI: async nativo, Pydantic v2 para validación, generación automática de OpenAPI docs, performance comparable a Node.js.
- Python 3.12: mejoras de performance, tipado estático moderno.
- El equipo tiene expertise en Python.
- Ecosistema rico para las integraciones requeridas (Telegram, geocoding, Excel, storage).

**Consecuencias**: Se requiere Python 3.12+ en producción. Usar `asyncpg` como driver de DB para aprovechar el async de FastAPI.

---

### Frontend: Angular 17+ (standalone components)

**Alternativas consideradas**: React, Vue 3, Next.js.

**Justificación**:
- El equipo tiene expertise en Angular.
- Angular Material proporciona componentes de UI listos para el caso de uso (tables, forms, maps).
- Standalone components (Angular 17) reducen boilerplate de NgModules.
- Angular PWA (`@angular/pwa`) habilitado para acceso móvil desde campo.
- RxJS nativo para manejo de SSE (streams de eventos).

**Consecuencias**: Requiere Node.js 20+ para build. Bundle inicial puede ser mayor que React — mitigar con lazy loading por módulo (admin/tech/customer).

---

### Base de datos: PostgreSQL 16

**Alternativas consideradas**: MySQL 8, SQLite (descartado para producción), MongoDB.

**Justificación**:
- `jsonb` nativo para `skills[]`, `default_checklist`, `payload` de eventos — sin necesidad de ORM especial.
- Índices parciales (`WHERE deleted_at IS NULL`) para performance en soft-deletes.
- `ARRAY` type para `skills text[]`.
- FTS nativo disponible si se necesita búsqueda de tickets en v2.
- Neon (PostgreSQL SaaS) ofrece 3GB free tier con branching para dev/staging.

**Producción gratuita**: Neon free tier (3GB, ~20 conexiones simultáneas).
**Local dev**: Docker image `postgres:16-alpine`.

**Consecuencias**: Usar connection pooling (PgBouncer o Neon pooler) antes de ir a producción para no saturar conexiones.

---

### Cache y Queue Broker: Redis 7

**Alternativas consideradas**: RabbitMQ (más robusto pero más complejo), Amazon SQS (no gratuito en escala), Celery con Redis (más pesado).

**Justificación**:
- Redis cubre dos necesidades con una sola instancia: cache (rate limiting, SSE) y queue broker para ARQ.
- ARQ usa Redis como backend — arquitectura simple.
- Upstash Redis: free tier suficiente para v1.

**Producción gratuita**: Upstash Redis free tier (10K commands/day — aumentar si necesario).
**Local dev**: Docker image `redis:7-alpine`.

---

### Task Workers: ARQ

**Alternativas consideradas**: Celery (más maduro, más complejo), RQ, Dramatiq.

**Justificación**:
- ARQ es async-native (asyncio) — compatible con FastAPI sin ejecutar workers en threads separados.
- Usa Redis (ya en el stack) — sin dependencia adicional.
- Syntax simple para definir jobs y crons.
- Suficiente para v1 (notificaciones, geocoding, export, Telegram mirror).

**Consecuencias**: Para v2 con mayor escala, evaluar migración a Celery o añadir más workers ARQ horizontalmente.

---

### Object Storage: Cloudflare R2 (producción) / MinIO (local)

**Alternativas consideradas**: AWS S3, Google Cloud Storage, Backblaze B2, Supabase Storage.

**Justificación**:
- **Cloudflare R2**: S3-compatible (boto3 funciona sin cambios), **0 costo de egress** (crítico para descargar fotos de evidencias), 10GB free + 10M operaciones/mes.
- **MinIO**: S3-compatible, Docker, completamente gratuito para dev local. Mismo boto3 client — zero cambio de código entre dev y prod (solo cambiar endpoint URL y credenciales).
- S3 y GCS cobran egress — inaceptable para una app de fotos de campo.

**Consecuencias**: Configurar `R2_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY` en producción. En local, usar MinIO con mismas variables apuntando a `http://localhost:9000`.

---

### Email: Brevo (ex-Sendinblue)

**Alternativas consideradas**: Resend (100/día free), SendGrid (100/día free), Mailgun (pagas después de trial), AWS SES (no free tier significativo).

**Justificación**:
- **9.000 emails/mes gratis** (300/día) — suficiente para v1.
- Cubre también **SMS** en el mismo SDK y cuenta — un proveedor para ambos canales.
- SDK Python oficial (`sib-api-v3-sdk`).
- Templates HTML en dashboard de Brevo — sin necesidad de gestionar templates en código para empezar.

**Consecuencias**: Límite de 300 emails/día puede alcanzarse con muchos tickets. Monitorear y escalar a plan paid si necesario. Verificar dominio de envío en Brevo para evitar spam.

---

### SMS: Brevo

**Justificación**: Mismo proveedor que email — reduce complejidad operacional. Free tier incluye ~160 SMS/mes de prueba. SMS es canal opcional/fallback ya que el sistema tiene Telegram como canal principal para técnicos/admin.

**Consecuencias**: SMS **no es el canal principal** — es fallback para clientes sin Telegram. El canal primario para técnicos/admin es Telegram (gratuito, sin límites). Si el volumen de SMS escala, evaluar Twilio (pay-as-you-go, ~$0.05/SMS).

---

### Geocoding: Nominatim (OSM) vía geopy

**Alternativas consideradas**: Google Maps Geocoding API (billing requerido), HERE (free tier 250K/mes), Mapbox (100K/mes free).

**Justificación**:
- **Completamente gratuito** sin límites de volumen mensual (solo rate limit de 1 req/s).
- geopy maneja el rate limiting automáticamente con `geopy.geocoders.Nominatim(user_agent="cospec-api")`.
- Para v1 con < 500 tickets/día el throughput es más que suficiente (cola de geocoding procesa 1/s).
- Si se necesita mayor precisión o velocidad en v2: migrar a HERE o Google Maps cambiando solo el geocoder en el worker.

**Consecuencias**: Obligatorio setear `user_agent` con nombre de la app para cumplir TOS de Nominatim. No usar en producción sin user_agent o se bloqueará la IP.

---

### Telegram: python-telegram-bot 21.x

**Alternativas consideradas**: httpx directo a Telegram API, aiogram.

**Justificación**:
- python-telegram-bot 21.x es async nativo (asyncio) — compatible con FastAPI.
- API de alto nivel para manejar commands, webhooks y envío de mensajes.
- Comunidad grande, documentación excelente.

**Consecuencias**: Requiere token del bot (`TELEGRAM_BOT_TOKEN`) y secret para webhook (`TELEGRAM_WEBHOOK_SECRET`). Se configurará cuando el usuario provea las credenciales del bot.

---

## Mapa de variables de entorno requeridas

Ver `.env.example` en raíz del proyecto.

## Infraestructura local (dev)

Ver `docker-compose.yml` en raíz del proyecto.
Levantar con: `docker compose up -d`

## Orden de implementación recomendado

```
Fase 1 — Core backend:
  shared/ → data/ (migrations + models) → api/auth → api/tickets (CRUD) → tests unit

Fase 2 — Operaciones de campo:
  api/status (transitions) → api/attachments (presign R2) → api/checklist → api/messages

Fase 3 — Async:
  workers/notifications (Brevo) → workers/geocoding (Nominatim) → workers/exports (openpyxl)

Fase 4 — Integraciones:
  SSE → Telegram bot → Dashboard endpoints

Fase 5 — Frontend Angular:
  auth → tickets list/detail → tech dashboard → admin dashboard → export UI
```

---

## Links de registro requeridos

| Servicio | URL | Qué obtener |
|----------|-----|-------------|
| Brevo | brevo.com | API Key, verificar dominio |
| Cloudflare R2 | dash.cloudflare.com | Account ID, Access Key, Secret Key, bucket name |
| Neon | neon.tech | Connection string PostgreSQL |
| Upstash | upstash.com | Redis URL + password |
| Telegram | @BotFather en Telegram | Bot token |
