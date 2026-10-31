import pandas as pd
import streamlit as st
import numpy as np
import io
import logging
import re
import zipfile

# ค่าคงที่สำหรับป้องกัน CSV / Formula Injection (CWE-1236)
PURE_NUMBER_PATTERN = re.compile(r'^[+-]?\d+(\.\d+)?([eE][+-]?\d+)?$')
DANGEROUS_FORMULA_PREFIXES = ('=', '@', '\t', '\r', '|', '%')


class UploadValidationError(ValueError):
    """
    ข้อผิดพลาดจากการตรวจสอบไฟล์ที่ "เราสร้างข้อความเอง" และปลอดภัยต่อการแสดงบน UI
    แยกออกจาก ValueError ทั่วไป (เช่น จากไลบรารีภายนอก) เพื่อไม่ให้ข้อความภายใน
    ที่อาจมี path หรือรายละเอียดระบบรั่วไหลออกหน้าจอ (CWE-209)
    """


GENERIC_LOAD_ERROR_REASON = "รูปแบบไฟล์ไม่รองรับ หรือไฟล์อาจเสียหาย"
MAX_ERROR_REASON_LENGTH = 300


def safe_error_reason(exc):
    """
    คืนข้อความอธิบายข้อผิดพลาดที่ปลอดภัยต่อการแสดงผลบน UI
    - แสดงเฉพาะข้อความจาก UploadValidationError ที่เราควบคุมเอง
    - exception อื่น ๆ (รวมถึง ValueError จาก pandas/openpyxl) ถูกแทนด้วยข้อความกลาง ๆ
      เพื่อไม่ให้ stack trace, path ภายใน หรือข้อมูลระบบรั่วไหลสู่ผู้ใช้
    """
    if isinstance(exc, UploadValidationError):
        message = str(exc).strip()
        if message:
            return message[:MAX_ERROR_REASON_LENGTH]
    return GENERIC_LOAD_ERROR_REASON


def sanitize_csv_cell(val):
    """
    ฆ่าเชื้อข้อมูลเซลล์เพื่อป้องกัน CSV / Formula Injection (CWE-1236)
    ตามแนวทางความปลอดภัยของ OWASP: หากค่าข้อความขึ้นต้นด้วย =, @, tab, cr, |, %
    หรือเครื่องหมาย +, - ที่ไม่ใช่ตัวเลขล้วน ให้เติม ' นำหน้าเพื่อให้โปรแกรมสเปรดชีต
    (เช่น Excel, Calc) แสดงผลเป็นข้อความธรรมดาแทนการรันสูตร
    """
    if not isinstance(val, str):
        return val
    if not val:
        return val

    first_char = val[0]
    stripped = val.lstrip()
    stripped_char = stripped[0] if stripped else ''

    if first_char in DANGEROUS_FORMULA_PREFIXES or stripped_char in DANGEROUS_FORMULA_PREFIXES:
        return f"'{val}"

    if first_char in ('+', '-') or stripped_char in ('+', '-'):
        if not PURE_NUMBER_PATTERN.match(stripped):
            return f"'{val}"

    return val


def sanitize_dataframe_for_csv(df: pd.DataFrame) -> pd.DataFrame:
    """
    ป้องกัน Formula Injection สำหรับ DataFrame ทั้งตารางก่อนส่งออกเป็นไฟล์ CSV
    ครอบคลุมทั้งชื่อคอลัมน์, ดัชนี (index) และข้อมูลในคอลัมน์ที่เป็น string/object
    โดยยังคงรักษาค่าตัวเลขและวันเวลาเดิมอย่างถูกต้อง
    """
    if df is None:
        return df

    df_clean = df.copy()

    # ทำความสะอาดชื่อคอลัมน์ (รองรับทั้ง Index ปกติ และ MultiIndex)
    if isinstance(df_clean.columns, pd.MultiIndex):
        df_clean.columns = df_clean.columns.map(
            lambda x: tuple(sanitize_csv_cell(p) if isinstance(p, str) else p for p in x)
        )
        if any(isinstance(n, str) for n in df_clean.columns.names):
            df_clean.columns = df_clean.columns.rename(
                [sanitize_csv_cell(n) if isinstance(n, str) else n for n in df_clean.columns.names]
            )
    else:
        new_cols = []
        for c in df_clean.columns:
            if isinstance(c, str):
                new_cols.append(sanitize_csv_cell(c))
            else:
                new_cols.append(c)
        df_clean.columns = new_cols

    # ทำความสะอาด Index และ Index Names เพื่อป้องกัน Formula Injection เมื่อ export แบบมี index
    if df_clean.index is not None:
        if isinstance(df_clean.index, pd.MultiIndex):
            df_clean.index = df_clean.index.map(
                lambda x: tuple(sanitize_csv_cell(p) if isinstance(p, str) else p for p in x)
            )
            if any(isinstance(n, str) for n in df_clean.index.names):
                df_clean.index = df_clean.index.rename(
                    [sanitize_csv_cell(n) if isinstance(n, str) else n for n in df_clean.index.names]
                )
        else:
            if df_clean.index.dtype == object or pd.api.types.is_string_dtype(df_clean.index):
                u_idx = df_clean.index.unique()
                idx_mapping = {val: sanitize_csv_cell(val) for val in u_idx}
                if any(isinstance(k, str) and k != v for k, v in idx_mapping.items()):
                    df_clean.index = df_clean.index.map(idx_mapping)
            if df_clean.index.name and isinstance(df_clean.index.name, str):
                df_clean.index.name = sanitize_csv_cell(df_clean.index.name)

    if df_clean.empty:
        return df_clean

    # ทำความสะอาดข้อมูลเฉพาะคอลัมน์ที่เป็น string หรือ object
    for col in df_clean.columns:
        if df_clean[col].dtype == object or pd.api.types.is_string_dtype(df_clean[col]):
            # ⚡ Bolt Optimization: Use unique value dictionary mapping instead of slow row-by-row .map(func).
            # In large load profiles, object columns have low distinct cardinalities (e.g. Period_Detail, Anomaly_Type, Month).
            # Mapping only unique values avoids hundreds of thousands of redundant cell function calls.
            s = df_clean[col]
            uniques = s.unique()
            mapping = {val: sanitize_csv_cell(val) for val in uniques}
            if any(isinstance(k, str) and k != v for k, v in mapping.items()):
                df_clean[col] = s.map(mapping)

    return df_clean


