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