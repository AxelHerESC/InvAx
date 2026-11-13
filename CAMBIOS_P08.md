# Cambios respecto al repositorio P07

## Elementos conservados

Frontend, estilos base, formulario de sesión, roles, movimiento con UUID, usuarios, cambio de contraseña, auditoría, PostgreSQL, tablas, PBKDF2, formato de tokens HMAC y rutas `/api/`. Se conservan manifest, iconos, Service Worker, IndexedDB, instalación y modo consulta sin conexión.

El Dockerfile raíz, `render.yaml`, `backend/iniciar_servidor.py`, objetos BaseManager, persistencia y documentación P07 siguen disponibles para el despliegue anterior. La nueva arquitectura usa un arranque y Dockerfile diferentes.

## Archivos nuevos

| Archivo o carpeta | Cambio |
| --- | --- |
| `backend/microservices/common.py` | RPC autenticado, cliente HTTP acotado, errores, autorización delegada, logs y trazas |
| `backend/microservices/gateway.py` | Destinos fijos, diagnóstico paralelo y CORS explícito |
| `backend/microservices/services.py` | Aplicaciones independientes auth/productos/ventas/reposiciones con lista de métodos |
| `backend/microservices/stores.py` | Roles SQL separados, CRUD, stock y ledger/auditoría atómicos, historial |
| `backend/microservices/app.py`, `run.py`, `__init__.py` | Fábrica por servicio y arranque de un solo proceso Gunicorn |
| `database/02_microservices.sql` | Migración aditiva de roles, permisos y políticas RLS |
| `scripts/configurar_roles_p08.py` | Preparación administrativa explícita con contraseñas ocultas |
| `scripts/evidencias_p08.py` | Consultas manuales y prueba de rechazo de reposición como vendedor |
| `deploy/microservices/Dockerfile` | Imagen común; una aplicación por contenedor mediante INVAX_SERVICE |
| `compose.microservices.yaml` | Cinco procesos, redes, healthchecks y solo Gateway publicado |
| `render-p08-free.yaml` | Cinco servicios nuevos Free y secreto compartido de clúster |
| `.env.microservices.example`, `.gitignore`, `.dockerignore` | Plantilla sin secretos y exclusiones de archivos privados/temporales |
| `requirements-microservices.txt`, `requirements-dev.txt` | Transporte requests y dependencias de pruebas |
| `.github/workflows/practica08.yml` | PostgreSQL TLS de prueba, tests, PWA y construcción Docker en CI |
| `tests/microservices/` | Integración real de cinco procesos con PostgreSQL, concurrencia y fallos |
| `tests/test_microservice_transport.py`, `tests/test_microservice_config.py` | Timeouts, JSON, CORS, trazas y límites de configuración |
| `frontend/product-admin.js` | Diálogos CRUD e historial con controles por rol y conexión |
| `PRACTICA08.md`, `GUIA_DESPLIEGUE_P08.md`, `EVIDENCIAS_P08.md`, este archivo | Arquitectura, ejecución, cambios y evidencias |
| `docs/qa-p08/` | Capturas de QA con datos ficticios y resultados de verificación |

## Archivos adaptados

| Archivo | Razón |
| --- | --- |
| `backend/app.py` | Inyección del adaptador HTTP; códigos remotos; health; CRUD e historiales públicos protegidos; detección P08 |
| `frontend/app.js` | Detección de capacidades, botones por rol, integración de CRUD, timeout 30 s y conservación de PWA |
| `frontend/index.html` | Controles y diálogos accesibles del catálogo/historial; carga del módulo nuevo |
| `frontend/styles.css` | Estilos de acciones y diálogos añadidos |
| `frontend/sw.js` | Nuevo recurso del shell y versión derivada de su contenido |
| `tests/test_backend.py` | POST productos ahora es una ruta protegida: sin sesión devuelve 401 en vez de ruta inexistente 405 |
| `README.md`, `DESPLIEGUE.md` | Referencias claras a la nueva versión y distinción con la arquitectura anterior |

## Límites que deben constar en el reporte

No se convirtió la autenticación a JWT. No se crearon cinco bases de datos; se implementaron propietarios y roles restringidos sobre la instancia existente. Ventas/reposiciones coordinan por HTTP y los movimientos se confirman en el servicio propietario de stock. La auditoría de movimientos P08 se confirma en su misma transacción, mejorando el registro separado legacy.

No se sustituyó el servicio que ya funciona. No se aplicó la migración al Supabase real, ni se publicaron servicios o ejecutó CI remota. La construcción Docker y Compose quedan por ejecutar donde Docker esté disponible. Estos pendientes son de instalación/verificación de infraestructura; no son resultados aprobados de esta entrega.
