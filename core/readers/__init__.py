"""Các bộ đọc file đầu vào (đề thi / hồ sơ vụ án).

Mỗi định dạng một module:
  - word_docx.py : .docx (Word OpenXML)
  - word_doc.py  : .doc  (Word 97-2003, nhị phân)
  - rtf.py       : .rtf  (kể cả RTF bị đổi đuôi thành .doc)
  - pdf.py       : .pdf  (có lớp chữ, bản scan, hoặc lẫn cả hai)
  - ocr.py       : nhận dạng chữ từ ảnh (Gemini / EasyOCR / Tesseract)

Điểm vào chung nằm ở core/file_parser.py.
"""
