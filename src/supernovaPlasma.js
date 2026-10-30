import {smoothRange} from './introMotion.js';
export const PLASMA_SECONDS=2.8;

/** Constant per-particle parameters; the GPU receives them once as attributes. */
export function plasmaSeed(out,index){
  out.phase=(index*2.39996323)%(Math.PI*2);
  out.lane=((index*73)%191)/190;
  out.jet=index%4===0?(index%8===0?-1:1):0;
  out.shell=index%3===0?1:.65;
  out.liftY=Math.sin(index*1.7);out.liftZ=Math.cos(index*.9);
  return out;
}

export const plasmaAlpha=age=>smoothRange(0,.12,Math.max(0,age))*(1-smoothRange(.45,PLASMA_SECONDS,Math.max(0,age)));

/** Ejecta, a broad shock shell and two jets along the tilted disk's normal. */
export function plasmaPoint(out,index,age){
  const {phase,lane,jet,shell,liftY,liftZ}=plasmaSeed(out,index),travel=Math.max(0,age);
  if(jet){
    const reach=travel*(1.5+lane*2.1),width=.12+travel*.18;
    out.x=Math.cos(phase+travel)*width;
    out.y=jet*reach*.83+Math.sin(phase)*width;
    out.z=-jet*reach*.55+Math.cos(phase)*width;
  }else{
    const radius=(.25+travel*(.9+lane*1.4))*shell;
    out.x=Math.cos(phase+travel*.25)*radius;
    out.y=Math.sin(phase+travel*.25)*radius*.55+liftY*travel*.24;
    out.z=Math.sin(phase+travel*.25)*radius*.83+liftZ*travel*.22;
  }
  out.alpha=plasmaAlpha(travel);
  out.size=(jet?.65:1)*(1+travel*.75);
  return out;
}

/** GLSL port of plasmaPoint: seed = (phase, lane, jet side or 0, shell scale), lift = (liftY, liftZ). */
export const PLASMA_GLSL=`
vec4 plasmaPoint(vec4 seed,vec2 lift,float age){
  float travel=max(0.0,age);
  if(seed.z!=0.0){
    float reach=travel*(1.5+seed.y*2.1),width=.12+travel*.18;
    return vec4(cos(seed.x+travel)*width,seed.z*reach*.83+sin(seed.x)*width,-seed.z*reach*.55+cos(seed.x)*width,.65*(1.0+travel*.75));
  }
  float radius=(.25+travel*(.9+seed.y*1.4))*seed.w,turn=seed.x+travel*.25;
  return vec4(cos(turn)*radius,sin(turn)*radius*.55+lift.x*travel*.24,sin(turn)*radius*.83+lift.y*travel*.22,1.0+travel*.75);
}`;
