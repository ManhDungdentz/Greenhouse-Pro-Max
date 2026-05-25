import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import timedelta
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# --- 1. CẤU HÌNH TRANG ---
st.set_page_config(page_title="Greenhouse Pro Max", layout="wide")
st.title("🌿 Hệ Thống Giám Sát Nhà Kính (Bản Mượt Tuyệt Đối)")

# --- 2. HÀM GỬI EMAIL ---
def send_email_alert(sender_mail, app_password, receiver_mail, vpd, status, temp, humi):
    try:
        msg = MIMEMultipart()
        msg['Subject'] = f"🚨 CẢNH BÁO VPD: {status}"
        body = f"📍 TRẠNG THÁI: {status}\nVPD: {vpd} kPa\nNhiệt độ: {temp}°C\nĐộ ẩm: {humi}%"
        msg.attach(MIMEText(body, 'plain', 'utf-8'))
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(sender_mail, app_password)
        server.sendmail(sender_mail, receiver_mail, msg.as_string())
        server.quit()
        return True
    except: return False

# --- 3. TÍNH TOÁN VPD ---
def calculate_vpd(temp, humi):
    if pd.isna(temp) or pd.isna(humi) or humi <= 5: return None
    vpsat = 0.61078 * np.exp((17.27 * temp) / (temp + 237.3))
    vpair = vpsat * (humi / 100)
    return round(max(0, vpsat - vpair), 2)

# --- 4. XỬ LÝ DỮ LIỆU & KHỬ NHIỄU "CỘT ĐÌNH" ---
def process_data(file):
    try:
        df = pd.read_json(file)
    except: return pd.DataFrame()
    
    if 'Thời gian' in df.columns:
        df['Thời gian'] = pd.to_datetime(df['Thời gian'].astype(str).str.replace('-', ' ', n=2).str.replace('-', ':'), errors='coerce', utc=True).dt.tz_localize(None)
        df = df.dropna(subset=['Thời gian']).sort_values('Thời gian')
    
    # Gộp cột Nhiệt độ/Độ ẩm từ các trạm khác nhau
    t_cols = [c for c in ['Nhiệt Độ', 'tempKK'] if c in df.columns]
    if t_cols: df['temp'] = df[t_cols].bfill(axis=1).iloc[:, 0]
    h_cols = [c for c in ['Độ ẩm', 'humiKK'] if c in df.columns]
    if h_cols: df['humi'] = df[h_cols].bfill(axis=1).iloc[:, 0]
    
    for col in ['temp', 'humi']:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col].astype(str).str.extract(r'(\d+\.?\d*)')[0], errors='coerce')
            
            # CHẶN RÁC VẬT LÝ: Bỏ qua các giá trị cảm biến hỏng (Độ ẩm < 10% hoặc Temp > 60)
            if col == 'temp':
                df.loc[df[col] > 150, col] = df[col] / 10 
                df.loc[(df[col] >= 45) & (df[col] <= 120), col] = (df[col] - 32) * 5/9 
                df.loc[(df[col] < 5) | (df[col] > 60), col] = np.nan
            if col == 'humi':
                df.loc[(df[col] < 10) | (df[col] > 100), col] = np.nan

    # LỌC LÀM MƯỢT (SMOOTHING): Trị dứt điểm "cột đình"
    df = df.dropna(subset=['temp', 'humi']).copy()
    if len(df) > 5:
        for c in ['temp', 'humi']:
            # Dùng Trung vị cửa sổ 5 để triệt tiêu các điểm nhảy vọt (spikes)
            df[c] = df[c].rolling(window=5, center=True, min_periods=1).median()
            # Lấp đầy các khoảng trống bằng nội suy tuyến tính
            df[c] = df[c].interpolate().ffill().bfill()

    if not df.empty: 
        df['VPD'] = df.apply(lambda r: calculate_vpd(r['temp'], r['humi']), axis=1)
        # Giới hạn VPD tối đa trên biểu đồ để tránh làm hỏng scale (Max 2.5)
        df.loc[df['VPD'] > 2.5, 'VPD'] = np.nan
        df['VPD'] = df['VPD'].interpolate()
        
    return df

# --- 5. GIAO DIỆN STREAMLIT ---
with st.sidebar:
    st.header("📧 Cấu hình Gmail")
    u_mail = st.text_input("Gmail gửi:")
    u_pass = st.text_input("Mật khẩu ứng dụng:", type="password")
    t_mail = st.text_input("Gmail nhận:")
    st.divider()
    uploaded_file = st.file_uploader("Tải file JSON dữ liệu", type=['json'])

