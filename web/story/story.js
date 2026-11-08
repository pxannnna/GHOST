import * as T from '../vendor/three/three.module.js';
import {createBuilding} from '../building3d/geometry.js';
import {applyRoomFocus} from '../building3d/room-focus.js';
import {updateArchitecture} from '../building3d/architecture.js';
const $=id=>document.getElementById(id), reduced=matchMedia('(prefers-reduced-motion: reduce)').matches;
const scenes=[
 [0,'Europe','CONTINENT','Someone needs help.<br>Where are they?','No cameras. No indoor GPS. We start with signals we cannot see.'],
 [12,'Edinburgh','CITY','A sound.<br>A city.','An aircraft passing overhead leaves an acoustic clue. Could its recording and flight path narrow the search?'],
 [24,"King’s Buildings",'CAMPUS','Closer.<br>King’s Buildings.','For this story, we arrive at the Nucleus in Edinburgh. The outdoor location is a scenario, not a computed result.'],
 [37,'The Nucleus','BUILDING','A building is<br>only the beginning.','Help needs to reach the right place inside. Let’s look through the building.'],
 [54,'The floor','PRESSURE','First, find<br>the floor.','Air pressure gives a height relative to a reference. In this scenario, we narrow the search to the second floor.'],
 [74,'The room','ACOUSTICS','Listen to<br>the room.','A short chirp returns from the walls and ceiling. We compare those echoes with the floor plan: Yew is the leading candidate.'],
 [96,'Help','WI-FI MOTION','Movement.<br>A place to send help.','Wi-Fi changes reveal motion. Here it stands in for a request for help: second floor, Yew first, with other candidate rooms retained.']
];
let time=0,playing=false,active=-1,last=performance.now(),sceneTime=0,w=1,h=1,land=null;
const canvas=$('map'),ctx=canvas.getContext('2d');
let renderer,world,camera,model,room,person,rings=[],links=[],devices=[],target=new T.Vector3(),dest=new T.Vector3(),look=new T.Vector3(),cam=new T.Vector3(110,100,130);
const originals=new Map();
const centre=new T.Vector3(), roomCenter=new T.Vector3();
const mapCam={lon:10,lat:52,span:70};
const mapTargets=[[10,52,70],[-4,56,13],[-3.184,55.939,.24]];
function error(message){$('load-error').hidden=false;$('load-error').textContent=message;}
fetch('./land.geojson').then(r=>{if(!r.ok)throw Error();return r.json();}).then(x=>land=x).catch(()=>error('Map outlines could not load. The building scenes remain available.'));
function initWorld(){
 renderer=new T.WebGLRenderer({antialias:true,alpha:false});renderer.setPixelRatio(Math.min(devicePixelRatio,2));renderer.setClearColor(0xf3f6f5);$('world').append(renderer.domElement);
 world=new T.Scene();world.add(new T.HemisphereLight(0xffffff,0x869396,2));const light=new T.DirectionalLight(0xfff8e9,2.5);light.position.set(-60,120,60);world.add(light);
 camera=new T.PerspectiveCamera(35,1,.1,1500);model=createBuilding();world.add(model.group);model.group.traverse(o=>{if(o.isMesh&&o.material?.color)originals.set(o.material,{color:o.material.color.clone(),opacity:o.material.opacity});});model.group.updateMatrixWorld(true);
 new T.Box3().setFromObject(model.group).getCenter(centre);room=model.roomParts.get('2/nuc-2-yew');new T.Box3().setFromObject(room.zone).getCenter(roomCenter);roomCenter.y=10.85;
 const ground=new T.Mesh(new T.PlaneGeometry(300,300),new T.MeshBasicMaterial({color:0xe9eeeb}));ground.rotation.x=-Math.PI/2;ground.position.y=-.3;world.add(ground);
 const grid=new T.GridHelper(300,30,0xdde4df,0xe1e7e3);grid.position.y=-.25;world.add(grid);
 person=new T.Group();const body=new T.Mesh(new T.CylinderGeometry(.23,.32,1.05,16),new T.MeshStandardMaterial({color:0x4043bc}));body.position.y=.8;person.add(body);const head=new T.Mesh(new T.SphereGeometry(.22,20,12),new T.MeshStandardMaterial({color:0x4043bc}));head.position.y=1.55;person.add(head);person.position.copy(roomCenter);world.add(person);
 for(let i=0;i<4;i++){const ring=new T.Mesh(new T.RingGeometry(.96,1,100),new T.MeshBasicMaterial({color:0x5656ed,transparent:true,opacity:.4,side:T.DoubleSide,depthWrite:false}));ring.rotation.x=-Math.PI/2;ring.position.copy(roomCenter);ring.position.y+=.15;world.add(ring);rings.push(ring);}
 for(const [i,offset] of [[-5,1,3],[5,1,-3]].entries()){const device=new T.Mesh(new T.BoxGeometry(.7,.5,.7),new T.MeshStandardMaterial({color:0x4545bd}));device.position.copy(roomCenter).add(new T.Vector3(...offset));world.add(device);devices.push(device);}
 for(let i=0;i<3;i++){const geom=new T.BufferGeometry().setFromPoints([new T.Vector3(),new T.Vector3(),new T.Vector3()]);const line=new T.Line(geom,new T.LineBasicMaterial({color:i===1?0xd39a34:0x5354cf,transparent:true,opacity:.6}));world.add(line);links.push(line);}
}
try{initWorld();}catch(e){error('3D graphics are unavailable. Try opening this page in a browser with WebGL enabled.');}
function resize(){w=$('stage').clientWidth;h=$('stage').clientHeight;const d=Math.min(devicePixelRatio,2);canvas.width=w*d;canvas.height=h*d;ctx.setTransform(d,0,0,d,0,0);if(renderer){renderer.setSize(w,h);camera.aspect=w/h;camera.updateProjectionMatrix();}}
new ResizeObserver(resize).observe($('stage'));
function point(lon,lat){const s=w/mapCam.span;return [w*(w<700?.5:.64)+(lon-mapCam.lon)*s,h*(w<700?.65:.53)-(lat-mapCam.lat)*s/Math.cos(mapCam.lat*Math.PI/180)];}
function path(points,stroke,fill,width=1){ctx.beginPath();points.forEach((p,i)=>i?ctx.lineTo(...p):ctx.moveTo(...p));if(fill){ctx.closePath();ctx.fillStyle=fill;ctx.fill();}if(stroke){ctx.strokeStyle=stroke;ctx.lineWidth=width;ctx.stroke();}}
function label(x,y,name,size=12,color='#56696d'){ctx.fillStyle=color;ctx.font=`${size}px Segoe UI`;ctx.fillText(name,x,y);}
function marker(lon,lat,name,pulse=true){const [x,y]=point(lon,lat);ctx.beginPath();ctx.arc(x,y,5,0,Math.PI*2);ctx.fillStyle='#4545ed';ctx.fill();ctx.beginPath();ctx.arc(x,y,12+(reduced?0:Math.sin(time*2)*3),0,Math.PI*2);ctx.strokeStyle='#4545ed55';ctx.stroke();label(x+18,y-14,name,14,'#303d44');}
function drawMap(){ctx.clearRect(0,0,w,h);ctx.fillStyle='#e9efee';ctx.fillRect(0,0,w,h);
 if(active<2){if(land){for(const f of land.features){const polygons=f.geometry.type==='MultiPolygon'?f.geometry.coordinates:[f.geometry.coordinates];for(const polygon of polygons){path(polygon[0].map(p=>point(...p)),'#b9c7c2','#f7f8f3',.8);}}}
 for(let lat=30;lat<75;lat+=10)path([point(-40,lat),point(65,lat)],'#b8c7c433',null);for(let lon=-30;lon<60;lon+=10)path([point(lon,25),point(lon,75)],'#b8c7c433',null);
 marker(-3.1883,55.9533,'Edinburgh');if(active===0){let p=point(17,47);label(...p,'EUROPE',18,'#889794');p=point(-9,61);label(...p,'NORTH ATLANTIC',10,'#91a3a4');}else{const p=point(-4.5,57.3);label(...p,'SCOTLAND',14,'#84958f');const a=point(-7.5,56.7),b=point(-.4,55.1);ctx.setLineDash([5,7]);path([a,b],'#7777d0',null,1);ctx.setLineDash([]);const t=(time-12)/12;const x=a[0]+(b[0]-a[0])*t,y=a[1]+(b[1]-a[1])*t;label(x,y,'✈',24,'#4848a8');}}
 else{drawCity();}
}
function drawCity(){
 // Schematic local street network. These are not surveyed roads or building footprints.
 for(let i=-8;i<9;i++){const a=point(-3.19+i*.004,55.90),b=point(-3.18+i*.004,55.98);path([a,b],'#d0dad6',null,10);path([point(-3.24,55.92+i*.004),point(-3.13,55.92+i*.004)],'#d0dad6',null,7);}
 const park=point(-3.161,55.946);ctx.fillStyle='#d5e3d7';ctx.beginPath();ctx.ellipse(...park,w*.09,h*.21,-.5,0,Math.PI*2);ctx.fill();label(park[0]-30,park[1],"Holyrood Park",11,'#7d9583');
 for(const [dx,dy,sx,sy] of [[-.002,.0015,.001,.001],[.0017,.001,.0012,.0006],[-.002,-.001,.001,.0008],[.0015,-.0012,.0007,.001]]){const a=point(-3.174+dx,55.9225+dy),b=point(-3.174+dx+sx,55.9225+dy+sy);ctx.fillStyle='#dbe2dd';ctx.fillRect(a[0],b[1],b[0]-a[0],a[1]-b[1]);}marker(-3.1883,55.9533,'Edinburgh');marker(-3.174,55.9225,"King’s Buildings · The Nucleus");
 const p=point(-3.174,55.9225);ctx.strokeStyle='#4545ed44';ctx.lineWidth=1;ctx.strokeRect(p[0]-55,p[1]-35,110,70);
}
function resetBuilding(){if(!model)return;for(const [m,v] of originals){m.color.copy(v.color);m.opacity=v.opacity;}for(const f of model.floors.values()){f.group.visible=true;f.slab.visible=true;if(f.assembledSlab)f.assembledSlab.visible=false;f.architecture.root.visible=true;f.architecture.roof.visible=true;f.architecture.skylights.visible=true;if(f.stair)f.stair.visible=true;}
 for(const p of model.roomParts.values()){p.zone.visible=true;p.walls.visible=true;p.walls.traverse(o=>{if(o.isMesh){o.material.transparent=true;o.material.opacity=.22;}});}}
