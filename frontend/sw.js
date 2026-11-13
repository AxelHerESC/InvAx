'use strict';
const VERSION='invax-shell-4de92672df46174d';
const SHELL=['/','/assets/styles.css','/assets/app.js','/assets/product-admin.js','/assets/offline-store.js','/assets/pwa.js','/assets/favicon.svg','/manifest.webmanifest','/assets/icons/icon-192.png','/assets/icons/icon-512.png'];
self.addEventListener('install',event=>event.waitUntil((async()=>{
 try{const cache=await caches.open(VERSION);await cache.addAll(SHELL.map(url=>new Request(url,{cache:'reload',credentials:'omit'})));}
 catch(error){await caches.delete(VERSION);throw error;}
})()));
self.addEventListener('activate',event=>event.waitUntil((async()=>{
 for(const name of await caches.keys())if(name.startsWith('invax-shell-')&&name!==VERSION)await caches.delete(name);
 await self.clients.claim();
})()));
// La actualización espera una decisión del usuario. No se recarga ninguna pestaña desde aquí.
self.addEventListener('message',event=>{if(event.data?.type==='ACTIVATE_UPDATE')event.waitUntil(self.skipWaiting());});
self.addEventListener('fetch',event=>{
 const request=event.request,url=new URL(request.url);
 if(request.method!=='GET'||url.origin!==self.location.origin||request.headers.has('Authorization')||url.pathname.startsWith('/api/'))return;
 // Lista cerrada: ni API, ni archivos arbitrarios, ni respuestas autenticadas.
 if(!SHELL.includes(url.pathname)||url.search)return;
 event.respondWith((async()=>{
  const cached=await (await caches.open(VERSION)).match(url.pathname);
  if(cached)return cached;
  return fetch(request);
 })());
});