# ค่าคงที่สำหรับกรองข้อมูลที่ผิดปกติ (Outliers)
DEFAULT_OUTLIER_KW_MAX = 2000000
DEFAULT_OUTLIER_V_MAX = 2000000

# ค่าคงที่สำหรับความปลอดภัยและการตรวจสอบไฟล์นำเข้า
ALLOWED_EXTENSIONS = {'csv', 'xlsx', 'xls', 'txt'}
MAX_FILE_SIZE_BYTES = 50 * 1024 * 1024  # 50 MB
MAX_EXCEL_UNCOMPRESSED_BYTES = 256 * 1024 * 1024  # 256 MB (กัน Zip Bomb ใน .xlsx)
MAX_UPLOAD_FILES = 20  # จำนวนไฟล์สูงสุดต่อการอัปโหลดหนึ่งครั้ง
MAX_TOTAL_UPLOAD_BYTES = 200 * 1024 * 1024  # 200 MB (กัน Resource Exhaustion จากหลายไฟล์)


def get_upload_size(uploaded_file):
    """
    คืนขนาดไฟล์ที่อัปโหลดเป็นไบต์ หรือ None หากตรวจสอบไม่ได้
    รองรับทั้งออบเจกต์ที่มี attribute size (Streamlit UploadedFile), file-like ที่มี getbuffer()
    และ stream ที่รองรับ seek/tell (เช่น TemporaryFile, BufferedReader)
    ไม่ยอมรับค่าขนาดติดลบ (เช่น -1 จาก chunked transfer หรือการปลอมแปลง) และจะตรวจหาขนาดจริงจาก stream
    """
    size = getattr(uploaded_file, 'size', None)
    if size is not None:
        try:
            val = int(size)
            if val >= 0:
                return val
        except (TypeError, ValueError):
            pass
    if hasattr(uploaded_file, 'getbuffer'):
        try:
            val = uploaded_file.getbuffer().nbytes
            if val >= 0:
                return int(val)
        except Exception:
            pass
    if hasattr(uploaded_file, 'seek') and hasattr(uploaded_file, 'tell'):
        try:
            curr_pos = uploaded_file.tell()
            uploaded_file.seek(0, io.SEEK_END)
            end_pos = uploaded_file.tell()
            uploaded_file.seek(curr_pos)
            val = int(end_pos)
            if val >= 0:
                return val
        except Exception:
            try:
                uploaded_file.seek(0)
            except Exception:
                pass
            return None
    return None


def validate_upload_batch(uploaded_files):
    """
    จำกัดจำนวนไฟล์และขนาดรวมต่อการอัปโหลดหนึ่งครั้ง เพื่อป้องกัน
    Resource Exhaustion / Denial of Service (CWE-770) จากการอัปโหลดหลายไฟล์พร้อมกัน
    แม้แต่ละไฟล์จะผ่านเพดานขนาดต่อไฟล์แล้วก็ตาม
    คืนค่าขนาดรวม (ไบต์) เมื่อผ่านการตรวจสอบ
    """
    files = list(uploaded_files or [])
    if len(files) > MAX_UPLOAD_FILES:
        raise UploadValidationError(
            f"อัปโหลดได้ไม่เกิน {MAX_UPLOAD_FILES} ไฟล์ต่อครั้ง"
        )

    total_bytes = 0
    for uploaded_file in files:
        size = get_upload_size(uploaded_file)
        if size is not None and size > 0:
            total_bytes += size
            if total_bytes > MAX_TOTAL_UPLOAD_BYTES:
                raise UploadValidationError(
                    f"ขนาดไฟล์รวมเกินกำหนด (สูงสุด {MAX_TOTAL_UPLOAD_BYTES // (1024 * 1024)} MB)"
                )
    return total_bytes


def validate_excel_archive(uploaded_file):
    """
    ตรวจขนาดข้อมูลภายในไฟล์ .xlsx (ZIP) ก่อนส่งให้ openpyxl แตกไฟล์
    เพื่อป้องกัน Zip Bomb / Decompression Bomb (CWE-409) ที่อาจทำให้หน่วยความจำหมด
    ไฟล์ที่ไม่ใช่ ZIP (เช่น HTML ที่เปลี่ยนนามสกุล) จะปล่อยให้ fallback เดิมจัดการต่อ
    """
    total_uncompressed = 0
    try:
        uploaded_file.seek(0)
        with zipfile.ZipFile(uploaded_file) as archive:
            for info in archive.infolist():
                total_uncompressed += info.file_size
                if total_uncompressed > MAX_EXCEL_UNCOMPRESSED_BYTES:
                    break
    except (zipfile.BadZipFile, OSError):
        return
    finally:
        try:
            uploaded_file.seek(0)
        except Exception:
            pass

    if total_uncompressed > MAX_EXCEL_UNCOMPRESSED_BYTES:
        raise UploadValidationError(
            f"ไฟล์ Excel มีข้อมูลเมื่อแตกไฟล์เกินกำหนด (สูงสุด {MAX_EXCEL_UNCOMPRESSED_BYTES // (1024 * 1024)} MB)"
        )


