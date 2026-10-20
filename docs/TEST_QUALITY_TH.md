# CI ตรวจพฤติกรรมของงาน Jules

ชุดนี้เป็น adapter รุ่นแรกสำหรับ Python 3.12 / unittest เท่านั้น ไม่เปิดใช้กับ repo อื่นโดยอัตโนมัติ
เจ้าของต้องตรวจ PR นี้ก่อน merge แล้วตั้ง quality profile ใน Controller โดยตรึง workflow ID,
revision, blob SHA ของ workflow และ `.github/quality/{runner.py,phase.py,profile.json}` รวมชื่อ check
`jules-quality` และ GitHub Actions App ID จากหลักฐานจริง ห้ามใช้ค่า placeholder เปิดระบบ

Controller เรียก workflow ผ่าน tag ที่ตรึง revision บน default branch ไม่ใช้ workflow/harness จาก PR เป้าหมาย
งาน selftest จาก pull_request ไม่ใช่หลักฐานรับงาน ระบบยังตรวจผู้สร้าง PR, scope, CI และ merge policy เดิม
งานที่ยังไม่มี profile ใช้นโยบายเดิมจนเจ้าของเปิด gate ครั้งแรก หลังเปิดแล้วการลบ profile ทำให้งานรอตั้งค่า

## หลักฐานที่ตรวจ

- งานบั๊กต้องมี test เพิ่มหรือปรับใน scope เดิม ใช้ test เดียวกันกับโค้ด base และ candidate: base ต้อง fail
  จาก assertion ของพฤติกรรม ส่วน candidate ต้อง pass; import/setup error ไม่นับเป็น red
- งานเพิ่ม tests ต้องผ่านกับโค้ดจริง จับ mutation ชั่วคราวในโมดูลแอปได้ และผ่านอีกครั้งหลังคืนไฟล์เดิม
- งานหลายสมาชิกต้องมีผลแยกทุกสมาชิก ไม่ผ่านทั้งชุดด้วย shared CI เพียงอย่างเดียว
- test ที่ไม่มี assertion, assert ค่าคงที่, กลืน exception หรือแทน sys.modules ต้องให้เจ้าของแก้/ตรวจ
  ชุดเดิมใน repo ไม่ถูกถือว่ามีคุณภาพโดยอัตโนมัติ และ adapter ไม่แก้ tests เดิมให้เอง

## การแยกการรัน

`runner.py` รันบน host ที่ไม่มี Jules secret และไม่ import โค้ดเป้าหมาย จากนั้นอ่าน Git objects ที่ระบุ SHA
สร้าง snapshot ชั่วคราว และใช้ container Python 3.12 ที่ติดตั้ง requirements-test.txt จาก approved base
เท่านั้น Container ทดสอบไม่มี token, network, Docker socket, host workspace หรือ mount สำหรับเขียน report;
snapshot และ phase.py เป็น readonly, user ไม่มีสิทธิ์ root, จำกัด CPU/RAM/process และลบ container เมื่อจบ/timeout

แต่ละ phase ไม่เกิน 180 วินาที รวม wrapper ไม่เกินประมาณ 12 นาที และ job ไม่เกิน 15 นาที
mutation ทดลองรวมไม่เกิน 3 แบบต่อสมาชิก ไม่ push การเปลี่ยนแปลง และเก็บ output ในหน่วยความจำแบบจำกัด
รายงานสร้างบน host หลัง process จบ อ่านเป็น JSON ขนาดจำกัดโดย Controller ไม่มีการ extract/execute artifact

`test_command` ระบุคำสั่ง unittest ตาม profile ที่อนุญาต ส่วน `executed_commands` บันทึก argv ของ phase
ที่เรียกจริงภายใน container จึงแยกค่าตั้งนโยบายจากสิ่งที่ได้รันจริง

## ข้อจำกัดและการเปิดใช้

static screening, red/green และ mutation sensitivity เป็นหลักฐานเฉพาะกรณี ไม่พิสูจน์ coverage ทั้งแอปหรือ
รับประกันว่า tests ที่จงใจหลอกจะตรวจพบเสมอ stdout ของเป้าหมายยังเป็นข้อมูลที่ไม่เชื่อถือ;
การตรึง wrapper/check provenance และการตรวจ PR ของเจ้าของยังจำเป็น
ถ้า framework/import/layout ไม่รองรับ หรือ scope ไม่มีไฟล์ tests ให้ BLOCKED เฉพาะงาน ไม่ขยาย scope/dependencies เอง

รัน `python -m unittest discover -s tests -p test_quality_runner.py -v` บน GitHub CI ที่มี Docker ก่อนเปิด profile
เครื่อง local ที่ไม่มี Docker จะ skip การตรวจ container จริง ต้องรายงานเป็น “ยังไม่ได้ทดสอบ container”
ห้ามใช้ผล mock/static หรือ selftest ที่ skip แทนผล container จริง และยังต้องขออนุมัติ merge/เปิดใช้แยกต่างหาก
