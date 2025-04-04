import streamlit as st
import pandas as pd
import datetime

def allocate_ships(preferred_sailing_df, ship_availability_df, acceptable_classes_df, months):
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
                allocated_ships.append({
                    'Month': month,
                    'vesselcode': ship_name,
                    'Assigned_LOB': assigned_lob[0],
                    'Starting Region': assigned_lob[1],
                    'Ending Region': assigned_lob[2]
                })
                lob_demand[assigned_lob] -= 1
                remaining_unassigned_ships.discard(ship_name)
                voyage_days = preferred_sailing_df[
                    (preferred_sailing_df['LOB'] == assigned_lob[0]) & 
                    (preferred_sailing_df['Starting Region'] == assigned_lob[1]) & 
                    (preferred_sailing_df['Ending Region'] == assigned_lob[2])
                ]['Avg Voyage days']
                avg_voyage_days = int(voyage_days.values[0]) if not voyage_days.empty else 60
                next_available_month_index = min(months.index(month) + (avg_voyage_days // 30), len(months) - 1)
                next_available_month = months[next_available_month_index]
                ship_status[ship_name] = {'end_region': assigned_lob[2], 'return_month': next_available_month}

        unassigned_ships = remaining_unassigned_ships
        all_allocations.extend(allocated_ships)

    return pd.DataFrame(all_allocations)

# Streamlit App
st.title("🚢 Ship Allocation Tool")

uploaded_files = st.file_uploader("Upload 3 Excel files: Preferred Sailing, Ship Availability, Acceptable Classes", accept_multiple_files=True, type=['xlsx'])

if len(uploaded_files) == 3:
    preferred_sailing_df = pd.read_excel(uploaded_files[0])
    ship_availability_df = pd.read_excel(uploaded_files[1])
    acceptable_classes_df = pd.read_excel(uploaded_files[2])
    
    acceptable_classes_df = acceptable_classes_df.set_index('LOB')['Class'].to_dict()
    months = ['2025-01', '2025-02', '2025-03', '2025-04', '2025-05', '2025-06']
    
    allocation_result = allocate_ships(preferred_sailing_df, ship_availability_df, acceptable_classes_df, months)
    
    if not allocation_result.empty:
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"Ship_Allocation_{timestamp}.xlsx"
        allocation_result.to_excel(filename, index=False)
        st.success("✅ Allocation Completed!")
        st.download_button(label="📥 Download Allocation File", data=open(filename, "rb"), file_name=filename)