## PRD — Plataforma de Reclamos y Campo
**Empresa**: Cospec Telecomunicaciones
**Objetivo**: Plataforma end-to-end para gestionar reclamos y órdenes de trabajo entre administrador, técnicos de campo y clientes, con navegación a domicilio, evidencias editables y exportación periódica a Excel.

### Roles
- Admin: crea/gestiona técnicos (único rol que puede darlos de alta), asigna tickets, configura SLA/checklists, revisa métricas y exporta reportes.
- Técnico: recibe tickets asignados, navega al domicilio, actualiza estado, captura evidencias (fotos/notas/checklist), puede editar antes del cierre.
- Cliente: crea/consulta reclamos propios, propone/acepta agenda, chatea, recibe notificaciones, visualiza evidencias (solo lectura).

### Alcance (v1)
- Reclamos/OT con datos: categoría, prioridad, SLA, dirección + lat/lon, contacto, ventana horaria.
- Asignación manual/automática (zona, skills, carga, proximidad geográfica).
- Flujo de estados: abierto → asignado → en ruta → en sitio → en trabajo → resuelto → cerrado.
- Navegación: deep-link a Google Maps/Waze con `lat,lon` para "ir a la dirección".
- Evidencias: fotos, notas, checklist configurable por tipo; editables hasta cierre; historial de cambios.
- Agenda/reprogramación: creación/edición de ventanas; confirmación cliente; impacto en SLA.
- Chat vinculado al ticket (cliente↔técnico↔admin) con historial; soporte de notificación tipo app móvil.
- Chat interno vía Telegram (bot) para notificar eventos de tickets y permitir respuesta básica ligada al ticket.
- Asistente IA (provider gratuito tipo Minimax) para consultas simples: estado del ticket, próximos pasos, checklist pendiente; opera solo con contexto del ticket.
- Dashboard técnico: tickets asignados, en ruta, en sitio, pendientes; vista lista y mapa.
- Dashboard admin: backlog, SLA breaches, productividad por técnico, mapa.
- Exportaciones automáticas a Excel (CSV/XLSX) diarias, mensuales, anuales; descarga desde panel admin.
- Notificaciones (email/SMS/push configurable) en eventos clave: creado, asignado, en ruta, en sitio, reprogramado, resuelto; espejo a Telegram para técnicos/admin si está conectado.

### Fuera de alcance (v1)
- Facturación/pagos, inventario de repuestos, integraciones OSS/BSS externas (solo webhook genérico), app móvil nativa (PWA/web primero), modo offline completo (se considera v2).

### Requisitos funcionales
- Alta de técnicos: solo admin; campos mínimos (nombre, contacto, zona, skills); activar/desactivar.
- Creación de ticket: cliente/admin; valida dirección y obtiene lat/lon (geocoding) si falta; registra evento.
- Asignación: manual o automática; genera evento y notifica a técnico; respeta skills/zona/disponibilidad.
- Navegación: botón "Ir" abre deep link Google Maps; guarda timestamp de “salida” y “llegada” al sitio.
- Transiciones de estado: validadas por rol; técnico no puede cerrar sin checklist y evidencia mínima.
- Evidencias: múltiples fotos/notas; checklist por tipo de reclamo; editable hasta cierre; audit trail de ediciones.
- Chat: permisos por rol; adjuntos permitidos; historial persistente.
- Reprogramación: cliente o técnico (si permitido); actualiza ventana; recalcula SLA si aplica; notifica.
- Cierre: requiere checklist completo + evidencia; marca `closed_at`; actualiza métricas SLA.
- Exportaciones: jobs programados (día/mes/año) generan CSV/XLSX con URL de descarga; columnas mínimas: ticket id, cliente, dirección, lat/lon, estado final, tiempos clave (creado/asignado/salida/llegada/cierre), SLA (OK/KO), técnico asignado, reprogramaciones, evidencias (links), notas, categoría/prioridad.

### Requisitos no funcionales
- Disponibilidad 99.5% objetivo; p95 API < 300 ms en operaciones de tickets.
- Seguridad: RBAC estricto; rate limiting en endpoints públicos; sin datos sensibles en logs; audit trail por ticket.
- Escalabilidad: colas para notificaciones/export; índices por estado/SLA/assign/cliente/zona.
- Observabilidad: logs JSON con trace_id; métricas de latencia, error rate, throughput de export/notificaciones.

### KPIs
- % tickets dentro de SLA (por categoría/prioridad/zona).
- Tiempo medio: asignación, en ruta, llegada, resolución, cierre.
- Productividad por técnico (tickets cerrados/día, re-trabajos, reprogramaciones).
- Ratio de reprogramaciones y motivos.

### Riesgos y mitigaciones
- Falta de lat/lon: forzar validación de dirección o geocoding asistido.
- Conectividad del técnico: permitir captura offline ligera (cola local) como v2.
- Privacidad de evidencias: URLs presignadas con expiración; control de acceso por ticket.

### Supuestos abiertos
- Canales de notificación finales (email/SMS/push) y proveedor serán definidos por infraestructura.
- Soporte multi-idioma opcional (v1 español; inglés como mejora futura).
