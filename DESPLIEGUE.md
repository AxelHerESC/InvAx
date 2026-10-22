# InvAx en Render Free y Supabase Free

## 1. Actualizar GitHub

Extraer InvAx_Supabase_Etapa2.zip y subir el contenido de la carpeta InvAx a la raíz de AxelHerESC/InvAx, reemplazando los archivos con el mismo nombre. Dockerfile y render.yaml deben quedar en la raíz. No subir el ZIP como archivo ni crear una carpeta InvAx adicional dentro del repositorio.

Mensaje sugerido: Adaptar InvAx a PostgreSQL de Supabase.

## 2. Obtener la conexión de Supabase

En el proyecto InvAx, pulsar Connect y elegir Session pooler. Usar el URI del panel con el host pooler y el puerto 5432. Esta alternativa permite conectarse desde redes IPv4. Conservar la cadena en privado y colocar la contraseña real en lugar de [YOUR-PASSWORD]. Si la contraseña contiene caracteres reservados de una URL, debe codificarse al formar el URI; nunca codificar el URI completo ni compartir la contraseña aquí.

No se necesitan SUPABASE_URL, anon key ni service_role key para este backend, porque se conecta a PostgreSQL con psycopg.

## 3. Crear el servicio mediante Blueprint

Crear una cuenta de Render y conectar el repositorio privado InvAx. En New → Blueprint seleccionar el repositorio y la rama que contiene render.yaml. El Blueprint declara un único Web Service con plan free. Revisar que no se propongan servicios de pago.

Render pedirá estas variables privadas:

| Variable | Contenido |
| --- | --- |
| DATABASE_URL | URI de Session pooler, con la contraseña de PostgreSQL |
| INVENTARIO_ADMIN_PASSWORD | Contraseña propia de al menos 12 caracteres para admin |
| INVENTARIO_VENDEDOR_PASSWORD | Otra contraseña propia de al menos 12 caracteres para vendedor |

El Blueprint genera automáticamente INVENTARIO_AUTHKEY e INVENTARIO_TOKEN_SECRET. No cambiarlas en cada despliegue: el secreto de tokens mantiene la validez de las sesiones hasta su vencimiento. Son distintas de las contraseñas de los usuarios.

Si se elige Web Service manualmente en lugar de Blueprint, se deben generar y configurar también esas dos variables, con valores aleatorios distintos de al menos 32 caracteres cada uno. Seleccionar Docker y Free; usar /api/listo como health check. No cambiar Docker Command, porque el Dockerfile ya incluye el comando de inicio.

Las contraseñas admin/vendedor solo se usan para la primera creación. Modificar las variables posteriormente no reemplaza contraseñas almacenadas en la base. No usar las contraseñas de demostración de la práctica anterior.

## 4. Comprobar el despliegue

1. Revisar los logs de construcción y arranque sin copiar credenciales.
2. Abrir https://TU-SERVICIO.onrender.com/api/salud.
3. Abrir https://TU-SERVICIO.onrender.com/api/listo: debe responder exito=true y el identificador de un servidor.
4. Probar el login y la consulta protegida en la etapa siguiente.
5. Comprobar en Supabase que se crearon admin y vendedor con hashes.
6. Reiniciar el servicio y verificar que los productos y usuarios permanecen.

El proyecto todavía no incluye una página web en /. Esa respuesta 404 no indica un fallo en la API.

## Seguridad y límites

- La API queda accesible mediante HTTPS en Render. La conexión PostgreSQL usa sslmode=require para cifrar el tráfico.
- Ninguna contraseña ni URI con credenciales se escribe en GitHub.
- RLS está activado en las tablas y no se dieron permisos a anon ni authenticated. La conexión administrativa del backend tiene permisos elevados y debe permanecer privada.
- Los tres objetos BaseManager solo escuchan en localhost; no se debe publicar sus puertos.
- El bloqueo de intentos de login es por objeto y se reinicia junto con los procesos. No es un bloqueo global persistente.
- Render Free puede suspender la aplicación por inactividad. Supabase conserva la base independientemente del disco temporal de Render; su plan Free también puede pausar proyectos inactivos.
- La integración real de PostgreSQL sigue pendiente hasta completar los pasos anteriores. Las pruebas de concurrencia contra PostgreSQL precederán a las ventas por HTTP.
