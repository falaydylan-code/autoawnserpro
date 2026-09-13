/* Browser input is dispatched only after the worker validates the current snapshot. */
(() => {
  let attached=null, cancelled=false, gestureUrl='', gestureStart=null;
  const pause=ms=>new Promise(r=>setTimeout(r,ms));
  async function release(id,p){try{await chrome.debugger.sendCommand({tabId:id},'Input.dispatchMouseEvent',{type:'mouseReleased',x:p.x,y:p.y,button:'left',buttons:0,clickCount:1});}catch{}}
  // Detaching mid-gesture must put the button up where the gesture BEGAN. A
  // release at (0,0) is a drop at the page corner; a release at the destination
  // completes the move the student just cancelled. If no gesture is in flight
  // there is nothing to release.
  async function detach(){cancelled=true;const id=attached,start=gestureStart;attached=null;gestureStart=null;if(id!=null){if(start)await release(id,start);try{await chrome.debugger.detach({tabId:id});}catch{}}}
  async function attach(id){if(attached===id)return;if(attached!=null)await detach();cancelled=false;try{await chrome.debugger.attach({tabId:id},'1.3');attached=id;}catch{throw new Error('Browser input unavailable. Close DevTools or another debugger for this tab and retry.');}}
  chrome.debugger.onDetach.addListener(({tabId})=>{if(tabId===attached){attached=null;cancelled=true;}});
  // The snapshot was validated against one document. If the tab starts loading
  // another while a gesture is in flight, every remaining event would land on
  // the replacement at stale coordinates. Cancel the gesture the moment
  // navigation begins, and re-check the URL before each event as well.
  chrome.tabs.onUpdated.addListener((tabId,change)=>{if(tabId===attached&&(change.url||change.status==='loading'))cancelled=true;});
  async function send(id,type,p,buttons,stopped){
    if(cancelled||attached!==id||stopped?.())throw new Error('Browser input cancelled.');
    const tab=await chrome.tabs.get(id);
    if(!tab.active)throw new Error('Assignment tab is no longer active.');
    if(tab.url!==gestureUrl||tab.status==='loading')throw new Error('The page navigated during browser input; the gesture was abandoned.');
    await chrome.debugger.sendCommand({tabId:id},'Input.dispatchMouseEvent',{type,x:p.x,y:p.y,button:type==='mouseMoved'?'none':'left',buttons,clickCount:type==='mouseMoved'?0:1});
  }
  // `stopped` is the worker's own stop flag, checked before every event so a
  // Stop or ETH-off that arrives mid-gesture halts it at once. A gesture that is
  // halted releases the button back at its START: releasing at the destination
  // would complete the very drop the student just cancelled.
  async function input(id,start,end,stopped){
    await attach(id);
    gestureUrl=(await chrome.tabs.get(id)).url;gestureStart=start;
    let completed=false;
    try{
      await send(id,'mouseMoved',start,0,stopped);await send(id,'mousePressed',start,1,stopped);
      if(end)for(let i=1;i<=16;i++){await pause(25);await send(id,'mouseMoved',{x:start.x+(end.x-start.x)*i/16,y:start.y+(end.y-start.y)*i/16},1,stopped);}
      await send(id,'mouseReleased',end||start,0,stopped);completed=true;
      return {ok:true,detail:'Browser input executed; awaiting independent verification.'};
    }finally{if(!completed&&attached===id)await release(id,start);gestureStart=null;}
  }
  async function pixels(data){const bitmap=await createImageBitmap(await (await fetch(data)).blob());const canvas=new OffscreenCanvas(bitmap.width,bitmap.height),ctx=canvas.getContext('2d');ctx.drawImage(bitmap,0,0);bitmap.close();const bytes=ctx.getImageData(0,0,canvas.width,canvas.height).data;return Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',bytes))).join(',');}
  globalThis.AssignmentVisual={input,detach,pixels};
})();
