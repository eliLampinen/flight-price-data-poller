import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import seaborn as sns
import os
import re

# Set the style for seaborn
sns.set(style="whitegrid")

# Get the directory of the current script
script_dir = os.path.dirname(os.path.abspath(__file__))
CSV_FILE = os.path.join(script_dir, 'flight_prices_log.csv')

# Load the CSV data into a pandas DataFrame
df = pd.read_csv(CSV_FILE)

# Combine 'log_date' and 'log_time' into a single 'timestamp' column
df['timestamp'] = pd.to_datetime(df['log_date'] + ' ' + df['log_time'], format='%Y-%m-%d %H:%M:%S', errors='coerce')

# Combine 'flight_date' and 'flight_time' into a single 'flight_datetime' column
df['flight_datetime'] = pd.to_datetime(df['flight_date'] + ' ' + df['flight_time'], format='%d-%m-%Y %H:%M', errors='coerce')

# Drop any rows where the 'flight_datetime' or 'timestamp' could not be parsed
df = df.dropna(subset=['flight_datetime', 'timestamp'])

# Sort the DataFrame for better plotting
df = df.sort_values(by=['flight_datetime', 'timestamp'])

# Create a directory for the plots
plots_dir = os.path.join(script_dir, 'plots')
os.makedirs(plots_dir, exist_ok=True)

# Function to sanitize strings for filenames
def sanitize_filename(s):
    # Remove any characters that are not alphanumeric or underscore
    return re.sub(r'[^\w\-]', '_', s)

# Plot the price trends for each flight
def plot_price_trends():
    flights_grouped = df.groupby(['flight_datetime', 'departure', 'destination'])

    for (flight_datetime, departure, destination), data in flights_grouped:
        # Create the plot
        plt.figure(figsize=(12, 6))

        # Plot the price over time
        sns.lineplot(x='timestamp', y='price', data=data, marker='o', linestyle='-')

        # Find min and max prices
        min_price = data['price'].min()
        max_price = data['price'].max()
        min_price_time = data.loc[data['price'].idxmin(), 'timestamp']
        max_price_time = data.loc[data['price'].idxmax(), 'timestamp']

        # Annotate min and max prices
        plt.annotate(f'Min Price: {min_price}€',
                     xy=(min_price_time, min_price),
                     xytext=(min_price_time, min_price + 10),
                     arrowprops=dict(facecolor='green', shrink=0.05),
                     fontsize=12, color='green')

        plt.annotate(f'Max Price: {max_price}€',
                     xy=(max_price_time, max_price),
                     xytext=(max_price_time, max_price + 10),
                     arrowprops=dict(facecolor='red', shrink=0.05),
                     fontsize=12, color='red')

        # Set the title and labels
        plt.title(f"Price Trend for Flight on {flight_datetime.strftime('%Y-%m-%d %H:%M')}\nFrom {departure} to {destination}", fontsize=16)
        plt.xlabel("Time of Check", fontsize=14)
        plt.ylabel("Price (€)", fontsize=14)

        # Format the x-axis dates
        plt.gca().xaxis.set_major_locator(mdates.AutoDateLocator())
        plt.gca().xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d\n%H:%M'))
        plt.xticks(rotation=45, ha='right')

        # Adjust y-axis to fit annotations
        y_min, y_max = plt.ylim()
        plt.ylim(y_min, y_max + 20)  # Adjust as needed

        # Add gridlines
        plt.grid(True, linestyle='--', alpha=0.7)

        # Tight layout
        plt.tight_layout()

        # Sanitize departure and destination for filename
        departure_safe = sanitize_filename(departure)
        destination_safe = sanitize_filename(destination)

        # Save the plot as a PNG file
        plot_filename = os.path.join(plots_dir, f"flight_price_trend_{flight_datetime.strftime('%Y-%m-%d_%H-%M')}_{departure_safe}_to_{destination_safe}.png")
        plt.savefig(plot_filename)
        plt.close()  # Close the figure to free memory
        print(f"Saved plot for flight on {flight_datetime.strftime('%Y-%m-%d %H:%M')} from {departure} to {destination} as {plot_filename}")

# Generate an HTML report to compile all plots
def generate_html_report():
    plot_files = sorted([f for f in os.listdir(plots_dir) if f.endswith('.png')])

    html_content = "<html><head><title>Flight Price Trends Report</title></head><body>"
    html_content += "<h1>Flight Price Trends Report</h1>"

    for plot_file in plot_files:
        # Extract flight_datetime, departure, and destination from filename
        # Assuming filenames are in the format: flight_price_trend_YYYY-MM-DD_HH-MM_departure_to_destination.png
        match = re.match(r'flight_price_trend_(.*?)_(.*?)_to_(.*?).png', plot_file)
        if match:
            flight_datetime_str = match.group(1).replace('_', ' ')
            departure = match.group(2).replace('_', ' ')
            destination = match.group(3).replace('_', ' ')
            flight_info = f"Flight on {flight_datetime_str} from {departure} to {destination}"
        else:
            flight_info = plot_file  # If the filename doesn't match, just use the filename

        html_content += f"<h2>{flight_info}</h2>"
        html_content += f'<img src="plots/{plot_file}" alt="{flight_info}" style="max-width:100%; height:auto;">'

    html_content += "</body></html>"

    report_filename = os.path.join(script_dir, 'flight_price_trends_report.html')
    with open(report_filename, 'w') as f:
        f.write(html_content)
    print(f"Generated HTML report: {report_filename}")

# Call the plotting and report generation functions
if __name__ == "__main__":
    plot_price_trends()
    generate_html_report()
