import pandas as pd
import re
from sqlalchemy import create_engine
import yfinance as yf
import datetime as dt
import time
import psycopg2
import schedule

PSYCOPG2_CONNECTION = "dbname='stock_project' user='postgres' host='localhost' password='1234'"
ENGINE_CONNECTION = 'postgresql://postgres:1234@localhost:5432/stock_project'
FIRST_USE = False



def message_parser(ideas):
    '''
    Json contains rows of price levels, which are parsed into Support, Price targes, and Stop-Outs    
    '''
    df_full = pd.DataFrame(columns=['ticker','price','type' ])
    regex = re.compile(r'(?:\$)(\d+(\.\d+)?)') #match prices
    for i in range(len(ideas)):
        print(ideas[i])
        if 'Support' in ideas[i] or 'support' in ideas[i]:
            ticker = re.search(r'[*][*][A-Z]+',ideas[i]).group(0)
            ticker = ticker.replace('**','')
            if re.match(r'[$]',ideas[i+1]):
                sup = [x.group(1) for x in regex.finditer(ideas[i+1])]
                dfSup = pd.DataFrame([ticker,price,'support'] for price in sup)
                dfSup.columns = ['ticker','price','type' ]
                df_full = df_full.append(dfSup)

        if 'Targets' in ideas[i]:
            ticker = re.search(r'[*][*][A-Z]+',ideas[i]).group(0)
            ticker = ticker.replace('**','')
            if re.match(r'[$]',ideas[i+1]):                   
                pt = [x.group(1) for x in regex.finditer(ideas[i+1])]
                dfpt = pd.DataFrame([ticker,price,'pt'] for price in pt)
                dfpt.columns = ['ticker','price','type' ]
                df_full = df_full.append(dfpt)

        if 'Stop out' in ideas[i]:
            ticker = re.search(r'[Stop out if][A-Z]+',ideas[i]).group(0)
            ticker = ticker.replace(' ','')
            if re.match(r'[$]',ideas[i+1]):
                stop = [x.group(1) for x in regex.finditer(ideas[i+1])]
                dfStop = pd.DataFrame([[ticker,stop[0],'stop']],columns = ['ticker','price','type'])                
                df_full = df_full.append(dfStop)

    return df_full
   

class SQL:
    '''
    Every SQL operation featured in this class
    '''

    def __init__(self):
        self.sql_create_trade_ideas = """ CREATE TABLE IF NOT EXISTS trade_ideas (
                        ticker VARCHAR(10) NOT NULL, 
                        price FLOAT,
                        type TEXT,
                        activated BOOL) """

        self.sql_create_portfolio= """ CREATE TABLE IF NOT EXISTS portfolio (
                                ticker VARCHAR(10) PRIMARY KEY, 
                                owned INT,
                                avg_buy FLOAT(3),
                                last_hour FLOAT(3),
                                hourly_state FLOAT(3)) """

        self.sql_create_records= """ CREATE TABLE IF NOT EXISTS records (
                            ticker VARCHAR(10) NOT NULL, 
                            ammount INT,
                            price FLOAT(3),
                            date timestamp(0)) """
        self.create_tables()

    def create_tables(self):
        self.connection = psycopg2.connect(PSYCOPG2_CONNECTION)
        self.connection.autocommit = True 
        self.engine = create_engine(ENGINE_CONNECTION)
        self.cursor = self.connection.cursor()

        for sql_statement in [self.sql_create_trade_ideas, self.sql_create_portfolio, self.sql_create_records]:
            print(sql_statement)
            self.cursor.execute(sql_statement)


    def reset_tables(self):
        self.cursor.execute(f"delete from trade_ideas")
        self.cursor.execute(f"delete from portfolio")
        self.cursor.execute(f"delete from records")
        self.create_tables()



    def fetch_all(self,table):
        '''
        Get full table from DB     
        '''
        q = (f"select * from {table}")
        df = pd.read_sql_query(q,self.connection)
        return df
    def activate_level(self,ticker,price_type, price,status):
        self.cursor.execute(f"UPDATE trade_ideas SET activated = {status} WHERE (ticker = '{ticker}' and type = '{price_type}' and price = '{price}')")
    def update_portfolio(self,ticker,owned,avg_buy,last_hour,state):
        self.cursor.execute(f"UPDATE portfolio SET owned = {owned},hourly_state = {state}, avg_buy = {avg_buy}, last_hour = {last_hour} WHERE ticker = '{ticker}'")
    def write_trade_idea(self,row):
        self.cursor.execute("INSERT INTO trade_ideas (ticker, price, type, activated) VALUES (%s, %s, %s, %s)", (row['ticker'], row['price'], row['type'], row['activated']))
    def write_portfolio(self,row):
        self.cursor.execute("INSERT INTO portfolio (ticker, owned, avg_buy, hourly_state) VALUES (%s, %s, %s, %s)", (row[0], row[1], row[2], row[3]))
    def write_record(self,row):
        self.cursor.execute("INSERT INTO records (ticker, ammount, price, date) VALUES (%s, %s, %s, %s)", (row[0], row[1], row[2], row[3]))


