"""Bill scanning: a photo or PDF of a bill -> merchant, date, total and items grouped by category.

    preprocess.py  OpenCV clean-up of photos (size, perspective, deskew, contrast)
    ocr.py         PDF text layer or OCR (RapidOCR: PP-OCR models on ONNX Runtime) -> lines
    parse.py       lines -> merchant, date, total, item lines (rules)
    items.py       items -> category groups, mapped to the user's categories
"""
