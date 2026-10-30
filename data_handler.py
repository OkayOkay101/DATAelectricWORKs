import pandas as pd
import streamlit as st
import numpy as np
import io
import logging

# ค่าคงที่สำหรับกรองข้อมูลที่ผิดปกติ (Outliers)
DEFAULT_OUTLIER_KW_MAX = 2000000
DEFAULT_OUTLIER_V_MAX = 2000000

# ค่าคงที่สำหรับความปลอดภัยและการตรวจสอบไฟล์นำเข้า
ALLOWED_EXTENSIONS = {'csv', 'xlsx', 'xls', 'txt'}
MAX_FILE_SIZE_BYTES = 50 * 1024 * 1024  # 50 MB


def is_header_row(row_str):
    if not isinstance(row_str, str):
        row_str = str(row_str) if row_str is not None else ""
    l_lower = row_str.lower()
    return (('clock' in l_lower and 'import' in l_lower) or
           ('ch1' in l_lower and 'ch4' in l_lower) or
           ('date' in l_lower and ('clock' in l_lower or 'time' in l_lower)) or
           ('pea no' in l_lower and 'clock' in l_lower) or
           ('pea no' in l_lower and ('clock' in l_lower or 'datatime' in l_lower or 'datetime' in l_lower)) or
           (('datatime' in l_lower or 'datetime' in l_lower) and ('import' in l_lower or 'kw' in l_lower)) or
           ('time' in l_lower and (('active' in l_lower and 'power' in l_lower) or 'kw' in l_lower or 'import' in l_lower)) or
           ('เวลา' in l_lower and 'พลังงาน' in l_lower) or
           ('วันที่' in l_lower and 'เวลา' in l_lower) or
           ('เวลา' in l_lower and 'kw' in l_lower))

def parse_text_lines(lines, delimiter=','):
    iterator = iter(lines)
    header_row_idx = -1
    buffered_header = []

    # 1. ค้นหาบรรทัดที่เป็นหัวตาราง
    for i in range(50):
        try:
            line = next(iterator)
        except StopIteration:
            break
        buffered_header.append(line)
        if is_header_row(line):
            header_row_idx = i
            if '\t' in line and ',' not in line:
                delimiter = '\t'
            elif ';' in line and ',' not in line:
                delimiter = ';'
            break
            
    if header_row_idx == -1:
        return None
        
    header_line = buffered_header[header_row_idx]
    
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
    buffered_data = []
    if kw_idx_candidates:
        if len(kw_idx_candidates) == 1:
            kw_idx = kw_idx_candidates[0]
        else:
            for _ in range(20):
                try:
                    buffered_data.append(next(iterator))
                except StopIteration:
                    break

            # 🎯 แก้ปัญหาข้อมูลศูนย์: สแกนข้อมูล 20 บรรทัดแรก เพื่อดูว่าคอลัมน์ไหน (Import/Export) มีข้อมูลใช้งานได้จริง
            best_idx = kw_idx_candidates[0]
            max_val = -1
            for cand_idx in kw_idx_candidates:
                cand_sum = 0
                for line in buffered_data:
                    parts = [p.strip() for p in (line.split() if delimiter == 'space' else line.split(delimiter))]
                    if cand_idx < len(parts):
                        val = parts[cand_idx].replace(',', '')
                        try:
                            cand_sum += float(val)
                        except Exception as e:
                            pass
                if cand_sum > max_val:
                    max_val = cand_sum
                    best_idx = cand_idx
            kw_idx = best_idx
            
    if clock_idx == -1 or kw_idx == -1:
        return None
        
    # 3. สกัดข้อมูลทีละบรรทัด
    data_rows = []

    def line_generator():
        for line in buffered_data:
            yield line
        for line in iterator:
            yield line

    class IteratorStream(io.TextIOBase):
        def __init__(self, it):
            self.it = it
            self.leftover = ''
            
        def read(self, size=-1):
            if size == -1:
                parts = []
                for line in self.it:
                    line = str(line)
                    if not line.endswith('\n'):
                        line += '\n'
                    parts.append(line)
                res = self.leftover + ''.join(parts)
                self.leftover = ''
                return res
            
            res = [self.leftover]
            current_len = len(self.leftover)
            while current_len < size:
                try:
                    line = str(next(self.it))
                    if not line.endswith('\n'):
                        line += '\n'
                    res.append(line)
                    current_len += len(line)
                except StopIteration:
                    break
            full_str = ''.join(res)
            self.leftover = full_str[size:]
            return full_str[:size]

        def readline(self, size=-1):
            if self.leftover:
                if '\n' in self.leftover:
                    idx = self.leftover.find('\n')
                    line = self.leftover[:idx + 1]
                    self.leftover = self.leftover[idx + 1:]
                    return line
                prefix = self.leftover
                self.leftover = ''
            else:
                prefix = ''

            try:
                line = str(next(self.it))
                if not line.endswith('\n'):
                    line += '\n'
                return prefix + line
            except StopIteration:
                return prefix

    stream = IteratorStream(line_generator())
    sep = r'\s+' if delimiter == 'space' else delimiter
    try:
        df_raw = pd.read_csv(
            stream,
            sep=sep,
            header=None,
            dtype=str,
            on_bad_lines='skip',
            engine='python' if sep == r'\s+' else 'c'
        )
    except Exception:
        return pd.DataFrame(columns=['Clock', 'kW_Import', 'Voltage'])

    if df_raw.empty:
        return pd.DataFrame(columns=['Clock', 'kW_Import', 'Voltage'])

    def get_col(idx, default_val):
        if idx != -1 and idx < len(df_raw.columns):
            return df_raw.iloc[:, idx].fillna('').astype(str).str.strip()
        return pd.Series([default_val] * len(df_raw))

    d_col = get_col(date_idx, "")
    c_col = get_col(clock_idx, "")
    kw_col = get_col(kw_idx, "0").replace('', '0')
    v_col = get_col(v_idx, "220").replace('', '220')

    d_lower = d_col.str.lower()
    c_lower = c_col.str.lower()

    mask_d = pd.Series(True, index=df_raw.index)
    if date_idx != -1:
        has_invalid_d = d_lower.str.contains('total|p|op|h|kwh|nan', regex=True, na=False)
        mask_d = ~(has_invalid_d | (d_lower == ''))

    has_invalid_c = c_lower.str.contains('total|p|op|h|kwh|nan|dnv/err', regex=True, na=False)
    mask_c = ~(has_invalid_c | (c_lower == ''))

    valid_mask = mask_c & mask_d

    valid_d = d_col[valid_mask]
    valid_c = c_col[valid_mask]

    if date_idx != -1:
        merged_clock = (valid_d + " " + valid_c).str.strip()
    else:
        merged_clock = valid_c.str.strip()

    out_df = pd.DataFrame({
        'Clock': merged_clock,
        'kW_Import': kw_col[valid_mask],
        'Voltage': v_col[valid_mask]
    })

    return out_df.reset_index(drop=True)

