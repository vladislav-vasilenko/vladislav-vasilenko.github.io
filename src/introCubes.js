/**
 * Cube transforms are composed on the GPU from the simulation's own position, Euler XYZ rotation
 * and scale arrays, so the CPU neither builds 1200 matrices nor uploads 16 floats per cube.
 */
const PARS = `
attribute vec3 cubePosition; attribute vec3 cubeRotation; attribute float cubeScale;
mat3 cubeBasis(vec3 r){
  vec3 c=cos(r), s=sin(r);
  return mat3(c.y*c.z, c.x*s.z+s.x*c.z*s.y, s.x*s.z-c.x*c.z*s.y,
    -c.y*s.z, c.x*c.z-s.x*s.y*s.z, s.x*c.z+c.x*s.y*s.z,
    s.y, -s.x*c.y, c.x*c.y);
}
`;

export function cubeTransformMaterial(shader) {
  shader.vertexShader = PARS + shader.vertexShader
    .replace('#include <beginnormal_vertex>', '#include <beginnormal_vertex>\nobjectNormal = cubeBasis(cubeRotation) * objectNormal;')
    .replace('#include <begin_vertex>', '#include <begin_vertex>\ntransformed = cubeBasis(cubeRotation) * (transformed * cubeScale) + cubePosition;');
}
