// Presentation values come from accepted measurements, never a preset room.
export function sessionResult(acoustic, wifi) {
  const result = acoustic?.result;
  const count = acoustic?.positions?.length ?? 0;
  const top = count && result?.status !== 'no_match' ? result?.candidates?.[0] : null;
  const statuses = {candidate: 'Top acoustic match', supported: 'Supported acoustic match', ambiguous: 'Closest match · ambiguous', no_match: 'No matching room'};
  const floor = top?.floor_ids?.length === 1 ? top.floor_ids[0] : acoustic?.floor_id;
  const lastAccepted = acoustic?.positions?.at(-1);
  const active = wifi?.connected && wifi.compatible && wifi.wifi && wifi.fresh && wifi.stage === 'detecting';
  const motion = active ? (wifi.motion === true ? 'Movement detected' : wifi.motion === false ? 'No movement detected' : 'Motion unknown')
    : wifi?.stage === 'detecting' ? 'Signal unavailable'
    : ['await_start', 'calibrating', 'await_stop', 'wait_status', 'settling'].includes(wifi?.stage) ? 'Calibrating'
    : 'Awaiting motion detection';
  return {
    top, floor, count, motion,
    title: top?.label ?? top?.room_id ?? (result?.status === 'no_match' ? 'No matching room' : 'Awaiting room measurement'),
    status: count ? statuses[result?.status] ?? 'Awaiting usable evidence' : 'Awaiting measurement',
    score: Number.isFinite(top?.score) ? top.score.toFixed(4) : '—',
    rt60: Number.isFinite(lastAccepted?.rt60_s) ? lastAccepted.rt60_s.toFixed(3) + ' s' : '—',
    snr: Number.isFinite(lastAccepted?.snr_db) ? lastAccepted.snr_db.toFixed(1) + ' dB' : '—',
    scope: acoustic?.floor_id == null ? 'All floors searched' : `Floor ${acoustic.floor_id === '0' ? 'G' : acoustic.floor_id} · selected search floor`,
    note: acoustic?.stage === 'rejected' ? 'Latest recording excluded. Showing the earlier accepted measurements.'
      : ['measuring', 'cancelling'].includes(acoustic?.stage) ? 'Measurement in progress. Showing the previous accepted result.'
      : count ? `${count} accepted position${count === 1 ? '' : 's'} · Match scores are not probabilities.`
      : 'Run an acoustic measurement in step 03 to see the room result.',
  };
}