def parse_excel_df(df_raw):
    """สำหรับอ่านไฟล์ตาราง (Excel) หรือรับต่อจาก pd.read_csv()"""
    header_row_idx = -1
    for i in range(min(50, len(df_raw))):
        row_str = ' '.join(df_raw.iloc[i].fillna('').astype(str))
        if is_header_row(row_str):
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
        c_str = str(c)
        c_clean = c_str.replace(' ', '').replace('.', '').replace('_', '').replace('(', '').replace(')', '').replace('\n', '')
        
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
                # ลองหาผลรวมของคอลัมน์เพื่อดูว่ามีข้อมูลจริงหรือไม่ (ถ้าเป็น 0 แสดงว่ากราฟแบน) - ⚡ Bolt: sample first 1000 rows
                cand_sum = pd.to_numeric(df[cand].head(1000).astype(str).str.replace(r'[^\d.-]', '', regex=True), errors='coerce').fillna(0).sum()
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
    if not file_ext or not isinstance(file_ext, str):
        raise ValueError("ไม่พบนามสกุลไฟล์ที่ถูกต้อง")

    clean_ext = file_ext.lower().lstrip('.')
    if clean_ext not in ALLOWED_EXTENSIONS:
        raise ValueError(
            f"ไม่อนุญาตให้อัปโหลดไฟล์นามสกุล .{clean_ext} (รองรับเฉพาะ: {', '.join(sorted(ALLOWED_EXTENSIONS))})"
        )

    # ตรวจสอบขนาดไฟล์เพื่อป้องกัน Denial of Service (DoS / Resource Exhaustion)
    file_size = getattr(uploaded_file, 'size', None)
    if file_size is None and hasattr(uploaded_file, 'getbuffer'):
        try:
            file_size = uploaded_file.getbuffer().nbytes
        except Exception:
            file_size = None
    if file_size is not None and file_size > MAX_FILE_SIZE_BYTES:
        raise ValueError(f"ขนาดไฟล์เกินกำหนด (สูงสุด {MAX_FILE_SIZE_BYTES // (1024 * 1024)} MB)")

    df_result = None

    # 1. หากเป็นไฟล์ Excel (.xlsx, .xls) หรือ HTML ให้ลองอ่านด้วย Excel engine ก่อน
    if clean_ext in ['xlsx', 'xls']:
        try:
            engine = 'openpyxl' if clean_ext == 'xlsx' else 'xlrd'
            uploaded_file.seek(0)
            df_raw = pd.read_excel(uploaded_file, engine=engine, header=None)
            df_result = parse_excel_df(df_raw)
        except Exception as e:
            logging.warning(f"Failed to read excel with {engine}: {e}")
            try:
                uploaded_file.seek(0)
                dfs = pd.read_html(uploaded_file, encoding='utf-8')
                if dfs:
                    df_result = parse_excel_df(dfs[0])
            except Exception as e:
                logging.warning(f"Failed to read html: {e}")

    # 2. หากเป็นไฟล์ CSV หรือ TXT
    if df_result is None and clean_ext in ['csv', 'txt']:
        # 2.1 ลองใช้ Pandas โดยตั้งค่า names=range(50)
        try:
            try:
                uploaded_file.seek(0)
                df_raw = pd.read_csv(uploaded_file, encoding='utf-8-sig', names=range(50), dtype=str, low_memory=False)
            except Exception as e:
                logging.warning(f"Failed to read CSV with utf-8-sig: {e}")
                uploaded_file.seek(0)
                df_raw = pd.read_csv(uploaded_file, encoding='cp874', names=range(50), dtype=str, low_memory=False)
            df_result = parse_excel_df(df_raw)
        except Exception as e:
            logging.warning(f"Failed to parse CSV with pandas: {e}")

        # 2.2 ลองอ่านแบบ Text บรรทัดต่อบรรทัด
        if df_result is None:
            encodings_to_try = ['utf-8-sig', 'cp874', 'utf-16', 'utf-16le', 'tis-620']
            for enc in encodings_to_try:
                try:
                    uploaded_file.seek(0)
                    text_stream = io.TextIOWrapper(uploaded_file, encoding=enc)
                    head = text_stream.read(100)
                    if len(head) > 0 and '\x00' not in head:
                        uploaded_file.seek(0)
                        text_stream.detach()
                        text_stream = io.TextIOWrapper(uploaded_file, encoding=enc)
                        df_result = parse_text_lines(text_stream, delimiter=',')
                        text_stream.detach()
                        if df_result is not None and not df_result.empty:
                            break
                    else:
                        text_stream.detach()
                except Exception as e:
                    logging.warning(f"Failed to read text lines with encoding {enc}: {e}")
                    if 'text_stream' in locals() and not text_stream.closed:
                        try:
                            text_stream.detach()
                        except Exception:
                            pass

    if df_result is None or df_result.empty:
        raise ValueError("อ่านไฟล์ไม่สำเร็จ โครงสร้างไฟล์ผิดปกติหรือไม่พบข้อมูลเวลา")

    return df_result