def sanitize_filename(filename: str) -> str:
    """
    ทำความสะอาดชื่อไฟล์ที่อัปโหลดเพื่อป้องกัน Path Traversal (CWE-22),
    Log Injection (CWE-117) และ Markdown/HTML Injection (CWE-79) บน UI
    โดยตัด path separator (/, \\) และลำดับ directory traversal (..)
    รวมถึงตัดอักขระควบคุม (control characters) และ escape อักขระ Markdown พิเศษ
    """
    if not filename or not isinstance(filename, str):
        return "unnamed_file"

    # 1. ตัด directory path เพื่อป้องกัน Path Traversal (รองรับทั้ง Unix '/' และ Windows '\\')
    clean_name = re.split(r'[/\\]', filename)[-1].strip()

    # 2. ป้องกันลำดับ path traversal ตกค้าง (เช่น ..)
    clean_name = re.sub(r'^\.+', '', clean_name).strip()
    if not clean_name:
        return "unnamed_file"

    # 3. กำจัด newline และ control characters เพื่อป้องกัน Log Injection (CWE-117)
    clean_name = re.sub(r'[\r\n\t\x00-\x1f\x7f-\x9f]', '', clean_name)

    # 4. ป้องกัน Markdown/HTML Injection บน UI (เช่น [phish](url) หรือรูปภาพใน st.toast)
    clean_name = re.sub(r'[\[\]\(\)`~<>]', '', clean_name).strip()

    return clean_name or "unnamed_file"


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
            if delimiter == ',':
                num_tabs = line.count('\t')
                num_semis = line.count(';')
                num_commas = line.count(',')
                if num_tabs > 0 and num_tabs >= num_semis and (num_tabs >= num_commas or num_commas == 0):
                    delimiter = '\t'
                elif num_semis > 0 and (num_semis >= num_commas or num_commas == 0):
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
        
        if ('date' in c_clean or 'วันที่' in c_clean) and not any(k in c_clean for k in ('time', 'clock', 'เวลา', 'update', 'candidate')):
            date_idx = i
        elif 'clock' in c_clean or 'ch1' == c_clean or 'time' in c_clean or 'datatime' in c_clean or 'เวลา' in c_clean: 
            clock_idx = i
        elif 'voltage' in c_clean or 'ch3' == c_clean or 'แรงดัน' in c_clean or c_clean == 'v' or 'volt' in c_clean: 
            v_idx = i
        
        # คอลัมน์ kWh คือพลังงานสะสม ไม่ใช่กำลังไฟฟ้า จึงต้องไม่ถูกเลือกเป็น kW
        is_energy_col = 'kwh' in c_clean

        # เพิ่มระบบค้นหาคอลัมน์พลังงานแบบหว่านแห (ทั้ง Import, Export และ Active Power)
        if not is_energy_col and (('kw' in c_clean and 'demand' in c_clean) or \
           ('import' in c_clean and 'kw' in c_clean) or \
           ('export' in c_clean and 'kw' in c_clean) or \
           'ch4' == c_clean or \
           ('active' in c_clean and 'power' in c_clean) or \
           'พลังงาน' in c_clean or \
           'กำลังไฟฟ้า' in c_clean or \
           c_clean == 'kw'):
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
            
    if clock_idx == -1 or kw_idx == -1 or clock_idx == kw_idx:
        return None
        
    if date_idx != -1 and (date_idx == clock_idx or date_idx == kw_idx):
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

    num_cols = len(df_raw.columns)

    # ⚡ Bolt Optimization: Fast unique value mapping for column extraction, validation & string merging.
    # In load profiles, timestamps and dates have low distinct cardinalities (96 times, ~2000 dates).
    # Performing fillna, astype(str), str.strip(), str.lower(), and regex across full Series takes >300ms
    # for 200k rows. Using unique dictionary maps and selective numpy masking cuts runtime by >50%.
    def clean_col(idx, default_val, replace_empty=None):
        if idx != -1 and idx < num_cols:
            col_s = df_raw.iloc[:, idx]
            u = col_s.unique()
            if len(u) <= len(col_s) * 0.5:
                col_map = {}
                for v in u:
                    if pd.isna(v):
                        clean_v = ""
                    else:
                        clean_v = str(v).strip()
                    if replace_empty is not None and clean_v == "":
                        clean_v = replace_empty
                    col_map[v] = clean_v
                return col_s.map(col_map)
            else:
                s_clean = col_s.fillna('').astype(str).str.strip()
                if replace_empty is not None:
                    s_clean = s_clean.replace('', replace_empty)
                return s_clean
        return pd.Series([default_val] * len(df_raw))

    c_col = clean_col(clock_idx, "")
    d_col = clean_col(date_idx, "") if date_idx != -1 else None
    kw_col = clean_col(kw_idx, "0", replace_empty="0")
    v_col = clean_col(v_idx, "220", replace_empty="220") if v_idx != -1 else pd.Series(["220"] * len(df_raw))

    invalid_pattern = r'^(?:total.*|p|op|h|kwh|nan)$'
    invalid_clock_pattern = r'^(?:total.*|p|op|h|kwh|nan|dnv/err)$'

    re_clock = re.compile(invalid_clock_pattern)
    u_c = c_col.unique()
    if len(u_c) <= len(c_col) * 0.5:
        map_c = {}
        for v in u_c:
            s = v.lower()
            map_c[v] = False if (not s or (s[0] in 'tpohknd' and re_clock.match(s))) else True
        mask_c = c_col.map(map_c).fillna(False).astype(bool)
    else:
        c_clean = c_col.str.lower()
        has_invalid_c = c_clean.str.contains(invalid_clock_pattern, regex=True, na=False)
        mask_c = ~(has_invalid_c | (c_clean == ''))

    if d_col is not None:
        re_date = re.compile(invalid_pattern)
        u_d = d_col.unique()
        if len(u_d) <= len(d_col) * 0.5:
            map_d = {}
            for v in u_d:
                s = v.lower()
                map_d[v] = False if (not s or (s[0] in 'tpohkn' and re_date.match(s))) else True
            mask_d = d_col.map(map_d).fillna(False).astype(bool)
        else:
            d_clean = d_col.str.lower()
            has_invalid_d = d_clean.str.contains(invalid_pattern, regex=True, na=False)
            mask_d = ~(has_invalid_d | (d_clean == ''))
        valid_mask = mask_c & mask_d
    else:
        valid_mask = mask_c

    valid_mask_np = valid_mask.to_numpy()
    c_valid = c_col[valid_mask_np]
    kw_valid = kw_col[valid_mask_np]
    v_valid = v_col[valid_mask_np]

    if d_col is not None:
        d_valid = d_col[valid_mask_np]
        merged_clock = d_valid + ' ' + c_valid
    else:
        merged_clock = c_valid

    out_df = pd.DataFrame({
        'Clock': merged_clock.reset_index(drop=True),
        'kW_Import': kw_valid.reset_index(drop=True),
        'Voltage': v_valid.reset_index(drop=True)
    })

    return out_df

