import {smoothRange} from './introMotion.js';
export const PLASMA_SECONDS=2.8;

/** Ejecta, a broad shock shell and two jets along the tilted disk's normal. */
export function plasmaPoint(out,index,age){
  const phase=index*2.39996323,lane=((index*73)%191)/190;
  const travel=Math.max(0,age),jet=index%4===0;
  if(jet){
    const side=index%8===0?-1:1,reach=travel*(1.5+lane*2.1),width=.12+travel*.18;
    out.x=Math.cos(phase+travel)*width;
    out.y=side*reach*.83+Math.sin(phase)*width;
    out.z=-side*reach*.55+Math.cos(phase)*width;
  }else{
    const radius=(.25+travel*(.9+lane*1.4))*(index%3===0?1:.65);
    out.x=Math.cos(phase+travel*.25)*radius;
    out.y=Math.sin(phase+travel*.25)*radius*.55+Math.sin(index*1.7)*travel*.24;
    out.z=Math.sin(phase+travel*.25)*radius*.83+Math.cos(index*.9)*travel*.22;
  }
  out.alpha=smoothRange(0,.12,travel)*(1-smoothRange(.45,PLASMA_SECONDS,travel));
  out.size=(jet?.65:1)*(1+travel*.75);
  return out;
}
