import pandas as pd

def get_equip_format(xl_path: str, row: int):
    df = pd.read_excel(xl_path)
    if row < 2 or row > len(df):
        raise ValueError("Row index out of bounds. Please provide a valid row index.")
    equipment_data = df.iloc[row - 2].to_dict()
    print(equipment_data)