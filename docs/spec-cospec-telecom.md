## Especificación Técnica v2 — Cospec Telecomunicaciones
**Dominio**: Gestión de reclamos y operaciones de campo.
**Versión**: 2.0 | **Fecha**: 2026-03-11 | **Estado**: APROBADA

---

### Stack de Tecnología

| Capa | Tecnología | Versión mínima | Tier gratuito |
|------|-----------|----------------|---------------|
| Backend | Python + FastAPI | 3.12 / 0.115 | — |
| Frontend | Angular | 17+ (standalone) | — |
| Base de datos | PostgreSQL | 16 | Neon (3GB free) / Docker local |
| Cache + Queue broker | Redis | 7 | Upstash (free tier) / Docker local |
| Task workers | ARQ (async Celery-like) | 0.26+ | — (usa Redis) |
| Object storage | Cloudflare R2 | — | 10GB + 0 egress free |
| Object storage local | MinIO (Docker) | RELEASE.2024+ | self-hosted |
| Email | Brevo (ex-Sendinblue) | SDK v7.6+ | 9.000 emails/mes gratis |
| SMS | Brevo | SDK v7.6+ | ~160 SMS/mes gratis |
| Geocoding | Nominatim (OSM) vía geopy | geopy 2.4+ | gratuito (1 req/s) |
| Telegram bot | python-telegram-bot | 21.x (async) | gratuito |
| Excel export | openpyxl | 3.1+ | — |
| Structured logging | structlog | 24.0+ | — |
| Schema validation | Pydantic v2 | 2.9+ | — |
| ORM | SQLAlchemy async | 2.0+ | — |
| Migrations | Alembic | 1.14+ | — |
| Email local (dev) | Mailpit (Docker) | — | self-hosted |

### Arquitectura

- **Backend**: REST API bajo `/api/v1/`, JSON, versioning en path. FastAPI con Pydantic v2.
- **Frontend**: Angular 17+ (PWA, standalone components). Angular Material UI. Deep links a Google Maps/Waze.
- **Storage**: Cloudflare R2 (producción) / MinIO (local). S3-compatible — boto3 como client. URLs presignadas con expiración de 1 hora para downloads, 15 min para uploads.
- **DB**: PostgreSQL 16. SQLAlchemy 2.0 async + asyncpg driver. Alembic para migraciones.
- **Workers**: ARQ sobre Redis. Queues: `notifications`, `exports`, `geocoding`, `telegram_mirror`.
- **Cache**: Redis 7 — rate-limit counters (sliding window), SSE heartbeat tracking.
- **Real-time**: Server-Sent Events (SSE) sobre `GET /api/v1/events`.
- **Observabilidad**: structlog (JSON) con `trace_id`, métricas p50/p95/p99, audit trail en `ticket_events`.

---

### Formato de respuesta estándar

Toda respuesta exitosa usa el envelope:
```json
{
  "success": true,
  "data": {},
  "error": null,
  "meta": { "timestamp": "ISO-8601", "version": "v1" }
}
```

Toda respuesta de error:
```json
{
  "success": false,
  "data": null,
  "error": {
    "type": "ValidationError",
    "code": "TICKET_INVALID_TRANSITION",
    "message": "No se puede transitar de 'abierto' a 'cerrado'.",
    "trace_id": "abc-123",
    "timestamp": "ISO-8601"
  },
  "meta": { "timestamp": "ISO-8601", "version": "v1" }
}
```

**Nunca retornar HTTP 200 con error dentro del body.**

