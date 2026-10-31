import logging
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st
import datetime

# --- นำเข้า (Import) โมดูลที่เราแยกไว้ ---
from data_handler import load_file, preprocess_data, get_usage_snapshots, sanitize_dataframe_for_csv, sanitize_filename
from tou_analyzer import apply_tou_and_anomaly

@st.cache_data
def convert_df_to_csv(df):
    return sanitize_dataframe_for_csv(df).to_csv(index=False).encode('utf-8-sig')

# ==========================================
# 🎨 Page Configuration & Custom CSS
# ==========================================
st.set_page_config(page_title="Load Profile & TOU Simulator", page_icon="⚡", layout="wide")

# ปรับแต่ง CSS เพื่อความสวยงามและทำให้ UI คลีนระดับมืออาชีพ
st.markdown("""
    <style>
        .block-container { padding-top: 2rem; padding-bottom: 2rem; }
        div[data-testid="stMetricValue"] { font-size: 1.8rem; color: #1d3557; }
        .stTabs [data-baseweb="tab-list"] { gap: 8px; }
        .stTabs [data-baseweb="tab"] { border-radius: 4px 4px 0px 0px; padding: 10px 16px; }
    </style>
""", unsafe_allow_html=True)

# ==========================================
# 🎛️ SIDEBAR: Controls & Upload
# ==========================================
with st.sidebar:
    st.header("📂 1. อัปโหลดข้อมูล")
    uploaded_files = st.file_uploader("ลากไฟล์ Excel, CSV, TXT ลงที่นี่", type=["csv", "xlsx", "xls", "txt"], accept_multiple_files=True, help="รองรับไฟล์ Load Profile จากการไฟฟ้า และไฟล์จาก Data Logger")
    
    st.divider()
    
    # 🔥 ปรับปรุงเพิ่มตัวเลือกประเภทการคิดค่าไฟ
    st.header("⚙️ 2. ตั้งค่าระบบคิดเงิน")
    rate_type = st.radio("ประเภทอัตราค่าไฟ:", ["TOU (Time of Use)", "อัตราเดียว (Single Rate)"], horizontal=True)
    
    with st.expander("💰 ตั้งค่าเรทราคา (บาท/หน่วย)", expanded=True):
        if rate_type == "TOU (Time of Use)":
            p_rate = st.number_input("เรท On-Peak", value=5.7982, format="%.4f")
            op_rate = st.number_input("เรท Off-Peak / Holiday", value=2.6369, format="%.4f")
            single_rate = None
        else:
            single_rate = st.number_input("เรทค่าไฟอัตราเดียว", value=4.5000, format="%.4f")
            p_rate = single_rate
            op_rate = single_rate

    with st.expander("⏰ ตั้งค่าเวลา On-Peak (สำหรับ TOU)", expanded=False):
        p_start = st.time_input("เวลาเริ่ม On-Peak", value=datetime.time(9, 0))
        p_end = st.time_input("เวลาสิ้นสุด On-Peak", value=datetime.time(22, 0))

    with st.expander("📅 ตั้งค่าวันหยุดนักขัตฤกษ์", expanded=False):
        st.caption("พิมพ์วันที่ (YYYY-MM-DD) คั่นด้วยลูกน้ำ (,)")
        curr_yr = datetime.date.today().year
        default_holidays = ", ".join([f"{curr_yr}-{m:02d}-{d:02d}" for m, d in [(1, 1), (4, 6), (4, 13), (4, 14), (4, 15), (5, 1), (5, 4), (6, 3), (7, 28), (8, 12), (10, 13), (10, 23), (12, 5), (12, 10), (12, 31)]])
        holiday_input = st.text_area("รายการวันหยุด:", value=default_holidays, height=120)
        holiday_list = [x.strip() for x in holiday_input.replace('\n', ',').split(',') if x.strip()]

    st.divider()
    
    st.header("📊 3. ตั้งค่าการแสดงผล")
    chart_type = st.sidebar.radio("เลือกรูปแบบกราฟ:", ["กราฟแท่ง (Bar)", "กราฟเส้น (Line)"])
    is_bar = "แท่ง" in chart_type
    sensitivity = st.slider("ความไวตรวจจับ Anomaly (ไฟกระชาก)", 1.0, 5.0, 2.5, 0.5)

# ==========================================
# 🖥️ MAIN DASHBOARD AREA
# ==========================================
st.title("⚡ Load Profile & Simulator \n(ระบบวิเคราะห์โหลดและจำลองค่าไฟ)")

# --- Welcome Screen (Empty State) ---
if not uploaded_files:
    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown("### 👋 ยินดีต้อนรับสู่ระบบวิเคราะห์โหลดและจำลองค่าไฟฟ้า (TOU)")
    col1, col2, col3 = st.columns(3)
    with col1:
        st.info("#### 📂 1. อัปโหลดไฟล์\nอัปโหลดไฟล์ Load Profile (.xlsx, .xls, .csv, .txt) ที่เมนูด้านซ้ายมือ สามารถเลือกหลายไฟล์พร้อมกันได้")
    with col2:
        st.warning("#### ⚙️ 2. ตรวจสอบตั้งค่า\nเลือกระบบค่าไฟ (TOU หรือ อัตราเดียว) กำหนดเรทราคาและเวลา On-Peak ให้ตรงกับบิลค่าไฟฟ้า")
    with col3:
        st.success("#### 📊 3. วิเคราะห์ผล\nดูแนวโน้มการใช้พลังงาน สัดส่วนช่วงเวลา และทดลอง 'จำลองเลื่อนเวลา' เพื่อคำนวณค่าไฟที่ประหยัดได้")

    with st.container(border=True):
        st.markdown("#### 📋 รูปแบบไฟล์และคอลัมน์ข้อมูลที่รองรับ (Supported File Format)")
        st.markdown(
            "ระบบรองรับไฟล์บันทึกการใช้ไฟฟ้า (Load Profile) ราย 15 นาที จากการไฟฟ้า (MEA/PEA) หรือเครื่องบันทึก Data Logger "
            "โดยมีคอลัมน์ข้อมูลหลักดังต่อไปนี้:"
        )

        sample_table_data = pd.DataFrame({
            "ชื่อคอลัมน์ที่รองรับ": [
                "วัน-เวลา (Clock / Date / Time / วันที่ / เวลา)",
                "กำลังไฟฟ้า (kW_Import / kW / Demand / กำลังไฟฟ้า)",
                "แรงดันไฟฟ้า (Voltage / Volt / V / แรงดัน)"
            ],
            "ความหมายและหน่วย": [
                "วันและเวลาที่บันทึกข้อมูล (ราย 15 นาที)",
                "กำลังไฟฟ้าที่ใช้งานจริง (กิโลวัตต์: kW)",
                "แรงดันไฟฟ้า ณ ขณะวัด (โวลต์: V) — หากไม่มี ระบบจะใช้ค่าปริยาย 220V"
            ],
            "ตัวอย่างข้อมูล (Sample)": [
                "2026-01-01 09:00:00 หรือ 01/01/2026 09:00",
                "150.50",
                "220.0"
            ]
        })

        st.dataframe(
            sample_table_data,
            width='stretch',
            hide_index=True,
            column_config={
                "ชื่อคอลัมน์ที่รองรับ": st.column_config.TextColumn("ชื่อคอลัมน์ที่รองรับ"),
                "ความหมายและหน่วย": st.column_config.TextColumn("ความหมายและหน่วย"),
                "ตัวอย่างข้อมูล (Sample)": st.column_config.TextColumn("ตัวอย่างข้อมูล (Sample)"),
            }
        )

        st.caption("💡 ระบบรองรับทั้งไฟล์ `.csv`, `.xlsx`, `.xls` และ `.txt` โดยหัวตารางสามารถอยู่บรรทัดใดก็ได้ใน 50 บรรทัดแรกของไฟล์")

        sample_csv_text = (
            "Clock,kW_Import,Voltage\n"
            "2026-01-01 08:30:00,45.20,220.5\n"
            "2026-01-01 08:45:00,48.10,221.0\n"
            "2026-01-01 09:00:00,120.50,219.8\n"
            "2026-01-01 09:15:00,155.00,219.2\n"
            "2026-01-01 09:30:00,180.20,218.5\n"
            "2026-01-01 09:45:00,175.80,218.9\n"
            "2026-01-01 10:00:00,165.40,219.5\n"
            "2026-01-01 10:15:00,170.00,219.0\n"
        )
        st.download_button(
            label="📥 ดาวน์โหลดไฟล์ตัวอย่างแม่แบบ (.csv)",
            data=sample_csv_text.encode('utf-8-sig'),
            file_name="load_profile_sample_template.csv",
            mime="text/csv",
            help="ดาวน์โหลดไฟล์ตัวอย่าง Load Profile สำหรับทดลองใช้งาน หรือใช้เป็นแม่แบบในการจัดเตรียมข้อมูล"
        )

    st.stop()

