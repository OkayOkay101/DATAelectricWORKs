# Functional Test สำหรับ TOU analyzer

ชุดนี้เรียก `apply_tou_and_anomaly` จริงกับ DataFrame ขนาดเล็ก ไม่ใช่ syntax check หรือ mock

## รันบนเครื่องหรือ CI

ใช้ Python 3.12 ใน virtualenv แยก แล้วรันจากราก repository:

```sh
python -m pip install -r requirements-test.txt
python -m unittest discover -s tests -p 'test_*.py' -v
```

CI ชื่อ `python-functional` รันบน push/pull_request โดยไม่รับ secrets ของ Controller และไม่ส่งต่อ checkout credentials ให้โค้ดทดสอบ ใช้ unittest ของ Python จึงไม่เพิ่ม test framework ใหม่ แพ็กเกจใน requirements-test.txt เป็นสภาพแวดล้อมทดสอบ ไม่ได้ล็อก dependencies ทั้งแอป

## สิ่งที่ตรวจ

- เวลาเริ่ม On-Peak รวมขอบเขตเริ่ม และเวลาจบเป็น Off-Peak
- เสาร์ อาทิตย์ และวันหยุดมีลำดับความสำคัญเหนือ On-Peak
- วันหยุดใช้กับทุกเวลาของวัน และรายการวันหยุดว่างยังวิเคราะห์ได้
- ช่วง On-Peak ข้ามเที่ยงคืน
- ค่าไฟคูณจากพลังงานจริง และไม่แก้ DataFrame ต้นฉบับ
- ตรวจ anomaly สูง ต่ำ และโหลดศูนย์
- วันที่อ่านไม่ได้ วันที่ไม่มีจริง และรายการที่ผสมวันที่ถูก/ผิด ปัจจุบันโยน ValueError

**วันที่ผิดรูปแบบยังไม่ได้รับการแก้ไข**: tests สองรายการท้ายยืนยันข้อผิดพลาดเดิมให้ทำซ้ำได้ ไม่ได้บอกว่าแอปจัดการข้อผิดพลาดได้แล้ว งานแก้บั๊กต้องเพิ่ม regression test ที่คาดหวังพฤติกรรมใหม่ให้ล้มเหลวก่อนแก้ และยังคงตรวจผลลัพธ์วันหยุดที่ถูกต้อง ห้ามแก้เพียงให้ test ผ่านโดยลบ assertions

ชุดนี้ครอบคลุมฟังก์ชันวิเคราะห์ TOU ไม่ได้พิสูจน์ UI Streamlit, การอัปโหลดไฟล์ หรือพฤติกรรมทั้งแอป

## ใช้กับ repository อื่นแบบปรับตามโครงการ

ระบบสามารถสำรวจภาษา/framework/คำสั่งเดิม แล้วเสนอ tests และ CI ที่เหมาะสมได้ แต่ยังไม่ได้เปิดการติดตั้งอัตโนมัติทุก repository ในการเปลี่ยนแปลงนี้:

1. เจ้าของเลือก repo ที่เชื่อม GitHub App และ Jules เอง
2. ใช้ test framework และ dependency lock เดิมก่อน ถ้าไม่มีให้เสนอทางเลือกและขออนุมัติ dependency ใหม่
3. อ่าน entry points และพฤติกรรมธุรกิจ สร้างเคสปกติ ขอบเขต และข้อผิดพลาดจากหลักฐานจริง
4. รันใน CI แยกจาก secrets ของ Controller และตรวจว่าการเปลี่ยนผลลัพธ์ให้ผิดทำให้ tests ล้มเหลว
5. เจ้าของตรวจ/merge PR ตั้งค่า scope คำสั่งทดสอบและ trusted check provider แล้วจึงยืนยัน Functional Test ใน Dashboard

การตรวจพบ framework หรือ CI สีเขียวอย่างเดียวไม่เพียงพอให้เปิดความพร้อมอัตโนมัติ ต้องตรวจว่าชุดทดสอบตรงกับพฤติกรรมที่เจ้าของต้องการจริง และ jobs ไม่ข้าม tests

สำหรับ repo นี้หลัง merge PR ชุดทดสอบและยืนยัน CI บน main แล้ว จึงพิจารณาตั้งคำสั่งด้านบน ใช้ `python-functional` จาก GitHub Actions และ scope `tou_analyzer.py`, `tests/**` สำหรับงานบั๊กดังกล่าว โดยไม่ขยายไป workflow หรือ controller ของระบบ
