// Measurement pages follow evidence; only step 04 owns an editable model view.
export function modelPresentation(view, pressure, acoustic) {
  if (view === 'model') return {editable: true};
  const result = {editable: false, floorId: null, roomKey: ''};
  if (view === 'floor') {
    if (pressure?.fresh && pressure.estimate?.status === 'settled') result.floorId = pressure.estimate.floor_id;
  } else if (['room', 'results'].includes(view)) {
    const ranking = acoustic?.result;
    const top = acoustic?.positions?.length && ranking?.status !== 'no_match' ? ranking?.candidates?.[0] : null;
    if (top) {
      const floors = top.floor_ids ?? [];
      result.floorId = floors.includes(acoustic.floor_id) ? acoustic.floor_id : floors.length === 1 ? floors[0] : null;
      if (result.floorId != null) result.roomKey = `${result.floorId}/${top.room_id}`;
    }
  }
  return result;
}