# --- Data Processing ---
def _render_skipped_files_notice(skipped_files):
    """แจ้งอย่างถาวรว่าไฟล์ใดถูกข้าม พร้อมสาเหตุและวิธีแก้ (ไม่ใช่แค่ toast ที่หายไป)"""
    details = "\n".join(f"- `{name}`: {reason}" for name, reason in skipped_files)
    st.warning(
        f"⚠️ ข้ามไฟล์ที่อ่านไม่ได้ {len(skipped_files)} ไฟล์\n\n"
        f"{details}\n\n"
        "**วิธีแก้:** ตรวจสอบว่าภายในไฟล์มีคอลัมน์วัน-เวลา (Clock / Date / Time) "
        "และกำลังไฟฟ้า (kW) ตามแม่แบบในหน้าแรก แล้วอัปโหลดไฟล์นั้นอีกครั้ง"
    )

with st.spinner('🔄 กำลังโหลด ประมวลผล และเชื่อมต่อข้อมูล...'):
    all_dfs = []
    skipped_files = []
    for file in uploaded_files:
        safe_filename = sanitize_filename(getattr(file, 'name', ''))
        file_ext = safe_filename.rsplit('.', 1)[-1].lower() if '.' in safe_filename else ''
        try:
            df_raw = load_file(file, file_ext)
            df_base = preprocess_data(df_raw)
            if not df_base.empty and 'Clock' in df_base.columns:
                all_dfs.append(df_base)
            else:
                skipped_files.append((safe_filename, "ไม่พบข้อมูลวัน-เวลาในไฟล์"))
                st.toast(f"⚠️ ข้ามไฟล์ '{safe_filename}' (ไม่มีข้อมูลเวลา)", icon="⚠️")
        except Exception as e:
            logging.error(f"Error reading file '{safe_filename}': {e}", exc_info=True)
            reason = str(e).strip() if isinstance(e, ValueError) else "รูปแบบไฟล์ไม่รองรับ หรือไฟล์อาจเสียหาย"
            skipped_files.append((safe_filename, reason))
            st.toast(f"❌ อ่านไฟล์ '{safe_filename}' ไม่ได้", icon="❌")

    if not all_dfs:
        st.error("⚠️ ไม่มีข้อมูลที่สามารถนำมาวิเคราะห์ได้เลย โปรดตรวจสอบไฟล์ที่อัปโหลด")
        if skipped_files:
            _render_skipped_files_notice(skipped_files)
        st.stop()

    df_combined = pd.concat(all_dfs, ignore_index=True)
    num_files = len(all_dfs)
    total_files = len(uploaded_files)
    del all_dfs
    df_combined = df_combined.sort_values(['Clock', 'kW_Import'], ascending=[True, False]).drop_duplicates(subset=['Clock'], keep='first').reset_index(drop=True)
    
    df_master = apply_tou_and_anomaly(df_combined, sensitivity, p_start, p_end, p_rate, op_rate, holiday_list)
    snapshots = get_usage_snapshots(df_master)

if skipped_files:
    _render_skipped_files_notice(skipped_files)
    st.success(f"✅ วิเคราะห์ข้อมูลสำเร็จ {num_files} จาก {total_files} ไฟล์")
else:
    st.success(f"✅ วิเคราะห์ข้อมูลสำเร็จ {num_files} ไฟล์")

if not df_master.empty:
    st.caption(
        f"📅 ข้อมูลที่อ่านได้: {df_master['Clock'].min():%d/%m/%Y %H:%M} ถึง "
        f"{df_master['Clock'].max():%d/%m/%Y %H:%M} • {len(df_master):,} แถว"
    )

# --- Snapshot Selector (Filter) ---
with st.container(border=True):
    col_snap1, col_snap2 = st.columns([1, 3])
    with col_snap1:
        st.markdown("#### 🔍 กรองช่วงเวลา")
    with col_snap2:
        snapshot_options = ["🌐 ดูข้อมูลทั้งหมด (All Data)"] + [s['label'] for s in snapshots]
        selected_snapshot = st.selectbox("เลือกรอบการทำงานของเครื่องจักร:", snapshot_options, label_visibility="collapsed")

if selected_snapshot == "🌐 ดูข้อมูลทั้งหมด (All Data)":
    df_display = df_master.copy()
else:
    sel_s = next((s for s in snapshots if s['label'] == selected_snapshot), None)
    if sel_s:
        df_display = df_master.iloc[sel_s['start_idx'] : sel_s['end_idx'] + 1].copy()
    else:
        df_display = df_master.copy()

# ==========================================
# 📑 TABS NAVIGATION
# ==========================================
tab1, tab2, tab3, tab4 = st.tabs([
    "📈 1. ภาพรวมพลังงาน (Overview)", 
    "📅 2. เจาะลึกรายวัน (Daily Insights)", 
    "🔄 3. กราฟจำลองเวลา (Shift Graph)", 
    "💰 4. วิเคราะห์ค่าไฟ & จำลอง (Cost Simulator)"
])

