import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st
import datetime

# --- นำเข้า (Import) โมดูลที่เราแยกไว้ ---
from data_handler import load_file, preprocess_data, get_usage_snapshots
from tou_analyzer import apply_tou_and_anomaly, get_color

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
    
    st.header("⚙️ 2. ตั้งค่าระบบ TOU")
    with st.expander("💰 ตั้งค่าเรทราคา (บาท/หน่วย)", expanded=True):
        p_rate = st.number_input("เรท On-Peak", value=5.7982, format="%.4f")
        op_rate = st.number_input("เรท Off-Peak / Holiday", value=2.6369, format="%.4f")

    with st.expander("⏰ ตั้งค่าเวลา On-Peak", expanded=True):
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
st.title("⚡ Load Profile & TOU Simulator \n(ระบบวิเคราะห์โหลดและจำลองค่าไฟ TOU)")

# --- Welcome Screen (Empty State) ---
if not uploaded_files:
    st.markdown("<br><br>", unsafe_allow_html=True)
    col1, col2, col3 = st.columns(3)
    with col1:
        st.info("#### 📂 1. อัปโหลดไฟล์\nอัปโหลดไฟล์ Load Profile (.xls, .csv, .txt) ที่เมนูด้านซ้ายมือ สามารถเลือกหลายไฟล์พร้อมกันได้")
    with col2:
        st.warning("#### ⚙️ 2. ตรวจสอบตั้งค่า\nเช็คเรทราคาค่าไฟ TOU และช่วงเวลา On-Peak / Off-Peak ให้ตรงกับบิลค่าไฟของคุณ")
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
    df_combined = df_combined.sort_values(['Clock', 'kW_Import'], ascending=[True, False]).drop_duplicates(subset=['Clock'], keep='first').reset_index(drop=True)
    df_combined = df_combined.sort_values('Clock').reset_index(drop=True)
    df_combined['Cumulative_kWh_Total'] = df_combined['kWh_15min'].cumsum()
    
    df_master = apply_tou_and_anomaly(df_combined, sensitivity, p_start, p_end, p_rate, op_rate, holiday_list)
    snapshots = get_usage_snapshots(df_master)
    
st.success(f"✅ วิเคราะห์ข้อมูลสำเร็จ {len(all_dfs)} ไฟล์")

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
    sel_s = next(s for s in snapshots if s['label'] == selected_snapshot)
    df_display = df_master.iloc[sel_s['start_idx'] : sel_s['end_idx'] + 1].copy()

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
    colors = df_display['Period_Detail'].apply(get_color)
    
    if is_bar:
        fig_all.add_trace(go.Bar(x=df_display['Clock'], y=df_display['kW_Import'], marker_color=colors, name="kW (แยกสี TOU/Holiday)"))
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
    st.info("💡 สีส้ม = On-Peak | สีเขียว = Off-Peak (กลางคืน/เสาร์-อาทิตย์) | สีเหลือง = Holiday (วันหยุดราชการ)")
    
    st.subheader("ความต้องการพลังงานไฟฟ้า (kW)")
    fig_kw_each = go.Figure()
    fig_kw_each.add_trace(go.Bar(x=df_display['Clock'], y=df_display['kW_Import'], marker_color="#457b9d", name="kW"))
    fig_kw_each.update_layout(height=350, margin=dict(l=20, r=20, t=20, b=20), template="plotly_white", hovermode="x unified")
    st.plotly_chart(fig_kw_each, use_container_width=True)

    st.subheader("พลังงานไฟฟ้า (kWh)")
    fig_kwh_each = go.Figure()
    fig_kwh_each.add_trace(go.Bar(x=df_display['Clock'], y=df_display['kWh_15min'], marker_color="#2a9d8f", name="kWh"))
    fig_kwh_each.update_layout(height=350, margin=dict(l=20, r=20, t=20, b=20), template="plotly_white", hovermode="x unified")
    st.plotly_chart(fig_kwh_each, use_container_width=True)

