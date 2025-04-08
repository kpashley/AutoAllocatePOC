import streamlit as st
import pandas as pd
import datetime
import time
import plotly.express as px

# ------------------ Ship Allocation Logic ------------------

def allocate_ships(preferred_sailing_df, ship_availability_df, months, suez_closed, panama_closed, congestion_delays):
    seen_ships = set()
    ship_status = {}
    unassigned_ships = set()
    all_allocations = []

    for month in months:
        lob_demand = preferred_sailing_df.set_index(['LOB', 'Starting Region', 'Ending Region'])['Prefered Sailing pm'].to_dict()
        available_ships_now = set(ship_availability_df[ship_availability_df['MonthYear'] == month]['vesselcode'])
        new_ships = available_ships_now - seen_ships
        seen_ships.update(available_ships_now)

        returned_ships = {ship for ship, details in ship_status.items() if details['return_month'] == month}
        available_ships = new_ships | returned_ships | unassigned_ships
        busy_ships = {ship for ship, details in ship_status.items() if details['return_month'] > month}
        available_ships -= busy_ships

        available_ships_list = []
        for ship in available_ships:
            if ship in ship_status:
                start_region = ship_status[ship]['end_region']
            else:
                start_region = ship_availability_df.loc[ship_availability_df['vesselcode'] == ship, 'MappedRegion'].values[0]
            available_ships_list.append((ship, start_region))

        allocated_ships = []
        remaining_unassigned_ships = set(ship for ship, _ in available_ships_list)
        sorted_lob_keys = sorted(lob_demand.keys(), key=lambda k: lob_demand[k], reverse=True)

        for ship_name, ship_region in available_ships_list:
            assigned_lob = next((
                key for key in sorted_lob_keys
                if key[1] == ship_region and lob_demand.get(key, 0) > 0
            ), None)

            if assigned_lob:
                lob_key = assigned_lob[0]
                extra_days = congestion_delays.get(lob_key, 0)
                voyage_days = preferred_sailing_df[
                    (preferred_sailing_df['LOB'] == lob_key) & 
                    (preferred_sailing_df['Starting Region'] == assigned_lob[1]) & 
                    (preferred_sailing_df['Ending Region'] == assigned_lob[2])
                ]['Avg Voyage days']

                avg_voyage_days = int(voyage_days.values[0]) if not voyage_days.empty else 60

                if suez_closed and 'Suez' in lob_key:
                    avg_voyage_days += 14
                if panama_closed and 'Panama' in lob_key:
                    avg_voyage_days += 10
                avg_voyage_days += extra_days

                next_available_month_index = min(months.index(month) + (avg_voyage_days // 30), len(months) - 1)
                next_available_month = months[next_available_month_index]

                allocated_ships.append({
                    'Month': month,
                    'vesselcode': ship_name,
                    'Assigned_LOB': lob_key,
                    'Starting Region': assigned_lob[1],
                    'Ending Region': assigned_lob[2],
                })

                lob_demand[assigned_lob] -= 1
                remaining_unassigned_ships.discard(ship_name)
                ship_status[ship_name] = {'end_region': assigned_lob[2], 'return_month': next_available_month}

        unassigned_ships = remaining_unassigned_ships
        all_allocations.extend(allocated_ships)

    return pd.DataFrame(all_allocations)

# ------------------ Streamlit UI ------------------

st.set_page_config(page_title="Ship Allocation Tool", layout="wide")
st.title("🚢 Smart Ship Allocation")
st.markdown("Upload the required files below to get started:")

# Canal closures
suez_closed = st.checkbox("🚧 Suez Canal is closed")
panama_closed = st.checkbox("🚧 Panama Canal is closed")

# Congestion Delays
st.subheader("⚓ Port Congestion Delays (Optional)")
congestion_delays = {}
actual_lobs = [
    'TPW', 'HBR-C', 'LAS-ES', 'EXP-A', 'LAS-EN', 'HBR-U Suez', 'TAW', 'AGE',
    'TAE', 'UMR-E', 'BAJ', 'GIR-C', 'UMR-W', 'AAG', 'JAB', 'ESA-S',
    'GIR-U', 'HBR-U Panama', 'GIP', 'PACS'
]

with st.expander("🔧 Adjust Congestion Days"):
    cols = st.columns(3)
    for i, lob in enumerate(actual_lobs):
        with cols[i % 3]:
            congestion_delays[lob] = st.slider(f"{lob}", 0, 30, 0, key=f"delay_{lob}")

# Uploads
uploaded_files = st.file_uploader(
    "📄 Upload 3 Excel files (Preferred Sailing, Ship Availability, Acceptable Classes)",
    accept_multiple_files=True, type=['xlsx']
)

if len(uploaded_files) == 3:
    preferred_sailing_df = pd.read_excel(uploaded_files[0])
    ship_availability_df = pd.read_excel(uploaded_files[1])
    # Acceptable Classes file is uploaded, but not used in logic
    _ = pd.read_excel(uploaded_files[2])  # Placeholder

    months = ['2025-01', '2025-02', '2025-03', '2025-04', '2025-05', '2025-06']

    if st.button("🚀 Run Allocation"):
        with st.spinner("⏳ Allocating ships. Please wait..."):
            time.sleep(1)
            allocation_result = allocate_ships(
                preferred_sailing_df,
                ship_availability_df,
                months,
                suez_closed,
                panama_closed,
                congestion_delays
            )

        if not allocation_result.empty:
            st.success("✅ Allocation completed successfully!")

            # Chart 1: Total per LOB
            st.subheader("📊 Number of Allocations per LOB (Overall)")
            lob_count = allocation_result['Assigned_LOB'].value_counts().reset_index()
            lob_count.columns = ['LOB', 'Count']
            fig_bar = px.bar(lob_count, x='LOB', y='Count', text='Count', color='LOB')
            fig_bar.update_traces(texttemplate='%{text:.0f}', textposition='outside')
            fig_bar.update_layout(yaxis=dict(tickformat='d'), showlegend=False)
            st.plotly_chart(fig_bar, use_container_width=True)

            # Chart 2: Per LOB per Month
            st.subheader("📅 Number of Allocations per LOB per Month")
            lob_month_counts = allocation_result.groupby(['Month', 'Assigned_LOB']).size().reset_index(name='Count')
            fig_lob_month = px.bar(lob_month_counts, x='Month', y='Count', color='Assigned_LOB', barmode='group', text='Count')
            fig_lob_month.update_traces(texttemplate='%{text:.0f}', textposition='outside')
            fig_lob_month.update_layout(yaxis=dict(tickformat='d'))
            st.plotly_chart(fig_lob_month, use_container_width=True)

            # Chart 3: Region-to-Region routes
            st.subheader("🌍 Region-to-Region Allocation Counts")
            route_counts = allocation_result.groupby(['Starting Region', 'Ending Region']).size().reset_index(name='Count')
            route_counts['Route'] = route_counts['Starting Region'] + " ➞ " + route_counts['Ending Region']
            fig_routes = px.bar(route_counts, x='Route', y='Count', text='Count')
            fig_routes.update_traces(texttemplate='%{text:.0f}', textposition='outside')
            fig_routes.update_layout(xaxis_tickangle=-45, yaxis=dict(tickformat='d'))
            st.plotly_chart(fig_routes, use_container_width=True)

            # Heatmap Table
            st.subheader("🗺️ Heatmap: LOB vs Month Allocation")
            pivot = allocation_result.pivot_table(index='Assigned_LOB', columns='Month', values='vesselcode', aggfunc='count').fillna(0).astype(int)
            st.dataframe(pivot.style.format(precision=0).background_gradient(cmap='Blues'))

            # Download
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"Ship_Allocation_{timestamp}.xlsx"
            allocation_result.to_excel(filename, index=False)
            with open(filename, "rb") as f:
                st.download_button("📅 Download Allocation Excel File", data=f, file_name=filename, mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        else:
            st.warning("⚠️ No allocations could be made. Please check your data.")
else:
    st.info("👆 Please upload all three required Excel files to begin.")
