# Primera etapa en un servidor

Esta entrega prepara la API para ejecutarse en un servidor Linux con Docker o Python. No incluye aún el frontend ni acredita una publicación: faltan la cuenta de alojamiento y el repositorio de destino.

## Componentes

Internet → terminación HTTPS del alojamiento → API Gunicorn → S1/S2/S3 en localhost → disco persistente.

Los tres objetos corren dentro de la misma instancia. Sus puertos 5100–5102 no se publican. Solo el puerto indicado en PORT recibe tráfico HTTP. Una única instancia mantiene el bloqueo de login de cada objeto y la base compartida; no se debe activar escalamiento horizontal con esta persistencia.

## Configuración del alojamiento

- Construcción: Dockerfile en la raíz del proyecto.
- Inicio: ya definido en Dockerfile.
- PORT: el puerto asignado por el proveedor; el valor por defecto es 8080.
- INVENTARIO_DATA_DIR: /app/data.
- Disco persistente: montado en /app/data y con permiso de escritura para el usuario inventario. Verificar el UID y permisos del montaje según el proveedor.
- INVENTARIO_ADMIN_PASSWORD e INVENTARIO_VENDEDOR_PASSWORD: contraseñas distintas, propias y de al menos 12 caracteres, configuradas como secretos del alojamiento.
- HTTPS: proporcionado por el alojamiento o por un proxy con certificado en un VPS.
- Ruta de comprobación: /api/salud. Solo indica que la API responde; validar también login y productos.

Las contraseñas solo crean los usuarios si la base no contiene ninguno. Modificar variables no cambia contraseñas de usuarios ya existentes. La base, el secreto de tokens y la clave de conexión se conservan juntos en el disco persistente. No se incluyen en GitHub.

El comando de inicio es `python -m backend.iniciar_servidor`. Inicia los tres objetos, espera su disponibilidad y después arranca Gunicorn. Si un proceso termina, detiene el conjunto y sale con error para que el alojamiento lo reinicie. No imprime contraseñas.

## Comprobación una vez desplegado

Abrir https://TU-DOMINIO/api/salud. Después probar POST /api/login con las credenciales configuradas y GET /api/productos con el token recibido. Reiniciar la instancia y verificar que la sesión sigue siendo reconocida y los datos permanecen.

La interfaz se incorporará a esta misma aplicación en una etapa posterior. Entonces la dirección raíz mostrará la página del inventario. Por ahora, la entrega pública consiste en la API.

## Estado de verificación

La comprobación del paquete se realiza en un proceso Linux con Gunicorn y los tres nodos. La imagen Docker y los permisos del disco del proveedor deben comprobarse al elegir el alojamiento. No hay una URL pública todavía.
