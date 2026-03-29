import streamlit as st
import pandas as pd
from streamlit_gsheets import GSheetsConnection
import plotly.express as px

# Set page config for a wider layout
st.set_page_config(page_title="Inventory Dashboard", layout="wide")

st.title("📦 Inventory Analysis Dashboard")

# 1. Connect to Google Sheets
conn = st.connection("gsheets", type=GSheetsConnection)

# 2. Fetch, Clean, and Sort Data
@st.cache_data(ttl=600)
def load_data():
    sheet_url = "https://docs.google.com/spreadsheets/d/1t1ZnGoLpqcF7OnkVXsp6I4yF-6le3-ai4BYKukaJka4"
    df = conn.read(spreadsheet=sheet_url, worksheet="DATA")
    
    # Clean up identifiers
    if 'Group by SKU' in df.columns:
        df['Group by SKU'] = df['Group by SKU'].astype(str)
    
    # Clean up stock numbers
    stock_cols =['LDN Sold', 'LDN Avail', 'LDN OH', 'GLO Sold', 'GLO Avail', 'GLO OH']
    for col in stock_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
            
    # Clean Prices
    if 'Sales Price (Price Tier 1)' in df.columns:
        df['Sales Price (Price Tier 1)'] = pd.to_numeric(
            df['Sales Price (Price Tier 1)'].astype(str).str.replace(r'[£$,]', '', regex=True), errors='coerce'
        )
        
    # Clean ABV
    if 'ABV' in df.columns:
        df['ABV'] = pd.to_numeric(
            df['ABV'].astype(str).str.replace(r'[%]', '', regex=True), errors='coerce'
        )
        
    # Ignore "service" locations
    if 'Default Location' in df.columns:
        df = df[df['Default Location'].fillna('').str.lower() != 'service']
        
    # Select our specific required columns
    core_columns =[
        'Group by SKU', 'Brand', 'Product Name', 'Group', 'Parent Style', 
        'Format Type', 'Format', 'Size', 'ABV', 'Sales Price (Price Tier 1)', 
        'Availability', 'Default Location',
        'LDN OH', 'LDN Avail', 'LDN Sold', 
        'GLO OH', 'GLO Avail', 'GLO Sold'
    ]
    existing_columns =[col for col in core_columns if col in df.columns]
    df = df.loc[:, ~df.columns.duplicated()]
    df = df[existing_columns]
    
    # --- CUSTOM DEFAULT SORTING ---
    if 'Format' in df.columns:
        # Define the explicit order for Formats
        format_order = ['Cask', 'Keg', 'Cans', 'Bottles', 'Bag in Box', 'Other']
        
        # Find any other formats in the data that aren't in our list and put them at the end
        existing_formats = df['Format'].dropna().unique().tolist()
        final_format_order = format_order +[f for f in existing_formats if f not in format_order]
        
        # Apply categorical sorting for the Format column
        df['Format'] = pd.Categorical(df['Format'], categories=final_format_order, ordered=True)
        
    # Sort the dataframe: Brand -> Format (custom order) -> Product Name
    sort_cols = [c for c in ['Brand', 'Format', 'Product Name'] if c in df.columns]
    if sort_cols:
        df = df.sort_values(by=sort_cols, ascending=[True] * len(sort_cols))
        
    # Convert Format back to a standard string so it plays nicely with the UI later
    if 'Format' in df.columns:
        df['Format'] = df['Format'].astype(str).replace('nan', '')
            
    return df

df = load_data()


# ---------------------------------------------------------
# Helper Function 1: Handle Dynamic Location Logic
# ---------------------------------------------------------
def apply_location_toggles(data, ldn_active, glo_active):
    df_loc = data.copy()
    
    # Recalculate Totals based ONLY on active locations
    df_loc['Total OH'] = (df_loc.get('LDN OH', 0) if ldn_active else 0) + (df_loc.get('GLO OH', 0) if glo_active else 0)
    df_loc['Total Avail'] = (df_loc.get('LDN Avail', 0) if ldn_active else 0) + (df_loc.get('GLO Avail', 0) if glo_active else 0)
    df_loc['Total Sold'] = (df_loc.get('LDN Sold', 0) if ldn_active else 0) + (df_loc.get('GLO Sold', 0) if glo_active else 0)
    
    # Filter out items where the active locations have exactly 0 stock
    df_loc = df_loc[df_loc['Total OH'] > 0]
    
    # Drop columns for inactive locations to keep the data table clean
    cols_to_drop = []
    if not ldn_active: cols_to_drop.extend(['LDN OH', 'LDN Avail', 'LDN Sold'])
    if not glo_active: cols_to_drop.extend(['GLO OH', 'GLO Avail', 'GLO Sold'])
    
    return df_loc.drop(columns=[c for c in cols_to_drop if c in df_loc.columns])


