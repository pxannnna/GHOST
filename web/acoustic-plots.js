const figures = {
  traces: ['Echo traces', 'Echo strength against reflection distance, separated by measurement position. Dots mark detected echoes.'],
  agreement: ['Position agreement', 'Compare accepted positions: vertical bands show reflections at similar distances. They do not by themselves identify a surface.'],
  decay: ['Reverberation', 'Sound-energy decay at each accepted position, using the 1 kHz band. The room ranking uses the combined reverberation evidence.'],
  recording: ['Recording & spectrum', 'The latest recorded sweep: microphone waveform above, frequency over time below.'],
};

export function mountEchoPlots(root) {
  root.innerHTML = `<div class="echo-plot-tabs" role="group" aria-label="Acoustic figures"></div>
    <figure class="echo-plot-figure"><a class="echo-plot-full" target="_blank" rel="noopener" hidden><img alt="" hidden></a>
    <p class="acoustic-note echo-plot-message" role="status">Start a measurement to see the figures.</p>
    <figcaption hidden></figcaption></figure>
    <div class="echo-plot-tools"><a target="_blank" rel="noopener" hidden>Open full-size figure ↗</a><button type="button" hidden>Reload figures</button></div>`;
  const tabs = root.querySelector('.echo-plot-tabs'), img = root.querySelector('img');
  const full = root.querySelector('.echo-plot-full'), open = root.querySelector('.echo-plot-tools a');
  const message = root.querySelector('.echo-plot-message'), caption = root.querySelector('figcaption');
  const retry = root.querySelector('button');
  let key = '', folder = '', selected = 'traces', manifest = null, last = null, request = null;
  function show(name) {
    selected = name;
    for (const button of tabs.children) button.setAttribute('aria-pressed', String(button.dataset.figure === name));
    img.hidden = true; full.hidden = true; open.hidden = true; caption.hidden = true;
    message.hidden = false; message.textContent = 'Loading figure…';
    const url = `${folder}/${name}.png`;
    img.alt = `${figures[name][0]} from this session's recorded audio`;
    caption.textContent = figures[name][1] + ` Positions: ${(name === 'recording' ? [last.measurement.position_label] : name === 'traces' ? manifest.positions : manifest.accepted_positions).join(', ')}.`;
    full.href = open.href = url;
    img.onload = () => { img.hidden = false; full.hidden = false; open.hidden = false; caption.hidden = false; message.hidden = true; };
    img.onerror = () => { message.hidden = false; message.textContent = 'Figure unavailable. Reload figures to try again.'; };
    img.src = url;
  }
  async function update(data, force = false) {
    const id = data?.measurement?.measurement_id ?? '';
    if (key === id && !force) return;
    key = id; last = data;
    request?.abort(); request = new AbortController();
    const currentRequest = request;
    tabs.replaceChildren(); img.onload = img.onerror = null; img.removeAttribute('src');
    img.hidden = full.hidden = open.hidden = caption.hidden = true;
    retry.hidden = !id; message.hidden = false;
    if (!id) { message.textContent = 'Start a measurement to see the figures.'; return; }
    const match = /^(web-[0-9a-f]+)\/(P[1-8])\/(\d{8}-\d{6})$/.exec(id);
    if (!match) { message.textContent = 'No saved browser recording is available for this measurement.'; return; }
    folder = `/acoustic-plots/${match[1]}/${match[2]}_${match[3]}`;
    message.textContent = 'Loading recorded-audio figures…';
    try {
      const response = await fetch(`${folder}/manifest.json`, {cache: 'no-store', signal: request.signal});
      if (!response.ok) throw Error();
      const next = await response.json();
      if (currentRequest !== request) return;
      if (next.measurement_id !== id) throw Error();
      manifest = next;
      const available = Object.keys(figures).filter(name => next.plots.includes(name));
      if (!available.length) throw Error();
      for (const name of available) {
        const button = document.createElement('button'); button.type = 'button'; button.textContent = figures[name][0]; button.dataset.figure = name;
        button.onclick = () => show(name); tabs.append(button);
      }
      show(available.includes(selected) ? selected : available[0]);
    } catch (error) {
      if (currentRequest !== request || error.name === 'AbortError') return;
      message.textContent = 'Figures could not be loaded. The recording and room ranking are still available.';
    }
  }
  retry.onclick = () => update(last, true);
  return update;
}