# ------------------------------------------
# TAB 2: เจาะลึกรายวัน
# ------------------------------------------
with tab2:
    available_dates = sorted(df_display['Date'].unique())
    if available_dates:
        col_d1, col_d2 = st.columns([1, 3])
        with col_d1: sel_date = st.selectbox("📅 เลือกวันที่ต้องการเจาะลึก", available_dates)
        day_df = df_display[df_display['Date'] == sel_date].copy()

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
        
        day_colors = day_df['Period_Detail'].apply(get_color)
        if is_bar: fig_15min.add_trace(go.Bar(x=day_df['Clock'], y=day_df['kW_Import'], marker_color=day_colors, name="kW"), row=1, col=1)
        else: fig_15min.add_trace(go.Scatter(x=day_df['Clock'], y=day_df['kW_Import'], mode='lines', fill='tozeroy', line=dict(color="#f4a261", width=2), name="kW"), row=1, col=1)
            
        fig_15min.add_trace(go.Bar(x=day_df['Clock'], y=day_df['kWh_15min'], marker_color="#2a9d8f", name="kWh"), row=2, col=1)
        fig_15min.add_trace(go.Bar(x=day_df['Clock'], y=day_df['Voltage'], marker_color="#e63946", name="Volt"), row=3, col=1)
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
    
    st.download_button("📥 ดาวน์โหลดไฟล์ที่ปรับเวลาแล้ว (.csv)", df_new_recalc.to_csv(index=False).encode('utf-8-sig'), f"shifted_{shift_minutes}mins.csv")
    st.divider()
    
    dates_for_shift = ["ดูทั้งหมด (ตั้งแต่ต้นจนจบ)"] + sorted(df_display['Date'].unique().tolist())
    view_date = st.selectbox("📅 เลือกรูปแบบการเปรียบเทียบกราฟ", dates_for_shift, key="shift_date_selector")
    
    if view_date == "ดูทั้งหมด (ตั้งแต่ต้นจนจบ)":
        plot_old, plot_new = df_display.sort_values('Clock'), df_new_recalc.sort_values('Clock')
        title_text = "กราฟเส้นเปรียบเทียบข้อมูลเดิม เทียบกับ ข้อมูลใหม่ (ทั้งหมด)"
    else:
        plot_old = df_display[df_display['Date'] == view_date].sort_values('Clock')
        plot_new = df_new_recalc[df_new_recalc['Original_Clock'].dt.date == view_date].sort_values('Clock')
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
        summary_mode = st.radio("ระดับการสรุปผล:", ["ภาพรวมทั้งหมด (Total)", "รายเดือน (Monthly)", "รายวัน (Daily)"], horizontal=True, label_visibility="collapsed")
        
        if summary_mode == "รายวัน (Daily)":
            df_summary = df_display[df_display['Date'] == st.selectbox("📅 เลือกวัน:", sorted(df_display['Date'].unique()))]
        elif summary_mode == "รายเดือน (Monthly)":
            df_summary = df_display[df_display['Month'] == st.selectbox("📅 เลือกเดือน:", sorted(df_display['Month'].unique()))]
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

        st.markdown("##### 🧾 แยกค่าใช้จ่ายตามช่วงเวลา (TOU)")
        cost_summary = df_summary.groupby('Period_Detail')[['kW_Import', 'Cost_THB']].sum().reset_index()
        summary_dict = cost_summary.set_index('Period_Detail').to_dict('index')
        
        cc1, cc2, cc3 = st.columns(3)
        p_data = summary_dict.get('On-Peak', {'kW_Import': 0.0, 'Cost_THB': 0.0})
        cc1.error(f"**🔴 On-Peak** ({p_rate} บ.)\n\nพลังงาน: {p_data['kW_Import']:,.2f} kW\n\n**เป็นเงิน: ฿ {p_data['Cost_THB']:,.2f}**")
        
        op_data = summary_dict.get('Off-Peak', {'kW_Import': 0.0, 'Cost_THB': 0.0})
        cc2.success(f"**🟢 Off-Peak** ({op_rate} บ.)\n\nพลังงาน: {op_data['kW_Import']:,.2f} kW\n\n**เป็นเงิน: ฿ {op_data['Cost_THB']:,.2f}**")
        
        h_data = summary_dict.get('Holiday', {'kW_Import': 0.0, 'Cost_THB': 0.0})
        cc3.warning(f"**🟡 Holiday** ({op_rate} บ.)\n\nพลังงาน: {h_data['kW_Import']:,.2f} kW\n\n**เป็นเงิน: ฿ {h_data['Cost_THB']:,.2f}**")

    st.markdown("### 🔄 ระบบจำลองค่าไฟฟ้า (TOU Time-Shift Simulator)")
    with st.container(border=True):
        st.markdown("ทดลองเลื่อนรอบการทำงานของเครื่องจักร เพื่อเปรียบเทียบค่าไฟฟ้าและโหลดในแต่ละช่วงเวลา TOU")
        shift_mins_sim = st.number_input("⏱️ ใส่เวลาที่เลื่อน (นาที):", value=0, step=15, help="บวก = เลื่อนเวลาไปข้างหน้า, ลบ = ถอยหลัง")
            
        if shift_mins_sim != 0:
            df_sim = df_summary.copy()
            df_sim['Clock'] = df_sim['Clock'] + pd.to_timedelta(shift_mins_sim, unit='m')
            df_sim = apply_tou_and_anomaly(df_sim, sensitivity, p_start, p_end, p_rate, op_rate, holiday_list)
            
            new_cost = df_sim['Cost_THB'].sum()
            new_total_kw = df_sim['kW_Import'].sum()
            
            st.markdown(f"#### 📊 สถานะคาดการณ์ (หลังเลื่อน {shift_mins_sim} นาที)")
            
            c1_sim, c2_sim, c3_sim, c4_sim = st.columns(4)
            c1_sim.metric("พลังงานที่ใช้ทั้งหมด", f"{df_sim['kWh_15min'].sum():,.1f} kWh")
            c2_sim.metric("โหลดรวมทั้งหมด", f"{new_total_kw:,.1f} kW")
            c3_sim.metric("ค่าไฟฟ้าประเมินใหม่", f"฿ {new_cost:,.2f}")
            c4_sim.metric("จุดผิดปกติ (Anomaly)", f"{len(df_sim[df_sim['Anomaly_Type'] != 'ปกติ'])} จุด")
            
            st.markdown("##### 🧾 แยกค่าใช้จ่ายตามช่วงเวลา (เวลาจำลอง)")
            sim_cost_summary = df_sim.groupby('Period_Detail')[['kW_Import', 'Cost_THB']].sum().reset_index()
            sim_dict = sim_cost_summary.set_index('Period_Detail').to_dict('index')
            
            sc1, sc2, sc3 = st.columns(3)
            p_data_sim = sim_dict.get('On-Peak', {'kW_Import': 0.0, 'Cost_THB': 0.0})
            sc1.error(f"**🔴 On-Peak** ({p_rate} บ.)\n\nพลังงาน: {p_data_sim['kW_Import']:,.2f} kW\n\n**เป็นเงิน: ฿ {p_data_sim['Cost_THB']:,.2f}**")
            
            op_data_sim = sim_dict.get('Off-Peak', {'kW_Import': 0.0, 'Cost_THB': 0.0})
            sc2.success(f"**🟢 Off-Peak** ({op_rate} บ.)\n\nพลังงาน: {op_data_sim['kW_Import']:,.2f} kW\n\n**เป็นเงิน: ฿ {op_data_sim['Cost_THB']:,.2f}**")
            
            h_data_sim = sim_dict.get('Holiday', {'kW_Import': 0.0, 'Cost_THB': 0.0})
            sc3.warning(f"**🟡 Holiday** ({op_rate} บ.)\n\nพลังงาน: {h_data_sim['kW_Import']:,.2f} kW\n\n**เป็นเงิน: ฿ {h_data_sim['Cost_THB']:,.2f}**")
            
            st.write("📋 **ข้อมูลดิบหลังจำลอง**")
            st.dataframe(df_sim[['Clock', 'kW_Import', 'Period_Detail', 'Cost_THB']].reset_index(drop=True), use_container_width=True, height=200)
        else:
            st.info("รอการป้อนตัวเลขจำลองเวลา... (กรุณาใส่ตัวเลขที่ไม่ใช่ 0 ในช่องด้านบน)")