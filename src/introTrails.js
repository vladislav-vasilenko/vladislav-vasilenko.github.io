/** One real cube per trail; patch averages are not trajectories in multi-arm fields. */
export function trailTokens(patchOf, patches) {
  const tokens = new Int32Array(patches).fill(-1);
  for(let i=0;i<patchOf.length;i++)if(tokens[patchOf[i]]<0)tokens[patchOf[i]]=i;
  return tokens;
}

/** The newest endpoint follows its cube every render, even between history samples. */
export function anchorTrailHeads(out, positions, tokens, historyLength) {
  for(let k=0;k<tokens.length;k++){
    const source=tokens[k]*3, end=(k*(historyLength-1)+historyLength-2)*6+3;
    out[end]=positions[source];out[end+1]=positions[source+1];out[end+2]=positions[source+2];
  }
}

export function playbackInteraction(pointerSpeed,touchBoost,active,release) {
  const motion=active?Math.min(1,Math.max(0,pointerSpeed)*.55+Math.max(0,touchBoost)*.5):1;
  return motion*(1-Math.min(1,Math.max(0,release))*.7);
}
