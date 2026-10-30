import {hash, normal, smoothRange} from './introMotion.js';

const TAU = Math.PI * 2;
export const COSMIC_ORDER = ['solar','saturn','galaxy'];
export const COSMIC_DURATIONS = {solar:14,saturn:7,galaxy:21};
export const ACCRETION_SECONDS = 4.6;

/** A wide offscreen spiral accelerates inward before the solar orbits take over. */
export function initialAccretion(out,index,view,seconds) {
  const delay=hash(index+37)*.7,q=smoothRange(0,3.6,Math.max(0,seconds-delay));
  const radius=(2.35+hash(index+11)*.7)*(1-.94*q);
  const angle=hash(index+17)*TAU-(seconds*.35+seconds*seconds*.22);
  out.x=Math.cos(angle)*view.halfWidth*radius;
  out.y=view.halfHeight*.34+Math.sin(angle)*view.halfHeight*radius*.72;
  out.z=Math.sin(angle)*radius*.7-1.3*q;
  out.scale=.64+hash(index+41)*.22;
  return out;
}

export function astronomySequence(out,seconds) {
  const elapsed=Math.max(0,seconds),lap=elapsed%42;
  const step=lap<14?0:lap<21?1:2,start=step===0?0:step===1?14:21;
  out.id=COSMIC_ORDER[step];out.previous=COSMIC_ORDER[(step+2)%3];
  out.mix=elapsed<14?1:smoothRange(0,1.6,lap-start);
  return out;
}

function project(out,x,y,z,view) {
  out.x=x;out.y=view.halfHeight*.34+y*.63-z*.78;out.z=y*.78+z*.63;
  return out;
}

/** An uneven stellar disk: broad logarithmic arms, a thick bulge and a sparse halo. */
export function galaxyPoint(out,index,view,seconds) {
  const extent=Math.min(view.halfWidth*1.12,view.halfHeight*.72),star=galaxyStar(index);
  const radius=extent*star.radius,angle=star.angle-seconds*star.rate;
  project(out,Math.cos(angle)*radius,Math.sin(angle)*radius,extent*star.thickness,view);
  out.scale=star.scale;out.r=star.tone[0];out.g=star.tone[1];out.b=star.tone[2];out.glow=star.glow;
  return out;
}

// A star's shape in extent units never changes; only the disk's rotation is evaluated per frame.
const galaxyStars=[];
function galaxyStar(index) {
  if(galaxyStars[index])return galaxyStars[index];
  const u=hash(index+17),v=hash(index+53),core=index%7<2,halo=index%29===0;
  let radius,angle,thickness;
  if(core){
    radius=.24*Math.cbrt(u);angle=v*TAU;
    thickness=normal(index+31)*.07*(1-radius);
  } else {
    radius=.15+Math.sqrt(u)*.85;
    // Six lanes with variable thickness, spurs and gaps, rather than solid spiral tubes.
    angle=(index%6)*TAU/6+Math.log(.12+radius)*1.8+normal(index+91)*(.08+.19*u);
    if(index%11===0)angle+=normal(index+29)*.48;
    thickness=normal(index+71)*(halo?.19:.018);
  }
  const bright=index%19===0, dust=!core&&index%9===0;
  const star={radius,angle,thickness,rate:.045+.025*(1-radius),
    scale:bright?.39:core?.16+v*.14:.12+v*.15,
    tone:dust?[.23,.16,.13]:core?[1,.73,.35]:bright?[.83,.91,1]:[.28+v*.18,.46+v*.17,.83],
    glow:dust?0:core?.28:bright?.30:.07};
  if(Number.isInteger(index)&&index>=0)galaxyStars[index]=star;
  return star;
}