# ------------------------------------------
# TAB 1: ภาพรวมทั้งหมด
# ------------------------------------------
with tab1:
    with st.container(border=True):
        st.markdown("#### ⚡ สรุปภาพรวมพลังงาน (Executive Summary)")
        m1, m2, m3, m4 = st.columns(4)
        total_kwh_display = df_display['kWh_15min'].sum() if not df_display.empty else 0.0
        peak_kw_display = df_display['kW_Import'].max() if not df_display.empty else 0.0
        total_cost_display = df_display['Cost_THB'].sum() if not df_display.empty else 0.0
        avg_kw_display = df_display['kW_Import'].mean() if not df_display.empty else 0.0

        m1.metric(
            "⚡ พลังงานไฟฟ้ารวม", 
            f"{total_kwh_display:,.2f} kWh", 
            help="ปริมาณพลังงานไฟฟ้ารวมทั้งหมดที่ใช้ในช่วงเวลาที่เลือก (หน่วย หรือ kWh)"
        )
        m2.metric(
            "🔥 ความต้องการไฟฟ้าสูงสุด (Peak)", 
            f"{peak_kw_display:,.2f} kW", 
            help="กำลังไฟฟ้าสูงสุดที่เกิดขึ้นในช่วงเวลาที่เลือก (Peak Demand)"
        )
        m3.metric(
            "💰 ค่าไฟฟ้าประเมินรวม", 
            f"฿ {total_cost_display:,.2f}", 
            help="ประมาณการค่าไฟฟ้าทั้งหมดตามอัตราค่าไฟที่ตั้งไว้"
        )
        m4.metric(
            "📈 โหลดไฟฟ้าเฉลี่ย", 
            f"{avg_kw_display:,.2f} kW", 
            help="กำลังไฟฟ้าเฉลี่ยตลอดช่วงเวลาที่เลือก"
        )

    st.subheader("📈 กราฟความต้องการพลังงานไฟฟ้ารวมและจุดผิดปกติ (kW)")
    fig_all = go.Figure()
    # ⚡ Bolt Optimization: Use map instead of apply for simple dictionary lookup
    color_map = {'Holiday': '#ffd166', 'On-Peak': '#e76f51', 'Off-Peak': '#2a9d8f'}
    colors = df_display['Period_Detail'].map(color_map).fillna('#2a9d8f')
    
    if is_bar:
        fig_all.add_trace(go.Bar(x=df_display['Clock'], y=df_display['kW_Import'], marker_color=colors, name="กำลังไฟฟ้า (kW - แยกสีช่วงเวลา)"))
    else:
        fig_all.add_trace(go.Scatter(x=df_display['Clock'], y=df_display['kW_Import'], mode='lines', fill='tozeroy', line=dict(color="#1d3557", width=2), name="กำลังไฟฟ้า (kW - ภาพรวม)"))
    
    all_anomalies = df_display[df_display['Anomaly_Type'] != 'ปกติ']
    if not all_anomalies.empty:
        high_all = all_anomalies[all_anomalies['Anomaly_Type'] == 'สูงกว่าเกณฑ์ (High)']
        if not high_all.empty: fig_all.add_trace(go.Scatter(x=high_all['Clock'], y=high_all['kW_Import'], mode='markers', name='สูงกว่าเกณฑ์', marker=dict(color='red', size=8)))
        low_all = all_anomalies[all_anomalies['Anomaly_Type'] == 'ไฟตก (Low)']
        if not low_all.empty: fig_all.add_trace(go.Scatter(x=low_all['Clock'], y=low_all['kW_Import'], mode='markers', name='ไฟตก', marker=dict(color='blue', size=8)))

    fig_all.update_layout(
        xaxis_title="วัน-เวลา (Timestamp)",
        yaxis_title="กำลังไฟฟ้า (kW)",
        height=400,
        margin=dict(l=20, r=20, t=40, b=20),
        template="plotly_white",
        hovermode="x unified"
    )
    st.plotly_chart(fig_all, width='stretch')
    if rate_type == "TOU (Time of Use)":
        st.info("💡 สีส้ม = On-Peak | สีเขียว = Off-Peak (กลางคืน/เสาร์-อาทิตย์) | สีเหลือง = Holiday (วันหยุดราชการ) | 🔴 จุดสีแดง = โหลดสูงผิดปกติ | 🔵 จุดสีน้ำเงิน = ไฟตก")
    else:
        st.info("💡 สีส้ม = เวลากลางวัน (09:00-22:00) | สีเขียว/เหลือง = เวลากลางคืนและวันหยุด (อ้างอิงช่วงเวลาเพื่อดูพฤติกรรม) | 🔴 จุดสีแดง = โหลดสูงผิดปกติ | 🔵 จุดสีน้ำเงิน = ไฟตก")
    
    st.subheader("⚡ กราฟความต้องการพลังงานไฟฟ้า (kW) ราย 15 นาที")
    fig_kw_each = go.Figure()
    fig_kw_each.add_trace(go.Bar(x=df_display['Clock'], y=df_display['kW_Import'], marker_color="#457b9d", name="กำลังไฟฟ้า (kW)"))
    fig_kw_each.update_layout(
        xaxis_title="วัน-เวลา (Timestamp)",
        yaxis_title="กำลังไฟฟ้า (kW)",
        height=350,
        margin=dict(l=20, r=20, t=20, b=20),
        template="plotly_white",
        hovermode="x unified"
    )
    st.plotly_chart(fig_kw_each, width='stretch')

    st.subheader("🔋 กราฟพลังงานไฟฟ้า (kWh) ราย 15 นาที")
    fig_kwh_each = go.Figure()
    fig_kwh_each.add_trace(go.Bar(x=df_display['Clock'], y=df_display['kWh_15min'], marker_color="#2a9d8f", name="พลังงานไฟฟ้า (kWh)"))
    fig_kwh_each.update_layout(
        xaxis_title="วัน-เวลา (Timestamp)",
        yaxis_title="พลังงานไฟฟ้า (kWh)",
        height=350,
        margin=dict(l=20, r=20, t=20, b=20),
        template="plotly_white",
        hovermode="x unified"
    )
    st.plotly_chart(fig_kwh_each, width='stretch')

    st.subheader("📊 กราฟพลังงานไฟฟ้ารวมรายวัน (Daily Total kWh)")
    df_daily_kwh = df_display.groupby('Date')['kWh_15min'].sum().reset_index()
    max_kwh = df_daily_kwh['kWh_15min'].max()
    
    fig_daily_kwh = go.Figure()
    fig_daily_kwh.add_trace(go.Bar(
        x=df_daily_kwh['Date'], 
        y=df_daily_kwh['kWh_15min'], 
        marker_color="#e76f51", 
        name="พลังงานไฟฟ้ารวมรายวัน (kWh)",
        text=df_daily_kwh['kWh_15min'].map('{:,.1f}'.format), 
        textposition='outside', 
        textfont=dict(size=14, color="#1d3557", family="Arial") 
    ))
    fig_daily_kwh.update_layout(
        xaxis_title="วันที่ (Date)",
        yaxis_title="พลังงานไฟฟ้ารวม (kWh)",
        height=400,
        margin=dict(l=20, r=20, t=40, b=20),
        template="plotly_white",
        hovermode="x unified",
        xaxis=dict(type='category', title="วันที่ (Date)"),
        yaxis=dict(title="พลังงานไฟฟ้ารวม (kWh)", range=[0, (max_kwh * 1.15) if (pd.notna(max_kwh) and max_kwh > 0) else 1.0])
    )
    fig_daily_kwh.update_yaxes(showgrid=True, gridcolor='lightgrey', griddash='dot')
    st.plotly_chart(fig_daily_kwh, width='stretch')

    st.subheader("📋 ตารางพลังงานไฟฟ้ารวมรายวัน (Daily Total kWh)")
    df_daily_table = df_daily_kwh.copy()
    df_daily_table.columns = ['วันที่ (Date)', 'พลังงานรวม (Total kWh)']
    
    st.dataframe(
        df_daily_table,
        width='stretch',
        hide_index=True,
        column_config={
            "วันที่ (Date)": st.column_config.DateColumn("วันที่ (Date)"),
            "พลังงานรวม (Total kWh)": st.column_config.NumberColumn("พลังงานรวม (Total kWh)", help="คลิกที่ชื่อคอลัมน์เพื่อเรียงลำดับจากมากไปน้อย", format="%.2f")
        }
    )

    daily_summary_csv = convert_df_to_csv(df_daily_table)
    st.download_button(
        label="📥 ดาวน์โหลดสรุปพลังงานรายวัน (.csv)",
        data=daily_summary_csv,
        file_name="daily_energy_summary.csv",
        mime="text/csv",
        help="ดาวน์โหลดข้อมูลสรุปพลังงานไฟฟ้ารายวันในรูปแบบไฟล์ CSV"
    )

    