function enter(index){active=index;$('tx-label').hidden=index!==6;$('rx-label').hidden=index!==6;const s=scenes[index];$('chapter').textContent=`0${index+1} / 07`;$('scale').textContent=s[2];$('title').innerHTML=s[3];$('subtitle').textContent=s[4];$('map').style.opacity=index<3?'1':'0';$('world').style.opacity=index>=3?'1':'0';$('signal').hidden=index<4;$('location-label').hidden=index<5;
 $('scene-note').textContent=index<2?'Land outlines · Natural Earth':index===2?'City / campus context · schematic':index===3?'Nucleus · existing floor-plan model':index===4?'Second floor · illustrative pressure estimate':index===5?'Yew first · Rowan / Hawthorn remain candidates':'Demo help request · no real emergency dispatch';
 for(const [i,b] of [...$('chapters').children].entries())b.setAttribute('aria-current',i===index?'step':'false');$('previous').disabled=index===0;$('next').disabled=index===6;
 resetBuilding();if(model&&index>=4)applyRoomFocus(model,'2');
 if(model&&index>=5){room.zone.material.color.setHex(0xefdab0);room.walls.traverse(o=>{if(o.isMesh){o.material.color.setHex(0xefdab0);o.material.opacity=.32;}});}
 if(model&&index===6){for(const [id,f] of model.floors)f.group.visible=id==='2';for(const [key,p] of model.roomParts){if(key!=='2/nuc-2-yew'){p.zone.visible=false;p.walls.visible=false;}}model.floors.get('2').architecture.root.visible=false;}
}
function update3d(dt){if(!renderer)return;const progress=Math.min(1,Math.max(0,(time-scenes[active][0])/10));
 if(active<=3){look.copy(centre);dest.copy(centre).add(new T.Vector3(83-10*progress,66,100-10*progress));}
 else if(active===4){look.copy(centre);look.y=10;dest.copy(look).add(new T.Vector3(64,82,85));}
 else if(active===5){look.copy(roomCenter).lerp(centre,.2);dest.copy(look).add(new T.Vector3(60,64,65));}
 else{look.copy(roomCenter).add(new T.Vector3(0,1,0));dest.copy(look).add(new T.Vector3(20-2*progress,16-2*progress,24-2*progress));}
 const smooth=reduced?1:1-Math.exp(-dt*1.1);cam.lerp(dest,smooth);target.lerp(look,smooth);camera.position.copy(cam);camera.lookAt(target);
 // Move the composition right to leave room for the narration; use vertical space on small screens.
 camera.setViewOffset(w,h,w<700?0:-w*.16,w<700?-h*.16:0,w,h);
 for(const f of model.floors.values())updateArchitecture(f.architecture,camera,target,active>=4);
 person.visible=active>=5;person.position.copy(roomCenter);if(active===6&&time>=100&&time<108&&!reduced)person.position.x+=Math.sin((time-100)*1.2)*1.7;
 rings.forEach((r,i)=>{r.visible=active===5;const v=((reduced?0:(time-74)*.45)+i*.25)%1;r.scale.setScalar(.2+v*7);r.material.opacity=(1-v)*.55;});
 links.forEach((line,i)=>{line.visible=active>=5;const c=roomCenter;const a=new T.Vector3(c.x-5,c.y+1,c.z+3);const b=person.position.clone().add(new T.Vector3(0,1,0));const z=active===5?new T.Vector3(c.x,c.y+4,c.z):new T.Vector3(c.x+5,c.y+1,c.z-3);if(active===5){a.copy(c).add(new T.Vector3(i-1,.6,0));b.copy(c).add(new T.Vector3(i-1,4,0));z.copy(c).add(new T.Vector3(i-1,.6,.4));}else b.z+=(i-1)*.5;line.geometry.setFromPoints([a,b,z]);line.material.opacity=reduced?.45:.25+.2*Math.sin(time*4+i);});
 devices.forEach((device,i)=>{device.visible=active===6;const node=$(i?'rx-label':'tx-label');node.hidden=active!==6;const p=device.position.clone().project(camera);node.style.left=`${(p.x*.5+.5)*w}px`;node.style.top=`${(-p.y*.5+.5)*h}px`;});
 const screen=roomCenter.clone().add(new T.Vector3(0,5,0)).project(camera);$('location-label').style.left=`${(screen.x*.5+.5)*w}px`;$('location-label').style.top=`${(-screen.y*.5+.5)*h}px`;
 if(active>=5)room.zone.material.color.setHex(!reduced&&Math.sin(time*2)>.3?0xf7e4bd:0xefdab0);
 renderer.render(world,camera);
}
function signal(){if(active<4)return;const motion=active===6,echo=active===5,phase=motion?(time<100?'baseline':time<108?'motion':'alert'):'',effectTime=reduced?0:time;let d='';for(let i=0;i<260;i++){const v=motion?Math.sin(i*.19+effectTime*4)*Math.sin(i*.055-effectTime)*(phase==='motion'?20:3):echo?Math.sin(i*.7)*Math.exp(-i/55)*26+(Math.abs(i-85)<3?28:0):Math.sin(i*.018+effectTime)*3;d+=`${i?'L':'M'}${i} ${34-v} `;}$('signal-path').setAttribute('d',d);$('signal-label').textContent=motion?(phase==='alert'?'DEMO HELP REQUEST':'WI-FI AMPLITUDE · ILLUSTRATION'):echo?'CHIRP → REFLECTION → MATCH':'AIR PRESSURE → HEIGHT';$('signal-value').textContent=motion?(phase==='baseline'?'Still room · baseline':phase==='motion'?'Movement detected':'Second floor · Yew first'):echo?'01  Yew\n02  Rowan\n03  Hawthorn':'Second floor';$('signal-note').textContent=motion?(phase==='alert'?'Other candidates: Rowan / Hawthorn. No real notification sent.':'Motion changes the channel; it does not establish distress.'):echo?'Ranked candidates · not a confirmed room':'Illustrative trace · calibrated reference required';}
function go(t){time=Math.max(0,Math.min(120,t));const index=scenes.findLastIndex(s=>time>=s[0]);if(index!==active)enter(index);if(active===6){$('title').innerHTML=time>=108?'A place to<br>start looking.':scenes[6][3];$('subtitle').textContent=time>=108?'Second floor. Yew first; Rowan and Hawthorn remain candidates. Automatic fall detection and a real emergency-service link are future work.':scenes[6][4];}$('play').textContent=playing?'Pause':time>=120?'Replay story':'Play story';$('timeline').value=time;$('time').textContent=`${Math.floor(time/60)}:${String(Math.floor(time%60)).padStart(2,'0')} / 2:00`;}
function play(value){playing=value;$('play').textContent=playing?'Pause':time>=120?'Replay story':'Play story';}
scenes.forEach((s,i)=>{const b=document.createElement('button');b.textContent=`0${i+1} ${s[1]}`;b.onclick=()=>go(s[0]);$('chapters').append(b);});
$('play').onclick=()=>{if(time>=120)go(0);play(!playing);};$('restart').onclick=()=>{go(0);play(false);};$('previous').onclick=()=>go(scenes[Math.max(0,active-1)][0]);$('next').onclick=()=>go(scenes[Math.min(6,active+1)][0]);$('timeline').oninput=e=>{play(false);go(Number(e.target.value));};$('fullscreen').onclick=async()=>{try{if(document.fullscreenElement)await document.exitFullscreen();else await document.documentElement.requestFullscreen();}catch{error('Full screen is unavailable in this preview. Open the local URL in your browser.');}};
document.addEventListener('keydown',e=>{if(e.target.closest('input,select')||e.ctrlKey||e.altKey||e.metaKey)return;if(e.code==='Space'&&!e.target.closest('button,a,summary')){e.preventDefault();$('play').click();}if(e.key==='ArrowRight')$('next').click();if(e.key==='ArrowLeft')$('previous').click();});document.addEventListener('visibilitychange',()=>{if(document.hidden)play(false);last=performance.now();});
go(0);resize();function frame(now){const dt=Math.min((now-last)/1000,.06);last=now;if(playing){go(time+dt*Number($('speed').value));if(time>=120)play(false);}const index=Math.min(active,2),m=[...mapTargets[index]];if(active===2){const travel=Math.min(1,Math.max(0,(time-24)/11));m[0]+=( -3.174-m[0])*travel;m[1]+=(55.9225-m[1])*travel;m[2]=.24*Math.pow(.045/.24,travel);}const a=reduced?1:1-Math.exp(-dt*.7);const follow=reduced?1:1-Math.exp(-dt*3);mapCam.lon+=(m[0]-mapCam.lon)*follow;mapCam.lat+=(m[1]-mapCam.lat)*follow;mapCam.span=Math.exp(Math.log(mapCam.span)+(Math.log(m[2])-Math.log(mapCam.span))*a);if(active<3)drawMap();else update3d(dt);signal();requestAnimationFrame(frame);}requestAnimationFrame(frame);
