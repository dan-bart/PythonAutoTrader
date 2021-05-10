import trader
import yfinance
from flask_sqlalchemy import SQLAlchemy
from flask import Flask, render_template, url_for
from flask_bootstrap import Bootstrap
from flask_table import Table, Col

import bokeh.sampledata
import pandas as pd
from bokeh.layouts import gridplot
from bokeh.plotting import figure, output_file, show
from bokeh.sampledata.stocks import AAPL, GOOG, IBM, MSFT
from math import pi
import numpy as np



sql_inst = trader.SQL()
app = Flask(__name__)

#data from DB
portfolio = sql_inst.fetch_all("portfolio")   
trade_ideas = sql_inst.fetch_all("discord_trade_ideas")
records = sql_inst.fetch_all("records")



@app.route("/", methods=["GET"])
@app.route("/home", methods=["GET"])
def home():
    return render_template('index.html.j2',page = '/home')

@app.route("/<stock>", methods=["GET"])
def stock_data(stock):
    return stock


@app.route("/portfolio")
def portfolio_fun():
    df = pd.DataFrame(MSFT)[:50]
    df["date"] = pd.to_datetime(df["date"])

    inc = df.close > df.open
    dec = df.open > df.close
    w = 12*60*60*1000 # half day in ms

    TOOLS = "pan,wheel_zoom,box_zoom,reset,save"

    p = figure(x_axis_type="datetime", tools=TOOLS, plot_width=1000, title = "MSFT Candlestick")
    p.xaxis.major_label_orientation = pi/4
    p.grid.grid_line_alpha=0.3

    p.segment(df.date, df.high, df.date, df.low, color="black")
    p.vbar(df.date[inc], w, df.open[inc], df.close[inc], fill_color="#D5E1DD", line_color="black")
    p.vbar(df.date[dec], w, df.open[dec], df.close[dec], fill_color="#F2583E", line_color="black")
    show(p)


    kwargs = {'script': script, 'div': div}
    kwargs['title'] = 'bokeh-with-flask' 

    df_portfolio = portfolio.style.highlight_max(axis=0, subset=['avg_buy']).render()
    

    return render_template("df.html.j2", length=portfolio.shape[1], dataframe=df_portfolio,page = '/portfolio', **kwargs)

@app.route("/ideas")
def ideas_fun():
    return render_template("df.html.j2", length=trade_ideas.shape[1], dataframe=trade_ideas.to_html())

@app.route("/records")
def records_fun():
    return render_template("df.html.j2", length=records.shape[1], dataframe=records.to_html())

@app.route("/dfcustom")
def dfcustom():
    data = portfolio.to_dict(orient="records")
    headers = portfolio.columns
    print(headers)
    return render_template("dfcustom.html.j2", data=data, headers=headers)



def datetime(x):
    return np.array(x, dtype=np.datetime64)


# @app.route("/bokehplot")
# def bokehplot():
#     figure = make_plot()
#     fig_script, fig_div = components(figure)
#     return render_template(
#         "bokeh.html.j2",
#         fig_script=fig_script,
#         fig_div=fig_div,
#         bkversion=bokeh.__version__,
#     )

if __name__ == '__main__':
    app.run(debug=True)


def plot_stock(stock):
    p1 = figure(x_axis_type="datetime", title="Stock Closing Prices")
    p1.grid.grid_line_alpha=0.3
    p1.xaxis.axis_label = 'Date'
    p1.yaxis.axis_label = 'Price'
    p1.line(x=datetime(AAPL['date']), y=AAPL['adj_close'], color='#A6CEE3', legend_label='AAPL')
    p1.legend.location = "top_left"

    aapl = np.array(AAPL['adj_close'])
    print(AAPL['adj_close'])
    print(datetime(AAPL['date']))
    aapl_dates = np.array(AAPL['date'], dtype=np.datetime64)

    window_size = 30
    window = np.ones(window_size)/float(window_size)
    aapl_avg = np.convolve(aapl, window, 'same')

    p2 = figure(x_axis_type="datetime", title="AAPL One-Month Average")
    p2.grid.grid_line_alpha = 0
    p2.xaxis.axis_label = 'Date'
    p2.yaxis.axis_label = 'Price'
    p2.ygrid.band_fill_color = "olive"
    p2.ygrid.band_fill_alpha = 0.1

    p2.circle(x=aapl_dates, y=aapl, size=4, legend_label='close',
            color='darkgrey', alpha=0.2)

    p2.line(x=aapl_dates, y=aapl_avg, legend_label='avg', color='navy')
    p2.legend.location = "top_left"

    output_file("stocks.html", title="stocks.py example")

    show(gridplot(children = [[p1,p2]], plot_width=400, plot_height=400))  # open a browser