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
    
    # Clean up SKU
    if 'SKU' in df.columns:
        df['SKU'] = df['SKU'].astype(str)
    
    # Ensure stock columns are numbers so we can do math on them
    stock_cols =['On Hand', 'Available', 'Committed']
    for col in stock_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
            
    # --- APPLY CORE FILTERS ---
    
    # 1. Only keep rows where On Hand > 0
    if 'On Hand' in df.columns:
        df = df[df['On Hand'] > 0]
        
    # 2. Ignore the "service" location (case-insensitive)
    if 'Default Location' in df.columns:
        # Fill empty locations with blank string to avoid errors, then filter
        df = df[df['Default Location'].fillna('').str.lower() != 'service']
        
    # --- SELECT REQUESTED COLUMNS ---
    core_columns =[
        'SKU', 'Default Location', 'Availability', 'Group', 'Brand', 
        'Product Name', 'Size', 'Format Type', 'ABV', 
        'Committed', 'Available', 'On Hand'
    ]
    
    # Trick to avoid crashes if a column name has a slight typo in the sheet
    existing_columns =[col for col in core_columns if col in df.columns]
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

selected_location = create_filter("Default Location")
selected_brand = create_filter("Brand")
selected_group = create_filter("Group")
selected_format = create_filter("Format Type")

# Apply filters
filtered_df = df.copy()
if selected_location:
    filtered_df = filtered_df[filtered_df["Default Location"].isin(selected_location)]
if selected_brand:
    filtered_df = filtered_df[filtered_df["Brand"].isin(selected_brand)]
if selected_group:
    filtered_df = filtered_df[filtered_df["Group"].isin(selected_group)]
if selected_format:
    filtered_df = filtered_df[filtered_df["Format Type"].isin(selected_format)]

# 4. Top Level KPIs
st.subheader("Key Metrics")
col1, col2, col3 = st.columns(3)

# Safeguard in case columns are missing
on_hand_sum = filtered_df['On Hand'].sum() if 'On Hand' in filtered_df.columns else 0
available_sum = filtered_df['Available'].sum() if 'Available' in filtered_df.columns else 0
committed_sum = filtered_df['Committed'].sum() if 'Committed' in filtered_df.columns else 0

col1.metric("Total Stock On Hand", f"{on_hand_sum:,.0f}")
col2.metric("Total Available", f"{available_sum:,.0f}")
col3.metric("Total Committed", f"{committed_sum:,.0f}")

st.divider()

# 5. Visualizations
col_chart1, col_chart2 = st.columns(2)

with col_chart1:
    st.subheader("Stock Status by Brand")
    if 'Brand' in filtered_df.columns:
        # Group by Brand
        brand_df = filtered_df.groupby("Brand")[['Available', 'Committed']].sum().reset_index()
        # Plotly stacked bar chart
        fig_brand = px.bar(brand_df, x="Brand", y=["Available", "Committed"], 
                         title="Available vs Committed per Brand", barmode="stack")
        st.plotly_chart(fig_brand, use_container_width=True)

with col_chart2:
    st.subheader("Top 10 Committed SKUs")
    if 'SKU' in filtered_df.columns and 'Committed' in filtered_df.columns:
        # Sort by Committed 
        top_committed = filtered_df.sort_values(by="Committed", ascending=False).head(10)
        # Add Product Name to hover data if it exists
        hover_data = ["Product Name"] if "Product Name" in filtered_df.columns else
