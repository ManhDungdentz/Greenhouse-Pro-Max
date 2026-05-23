import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import timedelta
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# --- CẤU HÌNH TRANG ---
st.set_page_config(page_title="Greenhouse Pro Max", layout="wide")
st.title("🌿 Hệ Thống Giám Sát Nhà Kính (Xử Lý Đứt Cáp)")

# --- HÀM GỬI EMAIL ---
def send_email_alert(sender_mail, app_password, receiver_mail, vpd, status, temp, humi):
    if vpd > 1.5:
        ly_do, tinh_trang = "Nóng và khô quá mức.", "Cây cháy lá, héo rũ."
        cach_xu_ly = "Bật phun sương, kéo rèm che nắng ngay."
    elif vpd < 0.4:
        ly_do, tinh_trang = "Độ ẩm quá cao.", "Nguy cơ thối rễ, nấm bệnh."
        cach_xu_ly = "Bật quạt thông gió, ngừng tưới."
    else:
        ly_do, tinh_trang, cach_xu_ly = "Lệch ngưỡng.", "Cây stress nhẹ.", "Kiểm tra lại thiết bị."

    try:
        msg = MIMEMultipart()
        msg['Subject'] = f"🚨 CẢNH BÁO VPD: {status}"
        body = f"📍 TRẠNG THÁI: {status}\nVPD: {vpd} kPa\nNhiệt độ: {temp}°C\nĐộ ẩm: {humi}%\n\nLý do: {ly_do}\nTình trạng: {tinh_trang}\nXử lý: {cach_xu_ly}"
        msg.attach(MIMEText(body, 'plain', 'utf-8'))
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(sender_mail, app_password)
        server.sendmail(sender_mail, receiver_mail, msg.as_string())
        server.quit()
        return True
    except: return False

# --- TÍNH VPD ---
def calculate_vpd(temp, humi):
    if pd.isna(temp) or pd.isna(humi): return None
    vpsat = 0.61078 * np.exp((17.27 * temp) / (temp + 237.3))
    vpair = vpsat * (humi / 100)
    return round(vpsat - vpair, 2)

def get_greenhouse_advice(vpd, stage):
    if pd.isna(vpd): return "N/A", "Chờ dữ liệu...", "#808080"
    if "Cây con" in stage: i_min, i_max = 0.4, 0.8
    elif "Sinh trưởng" in stage: i_min, i_max = 0.8, 1.2
    else: i_min, i_max = 1.2, 1.5
    
    if vpd < i_min - 0.2: return "🔴 QUÁ THẤP", "Nguy cơ nấm bệnh!", "#FF4B4B"
    if i_min <= vpd <= i_max: return "🟢 LÝ TƯỞNG", "Cây phát triển tốt.", "#00C851"
    if vpd > i_max + 0.3: return "🔴 QUÁ CAO", "Stress nhiệt nặng!", "#8B0000"
    return "🟡 HƠI LỆCH", "Cần điều chỉnh nhẹ thiết bị.", "#FFA500"

# --- XỬ LÝ DỮ LIỆU ---
def process_data(file):
    try:
        df = pd.read_json(file)
    except: return pd.DataFrame()
    
    if 'Thời gian' in df.columns:
        df['Thời gian'] = pd.to_datetime(df['Thời gian'].astype(str).str.replace('-', ' ', n=2).str.replace('-', ':'), errors='coerce', utc=True).dt.tz_localize(None)
        df = df.dropna(subset=['Thời gian']).sort_values('Thời gian')
    
    t_cols = [c for c in ['Nhiệt Độ', 'tempKK'] if c in df.columns]
    if t_cols: df['temp'] = df[t_cols].bfill(axis=1).iloc[:, 0]
    h_cols = [c for c in ['Độ ẩm', 'humiKK'] if c in df.columns]
    if h_cols: df['humi'] = df[h_cols].bfill(axis=1).iloc[:, 0]
    
    for col in ['temp', 'humi']:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col].astype(str).str.extract(r'(\d+\.?\d*)')[0], errors='coerce')
            
            if col == 'temp':
                df.loc[df[col] > 150, col] = df[col] / 10 
                df.loc[(df[col] >= 45) & (df[col] <= 120), col] = (df[col] - 32) * 5/9 
    
    df = df.dropna(subset=['temp', 'humi']).copy()
    
    # 1. BỘ LỌC TRUNG VỊ ĐỂ CHỐNG GAI NHIỄU (như đã hứa)
    if len(df) > 11:
        df['temp'] = df['temp'].rolling(window=11, center=True, min_periods=1).median()
        df['humi'] = df['humi'].rolling(window=11, center=True, min_periods=1).median()
        
    if not df.empty: 
        df['VPD'] = df.apply(lambda r: calculate_vpd(r['temp'], r['humi']), axis=1)
        
        # --- 2. CẮT ĐỨT ĐƯỜNG VẼ NẾU MẤT KẾT NỐI > 1 PHÚT ---
        # Tìm những chỗ thời gian bị hổng
        time_diffs = df['Thời gian'].diff()
        gap_indices = df[time_diffs > pd.Timedelta(minutes=1)].index
        
        # Nhét giá trị rỗng (NaN) vào chỗ hổng để Plotly tự động ngắt nét vẽ
        if len(gap_indices) > 0:
            nan_rows = pd.DataFrame([{'Thời gian': df.loc[i, 'Thời gian'] - pd.Timedelta(seconds=1)} for i in gap_indices])
            df = pd.concat([df, nan_rows]).sort_values('Thời gian').reset_index(drop=True)

    return df

