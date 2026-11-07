import assert from 'node:assert/strict';
import {createBuilding} from '../web/building3d/geometry.js';
import * as THREE from '../web/vendor/three/three.module.js';
import {updateArchitecture,shellAssumptions} from '../web/building3d/architecture.js';
import {applyRoomFocus} from '../web/building3d/room-focus.js';
import {visibleMeshes} from '../web/building3d/labels.js';

const model=createBuilding();
model.group.updateMatrixWorld(true);
assert.equal(model.floors.size,5);
assert.equal(model.floors.get('LG').group.position.y,0);
assert.equal(model.floors.get('LG').group.userData.levelIndex,-1);
assert.ok(model.floors.get('0').assembledSlab);
assert.ok(model.roomParts.get('0/alder').suppressInAssembly);
assert.ok(model.roomParts.get('2/nuc-12-oak').suppressInAssembly);
assert.ok(model.floors.get('0').stair.children.length>8);
const alder=model.roomParts.get('LG/alder');
assert.ok(alder.walls.children.length);
const box=new THREE.Box3().setFromObject(alder.walls);
assert.ok(Math.abs(box.max.y-4.3)<1e-5);
const oakbox=new THREE.Box3().setFromObject(model.roomParts.get('1/nuc-12-oak').walls);
assert.ok(Math.abs(oakbox.max.y-13.7)<1e-5);
for(const [x,z,y] of [[-5,20,.7],[10,-20,.3]]) {
  const ray=new THREE.Raycaster(new THREE.Vector3(x,30,z),new THREE.Vector3(0,-1,0));
  const hits=ray.intersectObject(model.floors.get('0').slab,true);
  assert.ok(hits.length);
  assert.ok(Math.abs(hits[0].point.y-y)<1e-5);
}
for (const key of ['0','2']) {
  const floor=model.floors.get(key);
  const theatre=model.roomParts.get(key === '0' ? '0/alder' : '2/nuc-12-oak').zone.userData;
  const x=(theatre.bounds_m[0]+theatre.bounds_m[2])/2;
  const z=(theatre.bounds_m[1]+theatre.bounds_m[3])/2;
  const ray=new THREE.Raycaster(new THREE.Vector3(x,30,z),new THREE.Vector3(0,-1,0));
  assert.equal(ray.intersectObject(floor.assembledSlab,true).length,0,'Shared theatre opening must remain clear');
}
const heights=[...model.floors.values()].map(f=>f.group.position.y);
for(const [index,floor] of [...model.floors.values()].entries()) {
  const top=heights[index+1] ?? heights[index]+shellAssumptions.topStoreyHeight;
  assert.ok(Math.abs(heights[index]+floor.architecture.root.userData.height_m-top)<1e-8);
  const shell=floor.architecture;
  const camera=new THREE.PerspectiveCamera();
  camera.position.set(80,40,80);
  updateArchitecture(shell,camera,new THREE.Vector3(),true);
  assert.equal(shell.roof.visible,false);
  assert.ok(shell.walls.some(w=>w.visible));
  assert.ok(shell.walls.some(w=>!w.visible));
  updateArchitecture(shell,camera,new THREE.Vector3(),false);
  assert.ok(shell.walls.every(w=>w.visible));
  assert.equal(shell.roof.visible,true);
}
// The external envelope also covers the space ABOVE room ceilings, below the
// next storey: the previous room-only model left these bands open to the sky.
for(const y of [5,8.5,10.5,11,15.8,17,20.4]) {
  const ray=new THREE.Raycaster(new THREE.Vector3(80,y,10),new THREE.Vector3(-1,0,0));
  const shells=[...model.floors.values()].map(f=>f.architecture.root);
  assert.ok(ray.intersectObjects(shells,true).length>0,`Exterior must enclose elevation ${y}`);
}
const roofRay=new THREE.Raycaster(new THREE.Vector3(15,30,15),new THREE.Vector3(0,-1,0));
const roofHit=roofRay.intersectObject(model.floors.get('3').architecture.roof,true)[0];
assert.ok(roofHit);
assert.ok(Math.abs(roofHit.point.y-20.685)<1e-5);
console.log('Geometry checks passed: elevations, stairs, theatres, continuous facades, roof and reversible cutaway.');
applyRoomFocus(model,'2');
model.group.updateMatrixWorld(true);
assert.equal(model.floors.get('3').group.visible,false);
assert.equal(model.floors.get('2').architecture.root.visible,true);
assert.equal(model.floors.get('2').architecture.roof.visible,false);
for(const id of ['LG','0','1']) {
  const floor=model.floors.get(id);
  assert.ok(floor.group.visible && floor.architecture.root.visible);
  assert.ok(floor.architecture.walls.every(w=>w.visible));
}
assert.ok(model.roomParts.get('2/nuc-2-yew').walls.visible);
assert.ok(model.roomParts.get('1/nuc-1-larch').walls.visible);
assert.equal(model.roomParts.get('1/nuc-12-oak').walls.visible,false);
const yew=model.roomParts.get('2/nuc-2-yew').zone;
const [minX,minZ,maxX,maxZ]=yew.userData.bounds_m;
const selectionRay=new THREE.Raycaster(new THREE.Vector3((minX+maxX)/2,30,(minZ+maxZ)/2),new THREE.Vector3(0,-1,0));
assert.equal(selectionRay.intersectObjects(visibleMeshes(model),false)[0].object.userData.roomKey,'2/nuc-2-yew');
// Cross-floor theatres must remain selectable on the exposed plan, too.
assert.ok(model.roomParts.get('2/nuc-12-oak').zone.visible);
applyRoomFocus(model,'0');
assert.ok(model.floors.get('LG').group.visible);
assert.equal(model.floors.get('1').group.visible,false);
assert.ok(model.roomParts.get('0/alder').zone.visible);
console.log('Room focus checks passed: upper floors/ceilings hidden, 3D room walls retained, lower cross-floor protrusions hidden, Yew pickable.');
