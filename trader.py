import requests
import json
import pandas as pd
import re
from sqlalchemy import create_engine
import sqlalchemy
import maya
import yfinance as yf
from datetime import datetime
from datetime import time
import psycopg2
import warnings
import schedule



def get_messages(channel_id):
    '''
    Gets a json of trade ideas from stock discord channel
    
    '''
    headers = {'authorization': 'MTM1NzI0Mjg3OTA1NDk3MDg4.YFyz4g.fsP2iLpU6GcFjZ34PjAkOd8wqas'}
    r = requests.get(f"https://discord.com/api/v8/channels/{channel_id}/messages", headers = headers)
    js = json.loads(r.text)

    return [[val['content'].split('\n'),val['edited_timestamp']] for val in js]

#example
#stock = ['**AAPL Support Levels @here**', '$125, $123, $121, $119', '', '**AAPL Price Targets**', '$125, $127, $130, $132.75', '', '**Stop out if AAPL c..es BELOW**', '$116']

def message_parser(stock):
    '''
    Json contains rows of price levels, which are parsed into Support, Price targes, and Stop-Outs    
    '''
    regex = re.compile(r'(?:\$)(\d+(\.\d+)?)')
    for i in range(len(stock)):
        if 'Support' in stock[i] or 'support' in stock[i]:
            ticker = re.search(r'[*][*][A-Z]+',stock[i]).group(0)
            ticker = ticker.replace('**','')
            for j in stock[i:]:
                if re.match(r'[$]',j):
                    sup = [x.group(1) for x in regex.finditer(j)]
                    dfSup = pd.DataFrame([ticker,price,'support'] for price in sup)
                    dfSup.columns = ['ticker','price','type' ]
                    break
        if 'Targets' in stock[i]:
            for j in stock[i:]:
                if re.match(r'[$]',j):                   
                    pt = [x.group(1) for x in regex.finditer(j)]
                    dfpt = pd.DataFrame([ticker,price,'pt'] for price in pt)
                    dfpt.columns = ['ticker','price','type' ]
                    break
        if 'Stop out' in stock[i]:
            for j in stock[i:]:
                if re.match(r'[$]',j):
                    stop = [x.group(1) for x in regex.finditer(j)]
                    dfStop = pd.DataFrame([[ticker,stop[0],'support']],columns = ['ticker','price','type'])                
                    break
    try:         
        df_full = pd.concat([dfSup,dfpt,dfStop],ignore_index=True)
        return df_full
    except:
        return
   

class SQL:
    '''
    Every SQL operation featured in this class
    '''

    def __init__(self):
        self.sql_create_trade_ideas = """ CREATE TABLE IF NOT EXISTS discord_trade_ideas (
                        ticker VARCHAR(10) NOT NULL, 
                        price FLOAT,
                        type TEXT,
                        edited timestamp,
                        activated BOOL) """

        self.sql_create_portfolio= """ CREATE TABLE IF NOT EXISTS portfolio (
                                ticker VARCHAR(10) PRIMARY KEY, 
                                owned INT,
                                avg_buy FLOAT,
                                hourly_state FLOAT) """

        self.sql_create_records= """ CREATE TABLE IF NOT EXISTS records (
                            ticker VARCHAR(10) NOT NULL, 
                            ammount INT,
                            price FLOAT,
                            date timestamp) """

        self.connection = psycopg2.connect("dbname='stock_project' user='postgres' host='localhost' password='1234'")
        self.connection.autocommit = True 
        self.engine = create_engine('postgresql://postgres:1234@localhost:5432/stock_project')
        self.cursor = self.connection.cursor()

        for sql_statement in [self.sql_create_trade_ideas, self.sql_create_portfolio, self.sql_create_records]:
            print(sql_statement)
            self.cursor.execute(sql_statement)

    def fetch_all(self,table):
        '''
        Get full table from DB     
        '''
        q = (f"select * from {table}")
        df = pd.read_sql_query(q,self.connection)
        return df
    def activate_level(self,ticker,price_type, price,status):
        self.cursor.execute(f"UPDATE discord_trade_ideas SET activated = {status} WHERE (ticker = '{ticker}' and type = '{price_type}' and price = '{price}')")
    def update_portfolio(self,ticker,owned,avg_buy,state):
        self.cursor.execute(f"UPDATE portfolio SET owned = {owned},hourly_state = {state}, avg_buy = {avg_buy} WHERE ticker = '{ticker}'")
    def write_trade_idea(self,row):
        self.cursor.execute("INSERT INTO discord_trade_ideas (ticker, price, type, edited, activated) VALUES (%s, %s, %s, %s, %s)", (row['ticker'], row['price'], row['type'], row['edited'], row['activated']))
    def write_portfolio(self,row):
        self.cursor.execute("INSERT INTO portfolio (ticker, owned, avg_buy, hourly_state) VALUES (%s, %s, %s, %s)", (row[0], row[1], row[2], row[3]))
    def write_record(self,row):
        self.cursor.execute("INSERT INTO records (ticker, ammount, price, date) VALUES (%s, %s, %s, %s)", (row[0], row[1], row[2], row[3]))


