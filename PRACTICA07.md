# InvAx — Práctica 07: Aplicaciones y Multiservicios

## Arquitectura conservada

Se partió del repositorio existente, no de una reconstrucción. El cliente es HTML/CSS/JavaScript convencional, servido por Flask en el mismo dominio. Las rutas existentes usan `/api/`, no `/api/v1/`. La autenticación utiliza tokens propios con cuerpo JSON y firma HMAC, no JWT estándar. Se conservaron ese formato, los permisos y los contratos existentes.

Flask/Gunicorn comunica el cliente con S1, S2 y S3 mediante BaseManager; los nodos son procesos en una misma instancia Render. PostgreSQL sigue en Supabase. La ampliación PWA no crea microservicios independientes ni añade balanceo por carga. Combina capacidades locales del navegador con los servicios remotos existentes.

## Archivos nuevos y modificados

| Archivo | Responsabilidad |
| --- | --- |
| frontend/manifest.webmanifest | Identidad, inicio, alcance y visualización standalone |
| frontend/icons/icon-192.png, icon-512.png | Iconos de instalación con margen para recorte maskable |
| frontend/sw.js | Instalación completa de shell, caché versionada, exclusión de API y activación controlada |
| frontend/pwa.js | Registro del SW, instrucciones de instalación y aviso de nueva versión |
| frontend/offline-store.js | IndexedDB, validación, SHA-256, límites, eliminación y aislamiento por contexto |
| frontend/app.js | Selección de fuente remota/local, panel, búsqueda, detalles, reconexión y bloqueo de escrituras |
| frontend/index.html y styles.css | Panel y avisos integrados con la identidad visual existente |
| backend/app.py | Rutas públicas del manifiesto y SW, CSP y metadatos de integridad en catálogo autenticado |
| servicio_remoto.py | Fecha de vencimiento de sesión en respuestas autenticadas |
| scripts/preparar_pwa.py | Versión de caché derivada del contenido real de todos los recursos y lógica del SW |
| Dockerfile | Ejecuta el preparado PWA durante la construcción; conserva el arranque de producción |
| .gitignore y .dockerignore | Exclusión de secretos locales, bases temporales, cachés y node_modules |
| tests/test_backend.py | Regresión REST y pruebas de recursos PWA e integridad |
| tests/test_pwa_build.py | Versionado reproducible y detección de recursos faltantes |
| tests/frontend/ | Pruebas de IndexedDB y Service Worker; dependencias solo de desarrollo |

No se modificó el esquema de Supabase, los roles, los secretos ni las dependencias Python de producción.

## Cómo funciona

### Instalación y shell

El manifiesto está en `/manifest.webmanifest`; el SW se sirve en `/sw.js` con alcance `/`. La lista de precarga incluye únicamente HTML y recursos estáticos públicos del proyecto; no hay fuentes externas que descargar. Si falla un recurso durante la instalación, se elimina la caché incompleta y no se activa esa versión. La activación elimina únicamente cachés antiguas con prefijo `invax-shell-`.

El SW no intercepta POST, peticiones con Authorization, rutas `/api/`, otros orígenes ni archivos arbitrarios. No almacena respuestas REST ni credenciales. Se usa caché primero para el shell de la versión activa: así una interfaz y sus scripts corresponden a la misma versión. La API siempre sigue la red.

`python scripts/preparar_pwa.py` deriva el nombre de caché del contenido de recursos y del propio SW. Render lo ejecuta automáticamente al construir Docker. No hace falta Node para producción. Para comprobar que la versión preparada corresponde a los archivos, ejecutar `python scripts/preparar_pwa.py --check`.

### Nueva versión

Un SW nuevo espera hasta que el usuario pulsa Actualizar ahora. Se rechaza la recarga si hay peticiones, un movimiento pendiente, un diálogo abierto o formularios con datos. Solo la pestaña que pidió actualizar se recarga; otras pestañas no reciben una recarga forzada. Al cerrar todas las pestañas, el navegador también puede activar normalmente una versión en espera.

### IndexedDB e integridad

La base `invax-offline` contiene `contexts` y `catalogs`. Cada contexto tiene un UUID, usuario, rol, vencimiento, preferencia de guardado y último uso. El catálogo contiene únicamente id, nombre, precio, cantidad y versión, además del resumen y las fechas. No se inventaron descripción ni categoría: esos campos no existen en el modelo actual.

