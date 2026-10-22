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

Build prerenders semantic EN `/` and RU `/ru/` documents using the same renderer and validated public snapshot. Canonicals, reciprocal hreflang, sitemap, description, social previews and factual ProfilePage/Person metadata are generated. This makes content available without JavaScript; interactive focus/theme controls enhance it afterward.

Reference: [Google profile page markup](https://developers.google.com/search/docs/appearance/structured-data/profile-page), [localized versions](https://developers.google.com/search/docs/specialty/international/localized-versions), [Yandex indexing](https://yandex.com/support/webmaster/en/robot-workings/robot). Search Console/Webmaster ownership and sitemap submission remain account-owner steps; no search placement is guaranteed.

## PWA and offline behavior

Bilingual manifests share one app identity. Supported browsers offer installation; Safari users can add the page to the Home Screen. A build-versioned service worker caches only an explicit same-origin list of public pages, snapshot, compiled assets and icons. It does not intercept private localhost APIs, arbitrary resources, POST requests or database files. Public pages and snapshot use network-first with offline fallback. Updates are activated through a visible user action; a reading session is not forcibly reloaded.

Verification includes bilingual non-JavaScript rendering, title replacement, escaping, public projection privacy boundaries, totals, offline navigation, cache exclusions and icon sizes. Real phone hardware / every mobile browser is not covered by these automated checks.
