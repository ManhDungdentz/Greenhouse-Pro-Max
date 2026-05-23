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
st.title("🌿 Hệ Thống Giám Sát Nhà Kính (Bản Lọc Nhiễu & Full)")

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
    return "🟡 HƠI LỆCH", "Cần điều chỉnh nhẹ.", "#FFA500"

# --- XỬ LÝ DỮ LIỆU & LỌC NHIỄU ---
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
            
            # 1. Sửa lỗi đơn vị (Vd: 332 -> 33.2)
            if col == 'temp':
                df.loc[df[col] > 100, col] = df[col] / 10 
            
            # 2. XÓA BỎ DỮ LIỆU NGOẠI LAI (Outliers) - Fix lỗi nhảy vọt cao chót vót
            if col == 'temp':
                df.loc[(df[col] < 5) | (df[col] > 55), col] = np.nan
            if col == 'humi':
                df.loc[(df[col] < 10) | (df[col] > 100), col] = np.nan
    
    df = df.dropna(subset=['temp', 'humi']).copy()
    
    # 3. Lọc trượt: Nếu giá trị thay đổi đột ngột > 8 đơn vị so với bản ghi trước -> Xóa nhiễu
    if len(df) > 1:
        df = df[df['temp'].diff().abs() < 8] 
        
    if not df.empty: 
        df['VPD'] = df.apply(lambda r: calculate_vpd(r['temp'], r['humi']), axis=1)
    return df

# --- SIDEBAR: CẤU HÌNH & BỘ LỌC ---
with st.sidebar:
    st.header("📧 Cấu hình Gmail")
    u_mail = st.text_input("Gmail gửi:")
    u_pass = st.text_input("Mật khẩu ứng dụng:", type="password")
    t_mail = st.text_input("Gmail nhận:")
    st.divider()
    uploaded_file = st.file_uploader("Tải file JSON quan trắc", type=['json'])

if uploaded_file:
    df = process_data(uploaded_file)
    if not df.empty:
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

        growth_stage = st.sidebar.radio("Giai đoạn cây:", ["🌱 Cây con", "🌿 Sinh trưởng", "🍅 Ra hoa"], index=1)
        stt_list = ["Tất cả"] + sorted(df_work['STT'].unique().tolist())
        sel_stt = st.sidebar.selectbox("📍 Chọn Trạm (STT):", stt_list)
        if sel_stt != "Tất cả": df_work = df_work[df_work['STT'] == sel_stt]

        # --- HIỂN THỊ DỮ LIỆU ---
        df_valid = df_work.dropna(subset=['VPD'])
        if not df_valid.empty:
            last = df_valid.iloc[-1]
            status, advice, color = get_greenhouse_advice(last['VPD'], growth_stage)
            
            st.subheader("📍 Trạng thái hiện tại (Đã lọc nhiễu)")
            m1, m2, m3 = st.columns([1, 1.2, 1.8])
            m1.metric("Nhiệt độ", f"{round(last['temp'], 1)} °C")
            m1.metric("Độ ẩm", f"{round(last['humi'], 1)} %")
            
            html_box = f'<div style="background-color:{color}; padding:15px; border-radius:10px; color:white; text-align:center;"><h3 style="margin:0;">VPD: {last["VPD"]} kPa</h3><b>{status}</b></div>'
            m2.markdown(html_box, unsafe_allow_html=True)
            m3.warning(f"**Chỉ đạo:** {advice}")

            if "🔴" in status:
                if st.button("📧 Gửi Email Cảnh Báo"):
                    if send_email_alert(u_mail, u_pass, t_mail, last['VPD'], status, last['temp'], last['humi']):
                        st.success("✅ Đã gửi email báo cáo!")
                    else: st.error("❌ Kiểm tra lại cấu hình Gmail!")

            # BIỂU ĐỒ MƯỢT MÀ
            fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.1)
            fig.add_trace(go.Scatter(x=df_valid['Thời gian'], y=df_valid['VPD'], name="VPD (kPa)", line=dict(color='green', width=2)), row=1, col=1)
            fig.add_trace(go.Scatter(x=df_valid['Thời gian'], y=df_valid['temp'], name="Nhiệt độ (°C)", line=dict(color='#1f77b4')), row=2, col=1)
            fig.add_trace(go.Scatter(x=df_valid['Thời gian'], y=df_valid['humi'], name="Độ ẩm (%)", line=dict(color='#d62728')), row=2, col=1)
            fig.update_layout(height=600, hovermode='x unified')
            st.plotly_chart(fig, use_container_width=True)

            # THỐNG KÊ MAX/MIN/MEAN
            st.subheader("📋 Thống kê chỉ số")
            st.table(df_valid[['temp', 'humi', 'VPD']].agg(['max', 'min', 'mean']).round(2))
            
            # BẢNG CHI TIẾT NHUỘM MÀU CẢNH BÁO
            def highlight_alert(row):
                if "Cây con" in growth_stage: i_min, i_max = 0.4, 0.8
                elif "Sinh trưởng" in growth_stage: i_min, i_max = 0.8, 1.2
                else: i_min, i_max = 1.2, 1.5
                if row['VPD'] < (i_min - 0.2) or row['VPD'] > (i_max + 0.3):
                    return ['background-color: #FFC7CE; color: #9C0006; font-weight: bold'] * len(row)
                return [''] * len(row)

            st.dataframe(
                df_valid[['Thời gian', 'STT', 'temp', 'humi', 'VPD']]
                .sort_values('Thời gian', ascending=False)
                .style.apply(highlight_alert, axis=1),
                use_container_width=True
            )
        else:
            st.error("🚨 Không có dữ liệu hợp lệ sau khi lọc nhiễu.")
else:
    st.info("👈 Hãy tải file JSON và cấu hình Gmail để bắt đầu.")
