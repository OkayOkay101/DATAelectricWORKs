import pandas as pd

def apply_tou_and_anomaly(df, sensitivity, p_start, p_end, p_rate, op_rate, holiday_list):
    """วิเคราะห์สถานะ TOU (Peak, Off-Peak, Holiday) และตรวจสอบไฟตกไฟเกินตามเงื่อนไขใหม่"""
    df = df.copy()
    
    df['Is_Weekend'] = df['Clock'].dt.weekday >= 5
    df['Date_Str'] = df['Clock'].dt.strftime('%Y-%m-%d')
    df['Is_Holiday'] = df['Date_Str'].isin(holiday_list)
    
    curr_time = df['Clock'].dt.time
    if p_start < p_end:
        is_peak_time = (curr_time >= p_start) & (curr_time < p_end)
    else:
        is_peak_time = (curr_time >= p_start) | (curr_time < p_end)
    
    # ⚡ เงื่อนไขใหม่: เริ่มต้นให้เป็น Off-Peak ทั้งหมด
    df['Period_Detail'] = 'Off-Peak'
    df['Rate_THB'] = op_rate
    
    # เงื่อนไขที่ 1: ถ้าเป็นช่วงเวลา On-Peak และเป็นวันจันทร์-ศุกร์ (ไม่ใช่วันหยุดนักขัตฤกษ์) -> ให้เป็น On-Peak
    peak_condition = is_peak_time & (~df['Is_Weekend']) & (~df['Is_Holiday'])
    df.loc[peak_condition, 'Period_Detail'] = 'On-Peak'
    df.loc[peak_condition, 'Rate_THB'] = p_rate
    
    # เงื่อนไขที่ 2: ถ้าเป็นวันเสาร์-อาทิตย์ หรือเป็นวันหยุดต่างๆ -> ให้เป็น Holiday ตลอด 24 ชั่วโมง (00:00 - 24:00)
    holiday_condition = df['Is_Weekend'] | df['Is_Holiday']
    df.loc[holiday_condition, 'Period_Detail'] = 'Holiday'
    df.loc[holiday_condition, 'Rate_THB'] = op_rate  # ใช้เรทเดียวกับ Off-Peak ตามมาตรฐาน
    
    df['Cost_THB'] = df['kWh_15min'] * df['Rate_THB']

    # ตรวจจับ Anomaly (ความผิดปกติ)
    active = df[df['kW_Import'] > 0.05]
    df['Anomaly_Type'] = 'ปกติ'
    if not active.empty:
        mean_v, std_v = active['kW_Import'].mean(), active['kW_Import'].std()
        upper = mean_v + (sensitivity * std_v)
        lower = max(0.01, mean_v - (sensitivity * std_v))
        df.loc[(df['kW_Import'] > upper) & (df['kW_Import'] > 0), 'Anomaly_Type'] = 'สูงกว่าเกณฑ์ (High)'
        df.loc[(df['kW_Import'] < lower) & (df['kW_Import'] > 0), 'Anomaly_Type'] = 'ไฟตก (Low)'
    
    return df

def get_color(period):
    """จับคู่สีสำหรับสร้างกราฟ UI"""
    if 'Holiday' in period: return '#ffd166' # สีเหลือง
    elif 'On-Peak' in period: return '#e76f51' # สีส้ม
    else: return '#2a9d8f' # สีเขียว (Off-Peak)