Se guarda una copia completa por contexto. Los IDs no se duplican. Hay un límite de 10000 productos, 5 MiB de datos serializados por copia y tres contextos recientes como máximo. Se eliminan contextos vencidos y se aplica LRU al iniciar nuevos contextos. Es más útil guardar el catálogo completo que limitarlo a tres productos.

El backend agrega `integridad` a la respuesta exitosa de `/api/productos`: algoritmo SHA-256, esquema 1, total, fecha UTC y hash. Se ordena por ID y se serializan filas `[id, nombre, precio con dos decimales como texto, cantidad, versión]` en JSON compacto UTF-8. El cliente reproduce el documento y usa Web Crypto para comprobarlo antes de guardar. La lectura local vuelve a comprobar el resumen. La sustitución del conjunto en IndexedDB es transaccional.

Esto comprueba consistencia del conjunto y detecta corrupción accidental; el hash no es una firma digital ni protege contra alguien que controla el navegador y puede reemplazar datos y resumen. La confianza en la respuesta remota depende del backend autorizado y HTTPS. IndexedDB no es una caja fuerte cifrada. Si Web Crypto o IndexedDB no están disponibles, no se deben considerar verificadas las capacidades offline; se muestra el error correspondiente.

### Sesión, privacidad y consulta offline

El guardado automático requiere activar una casilla; también existe guardado manual. El token continúa exclusivamente en sessionStorage como antes. Allí se guarda además el contexto de una sesión que previamente validó el servidor; no se crea un inicio de sesión offline.

La consulta offline solo se restaura en esa pestaña mientras siga vigente la sesión original. El vencimiento de 15 minutos no se prolonga por consultar la copia. Una ventana instalada nueva o una pestaña nueva sin contexto debe iniciar sesión con conexión. Conservar los datos en disco no concede permisos del backend, ni se puede detectar inmediatamente una revocación remota sin conectividad.

Cerrar sesión elimina los contextos y catálogos de ese usuario y limpia las vistas. BroadcastChannel informa a otras pestañas del cierre. Las escrituras tardías comprueban que el contexto no haya sido eliminado. Las copias caducadas quedan inaccesibles desde la interfaz y se purgan al iniciar nuevos contextos. No se intenta convertir almacenamiento local en una barrera frente al propietario del dispositivo o sus herramientas de desarrollo.

Eliminar datos locales desactiva además el guardado automático, para evitar que una actualización en segundo plano reponga inmediatamente lo borrado. Mientras esté en línea, el catálogo actual puede seguir visible en memoria; no queda disponible tras una recarga sin copia. Sin conexión, eliminar también vacía la vista local.

### Reconexión

`navigator.onLine` solo sirve como señal inicial. La aplicación confirma conectividad mediante la consulta autenticada del catálogo y comprueba su integridad. Cada petición expira a los 12 segundos. Ante errores de red o 5xx se muestra la última copia válida, con fecha y advertencia. Los reintentos automáticos esperan 15, 30, 60 y hasta 120 segundos, solamente con pestaña visible y sin diálogos abiertos; si un movimiento ya enviado quedó sin confirmar, también permite reintentar la lectura de conectividad con su diálogo abierto, sin reenviar automáticamente ese movimiento; el botón permite reintentar manualmente. En línea se consulta aproximadamente cada 15 segundos.

401 cierra la sesión; 403 se respeta como rechazo y no se transforma en consulta offline por error de red. Las ventas, reposiciones, creación de usuarios y cambios de contraseña requieren conexión verificada y siguen sometidos a autorización en el servidor. No se crea una cola de ventas offline. Se conserva el mecanismo previo de UUID para confirmar el resultado incierto de un movimiento que ya se había enviado en línea.

## Verificación ejecutada

- 38 pruebas Python de API, permisos, autenticación, stock, idempotencia, configuración, diagnóstico, recursos PWA y generación de versión.
- 10 pruebas Node de almacenamiento con fake-indexeddb, integridad, duplicados, respuestas incompletas, copia alterada, consentimiento, aislamiento, logout, LRU y SW.
- Comprobación de sintaxis de los cuatro archivos JavaScript y de versión de caché preparada.
- Revisión con Chrome en entorno temporal: catálogo de cuatro productos; guardado real en IndexedDB; caída simulada de API 503; búsqueda y detalles locales; acciones administrativas y reposición deshabilitadas; recarga durante caída; recuperación; reposición de una unidad; eliminación manual; aviso SW de versión nueva; rechazo de actualización con formulario lleno; actualización aceptada; apertura del shell y catálogo tras detener por completo el servidor de QA; cierre de sesión y recarga sin revelar el catálogo.

