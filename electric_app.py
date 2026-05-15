import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

# ตั้งค่าหน้าเว็บ
st.set_page_config(page_title="โปรแกรมวิเคราะห์ข้อมูลไฟฟ้า", layout="wide")
st.title("📊 โปรแกรมวิเคราะห์ข้อมูลไฟฟ้า (ตรวจจับ Anomaly รวม)")

# ---------------------------------------------------------
# แถบด้านข้าง: ตั้งค่าการตรวจจับความผิดปกติ
# ---------------------------------------------------------
st.sidebar.header("🛠️ ตั้งค่าการตรวจจับความผิดปกติ")
sensitivity = st.sidebar.slider("ระดับความไว (Sensitivity)", 1.0, 5.0, 2.5, 0.5)
st.sidebar.info("ค่าน้อย = จับผิดละเอียด (เจอจุดแปลกๆ เยอะ)\nค่ามาก = จับผิดเฉพาะจุดที่โดดแบบวิกฤตจริงๆ")

# 1. ระบบ Upload ไฟล์
uploaded_file = st.file_uploader("เลือกไฟล์ข้อมูล (.csv, .xlsx, .xls)", type=['csv', 'xlsx', 'xls'])

if uploaded_file is not None:
    try:
        file_ext = uploaded_file.name.split('.')[-1].lower()
        
        with st.spinner('กำลังประมวลผลข้อมูล...'):
            # อ่านไฟล์
            if file_ext == 'csv':
                df_raw = pd.read_csv(uploaded_file, header=None)
            elif file_ext == 'xlsx':
                df_raw = pd.read_excel(uploaded_file, engine='openpyxl', header=None)
            else:
                df_raw = pd.read_excel(uploaded_file, engine='xlrd', header=None)
                
            # ค้นหาหัวตาราง
            header_row = 0
            for i in range(min(20, len(df_raw))):
                row_str = ' '.join(df_raw.iloc[i].fillna('').astype(str)).lower()
                if ('clock' in row_str) or ('ch1' in row_str and 'no' in row_str):
                    header_row = i
                    break
                    
            df_raw.columns = df_raw.iloc[header_row].astype(str).str.strip()
            df = df_raw.iloc[header_row + 1:].reset_index(drop=True).copy()

            # จัดระเบียบชื่อคอลัมน์
            if 'CH1' in df.columns:
                df.rename(columns={'CH1': 'Clock', 'CH3': 'Voltage', 'CH4': 'kW_Import'}, inplace=True)
            else:
                df.rename(columns={'L1 Voltage': 'Voltage', 'Total import kW demand': 'kW_Import'}, inplace=True)

            # ทำความสะอาดข้อมูล
            for col in ['Voltage', 'kW_Import']:
                if col in df.columns:
                    df[col] = df[col].astype(str).str.replace(' V', '', regex=False)\
                                                 .str.replace(' kW', '', regex=False)\
                                                 .str.replace(',', '', regex=False)
                    df[col] = pd.to_numeric(df[col], errors='coerce')

            df['Clock'] = pd.to_datetime(df['Clock'], dayfirst=True, errors='coerce')
            df = df.dropna(subset=['Clock', 'Voltage', 'kW_Import'])
            df['Date'] = df['Clock'].dt.date

            # สร้างตัวแปรใหม่
            df = df[df['Voltage'] > 0].copy()
            df['Calc_Metric'] = (df['kW_Import'] / df['Voltage']) * 1000

            def clean_data(data, col):
                Q1 = data[col].quantile(0.25)
                Q3 = data[col].quantile(0.75)
                IQR = Q3 - Q1
                return data[((data[col] >= Q1 - 1.5 * IQR) & (data[col] <= Q3 + 1.5 * IQR)) | (data[col] == 0)]

            df_clean = clean_data(df, 'Calc_Metric')
            df_clean = clean_data(df_clean, 'Voltage')

            # ---------------------------------------------------------
            # 🧠 ระบบตรวจสอบความผิดปกติรวม (Total Anomaly Detection)
            # ---------------------------------------------------------
            mean_kw = df_clean['kW_Import'].mean()
            std_kw = df_clean['kW_Import'].std()
            
            upper_limit = mean_kw + (sensitivity * std_kw)
            lower_limit = max(0, mean_kw - (sensitivity * std_kw))
            
            df_clean['Anomaly_Type'] = 'ปกติ'
            df_clean.loc[df_clean['kW_Import'] > upper_limit, 'Anomaly_Type'] = 'สูงเกินไป (High)'
            df_clean.loc[df_clean['kW_Import'] < lower_limit, 'Anomaly_Type'] = 'ต่ำเกินไป (Low)'
            
            all_anomalies = df_clean[df_clean['Anomaly_Type'] != 'ปกติ']

        # =========================================================
        # สร้าง Tabs สำหรับแสดงผล
        # =========================================================
        tab1, tab2 = st.tabs(["🌐 สรุปภาพรวมและจุดผิดปกติทั้งหมด", "📅 เจาะลึกข้อมูลรายวัน (15 นาที)"])

        # ------------------- TAB 1: ภาพรวมทั้งหมด -------------------
        with tab1:
            st.subheader("🚨 สรุปจุดผิดปกติจากข้อมูลทั้งหมด")
            
            if not all_anomalies.empty:
                st.error(f"⚠️ ตรวจพบจุดผิดปกติรวมทั้งหมด **{len(all_anomalies)}** รายการ จากข้อมูลทั้งหมด {len(df_clean)} รายการ")
                
                # กราฟไทม์ไลน์รวมทั้งหมด
                fig_all = go.Figure()
                fig_all.add_trace(go.Scatter(x=df_clean['Clock'], y=df_clean['kW_Import'], 
                                             name="การใช้ไฟปกติ", line=dict(color="#a8dadc", width=1)))
                
                high_all = all_anomalies[all_anomalies['Anomaly_Type'] == 'สูงเกินไป (High)']
                if not high_all.empty:
                    fig_all.add_trace(go.Scatter(x=high_all['Clock'], y=high_all['kW_Import'], 
                                                 mode='markers', name='สูงผิดปกติ', marker=dict(color='red', size=6)))
                    
                low_all = all_anomalies[all_anomalies['Anomaly_Type'] == 'ต่ำเกินไป (Low)']
                if not low_all.empty:
                    fig_all.add_trace(go.Scatter(x=low_all['Clock'], y=low_all['kW_Import'], 
                                                 mode='markers', name='ต่ำผิดปกติ', marker=dict(color='orange', size=6)))

                fig_all.update_layout(title="กราฟแสดงการใช้ไฟฟ้ารวมทั้งหมด (จุดสี = ผิดปกติ)", 
                                      height=500, template="plotly_white", hovermode="x unified")
                st.plotly_chart(fig_all, use_container_width=True)

                # ตารางรวมจุดผิดปกติทั้งหมด
                st.write("📋 **ตารางรวมช่วงเวลาที่เกิดความผิดปกติ**")
                st.dataframe(all_anomalies[['Clock', 'kW_Import', 'Voltage', 'Anomaly_Type']].reset_index(drop=True), use_container_width=True)
            else:
                st.success("✅ เยี่ยมมาก! ไม่พบจุดผิดปกติในการใช้ไฟฟ้าจากข้อมูลทั้งหมดเลย")

            st.divider()
            
            # กราฟภาพรวมรายวัน (Daily Statistics)
            st.subheader("📈 สถิติเฉลี่ยรายวัน")
            daily = df_clean.groupby('Date').agg({
                'Calc_Metric': ['mean', 'min', 'max'],
                'kW_Import': ['mean', 'min', 'max'],
                'Voltage': ['mean', 'min', 'max']
            })
            daily.columns = ['M_Avg', 'M_Min', 'M_Max', 'kW_Avg', 'kW_Min', 'kW_Max', 'V_Avg', 'V_Min', 'V_Max']
            daily = daily.reset_index()

            fig_daily = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.1,
                                    subplot_titles=("พลังงานรวม (kW)", "แรงดันไฟฟ้า (V)"))

            def add_daily_plot(fig, x, avg, v_min, v_max, row, name, color):
                fig.add_trace(go.Scatter(x=x, y=v_max, mode='lines', line=dict(width=0), name='Max', showlegend=False), row=row, col=1)
                fig.add_trace(go.Scatter(x=x, y=v_min, mode='lines', line=dict(width=0), fill='tonexty', fillcolor=f'rgba{color}0.2)', name='Min', showlegend=False), row=row, col=1)
                fig.add_trace(go.Scatter(x=x, y=avg, mode='lines+markers', name=name, line=dict(color=f'rgb{color}1)')), row=row, col=1)

            add_daily_plot(fig_daily, daily['Date'], daily['kW_Avg'], daily['kW_Min'], daily['kW_Max'], 1, "เฉลี่ย kW", "(244, 162, 97,")
            add_daily_plot(fig_daily, daily['Date'], daily['V_Avg'], daily['V_Min'], daily['V_Max'], 2, "เฉลี่ย Volt", "(230, 57, 70,")
            
            fig_daily.update_layout(height=600, template="plotly_white", hovermode="x unified")
            st.plotly_chart(fig_daily, use_container_width=True)

        # ------------------- TAB 2: เจาะลึกรายวัน -------------------
        with tab2:
            st.sidebar.divider()
            st.sidebar.header("📅 เลือกวันที่ (สำหรับ Tab 2)")
            available_dates = sorted(df_clean['Date'].unique())
            selected_date = st.sidebar.selectbox("เลือกวันที่ต้องการดูแบบละเอียด", available_dates)

            st.subheader(f"⏱️ ข้อมูลละเอียดราย 15 นาที: วันที่ {selected_date}")
            
            day_df = df_clean[df_clean['Date'] == selected_date].sort_values('Clock')

            fig_15min = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.1,
                                      subplot_titles=("ความต้องการพลังงาน (kW)", "แรงดันไฟฟ้า (V)"))

            # กราฟ kW
            fig_15min.add_trace(go.Scatter(x=day_df['Clock'], y=day_df['kW_Import'], 
                                         name="kW Import", line=dict(color="#f4a261", width=2), fill='tozeroy'), row=1, col=1)
            
            high_anom_day = day_df[day_df['Anomaly_Type'] == 'สูงเกินไป (High)']
            if not high_anom_day.empty:
                fig_15min.add_trace(go.Scatter(x=high_anom_day['Clock'], y=high_anom_day['kW_Import'], 
                                             mode='markers', name='สูงผิดปกติ', marker=dict(color='red', size=8)), row=1, col=1)

            low_anom_day = day_df[day_df['Anomaly_Type'] == 'ต่ำเกินไป (Low)']
            if not low_anom_day.empty:
                fig_15min.add_trace(go.Scatter(x=low_anom_day['Clock'], y=low_anom_day['kW_Import'], 
                                             mode='markers', name='ต่ำผิดปกติ', marker=dict(color='orange', size=8)), row=1, col=1)

            # กราฟ Voltage
            fig_15min.add_trace(go.Scatter(x=day_df['Clock'], y=day_df['Voltage'], 
                                         name="Voltage (V)", line=dict(color="#e63946", width=2)), row=2, col=1)

            fig_15min.update_layout(height=600, template="plotly_white", hovermode="x unified")
            st.plotly_chart(fig_15min, use_container_width=True)

            with st.expander("📋 ดูตารางข้อมูลของวันที่เลือก"):
                st.dataframe(day_df[['Clock', 'Voltage', 'kW_Import', 'Calc_Metric', 'Anomaly_Type']].reset_index(drop=True), use_container_width=True)

    except Exception as e:
        st.error(f"❌ เกิดข้อผิดพลาดในการประมวลผลไฟล์: {e}")
        st.info("โปรดตรวจสอบความถูกต้องของไฟล์ Excel หรือ CSV ของคุณอีกครั้ง")
else:
    st.info("💡 โปรดอัปโหลดไฟล์ Excel หรือ CSV เพื่อเริ่มต้น")