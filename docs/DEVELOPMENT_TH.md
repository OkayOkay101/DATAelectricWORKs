# คู่มือนักพัฒนา (Developer Guide)

เอกสารนี้สำหรับผู้ที่แก้ไขโค้ด รันการทดสอบ หรือ build แอปสำหรับ Windows ถ้าต้องการใช้งานโปรแกรม ดู [คู่มือผู้ใช้งาน](USER_GUIDE_TH.md)

## สิ่งที่ต้องเตรียม

- **Python 3.12** แนะนำ เพราะ CI ทุก workflow ใช้ Python 3.12
- **ไลบรารีของแอป:** `pandas`, `numpy`, `plotly`, `streamlit`, `openpyxl`, `xlrd`, `xlwt` คำสั่งติดตั้งอยู่ใน [README_TH.md](../README_TH.md)
- **การ build สำหรับ Windows:** `packaging/build_windows.ps1` ติดตั้ง `pandas==2.2.3` และ `numpy==2.1.3` พร้อม `streamlit`, `plotly`, `openpyxl`, `xlrd`, `xlwt` และ `pyinstaller`
- **ไลบรารีสำหรับการทดสอบ:** `requirements-test.txt` ล็อก `pandas==2.2.3` และ `numpy==2.1.3` และกำหนด `streamlit>=1.35.0` กับ `plotly>=5.0.0`

## รันการทดสอบ

รันจากโฟลเดอร์รากของ repository:
```bash
pip install -r requirements-test.txt
python -m unittest discover -s tests -p "test_*.py"
```

ไฟล์ทดสอบอยู่ในโฟลเดอร์ `tests/` บางไฟล์ตรวจว่าเอกสารตรงกับโค้ด เช่น `test_functional_test_docs.py` และ `test_mock_data_docs.py`

## CI workflows

ไฟล์ workflow อยู่ในโฟลเดอร์ `.github/workflows/`

| Workflow | ทำงานเมื่อ | สิ่งที่ทำ |
| :--- | :--- | :--- |
| `python-baseline.yml` | push, pull_request, เรียกด้วยมือ | รัน `scripts/check_python_syntax.py` บน Python 3.12 ตรวจไวยากรณ์ของไฟล์ Python ที่ติดตามโดย Git โดยไม่ import โค้ด timeout 5 นาที |
| `python-functional.yml` | push, pull_request, เรียกด้วยมือ | รันคำสั่ง unittest ด้านบนบน Python 3.12 timeout 10 นาที ดู [FUNCTIONAL_TESTS_TH.md](FUNCTIONAL_TESTS_TH.md) |
| `jules-quality.yml` | pull_request ที่แก้ไฟล์ใน `.github/quality/`, ไฟล์ workflow นี้ หรือ `tests/test_quality_runner.py`; เรียกด้วยมือพร้อม input | selftest ของตัวปรับคุณภาพ (quality adapter) timeout 15 นาที ดู [TEST_QUALITY_TH.md](TEST_QUALITY_TH.md) |

## Build แอปสำหรับ Windows

รันจากโฟลเดอร์รากของ repository:
```powershell
powershell -ExecutionPolicy Bypass -File packaging\build_windows.ps1
powershell -ExecutionPolicy Bypass -File packaging\build_windows.ps1 -Python "C:\Path\To\python.exe" -Version 1.0.0
```

พารามิเตอร์:
- `-Python`: ไฟล์ Python ที่จะใช้ ค่าเริ่มต้นคือ `python`
- `-Version`: เวอร์ชันที่ใช้ในชื่อไฟล์ zip ค่าเริ่มต้นคือ `1.0.0`

สคริปต์จะติดตั้ง dependencies รัน PyInstaller แบบ onedir โดยใช้ `packaging\launcher.py` เป็นจุดเริ่มต้น แล้วสร้างไฟล์ zip ผลลัพธ์ (เขียนลงโฟลเดอร์ `dist`):
- โฟลเดอร์แอปชื่อ DATAelectricWORKs ซึ่งมีไฟล์ DATAelectricWORKs.exe อยู่ข้างใน
- ไฟล์ zip ชื่อ DATAelectricWORKs-v{Version}-windows-x64.zip โดย {Version} คือค่าของ `-Version`

`packaging/launcher.py` เลือกพอร์ตว่างบน `127.0.0.1` เปิดแอป `app.py` ด้วย Streamlit และเปิดเบราว์เซอร์หลังผ่านไปประมาณ 3 วินาที การปิดหน้าต่าง console จะหยุดแอป

## โครงสร้างโปรเจกต์

| พาธ | หน้าที่ |
| :--- | :--- |
| `app.py` | หน้าจอ Streamlit |
| `data_handler.py` | ตรวจไฟล์อัปโหลด อ่านไฟล์ และเตรียมข้อมูล |
| `tou_analyzer.py` | กำหนดช่วง TOU คำนวณค่าไฟ และตรวจจับความผิดปกติ |
| `generate_mock_data.py` | สร้างข้อมูลตัวอย่างใน `mock_data/` (`.csv`, `.xlsx`, `.txt`) |
| `run_main.py` | เปิดแอปด้วย Streamlit |
| `packaging/` | สคริปต์ build สำหรับ Windows และ launcher |
| `scripts/` | สคริปต์ตรวจของ repository เช่น การตรวจไวยากรณ์ |
| `tests/` | การทดสอบหน่วยและการทดสอบเอกสาร |
| `docs/` | เอกสารประกอบ |
| `.github/` | CI workflows และตัวปรับคุณภาพ |

โฟลเดอร์ `mock_data/` มีไฟล์ `mock_dataset.xls` ด้วย ซึ่ง `generate_mock_data.py` ไม่ได้สร้างไฟล์นี้ ไฟล์ที่อยู่ในรากโปรเจกต์อื่น เช่น `benchmark_bolt.py` ไม่ได้อธิบายในเอกสารนี้
