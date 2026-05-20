import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st
import datetime

# --- นำเข้า (Import) โมดูลที่เราแยกไว้ ---
from data_handler import load_file, preprocess_data, get_usage_snapshots
from tou_analyzer import apply_tou_and_anomaly, get_color

st.set_page_config(page_title="Load Profile & TOU Simulator (ระบบวิเคราะห์โหลดและจำลองค่าไฟ TOU)", page_icon="⚡", layout="wide")

# ปรับแต่ง CSS เล็กน้อยเพื่อซ่อนเมนูที่ไม่จำเป็นและทำให้ UI คลีนขึ้น
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
    st.header("🛠️ ตั้งค่า TOU & วันหยุด")

    with st.sidebar.expander("ตั้งค่าราคา (บาท/หน่วย)", expanded=True):
        p_rate = st.number_input("เรท On-Peak", value=5.7982, format="%.4f")
        op_rate = st.number_input("เรท Off-Peak / Holiday", value=2.6369, format="%.4f")

    with st.sidebar.expander("ตั้งค่าเวลา On-Peak", expanded=True):
        p_start = st.time_input("เริ่ม On-Peak", value=datetime.time(9, 0))
        p_end = st.time_input("สิ้นสุด On-Peak", value=datetime.time(22, 0))

    with st.sidebar.expander("ตั้งค่าวันหยุด (Holiday)", expanded=True):
        st.caption("พิมพ์วันที่ (YYYY-MM-DD) คั่นด้วยลูกน้ำ(,)")
        default_holidays = "2026-01-01, 2026-03-02, 2026-04-06, 2026-04-13, 2026-04-14, 2026-04-15, 2026-05-01, 2026-05-04, 2026-06-03, 2026-07-28, 2026-07-29, 2026-07-30, 2026-08-12, 2026-10-13, 2026-10-23, 2026-12-10, 2026-12-31"
        holiday_input = st.text_area("รายการวันหยุด:", value=default_holidays, height=150)
        holiday_list = [x.strip() for x in holiday_input.replace('\n', ',').split(',') if x.strip()]

    st.sidebar.divider()
    st.sidebar.header("⚙️ การแสดงผลและวิเคราะห์")
    sensitivity = st.sidebar.slider("ระดับความไว Anomaly", 1.0, 5.0, 2.5, 0.5)
    chart_type = st.sidebar.radio("เลือกรูปแบบกราฟ:", ["กราฟแท่ง (Bar)", "กราฟเส้น (Line)"])
    is_bar = "แท่ง" in chart_type

    st.sidebar.divider()
    uploaded_files = st.sidebar.file_uploader("📂 อัปโหลดไฟล์ข้อมูล (เลือกได้หลายไฟล์)", type=['csv', 'xlsx', 'xls', 'txt'], accept_multiple_files=True)

