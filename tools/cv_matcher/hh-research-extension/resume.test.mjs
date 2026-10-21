import test from "node:test";
import assert from "node:assert/strict";
import {webcrypto} from "node:crypto";
globalThis.crypto ??= webcrypto;
import "./resume-core.js";

const primary = "a".repeat(38), secondary = "b".repeat(38);
const policy = {primary_id: primary, resumes: [{id: primary, role: "primary", url: `https://hh.ru/resume/${primary}`},
  {id: secondary, role: "secondary", url: `https://hh.ru/resume/${secondary}`}]};
const snapshot = (id = primary) => ({id, title: "Research Engineer", quality: "full", captured_at: "2026-10-14T08:00:00Z",
  sections: [{key: "experience", heading: "Опыт работы", text: "PyTorch Transformer training. ".repeat(8)},
    {key: "skills", heading: "Навыки", text: "Python PyTorch SFT"}]});

test("a fresh check updates time without creating a new content version", async () => {
  const first = await ResumeSync.saveSnapshot(null, snapshot(), policy);
  const second = await ResumeSync.saveSnapshot(first.bundle, {...snapshot(), captured_at: "2026-10-14T10:00:00Z"}, policy);
  assert.equal(second.changed, false);
  assert.equal(second.bundle.resumes[0].changed_at, snapshot().captured_at);
  assert.equal(second.bundle.resumes[0].checked_at, "2026-10-14T10:00:00Z");
  assert.equal(second.bundle.resumes.length, 1);
});
test("a resume edit creates a new version, while whitespace-only edits do not", async () => {
  const first = await ResumeSync.saveSnapshot(null, snapshot(), policy);
  const same = snapshot(); same.sections[1].text = "Python   PyTorch\nSFT";
  assert.equal((await ResumeSync.saveSnapshot(first.bundle, same, policy)).changed, false);
  const changed = snapshot(); changed.sections[1].text += " diffusion";
  assert.equal((await ResumeSync.saveSnapshot(first.bundle, changed, policy)).changed, true);
});
test("a reserve snapshot never replaces the configured primary", async () => {
  const first = await ResumeSync.saveSnapshot(null, snapshot(), policy);
  const second = await ResumeSync.saveSnapshot(first.bundle, snapshot(secondary), policy);
  assert.equal(second.bundle.primary_id, primary);
  assert.equal(second.bundle.resumes.length, 2);
  assert.equal(second.bundle.resumes.find((r) => r.id === secondary).role, "secondary");
});
test("unknown, blocked or incomplete resumes are rejected", async () => {
  for (const invalid of [snapshot("c".repeat(38)), {...snapshot(), quality: "partial"}, {...snapshot(), sections: []}]) {
    await assert.rejects(ResumeSync.saveSnapshot(null, invalid, policy));
  }
});
