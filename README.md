
# Flight Poller

The **Flight Poller** monitors exact charter flights exposed via an external flight-data JSON API. Every configuration entry points to a ready-made API URL and a set of identifying fields, ensuring that the monitor can follow the precise departure you care about. Whenever the API price meets or beats your threshold the script sends an email alert and appends the observation to `flight_prices_log.csv` for later analysis.

## Table of Contents

- [Features](#features)
- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Configuration](#configuration)
- [Usage](#usage)
- [Data Visualization (Optional)](#data-visualization-optional)
- [Error Handling](#error-handling)

---

## Features

- **JSON API monitor**: Pulls structured data directly from a flight-data API using per-flight URLs you paste into the config.
- **Exact flight matching**: Identify flights by id, departure date/time, or any other field returned in the payload.
- **Smart pagination**: Automatically walks through all available API pages until the target flight is found.
- **Price-drop alerts**: Emails configurable recipients when a fare meets your threshold and beats the previous best price (optional equal-price alerts).
- **Historical logging**: Appends each observation to `flight_prices_log.csv`, enabling later trend analysis via the included plotting script.

## Prerequisites

- Python 3.8 or higher
- Required Python packages:
  - `requests`
   - `smtplib` / `email` (standard library for alerts)
   - `pandas`, `matplotlib`, `seaborn` (only required when running `visualize_flight_prices.py`)

## Installation

1. **Clone the Repository**

   ```bash
   git clone https://github.com/elilampinen/flight-price-data-poller.git
   cd flight-price-data-poller
   ```

2. **Create a Virtual Environment (Optional but Recommended)**

   ```bash
   python3 -m venv venv
   source venv/bin/activate  # On Windows use `venv\Scripts ctivate`
   ```

3. **Install Required Packages**

   ```bash
   pip install -r requirements.txt
   ```

## Configuration

All runtime options live in `configFile.py`. The important bits are your email credentials, the environment flag (`dev` disables the random startup delay), and the `FLIGHT_CONFIGS` list. Each entry in `FLIGHT_CONFIGS` must include:

- `name`: Friendly label used for logs and alert subjects.
- `api_url`: Full flight-data API URL you copied from the browser (the monitor overrides the `page` parameter while paging through results).
- `match`: Dictionary of field/value pairs that uniquely identify the flight (e.g. `id`, `r1_dep_date`, `r1_dep_time`).
- `price_threshold`: Integer threshold in euros.
- `emails`: Either a list or comma-separated string of recipients.

Additional rules:

- Include both `r2_dep_date` and `r2_dep_time` inside the `match` block so the poller can differentiate return durations (7/14/21-day packages).

Example snippet:

```python
email_sender = 'youremail@example.com'
email_password = 'app-password'
env = 'dev'

FLIGHT_CONFIGS = [
   {
      "name": "OUL -> LPA | 2026-03-09",
      "api_url": "https://api.exampleflightdata.com/flights?departure=1112&destination=291&page=1",
      "match": {
         "id": "3331717506",
         "r1_dep_date": "2026-03-09",
         "r1_dep_time": "16:55",
         "r2_dep_date": "2026-03-30",
         "r2_dep_time": "07:10"
      },
      "price_threshold": 600,
      "emails": ["alerts@example.com"]
   }
]
```

> **Tip:** Inspect the API JSON in your browser developer tools and copy the fields that best identify the flight (id is usually sufficient). The monitor walks through every available page until the matcher succeeds.

## Usage

To start monitoring flight prices, simply run:

```bash
python flight_price_monitor.py
```

The script will:
- Iterate over every entry in `FLIGHT_CONFIGS`.
- Page through the corresponding API endpoint until it finds the flight defined in `match`.
- Log the latest price into `flight_prices_log.csv`.
- Email each configured recipient when the price drops below your threshold and improves over the previous best logged price.

### Running Periodically

For continuous monitoring, it's recommended to set up a scheduled task or cron job. Here are a few examples:

**Linux (cron job)**:

```bash
# Run every hour
0 * * * * /path/to/your/venv/bin/python /path/to/flight_price_monitor.py
```

**Windows (Task Scheduler)**:

- Use Task Scheduler to run the script every hour or at a frequency of your choosing.

## Data Visualization (Optional)

Use `visualize_flight_prices.py` to convert the CSV into per-flight PNG plots plus a bundled HTML report:

```bash
python visualize_flight_prices.py
```

The script groups rows by departure and destination, then plots the observed fares over time. Exported figures live in `plots/` and the summary HTML is saved as `flight_price_trends_report.html`.


## Error Handling

- Errors are logged to an `error_log.txt` file.
- API request errors are logged to `api_error_log.json`.
- If an error occurs during the flight data fetch, an email alert will be sent to notify you.
