import requests
from bs4 import BeautifulSoup
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.utils import formatdate
import json
import os
import time
import random
from datetime import datetime
from configFile import (
    email_sender,
    email_password,
    email_receivers,
    dates_to_track,
    price_threshold,
    url,
    host,
    env
)

import csv
from datetime import datetime

# Constants
# Get the directory of the current script
script_dir = os.path.dirname(os.path.abspath(__file__))

# Define file paths relative to the script's directory
DATA_FILE = os.path.join(script_dir, 'previous_flights.json')
API_ERROR_LOG_FILE = os.path.join(script_dir, 'api_error_log.json')
GENERAL_ERROR_LOG_FILE = os.path.join(script_dir, 'error_log.txt')
LAST_RUN_LOG_FILE = os.path.join(script_dir, 'last_run.txt')
CSV_FILE = os.path.join(script_dir, 'flight_prices_log.csv')


def log_error_to_file(error_message):
    with open(GENERAL_ERROR_LOG_FILE, 'a') as error_log_file:
        error_log_file.write(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - {error_message}\n")
    print(f"Error logged: {error_message}")

def has_future_dates():
    today = datetime.now().date()
    print("Checking future dates...")
    for date_str in dates_to_track:
        date_part = date_str.split('·')[0].strip()
        try:
            flight_date = datetime.strptime(date_part, '%d-%m-%Y').date()
            if flight_date >= today:
                print(f"Future date found: {flight_date}")
                return True
        except ValueError:
            print(f"Invalid date format: {date_part}")
            continue
    print("No future dates to track.")
    return False

def fetch_flight_data():
    headers = {
        'Host': host,
        'User-Agent': 'curl/8.5.0',
        'Accept': '*/*',
    }

    print(f"Fetching flight data from URL: {url}")
    
    try:
        response = requests.get(url, headers=headers)
        if response.status_code != 200:
            print(f"Error: Failed to fetch data. Status code: {response.status_code}, Response text: {response.text}")
            handle_api_error(response.status_code)
            return None
        response.raise_for_status()
        print("Flight data fetched successfully.")
        with open(LAST_RUN_LOG_FILE, "w") as f:
            f.write(f"Last run: {datetime.now()}\n")
        return response.text
    except requests.RequestException as e:
        print(f"RequestException occurred: {str(e)}")
        handle_api_error(str(e))
        return None

def handle_api_error(error_message):
    error_logged_today = False
    today_str = datetime.now().strftime('%Y-%m-%d')

    if os.path.exists(API_ERROR_LOG_FILE):
        with open(API_ERROR_LOG_FILE, 'r') as f:
            error_log = json.load(f)
            last_error_date = error_log.get('last_error_date')
            if last_error_date == today_str:
                error_logged_today = True
    else:
        error_log = {}

    if not error_logged_today:
        send_error_email(error_message)
        error_log['last_error_date'] = today_str
        with open(API_ERROR_LOG_FILE, 'w') as f:
            json.dump(error_log, f)

def send_error_email(error_message):
    msg = MIMEMultipart()
    msg['From'] = email_sender
    msg['To'] = ', '.join(email_receivers)
    msg['Date'] = formatdate(localtime=True)
    msg['Subject'] = "Flight Monitor Error Alert"

    body = f"""
    An error occurred while fetching flight data:

    Error: {error_message}

    This is a notification to inform you of the issue. The script will attempt to run again in the next scheduled interval.
    """

    msg.attach(MIMEText(body, 'plain'))

    try:
        server = smtplib.SMTP_SSL('smtp.gmail.com', 465)
        server.login(email_sender, email_password)
        server.sendmail(email_sender, email_receivers, msg.as_string())
        server.quit()
        print("Error email sent.")
    except Exception as e:
        print(f"Failed to send error email: {e}")

def parse_flight_data(html_content):
    soup = BeautifulSoup(html_content, 'html.parser')
    flight_rows = soup.select('a.lms-row')
    flights = []

    print(f"Parsing {len(flight_rows)} flights from the HTML content.")
    
    for row in flight_rows:
        departure_info = row.select_one('div.departy p:nth-of-type(1)').text.strip()  # Extract departure place
        date_info = row.select_one('div.departy p:nth-of-type(2)').text.strip()  # Extract flight date and time
        destination_info = row.select_one('div.destiny p:nth-of-type(2)').text.strip()  # Extract destination
        price_info = row.select_one('div.pricey p.current-price').text.strip()

        hurry_element = row.select_one('div.hurry p')
        hurry_text = hurry_element.text.strip() if hurry_element else None

        price = int(price_info.split(' ')[0])  # Extract price as integer
        flight = {
            'departure_info': departure_info,
            'date_info': date_info,
            'destination_info': destination_info,
            'price': price,
            'link': row['href'],
            'hurry_text': hurry_text
        }
        flights.append(flight)
    
    print(f"Total flights parsed: {len(flights)}")
    return flights


def load_previous_flights():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r') as f:
            return json.load(f)
    else:
        return {}

def save_current_flights(flights_data):
    with open(DATA_FILE, 'w') as f:
        json.dump(flights_data, f)

def send_email(alerts):
    if not alerts:
        print("No alerts to send.")
        return

    print(f"Preparing to send {len(alerts)} alerts via email.")
    
    msg = MIMEMultipart()
    msg['From'] = email_sender
    msg['To'] = ', '.join(email_receivers)
    msg['Date'] = formatdate(localtime=True)
    msg['Subject'] = "Flight Alerts"

    body = ""

    for alert in alerts:
        if alert['type'] == 'price_drop':
            body += f"""
            Price Drop Alert:
            Flight Date: {alert['flight']['date_info']}
            New Price: {alert['flight']['price']} euros
            Destination: {alert['flight']['destination_info']}
            Booking Link: {alert['flight']['link']}
            ----------------------------------------
            """
        elif alert['type'] == 'hurry':
            body += f"""
            Hurry Alert:
            Limited Seats for Flight on {alert['flight']['date_info']}
            Seats Left: {alert['flight']['hurry_text']}
            Price: {alert['flight']['price']} euros
            Destination: {alert['flight']['destination_info']}
            Booking Link: {alert['flight']['link']}
            ----------------------------------------
            """

    msg.attach(MIMEText(body, 'plain'))

    try:
        server = smtplib.SMTP_SSL('smtp.gmail.com', 465)
        server.login(email_sender, email_password)
        server.sendmail(email_sender, email_receivers, msg.as_string())
        server.quit()
        print("Email sent with all alerts.")
    except Exception as e:
        print(f"Failed to send email: {e}")

def log_flight_price(flight_date, flight_time, departure, destination, price):
    current_time = datetime.now()
    log_date = current_time.strftime("%Y-%m-%d")
    log_time = current_time.strftime("%H:%M:%S")

    with open(CSV_FILE, 'a', newline='', encoding='utf-8') as csvfile:
        fieldnames = ['log_date', 'log_time', 'flight_date', 'flight_time', 'departure', 'destination', 'price']
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)

        if csvfile.tell() == 0:
            writer.writeheader()

        writer.writerow({
            'log_date': log_date,
            'log_time': log_time,
            'flight_date': flight_date,
            'flight_time': flight_time,
            'departure': departure,
            'destination': destination,
            'price': price
        })

