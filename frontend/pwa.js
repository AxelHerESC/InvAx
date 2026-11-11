(function(){
 'use strict';
 let installPrompt,registration,reloading=false,requested=false;
 const $=id=>document.getElementById(id);
 const busy=()=>Boolean(globalThis.InvAxLifecycle?.busy())||Boolean(document.querySelector('dialog[open]'))||['login-form','usuario-form','clave-form'].some(id=>Array.from($(id).querySelectorAll('input')).some(el=>el.value));
 function updateNotice(){if(registration?.waiting)$('pwa-update').hidden=false;}
 window.addEventListener('beforeinstallprompt',e=>{e.preventDefault();installPrompt=e;$('pwa-install-text').textContent='Instala InvAx para abrirla en su propia ventana.';});
 window.addEventListener('appinstalled',()=>{installPrompt=null;$('pwa-install-text').textContent='InvAx está instalada en este dispositivo.';});
 $('pwa-install').addEventListener('click',async()=>{
  if(installPrompt){const prompt=installPrompt;installPrompt=null;await prompt.prompt();await prompt.userChoice;}
  else $('pwa-install-text').textContent='En Chrome o Edge busca «Instalar aplicación» en el menú. En Safari usa Compartir → Añadir a pantalla de inicio o Añadir al Dock. Si no existe la opción, usa InvAx desde el navegador.';
 });
 $('pwa-update-button').addEventListener('click',()=>{
  if(busy()){$('pwa-update-text').textContent='Termina o cancela la operación y vacía los formularios antes de actualizar.';return;}
  if(registration?.waiting){requested=true;$('pwa-update-button').disabled=true;registration.waiting.postMessage({type:'ACTIVATE_UPDATE'});}
  else if(requested&&!reloading){reloading=true;location.reload();}
 });
 if(!('serviceWorker' in navigator)||!window.isSecureContext){$('pwa-install-text').textContent='La instalación y apertura sin conexión requieren un navegador compatible y HTTPS.';return;}
 navigator.serviceWorker.addEventListener('controllerchange',()=>{
  if(!requested)return;
  if(!busy()&&!reloading){reloading=true;location.reload();}
  else{$('pwa-update-button').disabled=false;$('pwa-update-text').textContent='Versión preparada. Termina tu operación y pulsa Actualizar ahora.';}
 });
 navigator.serviceWorker.register('/sw.js',{scope:'/',updateViaCache:'none'}).then(r=>{
  registration=r;updateNotice();
  r.addEventListener('updatefound',()=>{const worker=r.installing;worker?.addEventListener('statechange',()=>{if(worker.state==='installed'&&navigator.serviceWorker.controller)updateNotice();});});
 }).catch(()=>{$('pwa-install-text').textContent='No se pudo preparar la apertura sin conexión. Puedes seguir usando InvAx en línea.';});
 // Actualización del SW con cadencia limitada; sin recargas automáticas.
 document.addEventListener('visibilitychange',()=>{if(!document.hidden)registration?.update().catch(()=>{});});
})();
