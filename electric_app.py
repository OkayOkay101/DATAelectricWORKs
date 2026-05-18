import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

# ==========================================
# ⚙️ ส่วนที่ 1: ฟังก์ชันจัดการข้อมูล (Data Processing Functions)
# ==========================================

@st.cache_data
def load_file(uploaded_file, file_ext):
    """ฟังก์ชันอ่านไฟล์อัจฉริยะ: รองรับไฟล์ทั้ง 4 รูปแบบ (TXT, CSV, Load Profile, Excel)"""
    
    # 1. จัดการไฟล์ TXT (แก้ปัญหาคอลัมน์เหลื่อม)
    if file_ext == 'txt':
        bytes_data = uploaded_file.getvalue()
        string_data = bytes_data.decode("utf-8-sig", errors='ignore')
        lines = string_data.splitlines()
        
        header_row_idx = 0
        for i, line in enumerate(lines[:20]):
            line_lower = line.lower()
            if ('clock' in line_lower and ('import' in line_lower or 'status' in line_lower)) or \
               ('ch1' in line_lower and 'ch2' in line_lower):
                header_row_idx = i
                break
                
        header_line = lines[header_row_idx]
        if ',' in header_line:
            cols = [c.strip() for c in header_line.split(',') if c.strip()]
        else:
            cols = [c.strip() for c in header_line.split('\t') if c.strip()]
            if len(cols) <= 1:
                cols = [c.strip() for c in header_line.split() if c.strip()]
                
        data_rows = []
        for line in lines[header_row_idx+1:]:
            line_clean = line.strip()
            if not line_clean: continue
                
            parts = line_clean.split()
            if len(parts) >= 2:
                # รวมวันที่และเวลาให้เป็นคอลัมน์เดียว
                if ('/' in parts[0] or '-' in parts[0]) and ':' in parts[1]:
                    clock_str = f"{parts[0]} {parts[1]}"
                    row_data = [clock_str] + parts[2:]
                else:
                    row_data = parts
                data_rows.append(row_data[:len(cols)])
                
        return pd.DataFrame(data_rows, columns=cols)

    # 2. จัดการไฟล์ CSV และ Excel (Load Profile, FreezeData, Pro)
    else:
        if file_ext == 'csv':
            try:
                df_raw = pd.read_csv(uploaded_file, header=None, encoding='utf-8-sig', skip_blank_lines=True)
            except UnicodeDecodeError:
                uploaded_file.seek(0)
                df_raw = pd.read_csv(uploaded_file, header=None, encoding='cp874', skip_blank_lines=True)
        elif file_ext in ['xlsx', 'xls']:
            engine = 'openpyxl' if file_ext == 'xlsx' else 'xlrd'
            df_raw = pd.read_excel(uploaded_file, engine=engine, header=None)
        
        # ค้นหาตำแหน่งหัวตาราง (ข้าม Metadata ของ Load Profile)
        header_row = 0
        for i in range(min(30, len(df_raw))):
            row_str = ' '.join(df_raw.iloc[i].fillna('').astype(str)).lower()
            # เงื่อนไขหาหัวตารางที่ครอบคลุมทุกไฟล์
            if ('clock' in row_str and ('import' in row_str or 'status' in row_str)) or \
               ('ch1' in row_str and 'ch2' in row_str and 'ch3' in row_str):
                header_row = i
                break
                
        df_raw.columns = df_raw.iloc[header_row].astype(str).str.strip()
        return df_raw.iloc[header_row + 1:].reset_index(drop=True)