def main():
    if env != "dev":
        time.sleep(random.uniform(123, 1231))
        print(f"Running in {env} environment. Delayed start.")

    if not has_future_dates():
        print("No future dates available for tracking. Exiting.")
        return

    html_content = fetch_flight_data()
    if html_content is None:
        print("No HTML content fetched. Exiting.")
        return

    flights = parse_flight_data(html_content)
    previous_flights = load_previous_flights()
    current_flights = {}

    alerts = []

    for flight in flights:
        date_info = flight['date_info']
        departure = flight['departure_info']
        flight_date, flight_time = date_info.split(' · ')
        price = flight['price']
        hurry_text = flight['hurry_text']
        flight_key = date_info  

        destination_info = flight['destination_info']

        # Only log flights that are in dates_to_track
        if date_info in dates_to_track:
            log_flight_price(flight_date, flight_time, departure, destination_info, price)

        current_flights[flight_key] = {
            'price': price,
            'hurry_alert_sent': False
        }

        prev_flight_data = previous_flights.get(flight_key, {})
        prev_price = prev_flight_data.get('price')
        hurry_alert_sent = prev_flight_data.get('hurry_alert_sent', False)

        if hurry_text and not hurry_alert_sent:
            alerts.append({'type': 'hurry', 'flight': flight})
            current_flights[flight_key]['hurry_alert_sent'] = True
        else:
            current_flights[flight_key]['hurry_alert_sent'] = hurry_alert_sent

        if date_info in dates_to_track and price <= price_threshold:
            current_flights[flight_key]['price'] = price

            if prev_price is None or price < prev_price:
                alerts.append({'type': 'price_drop', 'flight': flight})

    send_email(alerts)
    save_current_flights(current_flights)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        error_message = f"Unexpected error in main(): {str(e)}"
        log_error_to_file(error_message)
