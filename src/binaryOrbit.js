// A directed orbital field for the intro, rather than an unstable N-body simulation.
// Looking 30° above the orbital plane gives visible near/far passes.
const ELEVATION = Math.PI / 6;
const SCREEN_DEPTH = Math.sin(ELEVATION);
const WORLD_DEPTH = Math.cos(ELEVATION);

/** Start outside both side edges, above the wells, with inward/downward momentum. */
export function asteroidEntrance(out, index, patch, view) {
  const side = patch % 2 ? 1 : -1;
  const lane = ((index * 37) % 31) / 30;
  out.x = side * (view.halfWidth + .35 + lane * .5);
  out.y = view.halfHeight * (.7 + lane * .7);
  out.z = index % 11 === 0 ? view.cameraZ * .12 : -.2;
  out.vx = -side * (1.6 + lane);
  out.vy = -.8 - lane * .8;
  out.spinX = (index % 2 ? -1 : 1) * (2.5 + lane * 2);
  out.spinZ = -side * (3 + lane * 2);
  return out;
}

/** Measured UI centres remain stationary and tappable while their orbital planes precess. */
export function binaryOrbitLayout(out, view, anchors) {
  const vertical = view.width <= 900;
  const main = anchors?.main || {x: view.width * (vertical ? .5 : .31), y: view.height * (vertical ? .31 : .46), width: view.width * .5, height: 130};
  const links = anchors?.links || {x: view.width * (vertical ? .5 : .77), y: view.height * (vertical ? .66 : .5), width: 280, height: 100};
  const units = view.halfHeight * 2 / view.height;
  out.mainX = (main.x - view.width / 2) * units;
  out.mainY = (view.height / 2 - main.y) * units;
  out.linksX = (links.x - view.width / 2) * units;
  out.linksY = (view.height / 2 - links.y) * units;
  const dx = out.linksX - out.mainX, dy = out.linksY - out.mainY;
  const distance = Math.max(.2, Math.hypot(dx, dy));
  out.ux = dx / distance; out.uy = dy / distance;
  out.px = -out.uy; out.py = out.ux;
  out.major = distance * .6; out.minor = distance * .4;
  out.bridgeX = out.mainX + dx * .6;
  out.bridgeY = out.mainY + dy * .6;
  const crossSpace = (Math.abs(out.px) * view.halfWidth + Math.abs(out.py) * view.halfHeight) * .86;
  const cross = (box, radius) => Math.min(crossSpace, Math.max(radius * .56,
    (Math.abs(out.px) * box.width / 2 + Math.abs(out.py) * box.height / 2 + 24) * units)) / SCREEN_DEPTH;
  out.majorCross = cross(main, out.major);
  out.minorCross = cross(links, out.minor);
  out.cameraZ = view.cameraZ;
  return out;
}

/** Clockwise local rings share a continuous infinity-shaped transfer stream. */
export function binaryOrbit(out, index, patch, layout, time = 0) {
  const band = .91 + ((index * 37) % 17) / 16 * .18;
  const jitter = ((index * 53) % 19) / 18 * .07 - .035;
  const phase = patch * 2.39996323 + time * .14 + jitter;
  const precession = -time * .018;
  let a, b, cx, cy;
  if (patch % 10 >= 7) {
    // These asteroids alternate between wells instead of remaining in a closed ring.
    const s = Math.sin(phase);
    a = (layout.major + layout.minor) * s + (layout.minor - layout.major) * s * s;
    b = ((layout.majorCross + layout.minorCross) / 2 + (layout.minorCross - layout.majorCross) / 2 * s) * Math.sin(2 * phase);
    const focus = s < 0 ? -layout.major : layout.minor;
    const turn = precession * s * s; // Preserve the crossing point during precession.
    const offset = a - focus;
    a = focus + offset * Math.cos(turn) - b * Math.sin(turn);
    b = offset * Math.sin(turn) + b * Math.cos(turn);
    cx = layout.bridgeX; cy = layout.bridgeY;
  } else {
    const major = patch % 10 < 5;
    const radius = major ? layout.major : layout.minor;
    const cross = major ? layout.majorCross : layout.minorCross;
    const x = radius * Math.cos(phase), y = -cross * Math.sin(phase);
    a = x * Math.cos(precession) - y * Math.sin(precession);
    b = x * Math.sin(precession) + y * Math.cos(precession);
    cx = major ? layout.mainX : layout.linksX;
    cy = major ? layout.mainY : layout.linksY;
  }
  a *= band; b *= band;
  out.x = cx + layout.ux * a + layout.px * b * SCREEN_DEPTH;
  out.y = cy + layout.uy * a + layout.py * b * SCREEN_DEPTH;
  out.z = Math.min(layout.cameraZ * .55, b * WORLD_DEPTH) - .1;
  const near = Math.max(0, out.z / layout.cameraZ);
  out.scale = .65 + (index % 9) / 8 * .35 + near * (patch % 11 === 0 ? 1.8 : .5);
  return out;
}