class Trader():
    def __init__(self, trade_ideas,sql_inst):
        self.trade_ideas = trade_ideas
        self.sql_inst = sql_inst
        self.portfolio = sql_inst.fetch_all('portfolio')
        self.cash_value = self.portfolio.loc[self.portfolio['ticker'] == 'cash','hourly_state'].iloc[0]


    #close trade if we are below the stop out on the daily close
    def check_daily_close(self,ticker):
        #necessary data
        data = yf.download(tickers = ticker, period = '1d',interval = '1h')
        stop = self.trade_ideas.loc[(self.trade_ideas['type'] == 'stop') & (self.trade_ideas['ticker'] == ticker)].sort_values(by = 'price').reset_index()
        supports = self.trade_ideas.loc[(self.trade_ideas['type'] != 'pt') & (self.trade_ideas['ticker'] == ticker)].sort_values(by = 'price').reset_index()
        pts = self.trade_ideas.loc[(self.trade_ideas['type'] == 'pt') & (self.trade_ideas['ticker'] == ticker)].sort_values(by = 'price',ascending = False).reset_index() # FROM HIGHEST
        latestOpen = data.iloc[len(data)-1]['Low']    
        owned = self.portfolio.loc[self.portfolio['ticker'] == ticker,'owned'].iloc[0]
        avg_buy = self.portfolio.loc[self.portfolio['ticker'] == ticker,'avg_buy'].iloc[0] 

        if(latestOpen+1<stop.iloc[0]['price'] and owned>0):
            state = latestOpen*owned-avg_buy*owned
            self.sql_inst.update_portfolio(ticker,0,avg_buy,latestOpen,state)
            self.cash_value = self.cash_value+latestOpen*owned
            self.sql_inst.update_portfolio('cash',0,0,latestOpen,self.cash_value)
            #reset all trade idea levels for this ticker
            for i, row in pts.iterrows():
                self.sql_inst.activate_level(row['ticker'],row['type'],row['price'],False)
            for i, row in supports.iterrows():
                self.sql_inst.activate_level(row['ticker'],row['type'],row['price'],False)                
            return [ticker,-owned,latestOpen,dt.datetime.now()]
        return None
             

    def check_trade(self,ticker):
        #necessary data
        data = yf.download(tickers = ticker, period = '1d',interval = '1h')
        supports = self.trade_ideas.loc[(self.trade_ideas['type'] == 'support') & (self.trade_ideas['ticker'] == ticker)].sort_values(by = 'price').reset_index()
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
        #check if the lowest support (stop-out) has been broken
        #sell this stock
        if(last_hour['Close']<supports.iloc[0]['price'] and owned>0):
            state = latestOpen*owned-avg_buy*owned
            self.sql_inst.update_portfolio(ticker,0,avg_buy,latestOpen,state)
            self.cash_value = self.cash_value+latestOpen*owned
            self.sql_inst.update_portfolio('cash',0,0,latestOpen,self.cash_value)
            #reset all trade idea levels for this ticker
            for i, row in pts.iterrows():
                self.sql_inst.activate_level(row['ticker'],row['type'],row['price'],False)
            for i, row in supports.iterrows():
                self.sql_inst.activate_level(row['ticker'],row['type'],row['price'],False)    
            print([ticker,-owned,latestOpen,dt.datetime.now()])            
            return [ticker,-owned,latestOpen,dt.datetime.now()]

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
            if ((len(curr_lvl) != 0) and (last_hour['Low']+0.1>=curr_lvl['price']) and (last_hour['Low'] - curr_lvl['price']<0.5)  and last_hour['Close']>=curr_lvl['price']): 
                if(supports.loc[supports['price'] == curr_lvl['price'],'activated'].iloc[0] == False): 
                    supports.loc[supports['price'] == curr_lvl['price'],'activated'] = True
                    self.sql_inst.activate_level(ticker,curr_lvl['type'],curr_lvl['price'],True)

                    #purchase proportionaly to the level, higher iterations represent lowe support
                    purchase = (len(supports)-i)*2
                    avg_buy = (avg_buy*owned + purchase*latestOpen)/(owned+purchase)
                    owned += purchase
                    state = latestOpen*owned-avg_buy*owned              
                    self.sql_inst.update_portfolio(ticker,owned,avg_buy,latestOpen,state)
                    self.cash_value = self.cash_value-latestOpen*purchase
                    self.sql_inst.update_portfolio('cash',0,0,latestOpen,self.cash_value)
                    print([ticker,purchase,latestOpen,dt.datetime.now()])
                    return [ticker,purchase,latestOpen,dt.datetime.now()]

        #price climbed up -> might have hit a price target -> sell some    
        elif(last_hour['Open']<last_hour['Close'] and owned >0):
            i = 0
            for i, row in pts.iterrows():
                if(pts.loc[pts['price'] == row['price'],'activated'].iloc[0] is False):
                    if((pts.iloc[i]['price'] - last_hour['Close']< 0.5) or last_hour['Close']>pts.iloc[i]['price']): #very close to price target or above
                        
                        if (i == 0): # highest price target -> sell all
                            state = latestOpen*owned-avg_buy*owned
                            self.sql_inst.update_portfolio(ticker,0,avg_buy,latestOpen,state)   
                            self.cash_value = self.cash_value-latestOpen*owned                         
                            self.sql_inst.update_portfolio('cash',0,0,latestOpen,self.cash_value)
                            
                            #reset all trade idea levels for this ticker
                            for i, row in pts.iterrows():
                                self.sql_inst.activate_level(row['ticker'],row['type'],row['price'],False)
                            for i, row in supports.iterrows():
                                self.sql_inst.activate_level(row['ticker'],row['type'],row['price'],False)  
                            print([ticker,-owned,latestOpen,dt.datetime.now()])
                            return [ticker,-owned,latestOpen,dt.datetime.now()]

                        else: #sell proportional
                            pts.loc[pts['price'] == row['price'],'activated'] = True
                            self.sql_inst.activate_level(row['ticker'],row['type'],row['price'],True)                            
                            if (owned*i/len(pts.index)>0):
                                sell = owned*i/len(pts.index)
                            else:
                                sell = owned
                            state = latestOpen*owned-avg_buy*owned
                            self.cash_value = self.cash_value+latestOpen*sell
                            self.sql_inst.update_portfolio('cash',0,0,latestOpen,self.cash_value)                            
                            self.sql_inst.update_portfolio(ticker,owned-sell,avg_buy,latestOpen,state) 
                            print([ticker,-sell,latestOpen,dt.datetime.now()])
                            return [ticker,-sell,latestOpen,dt.datetime.now()]

        #no new trade, just update hourly state
        if (owned>0):
            state = latestOpen*owned-avg_buy*owned
        else:
            state = self.portfolio.loc[self.portfolio['ticker'] == ticker,'hourly_state'].iloc[0]
        self.sql_inst.update_portfolio(ticker,owned,avg_buy,latestOpen,state)   
        print([ticker,owned,avg_buy,latestOpen,state])      
        return None

