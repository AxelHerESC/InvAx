# Actualizar InvAx en GitHub y Render

## Servicio existente

1. Extraer `InvAx_Frontend_Backend.zip`.
2. En el repositorio `AxelHerESC/InvAx`, abrir **Add file → Upload files**.
3. Arrastrar el CONTENIDO de la carpeta extraída `InvAx`, incluyendo las carpetas `frontend`, `backend`, `database` y `tests`, y los archivos de la raíz. No subir el ZIP ni una carpeta InvAx adicional. Reemplazar los archivos existentes.
4. Confirmar con **Commit changes**. Mensaje sugerido: `Implementar interfaz web y operaciones de InvAx`.
5. Render desplegará el commit si el despliegue automático está activo. En caso contrario, usar **Manual Deploy → Deploy latest commit** en el servicio existente.
6. Esperar **Your service is live** y abrir `https://invax.onrender.com/`. Si aparece la versión anterior, recargar la página.

No hay que crear otro servicio, cambiar las variables actuales ni ejecutar SQL de nuevo. El frontend usa la API del mismo dominio y el Dockerfile existente lo incluye automáticamente.

## Probar por pasos

1. Entrar como `admin` con su contraseña actual de InvAx. La contraseña de PostgreSQL no sirve para iniciar sesión aquí.
2. Comprobar el catálogo y el estado de los tres nodos. Reponer una unidad de un producto y comprobar el aumento.
3. Abrir Actividad y comprobar el registro de reposición.
4. Cerrar sesión y entrar como `vendedor`. Registrar una venta de una unidad y comprobar la disminución.
5. Volver a entrar o recargar para comprobar la persistencia. No compartir contraseñas ni tokens al enviar resultados o capturas.

Si un movimiento pierde la respuesta, usar **Reintentar confirmación**. Conserva el identificador para evitar aplicarlo dos veces.

## Referencia de variables privadas

| Variable | Valor |
| --- | --- |
| DATABASE_URL | URI PostgreSQL del Session pooler sin contraseña, descrito abajo |
| DATABASE_PASSWORD | Contraseña original de la base, sin comillas ni codificación URL |
| INVENTARIO_ADMIN_PASSWORD | Contraseña inicial de admin; al menos 12 caracteres |
| INVENTARIO_VENDEDOR_PASSWORD | Contraseña inicial distinta para vendedor; al menos 12 caracteres |
| INVENTARIO_AUTHKEY | Secreto interno aleatorio de al menos 32 caracteres |
| INVENTARIO_TOKEN_SECRET | Otro secreto aleatorio de al menos 32 caracteres |

El URI de este proyecto es:

```
postgresql://postgres.frefpudusrtazhwfhmpk@aws-1-us-west-2.pooler.supabase.com:5432/postgres
```

Debe aparecer una sola vez, sin espacios, comillas ni el texto `DATABASE_URL=`. La contraseña va solamente en `DATABASE_PASSWORD`. También se admite una contraseña correctamente codificada dentro de DATABASE_URL, pero la configuración separada evita problemas de caracteres especiales.

Las contraseñas iniciales solo crean las cuentas cuando la tabla usuarios está vacía. Cambiar esas variables después no cambia contraseñas ya guardadas. Cambiarlas desde la interfaz de la propia cuenta. Conservar los secretos internos entre despliegues.

Para un servicio nuevo, seleccionar Docker y Free, mantener Docker Command vacío y usar `/api/listo` como health check. El Blueprint genera los dos secretos internos y solicita el resto de variables; si se usa contraseña separada, añadir DATABASE_PASSWORD en Environment antes del despliegue.

## Límites del alojamiento

Render Free puede suspender la aplicación por inactividad. El primer acceso puede tardar mientras arranca. La base está en Supabase y no depende del disco temporal de Render. El plan gratuito de Supabase también puede pausar proyectos inactivos.

Los tres nodos están dentro de una sola instancia Render. Sus puertos no deben exponerse. El navegador utiliza HTTPS y la conexión PostgreSQL exige TLS. Mantener las credenciales fuera de GitHub y conservar la configuración de RLS y Data API existente.
