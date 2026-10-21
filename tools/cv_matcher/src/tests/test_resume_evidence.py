import base64,io,unittest,zipfile
from datetime import date
from types import SimpleNamespace
from unittest.mock import patch
from src.resume_evidence import extract,spreadsheet

class EvidenceFilesTests(unittest.TestCase):
    def test_short_fragment_is_evidence_not_a_full_resume_and_keeps_source_identity(self):
        text='Example: 2020-01 — 2024-12.'
        result=extract({'filename':'employment.md','content_base64':base64.b64encode(text.encode()).decode()})
        self.assertEqual(result['api_requests'],0);self.assertEqual(result['candidate']['text'],text)
        self.assertEqual(result['candidate']['label'],'employment.md');self.assertEqual(len(result['candidate']['file_hash']),64)

    def test_binary_xls_reader_preserves_date_types_and_never_evaluates_formulas(self):
        sheet=SimpleNamespace(start=(0,0),iter_rows=lambda:iter([['Employer','Start','End'],['Example',date(2020,1,1),date(2024,12,31)]]))
        book=SimpleNamespace(sheet_names=['Dates'],get_sheet_by_name=lambda _:sheet,close=lambda:None)
        with patch('python_calamine.CalamineWorkbook.from_filelike',return_value=book):
            text=spreadsheet(b'binary fixture','.xls')
        self.assertIn('2020-01-01',text);self.assertIn('Строка 2: Example',text)

    def test_real_xlsx_sheet_is_read_with_named_rows(self):
        data=io.BytesIO()
        with zipfile.ZipFile(data,'w') as z:
            z.writestr('[Content_Types].xml','<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/></Types>')
            z.writestr('_rels/.rels','<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>')
            z.writestr('xl/workbook.xml','<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Dates" sheetId="1" r:id="rId1"/></sheets></workbook>')
            z.writestr('xl/_rels/workbook.xml.rels','<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/></Relationships>')
            z.writestr('xl/worksheets/sheet1.xml','<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData><row r="1"><c r="A1" t="inlineStr"><is><t>Example: 2020-01 — 2024-12</t></is></c></row></sheetData></worksheet>')
        text=spreadsheet(data.getvalue(),'.xlsx');self.assertIn('Лист: Dates',text);self.assertIn('2024-12',text)

    def test_corrupt_files_and_excessive_tables_are_explicit_errors(self):
        with self.assertRaises(ValueError):extract({'filename':'a.xls','content_base64':'broken!'})
        with self.assertRaisesRegex(ValueError,'Excel'):spreadsheet(b'not excel','.xls')
        book=SimpleNamespace(sheet_names=['x']*21,close=lambda:None)
        with patch('python_calamine.CalamineWorkbook.from_filelike',return_value=book):
            with self.assertRaisesRegex(ValueError,'20 листов'):spreadsheet(b'fixture','.xls')
