import {useEffect,useMemo,useRef} from 'react';
import {useFrame} from '@react-three/fiber';
import * as THREE from 'three';
import {SUPERNOVA_AT} from '../introTextFragments.js';
import {plasmaSeed,plasmaAlpha,PLASMA_GLSL,PLASMA_SECONDS} from '../supernovaPlasma.js';

const COUNT=192;
const vertexShader=`
attribute vec4 seed; attribute vec2 lift; attribute vec3 plume; varying vec3 vPlume;
uniform float pixelRatio; uniform float age;
${PLASMA_GLSL}
void main(){
  vPlume=plume;
  vec4 point=plasmaPoint(seed,lift,age);
  vec4 p=modelViewMatrix*vec4(point.xyz,1.0);
  gl_Position=projectionMatrix*p;
  gl_PointSize=min(160.0,point.w*260.0*pixelRatio/max(1.0,-p.z));
}`;
const fragmentShader=`
varying vec3 vPlume; uniform float opacity; uniform float age;
void main(){
  vec2 p=gl_PointCoord*2.0-1.0;
  float r=dot(p,p);
  float wisps=.72+.28*sin(p.x*7.0+p.y*5.0+age*2.0);
  float cloud=exp(-r*3.6)*(1.0-smoothstep(.3,1.0,r))*wisps;
  gl_FragColor=vec4(vPlume,cloud*opacity*.13);
  #include <tonemapping_fragment>
  #include <colorspace_fragment>
}`;

/** One small additive draw call; the trajectories are closed-form, so the GPU evaluates them from age alone. */
export default function SupernovaPlasma({playback,simulation}){
  const points=useRef(null),material=useRef(null);
  const geometry=useMemo(()=>{
    const g=new THREE.BufferGeometry(),seed=new Float32Array(COUNT*4),lift=new Float32Array(COUNT*2),plume=new Float32Array(COUNT*3),s={};
    for(let i=0;i<COUNT;i++){
      plasmaSeed(s,i);
      seed.set([s.phase,s.lane,s.jet,s.shell],i*4);lift.set([s.liftY,s.liftZ],i*2);
      plume.set(s.jet?[.34,.6,1]:[1,.42+(i%7)/14,.23+(i%5)/9],i*3);
    }
    // three.js takes the vertex count from position; the shader computes the actual points.
    g.setAttribute('position',new THREE.BufferAttribute(new Float32Array(COUNT*3),3));
    g.setAttribute('seed',new THREE.BufferAttribute(seed,4));
    g.setAttribute('lift',new THREE.BufferAttribute(lift,2));
    g.setAttribute('plume',new THREE.BufferAttribute(plume,3));
    return g;
  },[]);
  const uniforms=useMemo(()=>({opacity:{value:0},age:{value:0},pixelRatio:{value:1}}),[]);
  useEffect(()=>()=>geometry.dispose(),[geometry]);
  useFrame(state=>{
    const age=simulation.textAge-SUPERNOVA_AT;
    const active=!!playback?.active&&playback.supernova&&!playback.releasing&&age>=0&&age<PLASMA_SECONDS;
    points.current.visible=active;
    if(!active)return;
    material.current.uniforms.opacity.value=plasmaAlpha(age);
    material.current.uniforms.age.value=age;
    material.current.uniforms.pixelRatio.value=state.gl.getPixelRatio();
  });
  return <points ref={points} geometry={geometry} frustumCulled={false} visible={false} renderOrder={1}>
    <shaderMaterial ref={material} vertexShader={vertexShader} fragmentShader={fragmentShader} uniforms={uniforms} transparent depthWrite={false} blending={THREE.AdditiveBlending} />
  </points>;
}
