# Desplegar InvAx P08 sin sustituir el servicio anterior

Este documento prepara una instalación nueva. El código ya está implementado; todavía no está publicado en Render. Para avanzar paso a paso, completar primero el apartado 1 y verificarlo antes de crear servicios.

## 1. Subir la versión con una referencia identificable

Descomprimir el ZIP: la carpeta `InvAx/` es la raíz del repositorio, no una subcarpeta que deba quedar dentro de otra carpeta InvAx. Conservar todos los archivos, incluidos `.github/`, `.gitignore`, `.dockerignore` y `.env.microservices.example`. No subir `.env` privados ni borrar el historial del repositorio.

Preferible crear rama `practica08`, subirla y comprobar los tests de Actions. El manifiesto Render incluido indica `branch: main`; si se despliega la rama de revisión, cambiar ese campo a `practica08` o seleccionarla manualmente. Guardar la referencia del commit P07. Revisar auto-deploy del servicio anterior antes de actualizar su rama para evitar una publicación accidental. No cambiar su Dockerfile ni su comando al nuevo arranque antes de preparar el entorno P08.

## 2. Preparar permisos en PostgreSQL de Supabase

Respaldar los datos y revisar que estén las cuatro tablas de `database/01_tablas.sql`. La base existente ya tiene el esquema: no hace falta volver a sembrarla. Aplicar **solo** `database/02_microservices.sql` usando una conexión administrativa privada. El archivo crea los roles `invax_auth` e `invax_productos` y concede los permisos necesarios; no contiene contraseñas ni elimina tablas. Las políticas RLS se aplican a esos roles específicos, no a `anon` ni `authenticated`.

Asignar contraseñas largas distintas a ambos roles por un canal administrativo privado. Se incluye un asistente que pide las tres contraseñas sin mostrarlas y utiliza SQL correctamente citado:

```bash
python -m pip install -r requirements-microservices.txt
python scripts/configurar_roles_p08.py
```

Antes se configura `ADMIN_DATABASE_URL` en el entorno privado de la terminal con la URL administrativa **sin contraseña**. El asistente aplica la migración y pide las contraseñas de cada rol, mínimo 16 caracteres. Si una confirmación falla, volver a ejecutarlo para completar ambos roles. Nunca pegar contraseñas, `ALTER ROLE ... PASSWORD ...` con valores reales ni URLs completas con contraseña en el repositorio, capturas o chat. En Render Free no hay shell: realizar esta preparación desde una terminal propia o el administrador de Supabase.

Para el Session pooler compartido usar el host/puerto reales de **Connect** de tu proyecto, manteniendo el nombre de base mostrado por Supabase. Los usuarios de los dos roles se forman como `invax_auth.REFERENCIA` e `invax_productos.REFERENCIA`. La referencia debe ser exactamente la del proyecto, sin duplicar la URL. Ejemplo estructural sin credenciales:

```text
postgresql://invax_auth.REFERENCIA@HOST-POOLER:5432/postgres
postgresql://invax_productos.REFERENCIA@HOST-POOLER:5432/postgres
```

Configurar la contraseña aparte en `DATABASE_PASSWORD` evita errores de codificación del URI. No reutilizar el usuario administrativo `postgres` para estos servicios: el código lo rechaza. La creación y permisos fueron probados con PostgreSQL aislado; el acceso de estos roles a través del pooler de tu Supabase debe verificarse al desplegar. Si aparece error de credenciales o de permisos, detenerse en este punto y revisar rol, referencia, contraseña y políticas, sin ampliar permisos globalmente.

## 3. Variables por proceso

| Servicio | INVAX_SERVICE | URLs de dependencias | Variables privadas adicionales |
| --- | --- | --- | --- |
| auth | auth | Ninguna | DATABASE_URL de invax_auth, DATABASE_PASSWORD, INVENTARIO_TOKEN_SECRET |
| productos | productos | AUTH_URL | DATABASE_URL de invax_productos, DATABASE_PASSWORD |
| ventas | ventas | AUTH_URL, PRODUCTOS_URL | Ninguna de base de datos/firma |
| reposiciones | reposiciones | AUTH_URL, PRODUCTOS_URL | Ninguna de base de datos/firma |
| gateway | gateway | AUTH_URL, PRODUCTOS_URL, VENTAS_URL, REPOSICIONES_URL | INVAX_ALLOWED_ORIGINS opcional |

Los cinco necesitan **el mismo** `INVAX_CLUSTER_TOKEN`, nuevo y aleatorio de al menos 32 caracteres. Generarlo una vez y guardarlo como secreto; no generar cinco valores distintos. No es el token de sesión, la contraseña de base ni el authkey legacy. Mantener `INVENTARIO_TOKEN_SECRET` igual al de P07 en auth si se desea compatibilidad de tokens existentes. No copiarlo a los otros servicios.

Las contraseñas `INVENTARIO_ADMIN_PASSWORD` y `INVENTARIO_VENDEDOR_PASSWORD` son necesarias para inicializar una base nueva sin admin, distintas y de al menos 12 caracteres; no cambian las cuentas que ya existen. En la base escolar actual se usan sus usuarios existentes. `PORT` lo proporciona Render; el arranque lo respeta. Nunca exponer variables privadas en JavaScript.

