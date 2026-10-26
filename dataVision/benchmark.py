"""
in this file we will be answering different questions about the data in the college_majors_2026.csv file.
Which programs outperform their national benchmark?

Columns: cip_title, institution_name, earnings_vs_national_pct (filter with earnings_cohort_size_4yr >= 30)
Chart: Horizontal bar chart centered at zero, showing the top and bottom programs

2. Do higher-paying programs connect to growing occupations?

Columns: median_earnings_4yr_usd, occupation_growth_pct_2024_34, cip_family_title
Chart: Scatter plot

3. How many of these programs lead to jobs that use AI tools, and how does that line up with job growth?

Columns: ai_software_occupation_share, occupation_growth_pct_2024_34, cip_family_title
Chart: Quadrant scatter plot (AI-augmented / worth watching / low AI + growing / low AI + shrinking)
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import textwrap

def get_national_bench(df):
    
   """
   Return the Dataframe slice that contains our necessary fields
   """
   df = df[~df['institution_state'].isin(['PR', 'GU', 'VI', 'AS', 'MP'])]
   return df.loc[df['earnings_cohort_size_4yr'] >= 30 ,['cip_title', 'institution_name', 'earnings_vs_national_pct']].dropna().sort_values('earnings_vs_national_pct')

def get_growing_occupation(df):
   return df.loc[:, ['median_earnings_4yr_usd', 'occupation_growth_pct_2024_34', 'cip_family_title']].dropna()

def get_ai_job_growth(df):
   return df.loc[:, ['ai_software_occupation_share', 'occupation_growth_pct_2024_34', 'cip_family_title']].dropna()


def get_highperformers(df, num=10):
   return df.head(num)


def get_underperformers(df, num = 10):
   return df.tail(num)


def plot_national_bench(df, n=10):

    fig, ax = plt.subplots(figsize=(10,9))



    hp = get_highperformers(df)
    up = get_underperformers(df)
    data = pd.concat([hp, up])
    print(data)
    
    ylabel = data['cip_title'].str[:40] + "\n" + data['institution_name'].str[:40]    
    colors = ["#c11a07" if v < 0 else "#15b356" for v in data['earnings_vs_national_pct']]
    positions = range(len(data)) 
    bars = ax.barh(positions, data['earnings_vs_national_pct'], color=colors, height=0.7)


    ax.bar_label(bars, fmt='%+.0f%%', padding=3, fontsize=8)   # value at the end of each bar
    ax.axvline(0, color='black', linewidth=1)
    ax.margins(x=0.12)    

    ax.yaxis.set_inverted(True)
    ax.set_yticks(positions)
    ax.set_yticklabels(ylabel, fontsize=8)  # arrange data from top to bottom

    ax.axvline(0, color='black', linewidth=1) 
    ax.set_xlabel("Earnings vs. national median for the same program (%)")
    ax.set_title(f"Top and Bottom {n} Programs vs National Benchmark")
    # for y, x in enumerate(data['earnings_vs_national_pct']):
    #     plt.annotate(str(x), xy=(x, y), va='center')
    plt.tight_layout()
    plt.savefig('new_nation.png')
    plt.show()



def plot_growing_occupation(df):


    grouped = df.groupby('cip_family_title')
    field = grouped[['median_earnings_4yr_usd', 'occupation_growth_pct_2024_34']].median()
    field['programs'] = grouped.size()
    field.columns = ['earnings', 'growth','programs']
    field = field[field['programs'] >= 20]
    print(field['programs'] / field['programs'].max() *400)

    top4 = field.nlargest(4, 'earnings').index
    bottom4 = field.nsmallest(4, 'earnings').index

    colors = []
    for name in field.index:
        if name in top4:
            colors.append('green')
        elif name in bottom4:
            colors.append('red')
        else:
            colors.append('lightgray')

    fig, ax = plt.subplots(figsize=(10,9))
    ax.scatter(field['growth'], field['earnings'], s=field['programs'] / field['programs'].max() *400,c=colors)
    ax.axvline(field['growth'].median(), color='gray', linestyle='--', linewidth=0.8)
    ax.axhline(field['earnings'].median(), color='gray', linestyle='--', linewidth=0.8)

    for i, name in enumerate(top4, start=1):
        ax.annotate(str(i), (field.loc[name, 'growth'], field.loc[name, 'earnings']),
                    fontsize=9, weight='bold', color='green',
                    xytext=(6, 6), textcoords='offset points')
        print(f"Top {i}. {name}")

    for i, name in enumerate(bottom4, start=1):
        ax.annotate(str(i), (field.loc[name, 'growth'], field.loc[name, 'earnings']),
                    fontsize=9, weight='bold', color='red',
                    xytext=(6, 6), textcoords='offset points')
        print(f"Bottom {i}. {name}")

    ax.set_xlabel("Projected job growth, 2024-34 (%)")
    ax.set_ylabel("Median earnings 4 yrs after graduation (USD)")
    ax.set_title("Median Earnings vs Projected Job Growth",
                 fontsize=14, weight='bold', loc='center')
    plt.tight_layout()
    plt.savefig("earnings_vs_growth.png", dpi=200, bbox_inches='tight')
    plt.show()

def plot_ai_use(df):
    grouped = df.groupby('cip_family_title')
    field = grouped[['ai_software_occupation_share', 'occupation_growth_pct_2024_34']].median()
    field['programs'] = grouped.size()
    field.columns = ['ai-use', 'growth','programs']
    field = field[field['programs'] >= 20]
    print(field['programs'] / field['programs'].max() *400)

    top4 = field.nlargest(4, 'ai-use').index
    bottom4 = field.nsmallest(4, 'ai-use').index

    colors = []
    for name in field.index:
        if name in top4:
            colors.append('green')
        elif name in bottom4:
            colors.append('red')
        else:
            colors.append('lightgray')

    fig, ax = plt.subplots(figsize=(10,9))
    ax.scatter(field['growth'], field['ai-use'], s=field['programs'] / field['programs'].max() *400,c=colors)
    ax.axvline(field['growth'].median(), color='gray', linestyle='--', linewidth=0.8)
    ax.axhline(field['ai-use'].median(), color='gray', linestyle='--', linewidth=0.8)

    for i, name in enumerate(top4, start=1):
        ax.annotate(str(i), (field.loc[name, 'growth'], field.loc[name, 'ai-use']),
                    fontsize=9, weight='bold', color='green',
                    xytext=(6, 6), textcoords='offset points')
        print(f"Top {i}. {name}")

    for i, name in enumerate(bottom4, start=1):
        ax.annotate(str(i), (field.loc[name, 'growth'], field.loc[name, 'ai-use']),
                    fontsize=9, weight='bold', color='red',
                    xytext=(6, 6), textcoords='offset points')
        print(f"Bottom {i}. {name}")

    ax.set_xlabel("Share of linked occupations using AI software)")
    ax.set_ylabel("Projected job growth, 2024-34 (%)")
    ax.set_title("AI use vs growth",
                 fontsize=14, weight='bold', loc='center')
    plt.tight_layout()
    plt.savefig("ai_use_vs_growth.png", dpi=200, bbox_inches='tight')
    plt.show()
