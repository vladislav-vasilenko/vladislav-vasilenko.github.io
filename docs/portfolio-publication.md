# Public portfolio: local sources, publication and rendering

The local Career Intelligence service is the source of the reviewed public projection. SQLite, credentials, applications, internal Luna/Terra assessments, source documents and private notes stay local. GitHub Pages receives only the allowlisted `public/hh-experience.json`; Actions builds `dist/` without opening the local database.

## Sources and controls

Resume → **Портфолио · введение, опыт HH и GitHub** → **Предпросмотр и редактирование**.

- Title and work history come from the primary full HH resume selected in the local service. Source links point to that HH resume.
- The introduction defaults to HH “About”. A reviewed RU/EN portfolio draft can override it. A changed source invalidates the draft until reviewed again.
- Public visuals have a separate opt-in selector, trajectory, sample and JSON preview/download. Changes require owner review. Auto-publication checks every five minutes while the local service runs.
- “Current direction” publishes the generic track, up to five focus topics, public labs already checked through GitHub, and stage labels. It omits private goals, target companies, criteria notes and evidence identifiers.
- Confirmed practical skills require an owner-confirmed project/research/professional result with a public GitHub link. Studying is separate. Repository existence or activity does not prove authorship or proficiency.
- Market charts show an observed sample, grouped cosine coordinates rounded to 0.01 and category/completeness totals. The public alluvial diagram shows sample composition, not the personal application funnel. No vacancy/employer identifiers, CRM, raw quotations or detailed fit scores are published.

## Public website

Default is a quiet overview; full CV retains the text and export. Appearance changes are client-side and preserve the same facts. Telegram follows Email in the contact row. Layouts wrap on narrow screens; larger charts scroll inside their own region.

The optional 3D intro has one central resume button and GitHub, LinkedIn, Email and Telegram links. The intro Email link uses `mr.vasilenko.vlad@yandex.ru` in both languages. Intro typography follows the page language; explicit `?lang=en`, `?lang=ru` or `/ru/` overrides the browser's preferred language. The English navigation link keeps an explicit language choice. EN/RU intro names and button labels are also prerendered.

Clicking the resume button assembles the portrait, holds it briefly, releases its grid springs and drops the cubes onto a temporary impact plane. Playback waits for the simulated portrait to settle, then for actual first contacts and at least eight rebound frames spanning 0.6 simulation seconds; fixed wall-clock delays cannot skip the fall on a slow phone. First impacts add a lateral impulse; subsequent bounces lose energy. The floor also resolves cubes already below it after a slow frame or a resize. When the controls span the screen center, their measured height reserves 40 px above the panel for visible impacts. The resume then scrolls into view as the plane lowers. Wheel/touch scrolling, navigation keys or the Stop button cancel playback. Manual scrolling remains available throughout. This is a visual illustration, not an actual model inference run.

Latent trajectories are always drawn with the scene. With gravity off, noise patches follow a slow elliptical orbit around the empty center, leaving the screen corners open. Gravity and color are accessible switches in a translucent glass panel; contact buttons use the same glass treatment with reduced-transparency fallbacks. Background motion is slower than cursor-triggered scattering. Manual handover moves remaining tokens to the margins, and a viewport mask excludes the resume column even if a fast scroll outruns the simulation. The canvas stops after handover. The resume rises as a white sheet with a rounded top edge; no gray transition gradient is used. Full CV, reduced-motion and print modes omit the intro.

Build prerenders semantic EN `/` and RU `/ru/` documents using the same renderer and validated public snapshot. Canonicals, reciprocal hreflang, sitemap, description, social previews and factual ProfilePage/Person metadata are generated. This makes content available without JavaScript; interactive focus/theme controls enhance it afterward.

Reference: [Google profile page markup](https://developers.google.com/search/docs/appearance/structured-data/profile-page), [localized versions](https://developers.google.com/search/docs/specialty/international/localized-versions), [Yandex indexing](https://yandex.com/support/webmaster/en/robot-workings/robot). Search Console/Webmaster ownership and sitemap submission remain account-owner steps; no search placement is guaranteed.

## PWA and offline behavior

Bilingual manifests share one app identity. Supported browsers offer installation; Safari users can add the page to the Home Screen. A build-versioned service worker caches only an explicit same-origin list of public pages, snapshot, compiled assets and icons. It does not intercept private localhost APIs, arbitrary resources, POST requests or database files. Public pages and snapshot use network-first with offline fallback. Updates are activated through a visible user action; a reading session is not forcibly reloaded.

Verification includes bilingual non-JavaScript rendering, title replacement, escaping, public projection privacy boundaries, totals, offline navigation, cache exclusions and icon sizes. Real phone hardware / every mobile browser is not covered by these automated checks.
