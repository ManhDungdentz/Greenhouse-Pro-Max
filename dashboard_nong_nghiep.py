import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import timedelta
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from twilio.rest import Client  # Lưu ý: Cần chạy lệnh 'pip install twilio' trong terminal

# --- CẤU HÌNH TRANG ---
st.set_page_config(page_title="Greenhouse Pro Max", layout="wide")
st.title("🌿 Hệ Thống Giám Sát Nhà Kính (Bản Full - Gửi SMS SĐT)")

# --- HÀM GỬI SMS ĐẾN SỐ ĐIỆN THOẠI (Thay thế hoàn toàn Zalo) ---
def send_sms_alert(sid, auth_token, from_num, to_num, vpd, status, temp, humi):
    try:
        client = Client(sid, auth_token)
        msg = f"🚨 CANH BAO VPD: {status}\n📈 VPD: {vpd} kPa\n🌡️ Temp: {temp}C\n💧 Humi: {humi}%\n🛠️ Kiem tra nha kinh ngay!"
        message = client.messages.create(
            body=msg,
            from_=from_num,
            to=to_num
        )
        return True if message.sid else False
    except: 
        return False

# --- HÀM GỬI EMAIL ---
def send_email_alert(sender_mail, app_password, receiver_mail, vpd, status, temp, humi):
    try:
        msg = MIMEMultipart()
        msg['Subject'] = f"🚨 CẢNH BÁO VPD: {status}"
        body = f"📍 TRẠNG THÁI: {status}\nVPD: {vpd} kPa\nNhiệt độ: {temp}°C\nĐộ ẩm: {humi}%\n\nKiểm tra hệ thống thiết bị ngay!"
        msg.attach(MIMEText(body, 'plain', 'utf-8'))
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(sender_mail, app_password)
        server.sendmail(sender_mail, receiver_mail, msg.as_string())
        server.quit()
        return True
    except: return False

# --- TÍNH TOÁN CHỈ SỐ VPD ---
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
    return "🟡 HƠI LỆCH", "Cần điều chỉnh nhẹ.", "#FFA500"

# --- XỬ LÝ DỮ LIỆU TỪ FILE JSON ---
def process_data(file):
    try:
        df = pd.read_json(file)
    except: return pd.DataFrame()
    if 'Thời gian' in df.columns:
        df['Thời gian'] = pd.to_datetime(df['Thời gian'].astype(str).str.replace('-', ' ', n=2).str.replace('-', ':'), errors='coerce', utc=True).dt.tz_localize(None)
        df = df.dropna(subset=['Thời gian']).sort_values('Thời gian')
    
    # Ưu tiên lấy dữ liệu từ cột KK (Không khí)
    t_cols = [c for c in ['tempKK', 'Nhiệt Độ'] if c in df.columns]
    if t_cols: df['temp'] = df[t_cols].bfill(axis=1).iloc[:, 0]
    h_cols = [c for c in ['humiKK', 'Độ ẩm'] if c in df.columns]
    if h_cols: df['humi'] = df[h_cols].bfill(axis=1).iloc[:, 0]
    
    for col in ['temp', 'humi']:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col].astype(str).str.extract(r'(\d+\.?\d*)')[0], errors='coerce')
            if col == 'temp':
                df.loc[df[col] > 150, col] = df[col] / 10 
                df.loc[(df[col] >= 45) & (df[col] <= 120), col] = (df[col] - 32) * 5/9 
                df.loc[(df[col] < 5) | (df[col] > 55), col] = np.nan 
            if col == 'humi':
                df.loc[(df[col] < 20) | (df[col] > 100), col] = np.nan 
                
    df = df.dropna(subset=['temp', 'humi']).copy()
    if not df.empty: df['VPD'] = df.apply(lambda r: calculate_vpd(r['temp'], r['humi']), axis=1)
    return df

# --- GIAO DIỆN THANH BÊN (SIDEBAR) ---
with st.sidebar:
    st.header("⚙️ Cấu hình Thông báo")
    tab1, tab2 = st.tabs(["📧 Gmail", "📱 Số điện thoại (SMS)"])
    with tab1:
        u_mail = st.text_input("Gmail gửi:")
        u_pass = st.text_input("Mật khẩu ứng dụng:", type="password")
        t_mail = st.text_input("Gmail nhận:")
    with tab2:
        st.caption("Cấu hình API gửi tin nhắn SMS SMS Gateway (Twilio)")
        tw_sid = st.text_input("Twilio Account SID:", type="password")
        tw_token = st.text_input("Twilio Auth Token:", type="password")
        tw_from = st.text_input("Số điện thoại ảo gửi (Twilio Number):")
        tw_to = st.text_input("Số điện thoại nhận (VD: +8490xxxxxxx):")
    
    st.divider()
    uploaded_file = st.file_uploader("Tải file JSON quan trắc", type=['json'])