COMMON_DATETIME_FORMATS = (
    "%d/%m/%Y %H:%M",
    "%d/%m/%Y %H:%M:%S",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%d-%m-%Y %H:%M",
    "%d-%m-%Y %H:%M:%S",
    "%Y/%m/%d %H:%M",
    "%Y/%m/%d %H:%M:%S",
    "%d/%m/%Y",
    "%Y-%m-%d",
    "%d/%m/%y %H:%M",
    "%d/%m/%y %H:%M:%S",
)

def fast_parse_datetime(series, dayfirst=True):
    """
    ⚡ Bolt Optimization: Fast vectorized datetime parser using common formats.
    Instead of slow element-by-element dateutil parsing with format='mixed' (which takes >30s for 200k rows),
    attempt fast C-level strptime parsing with prioritized format candidates.
    If any non-null rows fail to parse (e.g. malformed or mixed formats), patch only those failed rows.
    """
    if pd.api.types.is_datetime64_any_dtype(series):
        return series

    if len(series) == 0:
        return pd.to_datetime(series, dayfirst=dayfirst, errors='coerce', format='mixed')

    valid_samples = series.dropna()
    if valid_samples.empty:
        return pd.to_datetime(series, dayfirst=dayfirst, errors='coerce', format='mixed')

    # Find the first non-empty string sample to prioritize candidate formats
    first_val = ""
    for v in valid_samples:
        s_val = str(v).strip()
        if s_val:
            first_val = s_val
            break

    if not first_val:
        return pd.to_datetime(series, dayfirst=dayfirst, errors='coerce', format='mixed')

    candidates = list(COMMON_DATETIME_FORMATS)
    if "-" in first_val and len(first_val) >= 4 and first_val[:4].isdigit():
        candidates.sort(key=lambda fmt: 0 if fmt.startswith("%Y-%m-%d") else 1)
    elif "/" in first_val and len(first_val) >= 4 and first_val[:4].isdigit():
        candidates.sort(key=lambda fmt: 0 if fmt.startswith("%Y/%m/%d") else 1)
    elif "/" in first_val:
        candidates.sort(key=lambda fmt: 0 if fmt.startswith("%d/%m/%Y") else 1)
    elif "-" in first_val:
        candidates.sort(key=lambda fmt: 0 if fmt.startswith("%d-%m-%Y") else 1)

    parsed = None
    for fmt in candidates:
        try:
            res = pd.to_datetime(series, format=fmt, errors='coerce')
            success_count = res.notna().sum()
            if success_count > 0:
                mask_failed = res.isna() & (~series.isna()) & (series.astype(str).str.strip() != '')
                if not mask_failed.any():
                    parsed = res
                    break
                elif success_count >= len(valid_samples) * 0.5:
                    res.loc[mask_failed] = pd.to_datetime(
                        series.loc[mask_failed],
                        dayfirst=dayfirst,
                        errors='coerce',
                        format='mixed'
                    )
                    parsed = res
                    break
        except Exception:
            continue

    if parsed is None:
        parsed = pd.to_datetime(series, dayfirst=dayfirst, errors='coerce', format='mixed')

    return parsed