# ------------------------------------------
# TAB 2: เจาะลึกรายวัน
# ------------------------------------------
with tab2:
    available_dates = [pd.Timestamp(d).date() for d in sorted(df_display['Date'].unique())]
    if available_dates:
        col_d1, col_d2 = st.columns([1, 3])
        with col_d1: sel_date = st.selectbox("📅 เลือกวันที่ต้องการเจาะลึก", available_dates)
        day_df = df_display[df_display['Date'] == pd.Timestamp(sel_date)].copy()

        with st.container(border=True):
            st.markdown(f"#### 📊 สรุปภาพรวมพลังงานประจำวันที่ {sel_date}")
            m_col1, m_col2, m_col3, m_col4 = st.columns(4)
            peak_day_kw = day_df['kW_Import'].max() if not day_df.empty else 0.0
            total_day_kwh = day_df['kWh_15min'].sum() if not day_df.empty else 0.0
            total_day_cost = day_df['Cost_THB'].sum() if not day_df.empty else 0.0
            avg_day_kw = day_df['kW_Import'].mean() if not day_df.empty else 0.0

            m_col1.metric(
                "🔥 โหลดสูงสุดประจำวัน (Peak)",
                f"{peak_day_kw:,.2f} kW",
                help="กำลังไฟฟ้าสูงสุดที่เกิดขึ้นในวันที่เลือก (Peak Demand)"
            )
            m_col2.metric(
                "⚡ พลังงานรวมประจำวัน (Total kWh)",
                f"{total_day_kwh:,.2f} kWh",
                help="ปริมาณพลังงานไฟฟ้ารวมตลอดทั้งวัน (kWh)"
            )
            m_col3.metric(
                "💰 ค่าไฟฟ้าประจำวัน",
                f"฿ {total_day_cost:,.2f}",
                help="ประมาณการค่าไฟฟ้ารวมในวันที่เลือก"
            )
            m_col4.metric(
                "📈 โหลดเฉลี่ยประจำวัน",
                f"{avg_day_kw:,.2f} kW",
                help="กำลังไฟฟ้าเฉลี่ยตลอดทั้งวัน"
            )

        st.markdown("##### 🧾 สรุปสัดส่วนตามช่วงเวลา (Period Breakdown)")
        summary_daily = day_df.groupby('Period_Detail')[['kW_Import', 'kWh_15min', 'Cost_THB']].sum().reset_index()
        summary_daily.columns = ['สถานะ (Period)', 'โหลดรวม (kW)', 'พลังงานรวม (kWh)', 'ค่าไฟฟ้า (บาท)']
        st.dataframe(
            summary_daily,
            width='stretch',
            hide_index=True,
            column_config={
                "สถานะ (Period)": st.column_config.TextColumn("สถานะ (Period)"),
                "โหลดรวม (kW)": st.column_config.NumberColumn("โหลดรวม (kW)", format="%.2f"),
                "พลังงานรวม (kWh)": st.column_config.NumberColumn("พลังงานรวม (kWh)", format="%.2f"),
                "ค่าไฟฟ้า (บาท)": st.column_config.NumberColumn("ค่าไฟฟ้า (บาท)", format="฿ %.2f"),
            }
        )

        fig_15min = make_subplots(rows=4, cols=1, shared_xaxes=True, vertical_spacing=0.06, 
                                  subplot_titles=("กำลังไฟฟ้า (kW)", "พลังงานทุก 15 นาที (kWh)", "แรงดันไฟฟ้า (V)", "ประมาณการค่าไฟฟ้าราย 15 นาที (บาท)"))
        
        color_map = {'Holiday': '#ffd166', 'On-Peak': '#e76f51', 'Off-Peak': '#2a9d8f'}
        day_colors = day_df['Period_Detail'].map(color_map).fillna('#2a9d8f')
        if is_bar:
            fig_15min.add_trace(go.Bar(x=day_df['Clock'], y=day_df['kW_Import'], marker_color=day_colors, name="กำลังไฟฟ้า (kW)"), row=1, col=1)
        else:
            fig_15min.add_trace(go.Scatter(x=day_df['Clock'], y=day_df['kW_Import'], mode='lines', fill='tozeroy', line=dict(color="#f4a261", width=2), name="กำลังไฟฟ้า (kW)"), row=1, col=1)

        day_anomalies = day_df[day_df['Anomaly_Type'] != 'ปกติ']
        if not day_anomalies.empty:
            high_day = day_anomalies[day_anomalies['Anomaly_Type'] == 'สูงกว่าเกณฑ์ (High)']
            if not high_day.empty:
                fig_15min.add_trace(go.Scatter(x=high_day['Clock'], y=high_day['kW_Import'], mode='markers', name='สูงกว่าเกณฑ์', marker=dict(color='red', size=8)), row=1, col=1)
            low_day = day_anomalies[day_anomalies['Anomaly_Type'] == 'ไฟตก (Low)']
            if not low_day.empty:
                fig_15min.add_trace(go.Scatter(x=low_day['Clock'], y=low_day['kW_Import'], mode='markers', name='ไฟตก', marker=dict(color='blue', size=8)), row=1, col=1)
            
        fig_15min.add_trace(go.Bar(x=day_df['Clock'], y=day_df['kWh_15min'], marker_color="#2a9d8f", name="พลังงานไฟฟ้า (kWh)"), row=2, col=1)
        
        fig_15min.add_trace(go.Bar(x=day_df['Clock'], y=day_df['Voltage'], marker_color="#e63946", name="แรงดันไฟฟ้า (V)"), row=3, col=1)
        fig_15min.update_yaxes(range=[day_df['Voltage'].min() - 5, day_df['Voltage'].max() + 5], row=3, col=1)
        
        fig_15min.add_trace(go.Bar(x=day_df['Clock'], y=day_df['Cost_THB'], marker_color="#8338ec", name="ค่าไฟฟ้า (บาท)"), row=4, col=1)
        
        fig_15min.update_yaxes(title_text="กำลังไฟฟ้า (kW)", row=1, col=1)
        fig_15min.update_yaxes(title_text="พลังงานไฟฟ้า (kWh)", row=2, col=1)
        fig_15min.update_yaxes(title_text="แรงดันไฟฟ้า (V)", row=3, col=1)
        fig_15min.update_yaxes(title_text="ค่าไฟฟ้า (บาท)", row=4, col=1)
        fig_15min.update_xaxes(title_text="วัน-เวลา (Timestamp)", row=4, col=1)

        fig_15min.update_layout(height=900, template="plotly_white", hovermode="x unified", showlegend=False, margin=dict(l=20, r=20, t=40, b=20))
        st.plotly_chart(fig_15min, width='stretch')
        if rate_type == "TOU (Time of Use)":
            st.info("💡 สีส้ม = On-Peak | สีเขียว = Off-Peak (กลางคืน/เสาร์-อาทิตย์) | สีเหลือง = Holiday (วันหยุดราชการ) | 🔴 จุดสีแดง = โหลดสูงผิดปกติ | 🔵 จุดสีน้ำเงิน = ไฟตก")
        else:
            st.info("💡 สีส้ม = เวลากลางวัน (09:00-22:00) | สีเขียว/เหลือง = เวลากลางคืนและวันหยุด | 🔴 จุดสีแดง = โหลดสูงผิดปกติ | 🔵 จุดสีน้ำเงิน = ไฟตก")

        st.markdown(f"#### 📋 ตารางข้อมูลดิบประจำวันที่ {sel_date}")
        day_raw_table = day_df[['Clock', 'kW_Import', 'kWh_15min', 'Voltage', 'Period_Detail', 'Rate_THB', 'Cost_THB', 'Anomaly_Type']].copy()
        day_raw_table.columns = [
            'วัน-เวลา (Timestamp)',
            'กำลังไฟฟ้า (kW)',
            'พลังงานไฟฟ้า (kWh)',
            'แรงดันไฟฟ้า (V)',
            'ช่วงเวลา (Period)',
            'อัตราค่าไฟ (บาท/หน่วย)',
            'ค่าไฟฟ้า (บาท)',
            'สถานะความผิดปกติ (Anomaly)'
        ]
        st.dataframe(
            day_raw_table,
            width='stretch',
            hide_index=True,
            column_config={
                "วัน-เวลา (Timestamp)": st.column_config.DatetimeColumn("วัน-เวลา (Timestamp)", format="YYYY-MM-DD HH:mm"),
                "กำลังไฟฟ้า (kW)": st.column_config.NumberColumn("กำลังไฟฟ้า (kW)", format="%.2f"),
                "พลังงานไฟฟ้า (kWh)": st.column_config.NumberColumn("พลังงานไฟฟ้า (kWh)", format="%.2f"),
                "แรงดันไฟฟ้า (V)": st.column_config.NumberColumn("แรงดันไฟฟ้า (V)", format="%.1f"),
                "ช่วงเวลา (Period)": st.column_config.TextColumn("ช่วงเวลา (Period)"),
                "อัตราค่าไฟ (บาท/หน่วย)": st.column_config.NumberColumn("อัตราค่าไฟ (บาท/หน่วย)", format="%.4f"),
                "ค่าไฟฟ้า (บาท)": st.column_config.NumberColumn("ค่าไฟฟ้า (บาท)", format="%.2f"),
                "สถานะความผิดปกติ (Anomaly)": st.column_config.TextColumn("สถานะความผิดปกติ (Anomaly)"),
            }
        )

        daily_csv_data = convert_df_to_csv(day_raw_table)
        st.download_button(
            label=f"📥 ดาวน์โหลดข้อมูลดิบรายวันที่ {sel_date} (.csv)",
            data=daily_csv_data,
            file_name=f"daily_load_profile_{sel_date}.csv",
            mime="text/csv",
            help="ดาวน์โหลดข้อมูล Load Profile ราย 15 นาทีของวันที่เลือกในรูปแบบไฟล์ CSV"
        )
    else:
        st.info("ℹ️ ไม่พบข้อมูลวันที่สำหรับเจาะลึก กรุณาตรวจสอบหรืออัปโหลดไฟล์ข้อมูล")

