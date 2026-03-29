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
    df = conn.read(spreadsheet=sheet_url, worksheet="DATA")
    
    if 'Group by SKU' in df.columns:
        df['Group by SKU'] = df['Group by SKU'].astype(str)
    
    stock_cols =['LDN Sold', 'LDN Avail', 'LDN OH', 'GLO Sold', 'GLO Avail', 'GLO OH']
    for col in stock_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
            
    if 'Sales Price (Price Tier 1)' in df.columns:
        df['Sales Price (Price Tier 1)'] = pd.to_numeric(
            df['Sales Price (Price Tier 1)'].astype(str).str.replace(r'[£$,]', '', regex=True), errors='coerce'
        )
        
    if 'ABV' in df.columns:
        df['ABV'] = pd.to_numeric(
            df['ABV'].astype(str).str.replace(r'[%]', '', regex=True), errors='coerce'
        )
            
    df['Total OH'] = df.get('LDN OH', 0) + df.get('GLO OH', 0)
    df['Total Avail'] = df.get('LDN Avail', 0) + df.get('GLO Avail', 0)
    df['Total Sold'] = df.get('LDN Sold', 0) + df.get('GLO Sold', 0)

    if 'Total OH' in df.columns:
        df = df[df['Total OH'] > 0]
        
    if 'Default Location' in df.columns:
        df = df[df['Default Location'].fillna('').str.lower() != 'service']
        
    core_columns =[
        'Group by SKU', 'Brand', 'Product Name', 'Group', 'Parent Style', 
        'Format Type', 'Format', 'Size', 'ABV', 'Sales Price (Price Tier 1)', 
        'Availability', 'Default Location',
        'LDN OH', 'LDN Avail', 'LDN Sold', 
        'GLO OH', 'GLO Avail', 'GLO Sold',
        'Total OH', 'Total Avail', 'Total Sold'
    ]
    
    existing_columns =[col for col in core_columns if col in df.columns]
    df = df.loc[:, ~df.columns.duplicated()]
    df = df[existing_columns]
            
    return df

df = load_data()

# ---------------------------------------------------------
# Helper Function: Render Styled Data Table
# ---------------------------------------------------------
def render_inventory_table(data):
    def style_depot_columns(col):
        if 'LDN' in col.name:
            return['background-color: rgba(0, 150, 255, 0.15)'] * len(col) 
        elif 'GLO' in col.name:
            return['background-color: rgba(0, 200, 100, 0.15)'] * len(col) 
        elif 'Total' in col.name:
            return['background-color: rgba(255, 165, 0, 0.15)'] * len(col) 
        else:
            return [''] * len(col)

    format_dict = {}
    inventory_cols =['LDN Sold', 'LDN Avail', 'LDN OH', 'GLO Sold', 'GLO Avail', 'GLO OH', 'Total OH', 'Total Avail', 'Total Sold']
    for col in inventory_cols:
        if col in data.columns:
            format_dict[col] = "{:,.0f}"

    if 'Sales Price (Price Tier 1)' in data.columns:
        format_dict['Sales Price (Price Tier 1)'] = "{:,.2f}"
    if 'ABV' in data.columns:
        format_dict['ABV'] = "{:.1f}"

    styled_df = data.style.apply(style_depot_columns, axis=0).format(format_dict, na_rep="")
    
    # st.dataframe natively supports clicking headers to sort, and a search icon inside the UI
    st.dataframe(styled_df, use_container_width=True, hide_index=True)


# ---------------------------------------------------------
# UI Layout: Tabs
# ---------------------------------------------------------
tab_dash, tab_supplier, tab_format, tab_style = st.tabs([
    "📊 Dashboard", 
    "🏭 Brand / Supplier", 
    "📦 Format", 
    "🍺 Parent Style"
])

