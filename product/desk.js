'use strict';
(() => {
  const $ = id => document.getElementById(id);
  const methods = {ordinary:'Ordinary assessment',instruction:'Provenance instruction',document:'Document selection',ledger:'Claim ledger'};
  const methodDescriptions = {ordinary:'Assess the supplied cards directly.',instruction:'A short instruction asks the model to track reporting origins and retain distinct facts.',document:'Select useful documents before assessing their evidence.',ledger:'Record claims, scope and reporting origins before writing the assessment.'};
  const conditions = {
    base:{mark:'A only',text:'The original capability is supplied. The companion has scope notes, with no repeated claim or additional capability.'},
    repeat:{mark:'A + A′',text:'The companion repeats packet capture. Repetition adds no reporting origin; the compression and encryption fact is not supplied.'},
    new:{mark:'A + B',text:'The companion adds compression and encryption, without repeating packet capture. Both facts point to the same reporting origin.'},
    mixed:{mark:'A + A′ + B',text:'The companion repeats packet capture and adds compression and encryption. Keep the new fact without counting the repeated one twice.'}
  };
  const make = (tag, text, className) => {const e=document.createElement(tag);if(text!==undefined)e.textContent=text;if(className)e.className=className;return e;};
  let records, state, activeReader=null, lastCitation=null, closeTarget=null;
  const reducedMotion=matchMedia('(prefers-reduced-motion:reduce)');
  let motionWanted=true, motionAllowed=false, renderCount=0, traceRuns=[];
  function animate(element,frames,options={}){
    if(!motionAllowed||!element?.animate)return null;
    return element.animate(frames,{duration:260,easing:'cubic-bezier(.2,.75,.2,1)',...options});
  }
  function syncMotion(){
    motionAllowed=motionWanted&&!reducedMotion.matches;
    document.documentElement.dataset.motion=motionAllowed?'on':'off';
    $('motion-toggle').disabled=reducedMotion.matches;
    $('motion-toggle').setAttribute('aria-pressed',String(motionAllowed));
    $('motion-toggle').setAttribute('aria-label',reducedMotion.matches?'Motion is off: system reduced-motion preference is enabled':motionAllowed?'Disable interface motion':'Enable interface motion');
    $('motion-label').textContent=reducedMotion.matches?'Reduced motion':motionAllowed?'Motion on':'Motion off';
    $('trace-replay').disabled=!motionAllowed;
    $('trace-replay').title=motionAllowed?'Replay this illustration; no model is run':'Animation is disabled by the motion preference';
    if(!motionAllowed)document.getAnimations().forEach(animation=>animation.cancel());
  }
  function replayTrace(){
    if(!motionAllowed)return;
    traceRuns.forEach(animation=>animation?.cancel());traceRuns=[];
    document.querySelectorAll('.wire-active path').forEach((path,index)=>traceRuns.push(animate(path,[{strokeDashoffset:1},{strokeDashoffset:0}],{duration:800,delay:index*100,fill:'backwards'})));
    traceRuns.push(animate(document.querySelector('.origin-node'),[{transform:'scale(.96)'},{transform:'scale(1)'}],{duration:450}));
    document.querySelectorAll('.trace-card').forEach((card,index)=>{
      const rest=getComputedStyle(card).transform,base=rest==='none'?'':rest;
      traceRuns.push(animate(card,[{opacity:.35,transform:'translateY(12px) '+base},{opacity:1,transform:rest}],{duration:520,delay:250+index*90,fill:'backwards'}));
    });
  }
  const announce = text => {$('selection-status').textContent=text;};
  const selected = (method=state.method) => records.find(r=>r.method===method && r.condition===state.condition);
  function validate(data) {
    if(!Array.isArray(data.outcomes)||data.outcomes.length!==16)throw Error('The saved response grid is incomplete.');
    const seen=new Set();
    for(const r of data.outcomes){
      const key=r.method+'/'+r.condition;
      if(!Object.hasOwn(methods,r.method)||!Object.hasOwn(conditions,r.condition)||seen.has(key))throw Error('The saved case has duplicate or unknown selections.');
      seen.add(key);
      if(!r.response||!Array.isArray(r.response.claims)||!Array.isArray(r.response.evidence_record)||typeof r.response.limitations!=='string'||!r.packet||!Array.isArray(r.packet.documents))throw Error('A saved answer or its evidence is missing.');
      if(!/^[a-f0-9]{24}(\/attempt-\d+)?$/.test(r.relative_directory))throw Error('A raw evidence link is invalid.');
      for(const c of r.response.claims)if(typeof c.text!=='string'||typeof c.reporting_relationship!=='string'||!Array.isArray(c.citations)||c.citations.some(v=>typeof v!=='string'))throw Error('A saved claim is malformed.');
      const ids=new Set();
      for(const doc of r.packet.documents){
        if(typeof doc.id!=='string'||!Array.isArray(doc.passages)||typeof doc.source?.url!=='string')throw Error('A supplied document is malformed.');
        if(new URL(doc.source.url).protocol!=='https:')throw Error('A referenced publication link is invalid.');
        for(const p of doc.passages){const id=doc.id+':'+p.id;if(typeof p.text!=='string'||ids.has(id))throw Error('A supplied passage is missing or duplicated.');ids.add(id);}
      }
    }
    return data.outcomes;
  }
  function readState(){
    const p=new URL(location.href).searchParams;
    const method=Object.hasOwn(methods,p.get('method'))?p.get('method'):'ledger';
    const condition=Object.hasOwn(conditions,p.get('condition'))?p.get('condition'):'mixed';
    return {method,condition,compare:p.get('compare')==='1'&&method!=='ordinary'};
  }
  function saveState(){const url=new URL(location.href);url.searchParams.set('method',state.method);url.searchParams.set('condition',state.condition);if(state.compare)url.searchParams.set('compare','1');else url.searchParams.delete('compare');try{history.pushState(null,'',url);}catch(_){announce('Selection updated. This browser could not update the local URL.');}}
  function passageFor(id){for(const doc of selected().packet.documents){const p=doc.passages.find(p=>doc.id+':'+p.id===id);if(p)return{doc,passage:p};}return null;}
  function closeReader(){if($('passage-dialog').open)$('passage-dialog').close();}
  function showReader(){
    const id=activeReader.ids[activeReader.index],found=passageFor(id);
    if(!found){closeReader();$('action-message').textContent='Passage '+id+' is unavailable in this saved packet. Use the validation report to inspect the record.';$('action-message').hidden=false;return;}
    const {doc,passage}=found;
    $('dialog-title').textContent=id;
    $('dialog-context').textContent=(doc.id==='d0'?'Fixed actor context':doc.id==='d1'?'Original card':'Companion card')+' / researcher-written text';
    $('dialog-passage').textContent=passage.text;
    $('dialog-origin').textContent='Referenced source: '+doc.source.publisher+' · '+doc.source.title;
    $('dialog-source').href=doc.source.url;
    $('citation-position').textContent=(activeReader.index+1)+' / '+activeReader.ids.length;
    $('previous-passage').disabled=activeReader.index===0;
    $('next-passage').disabled=activeReader.index===activeReader.ids.length-1;
    if(document.activeElement===$('previous-passage')&&$('previous-passage').disabled)$('next-passage').focus();
    else if(document.activeElement===$('next-passage')&&$('next-passage').disabled)$('previous-passage').focus();
    document.querySelectorAll('.passage.selected').forEach(n=>n.classList.remove('selected'));
    const target=document.getElementById('passage-'+id);if(target)target.classList.add('selected');
    if(!$('passage-dialog').open){$('passage-dialog').showModal();$('close-dialog').focus();}
    else animate($('dialog-passage'),[{opacity:.45,transform:'translateY(4px)'},{opacity:1,transform:'none'}],{duration:180});
  }
  function openReader(ids,index,button){lastCitation=button;activeReader={ids,index};showReader();}
  function renderSources(){
    const container=$('sources');container.replaceChildren();
    for(const doc of selected().packet.documents){
      const section=make('section',undefined,'source-document');
      section.append(make('h4',(doc.id==='d0'?'Fixed attribution':doc.id==='d1'?'Original card':'Companion card')+' / '+doc.id));
      const link=make('a',doc.source.title+' ↗','source-link');link.href=doc.source.url;link.target='_blank';link.rel='noopener noreferrer';link.setAttribute('aria-label',doc.source.title+' (opens a new tab)');section.append(link);
      for(const p of doc.passages){
        const id=doc.id+':'+p.id,box=make('div',undefined,'passage');box.id='passage-'+id;box.tabIndex=-1;
        box.append(make('code',id),make('p',p.text));
        const back=make('button','Return to the citation ↑','return-citation');back.type='button';back.hidden=true;back.addEventListener('click',()=>{if(lastCitation?.isConnected){lastCitation.focus();lastCitation.scrollIntoView({block:'center',behavior:'instant'});}});box.append(back);section.append(box);
      }
      container.append(section);
    }
  }
  function renderAnswer(container,record){
    container.replaceChildren();const list=make('ol',undefined,'claims');
    record.response.claims.forEach((claim,claimIndex)=>{
      const item=make('li',undefined,'claim'),title=make('div',undefined,'claim-title');title.append(make('p',claim.text));item.append(title);
      const citations=make('div',undefined,'citation-list');citations.setAttribute('aria-label','Citations for claim '+(claimIndex+1));
      claim.citations.forEach((id,index)=>{const button=make('button',id,'citation');button.type='button';button.setAttribute('aria-label','Read supplied passage '+id+' for claim '+(claimIndex+1));button.setAttribute('aria-haspopup','dialog');button.addEventListener('click',()=>openReader(claim.citations,index,button));citations.append(button);});
      item.append(citations,make('p',claim.reporting_relationship,'relationship'));list.append(item);
    });
    if(!record.response.claims.length)container.append(make('p','This saved answer contains no final claims. Its limitations and evidence record remain available.','empty-answer'));
    container.append(list);
    const limit=make('section',undefined,'limitations');limit.append(make('strong','Limitations stated by the model'),make('p',record.response.limitations));container.append(limit);
    if(record.response.evidence_record.length){const details=make('details',undefined,'reasoning');details.append(make('summary','Inspect the saved evidence record'));const ul=make('ul');record.response.evidence_record.forEach(t=>ul.append(make('li',typeof t==='string'?t:JSON.stringify(t))));details.append(ul);container.append(details);}
  }
  function render(){
    closeReader();lastCitation=null;activeReader=null;
    $('action-message').hidden=true;
    const record=selected();$('method').value=state.method;
    document.querySelectorAll('[data-condition]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.condition===state.condition)));
    $('condition-mark').textContent=conditions[state.condition].mark;$('condition-description').textContent=conditions[state.condition].text;
    $('answer-title').textContent=methods[state.method];$('method-description').textContent=methodDescriptions[state.method];
    $('answer-meta').replaceChildren(make('span',record.response.claims.length+' final claims'),make('span',record.final_words+' final words'),make('span','Saved 5 Nov 2026'));
    renderSources();renderAnswer($('answer'),record);
    $('raw-answer').href='../'+record.relative_directory+'/answer.json';$('exact-input').href='../'+record.relative_directory+'/prompt.txt';
    $('compare').disabled=state.method==='ordinary';if($('compare').disabled)state.compare=false;$('compare').checked=state.compare;
    $('compare-help').textContent=state.method==='ordinary'?'Ordinary assessment is the baseline.':'Same evidence, another saved answer.';
    $('comparison').hidden=!state.compare;if(state.compare)renderAnswer($('comparison-answer'),selected('ordinary'));
    announce(methods[state.method]+', '+state.condition+' condition. '+record.response.claims.length+' saved claims loaded. No model was run.');
    if(renderCount++){
      document.querySelectorAll('#answer .claim').forEach((claim,index)=>animate(claim,[{opacity:.3,transform:'translateY(7px)'},{opacity:1,transform:'none'}],{duration:280,delay:index*40,fill:'backwards'}));
      if(state.compare)animate($('comparison'),[{opacity:.3,transform:'translateY(9px)'},{opacity:1,transform:'none'}],{duration:300});
    }
  }
  function specimen(id,animateChange=true){
    const r=records.find(r=>r.method==='ledger'&&r.condition==='mixed');
    const p=r.packet.documents.find(d=>d.id==='d2').passages.find(p=>p.id===id);
    $('specimen-text').textContent=p.text;$('specimen-note').textContent=id==='p2'?'A different sentence can repeat the same proposition.':'A distinct fact can share the same reporting origin.';
    document.querySelectorAll('[data-specimen]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.specimen===id)));
    $('specimen-letter').textContent=id==='p2'?'A\u2032':'B';
    $('specimen-summary').replaceChildren(make('span',id==='p2'?'Remote':'Compression'),make('br'),make('span',id==='p2'?'packet capture':'+ encryption'));
    $('specimen-kind').textContent=id==='p2'?'The same capability, retold':'An additional capability';
    if(animateChange){
      animate($('specimen-summary'),[{opacity:.2,transform:'translateY(5px)'},{opacity:1,transform:'none'}],{duration:240});
      animate(document.querySelector('.wire-active path:last-child'),[{strokeDashoffset:1},{strokeDashoffset:0}],{duration:550});
    }
  }
  try{
    records=validate(JSON.parse($('study-data').textContent));state=readState();
    $('interactive-desk').hidden=false;$('packet-details').open=matchMedia('(min-width:821px)').matches;
    document.querySelectorAll('[data-condition]').forEach(button=>button.addEventListener('click',()=>{state.condition=button.dataset.condition;render();saveState();}));
    $('method').addEventListener('change',event=>{state.method=event.target.value;render();saveState();});
    $('compare').addEventListener('change',event=>{state.compare=event.target.checked;render();saveState();});
    document.querySelectorAll('[data-specimen]').forEach(button=>button.addEventListener('click',()=>specimen(button.dataset.specimen)));
    $('close-dialog').addEventListener('click',closeReader);
    $('passage-dialog').addEventListener('close',()=>{const target=closeTarget||lastCitation;closeTarget=null;if(target?.isConnected)target.focus({preventScroll:true});});
    $('passage-dialog').addEventListener('keydown',event=>{
      if(event.key!=='Tab')return;
      const controls=Array.from($('passage-dialog').querySelectorAll('button:not([disabled]),a[href]'));
      const first=controls[0],last=controls[controls.length-1];
      if(event.shiftKey&&document.activeElement===first){event.preventDefault();last.focus();}
      else if(!event.shiftKey&&document.activeElement===last){event.preventDefault();first.focus();}
    });
    $('previous-passage').addEventListener('click',()=>{if(activeReader.index>0){activeReader.index--;showReader();}});
    $('next-passage').addEventListener('click',()=>{if(activeReader.index<activeReader.ids.length-1){activeReader.index++;showReader();}});
    $('view-in-packet').addEventListener('click',()=>{const target=document.getElementById('passage-'+activeReader.ids[activeReader.index]);closeTarget=target;closeReader();$('packet-details').open=true;if(target){target.querySelector('.return-citation').hidden=false;target.focus({preventScroll:true});target.scrollIntoView({block:'center',behavior:matchMedia('(prefers-reduced-motion:reduce)').matches?'instant':'smooth'});}});
    window.addEventListener('popstate',()=>{state=readState();render();});
    $('motion-toggle').addEventListener('click',()=>{motionWanted=!motionAllowed;syncMotion();announce(motionAllowed?'Interface motion enabled.':'Interface motion disabled.');});
    reducedMotion.addEventListener('change',syncMotion);
    $('trace-replay').addEventListener('click',replayTrace);
    syncMotion();render();specimen('p3',false);
    requestAnimationFrame(()=>{
      animate($('hero-title'),[{opacity:.3,transform:'translateY(14px)'},{opacity:1,transform:'none'}],{duration:650});
      replayTrace();
    });
  }catch(error){$('interactive-desk').hidden=true;$('data-error').hidden=false;$('error-message').textContent='The saved data is incomplete or invalid. The original validation report remains available below.';document.querySelectorAll('[data-specimen]').forEach(b=>b.disabled=true);console.error('Evidence Lens: saved data could not be rendered.',error);}
})();
