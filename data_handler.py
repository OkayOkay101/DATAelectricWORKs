import pandas as pd
import streamlit as st
import numpy as np
import io


def parse_text_lines(lines, delimiter=','):
    header_row_idx = -1
    # 1. ค้นหาบรรทัดที่เป็นหัวตาราง
    for i, line in enumerate(lines[:50]):
        l_lower = line.lower()
        if ('clock' in l_lower and 'import' in l_lower) or \
           ('ch1' in l_lower and 'ch4' in l_lower) or \
           ('date' in l_lower and 'clock' in l_lower) or \
           ('pea no' in l_lower and 'clock' in l_lower) or \
           ('pea no' in l_lower and 'datatime' in l_lower) or \
           ('datatime' in l_lower and 'import' in l_lower and 'kw' in l_lower) or \
           ('time' in l_lower and 'active' in l_lower and 'power' in l_lower) or \
           ('เวลา' in l_lower and 'พลังงาน' in l_lower) or \
           ('วันที่' in l_lower and 'เวลา' in l_lower) or \
           ('เวลา' in l_lower and 'kw' in l_lower):
            header_row_idx = i
            if '\t' in line and ',' not in line:
                delimiter = '\t'
            elif ';' in line and ',' not in line:
                delimiter = ';'
            break
            
    if header_row_idx == -1:
        return None
        
    header_line = lines[header_row_idx]
    
    if delimiter == ',' and ',' not in header_line:
        cols = [c.strip().lower() for c in header_line.split()]
        delimiter = 'space'
    elif delimiter == 'space':
        cols = [c.strip().lower() for c in header_line.split()]
    else:
        cols = [c.strip().lower() for c in header_line.split(delimiter)]
        
    # 2. ค้นหา Index ของคอลัมน์
    date_idx, clock_idx, v_idx = -1, -1, -1
    kw_idx_candidates = []
    
    for i, c in enumerate(cols):
        c_clean = c.replace(' ', '').replace('.', '').replace('_', '').replace('(', '').replace(')', '').replace('\n', '')
        
        if c_clean == 'date' or 'วันที่' in c_clean: 
            date_idx = i
        elif 'clock' in c_clean or 'ch1' == c_clean or 'time' in c_clean or 'datatime' in c_clean or 'เวลา' in c_clean: 
            clock_idx = i
        elif 'voltage' in c_clean or 'ch3' == c_clean or 'แรงดัน' in c_clean or c_clean == 'v' or 'volt' in c_clean: 
            v_idx = i
        
        # เพิ่มระบบค้นหาคอลัมน์พลังงานแบบหว่านแห (ทั้ง Import, Export และ Active Power)
        if ('kw' in c_clean and 'demand' in c_clean) or \
           ('import' in c_clean and 'kw' in c_clean) or \
           ('export' in c_clean and 'kw' in c_clean) or \
           'ch4' == c_clean or \
           ('active' in c_clean and 'power' in c_clean) or \
           'พลังงาน' in c_clean or \
           'กำลังไฟฟ้า' in c_clean or \
           c_clean == 'kw': 
            kw_idx_candidates.append(i)
    
    kw_idx = -1
    if kw_idx_candidates:
        if len(kw_idx_candidates) == 1:
            kw_idx = kw_idx_candidates[0]
        else:
            # 🎯 แก้ปัญหาข้อมูลศูนย์: สแกนข้อมูล 20 บรรทัดแรก เพื่อดูว่าคอลัมน์ไหน (Import/Export) มีข้อมูลใช้งานได้จริง
            best_idx = kw_idx_candidates[0]
            max_val = -1
            for cand_idx in kw_idx_candidates:
                cand_sum = 0
                for line in lines[header_row_idx+1:header_row_idx+21]:
                    parts = [p.strip() for p in line.split(delimiter)]
                    if cand_idx < len(parts):
                        val = parts[cand_idx].replace(',', '')
                        try:
                            cand_sum += float(val)
                        except:
                            pass
                if cand_sum > max_val:
                    max_val = cand_sum
                    best_idx = cand_idx
            kw_idx = best_idx
            
    if clock_idx == -1 or kw_idx == -1:
        return None
        
    # 3. สกัดข้อมูลทีละบรรทัด
    data_rows = []
    for line in lines[header_row_idx+1:]:
        line = line.strip()
        if not line: continue
        
        parts = [p.strip() for p in line.split(delimiter)]
        
        if date_idx != -1 and date_idx < len(parts):
            d_val = parts[date_idx].lower()
            if any(x in d_val for x in ['total', 'p', 'op', 'h', 'kwh', 'nan']) or not d_val:
                continue
        
        if clock_idx < len(parts):
            c_val = parts[clock_idx].lower()
            if any(x in c_val for x in ['total', 'p', 'op', 'h', 'kwh', 'nan', 'dnv/err']) or not c_val:
                continue
                
            date_val = parts[date_idx] if date_idx != -1 and date_idx < len(parts) else ""
            clock_val = parts[clock_idx]
            kw_val = parts[kw_idx] if kw_idx < len(parts) else "0"
            v_val = parts[v_idx] if v_idx != -1 and v_idx < len(parts) else "220"
            
            merged_clock = f"{date_val} {clock_val}" if date_val else clock_val
            data_rows.append([merged_clock, kw_val, v_val])
            
    return pd.DataFrame(data_rows, columns=['Clock', 'kW_Import', 'Voltage'])