La revisión visual usó sesión ficticia y SQLite temporal, con interruptores externos de QA que no se entregan en el proyecto. No se usaron credenciales ni datos de Supabase del usuario. Las pruebas con SQLite no acreditan concurrencia contra PostgreSQL.

Pendiente en el despliegue real: instalación como ventana standalone y prueba en teléfonos/Safari; actualización entre dos despliegues Render; controles de rol desde la aplicación instalada; concurrencia y persistencia contra Supabase. Tampoco se ejecutó una construcción Docker completa en esta revisión; se verificaron las rutas, los recursos y el preparado PWA con Python.

## Pruebas de navegador en Render

Realizar estas pruebas después de desplegar, dentro de los 15 minutos de vigencia de la sesión; no enviar capturas de Authorization ni credenciales.

1. Entrar en InvAx con conexión. En Chrome/Edge revisar Application → Manifest y Service Workers. Confirmar manifiesto cargado, iconos y SW activo con alcance `/`. Instalar desde el navegador si ofrece esa función y comprobar la ventana standalone. En navegadores sin instalación, comprobar la ayuda del botón.
2. Activar Guardar automáticamente en este dispositivo o usar Actualizar y guardar copia. Comprobar número de productos y fecha. En Application → IndexedDB → invax-offline verificar que no hay contraseñas ni tokens.
3. En Network, elegir Offline. Consultar o recargar; esperar la detección de red. Debe aparecer Solo consulta de referencia, conservar catálogo y permitir búsqueda y detalle pulsando el nombre.
4. Comprobar que los botones de venta/reposición y las funciones administrativas no permiten enviar operaciones. No debe existir cola de nuevas modificaciones.
5. Volver a Online y usar Actualizar y guardar copia. Debe recuperar catálogo autorizado y fecha reciente. Si expiró la sesión, volver a iniciar sesión: no es un fallo de caché.
6. Probar administrador y vendedor en sesiones separadas. Las operaciones no permitidas deben seguir devolviendo 403 en el backend, incluso en la aplicación instalada.
7. Para integridad, ejecutar `npm ci --prefix tests/frontend` y `npm test --prefix tests/frontend`: incluyen conjuntos truncados y copia alterada, verificando que no se sobrescribe la última copia válida. No modificar datos de producción para simularlo.
8. Mantener una pestaña abierta, desplegar una modificación de frontend y recargar o volver a la pestaña. Debe aparecer Nueva versión disponible. Con un formulario lleno no debe recargar; después de vaciarlo, aceptar y comprobar la nueva versión.
9. Eliminar datos locales. Comprobar la casilla desactivada, el mensaje sin copia y la ausencia de catálogo después de recargar en Offline.
10. Cerrar sesión, cambiar de cuenta y repetir en Offline. No deben reaparecer los datos locales de la sesión anterior. En una pestaña nueva sin contexto no se ofrece acceso offline al catálogo.

## Despliegue

1. Descomprimir InvAx_Practica07_Final.zip.
2. Subir a la raíz de AxelHerESC/InvAx el CONTENIDO de la carpeta InvAx, incluyendo backend, frontend, scripts, tests y todos los archivos de raíz. Arrastrar las carpetas completas; no aplanar sus archivos ni subir el ZIP. No es necesario vaciar el repositorio.
3. Confirmar que `frontend/offline-store.js`, `frontend/sw.js`, `scripts/preparar_pwa.py` y el Dockerfile actualizado están en sus rutas.
4. Commit y despliegue del último commit en el servicio InvAx de Render. Conservar todas las variables actuales. No crear otra base ni ejecutar SQL.
5. Abrir la URL de siempre. Si hay un SW anterior, aceptar el aviso de actualización cuando no haya formularios o movimientos pendientes.
6. Ejecutar las pruebas anteriores y recoger capturas del despliegue real para el reporte.

No se publicó este paquete automáticamente en GitHub ni Render. El ZIP contiene la implementación preparada para subir.
