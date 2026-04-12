import sqlite3

DB_PATH = "../ezbookkeeping/data/ezbookkeeping.db"

def insert_transaction(tx):

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("""
    INSERT INTO transaction
    (description, amount, category)
    VALUES (?, ?, ?)
    """, (tx["description"], tx["amount"], tx["category"]))

    conn.commit()
    conn.close()