# --- HIỂN THỊ MAIN DASHBOARD ---
if uploaded_file:
    df = process_data(uploaded_file)
    if not df.empty:
        # BỘ LỌC DỮ LIỆU THỜI GIAN
        st.sidebar.header("🔍 Lọc dữ liệu")
        df['Tháng'] = df['Thời gian'].dt.strftime('%m/%Y')
        filter_mode = st.sidebar.radio("Chế độ lọc thời gian:", ["Tất cả", "Tháng", "Khoảng ngày"])
        
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

        # BỘ LỌC TRẠM (STT)
        growth_stage = st.sidebar.radio("Giai đoạn cây:", ["🌱 Cây con", "🌿 Sinh trưởng", "🍅 Ra hoa"], index=1)
        stt_list = ["Tất cả"] + sorted(df_work['STT'].unique().tolist())
        sel_stt = st.sidebar.selectbox("📍 Chọn Trạm (STT):", stt_list)
        if sel_stt != "Tất cả": 
            df_work = df_work[df_work['STT'] == sel_stt]

        df_valid = df_work.dropna(subset=['VPD'])
        if not df_valid.empty:
            last = df_valid.iloc[-1]
            status, advice, color = get_greenhouse_advice(last['VPD'], growth_stage)
            
            # Khối hiển thị chỉ số Metric hiện tại
            st.subheader("📍 Trạng thái chỉ số hiện tại")
            m1, m2, m3 = st.columns([1, 1.2, 1.8])
            m1.metric("Nhiệt độ", f"{round(last['temp'], 1)} °C")
            m1.metric("Độ ẩm", f"{round(last['humi'], 1)} %")
            
            html_box = f'<div style="background-color:{color}; padding:15px; border-radius:10px; color:white; text-align:center;"><h3 style="margin:0;">VPD: {last["VPD"]} kPa</h3><b>{status}</b></div>'
            m2.markdown(html_box, unsafe_allow_html=True)
            m3.warning(f"**Chỉ đạo:** {advice}")

            # Khối nút bấm Gửi Cảnh báo
            if "🔴" in status:
                cb1, cb2 = st.columns(2)
                if cb1.button("📧 Gửi Gmail Cảnh Báo"):
                    if send_email_alert(u_mail, u_pass, t_mail, last['VPD'], status, last['temp'], last['humi']):
                        st.success("✅ Đã gửi Gmail thành công!")
                    else: 
                        st.error("❌ Lỗi cấu hình Gmail!")
                if cb2.button("📱 Gửi SMS Đến Điện Thoại"):
                    if send_sms_alert(tw_sid, tw_token, tw_from, tw_to, last['VPD'], status, last['temp'], last['humi']):
                        st.success(f"✅ Đã gửi tin nhắn SMS đến số {tw_to}!")
                    else: 
                        st.error("❌ Lỗi gửi SMS! Hãy kiểm tra lại tài khoản Twilio.")

            # BIỂU ĐỒ TRỰC QUAN
            fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.1)
            fig.add_trace(go.Scatter(x=df_valid['Thời gian'], y=df_valid['VPD'], name="VPD (kPa)", line=dict(color='green')), row=1, col=1)
            fig.add_trace(go.Scatter(x=df_valid['Thời gian'], y=df_valid['temp'], name="Nhiệt độ (°C)"), row=2, col=1)
            fig.add_trace(go.Scatter(x=df_valid['Thời gian'], y=df_valid['humi'], name="Độ ẩm (%)"), row=2, col=1)
            st.plotly_chart(fig, use_container_width=True)

            # BẢNG THỐNG KÊ CHỈ SỐ MAX, MIN, MEAN (Bảng ông cần quay lại)
            st.subheader("📊 Thống kê chỉ số (Max, Min, Trung bình)")
            stats_df = df_valid[['temp', 'humi', 'VPD']].agg(['max', 'min', 'mean']).round(2)
            stats_df.index = ['Lớn nhất (Max)', 'Nhỏ nhất (Min)', 'Trung bình (Mean)']
            st.table(stats_df)

            # BẢNG CHI TIẾT BẢN GHI (Nhuộm màu nền hồng chữ đỏ đậm cho dòng nguy hiểm)
            st.subheader("📋 Chi tiết bản ghi")
            def style_critical_rows(row):
                if row['VPD'] > 1.5 or row['VPD'] < 0.4:
                    return ['background-color: #FFC7CE; color: #9C0006; font-weight: bold'] * len(row)
                return [''] * len(row)

            st.dataframe(
                df_valid[['Thời gian', 'STT', 'temp', 'humi', 'VPD']]
                .sort_values('Thời gian', ascending=False)
                .style.apply(style_critical_rows, axis=1),
                use_container_width=True
            )
        else:
            st.error("🚨 Không tìm thấy dữ liệu hợp lệ trong bộ lọc.")
else:
    st.info("👈 Hãy tải file JSON quan trắc từ thanh bên để bắt đầu hiển thị dữ liệu.")
