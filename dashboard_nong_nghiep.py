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
st.title("🌿 Hệ Thống Giám Sát Nhà Kính (Bản Full Cảnh Báo)")

# --- 1. HÀM GỬI EMAIL CHI TIẾT (NÂNG CẤP) ---
def send_email_alert(sender_mail, app_password, receiver_mail, vpd, status, temp, humi):
    # Phân tích tình huống dựa trên chỉ số thực tế
    if vpd > 1.5:
        ly_do = "Nhiệt độ quá cao kết hợp độ ẩm thấp khiến không khí khô khốc."
        tinh_trang = "Cây đang mất nước cực nhanh, có nguy cơ cháy lá và ngừng sinh trưởng."
        cach_xu_ly = "1. Bật ngay hệ thống phun sương.\n2. Đóng rèm che nắng.\n3. Kiểm tra lưu lượng gió thông qua quạt hút."
    elif vpd < 0.4:
        ly_do = "Không khí bão hòa hơi nước, độ ẩm quá cao."
        tinh_trang = "Cây không thể thoát hơi nước, dễ gây thối rễ và nấm bệnh phát triển mạnh."
        cach_xu_ly = "1. Bật quạt thông gió công suất lớn.\n2. Dừng mọi hoạt động tưới/phun sương.\n3. Kiểm tra độ thông thoáng của nhà kính."
    else:
        ly_do = "Chỉ số đang nằm sát ngưỡng nguy hiểm."
        tinh_trang = "Cây bắt đầu bị stress nhẹ."
        cach_xu_ly = "Điều chỉnh nhẹ các thiết bị hạ nhiệt hoặc tăng ẩm."

    try:
        msg = MIMEMultipart()
        msg['Subject'] = f"🚨 CẢNH BÁO: {status} (VPD: {vpd} kPa)"
        
        body = f"""
        THÔNG BÁO TỪ HỆ THỐNG QUẢN TRẮC NHÀ KÍNH
        -------------------------------------------
        📍 TRẠNG THÁI: {status}
        📈 Chỉ số VPD: {vpd} kPa
        🌡️ Nhiệt độ: {temp} °C
        💧 Độ ẩm: {humi} %
        -------------------------------------------

        🔍 PHÂN TÍCH VÀ CHỈ ĐẠO:
        - Lý do xảy ra: {ly_do}
        - Tình trạng cây: {tinh_trang}

        🛠️ HÀNH ĐỘNG CẦN LÀM NGAY:
        {cach_xu_ly}

        ---
        Thời gian ghi nhận: {pd.Timestamp.now().strftime('%d/%m/%Y %H:%M:%S')}
        Vui lòng xử lý kịp thời để đảm bảo năng suất cây trồng!
        """
        msg.attach(MIMEText(body, 'plain', 'utf-8')) # Đảm bảo không lỗi font tiếng Việt
        
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(sender_mail, app_password)
        server.sendmail(sender_mail, receiver_mail, msg.as_string())
        server.quit()
        return True
    except Exception as e:
        st.sidebar.error(f"Lỗi: {e}")
        return False

# --- 2. TÍNH TOÁN VPD ---
def calculate_vpd(temp, humi):
    if pd.isna(temp) or pd.isna(humi): return None
    vpsat = 0.61078 * np.exp((17.27 * temp) / (temp + 237.3))
    vpair = vpsat * (humi / 100)
    return round(vpsat - vpair, 2)

def get_greenhouse_advice(vpd, stage):
    if pd.isna(vpd): return "N/A", "Đang chờ dữ liệu...", "#808080"
    if "Cây con" in stage: ideal_min, ideal_max = 0.4, 0.8
    elif "Sinh trưởng" in stage: ideal_min, ideal_max = 0.8, 1.2
    else: ideal_min, ideal_max = 1.2, 1.5

    if vpd < ideal_min - 0.2: return "🔴 QUÁ THẤP", "Nguy cơ nấm bệnh!", "#FF4B4B"
    if ideal_min <= vpd <= ideal_max: return "🟢 LÝ TƯỞNG", "Cây phát triển tốt.", "#00C851"
    if vpd > ideal_max + 0.3: return "🔴 QUÁ CAO", "Stress nhiệt nặng!", "#8B0000"
    return "🟡 HƠI LỆCH", "Cần điều chỉnh nhẹ.", "#FFA500"

