"""Local text extraction from applicant-supplied files. No uploads or LLM calls."""
from __future__ import annotations
import gzip
import hashlib
import io
import re
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

MAX_FILE = 12 * 1024 * 1024
MAX_EXPANDED = 48 * 1024 * 1024
MAX_TEXT = 250000
FORMATS = {".txt", ".md", ".docx", ".doc", ".pdf", ".pages"}


def redact_contacts(text):
    text = re.sub(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", "[email скрыт]", text)
    def phone(match):
        value = match[0]
        return "[телефон скрыт]" if 10 <= len(re.sub(r"\D", "", value)) <= 15 else value
    return re.sub(r"\+\d[\d ()–-]{8,}\d", phone, text)


def safe_zip(data):
    archive = zipfile.ZipFile(io.BytesIO(data))
    if len(archive.infolist()) > 4000 or sum(i.file_size for i in archive.infolist()) > MAX_EXPANDED:
        raise ValueError("Архив документа слишком велик после распаковки.")
    if any(i.flag_bits & 1 for i in archive.infolist()):
        raise ValueError("Защищённый паролем документ: сначала сохраните незашифрованную копию.")
    return archive


def docx_text(data):
    archive = safe_zip(data)
    if "word/document.xml" not in archive.namelist():
        raise ValueError("Файл не содержит документ Word DOCX.")
    parts = ["word/document.xml"] + sorted(n for n in archive.namelist() if re.fullmatch(r"word/(?:header|footer)\d+\.xml", n))
    paragraphs = []
    ns = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    for part in parts:
        root = ET.fromstring(archive.read(part))
        for paragraph in root.iter(ns + "p"):
            pieces = []
            for node in paragraph.iter():
                if node.tag == ns + "t": pieces.append(node.text or "")
                elif node.tag in {ns + "tab", ns + "br", ns + "cr"}: pieces.append("\n" if node.tag != ns + "tab" else "\t")
            value = "".join(pieces).strip()
            if value: paragraphs.append(value)
    return "\n".join(paragraphs)


def pdf_text(data):
    from pypdf import PdfReader
    reader = PdfReader(io.BytesIO(data))
    if reader.is_encrypted and not reader.decrypt(""):
        raise ValueError("PDF защищён паролем. Загрузите незашифрованную копию.")
    if len(reader.pages) > 40: raise ValueError("Для резюме поддерживается PDF до 40 страниц.")
    pages = [page.extract_text() or "" for page in reader.pages]
    empty = [str(i + 1) for i, text in enumerate(pages) if len(text.strip()) < 20]
    if empty:
        raise ValueError("В PDF нет достаточного текста на страницах " + ", ".join(empty) + ". Для скана сначала выполните OCR или экспортируйте текстовый PDF/DOCX.")
    return "\n\n".join(pages)


def _varint(data, pos):
    value = 0
    for shift in range(0, 70, 7):
        if pos >= len(data): raise ValueError("Оборванный IWA varint")
        byte = data[pos]; pos += 1
        value |= (byte & 127) << shift
        if not byte & 128: return value, pos
    raise ValueError("Некорректный IWA varint")


def _fields(data):
    pos, fields = 0, {}
    while pos < len(data):
        tag, pos = _varint(data, pos)
        number, kind = tag >> 3, tag & 7
        if not number: raise ValueError("Некорректное поле IWA")
        if kind == 0: value, pos = _varint(data, pos)
        elif kind in (1, 5):
            length = 8 if kind == 1 else 4
            if pos + length > len(data): raise ValueError("Оборванное поле IWA")
            value = data[pos:pos+length]; pos += length
        elif kind == 2:
            length, pos = _varint(data, pos)
            if pos + length > len(data): raise ValueError("Оборванное поле IWA")
            value = data[pos:pos+length]; pos += length
        else: raise ValueError("Неподдерживаемое поле IWA")
        fields.setdefault(number, []).append(value)
    return fields


def _snappy(raw):
    expected, pos = _varint(raw, 0)
    if expected > MAX_EXPANDED: raise ValueError("Слишком большой IWA блок")
    out = bytearray()
    def take(count):
        nonlocal pos
        if pos + count > len(raw): raise ValueError("Оборванный Snappy блок")
        chunk = raw[pos:pos+count]; pos += count
        return chunk
    while pos < len(raw):
        tag = take(1)[0]; kind = tag & 3
        if kind == 0:
            count = tag >> 2
            count = count + 1 if count < 60 else int.from_bytes(take(count - 59), "little") + 1
            if len(out) + count > expected: raise ValueError("Некорректная длина Snappy")
            out.extend(take(count))
        else:
            count = 4 + ((tag >> 2) & 7) if kind == 1 else 1 + (tag >> 2)
            offset = ((tag & 224) << 3) | take(1)[0] if kind == 1 else int.from_bytes(take(2 if kind == 2 else 4), "little")
            if not 0 < offset <= len(out) or len(out) + count > expected: raise ValueError("Некорректная ссылка Snappy")
            for _ in range(count): out.append(out[-offset])
    if len(out) != expected: raise ValueError("IWA распакован не полностью")
    return bytes(out)


def _iwa_messages(data):
    pos, stream = 0, bytearray()
    while pos < len(data):
        if pos + 4 > len(data): raise ValueError("Оборванный IWA frame")
        kind, length = data[pos], int.from_bytes(data[pos+1:pos+4], "little"); pos += 4
        if pos + length > len(data): raise ValueError("Оборванный IWA frame")
        chunk = data[pos:pos+length]; pos += length
        if kind == 0: stream.extend(_snappy(chunk))
        elif kind == 1: stream.extend(chunk[4:])
        elif kind >= 128: continue
        else: raise ValueError("Неизвестный формат IWA frame")
        if len(stream) > MAX_EXPANDED: raise ValueError("IWA слишком велик")
    pos = 0
    while pos < len(stream):
        size, pos = _varint(stream, pos)
        if pos + size > len(stream): raise ValueError("Оборванный IWA archive header")
        header = _fields(stream[pos:pos+size]); pos += size
        for info in header.get(2, []):
            fields = _fields(info)
            kind, length = fields[1][0], fields[3][0]
            if pos + length > len(stream): raise ValueError("Оборванный IWA archive payload")
            yield kind, bytes(stream[pos:pos+length]); pos += length


def pages_text(data):
    """Read iWork XML or text storage; never mistake a thumbnail for a complete CV.

    Format reference: github.com/obriensp/iWorkFileFormat, TSWP.StorageArchive
    (type 2001, kind field 1, UTF-8 text field 3), TSP.ArchiveInfo.
    """
    archive = safe_zip(data)
    names = archive.namelist()
    legacy = next((n for n in names if n in {"index.xml", "index.xml.gz"}), None)
    if legacy:
        xml = archive.read(legacy)
        if legacy.endswith(".gz"):
            with gzip.GzipFile(fileobj=io.BytesIO(xml)) as compressed: xml = compressed.read(MAX_EXPANDED + 1)
        if len(xml) > MAX_EXPANDED: raise ValueError("Pages XML слишком велик")
        root = ET.fromstring(xml)
        paras = ["".join(p.itertext()).strip() for p in root.iter() if p.tag.split("}")[-1] == "p"]
        return "\n".join(p for p in paras if p), "pages_xml"
    if "Index.zip" in names:
        archive = safe_zip(archive.read("Index.zip")); names = archive.namelist()
    stores, seen, expanded = [], set(), 0
    for name in sorted(n for n in names if n.endswith(".iwa")):
        for kind, payload in _iwa_messages(archive.read(name)):
            expanded += len(payload)
            if expanded > MAX_EXPANDED: raise ValueError("Pages содержит слишком много данных")
            if kind != 2001: continue
            fields = _fields(payload)
            storage_kind = fields.get(1, [3])[0]
            if storage_kind in {4, 7}: continue  # notes / auto-generated table of contents
            text = "".join(v.decode("utf-8", errors="strict") for v in fields.get(3, []) if isinstance(v, bytes)).strip()
            if text and text not in seen:
                stores.append((storage_kind != 0, text)); seen.add(text)
    if not stores:
        raise ValueError("Не удалось извлечь текст .pages. Экспортируйте из Pages в DOCX/PDF и загрузите копию; превью не считается полным резюме.")
    return "\n\n".join(text for _, text in sorted(stores, key=lambda item:item[0])), "pages_iwa_text_storage"


def extract_resume(data, filename, *, min_text=100):
    filename = Path(filename.replace("\\", "/")).name
    suffix = Path(filename).suffix.lower()
    if suffix not in FORMATS: raise ValueError("Поддерживаются .pages, .doc, .docx, .txt, .pdf, .md")
    if not data or len(data) > MAX_FILE: raise ValueError("Пустой файл или размер больше 12 МБ.")
    method, warnings = suffix[1:], []
    if suffix in {".txt", ".md"}:
        try: text = data.decode("utf-8-sig")
        except UnicodeDecodeError:
            if data.startswith((b'\xff\xfe', b'\xfe\xff')): text = data.decode("utf-16")
            else: raise ValueError("Сохраните текстовый файл в UTF-8 или UTF-16 с BOM.")
        if '\x00' in text: raise ValueError("Файл содержит бинарные данные вместо текста.")
    elif suffix == ".docx": text = docx_text(data)
    elif suffix == ".pdf": text = pdf_text(data)
    elif suffix == ".pages":
        text, method = pages_text(data)
        warnings.append("Для Pages проверьте полноту текста и порядок текстовых блоков по оригиналу.")
    else:
        if sys.platform != "darwin": raise ValueError("Чтение .doc требует macOS textutil; сохраните DOCX или TXT.")
        with tempfile.TemporaryDirectory(prefix="resume-doc-") as directory:
            source = Path(directory) / "resume.doc"; source.write_bytes(data)
            result = subprocess.run(["/usr/bin/textutil", "-convert", "txt", "-stdout", str(source)], capture_output=True, timeout=25, check=False)
            if result.returncode: raise ValueError("Не удалось прочитать .doc. Сохраните копию в DOCX.")
            text = result.stdout.decode("utf-8-sig"); method = "macos_textutil"
    text = redact_contacts(text).strip()
    if not min_text <= len(text) <= MAX_TEXT: raise ValueError("Извлечённого текста слишком мало или слишком много. Проверьте файл.")
    if text.count('\ufffd') > 3: raise ValueError("Текст содержит ошибки декодирования. Сохраните DOCX/TXT.")
    return {"id": "file_" + hashlib.sha256(data).hexdigest(), "source_type": "file", "title": Path(filename).stem,
            "filename": filename, "file_hash": hashlib.sha256(data).hexdigest(), "text": text,
            "extraction_method": method, "warnings": warnings, "quality": "needs_review"}