// Actual integer lattice voxels make the planets solid, with a deliberately cubic surface.
const sphere=[];
for(let x=-4;x<=4;x++)for(let y=-4;y<=4;y++)for(let z=-4;z<=4;z++){
  const r=Math.hypot(x,y,z);if(r<=4.35&&r>=3.05)sphere.push([x/4.35,y/4.35,z/4.35]);
}
function voxel(out,index,count,radius,spin){
  const p=sphere[Math.floor(index*sphere.length/count)%sphere.length];
  out.x=(p[0]*Math.cos(spin)+p[2]*Math.sin(spin))*radius;
  out.y=p[1]*radius;out.z=(-p[0]*Math.sin(spin)+p[2]*Math.cos(spin))*radius;
  out.scale=radius*.255/.088;
  return out;
}
const PLANETS=[[.65,.59,.5],[.98,.72,.38],[.2,.58,1],[.9,.30,.12],[.85,.65,.46],[.9,.79,.53],[.39,.85,.89],[.24,.38,1]];

export function astronomyPoint(out,index,view,seconds,id) {
  if(id==='galaxy')return galaxyPoint(out,index,view,seconds);
  const extent=Math.min(view.halfWidth*.94,view.halfHeight*.65);
  let x,y,z,scale,tone,glow=0;
  if(id==='solar'){
    if(index<240){
      voxel(out,index,240,extent*.12,seconds*.18);
      x=out.x;y=out.z;z=out.y;scale=out.scale;tone=[1,.64+hash(index)*.22,.12];glow=.6;
    }else if(index<560){
      const planet=Math.floor((index-240)/40),n=(index-240)%40;
      const radius=extent*(.22+planet*.105),angle=planet*1.73-seconds*.23/(.55+planet*.17)**1.5;
      voxel(out,n,40,extent*(planet<4?.022+planet*.005:.05-(planet-4)*.004),seconds*.3);
      x=radius*Math.cos(angle)+out.x;y=radius*Math.sin(angle)+out.z;z=out.y;scale=out.scale;tone=PLANETS[planet];
    }else if(index<1040){
      const planet=Math.floor((index-560)/60),n=(index-560)%60;
      const radius=extent*(.22+planet*.105),angle=n/60*TAU;
      x=radius*Math.cos(angle);y=radius*Math.sin(angle);z=0;scale=.10;tone=[.18,.26,.38];glow=.05;
    }else{
      const angle=hash(index)*TAU-seconds*.11,radius=extent*(.57+hash(index+1)*.045);
      x=radius*Math.cos(angle);y=radius*Math.sin(angle);z=normal(index+3)*.02;scale=.16;tone=[.47,.41,.34];
    }
  }else{
    if(index<430){
      voxel(out,index,430,extent*.28,seconds*.22);
      x=out.x;y=out.z;z=out.y*.91;scale=out.scale;
      const band=Math.sin(out.y/extent*115)*.06;tone=[.88+band,.71+band,.44+band];
    }else if(index<1080){
      const n=index-430,angle=hash(n+13)*TAU-seconds*.1;
      const radius=extent*(.37+hash(n+17)*.33),gap=radius/extent>.54&&radius/extent<.58;
      x=radius*Math.cos(angle);y=radius*Math.sin(angle);z=normal(n+29)*.007;
      scale=gap?.09:.22+hash(n+19)*.14;tone=gap?[.12,.1,.07]:[.77,.68,.5];
    }else{
      const moon=Math.floor((index-1080)/30),n=(index-1080)%30;
      const radius=extent*(.73+moon*.07),angle=moon*1.7-seconds*(.24-moon*.035);
      voxel(out,n,30,extent*(.025+moon*.006),seconds*.35);
      x=radius*Math.cos(angle)+out.x;y=radius*Math.sin(angle)+out.z;z=out.y+Math.sin(angle)*extent*.13;
      scale=out.scale;tone=moon===3?[.95,.58,.24]:[.65,.73,.82];
    }
  }
  project(out,x,y,z,view);out.scale=scale;out.r=tone[0];out.g=tone[1];out.b=tone[2];out.glow=glow;
  return out;
}

export const COSMIC_LABELS={
  ru:{solar:['Солнечная система','Солнце · 8 планет'],saturn:['Сатурн','Кольца · спутники'],galaxy:['Галактика','Ядро · диск · рукава']},
  en:{solar:['Solar system','Sun · 8 planets'],saturn:['Saturn','Rings · moons'],galaxy:['Galaxy','Bulge · disk · arms']},
};
