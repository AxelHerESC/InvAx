'use strict';
const $ = id => document.getElementById(id);
const storage = {get(k){try{return sessionStorage.getItem(k);}catch{return null;}},set(k,v){try{sessionStorage.setItem(k,v);}catch{}},remove(k){try{sessionStorage.removeItem(k);}catch{}}};
const state = {token:storage.get('invax.token'), usuario:null, rol:null, productos:[], vista:'inventario', movimiento:null, busy:{}};
const moneda = new Intl.NumberFormat('es-MX',{style:'currency',currency:'MXN',maximumFractionDigits:2});
const numero = new Intl.NumberFormat('es-MX');
const roles = {administrador:'Administrador', vendedor:'Vendedor'};
class ApiError extends Error {constructor(message,status){super(message);this.status=status;}}
function aviso(id,texto,tipo='error'){const el=$(id);el.textContent=texto;el.className='aviso '+tipo;el.hidden=!texto;}
function elemento(tag,texto,clase){const el=document.createElement(tag);if(texto!==undefined)el.textContent=texto;if(clase)el.className=clase;return el;}
function cerrarSesion(mensaje=''){
 state.token=null;state.usuario=null;state.rol=null;state.productos=[];state.movimiento=null;storage.remove('invax.token');
 for(const d of document.querySelectorAll('dialog[open]'))d.close();
 $('usuario-form').reset();$('clave-form').reset();$('aplicacion').hidden=true;$('acceso').hidden=false;$('login-form').reset();$('login-submit').disabled=true;
 aviso('login-error',mensaje);document.title='InvAx · Iniciar sesión';$('login-usuario').focus();
}
async function api(ruta,{method='GET',body,auth=true}={}){
 const controller=new AbortController();const timeout=setTimeout(()=>controller.abort(),30000);
 const headers={Accept:'application/json'};if(body)headers['Content-Type']='application/json';if(auth&&state.token)headers.Authorization='Bearer '+state.token;
 try{
  const res=await fetch(ruta,{method,headers,body:body?JSON.stringify(body):undefined,signal:controller.signal,cache:'no-store',credentials:'omit'});
  let data;try{data=await res.json();}catch{throw new ApiError('El servicio no devolvió una respuesta válida. Intenta nuevamente.',res.status||503);}
  if(!res.ok||!data.exito){if(res.status===401&&auth)cerrarSesion('Tu sesión terminó. Inicia sesión para continuar.');throw new ApiError(data.mensaje||'No se pudo completar la solicitud.',res.status);}
  if(data.servidor)$('nodo-actual').textContent='Atendido por '+data.servidor;
  return data;
 }catch(error){if(error instanceof ApiError)throw error;throw new ApiError(error.name==='AbortError'?'La respuesta tardó demasiado. Intenta nuevamente.':'No se pudo conectar con el servicio. Revisa tu conexión e intenta nuevamente.',0);}finally{clearTimeout(timeout);}
}
function ocupado(id,busy){$(id).setAttribute('aria-busy',String(busy));for(const c of $(id).querySelectorAll('input,select,button'))c.disabled=busy;}
function validarLogin(){const valid=$('login-usuario').value.trim().length>0&&$('login-clave').value.length>0;$('login-submit').disabled=state.busy.login||!valid;}
$('login-form').addEventListener('input',()=>{validarLogin();aviso('login-error','');});
$('login-usuario').addEventListener('blur',()=>{const invalid=!$('login-usuario').value.trim();$('login-usuario').setAttribute('aria-invalid',String(invalid));$('error-usuario').textContent=invalid?'Escribe tu usuario.':'';});
$('mostrar-clave').addEventListener('click',()=>{const mostrar=$('login-clave').type==='password';$('login-clave').type=mostrar?'text':'password';$('mostrar-clave').textContent=mostrar?'Ocultar':'Mostrar';$('mostrar-clave').setAttribute('aria-pressed',String(mostrar));});
$('login-form').addEventListener('submit',async e=>{
 e.preventDefault();if(state.busy.login||$('login-submit').disabled)return;state.busy.login=true;ocupado('login-form',true);$('login-submit').textContent='Entrando…';aviso('login-error','');
 try{const data=await api('/api/login',{method:'POST',auth:false,body:{usuario:$('login-usuario').value.trim(),clave:$('login-clave').value}});state.token=data.token;storage.set('invax.token',data.token);$('login-clave').value='';await abrirAplicacion(data);}catch(err){aviso('login-error',err.message);}finally{state.busy.login=false;ocupado('login-form',false);$('login-submit').textContent='Entrar a InvAx →';validarLogin();}
});
async function abrirAplicacion(sesion){
 state.usuario=sesion.usuario;state.rol=sesion.rol;state.vista='inventario';
 $('cuenta-usuario').textContent=state.usuario;$('cuenta-rol').textContent=roles[state.rol]||state.rol;$('avatar').textContent=state.usuario.slice(0,1).toUpperCase();
 document.querySelectorAll('[data-admin]').forEach(el=>el.hidden=state.rol!=='administrador');
 $('acceso').hidden=true;$('aplicacion').hidden=false;document.title='InvAx · Inventario';aviso('aviso-global','');
 await verVista('inventario');
 const pendiente=storage.get('invax.pendiente.'+state.usuario);
 if(pendiente){try{const op=JSON.parse(pendiente);if(op.request_id&&op.producto&&Number.isInteger(op.cantidad))abrirMovimiento(op.producto,op);}catch{}}
}
function renderProductos(){
 const busqueda=$('buscar-producto').value.trim().toLocaleLowerCase('es');const filtro=$('filtro-stock').value;
 const visibles=state.productos.filter(p=>(p.id+' '+p.nombre).toLocaleLowerCase('es').includes(busqueda)&&(filtro==='todos'||(filtro==='bajo'&&p.cantidad<=5)||(filtro==='agotado'&&p.cantidad===0)));
 const body=$('productos-body');body.replaceChildren();
 for(const p of visibles){
  const tr=elemento('tr');const td=elemento('td');const producto=elemento('div',undefined,'producto-celda');const icono=elemento('span','▧','producto-mini');icono.setAttribute('aria-hidden','true');const info=elemento('div');info.append(elemento('b',p.nombre),elemento('small',p.id+' · Versión '+p.version));producto.append(icono,info);td.append(producto);tr.append(td,elemento('td',moneda.format(p.precio)));
  const stock=elemento('td');const cantidad=elemento('span',numero.format(p.cantidad),'stock-numero');cantidad.append(elemento('span','unidades'));stock.append(cantidad);tr.append(stock);
  const estado=elemento('td');const badge=elemento('span',undefined,'badge '+(p.cantidad===0?'agotado':p.cantidad<=5?'bajo':''));const punto=elemento('span',undefined,'punto');punto.setAttribute('aria-hidden','true');badge.append(punto,document.createTextNode(p.cantidad===0?'Agotado':p.cantidad<=5?'Stock bajo':'Disponible'));estado.append(badge);tr.append(estado);
  const accion=elemento('td',undefined,'derecha');const boton=elemento('button',state.rol==='administrador'?'+ Reponer':'Registrar venta','accion-producto');boton.type='button';boton.disabled=state.rol==='vendedor'&&p.cantidad===0;boton.setAttribute('aria-label',(state.rol==='administrador'?'Reponer stock de ':'Vender ')+p.nombre);boton.addEventListener('click',()=>abrirMovimiento(p));accion.append(boton);tr.append(accion);body.append(tr);
 }
 $('productos-vacio').hidden=visibles.length!==0;$('conteo-productos').textContent=visibles.length+' de '+state.productos.length+' productos';
 $('total-productos').textContent=numero.format(state.productos.length);$('total-unidades').textContent=numero.format(state.productos.reduce((t,p)=>t+p.cantidad,0));$('total-bajos').textContent=numero.format(state.productos.filter(p=>p.cantidad<=5).length);$('total-valor').textContent=moneda.format(state.productos.reduce((t,p)=>t+p.precio*p.cantidad,0));
}
async function cargarInventario(){
 const token=state.token;const data=await api('/api/productos');if(state.token!==token)return;
 state.productos=data.productos;renderProductos();$('ultima-actualizacion').textContent='Actualizado '+new Date().toLocaleTimeString('es-MX',{hour:'2-digit',minute:'2-digit'});
 try{const nodos=await api('/api/servidores');if(state.token!==token)return;renderServidores(nodos.servidores);}catch(err){if(state.token){renderServidores(null);aviso('aviso-global','El catálogo está actualizado; el estado de servidores no pudo consultarse.','advertencia');}}
}
function renderServidores(nodos){
 const contenedor=$('servidores');contenedor.replaceChildren();
 for(const n of nodos||['S1','S2','S3'].map(servidor=>({servidor,disponible:null}))){const card=elemento('article',undefined,'servidor '+(n.disponible===null?'sin-verificar':n.disponible?'':'caido'));const icono=elemento('span','▤','icono-servidor');icono.setAttribute('aria-hidden','true');const info=elemento('div');info.append(elemento('b','Servidor '+n.servidor),elemento('small',n.disponible===null?'Sin verificar':n.disponible?'Disponible':'Sin respuesta'));const punto=elemento('span',undefined,'punto');punto.setAttribute('aria-hidden','true');card.append(icono,info,punto);contenedor.append(card);}
}
async function cargarAuditoria(){
 const token=state.token;const data=await api('/api/auditoria?limite=50');if(token!==state.token)return;const body=$('auditoria-body');body.replaceChildren();
 const acciones={login:'Inicio de sesión',vender:'Venta',agregar_stock:'Reposición',crear_usuario:'Crear usuario',cambiar_clave:'Cambio de contraseña'};
 for(const r of data.registros){const tr=elemento('tr');let fecha=new Date(r.creado_en);if(Number.isNaN(fecha.getTime()))fecha=new Date(r.creado_en.replace(' ','T')+'Z');tr.append(elemento('td',Number.isNaN(fecha.getTime())?r.creado_en:fecha.toLocaleString('es-MX')),elemento('td',r.usuario),elemento('td',acciones[r.accion]||r.accion),elemento('td',r.servidor));const td=elemento('td');td.append(elemento('span',r.exito?'Correcto':'Rechazado','badge '+(r.exito?'':'fallo')));tr.append(td,elemento('td',r.detalle));body.append(tr);}$('auditoria-vacia').hidden=data.registros.length!==0;
}
async function verVista(vista){
 if(vista!=='inventario'&&state.rol!=='administrador')return;
 state.vista=vista;for(const v of ['inventario','actividad','usuarios'])$('vista-'+v).hidden=v!==vista;
 for(const b of document.querySelectorAll('[data-vista]')){const activa=b.dataset.vista===vista;b.classList.toggle('nav-activa',activa);if(activa)b.setAttribute('aria-current','page');else b.removeAttribute('aria-current');}
 const datos={inventario:['VISIÓN GENERAL','Tu inventario, al día.','Consulta tus productos y registra sus movimientos.','Inventario'],actividad:['TRAZABILIDAD','Cada movimiento cuenta.','Consulta las acciones realizadas por tu equipo.','Actividad'],usuarios:['ADMINISTRACIÓN','Suma a tu equipo.','Crea cuentas y asigna los permisos necesarios.','Crear usuario']}[vista];
 $('pagina-etiqueta').textContent=datos[0];$('pagina-titulo').textContent=datos[1];$('pagina-descripcion').textContent=datos[2];$('miga').textContent='Tu espacio / '+datos[3];document.title='InvAx · '+datos[3];$('actualizar').hidden=vista==='usuarios';aviso('aviso-global','');
 await actualizar();
}
async function actualizar(){
 if(state.busy.actualizar||!state.token)return;state.busy.actualizar=true;$('actualizar').disabled=true;$('actualizar').textContent='Actualizando…';
 try{if(state.vista==='inventario')await cargarInventario();else if(state.vista==='actividad')await cargarAuditoria();}catch(err){if(state.token)aviso('aviso-global',err.message);}finally{state.busy.actualizar=false;$('actualizar').disabled=false;$('actualizar').textContent='↻ Actualizar';}
}
for(const b of document.querySelectorAll('[data-vista]'))b.addEventListener('click',()=>verVista(b.dataset.vista));
$('actualizar').addEventListener('click',()=>{aviso('aviso-global','');actualizar();});$('buscar-producto').addEventListener('input',renderProductos);$('filtro-stock').addEventListener('change',renderProductos);$('salir').addEventListener('click',()=>cerrarSesion());
function clavePendiente(){return 'invax.pendiente.'+state.usuario;}
function guardarPendiente(){storage.set(clavePendiente(),JSON.stringify(state.movimiento));}
function limpiarPendiente(){if(state.usuario)storage.remove(clavePendiente());if(state.movimiento)state.movimiento.pendiente=false;}
function abrirMovimiento(producto,anterior=null){
 state.movimiento=anterior?{...anterior,pendiente:true}:{tipo:state.rol==='administrador'?'reposiciones':'ventas',producto,cantidad:1,request_id:crypto.randomUUID(),pendiente:false};
 const op=state.movimiento;const venta=op.tipo==='ventas';$('movimiento-titulo').textContent=venta?'Registrar venta':'Reponer existencias';$('movimiento-producto').textContent=producto.nombre+' · '+producto.id;$('movimiento-cantidad').value=op.cantidad;$('movimiento-cantidad').max=venta?Math.min(producto.cantidad,10000):10000;$('movimiento-disponible').textContent='Existencias consultadas: '+producto.cantidad+' unidades.';$('movimiento-cantidad').disabled=op.pendiente;
 $('movimiento-cerrar').disabled=op.pendiente;$('movimiento-cancelar').disabled=op.pendiente;
 aviso('movimiento-error',op.pendiente?'Hay un movimiento sin confirmar. Reintenta para recuperar su resultado sin duplicarlo.':'');validarMovimiento();if(!$('movimiento-dialog').open)$('movimiento-dialog').showModal();
}
function validarMovimiento(limpiarMensaje=true){
 const op=state.movimiento;if(!op)return;const n=Number($('movimiento-cantidad').value);const max=op.tipo==='ventas'?Math.min(op.producto.cantidad,10000):10000;const valido=Number.isInteger(n)&&n>=1&&n<=max;
 $('movimiento-submit').disabled=state.busy.movimiento||(!op.pendiente&&!valido);$('movimiento-submit').textContent=op.pendiente?'Reintentar confirmación':op.tipo==='ventas'?'Confirmar venta':'Agregar existencias';
 if(!op.pendiente){$('movimiento-cantidad').setAttribute('aria-invalid',String(!valido));if(!valido)aviso('movimiento-error','Escribe una cantidad entera entre 1 y '+max+'.');else if(limpiarMensaje)aviso('movimiento-error','');}
}
$('movimiento-cantidad').addEventListener('input',()=>validarMovimiento());
function cerrarMovimiento(){if(state.busy.movimiento||state.movimiento?.pendiente)return;$('movimiento-dialog').close();state.movimiento=null;}
$('movimiento-cerrar').addEventListener('click',cerrarMovimiento);$('movimiento-cancelar').addEventListener('click',cerrarMovimiento);$('movimiento-dialog').addEventListener('cancel',e=>{if(state.busy.movimiento||state.movimiento?.pendiente)e.preventDefault();else state.movimiento=null;});
$('movimiento-form').addEventListener('submit',async e=>{
 e.preventDefault();if(state.busy.movimiento||$('movimiento-submit').disabled||!state.movimiento)return;
 const op=state.movimiento;if(!op.pendiente)op.cantidad=Number($('movimiento-cantidad').value);op.pendiente=true;guardarPendiente();state.busy.movimiento=true;ocupado('movimiento-form',true);$('movimiento-cerrar').disabled=true;$('movimiento-submit').textContent='Guardando…';aviso('movimiento-error','');
 try{const data=await api('/api/'+op.tipo,{method:'POST',body:{id_producto:op.producto.id,cantidad:op.cantidad,request_id:op.request_id}});limpiarPendiente();$('movimiento-dialog').close();state.movimiento=null;aviso('aviso-global',data.mensaje+' Existencias: '+data.stock_anterior+' → '+data.stock_actual+'.','exito');await actualizar();}
 catch(err){const incierto=!err.status||err.status>=500||err.status===401;if(!incierto){limpiarPendiente();op.request_id=crypto.randomUUID();}if(state.token)aviso('movimiento-error',incierto?'No pudimos confirmar el resultado. Reintenta sin cambiar los datos para evitar duplicar el movimiento.':err.message);}
 finally{state.busy.movimiento=false;ocupado('movimiento-form',false);if(state.movimiento){$('movimiento-cantidad').disabled=state.movimiento.pendiente;$('movimiento-cancelar').disabled=state.movimiento.pendiente;$('movimiento-cerrar').disabled=state.movimiento.pendiente;validarMovimiento(false);}}
});
function validarUsuario(){const valido=/^[A-Za-z0-9_.-]{3,32}$/.test($('nuevo-usuario').value)&&$('nueva-clave').value.length>=8;$('usuario-submit').disabled=state.busy.usuario||!valido;}
$('usuario-form').addEventListener('input',()=>{validarUsuario();aviso('usuario-error','');});
$('nuevo-usuario').addEventListener('blur',()=>{$('nuevo-usuario').setAttribute('aria-invalid',String(!/^[A-Za-z0-9_.-]{3,32}$/.test($('nuevo-usuario').value)));});
$('usuario-form').addEventListener('submit',async e=>{e.preventDefault();if(state.busy.usuario||$('usuario-submit').disabled)return;state.busy.usuario=true;ocupado('usuario-form',true);$('usuario-submit').textContent='Creando…';aviso('usuario-error','');try{const data=await api('/api/usuarios',{method:'POST',body:{usuario:$('nuevo-usuario').value,clave:$('nueva-clave').value,rol:$('nuevo-rol').value}});$('usuario-form').reset();aviso('aviso-global',data.mensaje,'exito');}catch(err){aviso('usuario-error',err.message);}finally{state.busy.usuario=false;ocupado('usuario-form',false);$('usuario-submit').textContent='Crear cuenta';validarUsuario();}});
$('cambiar-clave').addEventListener('click',()=>{$('clave-form').reset();aviso('clave-error','');$('clave-coincidencia').textContent='';validarClave();$('clave-dialog').showModal();});
$('clave-cerrar').addEventListener('click',()=>{if(!state.busy.clave)$('clave-dialog').close();});$('clave-dialog').addEventListener('cancel',e=>{if(state.busy.clave)e.preventDefault();});
function validarClave(){const actual=$('clave-actual').value,nueva=$('clave-nueva').value,confirmacion=$('clave-confirmacion').value;const coinciden=nueva===confirmacion;$('clave-submit').disabled=state.busy.clave||!actual||nueva.length<8||!coinciden;$('clave-coincidencia').textContent=confirmacion&&!coinciden?'Las contraseñas no coinciden.':'';$('clave-confirmacion').setAttribute('aria-invalid',String(Boolean(confirmacion&&!coinciden)));}
$('clave-form').addEventListener('input',()=>{validarClave();aviso('clave-error','');});
$('clave-form').addEventListener('submit',async e=>{e.preventDefault();if(state.busy.clave||$('clave-submit').disabled)return;state.busy.clave=true;ocupado('clave-form',true);$('clave-cerrar').disabled=true;$('clave-submit').textContent='Guardando…';try{const data=await api('/api/clave',{method:'PUT',body:{clave_actual:$('clave-actual').value,clave_nueva:$('clave-nueva').value}});$('clave-form').reset();$('clave-dialog').close();aviso('aviso-global',data.mensaje,'exito');}catch(err){aviso('clave-error',err.message);}finally{state.busy.clave=false;ocupado('clave-form',false);$('clave-cerrar').disabled=false;$('clave-submit').textContent='Guardar contraseña';validarClave();}});
setInterval(()=>{if(state.token&&!document.hidden&&!document.querySelector('dialog[open]'))actualizar();},30000);
(async()=>{if(!state.token)return;state.busy.login=true;validarLogin();$('login-submit').textContent='Restaurando sesión…';try{const sesion=await api('/api/sesion');await abrirAplicacion(sesion);}catch(err){if(state.token)aviso('login-error',err.message);}finally{state.busy.login=false;$('login-submit').textContent='Entrar a InvAx →';validarLogin();}})();
