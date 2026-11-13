/* Extensión de la interfaz para el Gateway P08; los permisos se validan en servidor. */
(function(){
 'use strict';
 let mode='create',selected=null;
 const allowed=()=>state.micro&&state.rol==='administrador'&&state.connected;
 function valid(){
  const price=Number($('producto-precio').value),quantity=Number($('producto-cantidad').value);
  const fields=/^P[0-9]{3}$/.test($('producto-id').value)&&$('producto-nombre').value.trim()&&$('producto-precio').value!==''&&Number.isFinite(price)&&price>=0&&price<=9999999999.99&&Math.abs(price*100-Math.round(price*100))<1e-6;
  $('producto-submit').disabled=state.busy.producto||!allowed()||(mode!=='delete'&&(!fields||(mode==='create'&&(!Number.isInteger(quantity)||quantity<0||quantity>10000))));
 }
 function open(next,product=null){
  if(!allowed())return;mode=next;selected=product;$('producto-form').reset();aviso('producto-error','');
  $('producto-id').value=product?.id||'';$('producto-nombre').value=product?.nombre||'';$('producto-precio').value=product?.precio??'';
  $('producto-id').disabled=next!=='create';$('producto-nombre').disabled=next==='delete';$('producto-precio').disabled=next==='delete';$('producto-inicial').hidden=next!=='create';
  $('producto-titulo').textContent={create:'Nuevo producto',edit:'Editar producto',delete:'Eliminar producto'}[next];
  $('producto-submit').textContent=next==='delete'?'Confirmar eliminación':'Guardar producto';
  $('producto-nota').textContent=next==='delete'?'Se permite eliminar únicamente si no hay stock ni historial de movimientos.':next==='edit'?'Las existencias se modifican mediante ventas o reposiciones. Si el producto cambió, actualiza antes de editar.':'Utiliza un identificador nuevo con formato P005.';
  valid();$('producto-dialog').showModal();
 }
 function close(){if(state.busy.producto)return;$('producto-dialog').close();$('producto-form').reset();selected=null;}
 $('nuevo-producto').addEventListener('click',()=>open('create'));
 $('producto-form').addEventListener('input',()=>{valid();aviso('producto-error','');});
 $('producto-cerrar').addEventListener('click',close);$('producto-cancelar').addEventListener('click',close);
 $('producto-dialog').addEventListener('cancel',e=>{if(state.busy.producto)e.preventDefault();else{$('producto-form').reset();selected=null;}});
 $('producto-form').addEventListener('submit',async e=>{
  e.preventDefault();if(!allowed()||$('producto-submit').disabled)return;
  const current=selected,op=mode;let body={nombre:$('producto-nombre').value.trim(),precio:Number($('producto-precio').value)};
  if(op==='create')body={...body,id:$('producto-id').value,cantidad:Number($('producto-cantidad').value)};
  else body=op==='delete'?{version:current.version}:{...body,version:current.version};
  state.busy.producto=true;ocupado('producto-form',true);$('producto-cerrar').disabled=true;
  try{const data=await api(op==='create'?'/api/productos':'/api/productos/'+current.id,{method:op==='create'?'POST':op==='edit'?'PATCH':'DELETE',body});
   state.busy.producto=false;close();aviso('aviso-global',data.mensaje,'exito');await actualizar();
  }catch(err){aviso('producto-error',err.message);}finally{state.busy.producto=false;ocupado('producto-form',false);$('producto-cerrar').disabled=false;$('producto-id').disabled=mode!=='create';$('producto-nombre').disabled=mode==='delete';$('producto-precio').disabled=mode==='delete';valid();}
 });
 function appendActions(cell,product){
  if(!state.micro||state.rol!=='administrador')return;
  for(const [action,label] of [['edit','Editar'],['delete','Eliminar']]){const b=elemento('button',label,'accion-producto');b.type='button';b.disabled=!state.connected;b.setAttribute('aria-label',label+' '+product.nombre);b.addEventListener('click',()=>open(action,product));cell.append(b);}
 }
 async function history(){
  if(!state.connected)return;$('historial-lista').textContent='Consultando movimientos…';
  try{const data=await api('/api/'+$('historial-tipo').value+'?limite=30');const box=$('historial-lista');box.replaceChildren();
   for(const item of data.operaciones){const row=elemento('p',new Date(item.creado_en).toLocaleString('es-MX')+' · '+item.usuario+' · '+item.solicitud.producto+' · '+item.solicitud.cantidad+' unidades · '+(item.respuesta.exito?'Aplicado':'Rechazado'),'detalle-fila');box.append(row);}
   if(!data.operaciones.length)box.textContent='Sin movimientos registrados.';
  }catch(err){$('historial-lista').textContent=err.message;}
 }
 $('ver-movimientos').addEventListener('click',()=>{if(!state.connected)return;$('historial-reposiciones').hidden=state.rol!=='administrador';$('historial-tipo').value='ventas';$('historial-dialog').showModal();history();});
 $('historial-tipo').addEventListener('change',history);$('historial-cerrar').addEventListener('click',()=>$('historial-dialog').close());
 globalThis.InvAxProductAdmin={appendActions};
})();