def parse_excel_df(df_raw):
    """สำหรับอ่านไฟล์ตาราง (Excel) หรือรับต่อจาก pd.read_csv()"""
    header_row_idx = -1
    for i in range(min(50, len(df_raw))):
        row_str = ' '.join(df_raw.iloc[i].fillna('').astype(str)).lower()
        if ('clock' in row_str and 'import' in row_str) or \
           ('ch1' in row_str and 'ch4' in row_str) or \
           ('date' in row_str and 'clock' in row_str) or \
           ('pea no' in row_str and 'clock' in row_str) or \
           ('pea no' in row_str and 'datatime' in row_str) or \
           ('datatime' in row_str and 'import' in row_str and 'kw' in row_str) or \
           ('time' in row_str and 'active' in row_str and 'power' in row_str) or \
           ('เวลา' in row_str and 'พลังงาน' in row_str) or \
           ('วันที่' in row_str and 'เวลา' in row_str) or \
           ('เวลา' in row_str and 'kw' in row_str):
            header_row_idx = i
            break
            
    if header_row_idx == -1:
        return None
        
    cols = df_raw.iloc[header_row_idx].fillna('').astype(str).str.lower().str.strip().tolist()
    
    # ป้องกัน Error คอลัมน์ชื่อซ้ำกัน (Duplicate Columns) จากไฟล์ขยะ
    new_cols = []
    for j, c in enumerate(cols):
        base = c if c not in ['', 'nan', 'none'] else f"unnamed_{j}"
        while base in new_cols:
            base += f"_{j}"
        new_cols.append(base)
        
    df = df_raw.iloc[header_row_idx+1:].reset_index(drop=True)
    df.columns = new_cols
    
    date_col, clock_col, v_col = None, None, None
    kw_candidates = []
    
    for c in df.columns:
        c_clean = c.replace(' ', '').replace('.', '').replace('_', '').replace('(', '').replace(')', '').replace('\n', '')
        
        if c_clean == 'date' or 'วันที่' in c_clean: 
            date_col = c
        elif 'clock' in c_clean or 'ch1' == c_clean or 'time' in c_clean or 'datatime' in c_clean or 'เวลา' in c_clean: 
            clock_col = c
        elif 'voltage' in c_clean or 'ch3' == c_clean or 'แรงดัน' in c_clean or c_clean == 'v' or 'volt' in c_clean: 
            v_col = c
        
        # 🎯 เก็บผู้ท้าชิงคอลัมน์พลังงานทั้งหมด (ทั้ง Import และ Export)
        if ('kw' in c_clean and 'demand' in c_clean) or \
           ('import' in c_clean and 'kw' in c_clean) or \
           ('export' in c_clean and 'kw' in c_clean) or \
           'ch4' == c_clean or \
           ('active' in c_clean and 'power' in c_clean and '+' in c_clean) or \
           ('active' in c_clean and 'power' in c_clean) or \
           'พลังงาน' in c_clean or \
           'กำลังไฟฟ้า' in c_clean or \
           c_clean == 'kw': 
            kw_candidates.append(c)
            
    kw_col = None
    if kw_candidates:
        if len(kw_candidates) == 1:
            kw_col = kw_candidates[0]
        else:
            # 🎯 แก้ปัญหาข้อมูลศูนย์: เลือกรวมคอลัมน์ที่มีข้อมูลเยอะที่สุด (หาค่า Sum สูงสุดระหว่าง Import กับ Export)
            max_sum = -1
            best_col = kw_candidates[0]
            for cand in kw_candidates:
                # ลองหาผลรวมของคอลัมน์เพื่อดูว่ามีข้อมูลจริงหรือไม่ (ถ้าเป็น 0 แสดงว่ากราฟแบน)
                cand_sum = pd.to_numeric(df[cand].astype(str).str.replace(r'[^\d.]', '', regex=True), errors='coerce').fillna(0).sum()
                if cand_sum > max_sum:
                    max_sum = cand_sum
                    best_col = cand
            kw_col = best_col
        
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
    
    # 1. ลองใช้ Pandas โดยตั้งค่า names=range(50) 
    if df_result is None:
        try:
            try:
                df_raw = pd.read_csv(io.BytesIO(bytes_data), encoding='utf-8-sig', names=range(50), dtype=str, low_memory=False)
            except:
                df_raw = pd.read_csv(io.BytesIO(bytes_data), encoding='cp874', names=range(50), dtype=str, low_memory=False)
            df_result = parse_excel_df(df_raw)
        except Exception:
            pass
            
    # 2. ลองอ่านแบบ Text บรรทัดต่อบรรทัด 
    if df_result is None:
        encodings_to_try = ['utf-8-sig', 'cp874', 'utf-16', 'utf-16le', 'tis-620']
        for enc in encodings_to_try:
            try:
                string_data = bytes_data.decode(enc)
                if len(string_data) > 0 and '\x00' not in string_data[:100]:
                    lines = string_data.splitlines()
                    df_result = parse_text_lines(lines, delimiter=',')
                    if df_result is not None and not df_result.empty:
                        break
            except:
                pass
            
    # 3. หากเป็นไฟล์ .xls (Binary) หรือ HTML 
    if df_result is None and file_ext in ['xlsx', 'xls', 'csv']:
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
    
    # ล้างข้อมูลให้เหลือเฉพาะตัวเลข
    # ⚡ Bolt Optimization: Attempt to_numeric first, and only use regex cleanup for failed values
    num_kw = pd.to_numeric(df['kW_Import'], errors='coerce')
    mask_kw = num_kw.isna()
    if mask_kw.any():
        clean_str_kw = df.loc[mask_kw, 'kW_Import'].astype(str).str.replace(r'[^\d.]', '', regex=True)
        num_kw.loc[mask_kw] = pd.to_numeric(clean_str_kw, errors='coerce')
    df['kW_Import'] = num_kw.fillna(0)
    
    num_v = pd.to_numeric(df['Voltage'], errors='coerce')
    mask_v = num_v.isna()
    if mask_v.any():
        clean_str_v = df.loc[mask_v, 'Voltage'].astype(str).str.replace(r'[^\d.]', '', regex=True)
        num_v.loc[mask_v] = pd.to_numeric(clean_str_v, errors='coerce')
    df['Voltage'] = num_v.fillna(220.0)
    
    # ตัด Outlier
    df = df[(df['kW_Import'] < 2000000) & (df['Voltage'] < 2000000)]
    
    # แปลงเวลา
    df['Clock'] = pd.to_datetime(df['Clock'], dayfirst=True, errors='coerce')
    df = df.dropna(subset=['Clock']).reset_index(drop=True)
    
    # ป้องกันไฟล์ทับกัน
    df = df.sort_values(['Clock', 'kW_Import'], ascending=[True, False])
    df = df.drop_duplicates(subset=['Clock'], keep='first').reset_index(drop=True)
    
    if df.empty:
        return pd.DataFrame()
        
    df['Date'] = df['Clock'].dt.normalize()

    # ⚡ Bolt: Format month/time with vectorized slicing while preserving midnight and missing values
    clock_str = df['Clock'].astype(str)

    month_series = clock_str.str.slice(0, 7)
    time_series = clock_str.str.slice(11, 16).replace('', '00:00')

    # Handle NaT explicitly to avoid literal 'NaT' strings or empty string replacements
    is_nat = df['Clock'].isna()
    if is_nat.any():
        month_series.loc[is_nat] = np.nan
        time_series.loc[is_nat] = np.nan

    df['Month'] = month_series
    df['Time_Str'] = time_series

    df['kWh_15min'] = df['kW_Import'] / 4.0
    
    return df