@st.cache_data
def preprocess_and_analyze(df_raw, sensitivity):
    """ฟังก์ชันทำความสะอาดข้อมูล และคำนวณหาค่าผิดปกติ"""
    df_raw.columns = df_raw.columns.astype(str).str.strip()
    
    rename_map = {}
    found_clock = False
    found_voltage = False
    found_kw = False

    # ตัดช่องว่างและตัวอักษรพิเศษเพื่อจับคู่คอลัมน์
    for c in df_raw.columns:
        c_norm = c.lower().replace(' ', '').replace('.', '').replace(':', '').replace('_', '').replace('\n', '')
        
        if not found_clock and ('clock' in c_norm or 'ch1' == c_norm):
            rename_map[c] = 'Clock'
            found_clock = True
        elif not found_voltage and ('voltage' in c_norm or 'ch3' == c_norm):
            rename_map[c] = 'Voltage'
            found_voltage = True
        elif not found_kw and (('import' in c_norm and 'kw' in c_norm) or 'ch4' == c_norm):
            rename_map[c] = 'kW_Import'
            found_kw = True
            
    df = df_raw.rename(columns=rename_map).copy()
    if 'Voltage' not in df.columns: df['Voltage'] = 220.0

    # ล้างค่าที่เป็น Text และแปลงเป็นตัวเลข
    for col in ['Voltage', 'kW_Import']:
        if col in df.columns:
            df[col] = df[col].astype(str).str.replace(' V', '', regex=False).str.replace(' kW', '', regex=False).str.replace(',', '', regex=False)
            df[col] = pd.to_numeric(df[col], errors='coerce')

    df['Clock'] = pd.to_datetime(df['Clock'], dayfirst=True, errors='coerce')
    df = df.dropna(subset=['Clock', 'kW_Import']).reset_index(drop=True)
    df['Date'] = df['Clock'].dt.date
    df['Time_Str'] = df['Clock'].dt.strftime('%H:%M')

    df['kWh_15min'] = df['kW_Import'] / 4
    df['Cumulative_kWh_Total'] = df['kWh_15min'].cumsum()

    # วิเคราะห์ Anomaly (เฉพาะตอนที่ไฟ > 0)
    active_mask = df['kW_Import'] > 0.0
    if active_mask.sum() > 0:
        mean_kw = df.loc[active_mask, 'kW_Import'].mean()
        std_kw = df.loc[active_mask, 'kW_Import'].std()
    else:
        mean_kw, std_kw = 0, 0
        
    upper_limit = mean_kw + (sensitivity * std_kw)
    lower_limit = max(0.1, mean_kw - (sensitivity * std_kw))
    
    df['Anomaly_Type'] = 'ปกติ'
    # เปลี่ยนคำว่า "กระชาก" เป็น "สูงกว่าเกณฑ์"
    df.loc[active_mask & (df['kW_Import'] > upper_limit), 'Anomaly_Type'] = 'สูงกว่าเกณฑ์ (High)'
    df.loc[active_mask & (df['kW_Import'] < lower_limit), 'Anomaly_Type'] = 'ไฟตก (Low)'
    
    return df

@st.cache_data
def get_usage_snapshots(df):
    """ฟังก์ชันสร้าง Snapshot หาช่วงเวลาที่มีการเดินเครื่อง"""
    snapshots = []
    in_session = False
    start_idx = None
    
    for idx, row in df.iterrows():
        if row['kW_Import'] > 0 and not in_session:
            in_session = True
            start_idx = idx
        elif row['kW_Import'] <= 0 and in_session:
            in_session = False
            snapshots.append((start_idx, idx)) 
            
    if in_session:
        snapshots.append((start_idx, len(df)-1))
        
    session_list = []
    for i, (s_idx, e_idx) in enumerate(snapshots):
        pad_s = max(0, s_idx - 1)
        pad_e = min(len(df)-1, e_idx)
        
        s_time = df.loc[pad_s, 'Clock'].strftime('%d/%m/%y %H:%M')
        e_time = df.loc[pad_e, 'Clock'].strftime('%d/%m/%y %H:%M')
        
        session_list.append({
            'label': f"⚡ รอบที่ {i+1}: {s_time} ถึง {e_time}",
            'start_idx': pad_s,
            'end_idx': pad_e
        })
    return session_list

# ==========================================
# 🖥️ ส่วนที่ 2: ส่วนติดต่อผู้ใช้งาน (UI Layout & Rendering)
# ==========================================

st.set_page_config(page_title="ระบบวิเคราะห์ข้อมูลไฟฟ้า", layout="wide")
st.title("📊 โปรแกรมวิเคราะห์ข้อมูลไฟฟ้า (Universal Mode & Dynamic Charts)")

# --- Sidebar ---
st.sidebar.header("🛠️ ตั้งค่าระบบ")
sensitivity = st.sidebar.slider("ระดับความไว Anomaly", 1.0, 5.0, 2.5, 0.5)

st.sidebar.divider()
st.sidebar.header("📈 รูปแบบการแสดงผลกราฟ")
chart_type = st.sidebar.radio("เลือกรูปแบบกราฟ (เฉพาะ kW):", ["กราฟแท่ง (Bar)", "กราฟเส้น (Line)"])
is_bar = "แท่ง" in chart_type

st.sidebar.divider()
uploaded_file = st.sidebar.file_uploader("📂 อัปโหลดไฟล์ข้อมูล", type=['csv', 'xlsx', 'xls', 'txt'])

