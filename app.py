import os
import trader
from flask_sqlalchemy import SQLAlchemy
from flask import Flask, render_template, url_for
from flask_bootstrap import Bootstrap
from bokeh.embed import components
import bokeh

sql_inst = trader.SQL()

app = Flask(__name__)

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
    return render_template("df.html.j2", length=portfolio.shape[1], dataframe=portfolio.to_html(),page = '/portfolio')

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