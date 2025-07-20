import sqlite3
import datetime as dt
from dateutil.relativedelta import relativedelta
import pandas as pd
import yfinance as yf

class DBManager:
    """
    將資料庫相關操作 (connect, store_stock_to_db, load_stock_from_db, metadata 管理) 
    都集中在這個類別。
    """
    def __init__(self, db_path: str):
        self.db_path = db_path
        # 建立一個 Connection (允許跨執行緒使用，需謹慎處理)
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        print(f"[DBManager] 已連線到 {self.db_path}")
        self.init_metadata_table()


    def close(self):
        if self.conn:
            self.conn.close()
            self.conn = None
            print(f"[DBManager] 關閉資料庫連線 {self.db_path}")


    def __enter__(self):
        return self   # 或回傳其他物件


    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


    def update_stock_in_db(self, stock: str):
            """
            更新数据库中指定股票的数据，确保从网络获取的数据填补到数据库中最新的日期。
            """
            # 获取数据库中指定股票的最新数据
            db_df = self.load_stock_from_db(stock, period="max")  # 获取最大范围的历史数据

            if db_df.empty:
                print(f"[DB] {stock} 数据为空，无法更新。")
                return
            
            # 获取数据库中最新的日期
            latest_db_date = db_df.index[-1].date()
            print(f"[DB] {stock} 在数据库中的最新日期: {latest_db_date}")

            # 获取从Yahoo Finance下载的最新数据，从最新日期后开始获取
            try:
                df_yf = yf.download(stock, start=latest_db_date.strftime('%Y-%m-%d'))
                
                if df_yf.empty:
                    print(f"[YF] 无法下载 {stock} 的数据。")
                    return
                
                # 清理数据，确保列名匹配
                if isinstance(df_yf.columns, pd.MultiIndex):
                    df_yf.columns = df_yf.columns.droplevel(level=1)
                
                df_yf.reset_index(inplace=True)
                df_yf['Date'] = pd.to_datetime(df_yf['Date'])
                df_yf.set_index('Date', inplace=True)

                # 检查必要的列
                required_columns = {'Open', 'High', 'Low', 'Close', 'Volume'}
                if not required_columns.issubset(df_yf.columns):
                    print(f"[YF] {stock} 的数据缺少必要的列。")
                    return
                
                latest_db_date = pd.to_datetime(latest_db_date)
                
                # 过滤出需要更新的数据
                new_data = df_yf[df_yf.index > latest_db_date]
                if not new_data.empty:
                    # 存入数据库
                    self.store_stock_to_db(stock, new_data)
                    print(f"[DB] {stock} 更新了 {len(new_data)} 条数据。")
                else:
                    print(f"[DB] {stock} 没有新的数据需要更新。")
            
            except Exception as e:
                print(f"[YF] 下载 {stock} 数据时发生错误：{e}")


    def store_stock_to_db(self, stock: str, df: pd.DataFrame):
        """
        將指定股票的 df 寫入 SQLite 資料庫 (using self.conn)。
        """
        table_name = stock.replace('.', '_')
        try:
            create_table_sql = f"""
            CREATE TABLE IF NOT EXISTS t_{table_name} (
                Date TEXT UNIQUE,
                Open REAL,
                High REAL,
                Low REAL,
                Close REAL,
                Volume REAL
            )
            """
            self.conn.execute(create_table_sql)
            self.conn.commit()
            # 再 append 新資料
            df.to_sql(f"t_{table_name}", self.conn, if_exists='append', index_label='Date')
            self.conn.commit()
            print(f"[DB] 已儲存 {stock} -> t_{table_name}")
        except Exception as e:
            self.conn.rollback()
            print(f"[DB] 儲存 {stock} 失敗：{e}")


    def load_stock_from_db(self, stock: str, period) -> pd.DataFrame:
        """
        從資料庫讀取指定股票的 DataFrame。
        若表不存在，回傳 None。
        """
        table_name = stock.replace('.', '_')
        try:
            # 解析 period，計算起始日期
            end_date = dt.datetime.now()
            if period.endswith('y'):
                years = int(period[:-1])
                start_date = end_date - relativedelta(years=years)
            elif period.endswith('m'):
                months = int(period[:-1])
                start_date = end_date - relativedelta(months=months)
            elif period.endswith('d'):
                days = int(period[:-1])
                start_date = end_date - relativedelta(days=days)
            else:
                # 預設為 1 年
                start_date = end_date - relativedelta(years=5)
            
            # 將日期轉換為字串，符合 SQL 格式
            start_date_str = start_date.strftime('%Y-%m-%d')
            end_date_str = end_date.strftime('%Y-%m-%d')
            
            # 執行 SQL 查詢，選擇日期範圍內的資料
            query = f"""
                SELECT * FROM t_{table_name}
                WHERE Date BETWEEN '{start_date_str}' AND '{end_date_str}'
                ORDER BY Date ASC
            """
            df = pd.read_sql(
                query,
                self.conn,
                parse_dates=['Date']
            ).set_index('Date', drop=False)
            df['Date'] = df.index

            if not df.empty:
                print(f"[DB] 已經有 {stock} 在 {start_date_str} 至 {end_date_str} 的資料。")
            else:
                print(f"[DB] {stock} 在 {start_date_str} 至 {end_date_str} 的資料為空。")
            return df
        except Exception as e:
            print(f"[DB] 讀取 {stock} 失敗或不存在: {e}")
            return pd.DataFrame()


    def init_metadata_table(self):
        """
        建立 metadata 表 (若不存在)，並確保其中有一筆 download_date 設為 '1970-01-01'。
        """
        c = self.conn.cursor()
        c.execute("""
            CREATE TABLE IF NOT EXISTS metadata (
                param TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        # 檢查是否已有 'download_date' 參數
        c.execute("SELECT value FROM metadata WHERE param='download_date'")
        row = c.fetchone()
        if not row:
            c.execute("INSERT INTO metadata (param, value) VALUES (?, ?)",
                      ("download_date", "1970-01-01"))
            self.conn.commit()
            print("[DB] 初始化 metadata 表，設置 download_date 為 '1970-01-01'。")


    def has_downloaded_today(self) -> bool:
        """
        檢查 metadata 表中的 download_date 是否等於今天 (YYYY-MM-DD)。
        """
        c = self.conn.cursor()
        c.execute("SELECT value FROM metadata WHERE param='download_date'")
        row = c.fetchone()
        if not row:
            return False
        last_date_str = row[0]
        last_date = dt.datetime.strptime(last_date_str, "%Y-%m-%d").date()
        today = dt.datetime.now().date()
        return (last_date == today)


    def set_downloaded_today(self):
        """
        將 metadata 表中的 download_date 更新為今天。
        """
        today_str = dt.datetime.now().strftime("%Y-%m-%d")
        c = self.conn.cursor()
        c.execute("""
            INSERT OR REPLACE INTO metadata (param, value)
            VALUES ('download_date', ?)
        """, (today_str,))
        self.conn.commit()
        print(f"[DB] 更新 download_date 為 {today_str}。")


    def get_stock(self, stock: str, period: str) -> pd.DataFrame:
        """
        獲取指定股票的資料。
        如果資料庫中沒有該股票的資料，則從 yfinance 下載，存入資料庫，並返回 DataFrame。
        """

        df = self.load_stock_from_db(stock, period)
        if df is not None and not df.empty:
            # print(f"[DB] 已經有 {stock} 的資料。")
            return df
        else:
            # 資料庫中沒有該股票，從 yfinance 下載
            print(f"[YF] 下載 {stock} 最新資料 {period}...")
            try:
                df_yf = yf.download(stock, period=period)
                
                # 壓平多重欄位 (若是 MultiIndex)
                if isinstance(df_yf.columns, pd.MultiIndex):
                    df_yf.columns = df_yf.columns.droplevel(level=1)
                
                df_yf.reset_index(inplace=True)
                df_yf['Date'] = pd.to_datetime(df_yf['Date'])
                df_yf.set_index('Date', inplace=True)

                if df_yf.empty:
                    print(f"[YF] 無法下載 {stock} 的資料。")
                    return pd.DataFrame()  # 回傳空的 DataFrame

                # 檢查必要欄位
                required_columns = {'Open', 'High', 'Low', 'Close', 'Volume'}
                if not required_columns.issubset(df_yf.columns):
                    print(f"[YF] {stock} 的資料缺少必要欄位。")
                    return pd.DataFrame()

                # 存入資料庫
                self.store_stock_to_db(stock, df_yf)
                print(f"[YF] {stock} 的資料已下載並存入資料庫。")
                return df_yf
            except Exception as e:
                print(f"[YF] 下載 {stock} 資料時發生錯誤：{e}")
                return pd.DataFrame()
            

    def list_stocks(self):
        """
        列出資料庫中目前已儲存的所有股票代碼（根據資料表名開頭 t_ 推斷）。
        例如：資料表 t_GOOG 對應股票 GOOG。
        """
        try:
            c = self.conn.cursor()
            c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 't_%'")
            rows = c.fetchall()
            stocks = [row[0][2:].replace('_', '.') for row in rows]  # 移除前綴 't_'，還原成股票代碼
            # print(f"[DB] 資料庫目前有以下股票：{stocks}")
            return stocks
        except Exception as e:
            print(f"[DB] 無法列出股票清單：{e}")
            return []
        
        