import { mountEchoPlots } from "./acoustic-plots.js?v=anna-20261108-auto";
export function mountAcoustics(root, onState) {
  root.className = 'acoustic-panel';
  root.innerHTML = `
    <div class="acoustic-heading"><h3>Room echoes</h3><span>LIVE AUDIO · LOCAL</span></div>
    <p class="acoustic-intro">Measure the room from several positions. Compare the echoes with rooms on a chosen floor, or search all floors.</p>
    <div class="acoustic-controls"><label>Search floor<select id="echo-floor"><option value="">All floors</option><option value="0">G · Ground</option><option value="1">1 · First</option><option value="2">2 · Second</option><option value="3">3 · Third</option></select></label><span id="echo-scope">Floor selection is manual.</span></div>
    <details class="acoustic-settings" open><summary>Microphone & speaker</summary>
      <div class="acoustic-controls"><label>Microphone<select id="echo-input" aria-label="Acoustic microphone"></select></label><label>Speaker<select id="echo-output" aria-label="Acoustic speaker"></select></label><button id="echo-refresh" type="button">Refresh devices</button></div>
      <div class="acoustic-controls"><label>Microphone height (m)<input id="echo-height" type="number" min="0.1" max="2.5" step="0.01" value="0.75"></label><label>Speaker–mic distance (m)<input id="echo-distance" type="number" min="0.01" max="1" step="0.01" value="0.10"></label><label>Playback gain<input id="echo-gain" type="number" min="0.01" max="0.3" step="0.01" value="0.10"></label></div>
      <p class="acoustic-note">Windows uses WASAPI exclusive mode. Close other audio apps if capture fails. The 0.10 m speaker–mic distance is an estimate; update it for your setup. Audio settings stay fixed within a session.</p>
    </details>
    <label class="acoustic-moved" id="echo-moved-label" hidden><input id="echo-moved" type="checkbox">I have moved the laptop to a different position in the same room, at the same height.</label>
    <div class="acoustic-actions"><button class="primary" id="echo-start" type="button" disabled>Start measurement · P1</button><button id="echo-cancel" type="button" disabled>Cancel measurement</button><button id="echo-reset" type="button">New room / reset positions</button></div>
    <p class="acoustic-note">Each measurement plays three short sweeps (about 20 seconds). Keep the laptop still while recording. Audio is saved on this computer.</p>
    <progress id="echo-progress" max="3" value="0" aria-label="Acoustic measurement progress" hidden></progress>
    <p id="echo-message" class="acoustic-message" role="status" aria-live="polite">Connecting to the local audio service…</p>
    <p id="echo-error" class="acoustic-error" role="alert" hidden></p>
    <div class="acoustic-stats"><div><span>Latest RT60</span><strong id="echo-rt60">—</strong></div><div><span>Signal / noise</span><strong id="echo-snr">—</strong></div><div><span>Estimated ceiling</span><strong id="echo-ceiling">—</strong></div><div><span>Accepted positions</span><strong id="echo-count">0</strong></div></div>
    <div class="acoustic-heading"><h3>Echo measurements</h3><span id="echo-chart-label">No recording yet</span></div>
    <div id="echo-figures"></div>
    <div class="acoustic-heading"><h3>Ranked room candidates</h3><strong id="echo-result-status">Awaiting measurement</strong></div>
    <p id="echo-evidence" class="acoustic-note">One position uses reverberation time. Additional positions can add ceiling and nearest-wall evidence.</p>
    <div class="acoustic-table-wrap"><table class="acoustic-table"><thead><tr><th>Rank</th><th>Room</th><th>Floor</th><th>Match score</th></tr></thead><tbody id="echo-ranking"><tr><td colspan="4">No measurements yet.</td></tr></tbody></table></div>
    <p class="acoustic-note">Match scores are not probabilities. “Supported” is an algorithm status, not a confirmed location. Similar rooms may remain ambiguous.</p>
    <p id="echo-history" class="acoustic-history"></p>`;
  const $ = id => root.querySelector('#echo-' + id);
  const write = (id, value) => { if ($(id).textContent !== value) $(id).textContent = value; };
  const fmt = (n, places = 2) => Number.isFinite(n) ? n.toFixed(places) : '—';
  let state = null, busy = false, polling = false, reachable = false, inventory = false, ranked = '';
  const working = () => ['measuring', 'cancelling', 'plotting'].includes(state?.stage);
  function buttons() {
    const locked = busy || !reachable || working(), count = state?.positions?.length ?? 0;
    $('start').disabled = locked || !inventory || !$('input').value || !$('output').value || (count > 0 && !$('moved').checked) || count >= 8;
    $('cancel').disabled = busy || !reachable || state?.stage !== 'measuring';
    $('reset').disabled = locked;
    $('floor').disabled = locked;
    $('refresh').disabled = locked || count > 0;
    for (const id of ['input', 'output', 'height', 'distance', 'gain']) $(id).disabled = locked || count > 0;
    $('moved').disabled = locked;
    $('moved-label').hidden = count === 0;
    write('start', count ? `Measure next position · P${count+1}` : 'Start measurement · P1');
  }
  const draw = mountEchoPlots($('figures'));
  function render(s) {
    state = s;
    if(s.settings){for(const [id,key] of [['height','mic_height_m'],['distance','speaker_mic_m'],['gain','gain']])$(id).value=s.settings[key];if(inventory){$('input').value=s.settings.input.id;$('output').value=s.settings.output.id;}}
    $('floor').value = s.floor_id ?? '';
    write('scope', s.floor_id === null ? 'All 14 database rooms · no floor restriction' : `Manual floor ${s.floor_id==='0'?'G':s.floor_id} · existing recordings are re-ranked`);
    write('message',s.message);$('message').dataset.stage=s.stage;
    $('progress').hidden = !['measuring', 'cancelling'].includes(s.stage);$('progress').value=s.progress;
    const m=s.last?.measurement, result=s.result, count=s.positions?.length??0;
    write('rt60',m?.rt60_s == null?'—':fmt(m.rt60_s,3)+' s');write('snr',m?.snr_db == null?'—':fmt(m.snr_db,1)+' dB');
    write('ceiling',result?.measured?.height_m == null?'Needs multiple positions':fmt(result.measured.height_m)+' m');write('count',String(count));
    write('chart-label',m?`${m.position_label} · ${s.last.quality_issues?.length?'excluded from ranking':'recorded'}`:'No recording yet');
    if (s.stage !== 'plotting') draw(s.last);
    const labels={listening:'Awaiting measurement',candidate:'Candidate',supported:'Supported',ambiguous:'Ambiguous',no_match:'No match'};
    write('result-status',labels[result?.status]??'Awaiting measurement');
    const terms=Object.keys(result?.candidates?.[0]?.cost_terms??{}).map(t=>({rt60:'reverberation',height:'ceiling height',wall:'nearest wall',span:'wall span'})[t]??t);
    write('evidence',count?`Ranking uses ${count} accepted position(s) · ${terms.join(' + ')||'not enough usable evidence'}.${s.stage==='rejected'?' Latest recording excluded; ranking uses earlier accepted positions.':''}`:'One position uses reverberation time. Additional positions can add ceiling and nearest-wall evidence.');
    const sig=JSON.stringify(result?.candidates??[]);
    if(sig!==ranked){ranked=sig;$('ranking').replaceChildren();
      for(const [i,c] of (result?.candidates??[]).entries()) {const row=document.createElement('tr');for(const value of [String(i+1).padStart(2,'0'),c.label??c.room_id,c.floor_ids.map(f=>f==='0'?'G':f).join('–'),fmt(c.score,4)]) {const td=document.createElement('td');td.textContent=value;row.append(td);}if(i===0)row.className='top';$('ranking').append(row);}
      if(!result?.candidates?.length){const row=document.createElement('tr'),td=document.createElement('td');td.colSpan=4;td.textContent='No accepted measurements for this session.';row.append(td);$('ranking').append(row);}
    }
    write('history',(s.positions??[]).map(p=>`${p.label}: RT60 ${fmt(p.rt60_s,3)} s · SNR ${fmt(p.snr_db,1)} dB`).join('  /  '));
    buttons();onState(s);
  }
  async function poll(){if(polling||(root.offsetParent===null&&state&&document.querySelector('[data-view="results"]').hidden&&document.querySelector('[data-view="model"]').hidden))return;polling=true;try{const r=await fetch('/acoustics/state',{cache:'no-store'});if(!r.ok)throw Error();reachable=true;render(await r.json());}catch{reachable=false;write('message','Local audio service unavailable. Check the Hub server.');buttons();}finally{polling=false;}}
  async function post(path,body={}) {if(busy)return false;busy=true;$('error').hidden=true;buttons();try{const r=await fetch('/acoustics/'+path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});const s=await r.json();if(!r.ok)throw Error(typeof s.detail==='string'?s.detail:'Check the audio settings and numerical values.');render(s);return true;}catch(e){write('error',e.message);$('error').hidden=false;return false;}finally{busy=false;buttons();}}
  async function refresh(){busy=true;buttons();try{const r=await fetch('/acoustics/devices');const d=await r.json();if(!r.ok)throw Error(d.detail??'Unable to read audio devices.');for(const [id,items,def] of [['input',d.inputs,d.default_input],['output',d.outputs,d.default_output]]){const old=$(id).value;$(id).replaceChildren(...items.map(p=>new Option(`${p.name} · ${p.api}`,p.id)));$(id).value=items.some(p=>String(p.id)===old)?old:String(def??'');}inventory=Boolean(d.inputs.length&&d.outputs.length);if(!inventory)throw Error('No microphone/speaker pair available. Connect devices and refresh.');}catch(e){write('error',e.message);$('error').hidden=false;}finally{busy=false;buttons();}}
  $('floor').onchange=()=>post('floor',{floor_id:$('floor').value||null});
  $('start').onclick=async()=>{const ok=await post('measure',{floor_id:$('floor').value||null,input_id:Number($('input').value),output_id:Number($('output').value),mic_height_m:Number($('height').value),speaker_mic_m:Number($('distance').value),gain:Number($('gain').value),new_position:$('moved').checked});if(ok)$('moved').checked=false;buttons();};
  $('cancel').onclick=()=>post('cancel');$('reset').onclick=()=>post('reset');$('refresh').onclick=refresh;$('moved').onchange=buttons;
  for(const id of ['input','output'])$(id).onchange=buttons;
  const timer=setInterval(poll,500);window.addEventListener('pagehide',()=>clearInterval(timer),{once:true});refresh();poll();
}
