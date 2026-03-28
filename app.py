import streamlit as st
import pandas as pd
from streamlit_gsheets import GSheetsConnection
import plotly.express as px

# Set page config for a wider layout
st.set_page_config(page_title="Inventory Dashboard", layout="wide")

st.title("📦 Inventory Analysis Dashboard")

# 1. Connect to Google Sheets
conn = st.connection("gsheets", type=GSheetsConnection)

# 2. Fetch and Cache Data
@st.cache_data(ttl=600)
def load_data():
    sheet_url = "https://docs.google.com/spreadsheets/d/1t1ZnGoLpqcF7OnkVXsp6I4yF-6le3-ai4BYKukaJka4"
    
    # Load all data from the "DATA" tab
    df = conn.read(spreadsheet=sheet_url, worksheet="DATA")
    
    # Clean up the new SKU identifier
    if 'Group by SKU' in df.columns:
        df['Group by SKU'] = df['Group by SKU'].astype(str)
    
    # Ensure all depot stock columns are treated as numbers
    stock_cols =[
        'LDN Sold', 'LDN Avail', 'LDN OH', 
        'GLO Sold', 'GLO Avail', 'GLO OH'
    ]
    for col in stock_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
            
    # Calculate Totals across both depots for easy filtering and charting
    df['Total OH'] = df.get('LDN OH', 0) + df.get('GLO OH', 0)
    df['Total Avail'] = df.get('LDN Avail', 0) + df.get('GLO Avail', 0)
    df['Total Sold'] = df.get('LDN Sold', 0) + df.get('GLO Sold', 0)

    # --- APPLY CORE FILTERS ---
    
    # 1. Only keep rows where total On Hand > 0
    if 'Total OH' in df.columns:
        df = df[df['Total OH'] > 0]
        
    # 2. Ignore the "service" location (case-insensitive)
    if 'Default Location' in df.columns:
        df = df[df['Default Location'].fillna('').str.lower() != 'service']
        
    # --- SELECT REQUESTED COLUMNS ---
    core_columns =[
        'Group by SKU', 'Brand', 'Product Name', 'Group', 'Parent Style', 
        'Format Type', 'Format', 'Size', 'ABV', 'Sales Price (Price Tier 1)', 
        'Availability', 'Default Location',
        'LDN OH', 'LDN Avail', 'LDN Sold', 
        'GLO OH', 'GLO Avail', 'GLO Sold',
        'Total OH', 'Total Avail', 'Total Sold'
    ]
    
    # Trick to avoid crashes if a column name is slightly off
    existing_columns = [col for col in core_columns if col in df.columns]
    
    # Remove any duplicate columns that pandas might have renamed
    df = df.loc[:, ~df.columns.duplicated()]
    
    df = df[existing_columns]
            
    return df

# Load the data
df = load_data()

# 3. Create a Sidebar for Granular Drill-Downs
st.sidebar.header("Filter Data")

# Helper function to create clean filters automatically
def create_filter(col_name):
    if col_name in df.columns:
        # Get unique values, drop blanks, sort alphabetically
        options = sorted([str(x) for x in df[col_name].unique() if pd.notna(x) and str(x).strip() != ''])
        return st.sidebar.multiselect(f"Filter by {col_name}", options=options)
    return[]

selected_brand = create_filter("Brand")
selected_group = create_filter("Group")
selected_format = create_filter("Format Type")
selected_location = create_filter("Default Location")

# Apply filters
filtered_df = df.copy()
if selected_brand:
    filtered_df = filtered_df[filtered_df["Brand"].isin(selected_brand)]
if selected_group:
    filtered_df = filtered_df[filtered_df["Group"].isin(selected_group)]
if selected_format:
    filtered_df = filtered_df[filtered_df["Format Type"].isin(selected_format)]
if selected_location:
    filtered_df = filtered_df[filtered_df["Default Location"].isin(selected_location)]

# 4. Top Level KPIs
st.subheader("Key Metrics (Combined Depots)")
col1, col2, col3 = st.columns(3)

on_hand_sum = filtered_df['Total OH'].sum() if 'Total OH' in filtered_df.columns else 0
available_sum = filtered_df['Total Avail'].sum() if 'Total Avail' in filtered_df.columns else 0
sold_sum = filtered_df['Total Sold'].sum() if 'Total Sold' in filtered_df.columns else 0

col1.metric("Total Stock On Hand", f"{on_hand_sum:,.0f}")
col2.metric("Total Available", f"{available_sum:,.0f}")
col3.metric("Total Sold", f"{sold_sum:,.0f}")

st.divider()

# 5. Visualizations
col_chart1, col_chart2 = st.columns(2)

with col_chart1:
    st.subheader("Stock Status by Brand")
    if 'Brand' in filtered_df.columns and not filtered_df.empty:
        brand_df = filtered_df.groupby("Brand")[['Total Avail', 'Total Sold']].sum().reset_index()
        fig_brand = px.bar(brand_df, x="Brand", y=["Total Avail", "Total Sold"], 
                         title="Total Available vs Sold per Brand", barmode="stack")
        st.plotly_chart(fig_brand, use_container_width=True)

with col_chart2:
    st.subheader("Top 10 Sold SKUs")
    if 'Group by SKU' in filtered_df.columns and 'Total Sold' in filtered_df.columns and not filtered_df.empty:
        top_sold = filtered_df.sort_values(by="Total Sold", ascending=False).head(10)
        
        hover_data = ["Product Name"] if "Product Name" in filtered_df.columns else None
        
        fig_sku = px.bar(top_sold, x="Group by SKU", y="Total Sold", hover_data=hover_data,
                         title="Highest Sold Products (Combined)", text_auto=True)
        st.plotly_chart(fig_sku, use_container_width=True)

# 6. Granular Data Table with Color Formatting
st.subheader("Granular Inventory Data")
st.write("Use the table below to sort and search through specific items.")

# Define the color mapping function
def style_depot_columns(col):
    # Using rgba ensures the text remains readable in both Light & Dark modes
    if 'LDN' in col.name:
        return['background-color: rgba(0, 150, 255, 0.15)'] * len(col) # Light Blue
    elif 'GLO' in col.name:
        return['background-color: rgba(0, 200, 100, 0.15)'] * len(col) # Light Green
    elif 'Total' in col.name:
        return['background-color: rgba(255, 165, 0, 0.15)'] * len(col) # Light Orange
    else:
        return [''] * len(col)

# Apply the styling to the dataframe
styled_df = filtered_df.style.apply(style_depot_columns, axis=0)

# Display the styled dataframe
st.dataframe(
    styled_df, 
    use_container_width=True,
    hide_index=True
)

# Optional: Add a button to manually clear the cache and pull fresh Google Sheets data
if st.button("Refresh Data"):
    st.cache_data.clear()
    st.rerun()