# --- TAB 1: DASHBOARD ---
with tab_dash:
    st.subheader("High-Level Inventory Overview")
    
    # Location Toggles
    st.write("**Toggle Depots for Dashboard Metrics:**")
    col_t1, col_t2 = st.columns(2)
    with col_t1:
        ldn_active = st.checkbox("Include LDN (London)", value=True)
    with col_t2:
        glo_active = st.checkbox("Include GLO (Gloucester)", value=True)
        
    # Dynamically calculate Dashboard Totals based on toggles
    dash_df = df.copy()
    dash_df['Dash OH'] = (dash_df.get('LDN OH', 0) if ldn_active else 0) + (dash_df.get('GLO OH', 0) if glo_active else 0)
    dash_df['Dash Avail'] = (dash_df.get('LDN Avail', 0) if ldn_active else 0) + (dash_df.get('GLO Avail', 0) if glo_active else 0)
    dash_df['Dash Sold'] = (dash_df.get('LDN Sold', 0) if ldn_active else 0) + (dash_df.get('GLO Sold', 0) if glo_active else 0)
    
    # Filter out empty rows based on current toggles
    dash_df = dash_df[dash_df['Dash OH'] > 0]
    
    col1, col2, col3 = st.columns(3)
    col1.metric("Selected Stock On Hand", f"{dash_df['Dash OH'].sum():,.0f}")
    col2.metric("Selected Available", f"{dash_df['Dash Avail'].sum():,.0f}")
    col3.metric("Selected Sold", f"{dash_df['Dash Sold'].sum():,.0f}")
    
    st.divider()
    
    chart_col1, chart_col2 = st.columns(2)
    
    with chart_col1:
        st.write("**Available vs Sold by Format**")
        if 'Format' in dash_df.columns and not dash_df.empty:
            format_agg = dash_df.groupby("Format")[['Dash Avail', 'Dash Sold']].sum().reset_index()
            fig_format = px.bar(format_agg, x="Format", y=["Dash Avail", "Dash Sold"], 
                             barmode="group", labels={'value': 'Volume', 'variable': 'Metric'})
            st.plotly_chart(fig_format, use_container_width=True)
            
    with chart_col2:
        st.write("**Available Stock: Style within Formats**")
        if 'Format' in dash_df.columns and 'Parent Style' in dash_df.columns and not dash_df.empty:
            # Sunburst chart is perfect for hierarchical data (Format -> Style)
            sun_df = dash_df[dash_df['Dash Avail'] > 0] # Only plot things we actually have
            if not sun_df.empty:
                fig_sun = px.sunburst(sun_df, path=['Format', 'Parent Style'], values='Dash Avail')
                st.plotly_chart(fig_sun, use_container_width=True)
            else:
                st.info("No available stock to display for selected locations.")


# --- TAB 2: BRAND / SUPPLIER ---
with tab_supplier:
    st.subheader("Inventory by Brand / Supplier")
    if 'Brand' in df.columns:
        brand_options = sorted([str(x) for x in df['Brand'].unique() if pd.notna(x) and str(x).strip() != ''])
        sel_brands = st.multiselect("Filter by Brand(s)", options=brand_options, key="brand_filter")
        
        filtered_brand_df = df[df['Brand'].isin(sel_brands)] if sel_brands else df
        render_inventory_table(filtered_brand_df)
    else:
        st.error("Brand column not found in data.")


# --- TAB 3: FORMAT ---
with tab_format:
    st.subheader("Inventory by Format")
    if 'Format' in df.columns:
        format_options = sorted([str(x) for x in df['Format'].unique() if pd.notna(x) and str(x).strip() != ''])
        sel_formats = st.multiselect("Filter by Format(s)", options=format_options, key="format_filter")
        
        filtered_format_df = df[df['Format'].isin(sel_formats)] if sel_formats else df
        render_inventory_table(filtered_format_df)
    else:
        st.error("Format column not found in data.")


# --- TAB 4: PARENT STYLE ---
with tab_style:
    st.subheader("Inventory by Parent Style")
    if 'Parent Style' in df.columns:
        style_options = sorted([str(x) for x in df['Parent Style'].unique() if pd.notna(x) and str(x).strip() != ''])
        sel_styles = st.multiselect("Filter by Parent Style(s)", options=style_options, key="style_filter")
        
        filtered_style_df = df[df['Parent Style'].isin(sel_styles)] if sel_styles else df
        render_inventory_table(filtered_style_df)
    else:
        st.error("Parent Style column not found in data.")

st.divider()
if st.button("Refresh Data from Google Sheets"):
    st.cache_data.clear()
    st.rerun()