Códigos de error del dominio:
| Code | HTTP | Descripción |
|------|------|-------------|
| `AUTH_INVALID_CREDENTIALS` | 401 | Email/contraseña incorrectos |
| `AUTH_TOKEN_EXPIRED` | 401 | Access token expirado |
| `AUTH_TOKEN_INVALID` | 401 | Token malformado o firmado incorrectamente |
| `AUTH_EMAIL_NOT_VERIFIED` | 403 | Email sin verificar; no puede crear tickets |
| `AUTH_REFRESH_TOKEN_REVOKED` | 401 | Refresh token ya utilizado o revocado |
| `TICKET_INVALID_TRANSITION` | 400 | Transición de estado no permitida |
| `TICKET_CHECKLIST_INCOMPLETE` | 422 | Cierre rechazado: checklist incompleto |
| `TICKET_NO_EVIDENCE` | 422 | Cierre rechazado: sin evidencia mínima |
| `ASSIGNMENT_NO_CANDIDATE` | 422 | Auto-asignación sin técnico elegible |
| `GEOCODING_FAILED` | 422 | No se pudo resolver lat/lon de la dirección |
| `RATE_LIMIT_EXCEEDED` | 429 | Demasiadas peticiones |
| `VALIDATION_FAILED` | 422 | Validación de campos (incluye array `errors[]`) |
| `NOT_FOUND` | 404 | Recurso no encontrado |
| `FORBIDDEN` | 403 | Rol insuficiente para la operación |

---

### Roles y permisos

| Recurso | admin | tech | customer |
|---------|-------|------|----------|
| Crear técnico | ✓ | — | — |
| Editar técnico | ✓ | — | — |
| Crear ticket | ✓ | — | ✓ |
| Ver todos los tickets | ✓ | Solo asignados | Solo propios |
| Asignar ticket | ✓ | — | — |
| Cambiar estado | ✓ | Solo tickets asignados | — |
| Subir evidencias | ✓ | Solo tickets asignados | — |
| Ver evidencias | ✓ | ✓ (propias) | ✓ (solo lectura) |
| Editar evidencias | ✓ | Hasta cierre | — |
| Reprogramar | ✓ | ✓ (si habilitado por config) | ✓ (propone) |
| Chat del ticket | ✓ | ✓ | ✓ |
| Exportar reportes | ✓ | — | — |
| Configurar categorías/SLA | ✓ | — | — |
| Dashboard admin | ✓ | — | — |
| Dashboard tech | — | ✓ | — |

---

### Auth Strategy

**JWT + Refresh Token Rotation**

- **Access token**: TTL 15 minutos. Payload: `{ sub: user_id, role, email, iat, exp }`. Firmado con HS256 (clave desde `JWT_SECRET` env var, mínimo 32 bytes).
- **Refresh token**: TTL 7 días. Token opaco (UUID v4). Almacenado como hash (SHA-256) en tabla `refresh_tokens`. Se invalida al usarse (rotation obligatoria).
- **Storage en cliente**: access token en memoria (no localStorage). Refresh token en cookie `HttpOnly; Secure; SameSite=Strict`.
- **Logout**: revoca el refresh token activo en DB (`revoked_at = NOW()`). El access token expira de forma natural (exposición máxima: 15 min).
- **Revocación inmediata**: si se requiere (ej. cuenta comprometida), setear `users.active = false`. El middleware valida `active` en cada request.
- **Password**: bcrypt, cost factor 12. Nunca loguear. Nunca retornar. Nunca almacenar en texto plano.
- **Email verification**: al registrarse, se envía email con token de 1 uso (UUID, TTL 24h) almacenado en `email_verification_tokens`. Hasta verificar, el usuario puede hacer login pero NO puede crear tickets (`AUTH_EMAIL_NOT_VERIFIED`).
- **Password reset**: `POST /api/v1/auth/forgot-password` genera token de 1 uso (TTL 1h) en `password_reset_tokens`. `POST /api/v1/auth/reset-password` lo consume y actualiza el hash.

**Flujos de autenticación**:
1. **Registro cliente**: `POST /api/v1/auth/register` → crea user (role=customer, active=true, email_verified=false) → envía email verificación → retorna user + access token + refresh token cookie.
2. **Login**: `POST /api/v1/auth/login` → valida credenciales → retorna access token + set-cookie refresh token.
3. **Refresh**: `POST /api/v1/auth/refresh` → lee refresh token de cookie → valida en DB → revoca el actual → emite nuevo par.
4. **Logout**: `POST /api/v1/auth/logout` → revoca refresh token de cookie → borra cookie.
5. **Me**: `GET /api/v1/auth/me` → retorna el usuario del access token.