def parse_excel_df(df_raw):
    """สำหรับอ่านไฟล์ตาราง (Excel) หรือรับต่อจาก pd.read_csv()"""
    if df_raw is None or len(df_raw) == 0:
        return None

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
        
        if ('date' in c_clean or 'วันที่' in c_clean) and not any(k in c_clean for k in ('time', 'clock', 'เวลา', 'update', 'candidate')):
            date_col = c
        elif 'clock' in c_clean or 'ch1' == c_clean or 'time' in c_clean or 'datatime' in c_clean or 'เวลา' in c_clean: 
            clock_col = c
        elif 'voltage' in c_clean or 'ch3' == c_clean or 'แรงดัน' in c_clean or c_clean == 'v' or 'volt' in c_clean: 
            v_col = c
        
        # คอลัมน์ kWh คือพลังงานสะสม ไม่ใช่กำลังไฟฟ้า จึงต้องไม่ถูกเลือกเป็น kW
        is_energy_col = 'kwh' in c_clean

        # 🎯 เก็บผู้ท้าชิงคอลัมน์พลังงานทั้งหมด (ทั้ง Import และ Export)
        if not is_energy_col and (('kw' in c_clean and 'demand' in c_clean) or \
           ('import' in c_clean and 'kw' in c_clean) or \
           ('export' in c_clean and 'kw' in c_clean) or \
           'ch4' == c_clean or \
           ('active' in c_clean and 'power' in c_clean and '+' in c_clean) or \
           ('active' in c_clean and 'power' in c_clean) or \
           'พลังงาน' in c_clean or \
           'กำลังไฟฟ้า' in c_clean or \
           c_clean == 'kw'):
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
        
    if not clock_col or not kw_col or clock_col == kw_col:
        return None
        
    if date_col and (date_col == clock_col or date_col == kw_col):
        return None
        
    invalid_pattern = r'^(?:total.*|p|op|h|kwh|nan)$'
    invalid_clock_pattern = r'^(?:total.*|p|op|h|kwh|nan|dnv/err)$'

    clock_series = df[clock_col]
    kw_series = df[kw_col]
    v_series = df[v_col] if v_col else None
    date_series = df[date_col] if date_col else None

    # ⚡ Bolt Optimization: Fast unique value mapping for clock/date validation & string merging.
    # Evaluating fillna, astype(str), str.strip(), str.lower(), and regex across hundreds of thousands
    # of rows is extremely slow (~300ms for 200k rows).
    # Since load profiles have low distinct cardinalities (only ~96 unique times, ~2000 unique dates),
    # evaluating validity on unique values and mapping back eliminates redundant allocations.
    # Slicing only required series avoids copying the entire DataFrame of unused columns.
    # ⚡ Bolt Optimization: Skip the costly Series.unique() cardinality probe for fixed-width
    # timestamp columns (len 16/19), which are high-cardinality by nature (one slot per row).
    # Series.unique() costs ~17ms per 200k rows and only existed to choose between two equivalent
    # filtering paths. Load profiles read from CSV/Excel store timestamps as plain Python str.
    re_clock = re.compile(invalid_clock_pattern)
    sample_val = None
    for v in clock_series.iloc[:20]:
        if pd.notna(v):
            s_val = v if type(v) is str else str(v)
            if s_val.strip():
                sample_val = v
                break
    use_byte_gate = type(sample_val) is str and len(sample_val) in (16, 19)

    mask_c = None
    if not use_byte_gate:
        u_c = clock_series.unique()
        if len(u_c) <= len(clock_series) * 0.5:
            map_c = {}
            for v in u_c:
                if pd.isna(v):
                    map_c[v] = False
                else:
                    s = str(v).strip().lower()
                    map_c[v] = False if (not s or (s[0] in 'tpohknd' and re_clock.match(s))) else True
            mask_c = clock_series.map(map_c).fillna(False).astype(bool)

    if mask_c is None:
        # ⚡ Bolt Optimization: High-cardinality clock columns (one unique timestamp per row)
        # previously ran full-series .astype(str).str.strip() .str.lower() .str.contains(regex)
        # on every row (~94ms per 200k rows). Every invalid pattern starts with an ASCII letter
        # t/p/o/h/k/n/d, whitespace, control bytes, or (after strip) non-ASCII whitespace, so a
        # vectorized first-byte check on a fixed-width byte buffer lets the regex run only on the
        # tiny candidate subset. Non-ASCII bytes are candidates so Unicode whitespace before a
        # footer keyword is still stripped and matched.
        try:
            clock_bytes = clock_series.fillna('').to_numpy(dtype='S19')
            first_byte = clock_bytes.view('uint8').reshape(len(clock_bytes), 19)[:, 0]
            trigger_bytes = np.frombuffer(b'tpohkndTPOHKND', dtype='uint8')
            is_candidate = (first_byte <= 32) | (first_byte >= 128) | np.isin(first_byte, trigger_bytes)
            valid_arr = np.ones(len(clock_series), dtype=bool)
            if is_candidate.any():
                c_clean = clock_series[is_candidate].fillna('').astype(str).str.strip().str.lower()
                has_invalid_c = c_clean.str.contains(invalid_clock_pattern, regex=True, na=False)
                valid_arr[is_candidate] = ~(has_invalid_c | (c_clean == '')).to_numpy()
            mask_c = pd.Series(valid_arr, index=clock_series.index)
        except Exception:
            c_clean = clock_series.fillna('').astype(str).str.strip().str.lower()
            has_invalid_c = c_clean.str.contains(invalid_clock_pattern, regex=True, na=False)
            mask_c = ~(has_invalid_c | (c_clean == ''))

    if date_series is not None:
        re_date = re.compile(invalid_pattern)
        u_d = date_series.unique()
        map_d = {}
        for v in u_d:
            if pd.isna(v):
                map_d[v] = False
            else:
                s = str(v).strip().lower()
                map_d[v] = False if (not s or (s[0] in 'tpohkn' and re_date.match(s))) else True
        mask_d = date_series.map(map_d).fillna(False).astype(bool)
        valid_mask = mask_c & mask_d
    else:
        valid_mask = mask_c

    valid_mask_np = valid_mask.to_numpy()
    clock_valid = clock_series[valid_mask_np]
    kw_valid = kw_series[valid_mask_np]
    v_valid = v_series[valid_mask_np] if v_series is not None else 220.0

    if date_series is not None:
        date_valid = date_series[valid_mask_np]
        u_dv = date_valid.unique()
        d_strip_map = {v: str(v).strip() for v in u_dv}
        u_cv = clock_valid.unique()
        c_strip_map = {v: str(v).strip() for v in u_cv}
        merged_clock = date_valid.map(d_strip_map).astype(str) + ' ' + clock_valid.map(c_strip_map).astype(str)
    else:
        merged_clock = clock_valid

    out_df = pd.DataFrame({
        'Clock': merged_clock.reset_index(drop=True),
        'kW_Import': kw_valid.reset_index(drop=True),
        'Voltage': v_valid.reset_index(drop=True) if v_series is not None else 220.0
    })
    return out_df

