type BatteryState = EventTarget & {level: number; charging: boolean};
type Connection = EventTarget & {saveData?: boolean};
type PowerNavigator = Navigator & {getBattery?: () => Promise<BatteryState>; connection?: Connection};
type PowerReason = 'reduced-motion' | 'save-data' | 'low-battery' | null;

export function introPowerReason(reducedMotion: boolean, saveData: boolean, battery?: {level: number; charging: boolean}): PowerReason {
  if (reducedMotion) return 'reduced-motion';
  if (saveData) return 'save-data';
  if (battery && Number.isFinite(battery.level) && battery.level >= 0 && battery.level <= .2 && battery.charging === false) return 'low-battery';
  return null;
}

/** Unknown/blocked battery data is not low battery. All signals stay on this device. */
export function watchIntroPower(nav: Navigator, motion: MediaQueryList, onDisable: (reason: Exclude<PowerReason, null>) => void): {ready: Promise<void>; dispose(): void} {
  const device = nav as PowerNavigator;
  let battery: BatteryState | undefined;
  let disposed = false;
  const dispose = () => {
    disposed = true;
    motion.removeEventListener('change', update);
    device.connection?.removeEventListener('change', update);
    battery?.removeEventListener('levelchange', update);
    battery?.removeEventListener('chargingchange', update);
  };
  const update = () => {
    const reason = introPowerReason(motion.matches, device.connection?.saveData === true, battery);
    if (!disposed && reason) { onDisable(reason); dispose(); }
  };
  motion.addEventListener('change', update);
  device.connection?.addEventListener('change', update);
  update();
  if (disposed || typeof device.getBattery !== 'function') return {ready: Promise.resolve(), dispose};
  const check = Promise.resolve().then(() => device.getBattery!()).then(value => {
    if (disposed) return;
    battery = value;
    battery.addEventListener('levelchange', update);
    battery.addEventListener('chargingchange', update);
    update();
  }).catch(() => {/* Unsupported or policy-blocked: keep the normal reading path. */});
  let timer: ReturnType<typeof setTimeout> | undefined;
  const ready = Promise.race([check, new Promise<void>(resolve => {timer = setTimeout(resolve, 200);})])
    .finally(() => {if (timer !== undefined) clearTimeout(timer);});
  return {ready, dispose};
}