## 4. Render gratuito: crear cinco Web Services nuevos

Crear servicios distintos del actual, en la misma región, desde la rama que contiene P08. Elegir runtime Docker y plan Free, con estos valores comunes:

- Dockerfile Path: `./deploy/microservices/Dockerfile`
- Docker Context: `.`
- Health Check Path: `/api/health`
- Dejar el Docker Command por defecto: ejecutará `python -m backend.microservices.run` con Gunicorn.

Orden recomendado para configurar URLs reales sin adivinarlas:

1. Crear `invax-p08-auth` con sus variables. Verificar arranque y `GET /api/health` 200.
2. Crear `invax-p08-productos`; `AUTH_URL` es la URL HTTPS real del servicio anterior, copiada del panel, sin `/api/health`. Comprobar arranque y acceso de su rol a PostgreSQL.
3. Crear `invax-p08-ventas` e `invax-p08-reposiciones` con las URLs HTTPS reales de auth y productos.
4. Crear `invax-p08-gateway` con las cuatro URLs HTTPS reales. Este es el enlace que abrirá el usuario y desde el que se instalará la PWA.
5. Probar login, catálogo, roles, venta, reposición e historial en el Gateway. `/api/salud` debe decir `microservicios: true`. `/api/servidores` con sesión válida debe mostrar los cuatro servicios.

El nombre solicitado puede recibir un sufijo de Render: **copiar la URL efectiva del panel**, no asumirla por el nombre. No poner las URLs privadas de Render en este modo Free. Los servicios internos de esta modalidad están accesibles por HTTPS público, pero `/internal/rpc` exige el secreto de clúster y las operaciones también autentican al usuario. El navegador no recibe el secreto y solo usa el Gateway; `/api/health` revela únicamente vida y nombre del servicio.

Alternativa: `render-p08-free.yaml` es un Blueprint de cinco servicios nuevos y un grupo que genera una sola credencial interna compartida. Elegir explícitamente ese archivo, no el `render.yaml` legacy. Las URLs y credenciales marcadas `sync: false` deben rellenarse privadamente y ajustarse a las URLs reales después de crear los servicios. Para el primer despliegue, la creación manual ordenada facilita detectar fallos de configuración.

Según la [documentación oficial Free](https://render.com/docs/free) y de [red privada](https://render.com/docs/private-network), consultadas el 13-11-2026, las instancias Free no reciben tráfico privado y comparten 750 horas mensuales por workspace. Los cinco servicios y el legacy consumen ese mismo cupo cuando están activos. Los arranques en frío pueden exceder los timeouts y causar 503; despertar cada servicio desde su health público, esperar y volver a probar el Gateway. No hay garantía de disponibilidad continua ni cinco cupos separados. El manifiesto no contrata servicios de pago.

Si se requiere aislamiento de red real en Render, hace falta infraestructura con servicios privados y revisar su costo: allí solo se publicaría el Gateway y se usarían las direcciones privadas en las variables. No se ha contratado ni configurado esa opción.

## 5. Compose para reproducir y obtener evidencias

Es opcional para el despliegue escolar en línea; no requiere sustituir Supabase por SQLite. Después de preparar los roles, copiar `.env.microservices.example` a `.env.microservices` y rellenar valores **en privado**. Los nombres `AUTH_DATABASE_URL/PASSWORD` y `PRODUCTOS_DATABASE_URL/PASSWORD` del archivo se transforman en las variables de cada contenedor.

```bash
docker compose --env-file .env.microservices -f compose.microservices.yaml config --quiet
docker compose --env-file .env.microservices -f compose.microservices.yaml up -d --build
docker compose --env-file .env.microservices -f compose.microservices.yaml ps
docker compose --env-file .env.microservices -f compose.microservices.yaml logs --tail=100 gateway ventas productos
```

Abrir `http://127.0.0.1:8080`. El resto de puertos no se publica; la red `core` es interna. Solo auth/productos tienen salida adicional para la base remota. Para reconstruir, repetir `up -d --build`. Para detener, `docker compose --env-file .env.microservices -f compose.microservices.yaml down`; no borra la base Supabase. No mostrar `config` sin `--quiet`, `docker inspect` ni el contenido del env en capturas: pueden revelar secretos.

## 6. Cierre y reversión

Mantener el servicio P07 hasta verificar P08 y capturar evidencias. El frontend del Gateway nuevo usa su propio origen/almacenamiento; una PWA instalada del enlace viejo seguirá abriendo ese enlace. Para comprobar P08, abrir el dominio nuevo e instalar desde allí si corresponde.

Si falla la nueva instalación, conservar P07 sin cambiarlo y corregir las variables del servicio afectado. Los roles y políticas añadidos no reemplazan la cuenta de conexión legacy. Ambos entornos comparten datos si apuntan a la misma base, por lo que conviene no usarlos simultáneamente para capturas o pruebas de stock; los tests automatizados van a una base aislada. No limpiar datos reales ni quitar roles mientras existan servicios que los utilicen.
