# InvAx

Sistema de inventario con backend Flask, objetos remotos Python y persistencia PostgreSQL en Supabase. El despliegue previsto es un Web Service de Render Free. No se necesita disco persistente en Render.

## Estado del proyecto

- Implementado: login y consulta de productos mediante HTTP, adaptación de persistencia a PostgreSQL y configuración de despliegue.
- Pendiente de validar en el alojamiento: conexión con el proyecto de Supabase y arranque completo con PostgreSQL.
- Próximas etapas: exponer ventas, reposición, usuarios y auditoría en la API; después frontend y pruebas desde varios navegadores.
- Todavía no se ha publicado una URL ni implementado el frontend. La ruta / devuelve 404 hasta incorporar la interfaz.

## Arquitectura

Navegador → API Flask/Gunicorn en Render → S1, S2 y S3 en localhost → PostgreSQL de Supabase.

S1, S2 y S3 son procesos internos de una misma instancia. Se conserva la invocación de objetos mediante BaseManager. Sus puertos 5100, 5101 y 5102 no se publican. La comunicación desde el navegador utiliza HTTPS proporcionado por Render y la conexión a PostgreSQL exige TLS.

La base almacena productos, usuarios, operaciones y auditoría. Las existencias se modifican con bloqueos de fila y transacciones. El identificador de operación se bloquea en PostgreSQL y se comprueba junto con su usuario y contenido para impedir descuentos repetidos. El registro de la operación se confirma en la misma transacción que el cambio de stock; la auditoría del servicio se registra por separado, como en la implementación original.

## Supabase

El script database/01_tablas.sql corresponde al que se ejecutó en el SQL Editor del proyecto. Si ya se ejecutó, no hace falta repetirlo. Mantener la Data API desactivada; los clientes del navegador usarán únicamente la API de InvAx. El backend se conecta con el usuario PostgreSQL indicado en DATABASE_URL, que debe tener los permisos necesarios para estas tablas. La configuración inicial utiliza la conexión del usuario postgres del proyecto; esa credencial solo se guarda en el alojamiento.

Los usuarios iniciales se crean al primer arranque si la tabla usuarios está vacía. Se guardan salt y hash PBKDF2, nunca la contraseña en texto. No son cuentas de Supabase Auth: InvAx conserva su propio sistema de autenticación y roles.

## Despliegue

Consultar DESPLIEGUE.md. El archivo render.yaml prepara un único servicio Free sin disco. Las credenciales se proporcionan en el panel, no en el repositorio. Los secretos internos permanecen en variables de entorno, de modo que no se pierden por el almacenamiento temporal de Render.

## Rutas actuales

| Método | Ruta | Uso |
| --- | --- | --- |
| GET | /api/salud | API HTTP activa; identifica InvAx |
| GET | /api/listo | Comprueba un objeto remoto y una lectura en la base |
| POST | /api/login | JSON con usuario y clave |
| GET | /api/productos | Authorization: Bearer TOKEN |

La ruta /api/listo devuelve 503 si no puede completarse la lectura. Una comprobación exitosa no garantiza que todos los nodos estén activos. El adaptador elige el primer nodo accesible y prueba el siguiente si hay un error; no implementa balanceo por carga.

## Verificación realizada antes de entregar

Pasaron diez pruebas HTTP con un objeto remoto real y SQLite temporal: autenticación, consulta, validación, tokens, errores HTTP, disponibilidad y respaldo ante un nodo caído. Verifican la capa HTTP y la compatibilidad con la lógica anterior. Además se comprobaron cuatro casos de configuración: secretos sin archivos, rechazo de secretos parciales o cortos y rechazo del arranque de producción sin DATABASE_URL. Se validó la sintaxis del script y las sentencias del adaptador con el parser de PostgreSQL. Estas comprobaciones no acreditan integración con PostgreSQL ni concurrencia contra Supabase. La conexión real, el arranque de los usuarios y los bloqueos deben validarse con el despliegue; las pruebas concurrentes se harán antes de publicar ventas en la interfaz.

Comando de regresión opcional: python -m unittest discover -s tests -v.

Sin DATABASE_URL, servidor.py e iniciar_cluster.py mantienen la alternativa SQLite para diagnóstico y compatibilidad. El arranque de producción backend.iniciar_servidor exige DATABASE_URL y los secretos; no permite un despliegue con SQLite por accidente.

## Archivos principales

- inventario_postgres.py: persistencia y transacciones PostgreSQL.
- persistencia.py: selección del almacén según DATABASE_URL.
- servicio_remoto.py: operaciones, roles y comprobación de disponibilidad.
- backend/app.py: rutas HTTP.
- backend/conexion.py: comunicación con los objetos remotos.
- backend/iniciar_servidor.py: arranque y cierre de los tres nodos y Gunicorn.
- configuracion.py: claves desde variables del alojamiento.
- Dockerfile y render.yaml: construcción y configuración de Render.

Python 3.10 o posterior. La imagen de despliegue utiliza Python 3.12. Los archivos SQLite y los clientes de consola anteriores se conservan para compatibilidad, pero no constituyen la persistencia del despliegue de InvAx.
