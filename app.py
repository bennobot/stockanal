import streamlit as st
import pandas as pd
from streamlit_gsheets import GSheetsConnection
import plotly.express as px

# Set page config for a wider layout
st.set_page_config(page_title="Inventory Dashboard", layout="wide")

st.title("📦 Inventory Analysis Dashboard")

# 1. Connect to Google Sheets
conn = st.connection("gsheets", type=GSheetsConnection)

# 2. Fetch and Cache Data (TTL caches data for 10 minutes to avoid hitting API limits)
@st.cache_data(ttl=600)
def load_data():
    # Store your specific Google Sheet URL in a variable
    sheet_url = "https://docs.google.com/spreadsheets/d/1t1ZnGoLpqcF7OnkVXsp6I4yF-6le3-ai4BYKukaJka4"
    
    # Load Data Source 1: AppScript Data (Pass the URL here)
    df_info = conn.read(spreadsheet=sheet_url, worksheet="DATA") # Replace with actual tab name
    
    # Load Data Source 2: Pasted Data (Pass the URL here too)
    df_stock = conn.read(spreadsheet=sheet_url, worksheet="Inventory") # Replace with actual tab name
    
    # Merge the two datasets on a common column, e.g., 'SKU'
    df_info['SKU'] = df_info['SKU'].astype(str)
    df_stock['SKU'] = df_stock['SKU'].astype(str)
    
    df_merged = pd.merge(df_info, df_stock, on="SKU", how="left")
    
    # Fill NaN values with 0 for stock columns
    df_merged['On_Hand'] = df_merged['On_Hand'].fillna(0)
    df_merged['Available'] = df_merged['Available'].fillna(0)
    df_merged['Sold'] = df_merged['Sold'].fillna(0)
    
    return df_merged

# 3. Create a Sidebar for Granular Drill-Downs
st.sidebar.header("Filter Data")

# Example filters (adjust based on your actual column names)
selected_category = st.sidebar.multiselect("Select Category", options=df["Category"].unique())
selected_sku = st.sidebar.multiselect("Select Specific SKU", options=df["SKU"].unique())

# Apply filters
filtered_df = df.copy()
if selected_category:
    filtered_df = filtered_df[filtered_df["Category"].isin(selected_category)]
if selected_sku:
    filtered_df = filtered_df[filtered_df["SKU"].isin(selected_sku)]

# 4. Top Level KPIs
st.subheader("Key Metrics")
col1, col2, col3 = st.columns(3)
col1.metric("Total Stock On Hand", f"{filtered_df['On_Hand'].sum():,.0f}")
col2.metric("Total Available", f"{filtered_df['Available'].sum():,.0f}")
col3.metric("Total Sold", f"{filtered_df['Sold'].sum():,.0f}")

st.divider()

# 5. Visualizations
col_chart1, col_chart2 = st.columns(2)

with col_chart1:
    st.subheader("Stock Status by Category")
    # Group by category
    cat_df = filtered_df.groupby("Category")[['Available', 'Sold']].sum().reset_index()
    # Plotly stacked bar chart
    fig_cat = px.bar(cat_df, x="Category", y=["Available", "Sold"], 
                     title="Available vs Sold per Category", barmode="stack")
    st.plotly_chart(fig_cat, use_container_width=True)

with col_chart2:
    st.subheader("Top 10 Selling SKUs")
    # Sort by sold
    top_sold = filtered_df.sort_values(by="Sold", ascending=False).head(10)
    fig_sku = px.bar(top_sold, x="SKU", y="Sold", 
                     title="Highest Selling Products", text_auto=True)
    st.plotly_chart(fig_sku, use_container_width=True)

# 6. Granular Data Table
st.subheader("Granular Inventory Data")
st.write("Use the table below to sort and search through specific items.")
# st.dataframe allows users to click headers to sort, and expand cells
st.dataframe(
    filtered_df[['SKU', 'Product_Name', 'Category', 'On_Hand', 'Available', 'Sold']], 
    use_container_width=True,
    hide_index=True
)

# Optional: Add a button to manually clear the cache and pull fresh Google Sheets data
if st.button("Refresh Data"):
    st.cache_data.clear()
    st.rerun()