@st.cache_data
def load_file(uploaded_file, file_ext):
    if not file_ext or not isinstance(file_ext, str):
        raise UploadValidationError("ไม่พบนามสกุลไฟล์ที่ถูกต้อง")

    clean_ext = file_ext.lower().lstrip('.')
    if clean_ext not in ALLOWED_EXTENSIONS:
        raise UploadValidationError(
            f"ไม่อนุญาตให้อัปโหลดไฟล์นามสกุล .{clean_ext} (รองรับเฉพาะ: {', '.join(sorted(ALLOWED_EXTENSIONS))})"
        )

    # ตรวจสอบขนาดไฟล์เพื่อป้องกัน Denial of Service (DoS / Resource Exhaustion)
    file_size = get_upload_size(uploaded_file)
    if file_size is not None and file_size > MAX_FILE_SIZE_BYTES:
        raise UploadValidationError(f"ขนาดไฟล์เกินกำหนด (สูงสุด {MAX_FILE_SIZE_BYTES // (1024 * 1024)} MB)")

    df_result = None

    # 1. หากเป็นไฟล์ Excel (.xlsx, .xls) หรือ HTML ให้ลองอ่านด้วย Excel engine ก่อน
    if clean_ext in ['xlsx', 'xls']:
        if clean_ext == 'xlsx':
            validate_excel_archive(uploaded_file)
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
        # 2.1 ลองใช้ Pandas
        # ⚡ Bolt Optimization: Try header=None first for fast C-speed reading on regular CSVs without allocating 50 columns.
        # Fallback to names=range(50) only if ragged/inconsistent columns trigger ParserError.
        try:
            try:
                uploaded_file.seek(0)
                try:
                    df_raw = pd.read_csv(uploaded_file, encoding='utf-8-sig', header=None, dtype=str, low_memory=False)
                except Exception:
                    uploaded_file.seek(0)
                    df_raw = pd.read_csv(uploaded_file, encoding='utf-8-sig', names=range(50), dtype=str, low_memory=False)
            except Exception as e:
                logging.warning(f"Failed to read CSV with utf-8-sig: {e}")
                uploaded_file.seek(0)
                try:
                    df_raw = pd.read_csv(uploaded_file, encoding='cp874', header=None, dtype=str, low_memory=False)
                except Exception:
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
        raise UploadValidationError("อ่านไฟล์ไม่สำเร็จ โครงสร้างไฟล์ผิดปกติหรือไม่พบข้อมูลเวลา")

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

    # ⚡ Bolt Optimization: Count non-null samples without copying the entire Series via dropna()
    # (~6ms per 200k rows). Only materialize the filtered Series when NaT/None values actually exist.
    valid_mask = series.notna()
    n_valid = int(valid_mask.sum())
    if n_valid == 0:
        return pd.to_datetime(series, dayfirst=dayfirst, errors='coerce', format='mixed')

    # Find the first non-empty string sample to prioritize candidate formats
    first_val = ""
    if n_valid == len(series):
        first_val = str(series.iloc[0]).strip()
        if not first_val:
            for v in series:
                s_val = str(v).strip()
                if s_val:
                    first_val = s_val
                    break
    else:
        for v in series[valid_mask]:
            s_val = str(v).strip()
            if s_val:
                first_val = s_val
                break

    if not first_val:
        return pd.to_datetime(series, dayfirst=dayfirst, errors='coerce', format='mixed')

    n = len(series)
    parsed = None

    # ⚡ Bolt Optimization: Fast vectorized byte-reordering parser for fixed-width DMY formats.
    # Standard pd.to_datetime(series, format='%d/%m/%Y %H:%M') takes ~380ms for 200k rows because
    # pandas falls back to slow strptime parsing for non-ISO formats.
    # Reordering ASCII byte buffers directly to ISO format in NumPy allows C-speed parsing in ~38ms.
    if len(first_val) == 16 and (first_val[2] == '/' or first_val[2] == '-') and first_val[5] == first_val[2] and first_val[10] == ' ' and first_val[13] == ':':
        try:
            sep_char = ord(first_val[2])
            # ⚡ Use width 19 so rows with seconds (or more) are not truncated to 16 chars.
            # b[:, 16] == 0 guarantees the original value is exactly 16 chars; longer values
            # are left for the mixed-format fallback so their seconds are not silently dropped.
            arr = series.to_numpy(dtype='S19')
            b = arr.view('uint8').reshape(n, 19)
            sep_mask = (b[:, 16] == 0) & (b[:, 2] == sep_char) & (b[:, 5] == sep_char) & (b[:, 10] == ord(' ')) & (b[:, 13] == ord(':'))
            if sep_mask.any():
                out = np.empty((n, 16), dtype='uint8')
                out[:, 0:4] = b[:, 6:10] # YYYY
                out[:, 4] = ord('-')
                out[:, 5:7] = b[:, 3:5] if dayfirst else b[:, 0:2]  # MM
                out[:, 7] = ord('-')
                out[:, 8:10] = b[:, 0:2] if dayfirst else b[:, 3:5] # DD
                out[:, 10] = ord('T')
                out[:, 11:16] = b[:, 11:16] # HH:MM

                res_arr = np.full(n, np.datetime64('NaT', 'ns'), dtype='datetime64[ns]')
                try:
                    res_arr[sep_mask] = out[sep_mask].view('S16').reshape(-1).astype('datetime64[ns]')
                except Exception:
                    s_iso = out[sep_mask].view('S16').reshape(-1).astype(str)
                    res_arr[sep_mask] = pd.to_datetime(pd.Series(s_iso), errors='coerce').to_numpy()

                nat_mask = np.isnat(res_arr)
                if not nat_mask.any():
                    parsed = pd.Series(res_arr, index=series.index)
                else:
                    failed_idx = np.where(nat_mask)[0]
                    cands = series.iloc[failed_idx]
                    failed_non_empty = cands.notna() & (cands.astype(str).str.strip() != '')
                    if not failed_non_empty.any():
                        parsed = pd.Series(res_arr, index=series.index)
                    elif sep_mask.sum() >= n_valid * 0.5:
                        actual_failed_idx = failed_idx[failed_non_empty.to_numpy()]
                        patched = pd.to_datetime(
                            series.iloc[actual_failed_idx],
                            dayfirst=dayfirst,
                            errors='coerce',
                            format='mixed'
                        )
                        res_arr[actual_failed_idx] = patched.to_numpy()
                        parsed = pd.Series(res_arr, index=series.index)
        except Exception:
            pass
    elif len(first_val) == 19 and (first_val[2] == '/' or first_val[2] == '-') and first_val[5] == first_val[2] and first_val[10] == ' ' and first_val[13] == ':' and first_val[16] == ':':
        try:
            sep_char = ord(first_val[2])
            # ⚡ Use width 20 so rows with fractional seconds/timezone are not truncated to 19 chars.
            # b[:, 19] == 0 guarantees the original value is exactly 19 chars; longer values
            # are left for the mixed-format fallback so their sub-second precision is preserved.
            arr = series.to_numpy(dtype='S20')
            b = arr.view('uint8').reshape(n, 20)
            sep_mask = (b[:, 19] == 0) & (b[:, 2] == sep_char) & (b[:, 5] == sep_char) & (b[:, 10] == ord(' ')) & (b[:, 13] == ord(':')) & (b[:, 16] == ord(':'))
            if sep_mask.any():
                out = np.empty((n, 19), dtype='uint8')
                out[:, 0:4] = b[:, 6:10] # YYYY
                out[:, 4] = ord('-')
                out[:, 5:7] = b[:, 3:5] if dayfirst else b[:, 0:2]  # MM
                out[:, 7] = ord('-')
                out[:, 8:10] = b[:, 0:2] if dayfirst else b[:, 3:5] # DD
                out[:, 10] = ord('T')
                out[:, 11:19] = b[:, 11:19] # HH:MM:SS

                res_arr = np.full(n, np.datetime64('NaT', 'ns'), dtype='datetime64[ns]')
                try:
                    res_arr[sep_mask] = out[sep_mask].view('S19').reshape(-1).astype('datetime64[ns]')
                except Exception:
                    s_iso = out[sep_mask].view('S19').reshape(-1).astype(str)
                    res_arr[sep_mask] = pd.to_datetime(pd.Series(s_iso), errors='coerce').to_numpy()

                nat_mask = np.isnat(res_arr)
                if not nat_mask.any():
                    parsed = pd.Series(res_arr, index=series.index)
                else:
                    failed_idx = np.where(nat_mask)[0]
                    cands = series.iloc[failed_idx]
                    failed_non_empty = cands.notna() & (cands.astype(str).str.strip() != '')
                    if not failed_non_empty.any():
                        parsed = pd.Series(res_arr, index=series.index)
                    elif sep_mask.sum() >= n_valid * 0.5:
                        actual_failed_idx = failed_idx[failed_non_empty.to_numpy()]
                        patched = pd.to_datetime(
                            series.iloc[actual_failed_idx],
                            dayfirst=dayfirst,
                            errors='coerce',
                            format='mixed'
                        )
                        res_arr[actual_failed_idx] = patched.to_numpy()
                        parsed = pd.Series(res_arr, index=series.index)
        except Exception:
            pass

    if parsed is not None:
        return parsed

    if not dayfirst:
        candidates = [
            fmt.replace("%d/%m/%Y", "%m/%d/%Y")
               .replace("%d-%m-%Y", "%m-%d-%Y")
               .replace("%d/%m/%y", "%m/%d/%y")
               .replace("%d-%m-%y", "%m-%d-%y")
               .replace("%d/%m", "%m/%d")
            for fmt in COMMON_DATETIME_FORMATS
        ]
    else:
        candidates = list(COMMON_DATETIME_FORMATS)

    if "-" in first_val and len(first_val) >= 4 and first_val[:4].isdigit():
        candidates.sort(key=lambda fmt: 0 if fmt.startswith("%Y-%m-%d") else 1)
    elif "/" in first_val and len(first_val) >= 4 and first_val[:4].isdigit():
        candidates.sort(key=lambda fmt: 0 if fmt.startswith("%Y/%m/%d") else 1)
    elif "/" in first_val:
        prefix = "%d/%m/%Y" if dayfirst else "%m/%d/%Y"
        candidates.sort(key=lambda fmt: 0 if fmt.startswith(prefix) else 1)
    elif "-" in first_val:
        prefix = "%d-%m-%Y" if dayfirst else "%m-%d-%Y"
        candidates.sort(key=lambda fmt: 0 if fmt.startswith(prefix) else 1)

    for fmt in candidates:
        try:
            res = pd.to_datetime(series, format=fmt, errors='coerce')
            success_count = res.notna().sum()
            if success_count > 0:
                if not res.isna().any():
                    parsed = res
                    break
                else:
                    isna_res = res.isna()
                    failed_cands = series[isna_res]
                    failed_non_empty = failed_cands.notna() & (failed_cands.astype(str).str.strip() != '')
                    if not failed_non_empty.any():
                        parsed = res
                        break
                    elif success_count >= n_valid * 0.5:
                        patch_mask = isna_res & series.notna() & (series.astype(str).str.strip() != '')
                        res.loc[patch_mask] = pd.to_datetime(
                            series.loc[patch_mask],
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

STANDARD_PREPROCESSED_COLS = (
    ('Clock', 'datetime64[ns]'),
    ('kW_Import', 'float64'),
    ('Voltage', 'float64'),
    ('Date', 'datetime64[ns]'),
    ('Month', 'object'),
    ('Time_Str', 'object'),
    ('kWh_15min', 'float64'),
)


def _empty_preprocessed_df(template_df=None):
    df_out = template_df.copy() if template_df is not None else pd.DataFrame()
    for col, dtype in STANDARD_PREPROCESSED_COLS:
        if col not in df_out.columns:
            df_out[col] = pd.Series(dtype=dtype)
        elif df_out[col].dtype == object and dtype != 'object':
            df_out[col] = df_out[col].astype(dtype)
    return df_out.iloc[:0]


@st.cache_data
def preprocess_data(df, kw_max=DEFAULT_OUTLIER_KW_MAX, v_max=DEFAULT_OUTLIER_V_MAX):
    if df is None or df.empty:
        return _empty_preprocessed_df(df)
        
    df = df.copy()

    if 'Clock' not in df.columns:
        return _empty_preprocessed_df(df)

    if 'kW_Import' not in df.columns:
        df['kW_Import'] = 0.0

    if 'Voltage' not in df.columns:
        df['Voltage'] = 220.0
    
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
    parsed_clock = fast_parse_datetime(df['Clock'], dayfirst=True)
    df['Clock'] = parsed_clock
    # ⚡ Bolt Optimization: Detect NaT via the raw int64 epoch array (iNaT sentinel) instead of
    # Series.isna(), and skip dropna + reset_index when nothing is dropped (the common case).
    # dropna(subset=...) copies the entire DataFrame (~7ms per 200k rows) even when no row is removed.
    if parsed_clock.dtype == 'datetime64[ns]':
        clock_ns = parsed_clock.to_numpy(dtype='int64')
        has_nat = bool((clock_ns == np.iinfo(np.int64).min).any())
    else:
        clock_ns = None
        has_nat = bool(parsed_clock.isna().any())
    if has_nat:
        df = df.dropna(subset=['Clock']).reset_index(drop=True)
        clock_ns = df['Clock'].to_numpy(dtype='int64')
    elif not df.index.equals(pd.RangeIndex(len(df))):
        df = df.reset_index(drop=True)
    
    # ป้องกันไฟล์ทับกัน
    # ⚡ Bolt Optimization: Fast monotonic check before multi-column lexsort and deduplication.
    # In load profiles, timestamps are almost universally recorded in chronological order.
    # Evaluating strictly increasing order via int64 epoch differences (`np.all(np.diff(ns) > 0)`)
    # allows bypassing expensive multi-column lexsort and deduplication when rows are already ordered.
    clock_series = df['Clock']
    ns = clock_ns if clock_ns is not None else clock_series.to_numpy(dtype='int64')
    if not (len(ns) <= 1 or np.all(np.diff(ns) > 0)):
        df = df.sort_values(['Clock', 'kW_Import'], ascending=[True, False])
        df = df.drop_duplicates(subset=['Clock'], keep='first').reset_index(drop=True)
        ns = df['Clock'].to_numpy(dtype='int64')
    
    if df.empty:
        return _empty_preprocessed_df(df)
        
    # ⚡ Bolt Optimization: Derive Date/Month/Time_Str from int64 epoch arithmetic instead of
    # repeated pandas `.dt` accessors (.dt.year/.month/.hour/.minute each scan the full column,
    # ~22ms per 200k rows combined). Numeric calendar conversion is done once on NumPy arrays.
    if df['Clock'].dtype == 'datetime64[ns]':
        NS_IN_DAY = 86_400_000_000_000
        days = ns // NS_IN_DAY
        df['Date'] = (days * NS_IN_DAY).astype('datetime64[ns]')
        # Civil-from-days conversion (Howard Hinnant's algorithm) for year/month.
        z = days + 719468
        era = z // 146097
        doe = z - era * 146097
        yoe = (doe - doe // 1460 + doe // 36524 - doe // 146096) // 365
        year = yoe + era * 400
        doy = doe - (365 * yoe + yoe // 4 - yoe // 100)
        mp = (5 * doy + 2) // 153
        month_num = mp + np.where(mp < 10, 3, -9)
        year = year + (month_num <= 2)
        ym = year * 100 + month_num
        hm = (ns % NS_IN_DAY) // 60_000_000_000
        # ⚡ Bolt Optimization: minute-of-day is always 0..1439, so index a fixed lookup table
        # instead of hashing 200k+ values through Series.map(dict).
        time_lookup = np.array([f'{m // 60:02d}:{m % 60:02d}' for m in range(1440)], dtype=object)
        time_str = time_lookup[hm]
    else:
        clock_dt = df['Clock'].dt
        df['Date'] = clock_dt.normalize()
        ym = (clock_dt.year * 100 + clock_dt.month).to_numpy()
        hm = (clock_dt.hour * 60 + clock_dt.minute).to_numpy()
        hm_dict = {int(v): f'{int(v) // 60:02d}:{int(v) % 60:02d}' for v in np.unique(hm)}
        time_str = pd.Series(hm, index=df.index).map(hm_dict).to_numpy()

    ym_dict = {int(v): f'{int(v) // 100:04d}-{int(v) % 100:02d}' for v in np.unique(ym)}
    df['Month'] = pd.Series(ym, index=df.index).map(ym_dict)
    df['Time_Str'] = time_str

    df['kWh_15min'] = df['kW_Import'] / 4.0
    
    return df


def sort_and_deduplicate_by_clock(df):
    """เรียงตาม Clock (kW มากก่อนเมื่อเวลาซ้ำ) และลบแถวเวลาเดิมที่ซ้ำกัน

    ⚡ Bolt Optimization: preprocess_data() เรียงและลบข้อมูลซ้ำให้แต่ละไฟล์แล้ว ดังนั้นข้อมูลที่
    concat ต่อกันมักเป็นลำดับเวลาเพิ่มขึ้นอยู่แล้ว การตรวจลำดับด้วย int64 epoch ก่อนทำให้ข้าม
    multi-column lexsort + drop_duplicates ที่ไม่ได้ทำอะไร (~53.6 ms/200k, ~163.3 ms/500k) ได้
    """
    if df is None:
        return None
    if df.empty or 'Clock' not in df.columns:
        return df.copy()

    if (
        'kW_Import' in df.columns
        and df['Clock'].dtype == 'datetime64[ns]'
        and df.index.equals(pd.RangeIndex(len(df)))
    ):
        ns = df['Clock'].to_numpy(dtype='int64')
        nat_sentinel = np.iinfo(np.int64).min
        if len(ns) == 1:
            if ns[0] != nat_sentinel:
                return df
        elif ns[0] != nat_sentinel and np.all(np.diff(ns) > 0):
            return df

    sort_cols = ['Clock', 'kW_Import'] if 'kW_Import' in df.columns else ['Clock']
    ascending = [True, False] if 'kW_Import' in df.columns else [True]

    return (
        df.sort_values(sort_cols, ascending=ascending)
        .drop_duplicates(subset=['Clock'], keep='first')
        .reset_index(drop=True)
    )


def get_usage_snapshots(df):
    if df is None or df.empty:
        return []

    if 'kW_Import' not in df.columns or 'Clock' not in df.columns:
        return []

    if not pd.api.types.is_numeric_dtype(df['kW_Import']):
        kw_num = pd.to_numeric(df['kW_Import'], errors='coerce').fillna(0.0)
        kw_array = kw_num.to_numpy(dtype='float64')
    else:
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
    # ⚡ Bolt Optimization: Only extract and format boundary timestamps instead of converting entire Series to strings
    clock_indices = np.concatenate((pad_s_array, pad_e_array))
    target_clocks = clock_series.iloc[clock_indices]
    if not pd.api.types.is_datetime64_any_dtype(target_clocks):
        target_clocks = fast_parse_datetime(target_clocks, dayfirst=True)

    # Fast vectorized format %d/%m/%y %H:%M -> e.g. 2026-01-01 00:00:00 -> 01/01/26 00:00
    c_str = target_clocks.astype(str)
    # yyyy-mm-dd hh:mm:ss -> dd/mm/yy hh:mm
    time_series = c_str.str.slice(11, 16).replace('', '00:00')
    formatted = (c_str.str.slice(8, 10) + '/' + c_str.str.slice(5, 7) + '/' + c_str.str.slice(2, 4) + ' ' + time_series).to_numpy()
    nat_mask = target_clocks.isna().to_numpy() if hasattr(target_clocks, 'isna') else (c_str == 'NaT').to_numpy()
    if nat_mask.any():
        formatted[nat_mask] = 'NaT'

    num_sessions = len(starts)
    s_times = formatted[:num_sessions]
    e_times = formatted[num_sessions:]

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