# ------------------------------------------
# TAB 3: จำลองเลื่อนเวลา (กราฟเปรียบเทียบ)
# ------------------------------------------
with tab3:
    st.subheader("🔄 ระบบจำลองการเลื่อนช่วงเวลาและเปรียบเทียบ")
    
    with st.container(border=True):
        col_s1, col_s2 = st.columns([1, 1])
        with col_s1:
            shift_minutes = st.number_input(
                "⏱️ จำนวนนาทีที่ต้องการเลื่อน (ปรับทีละ 15 นาที, ค่าบวก=เลื่อนไปข้างหน้า, ค่าลบ=ถอยหลัง)",
                value=15,
                step=15,
                help="ค่าบวก (+) = เลื่อนเวลาไปข้างหน้า, ค่าลบ (-) = เลื่อนเวลาถอยหลัง"
            )
        with col_s2:
            dates_for_shift = ["ดูทั้งหมด (ตั้งแต่ต้นจนจบ)"] + [pd.Timestamp(d).date() for d in sorted(df_display['Date'].unique())]
            view_date = st.selectbox("📅 เลือกรูปแบบการเปรียบเทียบกราฟ", dates_for_shift, key="shift_date_selector")
    
    df_new = df_display.copy()
    df_new['Original_Clock'] = df_new['Clock'] 
    df_new['Clock'] = df_new['Clock'] + pd.to_timedelta(shift_minutes, unit='m')
    df_new['Date'] = df_new['Clock'].dt.normalize()
    df_new_recalc = apply_tou_and_anomaly(df_new, sensitivity, p_start, p_end, p_rate, op_rate, holiday_list)

    if view_date == "ดูทั้งหมด (ตั้งแต่ต้นจนจบ)":
        plot_old, plot_new = df_display.sort_values('Clock'), df_new_recalc.sort_values('Clock')
        title_text = "กราฟเส้นเปรียบเทียบข้อมูลเดิม เทียบกับ ข้อมูลใหม่ (ทั้งหมด)"
    else:
        plot_old = df_display[df_display['Date'] == pd.Timestamp(view_date)].sort_values('Clock')
        plot_new = df_new_recalc[df_new_recalc['Original_Clock'].dt.normalize() == pd.Timestamp(view_date)].sort_values('Clock')
        title_text = f"กราฟเส้นเปรียบเทียบข้อมูลเดิม เทียบกับ ข้อมูลใหม่ ประจำวันที่ {view_date}"

    peak_old = plot_old['kW_Import'].max() if not plot_old.empty else 0.0
    peak_new = plot_new['kW_Import'].max() if not plot_new.empty else 0.0
    diff_peak = peak_new - peak_old

    cost_old = plot_old['Cost_THB'].sum() if not plot_old.empty else 0.0
    cost_new = plot_new['Cost_THB'].sum() if not plot_new.empty else 0.0
    diff_cost = cost_new - cost_old

    onpeak_old = plot_old[plot_old['Period_Detail'] == 'On-Peak']['kWh_15min'].sum() if not plot_old.empty else 0.0
    onpeak_new = plot_new[plot_new['Period_Detail'] == 'On-Peak']['kWh_15min'].sum() if not plot_new.empty else 0.0
    diff_onpeak = onpeak_new - onpeak_old

    with st.container(border=True):
        st.markdown("#### ⚡ สรุปผลกระทบจากการเลื่อนเวลา (Before vs After)")
        mc1, mc2, mc3, mc4 = st.columns(4)
        mc1.metric(
            "🔥 โหลดสูงสุดเปรียบเทียบ (Peak)",
            f"{peak_new:,.2f} kW",
            delta=f"{diff_peak:,.2f} kW",
            delta_color="inverse",
            help="กำลังไฟฟ้าสูงสุดหลังเลื่อนเวลา เทียบกับก่อนเลื่อน (เดิม: {:,.2f} kW)".format(peak_old)
        )
        mc2.metric(
            "⚡ พลังงานช่วง On-Peak",
            f"{onpeak_new:,.2f} kWh",
            delta=f"{diff_onpeak:,.2f} kWh",
            delta_color="inverse",
            help="ปริมาณพลังงาน On-Peak หลังเลื่อนเวลา เทียบกับก่อนเลื่อน (เดิม: {:,.2f} kWh)".format(onpeak_old)
        )
        mc3.metric(
            "💰 ค่าไฟฟ้าประเมินเปรียบเทียบ",
            f"฿ {cost_new:,.2f}",
            delta=f"{diff_cost:,.2f} ฿",
            delta_color="inverse",
            help="ค่าไฟฟ้าประเมินหลังเลื่อนเวลา เทียบกับก่อนเลื่อน (เดิม: ฿ {:,.2f})".format(cost_old)
        )
        mc4.metric(
            "⏱️ เวลาที่จำลองเลื่อน",
            f"{shift_minutes:+d} นาที" if shift_minutes != 0 else "0 นาที (เวลาเดิม)",
            help="ระยะเวลาที่เลื่อน (ค่าบวก=เลื่อนไปข้างหน้า, ค่าลบ=ถอยหลัง)"
        )

    fig_compare = go.Figure()
    fig_compare.add_trace(go.Scatter(x=plot_old['Clock'], y=plot_old['kW_Import'], mode='lines+markers', name='เก่า (Original)', line=dict(color='#1d3557', width=3)))
    fig_compare.add_trace(go.Scatter(x=plot_new['Clock'], y=plot_new['kW_Import'], mode='lines+markers', name=f'ใหม่ (Shifted {shift_minutes} นาที)', line=dict(color='#e63946', width=2.5, dash='dash')))
    fig_compare.update_layout(
        title=title_text,
        xaxis_title="วัน-เวลา (Timestamp)",
        yaxis_title="กำลังไฟฟ้า (kW)",
        height=500,
        template="plotly_white",
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
    )
    st.plotly_chart(fig_compare, width='stretch')
    st.caption("💡 กราฟเส้นสีน้ำเงินเข้มแสดงข้อมูลเดิม และเส้นประสีแดงแสดงข้อมูลหลังเลื่อนเวลา สามารถลากเมาส์เพื่อซูมดูช่วงเวลาที่ต้องการได้")

    csv_data = convert_df_to_csv(df_new_recalc)
    st.download_button(
        label="📥 ดาวน์โหลดไฟล์ที่ปรับเวลาแล้ว (.csv)",
        data=csv_data,
        file_name=f"shifted_{shift_minutes}mins.csv",
        mime="text/csv",
        help="ดาวน์โหลดข้อมูล Load Profile ที่ปรับเวลาแล้วในรูปแบบไฟล์ CSV"
    )