class Trader():
    def __init__(self, trade_ideas, portfolio,sql_inst):
        self.trade_ideas = trade_ideas
        self.portfolio = portfolio
        self.sql_inst = sql_inst

    def check_trade(self,ticker):
        #necessary data
        data = yf.download(tickers = ticker, period = '1d',interval = '1h')
        supports = self.trade_ideas.loc[(self.trade_ideas['type'] != 'pt') & (self.trade_ideas['ticker'] == ticker)].sort_values(by = 'price').reset_index()
        pts = self.trade_ideas.loc[(self.trade_ideas['type'] == 'pt') & (self.trade_ideas['ticker'] == ticker)].sort_values(by = 'price',ascending = False).reset_index() # FROM HIGHEST
        last_hour = data.iloc[len(data)-2]
        latestOpen = data.iloc[len(data)-1]['Open']    
        owned = self.portfolio.loc[self.portfolio['ticker'] == ticker,'owned'].iloc[0]
        avg_buy = self.portfolio.loc[self.portfolio['ticker'] == ticker,'avg_buy'].iloc[0]

        #check levels we are dealing with
        print(supports)
        print(pts)
        print(round(last_hour,2))
        print(latestOpen)

        cash_value = self.portfolio.loc[self.portfolio['ticker'] == 'cash','hourly_state'].iloc[0]
        #check if the lowest support (stop-out) has been broken
        #sell this stock
        if(last_hour['Close']<supports.iloc[0]['price'] and owned>0):
            state = avg_buy*owned-latestOpen*owned
            self.sql_inst.update_portfolio(ticker,0,avg_buy,state)
            self.sql_inst.update_portfolio('cash',0,0,cash_value+latestOpen*owned)
            #reset all trade idea levels for this ticker
            for row in pts:
                self.sql_inst.activate_level(row['ticker'],row['type'],row['price'],False)
            for row in supports:
                self.sql_inst.activate_level(row['ticker'],row['type'],row['price'],False)                
            return [ticker,-owned,latestOpen,datetime.now()]

        #bounce of some level (support) - buy
        if (last_hour['Open']>last_hour['Low'] and last_hour['Close']>last_hour['Low']):
            i = 0
            curr_lvl = pd.Series([])
            #find the support which held
            for i, row in supports.iterrows():
                if(i+1 == len(supports.index)): #no other upper bound
                    if((supports.iloc[i]['price']<latestOpen)):
                        curr_lvl = supports.iloc[i]
                elif( supports.iloc[i+1]['price']>latestOpen and supports.iloc[i]['price']<latestOpen): #price between the two supports
                    curr_lvl = supports.iloc[i]
                    break                   

            # check if the level which the price action bounced of was actually the defined support
            #current price is very close to our support but hourly close is above the support -> buy
            if (len(curr_lvl) == 0):
                return None
            if ((last_hour['Low']+0.1>=curr_lvl['price']) and (last_hour['Low'] - curr_lvl['price']<0.5)  and last_hour['Close']>=curr_lvl['price']): 
                if(supports.loc[supports['price'] == curr_lvl['price'],'activated'].iloc[0] == False): 
                    supports.loc[supports['price'] == curr_lvl['price'],'activated'] = True
                    self.sql_inst.activate_level(ticker,curr_lvl['type'],curr_lvl['price'],True)

                    #purchase proportionaly to the level, higher iterations represent lowe support
                    purchase = (len(supports)-i)*2
                    avg_buy = (avg_buy*owned + purchase*latestOpen)/(owned+purchase)
                    owned += purchase
                    state = avg_buy*owned-latestOpen*owned                
                    self.sql_inst.update_portfolio(ticker,owned,avg_buy,state)
                    self.sql_inst.update_portfolio('cash',0,0,cash_value-latestOpen*purchase)
                    return [ticker,purchase,latestOpen,datetime.now()]

        #price climbed up -> might have hit a price target -> sell some    
        elif(last_hour['Open']<last_hour['Close'] and owned >0):
            i = 0
            for i, row in pts.iterrows():
                if(pts.loc[pts['price'] == row['price'],'activated'].iloc[0] is False):
                    if((pts.iloc[i]['price'] - last_hour['Close']< 0.5) or last_hour['Close']>pts.iloc[i]['price']): #very close to price target or above
                        
                        if (i == 0): # highest price target -> sell all
                            state = avg_buy,avg_buy*owned-latestOpen*owned
                            self.sql_inst.update_portfolio(ticker,0,avg_buy,state)                               
                            self.sql_inst.update_portfolio('cash',0,0,cash_value-latestOpen*owned)
                            
                            #reset all trade idea levels for this ticker
                            for row in pts:
                                self.sql_inst.activate_level(row['ticker'],row['type'],row['price'],False)
                            for row in supports:
                                self.sql_inst.activate_level(row['ticker'],row['type'],row['price'],False)  

                            return [ticker,-owned,latestOpen,datetime.now()]

                        else: #sell proportional
                            pts.loc[pts['price'] == row['price'],'activated'] = True
                            self.sql_inst.activate_level(row['ticker'],row['type'],row['price'],True)                            
                            if (owned*i/len(pts.index)>0):
                                sell = owned*i/len(pts.index)
                            else:
                                sell = owned
                            state = avg_buy*owned-latestOpen*owned
                            self.sql_inst.update_portfolio('cash',0,0,cash_value+latestOpen*sell)                            
                            self.sql_inst.update_portfolio(ticker,owned-sell,avg_buy,state) 
                            return [ticker,-sell,latestOpen,datetime.now()]         
        return None

