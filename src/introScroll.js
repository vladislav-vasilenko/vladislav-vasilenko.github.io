/** Reserve a visible scroll interval for the fall before the resume enters the viewport. */
export function portraitScrollEnd(trackBottom, height) {
  const range = Math.max(0, trackBottom - height);
  return Math.max(0, range - Math.min(height * 0.85, range * 0.55));
}
