import trader
import yfinance as yf
from flask import Flask, render_template
import pandas as pd
from bokeh.plotting import figure
from bokeh.embed import components
from bokeh.models import ColumnDataSource, HoverTool, NumeralTickFormatter, Span
import numpy as np


sql_inst = trader.SQL()
app = Flask(__name__)

#data from DB
portfolio = sql_inst.fetch_all("portfolio")   
trade_ideas = sql_inst.fetch_all("trade_ideas")
records = sql_inst.fetch_all("records")
portfolio = portfolio.round(3)
trade_ideas = trade_ideas.round(3)
records = records.round(3)

@app.route("/")
@app.route("/home")
def home():
    return render_template('index.html.j2',page = '/home')

@app.route("/portfolio/<stock_name>")
def stock_data(stock_name):
    records_stock = records.loc[records.ticker == stock_name]
    ideas_stock = trade_ideas.loc[trade_ideas.ticker == stock_name]
    p1 = candlestick_plot(stock_name, records_stock,ideas_stock)
    script, div = components(p1)
    return render_template("plot.html.j2",page = '/portfolio', script = script, div = div)


@app.route("/portfolio")
def portfolio_fun():
    #html_df = re.sub(' mytable', '" id="mytable', portfolio.to_html(classes='mytable'))
    final = portfolio.to_json(orient='records')
    return render_template("df.html.j2",  dataframe=final)

@app.route("/ideas")
def ideas_fun():
    final = trade_ideas.to_json(orient='records')
    return render_template("df_ideas.html.j2",  dataframe=final)

@app.route("/records")
def records_fun():
    final = records.to_json(orient='records',date_unit='ms')
    return render_template("df_records.html.j2",  dataframe=final)

def candlestick_plot(stock_name, records, levels):
    df = yf.download(stock_name,period = '1y', interval="1h", prepost = False)
    df['Date'] = df.index
    df.reset_index(drop=True, inplace=True) 
    df["Date"] = pd.to_datetime(df["Date"], format='%Y-%m-%d %H:%M:%S').dt.tz_localize(None)  # Adjust this
    df["Date"] = df["Date"] + pd.DateOffset(hours=6)
    records['date'] =  pd.to_datetime(records['date'], format = '%Y-%m-%d %H:%M:%S')
    records['df_index'] = records['date'].apply(lambda x: np.argmax(df['Date']>x))
    records.loc[records['df_index'] == 0, "df_index"] = len(df)
    print(records.df_index)
    # Select the datetime format for the x axis depending on the timeframe
    xaxis_dt_format = '%d %m %Y, %H:%M:%S'
    fig = figure(sizing_mode='stretch_both',
                 tools="xpan,xwheel_zoom,reset,save",
                 active_drag='xpan',
                 active_scroll='xwheel_zoom',
                 x_axis_type='linear',
                 #x_range=Range1d(df.index[0], df.index[-1], bounds="auto"),
                 title=stock_name
                 )              
    fig.yaxis[0].formatter = NumeralTickFormatter(format="$5.3f")
    inc = df.Close > df.Open
    dec = ~inc
    # Colour scheme for increasing and descending candles
    INCREASING_COLOR = 'green'
    DECREASING_COLOR = 'red'

    width = 0.5

    levels_source = ColumnDataSource(data=dict(
        x1=levels.index,
        price=levels.price,
        type=levels.type,
        activated=levels.activated,
    ))


    inc_source = ColumnDataSource(data=dict(
        x1=df.index[inc],
        top1=df.Open[inc],
        bottom1=df.Close[inc],
        high1=df.High[inc],
        low1=df.Low[inc],
        Date1=df.Date[inc]
    ))

    dec_source = ColumnDataSource(data=dict(
        x2=df.index[dec],
        top2=df.Open[dec],
        bottom2=df.Close[dec],
        high2=df.High[dec],
        low2=df.Low[dec],
        Date2=df.Date[dec]
    ))

    records_source = ColumnDataSource(data=dict(
        i1 = records.df_index,
        d1=records.date,
        p1 = records.price,
        a1 = records.ammount
    ))

    # Plot candles
    # High and low
    print(records['date'])
    print(df["Date"])

    fig.segment(x0='x1', y0='high1', x1='x1', y1='low1', source=inc_source, color=INCREASING_COLOR)
    fig.segment(x0='x2', y0='high2', x1='x2', y1='low2', source=dec_source, color=DECREASING_COLOR)
    lines = []
    for i,r in levels.iterrows():
        print(r)
        if(r['type'] == 'pt'):
            hline = Span(location=r['price'], dimension='width', line_color='green', line_width=1)
        elif(r['type'] == 'support'):
            hline = Span(location=r['price'], dimension='width', line_color='orange', line_width=1)
        elif(r['type'] == 'stop'):
            hline = Span(location=r['price'], dimension='width', line_color='red', line_width=1)
        lines.append(hline)
    fig.renderers.extend(lines)


    c1 = fig.circle(x = 'i1', y = 'p1', source=records_source, size=10)
    # Open and close
    r1 = fig.vbar(x='x1', width=width, top='top1', bottom='bottom1', source=inc_source,
                    fill_color=INCREASING_COLOR, line_color="black")
    r2 = fig.vbar(x='x2', width=width, top='top2', bottom='bottom2', source=dec_source,
                    fill_color=DECREASING_COLOR, line_color="black")

    # Add on extra lines (e.g. moving averages) here
    # fig.line(df.index, <your data>)

    # Add on a vertical line to indicate a trading signal here
    # vline = Span(location=df.index[-<your index>, dimension='height',
    #              line_color="green", line_width=2)
    # fig.renderers.extend([vline])

    # Add date labels to x axis
    fig.xaxis.major_label_overrides = {
        i: date.strftime(xaxis_dt_format) for i, date in enumerate(pd.to_datetime(df["Date"]))
    }

    #Set up the hover tooltip to display some useful data
    fig.add_tools(HoverTool(
        renderers=[c1],
        tooltips=[
            ("Ammount", "@a1"),
            ("Price", "$@p1"),
            ("Date", "@d1{" + xaxis_dt_format + "}"),
        ],
        formatters={
            '@d1': 'datetime',
        }))



    fig.add_tools(HoverTool(
        renderers=[r1],
        tooltips=[
            ("Open", "$@top1"),
            ("High", "$@high1"),
            ("Low", "$@low1"),
            ("Close", "$@bottom1"),
            ("Date", "@Date1{" + xaxis_dt_format + "}"),
        ],
        formatters={
            '@Date1': 'datetime',
        }))

    fig.add_tools(HoverTool(
        renderers=[r2],
        tooltips=[
            ("Open", "$@top2"),
            ("High", "$@high2"),
            ("Low", "$@low2"),
            ("Close", "$@bottom2"),
            ("Date", "@Date2{" + xaxis_dt_format + "}")
        ],
        formatters={
            '@Date2': 'datetime'
        }))
    return fig

if __name__ == '__main__':
    app.run(debug=True)