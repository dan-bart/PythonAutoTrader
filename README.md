# PythonAutoTrader
Automatic Stock trading simulation using predefined Supports and Price Targets, running on PostgreSQL, visualized with Flask.
I used this project to get familiar with SQL, Flask (alternative to Django) and CSS/HTML.
Using a simulated portfolio (not connected to any real broker)

## Contents:

- **ideas.txt**
    - Text file containing price targets, supports and stop-outs for selected stocks. Parsed with **trader.py**

-  **trader.py** 
    - Checks hourly stock closes after each hour of trading, and sells/buys, if the price appears near predefined supports/price targets.
    - Runs each hour from 16:31 to 21:31
    - Checks, whether a stop-out level broke at 21:58 to sell all
    
- **app.py**
    - Flask application. Runs on local server. Includes interactive tables of defined trade ideas, portfolio, and recorder trades.
    - Stock graphs with open/close positions are accessible from the /portfolio tab. 
- **static** and **templates**
    - css and html templates for the main app

## How to run it
1. Clone repository
2. Install packages featured in trader.py and app.py
3. Create PostgreSQL server
4. Adapt 3 parameters in "trader.py" (PSYCOPG2_CONNECTION, ENGINE_CONNECTION, FIRST_USE)
5. Run flask app (https://flask.palletsprojects.com/en/2.0.x/quickstart/)

## Future extensions
- Run trader.py with cloud service (AWS)
- Create script to define own supports/price targets (via commonly used trading metrics: moving averages, trendlines..)