# ------------------------------------------
# TAB 4: สรุปข้อมูล และ ค่าไฟฟ้า
# ------------------------------------------
with tab4:
    with st.container(border=True):
        st.markdown("#### ⚙️ เลือกขอบเขตการคำนวณค่าไฟฟ้า")
        # --- อัปเดตส่วนนี้ เพิ่ม "กำหนดช่วงเวลา (Custom)" ---
        summary_mode = st.radio("ระดับการสรุปผล:", ["ภาพรวมทั้งหมด (Total)", "รายเดือน (Monthly)", "รายวัน (Daily)", "กำหนดช่วงเวลา (Custom)"], horizontal=True, label_visibility="collapsed")
        
        if summary_mode == "รายวัน (Daily)":
            # ⚡ Bolt Optimization: Cast Streamlit UI selectbox outputs to pd.Timestamp for valid datetime64 matching
            daily_dates_ui = [pd.Timestamp(d).date() for d in sorted(df_display['Date'].unique())]
            df_summary = df_display[df_display['Date'] == pd.Timestamp(st.selectbox("📅 เลือกวัน:", daily_dates_ui))]
        elif summary_mode == "รายเดือน (Monthly)":
            df_summary = df_display[df_display['Month'] == st.selectbox("📅 เลือกเดือน:", sorted(df_display['Month'].unique()))]
        elif summary_mode == "กำหนดช่วงเวลา (Custom)":
            # ⚡ Bolt Optimization: Use iloc for min/max on already sorted data (handle empty safely)
            if not df_display.empty:
                min_date = pd.Timestamp(df_display['Date'].iloc[0]).date()
                max_date = pd.Timestamp(df_display['Date'].iloc[-1]).date()
            else:
                min_date = pd.Timestamp(df_display['Date'].min()).date() if not pd.isna(df_display['Date'].min()) else None
                max_date = pd.Timestamp(df_display['Date'].max()).date() if not pd.isna(df_display['Date'].max()) else None
            
            date_range = st.date_input(
                "📅 เลือกช่วงเวลา (วันเริ่มต้น - วันสิ้นสุด):", 
                value=(min_date, max_date), 
                min_value=min_date, 
                max_value=max_date
            )
            
            if len(date_range) == 2:
                start_date, end_date = date_range
                df_summary = df_display[(df_display['Date'] >= pd.Timestamp(start_date)) & (df_display['Date'] <= pd.Timestamp(end_date))]
            elif len(date_range) > 0:
                st.info("📅 กำลังเลือกช่วงเวลา: กรุณาคลิกเลือกวันสิ้นสุดให้ครบถ้วน (ระบบแสดงผลเฉพาะวันเริ่มต้นชั่วคราว)")
                df_summary = df_display[df_display['Date'] == pd.Timestamp(date_range[0])]
            else:
                df_summary = df_display.iloc[:0]
        else:
            df_summary = df_display
            
    if df_summary.empty:
        st.info("ℹ️ ไม่พบข้อมูลการใช้ไฟฟ้าในช่วงเวลาที่เลือก กรุณาตรวจสอบหรือเลือกช่วงวันที่ใหม่")
    else:
        st.markdown("### 📊 สถานะปัจจุบัน (ก่อนจำลองเลื่อนเวลา)")
        orig_cost = df_summary['Cost_THB'].sum()
        total_kw = df_summary['kW_Import'].sum()
        
        with st.container(border=True):
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("พลังงานที่ใช้ทั้งหมด", f"{df_summary['kWh_15min'].sum():,.1f} kWh")
            c2.metric("โหลดรวมทั้งหมด", f"{total_kw:,.1f} kW")
            c3.metric("ค่าไฟฟ้าประเมิน", f"฿ {orig_cost:,.2f}")
            c4.metric("จุดผิดปกติ (Anomaly)", f"{len(df_summary[df_summary['Anomaly_Type'] != 'ปกติ'])} จุด")

            # 🔥 ส่วนที่แก้ไขตามคำขอ: แสดงผล kWh และซ่อน Peak/Off-Peak หากเป็นอัตราเดียว
            st.markdown("##### 🧾 แยกรายละเอียดพลังงาน")
            cost_summary = df_summary.groupby('Period_Detail')[['kWh_15min', 'Cost_THB']].sum().reset_index()
            summary_dict = cost_summary.set_index('Period_Detail').to_dict('index')
            
            if rate_type == "TOU (Time of Use)":
                cc1, cc2, cc3 = st.columns(3)
                p_data = summary_dict.get('On-Peak', {'kWh_15min': 0.0, 'Cost_THB': 0.0})
                cc1.error(f"**🔴 On-Peak** ({p_rate} บ.)\n\nพลังงาน: {p_data['kWh_15min']:,.2f} kWh\n\n**เป็นเงิน: ฿ {p_data['Cost_THB']:,.2f}**")
                
                op_data = summary_dict.get('Off-Peak', {'kWh_15min': 0.0, 'Cost_THB': 0.0})
                cc2.success(f"**🟢 Off-Peak** ({op_rate} บ.)\n\nพลังงาน: {op_data['kWh_15min']:,.2f} kWh\n\n**เป็นเงิน: ฿ {op_data['Cost_THB']:,.2f}**")
                
                h_data = summary_dict.get('Holiday', {'kWh_15min': 0.0, 'Cost_THB': 0.0})
                cc3.warning(f"**🟡 Holiday** ({op_rate} บ.)\n\nพลังงาน: {h_data['kWh_15min']:,.2f} kWh\n\n**เป็นเงิน: ฿ {h_data['Cost_THB']:,.2f}**")
            else:
                total_kwh = df_summary['kWh_15min'].sum()
                total_cost = df_summary['Cost_THB'].sum()
                st.info(f"**⚡ อัตราเดียว (Single Rate)** ({single_rate} บาท/หน่วย)\n\n⚡ **พลังงานรวมทั้งหมด:** {total_kwh:,.2f} kWh\n\n💰 **เป็นเงินประเมินทั้งหมด:** ฿ {total_cost:,.2f}")

        st.markdown("### 🔄 ระบบจำลองค่าไฟฟ้า (Time-Shift Simulator)")
        with st.container(border=True):
            st.markdown("ทดลองเลื่อนรอบการทำงานของเครื่องจักร เพื่อเปรียบเทียบค่าไฟฟ้าและโหลดพลังงานในแต่ละช่วงเวลา")
            shift_mins_sim = st.number_input("⏱️ ใส่เวลาที่เลื่อน (นาที):", value=0, step=15, help="บวก = เลื่อนเวลาไปข้างหน้า, ลบ = ถอยหลัง")
                
            if shift_mins_sim != 0:
                df_sim = df_summary.copy()
                df_sim['Clock'] = df_sim['Clock'] + pd.to_timedelta(shift_mins_sim, unit='m')
                df_sim['Date'] = df_sim['Clock'].dt.normalize()
                df_sim = apply_tou_and_anomaly(df_sim, sensitivity, p_start, p_end, p_rate, op_rate, holiday_list)
                
                new_cost = df_sim['Cost_THB'].sum()
                new_total_kw = df_sim['kW_Import'].sum()
                
                st.markdown(f"#### 📊 สถานะคาดการณ์ (หลังเลื่อน {shift_mins_sim} นาที)")
                
                c1_sim, c2_sim, c3_sim, c4_sim = st.columns(4)
                c1_sim.metric("พลังงานที่ใช้ทั้งหมด", f"{df_sim['kWh_15min'].sum():,.1f} kWh")
                c2_sim.metric("โหลดรวมทั้งหมด", f"{new_total_kw:,.1f} kW")
                
                # คำนวณส่วนต่างราคาเพื่อแสดงลูกศรขึ้น/ลง
                diff_cost = new_cost - orig_cost
                c3_sim.metric("ค่าไฟฟ้าประเมินใหม่", f"฿ {new_cost:,.2f}", delta=f"{diff_cost:,.2f} ฿", delta_color="inverse")
                c4_sim.metric("จุดผิดปกติ (Anomaly)", f"{len(df_sim[df_sim['Anomaly_Type'] != 'ปกติ'])} จุด")

                # 🎯 กล่องสรุปผลต่างค่าไฟ (Simulation Outcome Alert Banner)
                pct_change = (abs(diff_cost) / orig_cost * 100) if orig_cost > 0 else 0.0
                if diff_cost < -0.005:
                    st.success(f"🎉 **ผลการจำลอง:** ประหยัดค่าไฟฟ้าได้ **฿ {abs(diff_cost):,.2f}** (ลดลง **{pct_change:.2f}%**) จากการเลื่อนเวลา {shift_mins_sim:+d} นาที")
                elif diff_cost > 0.005:
                    st.warning(f"⚠️ **ผลการจำลอง:** ค่าไฟฟ้าเพิ่มขึ้น **฿ {diff_cost:,.2f}** (เพิ่มขึ้น **{pct_change:.2f}%**) จากการเลื่อนเวลา {shift_mins_sim:+d} นาที (ควรพิจารณาปรับช่วงเวลาใหม่)")
                else:
                    st.info(f"ℹ️ **ผลการจำลอง:** ค่าไฟฟ้าคงเดิม ไม่มีการเปลี่ยนแปลง (ผลต่าง ฿ 0.00) จากการเลื่อนเวลา {shift_mins_sim:+d} นาที")

                st.markdown("##### 🧾 แยกรายละเอียดพลังงาน (เวลาจำลอง)")
                sim_cost_summary = df_sim.groupby('Period_Detail')[['kWh_15min', 'Cost_THB']].sum().reset_index()
                sim_dict = sim_cost_summary.set_index('Period_Detail').to_dict('index')

                if rate_type == "TOU (Time of Use)":
                    sc1, sc2, sc3 = st.columns(3)
                    p_data_sim = sim_dict.get('On-Peak', {'kWh_15min': 0.0, 'Cost_THB': 0.0})
                    sc1.error(f"**🔴 On-Peak** ({p_rate} บ.)\n\nพลังงาน: {p_data_sim['kWh_15min']:,.2f} kWh\n\n**เป็นเงิน: ฿ {p_data_sim['Cost_THB']:,.2f}**")

                    op_data_sim = sim_dict.get('Off-Peak', {'kWh_15min': 0.0, 'Cost_THB': 0.0})
                    sc2.success(f"**🟢 Off-Peak** ({op_rate} บ.)\n\nพลังงาน: {op_data_sim['kWh_15min']:,.2f} kWh\n\n**เป็นเงิน: ฿ {op_data_sim['Cost_THB']:,.2f}**")

                    h_data_sim = sim_dict.get('Holiday', {'kWh_15min': 0.0, 'Cost_THB': 0.0})
                    sc3.warning(f"**🟡 Holiday** ({op_rate} บ.)\n\nพลังงาน: {h_data_sim['kWh_15min']:,.2f} kWh\n\n**เป็นเงิน: ฿ {h_data_sim['Cost_THB']:,.2f}**")
                else:
                    sim_total_kwh = df_sim['kWh_15min'].sum()
                    sim_total_cost = df_sim['Cost_THB'].sum()
                    st.info(f"**⚡ อัตราเดียว (Single Rate)** ({single_rate} บาท/หน่วย)\n\n⚡ **พลังงานรวมทั้งหมด:** {sim_total_kwh:,.2f} kWh\n\n💰 **เป็นเงินประเมินทั้งหมด:** ฿ {sim_total_cost:,.2f}")

                st.markdown("##### 📋 ตารางข้อมูลหลังจำลองเวลา")
                sim_display_table = df_sim[['Clock', 'kW_Import', 'kWh_15min', 'Period_Detail', 'Rate_THB', 'Cost_THB', 'Anomaly_Type']].copy()
                sim_display_table.columns = [
                    'วัน-เวลา (Timestamp)',
                    'กำลังไฟฟ้า (kW)',
                    'พลังงานไฟฟ้า (kWh)',
                    'ช่วงเวลา (Period)',
                    'อัตราค่าไฟ (บาท/หน่วย)',
                    'ค่าไฟฟ้า (บาท)',
                    'สถานะความผิดปกติ (Anomaly)'
                ]
                st.dataframe(
                    sim_display_table,
                    width='stretch',
                    hide_index=True,
                    column_config={
                        "วัน-เวลา (Timestamp)": st.column_config.DatetimeColumn("วัน-เวลา (Timestamp)", format="YYYY-MM-DD HH:mm"),
                        "กำลังไฟฟ้า (kW)": st.column_config.NumberColumn("กำลังไฟฟ้า (kW)", format="%.2f"),
                        "พลังงานไฟฟ้า (kWh)": st.column_config.NumberColumn("พลังงานไฟฟ้า (kWh)", format="%.2f"),
                        "ช่วงเวลา (Period)": st.column_config.TextColumn("ช่วงเวลา (Period)"),
                        "อัตราค่าไฟ (บาท/หน่วย)": st.column_config.NumberColumn("อัตราค่าไฟ (บาท/หน่วย)", format="%.4f"),
                        "ค่าไฟฟ้า (บาท)": st.column_config.NumberColumn("ค่าไฟฟ้า (บาท)", format="%.2f"),
                        "สถานะความผิดปกติ (Anomaly)": st.column_config.TextColumn("สถานะความผิดปกติ (Anomaly)"),
                    }
                )

                sim_csv_data = convert_df_to_csv(df_sim)
                st.download_button(
                    label="📥 ดาวน์โหลดผลการจำลองค่าไฟ (.csv)",
                    data=sim_csv_data,
                    file_name=f"cost_simulation_shift_{shift_mins_sim}mins.csv",
                    mime="text/csv",
                    help="ดาวน์โหลดข้อมูลผลการจำลองค่าไฟฟ้าตามช่วงเวลาที่เลือกในรูปแบบ CSV"
                )
            else:
                st.info("รอการป้อนตัวเลขจำลองเวลา... (กรุณาใส่ตัวเลขที่ไม่ใช่ 0 ในช่องด้านบน)")


