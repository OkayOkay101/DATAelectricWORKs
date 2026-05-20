import os
import sys
import streamlit.web.cli as stcli

def get_resource_path(relative_path):
    """ฟังก์ชันหาตำแหน่งพาธไฟล์ดิบที่แท้จริงหลังจากถูกมัดรวมด้วย PyInstaller"""
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.abspath("."), relative_path)

if __name__ == "__main__":
    # อ้างอิงไปยังไฟล์หน้าจอหลักหลักของคุณ (app.py)
    script_path = get_resource_path("app.py")
    
    sys.argv = [
        "streamlit", 
        "run", 
        script_path, 
        "--global.developmentMode=false",
        "--server.headless=false"  # <--- แก้ตรงนี้เป็น false ครับ
    ]
    sys.exit(stcli.main())