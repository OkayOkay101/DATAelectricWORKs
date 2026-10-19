import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st
import datetime

# --- นำเข้า (Import) โมดูลที่เราแยกไว้ ---
from data_handler import load_file, preprocess_data, get_usage_snapshots
from tou_analyzer import apply_tou_and_anomaly

@st.cache_data
def convert_df_to_csv(df):
    return df.to_csv(index=False).encode('utf-8-sig')

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
    uploaded_files = st.file_uploader("ลากไฟล์ Excel, CSV, TXT ลงที่นี่", accept_multiple_files=True, help="รองรับไฟล์ Load Profile จากการไฟฟ้า และไฟล์จาก Data Logger")
    
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
        default_holidays = "2026-01-01, 2026-03-02, 2026-04-06, 2026-04-13, 2026-04-14, 2026-04-15, 2026-05-01, 2026-05-04, 2026-06-03, 2026-07-28, 2026-07-29, 2026-07-30, 2026-08-12, 2026-10-13, 2026-10-23, 2026-12-10, 2026-12-31"
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
    st.markdown("<br><br>", unsafe_allow_html=True)
    col1, col2, col3 = st.columns(3)
    with col1:
        st.info("#### 📂 1. อัปโหลดไฟล์\nอัปโหลดไฟล์ Load Profile (.xls, .csv, .txt) ที่เมนูด้านซ้ายมือ สามารถเลือกหลายไฟล์พร้อมกันได้")
    with col2:
        st.warning("#### ⚙️ 2. ตรวจสอบตั้งค่า\nเลือกระบบค่าไฟ (TOU หรือ อัตราเดียว) และตรวจสอบเรทราคาให้ตรงกับบิลค่าไฟของคุณ")
    with col3:
        st.success("#### 📊 3. วิเคราะห์ผล\nดูแนวโน้มการใช้พลังงาน และทดลอง 'จำลองเลื่อนเวลา' เพื่อดูพฤติกรรมโหลดที่เปลี่ยนไป")
    st.stop()

# --- Data Processing ---
with st.spinner('🔄 กำลังโหลด ประมวลผล และเชื่อมต่อข้อมูล...'):
    all_dfs = []
    for file in uploaded_files:
        file_ext = file.name.split('.')[-1].lower()
        try:
            df_raw = load_file(file, file_ext)
            df_base = preprocess_data(df_raw)
            if not df_base.empty and 'Clock' in df_base.columns:
                all_dfs.append(df_base)
            else:
                st.toast(f"⚠️ ข้ามไฟล์ '{file.name}' (ไม่มีข้อมูลเวลา)", icon="⚠️")
        except Exception as e:
            st.toast(f"❌ อ่านไฟล์ '{file.name}' ไม่ได้: {e}", icon="❌")

    if not all_dfs:
        st.error("⚠️ ไม่มีข้อมูลที่สามารถนำมาวิเคราะห์ได้เลย โปรดตรวจสอบไฟล์ที่อัปโหลด")
        st.stop()

    df_combined = pd.concat(all_dfs, ignore_index=True)
    num_files = len(all_dfs)
    del all_dfs
    df_combined = df_combined.sort_values(['Clock', 'kW_Import'], ascending=[True, False]).drop_duplicates(subset=['Clock'], keep='first').reset_index(drop=True)
    
    df_master = apply_tou_and_anomaly(df_combined, sensitivity, p_start, p_end, p_rate, op_rate, holiday_list)
    snapshots = get_usage_snapshots(df_master)
    