# --- Tests ---
def test_no_lambda_in_download_button():
    import ast
    with open('app.py', 'r', encoding='utf-8') as f:
        tree = ast.parse(f.read())

    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == 'download_button':
            if len(node.args) > 1 and isinstance(node.args[1], ast.Lambda):
                raise AssertionError("st.download_button should not use lambda for data")
            if 'data' in [kw.arg for kw in node.keywords]:
                for kw in node.keywords:
                    if kw.arg == 'data' and isinstance(kw.value, ast.Lambda):
                        raise AssertionError("st.download_button should not use lambda for data")

def test_empty_date_input_index_error():
    import ast
    with open('app.py', 'r', encoding='utf-8') as f:
        tree = ast.parse(f.read())

    found_check = False
    for node in ast.walk(tree):
        if isinstance(node, ast.If) or isinstance(node, ast.IfExp):
            # Check for len(date_range) > 0 condition
            if isinstance(node.test, ast.Compare):
                if isinstance(node.test.left, ast.Call) and getattr(node.test.left.func, 'id', '') == 'len':
                    if getattr(node.test.left.args[0], 'id', '') == 'date_range':
                        if isinstance(node.test.ops[0], ast.Gt) and isinstance(node.test.comparators[0], ast.Constant) and node.test.comparators[0].value == 0:
                            found_check = True
                        elif isinstance(node.test.ops[0], ast.Eq) and isinstance(node.test.comparators[0], ast.Constant) and node.test.comparators[0].value == 2:
                            # It could be `elif len(date_range) > 0:`
                            for orelse in node.orelse:
                                if isinstance(orelse, ast.If) and getattr(orelse.test, 'left', None):
                                    if getattr(orelse.test.left, 'func', None) and getattr(orelse.test.left.func, 'id', '') == 'len':
                                        if getattr(orelse.test.left.args[0], 'id', '') == 'date_range':
                                            if isinstance(orelse.test.ops[0], ast.Gt) and isinstance(orelse.test.comparators[0], ast.Constant) and orelse.test.comparators[0].value == 0:
                                                found_check = True

    if not found_check:
        raise AssertionError("Regression: len(date_range) > 0 check is missing to prevent IndexError on empty date_input")

