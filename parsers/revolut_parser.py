import pandas as pd

def parse(file):

    df = pd.read_csv(file)

    if "State" in df.columns:
        df = df[df["State"] == "COMPLETED"]

    df["Amount"] = df["Amount"].astype(float)

    return df