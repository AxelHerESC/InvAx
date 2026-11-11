/* Copias de referencia; IndexedDB nunca recibe tokens ni contraseñas. */
(function(root){
 'use strict';
 const DB='invax-offline', VERSION=1, MAX_PRODUCTS=10000, MAX_BYTES=5*1024*1024, MAX_COPIES=3;
 let opening;
 function open(){
  if(!root.indexedDB)return Promise.reject(new Error('Este navegador no permite guardar datos sin conexión.'));
  if(!opening)opening=new Promise((resolve,reject)=>{
   const req=root.indexedDB.open(DB,VERSION);
   req.onupgradeneeded=()=>{req.result.createObjectStore('contexts',{keyPath:'id'});req.result.createObjectStore('catalogs',{keyPath:'id'});};
   req.onsuccess=()=>{req.result.onversionchange=()=>{req.result.close();opening=null;};resolve(req.result);};
   req.onerror=()=>{opening=null;reject(req.error);};req.onblocked=()=>{opening=null;reject(new Error('Cierra otras pestañas de InvAx para actualizar el almacenamiento.'));};
  });return opening;
 }
 async function transaction(mode,action){
  const db=await open();return new Promise((resolve,reject)=>{
   const tx=db.transaction(['contexts','catalogs'],mode);let result;
   tx.oncomplete=()=>resolve(result);tx.onerror=()=>reject(tx.error||new Error('No fue posible guardar la copia local.'));
   tx.onabort=()=>reject(tx.error||new Error('El almacenamiento local cambió durante la operación.'));
   try{action(tx,v=>{result=v;});}catch(e){tx.abort();reject(e);}
  });
 }
 function contextValid(c){return c&&typeof c.id==='string'&&c.id.length<=80&&typeof c.usuario==='string'&&['administrador','vendedor'].includes(c.rol)&&Number.isFinite(c.hasta)&&c.hasta>Date.now();}
 function normalize(products){
  if(!Array.isArray(products)||products.length>MAX_PRODUCTS)throw new Error('El catálogo está incompleto o excede el límite de 10000 productos.');
  const ids=new Set();const clean=products.map(p=>{
   if(!p||typeof p.id!=='string'||!/^P\d{3}$/.test(p.id)||ids.has(p.id)||typeof p.nombre!=='string'||!p.nombre.trim()||p.nombre.length>256||!Number.isFinite(p.precio)||p.precio<0||p.precio>9999999999.99||!Number.isSafeInteger(p.cantidad)||p.cantidad<0||!Number.isSafeInteger(p.version)||p.version<0)throw new Error('El catálogo contiene datos inválidos o duplicados.');
   ids.add(p.id);return {id:p.id,nombre:p.nombre,precio:p.precio,cantidad:p.cantidad,version:p.version};
  }).sort((a,b)=>a.id<b.id?-1:a.id>b.id?1:0);
  if(new TextEncoder().encode(JSON.stringify(clean)).length>MAX_BYTES)throw new Error('La copia supera el límite de 5 MiB.');return clean;
 }
 function canonical(products){return JSON.stringify(normalize(products).map(p=>[p.id,p.nombre,p.precio.toFixed(2),p.cantidad,p.version]));}
 async function digest(products){
  if(!root.crypto?.subtle)throw new Error('SHA-256 no está disponible; no se guardará una copia sin verificar.');
  const bytes=await root.crypto.subtle.digest('SHA-256',new TextEncoder().encode(canonical(products)));
  return Array.from(new Uint8Array(bytes),b=>b.toString(16).padStart(2,'0')).join('');
 }
 async function validateResponse(data){
  if(data?.exito!==true)throw new Error('La respuesta no es un catálogo autorizado.');
  const products=normalize(data.productos), info=data.integridad;
  if(!info||info.esquema!==1||info.algoritmo!=='SHA-256'||info.total!==products.length||!Number.isFinite(Date.parse(info.actualizado_en))||!/^[a-f0-9]{64}$/.test(info.sha256))throw new Error('La respuesta no contiene los metadatos de integridad esperados.');
  const hash=await digest(products);if(hash!==info.sha256)throw new Error('El catálogo no supera la verificación de integridad.');
  return {productos:products,hash,actualizado_en:info.actualizado_en};
 }
 async function begin(c){
  if(!contextValid(c))throw new Error('La sesión no permite una copia local.');
  return transaction('readwrite',(tx,done)=>{
   const cs=tx.objectStore('contexts'),cat=tx.objectStore('catalogs');const get=cs.get(c.id);
   get.onsuccess=()=>{const old=get.result;if(old&&(old.usuario!==c.usuario||old.rol!==c.rol)){tx.abort();return;}
    cs.put({id:c.id,usuario:c.usuario,rol:c.rol,hasta:c.hasta,auto:old?.auto===true,usado:Date.now()});done(old?.auto===true);
    const all=cs.getAll();all.onsuccess=()=>{const rows=all.result.sort((a,b)=>b.usado-a.usado);for(const r of rows){if(r.id!==c.id&&(r.hasta<=Date.now()||rows.indexOf(r)>=MAX_COPIES)){cs.delete(r.id);cat.delete(r.id);}}};
   };
  });
 }
 function same(c,stored){return contextValid(c)&&stored&&stored.usuario===c.usuario&&stored.rol===c.rol&&stored.hasta>Date.now();}
 async function settings(c,enabled){return transaction('readwrite',(tx,done)=>{const cs=tx.objectStore('contexts'),r=cs.get(c.id);r.onsuccess=()=>{if(!same(c,r.result)){done(false);return;}cs.put({...r.result,auto:enabled,usado:Date.now()});done(true);};});}
 async function save(c,data,automatic=false){
  const clean=await validateResponse(data);if(!contextValid(c))return false;
  return transaction('readwrite',(tx,done)=>{const cs=tx.objectStore('contexts'),r=cs.get(c.id);r.onsuccess=()=>{
   if(!same(c,r.result)||(automatic&&!r.result.auto)){done(false);return;}
   tx.objectStore('catalogs').put({id:c.id,...clean,guardado_en:new Date().toISOString()});cs.put({...r.result,usado:Date.now()});done(true);
  };});
 }
 async function read(c){
  if(!contextValid(c))return null;
  const row=await transaction('readwrite',(tx,done)=>{const cs=tx.objectStore('contexts'),r=cs.get(c.id);r.onsuccess=()=>{
   if(!same(c,r.result)){done(null);return;}const cat=tx.objectStore('catalogs').get(c.id);cat.onsuccess=()=>done(cat.result?{...cat.result,auto:r.result.auto}: {productos:null,auto:r.result.auto});cs.put({...r.result,usado:Date.now()});
  };});
  if(!row||!row.productos)return row;
  if(await digest(row.productos)!==row.hash)throw new Error('La copia local fue alterada. Elimínala y sincroniza de nuevo.');
  return row;
 }
 async function clear(c){return transaction('readwrite',(tx)=>{tx.objectStore('catalogs').delete(c.id);});}
 async function logout(usuario){return transaction('readwrite',(tx)=>{const cs=tx.objectStore('contexts'),r=cs.getAll();r.onsuccess=()=>{for(const c of r.result){if(c.usuario===usuario){cs.delete(c.id);tx.objectStore('catalogs').delete(c.id);}}};});}
 root.InvAxStore={open,begin,settings,save,read,clear,logout,normalize,canonical,digest,validateResponse,contextValid,limits:{MAX_PRODUCTS,MAX_BYTES,MAX_COPIES}};
})(globalThis);
