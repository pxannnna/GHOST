export function mountPressure(root, onState) {
  root.innerHTML = `<h2>USB barometer</h2>
    <div class="pressure-controls"><label>Device<select data-p="port" aria-label="Pressure device"><option value="">Auto-detect pressure board</option></select></label><button data-p="refresh">Refresh devices</button><button data-p="connect">Connect</button><button data-p="disconnect" disabled>Disconnect</button></div>
    <p data-p="connection" role="status" class="muted">Looking for connected devices…</p>
    <div class="pressure-calibration-controls"><div class="pressure-controls"><label>Current floor for calibration<select data-p="floor"><option value="">Select your current floor</option><option value="0">G · Ground</option><option value="1">1 · First</option><option value="2">2 · Second</option><option value="3">3 · Third</option></select></label><button data-p="calibrate" disabled>Calibrate here</button></div>
    <p class="muted">Keep the board still while calibrating. Detection then runs continuously. Recalibrate after reconnecting.</p><p data-p="calibration" class="muted"></p></div>
    <p class="pressure-error" data-p="error" role="alert" hidden></p>
    <button data-p="use" disabled>Use detected floor for room search</button><p data-p="used" class="muted" role="status"></p>`;
  const calibrationRoot = document.getElementById('pressure-calibration');
  calibrationRoot.replaceChildren(root.querySelector('.pressure-calibration-controls'));
  const $ = name => root.querySelector(`[data-p="${name}"]`) ?? calibrationRoot.querySelector(`[data-p="${name}"]`);
  let state = null, busy = false, polling = false;
  function buttons() {
    const running = ['connecting','connected','reconnecting'].includes(state?.stage);
    $('connect').disabled = busy || running;
    $('port').disabled = busy || running;
    $('disconnect').disabled = busy || !running;
    $('refresh').disabled = busy;
    $('calibrate').disabled = busy || !state?.can_calibrate || !$('floor').value;
    $('use').disabled = busy || !state?.fresh || state.estimate?.status !== 'settled';
  }
  function render(next) {
    state = next;
    $('connection').textContent = `${next.port ? next.port + ' · ' : ''}${next.message}`;
    $('calibration').textContent = next.calibration_floor == null ? 'Not calibrated.' : `Calibrated on floor ${next.calibration_floor === '0' ? 'G' : next.calibration_floor}.`;
    buttons(); onState(next);
  }
  async function refresh() {
    try {
      const r = await fetch('/pressure/devices', {cache:'no-store'});
      if (!r.ok) throw Error('Unable to list serial devices.');
      const data = await r.json(), previous = $('port').value;
      $('port').replaceChildren(new Option('Auto-detect pressure board', ''));
      for (const p of data.devices) $('port').add(new Option(`${p.port} · ${p.description}${p.recommended ? ' · pressure board' : ''}`, p.port));
      if (data.devices.some(p => p.port === previous)) $('port').value = previous;
    } catch (e) { $('error').textContent=e.message; $('error').hidden=false; }
  }
  async function action(path, body={}) {
    if (busy) return;
    busy=true; $('error').hidden=true; buttons();
    try {
      const r=await fetch('/pressure/'+path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
      const data=await r.json();
      if(!r.ok) throw Error(typeof data.detail === 'string' ? data.detail : 'Check the selected device and floor.');
      render(data);
    } catch(e) { $('error').textContent=e.message; $('error').hidden=false; }
    finally {busy=false;buttons();}
  }
  async function poll() {
    if(polling) return;
    polling=true;
    try {
      const r=await fetch('/pressure/state',{cache:'no-store'});
      if(!r.ok) throw Error();
      render(await r.json());
    } catch {
      render({stage:'offline',fresh:false,estimate:null,history_hpa:[],message:'Local pressure service unavailable.'});
    } finally {polling=false;}
  }
  $('refresh').onclick=refresh;
  $('connect').onclick=()=>action('connect',{port:$('port').value || null});
  $('disconnect').onclick=()=>action('disconnect');
  $('calibrate').onclick=()=>action('calibrate',{floor_id:$('floor').value});
  $('floor').onchange=buttons;
  $('use').onclick=async()=>{
    if(busy || !state?.fresh || state.estimate?.status !== 'settled') return;
    const floor=state.estimate.floor_id;
    busy=true;buttons();$('error').hidden=true;
    try {
      const r=await fetch('/acoustics/floor',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({floor_id:floor})});
      const data=await r.json();if(!r.ok) throw Error(data.detail || 'Unable to set the room-search floor.');
      $('used').textContent=`Room search now uses floor ${floor === '0' ? 'G' : floor}. Open 03 Room identification to measure.`;
    } catch(e) {$('error').textContent=e.message;$('error').hidden=false;}
    finally {busy=false;buttons();}
  };
  const timer=setInterval(poll,500);
  window.addEventListener('pagehide',()=>clearInterval(timer),{once:true});
  refresh();poll();
}