---

### Customer Registration

- Self-registration: `POST /api/v1/auth/register` (name, email, password, phone).
- Admin puede crear customers directamente: `POST /api/v1/users/customer` (skipea verificación de email).
- Restricción: customers con `email_verified = false` reciben error `AUTH_EMAIL_NOT_VERIFIED` al intentar `POST /api/v1/tickets`.
- Admin puede reenviar email de verificación: `POST /api/v1/users/{id}/resend-verification`.

---

### Categorías y Configuración de SLA

**Categorías de ticket** (admin-configurable, no hardcodeadas en código):

Valores iniciales del seed: `instalacion`, `reparacion`, `mantenimiento`, `inspeccion`, `emergencia`, `consulta`.

Cada categoría define:
- `name`, `slug` (único)
- `default_checklist: jsonb` — items de checklist por defecto para tickets de esta categoría
- `required_skills: text[]` — skills mínimos requeridos para la asignación automática
- `sla_rules: [{ priority, sla_hours }]` — reglas SLA por prioridad

**Lógica de cálculo SLA**:
```
sla_due_at = created_at + INTERVAL(sla_rules[category][priority].sla_hours + ' hours')
```

Fallback si no existe regla específica (defaults globales):
| Prioridad | SLA |
|-----------|-----|
| critical | 4 horas |
| high | 8 horas |
| medium | 24 horas |
| low | 72 horas |

**SLA en reprogramación**: NO se resetea automáticamente. Para evitar gaming (re-agendar para extender SLA), el SLA se congela. Admin puede override explícito con `sla_override: true` en el payload de reprogramación.

**SLA breach**: `NOW() > sla_due_at AND status NOT IN ('resuelto', 'cerrado')`. Se evalúa en queries del dashboard y en el worker periódico (cada 5 min) que emite evento SSE `ticket.sla_breach` a admins conectados.

---

### Modelo de datos