def hourly_update():
    sql_inst = SQL()
    all_trades = sql_inst.fetch_all('discord_trade_ideas')
    #check if cash value has already been defined
    if (len(sql_inst.fetch_all('portfolio')) == 0):
        sql_inst.write_portfolio(['cash',0,0,10000])
    portfolio = sql_inst.fetch_all('portfolio')
    tr = Trader(all_trades,portfolio,sql_inst)

    for i in all_trades['ticker'].unique():
        #adding new ticker
        if(i not in tr.portfolio['ticker']):
            sql_inst.write_portfolio([i,0,0,0])
            tr.portfolio = tr.portfolio.append({'ticker': i, 'owned': 0, 'avg_buy': 0, 'hourly_state': 0}, ignore_index = True)
            print(tr.portfolio )
        curr_trade = tr.check_trade(i)
        if curr_trade is not None:
            #update records with new trade              
            sql_inst.write_record(curr_trade)
def main():
    if False:
        sql_inst = SQL()
        stock_ideas =  '814856374663249971'
        all_ideas = []
        mess = get_messages(stock_ideas)
        #create dataframe of all trade ideas
        for stock in mess:
            price_data = message_parser(stock[0])
            if(price_data is not None):
                if(stock[1] != None):
                    date_time_obj = maya.parse(stock[1]).datetime()
                    price_data['edited'] = date_time_obj
                else:
                    price_data['edited'] = None
                all_ideas.append(price_data)

        df_full = pd.concat(all_ideas,ignore_index=True)
        df_full.drop_duplicates(subset = ['ticker','price','type'],inplace=True)
        df_full['activated'] = False
        for index, row in df_full.iterrows():
            sql_inst.write_trade_idea(row)

    hourly_update()
    # warnings.simplefilter(action='ignore', category=FutureWarning)
    # if (datetime.now().time() >= time(15,31,00)):
    #     hourly_update()

    # schedule.every().hour.do(hourly_update)
    # while (datetime.now().time() >= time(15,31,00) and datetime.now().time() <= time(21,35,00)):
    #     schedule.run_pending()



if __name__ == "__main__":
    main()