st.success(f"✅ วิเคราะห์ข้อมูลสำเร็จ {num_files} ไฟล์")

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
    st.subheader("กราฟแสดงความต้องการพลังงานไฟฟ้า (kW)")
    fig_all = go.Figure()
    # ⚡ Bolt Optimization: Use map instead of apply for simple dictionary lookup
    color_map = {'Holiday': '#ffd166', 'On-Peak': '#e76f51', 'Off-Peak': '#2a9d8f'}
    colors = df_display['Period_Detail'].map(color_map).fillna('#2a9d8f')
    
    if is_bar:
        fig_all.add_trace(go.Bar(x=df_display['Clock'], y=df_display['kW_Import'], marker_color=colors, name="kW (แยกสีช่วงเวลา)"))
    else:
        fig_all.add_trace(go.Scatter(x=df_display['Clock'], y=df_display['kW_Import'], mode='lines', fill='tozeroy', line=dict(color="#1d3557", width=2), name="kW (ภาพรวม)"))
    
    all_anomalies = df_display[df_display['Anomaly_Type'] != 'ปกติ']
    if not all_anomalies.empty:
        high_all = all_anomalies[all_anomalies['Anomaly_Type'] == 'สูงกว่าเกณฑ์ (High)']
        if not high_all.empty: fig_all.add_trace(go.Scatter(x=high_all['Clock'], y=high_all['kW_Import'], mode='markers', name='สูงกว่าเกณฑ์', marker=dict(color='red', size=8)))
        low_all = all_anomalies[all_anomalies['Anomaly_Type'] == 'ไฟตก (Low)']
        if not low_all.empty: fig_all.add_trace(go.Scatter(x=low_all['Clock'], y=low_all['kW_Import'], mode='markers', name='ไฟตก', marker=dict(color='blue', size=8)))

    fig_all.update_layout(height=400, margin=dict(l=20, r=20, t=40, b=20), template="plotly_white", hovermode="x unified")
    st.plotly_chart(fig_all, use_container_width=True)
    if rate_type == "TOU (Time of Use)":
        st.info("💡 สีส้ม = On-Peak | สีเขียว = Off-Peak (กลางคืน/เสาร์-อาทิตย์) | สีเหลือง = Holiday (วันหยุดราชการ)")
    else:
        st.info("💡 สีส้ม = เวลากลางวัน (09:00-22:00) | สีเขียว/เหลือง = เวลากลางคืนและวันหยุด (อ้างอิงช่วงเวลาเพื่อดูพฤติกรรม)")
    
    st.subheader("ความต้องการพลังงานไฟฟ้า (kW)")
    fig_kw_each = go.Figure()
    fig_kw_each.add_trace(go.Bar(x=df_display['Clock'], y=df_display['kW_Import'], marker_color="#457b9d", name="kW"))
    fig_kw_each.update_layout(height=350, margin=dict(l=20, r=20, t=20, b=20), template="plotly_white", hovermode="x unified")
    st.plotly_chart(fig_kw_each, use_container_width=True)

    st.subheader("พลังงานไฟฟ้า (kWh) ราย 15 นาที")
    fig_kwh_each = go.Figure()
    fig_kwh_each.add_trace(go.Bar(x=df_display['Clock'], y=df_display['kWh_15min'], marker_color="#2a9d8f", name="kWh"))
    fig_kwh_each.update_layout(height=350, margin=dict(l=20, r=20, t=20, b=20), template="plotly_white", hovermode="x unified")
    st.plotly_chart(fig_kwh_each, use_container_width=True)

    st.subheader("📊 กราฟพลังงานไฟฟ้ารวมรายวัน (Daily Total kWh)")
    df_daily_kwh = df_display.groupby('Date')['kWh_15min'].sum().reset_index()
    max_kwh = df_daily_kwh['kWh_15min'].max()
    
    fig_daily_kwh = go.Figure()
    fig_daily_kwh.add_trace(go.Bar(
        x=df_daily_kwh['Date'], 
        y=df_daily_kwh['kWh_15min'], 
        marker_color="#e76f51", 
        name="Total kWh/Day",
        text=df_daily_kwh['kWh_15min'].map('{:,.1f}'.format), 
        textposition='outside', 
        textfont=dict(size=14, color="#1d3557", family="Arial") 
    ))
    fig_daily_kwh.update_layout(height=400, margin=dict(l=20, r=20, t=40, b=20), template="plotly_white", hovermode="x unified", xaxis=dict(type='category'), yaxis=dict(range=[0, max_kwh * 1.15]))
    fig_daily_kwh.update_yaxes(showgrid=True, gridcolor='lightgrey', griddash='dot')
    st.plotly_chart(fig_daily_kwh, use_container_width=True)

    st.subheader("📋 ตารางพลังงานไฟฟ้ารวมรายวัน (Daily Total kWh)")
    df_daily_table = df_daily_kwh.copy()
    df_daily_table.columns = ['วันที่ (Date)', 'พลังงานรวม (Total kWh)']
    
    st.dataframe(
        df_daily_table,
        use_container_width=True,
        hide_index=True,
        column_config={
            "วันที่ (Date)": st.column_config.DateColumn("วันที่ (Date)"),
            "พลังงานรวม (Total kWh)": st.column_config.NumberColumn("พลังงานรวม (Total kWh)", help="คลิกที่ชื่อคอลัมน์เพื่อเรียงลำดับจากมากไปน้อย", format="%.2f")
        }
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

        st.markdown(f"#### 📊 สรุปสัดส่วนการใช้พลังงานประจำวันที่ {sel_date}")
        
        m_col1, m_col2, m_col3 = st.columns(3)
        m_col1.metric("โหลดรวมประจำวัน (Sum kW)", f"{day_df['kW_Import'].sum():,.2f} kW")
        m_col2.metric("พลังงานรวมประจำวัน (Total kWh)", f"{day_df['kWh_15min'].sum():,.2f} kWh")
        m_col3.metric("ค่าไฟฟ้าประจำวัน", f"฿ {day_df['Cost_THB'].sum():,.2f}")
        
        st.write("")
        summary_daily = day_df.groupby('Period_Detail')[['kW_Import', 'kWh_15min', 'Cost_THB']].sum().reset_index()
        summary_daily.columns = ['สถานะ (Period)', 'โหลดรวม (kW)', 'พลังงานรวม (kWh)', 'ค่าไฟฟ้า (บาท)']
        st.dataframe(summary_daily, use_container_width=True, hide_index=True)

        fig_15min = make_subplots(rows=4, cols=1, shared_xaxes=True, vertical_spacing=0.05, 
                                  subplot_titles=("พลังงาน (kW)", "พลังงานทุก 15 นาที (kWh)", "แรงดันไฟฟ้า (V)", "ประมาณการค่าไฟฟ้าราย 15 นาที (THB)"))
        
        color_map = {'Holiday': '#ffd166', 'On-Peak': '#e76f51', 'Off-Peak': '#2a9d8f'}
        day_colors = day_df['Period_Detail'].map(color_map).fillna('#2a9d8f')
        if is_bar: fig_15min.add_trace(go.Bar(x=day_df['Clock'], y=day_df['kW_Import'], marker_color=day_colors, name="kW"), row=1, col=1)
        else: fig_15min.add_trace(go.Scatter(x=day_df['Clock'], y=day_df['kW_Import'], mode='lines', fill='tozeroy', line=dict(color="#f4a261", width=2), name="kW"), row=1, col=1)
            
        fig_15min.add_trace(go.Bar(x=day_df['Clock'], y=day_df['kWh_15min'], marker_color="#2a9d8f", name="kWh"), row=2, col=1)
        
        fig_15min.add_trace(go.Bar(x=day_df['Clock'], y=day_df['Voltage'], marker_color="#e63946", name="Volt"), row=3, col=1)
        fig_15min.update_yaxes(range=[day_df['Voltage'].min() - 5, day_df['Voltage'].max() + 5], row=3, col=1)
        
        fig_15min.add_trace(go.Bar(x=day_df['Clock'], y=day_df['Cost_THB'], marker_color="#8338ec", name="THB"), row=4, col=1)
        
        fig_15min.update_layout(height=900, template="plotly_white", hovermode="x unified", showlegend=False, margin=dict(l=20, r=20, t=40, b=20))
        st.plotly_chart(fig_15min, use_container_width=True)

        st.markdown(f"#### 📋 ตารางข้อมูลดิบประจำวันที่ {sel_date}")
        st.dataframe(day_df[['Clock', 'kW_Import', 'kWh_15min', 'Voltage', 'Period_Detail', 'Rate_THB', 'Cost_THB', 'Anomaly_Type']].reset_index(drop=True), use_container_width=True)

# ------------------------------------------
# TAB 3: จำลองเลื่อนเวลา (กราฟเปรียบเทียบ)
# ------------------------------------------
with tab3:
    st.subheader("🔄 ระบบจำลองการเลื่อนช่วงเวลาและเปรียบเทียบ")
    shift_minutes = st.number_input("⏱️ จำนวนนาทีที่ต้องการเลื่อน (ปรับทีละ 15 นาที, ค่าบวก=เลื่อนไปข้างหน้า, ค่าลบ=ถอยหลัง)", value=15, step=15)
    
    df_new = df_display.copy()
    df_new['Original_Clock'] = df_new['Clock'] 
    df_new['Clock'] = df_new['Clock'] + pd.to_timedelta(shift_minutes, unit='m')
    df_new_recalc = apply_tou_and_anomaly(df_new, sensitivity, p_start, p_end, p_rate, op_rate, holiday_list)
    
    csv_data = convert_df_to_csv(df_new_recalc)
    st.download_button("📥 ดาวน์โหลดไฟล์ที่ปรับเวลาแล้ว (.csv)", csv_data, f"shifted_{shift_minutes}mins.csv")
    st.divider()
    
    dates_for_shift = ["ดูทั้งหมด (ตั้งแต่ต้นจนจบ)"] + [pd.Timestamp(d).date() for d in sorted(df_display['Date'].unique())]
    view_date = st.selectbox("📅 เลือกรูปแบบการเปรียบเทียบกราฟ", dates_for_shift, key="shift_date_selector")
    
    if view_date == "ดูทั้งหมด (ตั้งแต่ต้นจนจบ)":
        plot_old, plot_new = df_display.sort_values('Clock'), df_new_recalc.sort_values('Clock')
        title_text = "กราฟเส้นเปรียบเทียบข้อมูลเดิม เทียบกับ ข้อมูลใหม่ (ทั้งหมด)"
    else:
        plot_old = df_display[df_display['Date'] == pd.Timestamp(view_date)].sort_values('Clock')
        plot_new = df_new_recalc[df_new_recalc['Original_Clock'].dt.normalize() == pd.Timestamp(view_date)].sort_values('Clock')
        title_text = f"กราฟเส้นเปรียบเทียบข้อมูลเดิม เทียบกับ ข้อมูลใหม่ ประจำวันที่ {view_date}"
    
    fig_compare = go.Figure()
    fig_compare.add_trace(go.Scatter(x=plot_old['Clock'], y=plot_old['kW_Import'], mode='lines+markers', name='เก่า (Original)', line=dict(color='#1d3557', width=3)))
    fig_compare.add_trace(go.Scatter(x=plot_new['Clock'], y=plot_new['kW_Import'], mode='lines+markers', name=f'ใหม่ (Shifted {shift_minutes} นาที)', line=dict(color='#e63946', width=2.5, dash='dash')))
    fig_compare.update_layout(title=title_text, height=500, template="plotly_white", hovermode="x unified", legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
    st.plotly_chart(fig_compare, use_container_width=True)

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
                df_summary = df_display[df_display['Date'] == pd.Timestamp(date_range[0])]
            else:
                df_summary = df_display.iloc[:0]
        else:
            df_summary = df_display
            
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
            
            st.write("📋 **ข้อมูลดิบหลังจำลอง**")
            st.dataframe(df_sim[['Clock', 'kW_Import', 'Period_Detail', 'Cost_THB']].reset_index(drop=True), use_container_width=True, height=200)
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