```sql
-- Existentes (actualizados)
users(
  id uuid PK,
  role text CHECK(role IN ('admin','tech','customer')),
  name text,
  email text UNIQUE,
  phone text,
  zone text,                         -- solo aplica a técnicos
  skills text[],                     -- solo aplica a técnicos
  active bool DEFAULT true,
  email_verified bool DEFAULT false, -- nuevo
  email_verified_at timestamptz,     -- nuevo
  created_at timestamptz,
  updated_at timestamptz,
  deleted_at timestamptz             -- soft delete
)

tickets(
  id uuid PK,
  title text,
  description text,
  category text,                     -- FK a categories.slug (no FK hard para flexibilidad)
  priority text CHECK(priority IN ('low','medium','high','critical')),
  status text CHECK(status IN ('abierto','asignado','en_ruta','en_sitio','en_trabajo','resuelto','cerrado')),
  sla_due_at timestamptz,
  sla_override bool DEFAULT false,   -- nuevo
  geocoding_status text DEFAULT 'done' CHECK(geocoding_status IN ('pending','done','failed')), -- nuevo
  customer_id uuid FK users,
  assigned_to uuid FK users NULLABLE,
  address text,
  lat numeric(9,6) NULLABLE,
  lon numeric(9,6) NULLABLE,
  window_start timestamptz NULLABLE,
  window_end timestamptz NULLABLE,
  created_at timestamptz,
  updated_at timestamptz,
  closed_at timestamptz NULLABLE,
  deleted_at timestamptz
)

ticket_events(
  id uuid PK,
  ticket_id uuid FK tickets,
  actor_id uuid FK users,
  type text,                         -- created|assigned|status_changed|evidence_added|evidence_edited|message_sent|rescheduled|closed|sla_breach|ai_queried
  payload jsonb,
  created_at timestamptz
)

checklists(
  id uuid PK,                        -- nuevo: PK explícita
  ticket_id uuid FK tickets,
  item text,
  status text DEFAULT 'pending' CHECK(status IN ('pending','done')),
  updated_by uuid FK users NULLABLE,
  created_at timestamptz,
  updated_at timestamptz
)

messages(
  id uuid PK,
  ticket_id uuid FK tickets,
  sender_id uuid FK users,
  body text,
  attachment_id uuid FK attachments NULLABLE, -- nuevo
  created_at timestamptz
)

attachments(
  id uuid PK,
  ticket_id uuid FK tickets,
  uploader_id uuid FK users,
  storage_key text,                  -- path en bucket (NO exponer al cliente)
  original_filename text,
  content_type text,
  type text CHECK(type IN ('photo','doc','note')),
  created_at timestamptz,
  deleted_at timestamptz
)

appointments(
  id uuid PK,
  ticket_id uuid FK tickets,
  window_start timestamptz,
  window_end timestamptz,
  status text CHECK(status IN ('pending','confirmed','rescheduled','cancelled')),
  updated_by uuid FK users,
  updated_at timestamptz,
  created_at timestamptz
)

exports(
  id uuid PK,
  period_date date,
  kind text CHECK(kind IN ('daily','monthly','annual')),
  storage_key text,                  -- path en bucket
  generated_at timestamptz,
  status text CHECK(status IN ('scheduled','running','completed','failed')),
  triggered_by uuid FK users,        -- nuevo: para notificar al admin correcto
  error_message text NULLABLE,       -- nuevo: causa de fallo
  created_at timestamptz
)

-- Nuevas tablas
categories(
  id uuid PK,
  name text,
  slug text UNIQUE,
  default_checklist jsonb,           -- [{"item": "Verificar equipo", ...}]
  required_skills text[],
  active bool DEFAULT true,
  created_at timestamptz,
  updated_at timestamptz
)

sla_rules(
  id uuid PK,
  category_id uuid FK categories,
  priority text CHECK(priority IN ('low','medium','high','critical')),
  sla_hours int,
  created_at timestamptz,
  UNIQUE(category_id, priority)
)

refresh_tokens(
  id uuid PK,
  user_id uuid FK users,
  token_hash text UNIQUE,            -- SHA-256 del token opaco
  expires_at timestamptz,
  revoked_at timestamptz NULLABLE,
  created_at timestamptz
)

telegram_links(
  id uuid PK,
  user_id uuid FK users UNIQUE,
  chat_id text UNIQUE,
  linked_at timestamptz
)

telegram_link_codes(
  id uuid PK,
  user_id uuid FK users,
  code text UNIQUE,                  -- código temporal de 6 dígitos
  expires_at timestamptz,
  used_at timestamptz NULLABLE,
  created_at timestamptz
)

email_verification_tokens(
  id uuid PK,
  user_id uuid FK users,
  token_hash text UNIQUE,
  expires_at timestamptz,
  used_at timestamptz NULLABLE,
  created_at timestamptz
)

password_reset_tokens(
  id uuid PK,
  user_id uuid FK users,
  token_hash text UNIQUE,
  expires_at timestamptz,
  used_at timestamptz NULLABLE,
  created_at timestamptz
)
```

**Índices**:
```sql
CREATE INDEX idx_tickets_status_sla ON tickets(status, sla_due_at);
CREATE INDEX idx_tickets_assigned_status ON tickets(assigned_to, status) WHERE deleted_at IS NULL;
CREATE INDEX idx_tickets_customer ON tickets(customer_id, created_at) WHERE deleted_at IS NULL;
CREATE INDEX idx_tickets_zone_status ON tickets(category, status) WHERE deleted_at IS NULL;
CREATE INDEX idx_ticket_events_ticket ON ticket_events(ticket_id, created_at);
CREATE INDEX idx_messages_ticket ON messages(ticket_id, created_at);
CREATE INDEX idx_attachments_ticket ON attachments(ticket_id) WHERE deleted_at IS NULL;
CREATE INDEX idx_checklists_ticket ON checklists(ticket_id);
CREATE INDEX idx_refresh_tokens_user ON refresh_tokens(user_id) WHERE revoked_at IS NULL;
```

