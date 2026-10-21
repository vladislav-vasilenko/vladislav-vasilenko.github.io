import base64
import io
import json
from pathlib import Path
import tempfile
import subprocess
import sys
import unittest
import zipfile
from xml.sax.saxutils import escape
from fastapi.testclient import TestClient
from pypdf import PdfWriter
from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject
from src.resume_files import extract_resume, _snappy
from resume_import_server import create_app

TEXT = 'Research Engineer PyTorch Transformer pre-training SFT diffusion reproducible experiments. ' * 4 + 'FINAL_EVIDENCE'

def archive(parts):
    out = io.BytesIO()
    with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as z:
        for name, data in parts.items(): z.writestr(name, data)
    return out.getvalue()

def varint(n):
    out = bytearray()
    while n > 127: out.append((n & 127) | 128); n >>= 7
    out.append(n); return bytes(out)

def field(n, value):
    return varint(n * 8) + varint(value) if isinstance(value, int) else varint(n * 8 + 2) + varint(len(value)) + value

def iwa(text):
    payload = field(1, 0) + field(3, text.encode())
    info = field(1, 2001) + field(3, len(payload))
    header = field(1, 1) + field(2, info)
    data = varint(len(header)) + header + payload
    # A raw Snappy literal with little-endian length.
    length = len(data) - 1
    size = max(1, (length.bit_length() + 7) // 8)
    raw = varint(len(data)) + bytes([(59 + size) << 2]) + length.to_bytes(size, 'little') + data
    return bytes([0]) + len(raw).to_bytes(3, 'little') + raw

def pdf(text=TEXT):
    writer = PdfWriter(); page = writer.add_blank_page(width=600, height=800)
    font = DictionaryObject({NameObject('/Type'): NameObject('/Font'), NameObject('/Subtype'): NameObject('/Type1'), NameObject('/BaseFont'): NameObject('/Helvetica')})
    page[NameObject('/Resources')] = DictionaryObject({NameObject('/Font'): DictionaryObject({NameObject('/F1'): writer._add_object(font)})})
    stream = DecodedStreamObject(); stream.set_data(f'BT /F1 10 Tf 10 700 Td ({text}) Tj ET'.encode())
    page[NameObject('/Contents')] = writer._add_object(stream)
    out = io.BytesIO(); writer.write(out); return out.getvalue()

class ResumeFilesTests(unittest.TestCase):
    def test_utf8_utf16_markdown_and_redaction(self):
        for suffix, data in [('.txt', TEXT.encode()), ('.md', ('# CV\n' + TEXT).encode('utf-16'))]:
            result = extract_resume(data, 'my-resume' + suffix)
            self.assertIn('FINAL_EVIDENCE', result['text']); self.assertEqual(result['quality'], 'needs_review')
            self.assertEqual(result['id'], 'file_' + result['file_hash'])
        result = extract_resume((TEXT + ' user@example.com +7 (999) 123-45-67').encode(), 'CV.txt')
        self.assertNotIn('example.com', result['text']); self.assertNotIn('999', result['text'])

    def test_docx_body_table_and_header_are_retained(self):
        ns = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
        data = archive({'word/document.xml': f'<w:document xmlns:w="{ns}"><w:body><w:p><w:r><w:t>{escape(TEXT)}</w:t></w:r></w:p><w:tbl><w:tr><w:tc><w:p><w:r><w:t>TABLE_EVIDENCE Русский текст</w:t></w:r></w:p></w:tc></w:tr></w:tbl></w:body></w:document>', 'word/header1.xml': f'<w:hdr xmlns:w="{ns}"><w:p><w:r><w:t>HEADER_EVIDENCE</w:t></w:r></w:p></w:hdr>'})
        result = extract_resume(data, 'CV.docx')
        for evidence in ['FINAL_EVIDENCE', 'TABLE_EVIDENCE Русский текст', 'HEADER_EVIDENCE']: self.assertIn(evidence, result['text'])

    def test_text_pdf_and_scan_rejection(self):
        self.assertIn('FINAL_EVIDENCE', extract_resume(pdf(), 'CV.pdf')['text'])
        with self.assertRaisesRegex(ValueError, 'OCR'): extract_resume(pdf(''), 'scan.pdf')

    def test_modern_and_legacy_pages_use_actual_text_not_preview(self):
        for parts in [{'Index/Document.iwa': iwa(TEXT + ' Текст опыта'), 'preview.jpg': b'not a document'}, {'Index.zip': archive({'Document.iwa': iwa(TEXT)})}, {'index.xml': '<document><p>' + TEXT + '</p></document>'}]:
            result = extract_resume(archive(parts), 'CV.pages')
            self.assertIn('FINAL_EVIDENCE', result['text']); self.assertTrue(result['warnings'])
        with self.assertRaisesRegex(ValueError, 'DOCX/PDF'): extract_resume(archive({'preview.jpg': b'only image'}), 'CV.pages')

    @unittest.skipUnless(sys.platform == 'darwin', 'macOS DOC conversion')
    def test_legacy_word_conversion(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'cv.txt'; source.write_text(TEXT)
            doc = Path(directory) / 'cv.doc'
            subprocess.run(['/usr/bin/textutil', '-convert', 'doc', '-output', str(doc), str(source)], check=True, capture_output=True)
            self.assertIn('FINAL_EVIDENCE', extract_resume(doc.read_bytes(), 'CV.doc')['text'])

    def test_invalid_files_and_corrupt_compression_fail(self):
        for data, filename in [(b'not zip', 'CV.docx'), (b'hello', 'CV.exe'), (b'\x00' * 200, 'CV.txt'), (b'short', 'CV.md')]:
            with self.assertRaises((ValueError, zipfile.BadZipFile)): extract_resume(data, filename)
        with self.assertRaises(ValueError): _snappy(b'\x05\x01\x00')

    def test_loopback_service_requires_token_and_returns_review_candidate(self):
        token = 'fixture-token-only-for-unit-test'
        with TestClient(create_app(token)) as client:
            payload = {'filename': 'CV.txt', 'content_base64': base64.b64encode(TEXT.encode()).decode()}
            self.assertEqual(client.post('/extract', json=payload).status_code, 401)
            headers = {'X-Resume-Import-Token': token}
            result = client.post('/extract', json=payload, headers=headers)
            self.assertEqual(result.status_code, 200); self.assertEqual(result.json()['quality'], 'needs_review')
            self.assertEqual(client.post('/extract', json={'filename': 'CV.txt', 'content_base64': '!'}, headers=headers).status_code, 422)
            response = client.options('/extract', headers={'Origin': 'https://evil.test', 'Access-Control-Request-Method': 'POST'})
            self.assertNotIn('access-control-allow-origin', response.headers)
            allowed = client.options('/extract', headers={'Origin': 'chrome-extension://' + 'a' * 32, 'Access-Control-Request-Method': 'POST', 'Access-Control-Request-Headers': 'X-Resume-Import-Token'})
            self.assertEqual(allowed.status_code, 200)

if __name__ == '__main__': unittest.main()
