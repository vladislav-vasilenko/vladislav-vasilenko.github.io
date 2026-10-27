import {useEffect,useMemo,useRef} from 'react';
import {useFrame} from '@react-three/fiber';
import * as THREE from 'three';
import {SUPERNOVA_AT} from '../introTextFragments.js';
import {plasmaPoint,PLASMA_SECONDS} from '../supernovaPlasma.js';

const COUNT=192;
const vertexShader=`
attribute vec4 plume; varying vec4 vPlume;
uniform float pixelRatio;
void main(){
  vPlume=plume;
  vec4 p=modelViewMatrix*vec4(position,1.0);
  gl_Position=projectionMatrix*p;
  gl_PointSize=min(160.0,plume.a*260.0*pixelRatio/max(1.0,-p.z));
}`;
const fragmentShader=`
varying vec4 vPlume; uniform float opacity; uniform float age;
void main(){
  vec2 p=gl_PointCoord*2.0-1.0;
  float r=dot(p,p);
  float wisps=.72+.28*sin(p.x*7.0+p.y*5.0+age*2.0);
  float cloud=exp(-r*3.6)*(1.0-smoothstep(.3,1.0,r))*wisps;
  gl_FragColor=vec4(vPlume.rgb,cloud*opacity*.13);
  #include <tonemapping_fragment>
  #include <colorspace_fragment>
}`;

/** One small additive draw call; the gas fades before the portrait becomes readable. */
export default function SupernovaPlasma({playback,simulation}){
  const points=useRef(null),material=useRef(null);
  const geometry=useMemo(()=>{
    const g=new THREE.BufferGeometry();
    g.setAttribute('position',new THREE.BufferAttribute(new Float32Array(COUNT*3),3).setUsage(THREE.DynamicDrawUsage));
    g.setAttribute('plume',new THREE.BufferAttribute(new Float32Array(COUNT*4),4).setUsage(THREE.DynamicDrawUsage));
    return g;
  },[]);
  const uniforms=useMemo(()=>({opacity:{value:0},age:{value:0},pixelRatio:{value:1}}),[]);
  const scratch=useMemo(()=>({}),[]);
  useEffect(()=>()=>geometry.dispose(),[geometry]);
  useFrame(state=>{
    const age=simulation.textAge-SUPERNOVA_AT;
    const active=!!playback?.active&&playback.supernova&&!playback.releasing&&age>=0&&age<PLASMA_SECONDS;
    points.current.visible=active;
    if(!active)return;
    const position=geometry.attributes.position.array,plume=geometry.attributes.plume.array;
    for(let i=0;i<COUNT;i++){
      const p=plasmaPoint(scratch,i,age),ix=i*3,color=i*4,jet=i%4===0;
      position[ix]=p.x;position[ix+1]=p.y;position[ix+2]=p.z;
      plume[color]=jet?.34:1;plume[color+1]=jet?.6:.42+(i%7)/14;plume[color+2]=jet?1:.23+(i%5)/9;plume[color+3]=p.size;
    }
    geometry.attributes.position.needsUpdate=true;geometry.attributes.plume.needsUpdate=true;
    material.current.uniforms.opacity.value=scratch.alpha;
    material.current.uniforms.age.value=age;
    material.current.uniforms.pixelRatio.value=state.gl.getPixelRatio();
  });
  return <points ref={points} geometry={geometry} frustumCulled={false} visible={false} renderOrder={1}>
    <shaderMaterial ref={material} vertexShader={vertexShader} fragmentShader={fragmentShader} uniforms={uniforms} transparent depthWrite={false} blending={THREE.AdditiveBlending} />
  </points>;
}