if uploaded_file is not None:
    file_ext = uploaded_file.name.split('.')[-1].lower()
    
    with st.spinner('กำลังวิเคราะห์และจัดโครงสร้างข้อมูล...'):
        df_raw = load_file(uploaded_file, file_ext)
        df_master = preprocess_and_analyze(df_raw, sensitivity)
        snapshots = get_usage_snapshots(df_master)

    st.sidebar.divider()
    st.sidebar.header("🔍 ระบบ Snapshot (กรองช่วงเวลา)")
    snapshot_options = ["🌐 ดูข้อมูลทั้งหมด (All Data)"] + [s['label'] for s in snapshots]
    selected_snapshot = st.sidebar.selectbox("เลือกช่วงเวลาทำงาน:", snapshot_options)

    if selected_snapshot == "🌐 ดูข้อมูลทั้งหมด (All Data)":
        df_display = df_master.copy()
    else:
        selected_s = next(s for s in snapshots if s['label'] == selected_snapshot)
        df_display = df_master.iloc[selected_s['start_idx'] : selected_s['end_idx'] + 1].copy()

    if selected_snapshot != "🌐 ดูข้อมูลทั้งหมด (All Data)":
        st.success(f"🎯 **โหมด Snapshot ทำงาน:** กำลังแสดงผลเฉพาะช่วงเวลา {selected_snapshot}")

    # ==========================================
    # 📑 ส่วนที่ 3: สร้าง Tabs แสดงผลข้อมูล
    # ==========================================
    tab1, tab2, tab3, tab4 = st.tabs([
        "🌐 ภาพรวมทั้งหมด", 
        "📅 เจาะลึกรายวัน",
        "🔄 จำลองเลื่อนเวลา (15 นาที)",
        "📋 สรุปและข้อมูลดิบ"
    ])

    # --- TAB 1: ภาพรวม ---
    with tab1:
        all_anomalies = df_display[df_display['Anomaly_Type'] != 'ปกติ']
        
        st.subheader("กราฟแสดงความต้องการพลังงานไฟฟ้า (kW)")
        fig_all = go.Figure()
        
        # ปรับเปลี่ยนกราฟตามที่ผู้ใช้เลือก (แท่ง หรือ เส้น)
        if is_bar:
            fig_all.add_trace(go.Bar(x=df_display['Clock'], y=df_display['kW_Import'], name="การใช้ไฟปกติ", marker_color="#1d3557"))
        else:
            fig_all.add_trace(go.Scatter(x=df_display['Clock'], y=df_display['kW_Import'], mode='lines', name="การใช้ไฟปกติ", fill='tozeroy', line=dict(color="#1d3557", width=2)))
        
        high_all = all_anomalies[all_anomalies['Anomaly_Type'] == 'สูงกว่าเกณฑ์ (High)']
        if not high_all.empty:
            fig_all.add_trace(go.Scatter(x=high_all['Clock'], y=high_all['kW_Import'], mode='markers', name='สูงกว่าเกณฑ์', marker=dict(color='red', size=8)))
            
        low_all = all_anomalies[all_anomalies['Anomaly_Type'] == 'ไฟตก (Low)']
        if not low_all.empty:
            fig_all.add_trace(go.Scatter(x=low_all['Clock'], y=low_all['kW_Import'], mode='markers', name='ต่ำกว่าเกณฑ์', marker=dict(color='orange', size=8)))

        fig_all.update_layout(height=400, template="plotly_white", hovermode="x unified")
        st.plotly_chart(fig_all, use_container_width=True)
        
        st.subheader("พลังงานไฟฟ้าสะสม (Cumulative kWh)")
        fig_cumsum = go.Figure()
        fig_cumsum.add_trace(go.Bar(x=df_display['Clock'], y=df_display['Cumulative_kWh_Total'], marker_color="#457b9d"))
        fig_cumsum.update_layout(height=350, template="plotly_white", hovermode="x unified")
        st.plotly_chart(fig_cumsum, use_container_width=True)

    # --- TAB 2: รายวัน ---
    with tab2:
        available_dates = sorted(df_display['Date'].unique())
        if len(available_dates) > 0:
            col_date, _ = st.columns([1, 3])
            selected_date = col_date.selectbox("📅 เลือกวันที่ต้องการเจาะลึก", available_dates)
            
            day_df = df_display[df_display['Date'] == selected_date].copy()
            day_df['Cumulative_kWh_Daily'] = day_df['kWh_15min'].cumsum()

            fig_15min = make_subplots(rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.1, subplot_titles=("พลังงาน (kW)", "พลังงานสะสมรายวัน (kWh)", "แรงดันไฟฟ้า (V)"))
            
            # ปรับกราฟย่อยตามที่เลือกเช่นกัน
            if is_bar:
                fig_15min.add_trace(go.Bar(x=day_df['Clock'], y=day_df['kW_Import'], marker_color="#f4a261", name="kW"), row=1, col=1)
            else:
                fig_15min.add_trace(go.Scatter(x=day_df['Clock'], y=day_df['kW_Import'], mode='lines', fill='tozeroy', line=dict(color="#f4a261", width=2), name="kW"), row=1, col=1)
                
            fig_15min.add_trace(go.Bar(x=day_df['Clock'], y=day_df['Cumulative_kWh_Daily'], marker_color="#2a9d8f", name="kWh"), row=2, col=1)
            fig_15min.add_trace(go.Bar(x=day_df['Clock'], y=day_df['Voltage'], marker_color="#e63946", name="Volt"), row=3, col=1)
            
            fig_15min.update_layout(height=700, template="plotly_white", hovermode="x unified", showlegend=False)
            st.plotly_chart(fig_15min, use_container_width=True)

    # --- TAB 3: เลื่อนเวลา (Shift Time) ทีละ 15 นาที ---
    with tab3:
        st.subheader("🔄 ระบบจำลองการเลื่อนช่วงเวลาและเปรียบเทียบ")
        # เปลี่ยนเป็นปรับทีละ 15 นาที
        shift_minutes = st.number_input("⏱️ จำนวนนาทีที่ต้องการเลื่อน (ปรับทีละ 15 นาที, ค่าบวก=เลื่อนไปข้างหน้า, ค่าลบ=ถอยหลัง)", value=15, step=15)
        
        df_new = df_display.copy()
        df_new['Original_Clock'] = df_new['Clock'] 
        df_new['Clock'] = df_new['Clock'] + pd.to_timedelta(shift_minutes, unit='m')
        
        csv_buffer = df_new.to_csv(index=False).encode('utf-8-sig')
        st.download_button("📥 ดาวน์โหลดไฟล์ที่ปรับเวลาแล้ว (.csv)", data=csv_buffer, file_name=f"shifted_{shift_minutes}mins.csv", mime="text/csv")
        
        st.divider()
        
        available_dates_old = sorted(df_display['Date'].unique())
        if len(available_dates_old) > 0:
            view_date = st.selectbox("📅 เลือกวันที่ต้องการเปรียบเทียบกราฟ", available_dates_old, key="shift_date_selector")
            
            plot_old = df_display[df_display['Date'] == view_date].sort_values('Clock')
            plot_new = df_new[df_new['Original_Clock'].dt.date == view_date].sort_values('Clock')
            
            fig_compare = go.Figure()
            fig_compare.add_trace(go.Scatter(x=plot_old['Clock'], y=plot_old['kW_Import'], mode='lines+markers', name='เก่า (Original)', line=dict(color='#1d3557', width=3)))
            fig_compare.add_trace(go.Scatter(x=plot_new['Clock'], y=plot_new['kW_Import'], mode='lines+markers', name=f'ใหม่ (Shifted {shift_minutes} นาที)', line=dict(color='#e63946', width=2.5, dash='dash')))
            
            fig_compare.update_layout(title="กราฟเส้นเปรียบเทียบข้อมูลเดิม เทียบกับ ข้อมูลใหม่", height=450, template="plotly_white", hovermode="x unified")
            st.plotly_chart(fig_compare, use_container_width=True)

            with st.expander("📋 ดูตารางเปรียบเทียบเวลา (ตรวจสอบความถูกต้อง)"):
                compare_table = pd.DataFrame({
                    "เวลาดั้งเดิม (Original)": plot_new['Original_Clock'].dt.strftime('%d/%m/%y %H:%M'),
                    "เวลาใหม่ที่เลื่อนแล้ว (Shifted)": plot_new['Clock'].dt.strftime('%d/%m/%y %H:%M'),
                    "การใช้ไฟฟ้า (kW)": plot_new['kW_Import']
                }).reset_index(drop=True)
                st.dataframe(compare_table, use_container_width=True)

    # --- TAB 4: สรุปและข้อมูลดิบ ---
    with tab4:
        st.subheader("📊 สรุปข้อมูล (Summary of Selected Period)")
        kpi1, kpi2, kpi3 = st.columns(3)
        kpi1.metric("พลังงานรวม (Total kWh)", f"{df_display['kWh_15min'].sum():,.2f}")
        kpi2.metric("ความต้องการไฟฟ้าสูงสุด (Peak kW)", f"{df_display['kW_Import'].max():,.2f}")
        kpi3.metric("จุดผิดปกติ (Anomalies)", f"{len(df_display[df_display['Anomaly_Type'] != 'ปกติ'])}")

        st.divider()
        st.write("📋 **ตารางข้อมูลดิบ (Raw Data Table)**")
        st.dataframe(df_display[['Clock', 'kW_Import', 'Voltage', 'kWh_15min', 'Anomaly_Type']].reset_index(drop=True), use_container_width=True)

else:
    st.info("💡 โปรดอัปโหลดไฟล์ Excel, CSV หรือ TXT จากแถบด้านข้างซ้ายมือเพื่อเริ่มต้นการใช้งาน")