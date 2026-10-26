/** A filled navigation marker; the link text remains the accessible label. */
export function directionArrow(direction:'right'|'left'|'up'|'down'|'external'='right'):string {
 return `<span class="direction-arrow direction-arrow--${direction}" aria-hidden="true">➤</span>`;
}
