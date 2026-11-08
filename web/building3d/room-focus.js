// Reveal a room in the translucent 3D cutaway, retaining its actual wall height.
export function applyRoomFocus(model, floorId) {
  const target=model.floors.get(floorId);
  if(!target) return;
  const elevation=target.group.userData.elevation_m;
  for(const [id,floor] of model.floors) {
    floor.group.visible=floor.group.userData.elevation_m<=elevation;
    floor.group.position.y=floor.group.userData.elevation_m;
    floor.architecture.root.visible=true;
    const sharedOpening=id!==floorId && Boolean(floor.assembledSlab);
    floor.slab.visible=!sharedOpening;
    if(floor.assembledSlab) floor.assembledSlab.visible=sharedOpening;
    floor.architecture.roof.visible=false;
    floor.architecture.skylights.visible=false;
    if(floor.stair) floor.stair.visible=id!==floorId;
  }
  for(const part of model.roomParts.values()) {
    const onPlan=part.zone.userData.floorId===floorId;
    const below=part.zone.userData.elevation_m<elevation;
    part.zone.visible=onPlan || (below && !part.suppressInAssembly);
    // A lower access envelope must not protrude into the floor being inspected.
    const top=part.zone.userData.elevation_m+(part.zone.userData.rendered_clearance_m ?? 0);
    part.walls.visible=onPlan || (below && top<=elevation && !part.suppressInAssembly);
    part.zone.userData.focus_muted=!onPlan;
  }
}