def check_close():
    sql_inst = SQL()
    all_ideas = sql_inst.fetch_all('trade_ideas')
    portfolio = sql_inst.fetch_all('portfolio')
    tr = Trader(all_ideas,sql_inst)
    for i in all_ideas['ticker'].unique():
        curr_trade = tr.check_daily_close(i)
        if curr_trade is not None:
            #update records with new trade   
            try:   
                curr_trade[1].values.astype(int)  
            except:
                curr_trade[1] = curr_trade[1]           
            sql_inst.write_record(curr_trade)
   
def hourly_update():
    sql_inst = SQL()
    all_ideas = sql_inst.fetch_all('trade_ideas')
    #check if cash value has already been defined
    if (len(sql_inst.fetch_all('portfolio')) == 0):
        sql_inst.write_portfolio(['cash',0,0,100000])
    portfolio = sql_inst.fetch_all('portfolio')
    tr = Trader(all_ideas,sql_inst)

    print(all_ideas['ticker'].unique())
    for i in all_ideas['ticker'].unique():
        #adding new ticker
        if(i not in portfolio['ticker'].values):
            sql_inst.write_portfolio([i,0,0,0])
            new_row = {'ticker':i,'owned':0,'avg_buy':0,'last_hour  ':0,'hourly_state': 0}
            tr.portfolio = tr.portfolio.append(new_row, ignore_index = True)
        curr_trade = tr.check_trade(i)
        if curr_trade is not None:
            #update records with new trade  
            try:   
                curr_trade[1].values.astype(int)  
            except:
                curr_trade[1] = curr_trade[1]
            sql_inst.write_record(curr_trade)


def redo_ideas():
    sql_inst = SQL()
    sql_inst.reset_tables()
    f = open("ideas.txt", "r")
    stock_ideas = f.read().splitlines()
    df_full = message_parser(stock_ideas)
    df_full['activated'] = False
    for index, row in df_full.iterrows():
        sql_inst.write_trade_idea(row)

def main():
    if FIRST_USE:  
        redo_ideas()
    #start hourly trading
    while True:
        if (dt.datetime.now().time() >=dt.time(16,31)):
            hourly_update()
            break
        time.sleep(10)
    schedule.every().hour.do(hourly_update)
    #stop at 21:55
    while(dt.datetime.now().time() <= dt.time(21,55)):
        schedule.run_pending()
        time.sleep(10)

    #check closes below stop-outs
    while True:
        if (dt.datetime.now().time() >=dt.time(21,8)):
            check_close()
            break
        time.sleep(10)


if __name__ == "__main__":
    main()
