# InvAx

Inventario escolar con frontend HTML/CSS/JavaScript, API Flask y objetos remotos Python. Se despliega en un Web Service de Render Free y guarda sus datos en PostgreSQL de Supabase. La interfaz se sirve desde `/` en el mismo dominio que la API; no requiere compilar Node ni alojar el frontend por separado.

## Funciones

- Inicio de sesión y restauración de sesión en la pestaña.
- Catálogo con búsqueda, filtros de existencias y métricas de inventario.
- Vendedor: consultar y registrar ventas.
- Administrador: consultar, reponer existencias, crear cuentas y consultar auditoría.
- Ambos roles pueden cambiar su propia contraseña.
- Comprobación de disponibilidad de S1, S2 y S3.
- Validación de cantidades y permisos en el backend. Los movimientos llevan UUID para reintentar sin duplicar el cambio de existencias.

No se incluyen contraseñas de acceso en el frontend. Las cuentas iniciales son `admin` y `vendedor`, con las contraseñas configuradas al primer arranque del servicio.

## Arquitectura y persistencia

Navegador → HTTPS de Render → Flask/Gunicorn → S1/S2/S3 mediante BaseManager → PostgreSQL de Supabase.

Los tres nodos son procesos internos de la misma instancia, con puertos de localhost. El adaptador prueba el primer nodo accesible y continúa con el siguiente ante errores; no realiza balanceo por carga. El estado de un nodo comprueba su respuesta; `/api/listo` además hace una lectura de la base mediante un nodo disponible.

PostgreSQL almacena productos, usuarios, operaciones y auditoría. El cambio de stock y la respuesta de una operación se confirman en una misma transacción, con bloqueo de fila y del identificador de operación. El servicio registra la auditoría por separado. Las contraseñas se almacenan como hashes PBKDF2; los tokens están firmados con HMAC. Se comprueban rol y cuenta activa al autorizar cada operación.

El navegador conserva el token en sessionStorage, sin almacenar contraseñas. Si un movimiento pierde su respuesta, conserva el mismo UUID y permite reintentar su confirmación. No se permite modificar ese movimiento mientras su resultado es incierto.

## Rutas

Todas las rutas salvo `/`, assets, salud, listo y login requieren `Authorization: Bearer TOKEN`.

| Método | Ruta | Uso |
| --- | --- | --- |
| GET | / | Interfaz web |
| GET | /api/salud | Salud HTTP |
| GET | /api/listo | Nodo y lectura de persistencia |
| POST | /api/login | usuario, clave |
| GET | /api/sesion | Usuario y rol |
| GET | /api/productos | Catálogo |
| GET | /api/productos/P001 | Producto |
| POST | /api/ventas | id_producto, cantidad, request_id UUID |
| POST | /api/reposiciones | id_producto, cantidad, request_id UUID |
| POST | /api/usuarios | usuario, clave, rol |
| PUT | /api/clave | clave_actual, clave_nueva |
| GET | /api/auditoria?limite=50 | Últimos registros; límite 1 a 100 |
| GET | /api/servidores | Disponibilidad de nodos |

La cantidad debe ser un entero entre 1 y 10000. Una operación rechazada por existencias devuelve 409; sesión inválida 401; permisos insuficientes 403; almacén o clúster inaccesible 503.

## Despliegue y comprobaciones

Consultar `DESPLIEGUE.md`. Se conserva el esquema de `database/01_tablas.sql`; esta actualización no requiere repetirlo. Las credenciales solo se configuran en Render. No se necesita Supabase Auth, anon key ni service_role key: únicamente el backend se conecta a PostgreSQL con psycopg. Mantener la Data API desactivada y las tablas con RLS como están configuradas.

Verificación automatizada: 33 pruebas de HTTP, autenticación, roles, reintentos, existencias, concurrencia con SQLite temporal, configuración y diagnóstico PostgreSQL. Utilizan un objeto remoto real para las pruebas HTTP. No acreditan concurrencia ni integración contra el PostgreSQL del usuario. La sintaxis de JavaScript se revisó con `node --check frontend/app.js`. La revisión visual automatizada no pudo completarse por un fallo del navegador de vista previa; comprobar la interfaz en Render tras actualizar.

Comando de regresión: `python -m unittest discover -s tests -v`.

El arranque de producción es `python -m backend.iniciar_servidor`, incluido en Dockerfile. Exige PostgreSQL y secretos por variables de entorno. Los clientes anteriores y la alternativa SQLite se conservan para diagnóstico y compatibilidad, no para la persistencia del despliegue.
