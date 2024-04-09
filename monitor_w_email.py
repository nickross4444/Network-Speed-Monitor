import speedtest
import logging
import time
from statistics import mean, stdev
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# Configuration
LEARNING_MODE_RUNS = 5  # Number of runs to determine the normal speed
SPEED_TOLERANCE_FACTOR = 2  # How much variance from the mean we tolerate
LEARNING_PHASE_SLEEP_INTERVAL = 1#60  # Seconds to wait between learning phase runs
MONITORING_PHASE_SLEEP_INTERVAL = 5#3600  # Seconds to wait between monitoring phase runs

# Function to read configurations
def read_email_config():
    config = {}
    with open("config.txt", "r") as file:
        for line in file:
            key, value = line.strip().split('=', 1)
            config[key] = value
    return config

config = read_email_config()

EMAIL_SENDER = config['EMAIL_SENDER']
EMAIL_PASSWORD = config['EMAIL_PASSWORD']
EMAIL_RECEIVER = config['EMAIL_RECEIVER']
SMTP_SERVER = config['SMTP_SERVER']
SMTP_PORT = int(config['SMTP_PORT'])  # Ensure this is an integer

# Logging configuration
logging.basicConfig(filename='network_speed.log', level=logging.INFO, format='%(asctime)s: %(message)s')

def send_notification(message):
    msg = MIMEMultipart()
    msg['From'] = EMAIL_SENDER
    msg['To'] = EMAIL_RECEIVER
    msg['Subject'] = 'Network Speed Alert'
    msg.attach(MIMEText(message, 'plain'))

    try:
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(EMAIL_SENDER, EMAIL_PASSWORD)
        text = msg.as_string()
        server.sendmail(EMAIL_SENDER, EMAIL_RECEIVER, text)
        server.quit()
        print("Notification sent successfully.")
    except Exception as e:
        print(f"Failed to send notification: {e}")

def measure_speed():
    try:
        st = speedtest.Speedtest()
        st.download()
        st.upload()
        download_speed = st.results.download / 1e6  # Convert to Mbps
        upload_speed = st.results.upload / 1e6  # Convert to Mbps
        return download_speed, upload_speed
    except Exception as e:
        logging.error(f"Error measuring speed: {e}")
        return None, None

def learn_normal_speeds(runs=LEARNING_MODE_RUNS):
    download_speeds = []
    upload_speeds = []

    for _ in range(runs):
        download_speed, upload_speed = measure_speed()
        if download_speed is not None and upload_speed is not None:
            download_speeds.append(download_speed)
            upload_speeds.append(upload_speed)
        time.sleep(LEARNING_PHASE_SLEEP_INTERVAL)

    download_mean = mean(download_speeds)
    upload_mean = mean(upload_speeds)
    download_std = stdev(download_speeds)
    upload_std = stdev(upload_speeds)

    normal_download_range = (download_mean - SPEED_TOLERANCE_FACTOR * download_std, 
                             download_mean + SPEED_TOLERANCE_FACTOR * download_std)
    normal_upload_range = (upload_mean - SPEED_TOLERANCE_FACTOR * upload_std, 
                           upload_mean + SPEED_TOLERANCE_FACTOR * upload_std)

    return normal_download_range, normal_upload_range

def monitor_speed(normal_download_range, normal_upload_range):
    while True:
        download_speed, upload_speed = measure_speed()
        if download_speed is not None and upload_speed is not None:
            print(f"Download Speed: {download_speed:.2f} Mbps, Upload Speed: {upload_speed:.2f} Mbps")
            if not (normal_download_range[0] <= download_speed <= normal_download_range[1]):
                message = f"Abnormal Download Speed: {download_speed:.2f} Mbps"
                logging.info(message)
                print(message)
                send_notification(message)

            if not (normal_upload_range[0] <= upload_speed <= normal_upload_range[1]):
                message = f"Abnormal Upload Speed: {upload_speed:.2f} Mbps"
                logging.info(message)
                print(message)
                send_notification(message)
                
        else:
            print("Error in measuring speed. Skipping this run.")
        time.sleep(MONITORING_PHASE_SLEEP_INTERVAL)

def main():
    print("Learning normal speeds...")
    normal_download_range, normal_upload_range = learn_normal_speeds()
    logging.info(f"Learned normal download speed range: {normal_download_range}")
    logging.info(f"Learned normal upload speed range: {normal_upload_range}")
    print(f"Learned normal download speed range: {normal_download_range}")
    print(f"Learned normal upload speed range: {normal_upload_range}")
    monitor_speed(normal_download_range, normal_upload_range)

if __name__ == "__main__":
    main()
