import pandas as pd
import streamlit as st
import io

def parse_text_lines(lines, delimiter=','):
    header_row_idx = -1
    # 1. ค้นหาบรรทัดที่เป็นหัวตาราง (เพิ่มเงื่อนไข 'time' และ 'active power+')
    for i, line in enumerate(lines[:50]):
        l_lower = line.lower()
        if ('clock' in l_lower and 'import' in l_lower) or \
           ('ch1' in l_lower and 'ch4' in l_lower) or \
           ('date' in l_lower and 'clock' in l_lower) or \
           ('pea no' in l_lower and 'clock' in l_lower) or \
           ('time' in l_lower and 'active power+' in l_lower):
            header_row_idx = i
            # ตรวจจับ Tab
            if '\t' in line and ',' not in line:
                delimiter = '\t'
            break
            
    if header_row_idx == -1:
        return None
        
    header_line = lines[header_row_idx]
    
    # จัดการกรณี txt ที่หัวตารางคั่นด้วย space หรือ delimiter ผิดปกติ
    if delimiter == ',' and ',' not in header_line:
        cols = [c.strip().lower() for c in header_line.split()]
        delimiter = 'space'
    elif delimiter == 'space':
        cols = [c.strip().lower() for c in header_line.split()]
    else:
        cols = [c.strip().lower() for c in header_line.split(delimiter)]
        
    # 2. ค้นหา Index (ตำแหน่ง) ของคอลัมน์ที่ต้องการ (เพิ่มเงื่อนไข 'time' และ 'activepower+')
    date_idx, clock_idx, kw_idx, v_idx = -1, -1, -1, -1
    for i, c in enumerate(cols):
        c_clean = c.replace(' ', '').replace('.', '').replace('_', '')
        if c_clean == 'date': date_idx = i
        elif 'clock' in c_clean or 'ch1' == c_clean or 'time' in c_clean: clock_idx = i
        elif ('import' in c_clean and 'kw' in c_clean) or 'ch4' == c_clean or 'activepower+' in c_clean: kw_idx = i
        elif 'voltage' in c_clean or 'ch3' == c_clean: v_idx = i
        
    if clock_idx == -1 or kw_idx == -1:
        return None
        
    # 3. ดึงข้อมูลทีละบรรทัดเฉพาะ Index ที่ต้องการเท่านั้น (เตะขยะส่วนเกินทิ้ง)
    data_rows = []
    for line in lines[header_row_idx+1:]:
        line = line.strip()
        if not line: continue
        
        if delimiter == 'space':
            parts = [p.strip() for p in line.split()]
        else:
            parts = [p.strip() for p in line.split(delimiter)]
        
        # กรองบรรทัดขยะในคอลัมน์ date (พวกคำว่า Total, P, OP)
        if date_idx != -1 and date_idx < len(parts):
            d_val = parts[date_idx].lower()
            if any(x in d_val for x in ['total', 'p', 'op', 'h', 'kwh', 'nan']) or not d_val:
                continue
        
        # กรองบรรทัดขยะในคอลัมน์ clock
        if clock_idx < len(parts):
            c_val = parts[clock_idx].lower()
            if any(x in c_val for x in ['total', 'p', 'op', 'h', 'kwh', 'nan', 'dnv/err']) or not c_val:
                continue
                
            # ดึงข้อมูลจากช่อง
            date_val = parts[date_idx] if date_idx != -1 and date_idx < len(parts) else ""
            clock_val = parts[clock_idx]
            kw_val = parts[kw_idx] if kw_idx < len(parts) else "0"
            v_val = parts[v_idx] if v_idx != -1 and v_idx < len(parts) else "220"
            
            # รวมวันที่และเวลา
            if date_val:
                merged_clock = f"{date_val} {clock_val}"
            else:
                merged_clock = clock_val
                
            data_rows.append([merged_clock, kw_val, v_val])
            
    # ส่งคืนตารางที่มีโครงสร้างตรงเป๊ะ 3 คอลัมน์ 100%
    return pd.DataFrame(data_rows, columns=['Clock', 'kW_Import', 'Voltage'])

def parse_excel_df(df_raw):
    """สำหรับอ่านไฟล์ Excel .xlsx ของแท้ หรือรับต่อจาก pd.read_csv()"""
    header_row_idx = -1
    for i in range(min(50, len(df_raw))):
        row_str = ' '.join(df_raw.iloc[i].fillna('').astype(str)).lower()
        if ('clock' in row_str and 'import' in row_str) or \
           ('ch1' in row_str and 'ch4' in row_str) or \
           ('date' in row_str and 'clock' in row_str) or \
           ('pea no' in row_str and 'clock' in row_str) or \
           ('time' in row_str and 'active power+' in row_str):
            header_row_idx = i
            break
            
    if header_row_idx == -1:
        return None
        
    cols = df_raw.iloc[header_row_idx].fillna('').astype(str).str.lower().str.strip().tolist()
    df = df_raw.iloc[header_row_idx+1:].reset_index(drop=True)
    df.columns = cols
    
    date_col, clock_col, kw_col, v_col = None, None, None, None
    for c in df.columns:
        c_clean = c.replace(' ', '').replace('.', '').replace('_', '')
        if c_clean == 'date': date_col = c
        elif 'clock' in c_clean or 'ch1' == c_clean or 'time' in c_clean: clock_col = c
        elif ('import' in c_clean and 'kw' in c_clean) or 'ch4' == c_clean or 'activepower+' in c_clean: kw_col = c
        elif 'voltage' in c_clean or 'ch3' == c_clean: v_col = c
        
    if not clock_col or not kw_col:
        return None
        
    invalid_vals = ['total', 'p', 'op', 'h', 'kwh', 'nan', '']
    
    if date_col:
        mask = df[date_col].astype(str).str.strip().str.lower().isin(invalid_vals)
        df = df[~mask]
        df['Merged_Clock'] = df[date_col].astype(str).str.strip() + ' ' + df[clock_col].astype(str).str.strip()
        clock_col = 'Merged_Clock'
    else:
        mask = df[clock_col].astype(str).str.strip().str.lower().isin(invalid_vals)
        df = df[~mask]
        
    out_df = pd.DataFrame()
    out_df['Clock'] = df[clock_col]
    out_df['kW_Import'] = df[kw_col]
    out_df['Voltage'] = df[v_col] if v_col else 220.0
    return out_df