# ---------------------------------------------------------
# Helper Function 2: Render Styled Data Table
# ---------------------------------------------------------
def render_inventory_table(data):
    def style_depot_columns(col):
        if 'LDN' in col.name: return['background-color: rgba(0, 150, 255, 0.15)'] * len(col) 
        elif 'GLO' in col.name: return['background-color: rgba(0, 200, 100, 0.15)'] * len(col) 
        elif 'Total' in col.name: return['background-color: rgba(255, 165, 0, 0.15)'] * len(col) 
        else: return [''] * len(col)

    format_dict = {}
    inventory_cols =['LDN Sold', 'LDN Avail', 'LDN OH', 'GLO Sold', 'GLO Avail', 'GLO OH', 'Total OH', 'Total Avail', 'Total Sold']
    for col in inventory_cols:
        if col in data.columns: format_dict[col] = "{:,.0f}"

    if 'Sales Price (Price Tier 1)' in data.columns: format_dict['Sales Price (Price Tier 1)'] = "{:,.2f}"
    if 'ABV' in data.columns: format_dict['ABV'] = "{:.1f}"

    styled_df = data.style.apply(style_depot_columns, axis=0).format(format_dict, na_rep="")
    st.dataframe(styled_df, use_container_width=True, hide_index=True)


# ---------------------------------------------------------
# Helper Function 3: Tab Builder Engine (Toggles + Drilldown Filters)
# ---------------------------------------------------------
def render_data_tab(tab_data, primary_col, tab_id):
    st.write("**1. Select Depot Locations**")
    col_l1, col_l2 = st.columns(2)
    ldn_active = col_l1.checkbox("Include LDN (London)", value=True, key=f"{tab_id}_ldn")
    glo_active = col_l2.checkbox("Include GLO (Gloucester)", value=True, key=f"{tab_id}_glo")
    
    # Apply the toggles to filter the data
    tab_df = apply_location_toggles(tab_data, ldn_active, glo_active)
    
    if tab_df.empty:
        st.warning("No inventory available for the selected locations.")
        return
        
    st.write("**2. Drill Down Data**")
    col1, col2, col3, col4 = st.columns(4)
    
    # Determine the columns for the secondary filters dynamically
    filter_cols =['Brand', 'Format', 'Parent Style']
    if primary_col in filter_cols:
        filter_cols.remove(primary_col)
        
    # Render Primary Filter
    with col1:
        if primary_col in tab_df.columns:
            options_primary = sorted([str(x) for x in tab_df[primary_col].unique() if pd.notna(x) and str(x).strip() != ''])
            sel_primary = st.multiselect(f"{primary_col}", options=options_primary, key=f"{tab_id}_prim")
            if sel_primary: tab_df = tab_df[tab_df[primary_col].isin(sel_primary)]
            
    # Render Secondary Filter 1
    with col2:
        if filter_cols[0] in tab_df.columns:
            options_sec1 = sorted([str(x) for x in tab_df[filter_cols[0]].unique() if pd.notna(x) and str(x).strip() != ''])
            sel_sec1 = st.multiselect(f"{filter_cols[0]}", options=options_sec1, key=f"{tab_id}_sec1")
            if sel_sec1: tab_df = tab_df[tab_df[filter_cols[0]].isin(sel_sec1)]
            
    # Render Secondary Filter 2
    with col3:
        if filter_cols[1] in tab_df.columns:
            options_sec2 = sorted([str(x) for x in tab_df[filter_cols[1]].unique() if pd.notna(x) and str(x).strip() != ''])
            sel_sec2 = st.multiselect(f"{filter_cols[1]}", options=options_sec2, key=f"{tab_id}_sec2")
            if sel_sec2: tab_df = tab_df[tab_df[filter_cols[1]].isin(sel_sec2)]
            
    # Render Price Slider
    with col4:
        if 'Sales Price (Price Tier 1)' in tab_df.columns:
            valid_prices = tab_df['Sales Price (Price Tier 1)'].dropna()
            if not valid_prices.empty:
                min_p = float(valid_prices.min())
                max_p = float(valid_prices.max())
                if min_p < max_p:
                    price_range = st.slider("Price Range", min_value=min_p, max_value=max_p, value=(min_p, max_p), format="£%f", key=f"{tab_id}_price")
                    # Keep rows within price range OR rows that don't have a price yet
                    in_range = tab_df['Sales Price (Price Tier 1)'].between(price_range[0], price_range[1])
                    is_nan = tab_df['Sales Price (Price Tier 1)'].isna()
                    tab_df = tab_df[in_range | is_nan]
                elif min_p == max_p:
                    st.write(f"**Price Range:** £{min_p:,.2f}")
                    
    # Render Final Table
    st.divider()
    render_inventory_table(tab_df)