@st.cache_data
def preprocess_data(df, kw_max=DEFAULT_OUTLIER_KW_MAX, v_max=DEFAULT_OUTLIER_V_MAX):
    if df is None or df.empty:
        return pd.DataFrame()
        
    df = df.copy()
    
    # ล้างข้อมูลให้เหลือเฉพาะตัวเลข
    # ⚡ Bolt Optimization: Attempt to_numeric first, and only use regex cleanup for failed values
    num_kw = pd.to_numeric(df['kW_Import'], errors='coerce')
    mask_kw = num_kw.isna()
    if mask_kw.any():
        clean_str_kw = df.loc[mask_kw, 'kW_Import'].astype(str).str.replace(r'[^\d.-]', '', regex=True)
        num_kw.loc[mask_kw] = pd.to_numeric(clean_str_kw, errors='coerce')
    df['kW_Import'] = num_kw.fillna(0)
    
    num_v = pd.to_numeric(df['Voltage'], errors='coerce')
    mask_v = num_v.isna()
    if mask_v.any():
        clean_str_v = df.loc[mask_v, 'Voltage'].astype(str).str.replace(r'[^\d.-]', '', regex=True)
        num_v.loc[mask_v] = pd.to_numeric(clean_str_v, errors='coerce')
    df['Voltage'] = num_v.fillna(220.0)
    
    # ตัด Outlier (แสดงเตือนแทนการลบทิ้ง)
    outlier_mask = (df['kW_Import'] >= kw_max) | (df['Voltage'] >= v_max)
    if outlier_mask.any():
        st.warning(f"พบข้อมูลที่มีค่าสูงผิดปกติ (>= {kw_max:,}) จำนวน {outlier_mask.sum()} แถว ระบบจะไม่ลบทิ้ง โปรดตรวจสอบความถูกต้อง")
    
    # แปลงเวลา
    # ⚡ Bolt Optimization: Use fast_parse_datetime instead of slow format='mixed'
    df['Clock'] = fast_parse_datetime(df['Clock'], dayfirst=True)
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
        clock_series = fast_parse_datetime(clock_series, dayfirst=True)

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

def test_regression_negative_values():
    import pandas as pd
    df = pd.DataFrame({'Clock': ['01/01/2023 00:15'], 'kW_Import': ['-100,500.5'], 'Voltage': ['220']})
    res = preprocess_data(df)
    assert res.iloc[0]['kW_Import'] == -100500.5

def test_regression_space_delimiter():
    import pandas as pd
    lines = [
        "Date Clock kW_Import Voltage",
        "01/01/2023 00:15 100.5 220",
        "01/01/2023 00:30 110.2 221"
    ]
    df = parse_text_lines(lines, delimiter='space')
    assert df is not None and not df.empty
    assert len(df) == 2
    assert df.iloc[0]['kW_Import'] == '100.5'

def test_regression_high_load_outlier():
    import pandas as pd
    df = pd.DataFrame({'Clock': ['01/01/2023 00:15'], 'kW_Import': ['2500000'], 'Voltage': ['220']})
    res = preprocess_data(df)
    assert len(res) == 1
    assert res.iloc[0]['kW_Import'] == 2500000