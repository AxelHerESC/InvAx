# Registro de verificación P08

Fecha de entrega: 13 de noviembre de 2026.

- Python 3.12, PostgreSQL 17.11 temporal con TLS, cinco procesos WSGI HTTP independientes.
- Pytest: **66 passed, 37 subtests passed in 17.45s**.
- Frontend/PWA: **10 tests, 10 pass, 0 fail**.
- Todos los JS pasaron `node --check`.
- Caché validada: `invax-shell-4de92672df46174d`.
- `git diff --check` sin errores; Dockerfile raíz y render.yaml sin cambios respecto al repositorio base.
- Navegador: CRUD de P020 sin historial, reposición P002 25→26, historial, guardado de copia y recarga tras detener servidor con cuatro productos y escrituras deshabilitadas.

`online.jpg` y `offline.jpg` muestran datos ficticios en un entorno desechable. No son capturas de Supabase ni Render. Las rutas auxiliares del servidor de QA y sus sesiones ficticias no se entregan en la aplicación.

No ejecutados aquí: Docker build, Docker Compose, workflow en GitHub, migración del Supabase escolar y despliegue P08 en Render. Véase EVIDENCIAS_P08.md para repetir y completar las verificaciones.