# --- THANH BÊN (SIDEBAR) ---
with st.sidebar:
    st.header("⚙️ Cấu hình")
    u_mail = st.text_input("Gmail gửi:")
    u_pass = st.text_input("Mật khẩu ứng dụng:", type="password")
    t_mail = st.text_input("Gmail nhận:")
    st.divider()
    uploaded_file = st.file_uploader("Tải file JSON", type=['json'])

if uploaded_file:
    df = process_data(uploaded_file)
    if not df.empty:
        st.sidebar.header("🔍 Lọc dữ liệu")
        df['Tháng'] = df['Thời gian'].dt.strftime('%m/%Y')
        filter_mode = st.sidebar.radio("Chế độ lọc:", ["Tất cả", "Tháng", "Khoảng ngày"])
        
        if filter_mode == "Tháng":
            sel_m = st.sidebar.multiselect("Chọn tháng:", df['Tháng'].unique(), default=df['Tháng'].unique()[-1:])
            df_work = df[df['Tháng'].isin(sel_m)].copy()
        elif filter_mode == "Khoảng ngày":
            c1, c2 = st.sidebar.columns(2)
            start = pd.to_datetime(c1.date_input("Từ ngày", df['Thời gian'].min()))
            end = pd.to_datetime(c2.date_input("Đến ngày", df['Thời gian'].max())) + timedelta(days=1)
            df_work = df[(df['Thời gian'] >= start) & (df['Thời gian'] < end)].copy()
        else:
            df_work = df.copy()

        stage = st.sidebar.radio("Giai đoạn:", ["🌱 Cây con", "🌿 Sinh trưởng", "🍅 Ra hoa"], index=1)
        stt_list = ["Tất cả"] + sorted(df_work['STT'].unique().tolist())
        sel_stt = st.sidebar.selectbox("📍 Chọn Trạm:", stt_list)
        if sel_stt != "Tất cả": df_work = df_work[df_work['STT'] == sel_stt]

        # --- HIỂN THỊ CHỈ SỐ ---
        # Bỏ qua các dòng NaN vừa tạo để tính toán số liệu cuối cùng
        df_valid_for_calc = df_work.dropna(subset=['VPD'])
        
        if not df_valid_for_calc.empty:
            last = df_valid_for_calc.iloc[-1]
            status, advice, color = get_greenhouse_advice(last['VPD'], stage)
            
            st.subheader("📍 Trạng thái hiện tại")
            m1, m2, m3 = st.columns([1, 1.2, 1.8])
            m1.metric("Nhiệt độ", f"{round(last['temp'], 1)} °C")
            m1.metric("Độ ẩm", f"{round(last['humi'], 1)} %")
            
            st.markdown(f'''
                <div style="background-color:{color}; padding:20px; border-radius:15px; color:white; text-align:center;">
                    <h2 style="margin:0;">VPD: {last["VPD"]} kPa</h2>
                    <b style="font-size:1.2em;">{status}</b>
                </div>
            ''', unsafe_allow_html=True)
            
            st.info(f"**Chỉ đạo chuyên gia:** {advice}")

            if st.button("📧 Gửi Email Cảnh Báo Khẩn"):
                if send_email_alert(u_mail, u_pass, t_mail, last['VPD'], status, last['temp'], last['humi']):
                    st.success("✅ Đã gửi!")
                else: st.error("❌ Lỗi cấu hình Gmail!")

            # --- BIỂU ĐỒ TỰ ĐỘNG NGẮT KẾT NỐI (Giữ nguyên connectgaps=False mặc định) ---
            st.subheader("📊 Biểu đồ diễn biến")
            fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.1)
            fig.add_trace(go.Scatter(x=df_work['Thời gian'], y=df_work['VPD'], name="VPD (kPa)", line=dict(color='green', width=3, shape='spline')), row=1, col=1)
            fig.add_trace(go.Scatter(x=df_work['Thời gian'], y=df_work['temp'], name="Nhiệt độ (°C)", line=dict(shape='spline')), row=2, col=1)
            fig.add_trace(go.Scatter(x=df_work['Thời gian'], y=df_work['humi'], name="Độ ẩm (%)", line=dict(shape='spline')), row=2, col=1)
            fig.update_layout(height=500, margin=dict(l=20, r=20, t=20, b=20), hovermode='x unified')
            fig.update_yaxes(range=[0, 3], row=1, col=1)
            st.plotly_chart(fig, use_container_width=True)

            # THỐNG KÊ
            st.subheader("📋 Thống kê chỉ số")
            st.table(df_valid_for_calc[['temp', 'humi', 'VPD']].agg(['max', 'min', 'mean']).round(2))
            
            # BẢNG DỮ LIỆU CHI TIẾT
            def highlight_alert(row):
                if pd.isna(row['VPD']): return [''] * len(row)
                if "Cây con" in stage: i_min, i_max = 0.4, 0.8
                elif "Sinh trưởng" in stage: i_min, i_max = 0.8, 1.2
                else: i_min, i_max = 1.2, 1.5
                if row['VPD'] < (i_min - 0.2) or row['VPD'] > (i_max + 0.3):
                    return ['background-color: #FFC7CE; color: #9C0006; font-weight: bold'] * len(row)
                return [''] * len(row)

            st.dataframe(
                df_valid_for_calc[['Thời gian', 'STT', 'temp', 'humi', 'VPD']]
                .sort_values('Thời gian', ascending=False)
                .style.apply(highlight_alert, axis=1),
                use_container_width=True
            )
        else:
            st.error("🚨 Không có dữ liệu hợp lệ trong khoảng thời gian đã chọn.")
else:
    st.info("👈 Hãy tải file JSON để bắt đầu.")
