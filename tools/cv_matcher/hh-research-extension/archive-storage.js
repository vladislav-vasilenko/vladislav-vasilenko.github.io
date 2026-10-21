/* Durable overflow for archive metadata/outbox. Never evicts unsynchronized records. */
(function(root){
 let opened;
 function database(){
  if(!opened)opened=new Promise((resolve,reject)=>{const request=indexedDB.open('career-archive-overflow',1);request.onupgradeneeded=()=>request.result.createObjectStore('values');request.onsuccess=()=>resolve(request.result);request.onerror=()=>reject(request.error);request.onblocked=()=>reject(Error('Хранилище архива занято другой версией расширения.'));});
  return opened;
 }
 async function transaction(mode,fn){const db=await database();return new Promise((resolve,reject)=>{const tx=db.transaction('values',mode),result={};fn(tx.objectStore('values'),result);tx.oncomplete=()=>resolve(result);tx.onerror=()=>reject(tx.error);tx.onabort=()=>reject(tx.error||Error('Запись архива прервана.'));});}
 const disk={
  read:async keys=>typeof indexedDB==='undefined'?{}:transaction('readonly',(s,result)=>{for(const key of keys){const r=s.get(key);r.onsuccess=()=>{if(r.result!==undefined)result[key]=r.result;};}}),
  write:data=>transaction('readwrite',s=>{for(const [key,value] of Object.entries(data))s.put(value,key);}),
  remove:keys=>transaction('readwrite',s=>{for(const key of keys)s.delete(key);})
 };
 function create(local,db=disk){
  async function read(keys){keys=Array.isArray(keys)?keys:[keys];return {...await local.get(keys),...await db.read(keys)};}
  async function write(data){
   // Overflow is authoritative until a newer local write and its cleanup both finish.
   // Serial users (archiveQueue) keep version receipts and outbox changes ordered.
   const keys=Object.keys(data),previous=await db.read(keys);
   try{await local.set(data);}catch(error){try{await db.write(data);return;}catch{throw Error('Хранилище Chrome заполнено; резервная запись не удалась. Данные не очищались. Сначала синхронизируйте архив с сервисом.');}}
   if(Object.keys(previous).length)await db.remove(keys);
  }
  return {read,write};
 }
 root.createArchiveStorage=create;
 if(typeof chrome!=='undefined')root.ArchiveStorage=create(chrome.storage.local);
})(globalThis);