# --- 3. XỬ LÝ DỮ LIỆU ---
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
                df.loc[(df[col] < 5) | (df[col] > 55), col] = np.nan 
            if col == 'humi':
                df.loc[(df[col] < 20) | (df[col] > 100), col] = np.nan 
    df = df.dropna(subset=['temp', 'humi']).copy()
    if not df.empty: df['VPD'] = df.apply(lambda r: calculate_vpd(r['temp'], r['humi']), axis=1)
    return df

# --- 4. GIAO DIỆN THANH BÊN (SIDEBAR) ---
with st.sidebar:
    st.header("📧 Cấu hình Gmail")
    u_mail = st.text_input("Gmail gửi:", placeholder="ten_cua_ban@gmail.com")
    u_pass = st.text_input("Mật khẩu ứng dụng:", type="password")
    t_mail = st.text_input("Gmail nhận:", placeholder="sep_cua_ban@gmail.com")
    
    st.divider()
    uploaded_file = st.file_uploader("Tải file JSON quan trắc", type=['json'])

# --- 5. HIỂN THỊ NỘI DUNG CHÍNH ---
if uploaded_file:
    df = process_data(uploaded_file)
    if not df.empty:
        # Bộ lọc thời gian & trạm
        st.sidebar.header("🔍 Lọc dữ liệu")
        growth_stage = st.sidebar.radio("Giai đoạn cây:", ["🌱 Cây con", "🌿 Sinh trưởng", "🍅 Ra hoa"], index=1)
        stt_list = ["Tất cả"] + sorted(df['STT'].unique().tolist())
        sel_stt = st.sidebar.selectbox("📍 Chọn Trạm:", stt_list)
        
        df_work = df.copy()
        if sel_stt != "Tất cả": df_work = df_work[df_work['STT'] == sel_stt]
        df_valid = df_work.dropna(subset=['VPD'])
        
        if not df_valid.empty:
            last = df_valid.iloc[-1]
            status, advice, color = get_greenhouse_advice(last['VPD'], growth_stage)
            
            # Khối hiển thị thông số lớn
            st.subheader("📍 Trạng thái hiện tại")
            m1, m2, m3 = st.columns([1, 1, 2])
            m1.metric("Nhiệt độ", f"{round(last['temp'], 1)} °C")
            m1.metric("Độ ẩm", f"{round(last['humi'], 1)} %")
            
            html_card = f'<div style="background-color:{color}; padding:25px; border-radius:15px; color:white; text-align:center;"><h2 style="margin:0;">VPD: {last["VPD"]} kPa</h2><p style="font-size:18px;">{status}</p></div>'
            m2.markdown(html_card, unsafe_allow_html=True)
            m3.warning(f"**Chỉ đạo từ hệ thống:** {advice}")

            # NÚT GỬI MAIL CẢNH BÁO
            if "🔴" in status:
                if st.button("📧 GỬI BÁO CÁO CHI TIẾT QUA EMAIL"):
                    if not u_mail or not u_pass or not t_mail:
                        st.error("Thiếu thông tin Gmail ở thanh bên!")
                    else:
                        with st.spinner("Đang gửi..."):
                            if send_email_alert(u_mail, u_pass, t_mail, last['VPD'], status, last['temp'], last['humi']):
                                st.success("✅ Đã gửi mail báo cáo kèm hướng dẫn xử lý!")

            # Biểu đồ Plotly
            st.markdown("---")
            fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.1)
            fig.add_trace(go.Scatter(x=df_valid['Thời gian'], y=df_valid['VPD'], name="VPD", line=dict(color='green')), row=1, col=1)
            fig.add_trace(go.Scatter(x=df_valid['Thời gian'], y=df_valid['temp'], name="Nhiệt độ"), row=2, col=1)
            fig.add_trace(go.Scatter(x=df_valid['Thời gian'], y=df_valid['humi'], name="Độ ẩm"), row=2, col=1)
            st.plotly_chart(fig, use_container_width=True)

            # Bảng thống kê và dữ liệu
            st.subheader("📋 Thống kê & Chi tiết")
            summ = df_valid[['temp', 'humi', 'VPD']].agg(['max', 'min', 'mean']).round(2)
            st.table(summ)
            
            st.dataframe(df_valid[['Thời gian', 'STT', 'temp', 'humi', 'VPD']].sort_values('Thời gian', ascending=False), use_container_width=True)
