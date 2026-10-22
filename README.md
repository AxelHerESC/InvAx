# Inventario web — etapa 1 para servidor

El objetivo es publicar la API en Internet desde esta etapa. La configuración de servidor está en DESPLIEGUE.md y Dockerfile. Los comandos locales de este README son únicamente una alternativa de diagnóstico. No hay un despliegue público realizado todavía.

Python 3.10 o posterior. Ejecuta los comandos desde la carpeta que contiene este README.

## Avance por etapas

1. Backend HTTP, autenticación y consulta del inventario (implementado).
2. Ventas, reposición, usuarios y auditoría mediante HTTP; validar concurrencia, permisos e idempotencia.
3. Frontend con HTML, CSS y JavaScript: acceso, inventario y operaciones por rol. Se servirá inicialmente desde el backend para simplificar la conexión.
4. Integración: sesiones, mensajes de error, botones durante solicitudes y pruebas con dos navegadores.
5. GitHub y despliegue con HTTPS, persistencia y configuración de secretos. Elegir alojamiento después de validar la aplicación local.

## Arquitectura actual

Cliente HTTP → backend Flask → objetos remotos BaseManager → SQLite compartida.

Se reutilizan los nueve archivos de la práctica anterior. configuracion.py ahora permite elegir la carpeta persistente con INVENTARIO_DATA_DIR; los otros ocho archivos originales se conservan sin cambios. La API utiliza el mismo cluster y no crea otra base de datos ni otro sistema de usuarios. Los tres nodos actuales son procesos que comparten un archivo local, no bases replicadas en equipos diferentes. El adaptador de la etapa 1 usa los objetos en localhost. En el arranque de servidor, Gunicorn expone únicamente la API HTTP y mantiene internos los objetos. Las conexiones internas BaseManager no deben publicarse en Internet.

Para un despliegue en un solo servidor se puede mantener un disco local persistente y los procesos internos. Para desplegar nodos en máquinas distintas habrá que adaptar la persistencia a un servicio accesible por red y revisar coordinación y tiempos de espera. El arranque de servidor exige contraseñas iniciales propias y utiliza Gunicorn. En el alojamiento se configurarán el disco persistente y HTTPS.

## Instalación en Windows (CMD)

```bat
python -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements.txt
```

## Terminal 1: cluster

```bat
.venv\Scripts\activate
python iniciar_cluster.py
```

Mantén esta terminal abierta. Los nodos son S1, S2 y S3, en puertos 5100, 5101 y 5102.

## Terminal 2: backend

Abre otra terminal en la misma carpeta:

```bat
.venv\Scripts\activate
python -m flask --app backend.app run --host 127.0.0.1 --port 5000
```

Abre http://127.0.0.1:5000/api/salud. Debe responder JSON con exito=true. Esta ruta solo confirma que Flask está activo; el login y la consulta comprueban la conexión con el cluster.

No hay página de inicio todavía: abrir / devuelve 404, porque la interfaz corresponde a la etapa 3.

## Terminal 3: pruebas manuales en PowerShell

Las credenciales siguientes solo sirven en una base nueva con los valores iniciales originales. Si ya cambiaste las contraseñas, utiliza las actuales.

```powershell
$datos = @{usuario='admin'; clave='Admin2026!'} | ConvertTo-Json
$sesion = Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:5000/api/login' -ContentType 'application/json' -Body $datos
$sesion | Select-Object exito, usuario, rol, servidor
$cabeceras = @{Authorization = "Bearer $($sesion.token)"}
Invoke-RestMethod -Uri 'http://127.0.0.1:5000/api/productos' -Headers $cabeceras | ConvertTo-Json -Depth 5
```

Se esperan los cuatro productos iniciales si no se han cambiado los datos. La respuesta identifica el nodo que atendió la solicitud. No compartas el token en capturas.

## Rutas implementadas

| Método | Ruta | Uso |
| --- | --- | --- |
| GET | /api/salud | Comprobar el backend HTTP |
| POST | /api/login | Autenticar con usuario y clave en JSON |
| GET | /api/productos | Consultar con Authorization: Bearer TOKEN |

Códigos: 200 éxito, 400 JSON o campos inválidos, 401 autenticación rechazada, 404 ruta inexistente, 405 método no permitido, 413 cuerpo demasiado grande, 415 contenido que no es JSON y 503 cluster inaccesible. Las rutas HTTP inválidas también devuelven JSON. El bloqueo de intentos se conserva en cada objeto remoto y devuelve 401 en esta etapa.

El adaptador intenta los nodos en orden y pasa al siguiente ante errores de conexión. No balancea carga ni comprueba todos los nodos al iniciar. El token se envía en cada solicitud; el backend HTTP no almacena las contraseñas del navegador. Las consultas no permiten caché.

## Pruebas automatizadas

```bat
python -m unittest discover -s tests -v
```

Crean un objeto remoto real en un proceso aparte y una base temporal. No requieren arrancar el cluster y no modifican el inventario de uso. Cubren login, lectura, rechazo de credenciales y tokens, validación de JSON, errores HTTP, indisponibilidad y respaldo ante un nodo caído.

## Archivos agregados

- backend/app.py: rutas HTTP y respuestas JSON.
- backend/conexion.py: comunicación con los objetos remotos.
- backend/__init__.py: paquete Python.
- tests/: pruebas de integración.
- requirements.txt: dependencia de Flask.
- .gitignore: exclusión de bases, claves, secretos y entorno virtual.

No se incluye una base de datos ni secretos en el ZIP. Para conservar datos existentes, copia los archivos nuevos a una copia de tu proyecto y conserva sus archivos locales de datos y seguridad juntos; no los subas a GitHub.