def test_no_hardcoded_default_holidays():
    import ast
    with open('app.py', 'r', encoding='utf-8') as f:
        tree = ast.parse(f.read())
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == 'default_holidays':
                    if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                        if "2026-" in node.value.value:
                            raise AssertionError("Regression: default_holidays is hardcoded.")

def test_convert_df_to_csv_uses_sanitization():
    import ast
    with open('app.py', 'r', encoding='utf-8') as f:
        tree = ast.parse(f.read())

    found_sanitization = False
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == 'convert_df_to_csv':
            for child in ast.walk(node):
                if isinstance(child, ast.Call) and getattr(child.func, 'id', '') == 'sanitize_dataframe_for_csv':
                    found_sanitization = True
                    break

    if not found_sanitization:
        raise AssertionError("Regression: convert_df_to_csv must sanitize DataFrame against formula injection")

def test_no_exception_leakage_in_toast():
    import ast
    with open('app.py', 'r', encoding='utf-8') as f:
        tree = ast.parse(f.read())

    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and getattr(node.func, 'attr', '') == 'toast':
            for arg in node.args:
                if isinstance(arg, ast.JoinedStr):
                    for val in arg.values:
                        if isinstance(val, ast.FormattedValue):
                            if isinstance(val.value, ast.Name) and val.value.id == 'e':
                                raise AssertionError("Regression: Exception object leaked to UI via st.toast")