@st.cache_data
def load_file(uploaded_file, file_ext):
    bytes_data = uploaded_file.getvalue()
    df_result = None
    
    # 1. ลองใช้ Pandas อ่านแบบ CSV ก่อนเลย (แก้ปัญหาไฟล์ที่มี Newline ในช่องตาราง เช่น "\n" ระหว่างบรรทัดได้อย่างสมบูรณ์)
    if df_result is None:
        try:
            try:
                df_raw = pd.read_csv(io.BytesIO(bytes_data), encoding='utf-8-sig', header=None, on_bad_lines='skip')
            except:
                df_raw = pd.read_csv(io.BytesIO(bytes_data), encoding='cp874', header=None, on_bad_lines='skip')
            df_result = parse_excel_df(df_raw)
        except Exception:
            pass
            
    # 2. ลองสกัดข้อมูลจากการอ่านเป็นบรรทัด (แก้ปัญหาไฟล์ตารางเบี้ยวได้อย่างเด็ดขาด)
    if df_result is None:
        try:
            try:
                string_data = bytes_data.decode("utf-8-sig")
            except:
                string_data = bytes_data.decode("cp874", errors='ignore')
                
            lines = string_data.splitlines()
            df_result = parse_text_lines(lines, delimiter=',')
        except Exception:
            pass
            
    # 3. หากสกัดแบบบรรทัดล้มเหลว (เช่นเป็นไฟล์ .xlsx Binary) ค่อยอ่านแบบ Excel
    if df_result is None and file_ext in ['xlsx', 'xls']:
        try:
            engine = 'openpyxl' if file_ext == 'xlsx' else 'xlrd'
            df_raw = pd.read_excel(io.BytesIO(bytes_data), engine=engine, header=None)
            df_result = parse_excel_df(df_raw)
        except:
            try:
                dfs = pd.read_html(io.BytesIO(bytes_data), encoding='utf-8')
                if dfs:
                    df_result = parse_excel_df(dfs[0])
            except:
                pass
                
    if df_result is None or df_result.empty:
        raise ValueError("อ่านไฟล์ไม่สำเร็จ โครงสร้างไฟล์ผิดปกติหรือไม่พบข้อมูลเวลา")
        
    return df_result

@st.cache_data
def preprocess_data(df):
    if df is None or df.empty:
        return pd.DataFrame()
        
    df = df.copy()
    
    # 🧹 ล้างข้อมูลให้เหลือเฉพาะตัวเลข
    df['kW_Import'] = df['kW_Import'].astype(str).str.replace(r'[^\d.]', '', regex=True)
    df['kW_Import'] = pd.to_numeric(df['kW_Import'], errors='coerce').fillna(0)
    
    df['Voltage'] = df['Voltage'].astype(str).str.replace(r'[^\d.]', '', regex=True)
    df['Voltage'] = pd.to_numeric(df['Voltage'], errors='coerce').fillna(220.0)
    
    # 📅 แปลงเวลา
    df['Clock'] = pd.to_datetime(df['Clock'], dayfirst=True, errors='coerce')
    df = df.dropna(subset=['Clock']).reset_index(drop=True)
    
    # 🛡️ ป้องกันไฟล์ทับกัน (เก็บค่า kW ที่มีข้อมูลจริง > 0 เอาไว้เสมอ)
    df = df.sort_values(['Clock', 'kW_Import'], ascending=[True, False])
    df = df.drop_duplicates(subset=['Clock'], keep='first').reset_index(drop=True)
    df = df.sort_values('Clock').reset_index(drop=True)
    
    if df.empty:
        return pd.DataFrame()
        
    df['Date'] = df['Clock'].dt.date
    df['Month'] = df['Clock'].dt.strftime('%Y-%m')
    df['Time_Str'] = df['Clock'].dt.strftime('%H:%M')
    df['kWh_15min'] = df['kW_Import'] / 4.0
    
    return df

def get_usage_snapshots(df):
    snapshots = []
    in_session = False
    start_idx = None
    
    for idx, row in df.iterrows():
        if row['kW_Import'] > 0 and not in_session:
            in_session = True; start_idx = idx
        elif row['kW_Import'] <= 0 and in_session:
            in_session = False; snapshots.append((start_idx, idx)) 
            
    if in_session: snapshots.append((start_idx, len(df)-1))
        
    session_list = []
    for i, (s_idx, e_idx) in enumerate(snapshots):
        pad_s = max(0, s_idx - 1)
        pad_e = min(len(df)-1, e_idx)
        s_time = df.loc[pad_s, 'Clock'].strftime('%d/%m/%y %H:%M')
        e_time = df.loc[pad_e, 'Clock'].strftime('%d/%m/%y %H:%M')
        session_list.append({
            'label': f"⚡ รอบที่ {i+1}: {s_time} ถึง {e_time}",
            'start_idx': pad_s, 'end_idx': pad_e
        })
    return session_list