---

### Flujos

**Alta de técnico (solo admin)**: crea user role=tech; requiere zona/skills; activo por defecto.

**Registro cliente**: POST /api/v1/auth/register → user role=customer, email_verified=false → job envía email de verificación → cliente verifica → puede crear tickets.

**Crear ticket**:
1. Valida campos obligatorios (incluye category existente en categories.slug).
2. Calcula `sla_due_at` según reglas de la categoría + prioridad.
3. Si `lat/lon` no vienen en payload → `geocoding_status = 'pending'` → encola job de geocoding.
4. Si `lat/lon` vienen → `geocoding_status = 'done'`.
5. Inserta ticket con `status = 'abierto'`.
6. Inserta checklist items desde `categories.default_checklist`.
7. Crea `ticket_event(type='created')`.
8. Notifica a admins (SSE event: `ticket.created`).

**Asignación manual**: POST /api/v1/tickets/{id}/assign (admin). Valida técnico activo. Actualiza `assigned_to`, `status → 'asignado'`. Crea event. Notifica técnico (SSE + Telegram mirror).

**Auto-asignación**: POST /api/v1/tickets/{id}/auto-assign (admin). Algoritmo de scoring:
1. Filtra técnicos activos con `required_skills ⊆ tech.skills` y `tech.zone = ticket.zone`.
2. Score por técnico: `score = 100 - (tickets_activos * 10) - distancia_km_al_ultimo_ticket_activo`.
3. Elige técnico con mayor score. Si empate: menor `tickets_activos`. Si no hay candidatos → `422 ASSIGNMENT_NO_CANDIDATE`.

**Navegación**: técnico pulsa "Ir" → frontend abre deep link `https://www.google.com/maps/dir/?api=1&destination={lat},{lon}`. Botón deshabilitado si `geocoding_status != 'done'`. Al cambiar estado a `en_ruta` → `POST /api/v1/tickets/{id}/status { next_status: 'en_ruta', timestamp: <salida> }`.

**Transiciones de estado**:
```
abierto → asignado (solo vía /assign o /auto-assign)
asignado → en_ruta (técnico asignado)
en_ruta → en_sitio (técnico asignado)
en_sitio → en_trabajo (técnico asignado)
en_trabajo → resuelto (técnico asignado)
resuelto → cerrado (técnico asignado o admin; requiere checklist completo + ≥1 evidencia)
```
Admin puede retroceder tickets (reasignación) desde cualquier estado hasta `asignado`.

**Evidencias**: POST presign → upload directo a bucket → frontend confirma con attachment_id. Editables mientras `status != 'cerrado'`. Cada edición crea event en `ticket_events`. `GET /attachments` genera presigned download URLs (TTL 1h) en cada request; `storage_key` nunca se expone al cliente.

**Cierre**: Requiere `checklist.every(item.status == 'done')` + `attachments.count >= 1`. Si falla → `422 TICKET_CHECKLIST_INCOMPLETE` o `TICKET_NO_EVIDENCE`. Al cerrar: `closed_at = NOW()`, event de cierre, notificaciones a participantes.

**Reprogramación**: `POST /api/v1/tickets/{id}/appointments`. Crea nueva entrada en `appointments`. Si `sla_override: true` → admin puede extender `sla_due_at`. Notifica técnico + cliente. Crea event.

**Export**: job cron genera CSV/XLSX con columnas definidas. Almacena en bucket. Actualiza `exports.status`. Worker emite SSE `export.completed` al admin que lo disparó. `GET /exports/{id}` genera presigned download URL en cada request.

