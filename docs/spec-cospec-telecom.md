## Especificación Técnica — Cospec Telecomunicaciones
**Dominio**: Gestión de reclamos y operaciones de campo.

### Arquitectura
- Backend REST (JSON) con colas para notificaciones/export y un servicio ligero de IA (provider gratuito tipo Minimax) para Q&A contextual. Futuro: GraphQL si se requiere agregación rica.
- Frontend web (admin/técnico/cliente) con vista lista + mapa y deep links a Google Maps.
- Storage de archivos/evidencias en objeto (S3/GCS equivalente) con URLs presignadas.
- DB relacional (PostgreSQL) con índices por estado, SLA, asignación, cliente, zona, fechas.
- Workers: notificaciones y export (cron diario/mensual/anual).

### Roles y permisos
- Admin: único que crea/edita técnicos; CRUD tickets; asigna/reasigna; configura SLA/checklists; exporta reportes.
- Técnico: opera solo tickets asignados; cambia estado (según flujo); agrega/edita evidencias antes de cierre; chatea.
- Cliente: crea/consulta sus tickets; propone/acepta agenda; chatea; ve evidencias (solo lectura).

### Modelo de datos (mínimo)
- users(id, role[admin|tech|customer], name, email, phone, zone, skills jsonb, active, created_at)
- tickets(id, title, description, category, priority, status, sla_due_at, customer_id, assigned_to, address, lat, lon, window_start, window_end, created_at, updated_at, closed_at)
- ticket_events(id, ticket_id, actor_id, type, payload jsonb, created_at) — audit/timeline
- appointments(id, ticket_id, window_start, window_end, status[pending|confirmed|rescheduled|cancelled], updated_by, updated_at)
- messages(id, ticket_id, sender_id, body, created_at)
- attachments(id, ticket_id, uploader_id, url, type[photo|doc|note], created_at)
- checklists(id, ticket_id, item, status[pending|done], updated_by, updated_at)
- exports(id, period_date, kind[daily|monthly|annual], file_url, generated_at, status)
Índices sugeridos: tickets(status,sla_due_at), tickets(assigned_to,status), tickets(customer_id,created_at), tickets(zone,status), messages(ticket_id,created_at), attachments(ticket_id,created_at).

### Flujos
- Alta de técnico (solo admin): crea user role=tech; requiere zona/skills; activa/desactiva.
- Crear ticket: valida dirección; si falta lat/lon, geocode; crea ticket + event; notifica.
- Asignar ticket: manual/automática (zona, skills, carga, proximidad); event + notificación a técnico.
- Navegar: botón genera deep link `https://www.google.com/maps/dir/?api=1&destination=<lat>,<lon>`; registra timestamps de salida/llegada.
- Estados: abierto→asignado→en ruta→en sitio→en trabajo→resuelto→cerrado. Validar transiciones por rol y estado previo.
- Evidencias: adjuntar fotos/notas; checklist por tipo; editable mientras status ≠ cerrado; cada edición genera event.
- Reprogramar: actualiza ventana; requiere confirmación; impacta SLA si aplica; notifica a técnico/cliente.
- Cierre: requiere checklist completo + ≥1 evidencia; set closed_at; event; recalcula SLA.
- Export: jobs programados (cron) generan CSV/XLSX y guardan file_url; descarga desde panel admin.

### Endpoints (borrador REST)
- Auth (placeholder, depende de stack): login/refresh.
- Técnicos: `POST /users/tech` (admin), `GET /users/tech`, `PATCH /users/tech/{id}` (activar/desactivar/zonas/skills).
- Tickets: `POST /tickets`, `GET /tickets` (filtros por estado, prioridad, zona, asignado, fecha), `GET /tickets/{id}`.
- Asignación: `POST /tickets/{id}/assign` (admin); `POST /tickets/{id}/auto-assign` (admin/opcional worker).
- Estados: `POST /tickets/{id}/status` (payload: next_status, timestamps opcionales para en_ruta/en_sitio).
- Agenda: `POST /tickets/{id}/appointments` (crear/actualizar), `GET /tickets/{id}/appointments`.
- Mensajes: `GET /tickets/{id}/messages`, `POST /tickets/{id}/messages`.
- IA asistente: `POST /tickets/{id}/ai-query` (role user/admin/tech; prompt breve; responde solo con contexto del ticket).
- Evidencias: `POST /tickets/{id}/attachments` (presign flow), `GET /tickets/{id}/attachments`.
- Checklists: `GET /tickets/{id}/checklist`, `POST /tickets/{id}/checklist` (update statuses).
- Export: `POST /exports/run` (admin, period kind/date), `GET /exports` (listar), `GET /exports/{id}` (descarga).

### Validaciones y reglas
- Rol admin requerido para crear técnicos y asignar manualmente.
- Rol técnico solo modifica tickets asignados a sí mismo.
- Lat/lon obligatorios para habilitar navegación; si no, forzar geocoding previo.
- Transiciones de estado solo permitidas en orden definido; cierre requiere checklist completo y evidencia.
- Tamaño y tipo de adjuntos validados; URLs presignadas con expiración.
- Rate limiting en endpoints públicos (auth/crear ticket).

### Notificaciones
- Evento → cola → worker envía email/SMS/push según configuración; espejo opcional a Telegram (bot) para técnicos/admin.
- Plantillas por estado: creado, asignado, en ruta, en sitio, reprogramado, resuelto.

### Export (Excel/CSV)
- Programación: cron diario (día anterior), mensual (mes anterior), anual (año anterior).
- Columnas mínimas: ticket_id, cliente, dirección, lat, lon, estado_final, creado, asignado, salida, llegada, resuelto, cerrado, SLA_OK(bool), técnico, reprogramaciones, evidencias_urls, notas, categoría, prioridad, zona.
- Archivos almacenados en bucket con expiración configurable; accesibles vía URL autenticada.

### Observabilidad
- Logs JSON con trace_id y user_id hash. No loguear datos sensibles.
- Métricas: p50/p95/p99 por endpoint; tasa de error; colas (pendiente/procesado); duración de export job; notificaciones entregadas/fallidas; ratio de respuestas IA exitosas/timeout.
- Audit trail en ticket_events para cambios de estado, asignación, evidencias, checklist, consultas IA.

### Rendimiento y NFR
- p95 < 300 ms en operaciones de tickets/consulta; export job < 10 min.
- Disponibilidad objetivo 99.5%.
- Escalabilidad horizontal de workers para notificaciones/export.

### Pruebas (mínimo)
- Unit: transiciones de estado, reglas de checklist, asignación automática (zona/skill/carga).
- Integración: creación → asignación → evidencias → cierre; export job produce CSV con columnas mínimas; notificación encola y se marca entregada.
- E2E feliz: cliente crea ticket, admin asigna, técnico navega, actualiza en ruta/en sitio, sube fotos/notas, completa checklist, cierra; export disponible.