if uploaded_file:
    df = process_data(uploaded_file)
    if not df.empty:
        # Bộ lọc thời gian và trạm
        st.sidebar.header("🔍 Bộ lọc")
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
        else: df_work = df.copy()

        stt_list = ["Tất cả"] + sorted(df_work['STT'].unique().tolist())
        sel_stt = st.sidebar.selectbox("📍 Chọn Trạm:", stt_list)
        if sel_stt != "Tất cả": df_work = df_work[df_work['STT'] == sel_stt]

        # Dashboard hiển thị
        df_valid = df_work.dropna(subset=['VPD'])
        if not df_valid.empty:
            last = df_valid.iloc[-1]
            vpd_val = last['VPD']
            color = "#00C851" if 0.8 <= vpd_val <= 1.2 else ("#1E90FF" if vpd_val < 0.8 else "#FF4B4B")
            status = "🟢 LÝ TƯỞNG" if 0.8 <= vpd_val <= 1.2 else ("🔵 QUÁ THẤP" if vpd_val < 0.8 else "🔴 QUÁ CAO")

            st.subheader("📍 Thông số hiện tại")
            m1, m2, m3 = st.columns([1, 1.2, 1.8])
            m1.metric("Nhiệt độ", f"{round(last['temp'], 1)} °C")
            m1.metric("Độ ẩm", f"{round(last['humi'], 1)} %")
            m2.markdown(f'<div style="background-color:{color};padding:20px;border-radius:10px;color:white;text-align:center;"><h3>VPD: {vpd_val} kPa</h3><b>{status}</b></div>', unsafe_allow_html=True)
            m3.info(f"Dữ liệu trạm {last['STT']} cập nhật lúc {last['Thời gian'].strftime('%H:%M %d/%m')}")

            if st.button("📧 Gửi Email Cảnh Báo Ngay"):
                if send_email_alert(u_mail, u_pass, t_mail, vpd_val, status, last['temp'], last['humi']):
                    st.success("✅ Đã gửi email thành công!")
                else: st.error("❌ Lỗi cấu hình Gmail!")

            # --- BIỂU ĐỒ DIỄN BIẾN MƯỢT MÀ ---
            st.subheader("📊 Biểu đồ diễn biến (Đã làm mượt)")
            fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.1)
            # VPD Trace
            fig.add_trace(go.Scatter(x=df_valid['Thời gian'], y=df_valid['VPD'], name="VPD (kPa)", line=dict(color='green', width=3)), row=1, col=1)
            # Dải màu đậm (Opacity 0.4)
            fig.add_hrect(y0=0, y1=0.8, fillcolor="rgba(30, 144, 255, 0.4)", line_width=0, row=1, col=1)
            fig.add_hrect(y0=0.8, y1=1.2, fillcolor="rgba(0, 200, 81, 0.4)", line_width=0, row=1, col=1)
            fig.add_hrect(y0=1.2, y1=2.5, fillcolor="rgba(255, 75, 75, 0.4)", line_width=0, row=1, col=1)
            
            # Temp & Humi Trace
            fig.add_trace(go.Scatter(x=df_valid['Thời gian'], y=df_valid['temp'], name="Nhiệt độ (°C)"), row=2, col=1)
            fig.add_trace(go.Scatter(x=df_valid['Thời gian'], y=df_valid['humi'], name="Độ ẩm (%)"), row=2, col=1)
            
            fig.update_layout(height=600, template="plotly_white", hovermode='x unified')
            fig.update_yaxes(range=[0, 2.5], row=1, col=1) # Khóa trục Y VPD
            st.plotly_chart(fig, use_container_width=True)

            # Bảng dữ liệu chi tiết
            st.subheader("📋 Bảng thống kê & Dữ liệu chi tiết")
            st.table(df_valid[['temp', 'humi', 'VPD']].agg(['max', 'min', 'mean']).round(2))
            
            def style_vpd(row):
                if row['VPD'] > 1.2: return ['background-color: #FFC7CE'] * len(row)
                if row['VPD'] < 0.8: return ['background-color: #D6EAF8'] * len(row)
                return [''] * len(row)

            st.dataframe(df_valid[['Thời gian', 'STT', 'temp', 'humi', 'VPD']].sort_values('Thời gian', ascending=False).style.apply(style_vpd, axis=1), use_container_width=True)
        else: st.error("🚨 Không có dữ liệu hợp lệ.")
else: st.info("👈 Hãy tải file JSON vào sidebar để bắt đầu.")