---

### Geocoding

- Proveedor configurable: `GEOCODING_PROVIDER=google|nominatim` (env var).
- **Google Maps Geocoding API**: alta precisión, requiere `GOOGLE_MAPS_API_KEY` y billing habilitado.
- **Nominatim (OSM)**: gratuito, rate limit 1 req/s, adecuado para < 1000 geocodificaciones/día.
- **Flujo async**: si ticket se crea sin lat/lon → `geocoding_status = 'pending'` → worker procesa en cola (retry 3 veces con backoff exponencial) → actualiza `lat`, `lon`, `geocoding_status = 'done'` → emite SSE `ticket.geocoded` para que el frontend reactive el botón de navegación.
- Si tras 3 intentos falla → `geocoding_status = 'failed'` → admin puede ingresar lat/lon manualmente vía `PATCH /api/v1/tickets/{id}`.

---

### Real-time Notifications (SSE)

- **Endpoint**: `GET /api/v1/events`
- **Auth**: Bearer token en header `Authorization` o query param `?token=<access_token>` (para compatibilidad con `EventSource` de browser que no permite headers custom).
- **Canal por usuario**: cada conexión recibe solo eventos del scope de su rol.
- **Formato**:
  ```
  id: <event_uuid>
  event: ticket.assigned
  data: {"ticket_id":"...","assigned_to":"...","title":"...","timestamp":"..."}

  ```
- **Reconnect**: clientes deben implementar reconexión automática con `Last-Event-ID`. El server re-emite eventos de los últimos 30 segundos si se provee `Last-Event-ID`.
- **Fallback polling**: `GET /api/v1/tickets?updated_after=<iso_timestamp>` para clientes offline.

**Eventos por rol**:
| Evento | admin | tech | customer |
|--------|-------|------|----------|
| `ticket.created` | ✓ | — | — |
| `ticket.assigned` | ✓ | ✓ (propio) | — |
| `ticket.status_changed` | ✓ | ✓ (propio) | ✓ (propio) |
| `ticket.message_added` | ✓ | ✓ (propio) | ✓ (propio) |
| `ticket.rescheduled` | ✓ | ✓ (propio) | ✓ (propio) |
| `ticket.sla_breach` | ✓ | — | — |
| `ticket.geocoded` | ✓ | ✓ (propio) | — |
| `export.completed` | ✓ (triggereador) | — | — |

---

### Telegram Bot

- **Tipo**: webhook. Telegram envía updates a `POST /api/v1/integrations/telegram/webhook`.
- **Seguridad**: validar header `X-Telegram-Bot-Api-Secret-Token` contra `TELEGRAM_WEBHOOK_SECRET` env var.
- **Vinculación de cuenta**:
  1. Usuario abre app web → solicita código: `GET /api/v1/integrations/telegram/link-code`.
  2. Recibe código temporal de 6 dígitos (TTL 10 min).
  3. Envía `/vincular <codigo>` al bot de Telegram.
  4. Bot confirma llamando `POST /api/v1/integrations/telegram/link` con `{ chat_id, code }`.
  5. Se crea registro en `telegram_links`.

**Eventos mirroreados (app → Telegram)**:
- Ticket asignado: `📋 Ticket #{{id}} asignado — {{título}} | {{dirección}}`
- Estado cambiado: `🔄 Ticket #{{id}} → {{nuevo_estado}}`
- Nuevo mensaje: `💬 {{remitente}} en Ticket #{{id}}: {{preview_50_chars}}`
- Reprogramado: `📅 Ticket #{{id}} reprogramado a {{ventana}}`
- SLA breach (solo admin): `⚠️ SLA BREACH — Ticket #{{id}} | {{categoría}} | {{prioridad}}`

