# Load Profile & TOU Simulator (ระบบวิเคราะห์โหลดและจำลองค่าไฟ TOU)

วิเคราะห์ข้อมูล **Load Profile** ของการใช้ไฟฟ้า (ค่ากำลังไฟฟ้า ปกติบันทึกทุก 15 นาที) และจำลองค่าไฟฟ้าแบบ **TOU (Time of Use)** หรือแบบอัตราเดียว โปรแกรมทำงานบนเว็บเบราว์เซอร์ในเครื่องของคุณ ข้อมูลจึงไม่ถูกส่งออกไปที่อื่น

> 🇬🇧 English: [README.md](README.md)

## โปรแกรมทำอะไรได้บ้าง

1. **อัปโหลดไฟล์** `.csv`, `.txt`, `.xlsx`, `.xls` (ไม่เกิน 20 ไฟล์ ไฟล์ละ 50 MB รวมไม่เกิน 200 MB) หลายไฟล์จะถูกรวมให้อัตโนมัติ
2. **ตั้งค่าการคิดค่าไฟ** เลือก TOU หรืออัตราเดียว กรอกเรท เวลา On-Peak และรายการวันหยุด
3. **ดูผลลัพธ์** แยกเป็น 4 แท็บ
   - **ภาพรวมพลังงาน**: พลังงานรวม (kWh) ความต้องการสูงสุด (kW) ค่าไฟประเมิน และจุดผิดปกติ
   - **เจาะลึกรายวัน**: กราฟและตาราง 15 นาทีของวันที่เลือก
   - **กราฟจำลองเวลา**: เลื่อนเวลาการใช้ไฟแล้วเทียบกับข้อมูลเดิม
   - **วิเคราะห์ค่าไฟ**: สรุปตามช่วงเวลา (รวม รายเดือน รายวัน หรือกำหนดช่วงเอง)
4. **ดาวน์โหลด** ผลลัพธ์เป็นไฟล์ CSV

คู่มือการใช้งานฉบับเต็มอยู่ที่ [คู่มือผู้ใช้งาน](docs/USER_GUIDE_TH.md)

## ดาวน์โหลดสำหรับ Windows

ดาวน์โหลดเวอร์ชันล่าสุดได้จาก [หน้า Releases](https://github.com/OkayOkay101/DATAelectricWORKs/releases) แตกไฟล์ zip แล้วดับเบิลคลิก `DATAelectricWORKs.exe` ไม่ต้องติดตั้ง Python

ไฟล์ยังไม่ได้ลงนามดิจิทัล Windows อาจแสดงคำเตือน SmartScreen ให้เลือก "More info" แล้ว "Run anyway" ถ้าคุณมั่นใจว่าดาวน์โหลดจากแหล่งนี้

## รันจากซอร์สโค้ด

แนะนำ Python 3.12

```bash
python -m venv venv
venv\Scripts\activate            # macOS / Linux: source venv/bin/activate
pip install pandas numpy plotly streamlit openpyxl xlrd xlwt
streamlit run app.py
```

ต้องการข้อมูลตัวอย่าง ให้รัน `python generate_mock_data.py` ไฟล์จะถูกสร้างในโฟลเดอร์ `mock_data/`

## รันการทดสอบ

```bash
pip install -r requirements-test.txt
python -m unittest discover -s tests -p "test_*.py"
```

## เอกสารประกอบ

| เอกสาร | ภาษา |
| :--- | :--- |
| [คู่มือผู้ใช้งาน](docs/USER_GUIDE_TH.md) / [User Guide](docs/USER_GUIDE_EN.md) | TH / EN |
| [คู่มือเริ่มต้นใช้งานอย่างรวดเร็ว](docs/GETTING_STARTED_TH.md) | TH |
| [รูปแบบข้อมูลนำเข้า](docs/INPUT_FORMATS_TH.md) | TH |
| [แก้ปัญหาการใช้งาน](docs/TROUBLESHOOTING_TH.md) | TH |
| [การทดสอบเชิงฟังก์ชัน](docs/FUNCTIONAL_TESTS_TH.md) | TH |
| [คุณภาพของการทดสอบ](docs/TEST_QUALITY_TH.md) | TH |

## โครงสร้างโปรเจกต์

| พาธ | หน้าที่ |
| :--- | :--- |
| `app.py` | หน้าจอ Streamlit |
| `data_handler.py` | ตรวจสอบไฟล์ที่อัปโหลด อ่านข้อมูล และเตรียมข้อมูล |
| `tou_analyzer.py` | กำหนดช่วง TOU คำนวณค่าไฟ และตรวจจับจุดผิดปกติ |
| `generate_mock_data.py` | สร้างข้อมูลตัวอย่างใน `mock_data/` |
| `run_main.py` | ตัวเปิดโปรแกรมที่เรียก Streamlit |
| `tests/` | การทดสอบหน่วย (unit tests) |
| `docs/` | เอกสารประกอบ |

## ใบอนุญาต

ยังไม่มีไฟล์ใบอนุญาตในโปรเจกต์
