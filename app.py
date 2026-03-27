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
    df['SKU'] = df['SKU'].astype(str)
    
    # Ensure stock columns are numbers (forces any text/blanks into NaN, then we fill with 0)
    stock_cols = ['On Hand', 'Available', 'Committed']
    for col in stock_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
            
    return df

# Load the data
df = load_data()

# 3. Create a Sidebar for Granular Drill-Downs
st.sidebar.header("Filter Data")

# Using Category and Brand for filters, dropping blanks to keep the list clean
categories =[c for c in df["Category"].unique() if pd.notna(c)]
brands =[b for b in df["Brand"].unique() if pd.notna(b)]

selected_category = st.sidebar.multiselect("Select Category", options=categories)
selected_brand = st.sidebar.multiselect("Select Brand", options=brands)

# Apply filters
filtered_df = df.copy()
if selected_category:
    filtered_df = filtered_df[filtered_df["Category"].isin(selected_category)]
if selected_brand:
    filtered_df = filtered_df[filtered_df["Brand"].isin(selected_brand)]

# 4. Top Level KPIs
st.subheader("Key Metrics")
col1, col2, col3 = st.columns(3)
col1.metric("Total Stock On Hand", f"{filtered_df['On Hand'].sum():,.0f}")
col2.metric("Total Available", f"{filtered_df['Available'].sum():,.0f}")
col3.metric("Total Committed", f"{filtered_df['Committed'].sum():,.0f}")

st.divider()

# 5. Visualizations
col_chart1, col_chart2 = st.columns(2)

with col_chart1:
    st.subheader("Stock Status by Category")
    # Group by category
    cat_df = filtered_df.groupby("Category")[['Available', 'Committed']].sum().reset_index()
    # Plotly stacked bar chart
    fig_cat = px.bar(cat_df, x="Category", y=["Available", "Committed"], 
                     title="Available vs Committed per Category", barmode="stack")
    st.plotly_chart(fig_cat, use_container_width=True)

with col_chart2:
    st.subheader("Top 10 Committed SKUs")
    # Sort by Committed (Replacing the old 'Sold' logic)
    top_committed = filtered_df.sort_values(by="Committed", ascending=False).head(10)
    # Using 'SKU' on the x-axis, but hovering will show more info
    fig_sku = px.bar(top_committed, x="SKU", y="Committed", hover_data=["Product Name", "Brand"],
                     title="Highest Committed Products", text_auto=True)
    st.plotly_chart(fig_sku, use_container_width=True)

# 6. Granular Data Table
st.subheader("Granular Inventory Data")
st.write("Use the table below to sort and search through specific items.")

# Select a clean list of columns to display in the table
display_columns =[
    'SKU', 'Product Name', 'Brand', 'Category', 
    'Sales Price (Price Tier 1)', 'Format', 
    'On Hand', 'Available', 'Committed'
]

# Note: Sometimes Google Sheets has duplicate headers. We use a trick to only select columns that actually exist.
existing_columns = [col for col in display_columns if col in filtered_df.columns]

st.dataframe(
    filtered_df[existing_columns], 
    use_container_width=True,
    hide_index=True
)

# Optional: Add a button to manually clear the cache and pull fresh Google Sheets data
if st.button("Refresh Data"):
    st.cache_data.clear()
    st.rerun()