# ---------------------------------------------------------
# UI Layout: Tabs Setup
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
    
    st.write("**Select Depot Locations**")
    col_t1, col_t2 = st.columns(2)
    with col_t1: dash_ldn = st.checkbox("Include LDN (London)", value=True, key="dash_ldn")
    with col_t2: dash_glo = st.checkbox("Include GLO (Gloucester)", value=True, key="dash_glo")
        
    # Get location-filtered data for the dashboard
    dash_df = apply_location_toggles(df, dash_ldn, dash_glo)
    
    col1, col2, col3 = st.columns(3)
    col1.metric("Selected Stock On Hand", f"{dash_df['Total OH'].sum() if 'Total OH' in dash_df else 0:,.0f}")
    col2.metric("Selected Available", f"{dash_df['Total Avail'].sum() if 'Total Avail' in dash_df else 0:,.0f}")
    col3.metric("Selected Sold", f"{dash_df['Total Sold'].sum() if 'Total Sold' in dash_df else 0:,.0f}")
    
    st.divider()
    chart_col1, chart_col2 = st.columns(2)
    
    with chart_col1:
        st.write("**Available vs Sold by Format**")
        if 'Format' in dash_df.columns and not dash_df.empty:
            format_agg = dash_df.groupby("Format")[['Total Avail', 'Total Sold']].sum().reset_index()
            fig_format = px.bar(format_agg, x="Format", y=["Total Avail", "Total Sold"], 
                             barmode="group", labels={'value': 'Volume', 'variable': 'Metric'})
            st.plotly_chart(fig_format, use_container_width=True)
            
    with chart_col2:
        st.write("**Available Stock: Style within Formats**")
        if 'Format' in dash_df.columns and 'Parent Style' in dash_df.columns and not dash_df.empty:
            sun_df = dash_df[dash_df['Total Avail'] > 0].copy()
            if not sun_df.empty:
                sun_df['Format'] = sun_df['Format'].fillna('Unknown Format').replace('', 'Unknown Format')
                sun_df['Parent Style'] = sun_df['Parent Style'].fillna('Unknown Style').replace('', 'Unknown Style')
                fig_sun = px.sunburst(sun_df, path=['Format', 'Parent Style'], values='Total Avail')
                st.plotly_chart(fig_sun, use_container_width=True)
            else:
                st.info("No available stock to display for selected locations.")


# --- TAB 2: BRAND / SUPPLIER ---
with tab_supplier:
    st.subheader("Inventory by Brand / Supplier")
    render_data_tab(df, primary_col="Brand", tab_id="sup")


# --- TAB 3: FORMAT ---
with tab_format:
    st.subheader("Inventory by Format")
    render_data_tab(df, primary_col="Format", tab_id="form")


# --- TAB 4: PARENT STYLE ---
with tab_style:
    st.subheader("Inventory by Parent Style")
    render_data_tab(df, primary_col="Parent Style", tab_id="style")


st.divider()
if st.button("Refresh Data from Google Sheets"):
    st.cache_data.clear()
    st.rerun()