if uploaded_files:
    with st.spinner('กำลังโหลด ประมวลผล และเชื่อมต่อข้อมูลจากทุกไฟล์...'):
        all_dfs = []
        for file in uploaded_files:
            file_ext = file.name.split('.')[-1].lower()
            try:
                df_raw = load_file(file, file_ext)
                df_base = preprocess_data(df_raw)
                
                if not df_base.empty and 'Clock' in df_base.columns:
                    all_dfs.append(df_base)
                else:
                    st.sidebar.warning(f"⚠️ ข้ามไฟล์ '{file.name}' (หาคอลัมน์เวลาไม่พบ หรือเป็นไฟล์เปล่า)")
                    
            except Exception as e:
                st.sidebar.error(f"❌ อ่านไฟล์ '{file.name}' ไม่ได้: {e}")

        if all_dfs:
            df_combined = pd.concat(all_dfs, ignore_index=True)
            
            if 'Clock' in df_combined.columns:
                df_combined = df_combined.sort_values(['Clock', 'kW_Import'], ascending=[True, False]).drop_duplicates(subset=['Clock'], keep='first').reset_index(drop=True)
                df_combined = df_combined.sort_values('Clock').reset_index(drop=True)
                df_combined['Cumulative_kWh_Total'] = df_combined['kWh_15min'].cumsum()
                
                df_master = apply_tou_and_anomaly(df_combined, sensitivity, p_start, p_end, p_rate, op_rate, holiday_list)
                snapshots = get_usage_snapshots(df_master)
                
                st.sidebar.success(f"✅ รวมและประมวลผลสำเร็จ {len(all_dfs)} ไฟล์")
                
                st.sidebar.divider()
                st.sidebar.header("🔍 ระบบ Snapshot (กรองช่วงเวลา)")
                snapshot_options = ["🌐 ดูข้อมูลทั้งหมด (All Data)"] + [s['label'] for s in snapshots]
                selected_snapshot = st.sidebar.selectbox("เลือกรอบการเดินเครื่อง:", snapshot_options)

                if selected_snapshot == "🌐 ดูข้อมูลทั้งหมด (All Data)":
                    df_display = df_master.copy()
                else:
                    sel_s = next(s for s in snapshots if s['label'] == selected_snapshot)
                    df_display = df_master.iloc[sel_s['start_idx'] : sel_s['end_idx'] + 1].copy()

                # ==========================================
                # 📑 สร้าง Tabs แสดงผล
                # ==========================================
                tab1, tab2, tab3, tab4 = st.tabs(["🌐 ภาพรวมทั้งหมด", "📅 เจาะลึกรายวัน", "🔄 จำลองเลื่อนเวลา", "📋 สรุปข้อมูล และ ค่าไฟฟ้า"])

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
                        if not high_all.empty:
                            fig_all.add_trace(go.Scatter(x=high_all['Clock'], y=high_all['kW_Import'], mode='markers', name='สูงกว่าเกณฑ์', marker=dict(color='red', size=8)))
                        low_all = all_anomalies[all_anomalies['Anomaly_Type'] == 'ไฟตก (Low)']
                        if not low_all.empty:
                            fig_all.add_trace(go.Scatter(x=low_all['Clock'], y=low_all['kW_Import'], mode='markers', name='ไฟตก', marker=dict(color='blue', size=8)))

                    fig_all.update_layout(height=400, template="plotly_white", hovermode="x unified")
                    st.plotly_chart(fig_all, use_container_width=True)
                    if is_bar: st.info("💡 สีส้ม = On-Peak | สีเขียว = Off-Peak (กลางคืน/เสาร์-อาทิตย์) | สีเหลือง = Holiday (วันหยุดราชการ)")
                    
                    # 🔥 แก้ไขจุดที่ 1: เปลี่ยนจากพลังงานสะสม เป็น ความต้องการพลังงานไฟฟ้า (kW) แบบไม่สะสม
                    st.subheader("ความต้องการพลังงานไฟฟ้า (kW) แบบไม่สะสม")
                    fig_kw_each = go.Figure()
                    fig_kw_each.add_trace(go.Bar(x=df_display['Clock'], y=df_display['kW_Import'], marker_color="#457b9d", name="kW"))
                    fig_kw_each.update_layout(height=350, template="plotly_white", hovermode="x unified")
                    st.plotly_chart(fig_kw_each, use_container_width=True)

                with tab2:
                    available_dates = sorted(df_display['Date'].unique())
                    if available_dates:
                        sel_date = st.selectbox("📅 เลือกวันที่ต้องการเจาะลึก", available_dates)
                        day_df = df_display[df_display['Date'] == sel_date].copy()

                        st.markdown(f"#### 📊 สรุปสัดส่วนการใช้พลังงานประจำวันที่ {sel_date}")
                        
                        # 🔥 แก้ไขจุดที่ 2: เพิ่มกล่อง Metric โชว์โหลดรวม (Sum kW) เคียงคู่ไปกับตัวอื่น
                        m_col1, m_col2, m_col3 = st.columns(3)
                        m_col1.metric("โหลดรวมประจำวัน (Sum kW)", f"{day_df['kW_Import'].sum():,.2f} kW")
                        m_col2.metric("พลังงานรวมประจำวัน (Total kWh)", f"{day_df['kWh_15min'].sum():,.2f} kWh")
                        m_col3.metric("ค่าไฟฟ้าประจำวัน", f"฿ {day_df['Cost_THB'].sum():,.2f}")
                        
                        st.write("")
                        # เพิ่มคอลัมน์แสดงผลในตารางกลุ่มสัดส่วนให้มีครบทั้ง kW และ kWh
                        summary_daily = day_df.groupby('Period_Detail')[['kW_Import', 'kWh_15min', 'Cost_THB']].sum().reset_index()
                        summary_daily.columns = ['สถานะ (Period)', 'โหลดรวม (kW)', 'พลังงานรวม (kWh)', 'ค่าไฟฟ้า (บาท)']
                        st.dataframe(summary_daily, use_container_width=True, hide_index=True)

                        # 🔥 แก้ไขจุดที่ 3: ปรับ Subplot แถวที่ 2 จากพลังงานสะสมรายวัน เป็น พลังงานราย 15 นาที (kWh) แบบไม่สะสม
                        fig_15min = make_subplots(rows=4, cols=1, shared_xaxes=True, vertical_spacing=0.05, 
                                                  subplot_titles=("พลังงาน (kW)", "พลังงานราย 15 นาที (kWh) *ไม่สะสม", "แรงดันไฟฟ้า (V)", "ประมาณการค่าไฟฟ้าราย 15 นาที (THB)"))
                        
                        day_colors = day_df['Period_Detail'].apply(get_color)
                        if is_bar:
                            fig_15min.add_trace(go.Bar(x=day_df['Clock'], y=day_df['kW_Import'], marker_color=day_colors, name="kW"), row=1, col=1)
                        else:
                            fig_15min.add_trace(go.Scatter(x=day_df['Clock'], y=day_df['kW_Import'], mode='lines', fill='tozeroy', line=dict(color="#f4a261", width=2), name="kW"), row=1, col=1)
                            
                        # ใช้ day_df['kWh_15min'] ตรงๆ ไม่ใช้ .cumsum() เพื่อให้ไม่สะสม
                        fig_15min.add_trace(go.Bar(x=day_df['Clock'], y=day_df['kWh_15min'], marker_color="#2a9d8f", name="kWh"), row=2, col=1)
                        fig_15min.add_trace(go.Bar(x=day_df['Clock'], y=day_df['Voltage'], marker_color="#e63946", name="Volt"), row=3, col=1)
                        fig_15min.add_trace(go.Bar(x=day_df['Clock'], y=day_df['Cost_THB'], marker_color="#8338ec", name="THB"), row=4, col=1)
                        
                        fig_15min.update_layout(height=900, template="plotly_white", hovermode="x unified", showlegend=False)
                        st.plotly_chart(fig_15min, use_container_width=True)

                        # 🔥 เพิ่มตารางข้อมูลดิบประจำวันที่มีทั้งหน่วย kW และ kWh ครบถ้วน
                        st.markdown(f"#### 📋 ตารางข้อมูลดิบประจำวันที่ {sel_date}")
                        st.dataframe(day_df[['Clock', 'kW_Import', 'kWh_15min', 'Voltage', 'Period_Detail', 'Rate_THB', 'Cost_THB', 'Anomaly_Type']].reset_index(drop=True), use_container_width=True)

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
                        plot_old = df_display.sort_values('Clock')
                        plot_new = df_new_recalc.sort_values('Clock')
                        title_text = "กราฟเส้นเปรียบเทียบข้อมูลเดิม เทียบกับ ข้อมูลใหม่ (ทั้งหมด)"
                    else:
                        plot_old = df_display[df_display['Date'] == view_date].sort_values('Clock')
                        plot_new = df_new_recalc[df_new_recalc['Original_Clock'].dt.date == view_date].sort_values('Clock')
                        title_text = f"กราฟเส้นเปรียบเทียบข้อมูลเดิม เทียบกับ ข้อมูลใหม่ ประจำวันที่ {view_date}"
                    
                    fig_compare = go.Figure()
                    fig_compare.add_trace(go.Scatter(x=plot_old['Clock'], y=plot_old['kW_Import'], mode='lines+markers', name='เก่า (Original)', line=dict(color='#1d3557', width=3)))
                    fig_compare.add_trace(go.Scatter(x=plot_new['Clock'], y=plot_new['kW_Import'], mode='lines+markers', name=f'ใหม่ (Shifted {shift_minutes} นาที)', line=dict(color='#e63946', width=2.5, dash='dash')))
                    fig_compare.update_layout(title=title_text, height=450, template="plotly_white", hovermode="x unified")
                    st.plotly_chart(fig_compare, use_container_width=True)

                with tab4:
                    st.subheader("📊 สรุปข้อมูลพลังงานและการแจ้งเตือน")
                    summary_mode = st.radio("เลือกรูปแบบการดูสรุปผล:", ["ภาพรวมทั้งหมด", "ดูเป็นรายเดือน", "ดูเป็นรายวัน"], horizontal=True)
                    
                    if summary_mode == "ดูเป็นรายวัน":
                        avail_dates = sorted(df_display['Date'].unique())
                        sel_sum_date = st.selectbox("📅 เลือกวันที่ต้องการดูสรุป", avail_dates, key="summary_date")
                        df_summary = df_display[df_display['Date'] == sel_sum_date]
                        st.markdown(f"#### สรุปข้อมูลประจำวันที่ {sel_sum_date}")
                    elif summary_mode == "ดูเป็นรายเดือน":
                        avail_months = sorted(df_display['Month'].unique())
                        sel_sum_month = st.selectbox("📅 เลือกเดือนที่ต้องการดูสรุป (รูปแบบ YYYY-MM)", avail_months, key="summary_month")
                        df_summary = df_display[df_display['Month'] == sel_sum_month]
                        st.markdown(f"#### สรุปข้อมูลประจำเดือน {sel_sum_month}")
                    else:
                        df_summary = df_display
                        st.markdown("#### สรุปข้อมูลภาพรวมทั้งหมด")

                    kpi1, kpi2, kpi3 = st.columns(3)
                    kpi1.metric("พลังงานรวม (Total kWh)", f"{df_summary['kWh_15min'].sum():,.2f}")
                    kpi2.metric("ความต้องการไฟฟ้าสูงสุด (Peak kW)", f"{df_summary['kW_Import'].max():,.2f}")
                    kpi3.metric("จุดผิดปกติ (Anomalies)", f"{len(df_summary[df_summary['Anomaly_Type'] != 'ปกติ'])}")

                    st.divider()
                    st.subheader("💰 สรุปประมาณการค่าไฟฟ้า (แยกตามเงื่อนไข On-Peak, Off-Peak, Holiday)")
                    
                    cost_summary = df_summary.groupby('Period_Detail')[['kW_Import', 'Cost_THB']].sum().reset_index()
                    orig_cost = df_summary['Cost_THB'].sum()
                    
                    col1, col2 = st.columns([1.5, 2])
                    with col1:
                        st.markdown(f"#### 🏷️ รวมค่าไฟเบื้องต้น: {orig_cost:,.2f} บาท")
                        st.markdown(f"#### ⚡ พลังงานรวมทั้งหมด: {df_summary['kW_Import'].sum():,.2f} kW")
                        
                        summary_dict = cost_summary.set_index('Period_Detail').to_dict('index')
                        
                        p_data = summary_dict.get('On-Peak', {'kW_Import': 0.0, 'Cost_THB': 0.0})
                        st.info(f"**🔴 On-Peak (เรท {p_rate} บ.)**\n- พลังงานรวม: {p_data['kW_Import']:,.2f} kW\n- เป็นเงิน: {p_data['Cost_THB']:,.2f} บาท")
                        
                        op_data = summary_dict.get('Off-Peak', {'kW_Import': 0.0, 'Cost_THB': 0.0})
                        st.success(f"**🟢 Off-Peak (เรท {op_rate} บ.)**\n- พลังงานรวม: {op_data['kW_Import']:,.2f} kW\n- เป็นเงิน: {op_data['Cost_THB']:,.2f} บาท")
                        
                        h_data = summary_dict.get('Holiday', {'kW_Import': 0.0, 'Cost_THB': 0.0})
                        st.warning(f"**🟡 Holiday (เรท {op_rate} บ.)**\n- พลังงานรวม: {h_data['kW_Import']:,.2f} kW\n- เป็นเงิน: {h_data['Cost_THB']:,.2f} บาท")

                    with col2:
                        st.write("📋 **ตารางข้อมูลดิบ (ปัจจุบัน)**")
                        st.dataframe(df_summary[['Clock', 'kW_Import', 'Voltage', 'kWh_15min', 'Period_Detail', 'Rate_THB', 'Cost_THB', 'Anomaly_Type']].reset_index(drop=True), use_container_width=True)

                    # --- ส่วนจำลองเลื่อนเวลาในหน้าสรุป ---
                    st.divider()
                    st.subheader("🔄 จำลองเลื่อนเวลาทำงานเพื่อเปรียบเทียบค่าไฟ")
                    st.info("💡 ลองใส่จำนวนนาทีเพื่อดูว่าถ้าเลื่อนการทำงานทั้งหมด ค่าไฟจะประหยัดขึ้นหรือแพงขึ้นเท่าไหร่ (ค่าบวก=เลื่อนไปข้างหน้า, ค่าลบ=ถอยหลัง)")
                    
                    shift_mins_sim = st.number_input("⏱️ จำนวนนาทีที่ต้องการเลื่อน (จำลองค่าไฟ):", value=0, step=15)
                    
                    if shift_mins_sim != 0:
                        df_sim = df_summary.copy()
                        df_sim['Clock'] = df_sim['Clock'] + pd.to_timedelta(shift_mins_sim, unit='m')
                        
                        df_sim = apply_tou_and_anomaly(df_sim, sensitivity, p_start, p_end, p_rate, op_rate, holiday_list)
                        
                        new_cost = df_sim['Cost_THB'].sum()
                        diff = orig_cost - new_cost
                        
                        sim_col1, sim_col2 = st.columns([1.5, 2])
                        with sim_col1:
                            st.markdown(f"#### 🏷️ รวมค่าไฟใหม่ (หลังเลื่อน {shift_mins_sim} นาที): {new_cost:,.2f} บาท")
                            st.markdown(f"#### ⚡ พลังงานรวมใหม่ทั้งหมด: {df_sim['kW_Import'].sum():,.2f} kW")
                            
                            if diff > 0:
                                st.success(f"🎉 **ประหยัดเงินได้: {diff:,.2f} บาท**")
                            elif diff < 0:
                                st.error(f"⚠️ **เสียเงินเพิ่ม: {abs(diff):,.2f} บาท**")
                            else:
                                st.info("⚖️ **ค่าไฟเท่าเดิม ไม่เปลี่ยนแปลง**")
                            
                            sim_cost_summary = df_sim.groupby('Period_Detail')[['kW_Import', 'Cost_THB']].sum().reset_index()
                            sim_dict = sim_cost_summary.set_index('Period_Detail').to_dict('index')
                            
                            p_data_sim = sim_dict.get('On-Peak', {'kW_Import': 0.0, 'Cost_THB': 0.0})
                            st.info(f"**🔴 On-Peak (เรท {p_rate} บ.)**\n- พลังงานรวม: {p_data_sim['kW_Import']:,.2f} kW\n- เป็นเงิน: {p_data_sim['Cost_THB']:,.2f} บาท")
                            
                            op_data_sim = sim_dict.get('Off-Peak', {'kW_Import': 0.0, 'Cost_THB': 0.0})
                            st.success(f"**🟢 Off-Peak (เรท {op_rate} บ.)**\n- พลังงานรวม: {op_data_sim['kW_Import']:,.2f} kW\n- เป็นเงิน: {op_data_sim['Cost_THB']:,.2f} บาท")
                            
                            h_data_sim = sim_dict.get('Holiday', {'kW_Import': 0.0, 'Cost_THB': 0.0})
                            st.warning(f"**🟡 Holiday (เรท {op_rate} บ.)**\n- พลังงานรวม: {h_data_sim['kW_Import']:,.2f} kW\n- เป็นเงิน: {h_data_sim['Cost_THB']:,.2f} บาท")
                                    
                        with sim_col2:
                            st.write("📋 **ตารางข้อมูลดิบ (เวลาใหม่ที่จำลอง)**")
                            st.dataframe(df_sim[['Clock', 'kW_Import', 'Voltage', 'kWh_15min', 'Period_Detail', 'Rate_THB', 'Cost_THB', 'Anomaly_Type']].reset_index(drop=True), use_container_width=True)

            else:
                st.error("❌ ไม่พบคอลัมน์เวลา (Clock) ในไฟล์ทั้งหมดที่รวมกัน โปรดตรวจสอบข้อมูลภายในไฟล์อีกครั้ง")
        else:
            st.error("⚠️ ไม่มีข้อมูลที่สามารถนำมาวิเคราะห์ได้เลย โปรดตรวจสอบไฟล์ที่อัปโหลด (อาจเป็นไฟล์ว่าง หรืออ่านหัวตารางไม่พบ)")

else:
    st.info("💡 โปรดอัปโหลดไฟล์ (สามารถลากคลุมเพื่ออัปโหลดหลายไฟล์พร้อมกันได้)")