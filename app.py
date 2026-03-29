import streamlit as st
import pandas as pd
from streamlit_gsheets import GSheetsConnection
import plotly.express as px

# Set page config for a wider layout
st.set_page_config(page_title="Inventory Dashboard", layout="wide")

# Inject custom CSS to reduce the global font size and make the app tighter
st.markdown("""
    <style>
        html, body,[class*="css"] {
            font-size: 14px; 
        }
    </style>
""", unsafe_allow_html=True)

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
            
    # Clean Prices and RENAME column to "Price"
    if 'Sales Price (Price Tier 1)' in df.columns:
        df['Sales Price (Price Tier 1)'] = pd.to_numeric(
            df['Sales Price (Price Tier 1)'].astype(str).str.replace(r'[£$,]', '', regex=True), errors='coerce'
        )
        df.rename(columns={'Sales Price (Price Tier 1)': 'Price'}, inplace=True)
        
    # Clean ABV
    if 'ABV' in df.columns:
        df['ABV'] = pd.to_numeric(
            df['ABV'].astype(str).str.replace(r'[%]', '', regex=True), errors='coerce'
        )
        
    # Ignore "service" locations
    if 'Default Location' in df.columns:
        df = df[df['Default Location'].fillna('').str.lower() != 'service']
        
    # Select our specific required columns (using Price instead of the old name)
    core_columns =[
        'Group by SKU', 'Brand', 'Product Name', 'Group', 'Parent Style', 
        'Format Type', 'Format', 'Size', 'ABV', 'Price', 
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
        format_order =['Cask', 'Keg', 'Cans', 'Bottles', 'Bag in Box', 'Other']
        existing_formats = df['Format'].dropna().unique().tolist()
        final_format_order = format_order +[f for f in existing_formats if f not in format_order]
        
        # Apply categorical sorting for the Format column
        df['Format'] = pd.Categorical(df['Format'], categories=final_format_order, ordered=True)
        
    # Sort the dataframe: Brand -> Format (custom order) -> Product Name
    sort_cols = [c for c in ['Brand', 'Format', 'Product Name'] if c in df.columns]
    if sort_cols:
        df = df.sort_values(by=sort_cols, ascending=[True] * len(sort_cols))
        
    # Convert Format back to a string so filters work cleanly
    if 'Format' in df.columns:
        df['Format'] = df['Format'].astype(str).replace('nan', '')
            
    return df

df = load_data()


# ---------------------------------------------------------
# Helper Function 1: Handle Dynamic Location Logic
# ---------------------------------------------------------
def apply_location_toggles(data, ldn_active, glo_active):
    df_loc = data.copy()
    
    df_loc['Total OH'] = (df_loc.get('LDN OH', 0) if ldn_active else 0) + (df_loc.get('GLO OH', 0) if glo_active else 0)
    df_loc['Total Avail'] = (df_loc.get('LDN Avail', 0) if ldn_active else 0) + (df_loc.get('GLO Avail', 0) if glo_active else 0)
    df_loc['Total Sold'] = (df_loc.get('LDN Sold', 0) if ldn_active else 0) + (df_loc.get('GLO Sold', 0) if glo_active else 0)
    
    # Filter out items where the active locations have exactly 0 stock
    df_loc = df_loc[df_loc['Total OH'] > 0]
    
    # Drop columns for inactive locations
    cols_to_drop =[]
    if not ldn_active: cols_to_drop.extend(['LDN OH', 'LDN Avail', 'LDN Sold'])
    if not glo_active: cols_to_drop.extend(['GLO OH', 'GLO Avail', 'GLO Sold'])
    
    return df_loc.drop(columns=[c for c in cols_to_drop if c in df_loc.columns])


# ---------------------------------------------------------
# Helper Function 2: Render Styled Data Table
# ---------------------------------------------------------
def render_inventory_table(data):
    # DROP columns we don't want to show on screen to save horizontal space
    cols_to_hide = ['Format', 'Default Location']
    display_df = data.drop(columns=[c for c in cols_to_hide if c in data.columns])

    def style_depot_columns(col):
        if 'LDN' in col.name: return['background-color: rgba(0, 150, 255, 0.15)'] * len(col) 
        elif 'GLO' in col.name: return['background-color: rgba(0, 200, 100, 0.15)'] * len(col) 
        elif 'Total' in col.name: return['background-color: rgba(255, 165, 0, 0.15)'] * len(col) 
        else: return [''] * len(col)

    format_dict = {}
    inventory_cols =['LDN Sold', 'LDN Avail', 'LDN OH', 'GLO Sold', 'GLO Avail', 'GLO OH', 'Total OH', 'Total Avail', 'Total Sold']
    for col in inventory_cols:
        if col in display_df.columns: format_dict[col] = "{:,.0f}"

    if 'Price' in display_df.columns: format_dict['Price'] = "{:,.2f}"
    if 'ABV' in display_df.columns: format_dict['ABV'] = "{:.1f}"

    # Apply colors and reduce the font size of the table specifically to 12px
    styled_df = (display_df.style
                 .apply(style_depot_columns, axis=0)
                 .set_properties(**{'font-size': '12px'})
                 .format(format_dict, na_rep=""))
    
    # st.dataframe with column_config to squeeze the SKU column
    st.dataframe(
        styled_df, 
        use_container_width=True, 
        hide_index=True,
        column_config={
            "Group by SKU": st.column_config.TextColumn(
                "SKU",
                width="small",  # Forces it to be narrow
                help="Double click cell to copy SKU"
            )
        }
    )


# ---------------------------------------------------------
# UI Layout: Tabs Setup
# ---------------------------------------------------------
tab_dash, tab_data = st.tabs(["📊 Dashboard", "🗄️ Inventory Data"])

# --- TAB 1: DASHBOARD ---
with tab_dash:
    st.subheader("High-Level Inventory Overview")
    
    st.write("**Select Depot Locations**")
    col_t1, col_t2 = st.columns(2)
    with col_t1: dash_ldn = st.checkbox("Include LDN (London)", value=True, key="dash_ldn")
    with col_t2: dash_glo = st.checkbox("Include GLO (Gloucester)", value=True, key="dash_glo")
        
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


# --- TAB 2: INVENTORY DATA EXPLORER ---
with tab_data:
    st.subheader("Granular Data Explorer")
    
    st.write("**1. Select Depot Locations**")
    col_l1, col_l2 = st.columns(2)
    with col_l1: data_ldn = st.checkbox("Include LDN (London)", value=True, key="data_ldn")
    with col_l2: data_glo = st.checkbox("Include GLO (Gloucester)", value=True, key="data_glo")
    
    # Apply toggles
    tab_df = apply_location_toggles(df, data_ldn, data_glo)
    
    if tab_df.empty:
        st.warning("No inventory available for the selected locations.")
    else:
        st.write("**2. Drill Down Data**")
        col1, col2, col3, col4 = st.columns(4)
        
        # Brand Filter
        with col1:
            if 'Brand' in tab_df.columns:
                options_brand = sorted([str(x) for x in tab_df['Brand'].unique() if pd.notna(x) and str(x).strip() != ''])
                sel_brand = st.multiselect("Supplier / Brand", options=options_brand)
                if sel_brand: tab_df = tab_df[tab_df['Brand'].isin(sel_brand)]
                
        # Format Filter
        with col2:
            if 'Format' in tab_df.columns:
                options_format = sorted([str(x) for x in tab_df['Format'].unique() if pd.notna(x) and str(x).strip() != ''])
                sel_format = st.multiselect("Format", options=options_format)
                if sel_format: tab_df = tab_df[tab_df['Format'].isin(sel_format)]
                
        # Style Filter
        with col3:
            if 'Parent Style' in tab_df.columns:
                options_style = sorted([str(x) for x in tab_df['Parent Style'].unique() if pd.notna(x) and str(x).strip() != ''])
                sel_style = st.multiselect("Parent Style", options=options_style)
                if sel_style: tab_df = tab_df[tab_df['Parent Style'].isin(sel_style)]
                
        # Price Filter
        with col4:
            if 'Price' in tab_df.columns:
                valid_prices = tab_df['Price'].dropna()
                if not valid_prices.empty:
                    min_p = float(valid_prices.min())
                    max_p = float(valid_prices.max())
                    if min_p < max_p:
                        price_range = st.slider("Price Range", min_value=min_p, max_value=max_p, value=(min_p, max_p), format="£%f")
                        in_range = tab_df['Price'].between(price_range[0], price_range[1])
                        is_nan = tab_df['Price'].isna()
                        tab_df = tab_df[in_range | is_nan]
                    elif min_p == max_p:
                        st.write(f"**Price Range:** £{min_p:,.2f}")
                        
        st.divider()
        # Render the final clean table
        render_inventory_table(tab_df)


st.divider()
if st.button("Refresh Data from Google Sheets"):
    st.cache_data.clear()
    st.rerun()