**Comandos (Telegram → app)** — solo para roles vinculados:
| Comando | Rol | Equivalencia API |
|---------|-----|-----------------|
| `/estado <ticket_id>` | admin, tech, customer | GET /tickets/{id} |
| `/en_ruta <ticket_id>` | tech | POST /tickets/{id}/status { next_status: en_ruta } |
| `/en_sitio <ticket_id>` | tech | POST /tickets/{id}/status { next_status: en_sitio } |
| `/responder <ticket_id> <mensaje>` | admin, tech, customer | POST /tickets/{id}/messages |
| `/ayuda` | todos | Lista de comandos disponibles según rol |

- Bot valida que el técnico está asignado al ticket antes de procesar comandos de estado.
- Respuestas del bot son siempre texto plano (no markdown complejo para compatibilidad).

---

### Dashboard

**Admin Dashboard** (`GET /api/v1/dashboard/admin`):
```json
{
  "tickets_by_status": { "abierto": 12, "asignado": 8, ... },
  "sla": {
    "breach_count": 3,
    "breach_rate_7d": 0.05,
    "urgent_breaches": [{ "ticket_id": "...", "title": "...", "overdue_hours": 2.5 }]
  },
  "avg_resolution_hours": { "by_category": {}, "by_priority": {} },
  "created_today": 5,
  "created_this_week": 32,
  "tech_productivity": [
    { "tech_id": "...", "name": "...", "closed_today": 3, "closed_week": 18, "reschedules": 1 }
  ],
  "pending_exports": 0,
  "notifications_failed_24h": 0
}
```

**Tech Dashboard** (`GET /api/v1/dashboard/tech`):
```json
{
  "my_tickets_by_status": { "asignado": 3, "en_ruta": 1, "en_sitio": 0 },
  "next_appointments": [
    { "ticket_id": "...", "title": "...", "address": "...", "lat": 0, "lon": 0, "window_start": "..." }
  ],
  "pending_checklists": [{ "ticket_id": "...", "title": "...", "pending_count": 2 }],
  "today_route": [{ "ticket_id": "...", "title": "...", "address": "...", "lat": 0, "lon": 0 }]
}
```

---

### Notificaciones

- Evento de dominio → cola de notificaciones → worker envía por canal configurado: email / SMS / push.
- Canales por usuario: configurables en `users.notification_preferences jsonb`.
- Espejo a Telegram si el usuario tiene `telegram_links` activo.
- Plantillas por evento: `ticket.created`, `ticket.assigned`, `ticket.en_ruta`, `ticket.en_sitio`, `ticket.rescheduled`, `ticket.resolved`.
- Retry: 3 intentos con backoff exponencial (1s, 4s, 16s). Tras 3 fallos: log nivel ERROR + registro en `notification_failures` (tabla o campo en `ticket_events`).
- Métricas: `notifications_delivered`, `notifications_failed`, `notifications_pending` en dashboard admin.

---

### Export (Excel/CSV)

- Programación automática: cron diario (día anterior 00:05), mensual (día 1 del mes, mes anterior), anual (1 enero).
- Manual: admin dispara `POST /api/v1/exports/run`.
- Job: query PostgreSQL → genera XLSX usando librería del servidor → sube a bucket → actualiza `exports.status = 'completed'` → emite SSE `export.completed`.
- Columnas mínimas: ticket_id, cliente, dirección, lat, lon, estado_final, creado_at, asignado_at, salida_at, llegada_at, resuelto_at, cerrado_at, sla_due_at, sla_ok (bool), técnico, reprogramaciones_count, evidencias_urls, notas, categoría, prioridad, zona_técnico.
- Archivos en bucket con TTL configurable (default 30 días). `GET /exports/{id}` genera presigned download URL (TTL 1h) en cada request.
- Si job falla: `exports.status = 'failed'`, `error_message` con causa, notificación al admin.

---

### Attachment Access Control

