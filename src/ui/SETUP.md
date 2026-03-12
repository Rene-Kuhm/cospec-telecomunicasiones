# Setup — Frontend Angular (Cospec UI)

## Requisitos

- Node.js >= 20 LTS
- Angular CLI >= 17: `npm install -g @angular/cli@17`

---

## Inicialización del proyecto (una sola vez)

```bash
# Desde src/ui/
ng new cospec-ui \
  --standalone \
  --routing \
  --style=scss \
  --skip-git \
  --directory=.

# Angular Material (UI components)
ng add @angular/material
# Elegir: tema "Indigo/Pink" o "Custom" → sí a typography → sí a animations

# PWA support (para técnicos en campo desde móvil)
ng add @angular/pwa

# NgRx (state management) — para tickets, auth, notificaciones
ng add @ngrx/store@latest
ng add @ngrx/effects@latest
ng add @ngrx/entity@latest
ng add @ngrx/router-store@latest

# Leaflet (mapas — más liviano que Google Maps, usa OSM)
npm install leaflet @types/leaflet

# Utilidades
npm install date-fns            # manejo de fechas
npm install lodash-es @types/lodash-es
```

---

## Estructura de módulos (lazy-loaded)

```
src/
├── app/
│   ├── app.config.ts          ← configuración standalone (providers, routing)
│   ├── app.routes.ts          ← routing principal con lazy loading
│   │
│   ├── core/                  ← servicios singleton (HTTP, Auth, SSE, Storage)
│   │   ├── auth/
│   │   │   ├── auth.service.ts
│   │   │   ├── auth.guard.ts
│   │   │   ├── role.guard.ts
│   │   │   └── auth.interceptor.ts    ← añade Bearer token a requests
│   │   ├── api/
│   │   │   ├── api.service.ts         ← wrapper de HttpClient con envelope unwrap
│   │   │   ├── tickets.service.ts
│   │   │   ├── attachments.service.ts
│   │   │   └── exports.service.ts
│   │   ├── sse/
│   │   │   └── events.service.ts      ← SSE connection + EventSource management
│   │   └── notification/
│   │       └── notification.service.ts
│   │
│   ├── shared/                ← componentes y pipes reutilizables
│   │   ├── components/
│   │   │   ├── ticket-status-badge/
│   │   │   ├── priority-badge/
│   │   │   ├── map-preview/           ← Leaflet widget con lat/lon
│   │   │   └── file-upload/           ← presign + upload directo a R2
│   │   ├── pipes/
│   │   │   ├── sla-status.pipe.ts
│   │   │   └── relative-time.pipe.ts
│   │   └── models/
│   │       ├── ticket.model.ts
│   │       ├── user.model.ts
│   │       └── api-response.model.ts  ← envelope type { success, data, error, meta }
│   │
│   ├── features/
│   │   ├── auth/              ← login, register, verify-email, reset-password
│   │   │   └── auth.routes.ts
│   │   │
│   │   ├── admin/             ← LAZY — solo rol admin
│   │   │   ├── admin.routes.ts
│   │   │   ├── dashboard/
│   │   │   ├── tickets/       ← backlog, assign, SLA view
│   │   │   ├── technicians/   ← CRUD técnicos
│   │   │   ├── exports/       ← trigger + download
│   │   │   └── config/        ← categorías, SLA rules
│   │   │
│   │   ├── tech/              ← LAZY — solo rol tech
│   │   │   ├── tech.routes.ts
│   │   │   ├── dashboard/     ← mis tickets, ruta del día
│   │   │   ├── ticket-detail/ ← estado, evidencias, checklist, chat
│   │   │   └── navigation/    ← botón "Ir" con deep link + mapa
│   │   │
│   │   └── customer/          ← LAZY — solo rol customer
│   │       ├── customer.routes.ts
│   │       ├── my-tickets/
│   │       ├── create-ticket/
│   │       └── ticket-detail/ ← chat, evidencias (readonly), appointments
│   │
│   └── store/                 ← NgRx state
│       ├── auth/
│       ├── tickets/
│       └── notifications/
│
├── environments/
│   ├── environment.ts          ← development
│   └── environment.prod.ts     ← production
│
└── ngsw-config.json           ← PWA cache strategy
```

---

## Variables de entorno Angular

Editar `src/environments/environment.ts`:
```typescript
export const environment = {
  production: false,
  apiUrl: 'http://localhost:8000/api/v1',
  sseUrl: 'http://localhost:8000/api/v1/events',
};
```

Editar `src/environments/environment.prod.ts`:
```typescript
export const environment = {
  production: true,
  apiUrl: 'https://api.cospec-telecom.com/api/v1',
  sseUrl: 'https://api.cospec-telecom.com/api/v1/events',
};
```

---

## SSE Service (EventSource para notificaciones en tiempo real)

El servicio debe:
1. Crear `EventSource` con `?token=<access_token>` (EventSource no permite headers custom).
2. Escuchar eventos tipados: `ticket.assigned`, `ticket.status_changed`, etc.
3. Dispatch a NgRx store al recibir eventos relevantes.
4. Reconexión automática en `onerror` con backoff (EventSource reconecta solo, pero controlar el token expirado).
5. Cerrar conexión en logout.

Patrón de uso en `events.service.ts`:
```typescript
// RxJS fromEvent wrapper sobre EventSource
connect(token: string): Observable<SSEEvent> {
  const url = `${environment.sseUrl}?token=${token}`;
  const eventSource = new EventSource(url);
  return new Observable(observer => {
    eventSource.onmessage = e => observer.next(JSON.parse(e.data));
    eventSource.onerror = e => observer.error(e);
    return () => eventSource.close();
  });
}
```

---

## API Response Interceptor

Todos los endpoints retornan `{ success, data, error, meta }`. Crear interceptor que:
1. Si `success: true` → retorna `response.data` directamente.
2. Si `success: false` → lanza error tipado con `response.error.code` y `response.error.message`.
3. Si HTTP 401 con `AUTH_TOKEN_EXPIRED` → intenta refresh automático y reintenta request.

---

## Comandos útiles

```bash
# Correr en dev
ng serve --proxy-config proxy.conf.json

# Build producción
ng build --configuration production

# Generar componente standalone
ng g c features/admin/tickets/ticket-list --standalone --style=scss

# Generar servicio
ng g s core/api/tickets

# Generar NgRx feature
ng g @ngrx/schematics:feature store/tickets --module app

# Tests
ng test
ng test --code-coverage

# Lint
ng lint
```

---

## proxy.conf.json (dev — proxy al backend local)

Crear en raíz del proyecto Angular:
```json
{
  "/api": {
    "target": "http://localhost:8000",
    "secure": false,
    "changeOrigin": true
  },
  "/api/v1/events": {
    "target": "http://localhost:8000",
    "secure": false,
    "ws": false
  }
}
```

En `angular.json`, bajo `serve.options`:
```json
"proxyConfig": "proxy.conf.json"
```

---

## PWA — Estrategia de caché

Para técnicos en campo con conectividad intermitente, configurar en `ngsw-config.json`:
- **Shell app** (routing, assets): `prefetch` strategy.
- **API tickets**: `freshness` (red primero, caché como fallback).
- **Imágenes de evidencias**: no cachear (presigned URLs expiran).
