'use strict';
/* Shared loading indicator: a spinner with text, and a real progress bar when the total is known. */
const Busy={
 create(text){
  const box=document.createElement('div');box.className='busy';box.setAttribute('role','status');
  const spinner=document.createElement('span');spinner.className='busySpinner';spinner.setAttribute('aria-hidden','true');
  const label=document.createElement('span');label.className='busyText';label.textContent=text;
  box.append(spinner,label);let bar=null;
  box.update=(value,done,total)=>{label.textContent=value;if(!total)return;if(!bar){bar=document.createElement('progress');bar.className='busyBar';box.append(bar);}bar.max=total;bar.value=done;};
  return box;
 },
};
globalThis.Busy=Busy;