- `attachments.storage_key` almacena el path en bucket (ej. `tickets/{ticket_id}/photos/uuid.jpg`). **Nunca se expone al cliente**.
- `GET /api/v1/tickets/{id}/attachments` genera presigned download URL (TTL 1h) en cada request. El cliente siempre recibe `download_url` fresca; no hay URLs estáticas públicas.
- `POST /api/v1/tickets/{id}/attachments` retorna `upload_url` (presigned PUT, TTL 15 min) + `attachment_id` (para referenciar en mensajes) + `download_url` (TTL 1h).
- Acceso RBAC: solo participantes del ticket (customer propietario, técnico asignado, admin) pueden obtener attachment URLs. El backend valida antes de generar la presigned URL.
- Borrado de evidencias: solo si `ticket.status != 'cerrado'`; soft delete (`deleted_at`); crea event.

---

### Validaciones y reglas

- Admin requerido para crear/editar técnicos y asignar manualmente.
- Técnico solo modifica tickets asignados a sí mismo.
- Lat/lon obligatorios para habilitar botón de navegación; si faltan → geocoding async.
- Transiciones de estado validadas en backend (no confiar en frontend).
- Cierre requiere checklist completo y ≥1 evidencia.
- Tamaño máximo de adjuntos: 20 MB por archivo, 10 archivos por ticket (configurable por env `MAX_ATTACHMENT_SIZE_MB`, `MAX_ATTACHMENTS_PER_TICKET`).
- Tipos de archivo permitidos: `image/jpeg`, `image/png`, `image/heic`, `application/pdf`, `text/plain`.
- Rate limiting: `/api/v1/auth/login` → 10 req/min por IP. `/api/v1/auth/register` → 5 req/min por IP. Endpoints generales → 100 req/min por usuario autenticado.

---

### Observabilidad

- **Logs**: JSON con campos `timestamp`, `level`, `service`, `version`, `trace_id`, `user_id` (hash anónimo), `message`, `context`. Nunca loguear PII ni secrets.
- **Métricas**: p50/p95/p99 por endpoint; error rate por tipo; tamaño de cola (notificaciones/export/geocoding); duración de export jobs; notificaciones entregadas/fallidas.
- **Trazas**: `trace_id` propagado en todos los logs y en header `X-Trace-Id` de respuestas de error.
- **Audit trail**: `ticket_events` registra TODOS los cambios de estado, asignaciones, evidencias, checklist, mensajes, consultas IA, accesos de Telegram.

---

### Rendimiento y NFR

- p95 < 300 ms en operaciones CRUD de tickets.
- Export job < 10 min para datasets de hasta 10.000 tickets.
- Geocoding async: p95 < 5s para Nominatim, p95 < 1s para Google.
- SSE: soporte de al menos 500 conexiones concurrentes por instancia de backend.
- Disponibilidad objetivo: 99.5%.
- Escalabilidad: workers de notificaciones, export y geocoding escalan horizontalmente.

---

### Pruebas (mínimo)

**Unit** (80% coverage):
- Máquina de estado: todas las transiciones válidas e inválidas.
- Cálculo de SLA (por categoría, prioridad, fallback a defaults).
- Algoritmo de scoring de auto-asignación.
- Generación de presigned URLs (mock del storage client).
- Validación de cierre (checklist + evidencia).

**Integración** (60% coverage):
- Flujo completo: crear ticket → asignar → actualizar estados → subir evidencias → completar checklist → cerrar.
- Export job: genera CSV con columnas mínimas correctas.
- Notificación: evento encola y se marca entregada.
- Auth: registro → verificación email → login → refresh → logout.
- Geocoding: ticket sin lat/lon → job async → ticket actualizado.

**E2E (flujos críticos obligatorios)**:
1. Cliente registra cuenta → verifica email → crea ticket → admin asigna → técnico navega → actualiza en_ruta/en_sitio → sube evidencias → completa checklist → cierra → admin descarga export.
2. Auto-asignación: ticket creado → auto-assign selecciona técnico correcto → técnico notificado vía SSE + Telegram.
3. SLA breach: ticket vence → worker detecta → admin recibe alerta SSE + Telegram.
4. Password reset completo.
