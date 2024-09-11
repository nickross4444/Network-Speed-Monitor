Run with python to create a logfile of your abnormal internet speeds, along with optional email notifications and a local dashboard.
Access the dashboard with https://localhost:5000 in a browser, or change localhost to an ip address to access from another device.
If you want email notifications, after enabling the boolean in the python script, create a file called config.txt with the following contents:

EMAIL_SENDER=your_email@example.com
EMAIL_PASSWORD=your_app_password
EMAIL_RECEIVER=recipient_email@example.com
SMTP_SERVER=smtp.example.com
SMTP_PORT=587
