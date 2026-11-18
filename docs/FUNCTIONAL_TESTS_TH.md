# Functional Test สำหรับ TOU analyzer

ชุดนี้เรียก `apply_tou_and_anomaly` จริงกับ DataFrame ขนาดเล็ก ไม่ใช่ syntax check หรือ mock

## รันบนเครื่องหรือ CI

ใช้ Python 3.12 ใน virtualenv แยก แล้วรันจากราก repository:

```sh
python -m pip install -r requirements-test.txt
python -m unittest discover -s tests -p 'test_*.py' -v
```

repo นี้มี workflow `.github/workflows/python-functional.yml` (ชื่อ Python Functional Tests) ที่รันเมื่อ push, pull_request และ workflow_dispatch บน ubuntu-latest ใช้ Python 3.12 ติดตั้ง `requirements-test.txt` แล้วรันคำสั่ง unittest ด้านบน มี timeout 10 นาที สิทธิ์ของ workflow คืออ่าน contents อย่างเดียว และ checkout ไม่เก็บ credentials ไว้ ไม่ใช้ secrets ใด ๆ ใช้ unittest ของ Python จึงไม่เพิ่ม test framework ใหม่ แพ็กเกจใน requirements-test.txt เป็นสภาพแวดล้อมทดสอบ ไม่ได้ล็อก dependencies ทั้งแอป

## สิ่งที่ตรวจ

- เวลาเริ่ม On-Peak รวมขอบเขตเริ่ม และเวลาจบเป็น Off-Peak
- เสาร์ อาทิตย์ และวันหยุดมีลำดับความสำคัญเหนือ On-Peak
- วันหยุดใช้กับทุกเวลาของวัน และรายการวันหยุดว่างยังวิเคราะห์ได้
- ช่วง On-Peak ข้ามเที่ยงคืน
- ค่าไฟคูณจากพลังงานจริง และไม่แก้ DataFrame ต้นฉบับ
- ตรวจ anomaly สูง ต่ำ และโหลดศูนย์
- วันหยุดที่อ่านไม่ได้หรือไม่มีจริงจะถูกละเว้น และวันหยุดที่ถูกต้องในรายการผสมยังมีผล

วันที่อ่านไม่ได้และวันที่ไม่มีจริงถูกทดสอบว่าไม่ทำให้การวิเคราะห์ล้มเหลว ส่วนรายการที่ผสมวันหยุดถูกต้องกับวันที่ผิดรูปแบบยังคงใช้วันหยุดที่ถูกต้อง

ชุดนี้ครอบคลุมฟังก์ชันวิเคราะห์ TOU ไม่ได้พิสูจน์ UI Streamlit, การอัปโหลดไฟล์ หรือพฤติกรรมทั้งแอป

## ใช้กับ repository อื่นแบบปรับตามโครงการ

ระบบสามารถสำรวจภาษา/framework/คำสั่งเดิม แล้วเสนอ tests และ CI ที่เหมาะสมได้ แต่ยังไม่ได้เปิดการติดตั้งอัตโนมัติทุก repository ในการเปลี่ยนแปลงนี้:

1. เจ้าของเลือก repo ที่เชื่อม GitHub App และ Jules เอง
2. ใช้ test framework และ dependency lock เดิมก่อน ถ้าไม่มีให้เสนอทางเลือกและขออนุมัติ dependency ใหม่
3. อ่าน entry points และพฤติกรรมธุรกิจ สร้างเคสปกติ ขอบเขต และข้อผิดพลาดจากหลักฐานจริง
4. รันใน CI แยกจาก secrets ของ Controller และตรวจว่าการเปลี่ยนผลลัพธ์ให้ผิดทำให้ tests ล้มเหลว
5. เจ้าของตรวจ/merge PR ตั้งค่า scope คำสั่งทดสอบและ trusted check provider แล้วจึงยืนยัน Functional Test ใน Dashboard

การตรวจพบ framework หรือ CI สีเขียวอย่างเดียวไม่เพียงพอให้เปิดความพร้อมอัตโนมัติ ต้องตรวจว่าชุดทดสอบตรงกับพฤติกรรมที่เจ้าของต้องการจริง และ jobs ไม่ข้าม tests

สำหรับ repo นี้ workflow มีอยู่แล้ว แต่เอกสารนี้ตรวจได้แค่ไฟล์ใน repo ไม่ได้ยืนยันผลการรันจริง ก่อนเปิดใช้ Functional Test ควรดูว่าการรันบน main ผ่านจริงใน GitHub Actions แล้วจึงใช้คำสั่งด้านบนกับ scope `tou_analyzer.py` และไฟล์ทั้งหมดในโฟลเดอร์ `tests/` สำหรับงานบั๊กดังกล่าว โดยไม่ขยายไป workflow หรือ controller ของระบบ
