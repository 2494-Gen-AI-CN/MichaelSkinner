import pandas as pd
import numpy as np
# import matplotlib.pyplot as plt

def load_data(file_path):
    """Load data from a CSV file."""
    try:
        data = pd.read_csv(file_path)
        return data
    except FileNotFoundError:
        print(f"File not found: {file_path}")
        return None
    except pd.errors.EmptyDataError:
        print(f"No data: {file_path} is empty.")
        return None
    except pd.errors.ParserError:
        print(f"Parsing error: Could not parse {file_path}.")
        return None

def clean_data(df):
    """Clean the DataFrame by handling missing values and duplicates."""
    if df is not None:
        df = df.drop_duplicates()
    return df
df = load_data('college_majors_2026.csv')
df = clean_data(df)
print(df.columns if df is not None else "No data to display.")
print(df['credential_name'].unique() if df is not None else "No data to display.")

# print(df['cip_family_title'].value_counts() if df is not None else "No data to display.")
print(df['cip_title'].value_counts() if df is not None else "No data to display.")