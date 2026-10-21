import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from src.resume_source import CachedEmbeddings, content_hash, load_hh_resumes, search_hh_resumes, resume_chunks


class ResumeSourceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.policy = {"primary_id": "primary", "max_age_hours": 24, "secondary_min_advantage": .05,
                       "resumes": [{"id": "primary", "role": "primary"}, {"id": "reserve", "role": "secondary"}]}
        (self.root / "policy.json").write_text(json.dumps(self.policy))
        self.now = datetime(2026, 10, 14, 12, tzinfo=timezone.utc)

    def snapshot(self, rid="primary", checked="2026-10-14T11:00:00Z"):
        snapshot = {"id": rid, "title": "Research Engineer", "quality": "full", "checked_at": checked,
                    "sections": [{"key": "experience", "heading": "Опыт работы", "text": "PyTorch Transformer training. " * 8}]}
        snapshot["content_hash"] = content_hash(snapshot)
        return snapshot

    def load(self, resumes):
        (self.root / "bundle.json").write_text(json.dumps({"resumes": resumes}))
        return load_hh_resumes(self.root / "bundle.json", self.root / "policy.json", now=self.now)

    def test_missing_or_stale_primary_cannot_fall_back_to_reserve(self):
        for resumes in [[self.snapshot("reserve")], [self.snapshot(checked="2026-10-12T11:00:00Z"), self.snapshot("reserve")]]:
            with self.assertRaises(ValueError):
                self.load(resumes)

    def test_stale_reserve_is_skipped_and_text_edits_invalidate_version(self):
        result = self.load([self.snapshot(), self.snapshot("reserve", "2026-10-12T11:00:00Z")])
        self.assertEqual(len(result["resumes"]), 1)
        modified = self.snapshot(); modified["sections"][0]["text"] += " diffusion"
        with self.assertRaises(ValueError):
            self.load([modified])

    def test_future_and_timezone_free_check_dates_are_rejected(self):
        for checked in ["2026-10-15T11:00:00Z", "2026-10-14T11:00:00"]:
            with self.assertRaises(ValueError):
                self.load([self.snapshot(checked=checked)])

    def test_embeddings_are_shared_and_only_changed_chunks_are_recomputed(self):
        class Backend:
            model = "fixture"
            def __init__(self): self.calls = []
            def embed_documents(self, texts):
                self.calls.append(texts)
                return [[float(len(text)), 1.] for text in texts]
        backend = Backend()
        cache = CachedEmbeddings(backend, self.root / "embeddings")
        cache.embed_documents(["PyTorch training", "SFT", "SFT"])
        cache.embed_documents(["PyTorch   training", "SFT", "DiT"])
        self.assertEqual([len(call) for call in backend.calls], [2, 1])
        CachedEmbeddings(backend, self.root / "embeddings", "new-weights").embed_documents(["SFT"])
        self.assertEqual(len(backend.calls), 3)

    def test_primary_is_preferred_unless_reserve_has_clear_advantage(self):
        primary, reserve = self.snapshot(), self.snapshot("reserve")
        reserve["title"] = "Reserve Engineer"
        class DB:
            def search_similar_vacancies_multi_chunk(self, chunks, **kwargs):
                distance = .47 if chunks[0] == "Reserve Engineer" else .5
                return [{"id": "job", "distance": distance}]
        bundle = {"primary": primary, "resumes": [primary, reserve], "policy": self.policy}
        self.assertEqual(search_hh_resumes(DB(), bundle, include_secondary=True)[0]["_resume"]["id"], "primary")
        self.policy["secondary_min_advantage"] = .02
        self.assertEqual(search_hh_resumes(DB(), bundle, include_secondary=True)[0]["_resume"]["id"], "reserve")

    def test_long_experience_keeps_later_evidence_in_separate_chunks(self):
        resume = self.snapshot()
        resume['sections'][0]['text'] = 'Transformer experiments ' * 700 + 'FINAL_AUDIO_EVIDENCE'
        chunks = resume_chunks(resume)
        self.assertGreater(len(chunks), 10)
        self.assertIn('FINAL_AUDIO_EVIDENCE', chunks[-1])
        self.assertTrue(all(len(c) < 1020 for c in chunks))


if __name__ == "__main__":
    unittest.main()

class GeneralResumeBundleTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.now=datetime(2026,10,14,12,tzinfo=timezone.utc)
    def document(self, source='google_docs'):
        rid='gdoc_1234567890ABC' if source=='google_docs' else 'file_'+'a'*64
        r={'id':rid,'title':'Research CV','source_type':source,'source_url':'https://docs.google.com/document/d/1234567890ABC/edit' if source=='google_docs' else '', 'quality':'full','checked_at':'2026-10-14T11:00:00Z','reviewed_at':'2026-10-14T11:00:00Z','file_hash':'a'*64,'sections':[{'key':'document','heading':'Резюме','text':'PyTorch Transformer SFT '*8}]}
        r['content_hash']=content_hash(r);return r
    def load(self, rows, primary):
        path=self.root/'resumes.json';path.write_text(json.dumps({'schema_version':2,'primary_id':primary,'resumes':rows}))
        return load_hh_resumes(path,self.root/'missing-policy.json',now=self.now)
    def test_google_docs_can_be_primary_without_private_hh_policy(self):
        r=self.document();self.assertEqual(self.load([r],r['id'])['primary']['id'],r['id'])
    def test_files_do_not_expire_but_docs_require_a_recent_read(self):
        r=self.document('file');r['checked_at']='2025-01-01T00:00:00Z';self.assertEqual(self.load([r],r['id'])['primary']['source_type'],'file')
        d=self.document();d['checked_at']='2025-01-01T00:00:00Z'
        with self.assertRaises(ValueError):self.load([d],d['id'])
    def test_html_login_wrong_origin_unreviewed_and_edited_hash_are_not_accepted(self):
        for change in [{'source_url':'https://evil.test/document/d/1234567890ABC/edit'},{'reviewed_at':None},{'quality':'needs_review'},{'content_hash':'wrong'}]:
            r={**self.document(),**change}
            with self.assertRaises(ValueError):self.load([r],r['id'])
    def test_all_valid_hh_resumes_are_accepted_with_roles_from_selected_primary(self):
        rows=[]
        for char in 'abcdef':
            r={'id':char*38,'title':'Research','source_type':'hh','source_url':'https://hh.ru/resume/'+char*38,'quality':'full','checked_at':'2026-10-14T11:00:00Z','sections':[{'key':'experience','heading':'Опыт','text':'PyTorch ML '*30}]};r['content_hash']=content_hash(r);rows.append(r)
        result=self.load(rows,rows[0]['id']);self.assertEqual(len(result['resumes']),6);self.assertEqual(sum(r['role']=='primary' for r in result['resumes']),1)