def get_usage_snapshots(df):
    if df is None or df.empty:
        return []

    kw_array = df['kW_Import'].to_numpy()
    
    is_positive = kw_array > 0
    padded = np.concatenate(([False], is_positive, [False]))
    diff = np.diff(padded.astype(np.int8))

    starts = np.where(diff == 1)[0]
    ends = np.where(diff == -1)[0]

    if len(starts) == 0:
        return []
        
    df_len = len(df)

    pad_s_array = np.maximum(0, starts - 1)

    ends_adjusted = np.where(ends < df_len, ends, df_len - 1)
    pad_e_array = np.minimum(df_len - 1, ends_adjusted)

    clock_series = df['Clock']
    if not pd.api.types.is_datetime64_any_dtype(clock_series):
        clock_series = pd.to_datetime(clock_series)

    # Fast vectorized format %d/%m/%y %H:%M -> e.g. 2026-01-01 00:00:00 -> 01/01/26 00:00
    c_str = clock_series.astype(str)
    # yyyy-mm-dd hh:mm:ss -> dd/mm/yy hh:mm
    formatted_times = c_str.str.slice(8, 10) + '/' + c_str.str.slice(5, 7) + '/' + c_str.str.slice(2, 4) + ' ' + c_str.str.slice(11, 16)

    s_times = formatted_times.iloc[pad_s_array].to_numpy()
    e_times = formatted_times.iloc[pad_e_array].to_numpy()

    session_list = []
    for i in range(len(starts)):
        pad_s = int(pad_s_array[i])
        pad_e = int(pad_e_array[i])

        session_list.append({
            'label': f"⚡ รอบที่ {i+1}: {s_times[i]} ถึง {e_times[i]}",
            'start_idx': pad_s,
            'end_idx': pad_e
        })

    return session_list