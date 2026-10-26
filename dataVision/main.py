"""  What fields have the highest earnings?
  Which programs balance earnings and debt?
  How do earnings change after graduation?
  
  """

import pandas as pd 

import matplotlib.pyplot as plt

path = "college_majors_2026.csv"

def load_frame(path):

    df = pd.read_csv(path)

    # Clean all target numeric columns upfront
    time_columns = ['median_earnings_1yr_usd', 'median_earnings_4yr_usd', 'median_earnings_5yr_usd']
    for col in time_columns:
        df[col] = pd.to_numeric(df[col], errors='coerce')

    # Drop rows where crucial columns are missing
    df = df.dropna(subset=['median_earnings_4yr_usd', 'median_debt_usd'])

    return df 

def field_highest(df):

    return df.groupby("cip_family_title")["median_earnings_4yr_usd"].median().sort_values(ascending=False)

    
def debt_earnings(df):
    # Filter out rows where debt is zero to avoid division by zero errors
    clean_df = df[df["median_debt_usd"] > 0].copy()
    clean_df["debt_to_earnings_ratio"] = (
        clean_df["median_earnings_4yr_usd"] / clean_df["median_debt_usd"]
    )
    return (
        clean_df.groupby("cip_family_title")["debt_to_earnings_ratio"]
        .median()
        .sort_values(ascending=False)
    )



def field_highest_chart(df):
    
    grouped_data = field_highest(df)

    fig, ax = plt.subplots(figsize=(12, 16))

    # Plot bars with a clean color and defined borders
    bars = ax.barh(
        grouped_data.index,
        grouped_data.values,
        color="#2b7bba",
        edgecolor="none",
        height=0.6,
    )

    # Format labels, titles, and shift the left margin outward
    ax.set_xlabel("Median Earnings 4-Year (USD)", fontsize=14, labelpad=12)
    ax.set_ylabel("CIP Family Title", fontsize=14, labelpad=12)
    ax.set_title(
        "Median Earnings by CIP Family Title",
        fontsize=14,
        fontweight="bold",
        pad=15,
    )

    # Keep highest at the top
    ax.invert_yaxis() 

    # Extend canvas padding so that the labels are not cut off
    plt.subplots_adjust(left=0.45, right=0.92)

    fig.savefig("median_earnings_by_cip_family_title.png", bbox_inches="tight")

    plt.show()

    plt.close(fig)

def debt_earnings_chart(df):
    
    grouped_ratio = debt_earnings(df)

    fig, ax = plt.subplots(figsize=(12, 16))
    
    bars = ax.barh(grouped_ratio.index, grouped_ratio.values, color="#5cb85c", height=0.6)
    
    ax.set_xlabel("Median Earnings-to-Debt Ratio ($ Earned per $1 Owed)", fontsize=14, labelpad=12)
    ax.set_ylabel("CIP Family Title", fontsize=14, labelpad=12)
    ax.set_title("Ranked Return on Investment: Earnings-to-Debt Ratio", fontsize=14, fontweight='bold', pad=15)
    
    ax.invert_yaxis()
    ax.grid(axis='x', linestyle='--', alpha=0.5)

    ax.margins(x=0.15)
    
    # Add numerical value labels right next to the bars
    for bar in bars:
        width = bar.get_width()
        ax.text(width + 0.1, bar.get_y() + bar.get_height()/2, f"{width:.1f}x", va='center', ha='left', fontsize=10)
        
    plt.subplots_adjust(left=0.45, right=0.92)
    fig.savefig("earnings_debt_ratio_ranking.png", bbox_inches="tight")
    plt.show()
    plt.close(fig)

def plot_earnings_over_time(df):
    
    time_columns = ['median_earnings_1yr_usd', 'median_earnings_4yr_usd', 'median_earnings_5yr_usd']
    x_labels = ['Year 1', 'Year 4', 'Year 5']
    
    # Group by major family and compute the medians across time intervals
    grouped_timeline = df.groupby('cip_family_title')[time_columns].median()
    
    # Selected a few fields to plot so the chart stays highly readable
    selected_fields = [
        'Computer and Information Sciences and Support Services',
        'Engineering',
        'Business, Management, Marketing, and Related Support Services',
        'Social Sciences',
        'Visual and Performing Arts'
    ]
    
    fig, ax = plt.subplots(figsize=(10, 6))
    
    #Loop through the rows
    for field in selected_fields:
        # Check if the field exists in the data 
        if field in grouped_timeline.index:
            # Grab the specific row values for this major
            y_values = grouped_timeline.loc[field]
            
            # Plot the line directly: X is years, Y is the row values
            ax.plot(x_labels, y_values, marker='o', linewidth=2.5, label=field)
        
    # Polishing and Formatting
    ax.set_title("Salary Growth Trajectory Post-Graduation", fontsize=14, fontweight='bold', pad=15)
    ax.set_xlabel("Time Elapsed Since Graduation", fontsize=12, labelpad=10)
    ax.set_ylabel("Median Earnings (USD)", fontsize=12, labelpad=10)
    
    ax.get_yaxis().set_major_formatter(plt.FuncFormatter(lambda y, loc: f"${y:,.0f}"))
    ax.grid(axis='y', linestyle='--', alpha=0.5)
    
    # Place the legend cleanly outside
    ax.legend(loc='upper left', bbox_to_anchor=(1.02, 1), frameon=True)
    
    fig.savefig("earnings_growth_trajectory.png", bbox_inches="tight")
    plt.show()
    plt.close(fig)

  


if __name__ == "__main__":
    
    main_df = load_frame(path)
    
    field_highest_chart(main_df)

    debt_earnings_chart(main_df)

    plot_earnings_over_time(main_df)





