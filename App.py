import streamlit as st
import pandas as pd
import datetime
import time

def allocate_ships(preferred_sailing_df, ship_availability_df, acceptable_classes_df, months, suez_closed, panama_closed, congestion_delays):
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
            ship_class = ship_availability_df.loc[ship_availability_df['vesselcode'] == ship_name, 'Class'].values[0]
            assigned_lob = next((
                key for key in sorted_lob_keys 
                if key[1] == ship_region and lob_demand.get(key, 0) > 0 and
                ship_class in acceptable_classes_df.get(key[0], [])
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
                    'Voyage Days': avg_voyage_days
                })

                lob_demand[assigned_lob] -= 1
                remaining_unassigned_ships.discard(ship_name)
                ship_status[ship_name] = {'end_region': assigned_lob[2], 'return_month': next_available_month}

        unassigned_ships = remaining_unassigned_ships
        all_allocations.extend(allocated_ships)

    return pd.DataFrame(all_allocations)


# ---------- Streamlit App Starts Here ----------

st.set_page_config(page_title="Ship Allocation Tool", layout="wide")
st.title("🚢 Smart Ship Allocation POC")

st.markdown("Upload the required data files below to get started:")

# Always visible
suez_closed = st.checkbox("🚧 Suez Canal is closed")
panama_closed = st.checkbox("🚧 Panama Canal is closed")

# Show port congestion sliders before file upload
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

uploaded_files = st.file_uploader("📤 Upload 3 Excel files (Preferred Sailing, Ship Availability, Acceptable Classes)", accept_multiple_files=True, type=['xlsx'])

if len(uploaded_files) == 3:
    preferred_sailing_df = pd.read_excel(uploaded_files[0])
    ship_availability_df = pd.read_excel(uploaded_files[1])
    acceptable_classes_df = pd.read_excel(uploaded_files[2])
    acceptable_classes_df = acceptable_classes_df.set_index('LOB')['Class'].to_dict()

    months = ['2025-01', '2025-02', '2025-03', '2025-04', '2025-05', '2025-06']

    if st.button("🚀 Run Allocation"):
        with st.spinner("⏳ Allocating ships. Please wait..."):
            time.sleep(1)  # Simulate delay
            allocation_result = allocate_ships(preferred_sailing_df, ship_availability_df, acceptable_classes_df, months, suez_closed, panama_closed, congestion_delays)

        if not allocation_result.empty:
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"Ship_Allocation_{timestamp}.xlsx"
            allocation_result.to_excel(filename, index=False)

            st.success("✅ Allocation completed successfully!")
            st.dataframe(allocation_result)

            with open(filename, "rb") as f:
                st.download_button(label="📥 Download Allocation Excel File", data=f, file_name=filename, mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        else:
            st.warning("⚠️ No allocations could be made. Please check your data.")
else:
    st.info("👆 Please upload all three required Excel files to begin.")
