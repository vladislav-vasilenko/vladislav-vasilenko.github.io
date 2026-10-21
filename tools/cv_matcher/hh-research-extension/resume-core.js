(function (root) {
  "use strict";
  function normalize(value) { return String(value || "").normalize("NFKC").replace(/\s+/g, " ").trim(); }
  function matchingText(resume) {
    return [normalize(resume.title), ...resume.sections.map((section) =>
      `${normalize(section.heading)}\n${normalize(section.text)}`)].join("\n\n");
  }
  async function contentHash(resume) {
    const data = new TextEncoder().encode(matchingText(resume));
    const bytes = await crypto.subtle.digest("SHA-256", data);
    return [...new Uint8Array(bytes)].map((b) => b.toString(16).padStart(2, "0")).join("");
  }
  async function saveSnapshot(bundle, incoming, policy) {
    const definition = policy.resumes.find((resume) => resume.id === incoming.id);
    if (!definition || incoming.quality !== "full" || !incoming.title ||
      !incoming.sections?.some((s) => s.key === "experience" && normalize(s.text).length > 100)) {
      throw new Error("Резюме не распознано или прочитано не полностью. Старый снимок сохранён.");
    }
    const hash = await contentHash(incoming);
    const previous = bundle?.resumes?.find((resume) => resume.id === incoming.id);
    const unchanged = previous?.content_hash === hash;
    const snapshot = {...incoming, source_type:"hh", role: definition.role, source_url: definition.url,
      ...(incoming.import_origin||previous?.import_origin?{import_origin:incoming.import_origin||previous.import_origin}:{}),
      content_hash: hash, checked_at: incoming.captured_at,
      changed_at: unchanged ? previous.changed_at : incoming.captured_at,
      matching_text: matchingText(incoming)};
    return {changed: !unchanged, bundle: {...bundle,schema_version: 2, primary_id: policy.primary_id,
      exported_at: new Date().toISOString(), resumes: [
        ...(bundle?.resumes || []).filter((resume) => resume.id !== incoming.id), snapshot].map(r=>({...r,role:r.id===policy.primary_id?"primary":"secondary"}))}};
  }
  root.ResumeSync = {normalize, matchingText, contentHash, saveSnapshot};
})(globalThis);
