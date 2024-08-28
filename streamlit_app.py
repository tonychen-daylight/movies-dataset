import streamlit as st
import pandas as pd
import pulp

# Sidebar for input
st.sidebar.header('Trip History')
st.sidebar.date_input("Start Date", datetime.date(2024, 8, 6))

# Sample dataset
data = [
    {'Trip ID': 1, 'Start Date': '2023-11-01', 'End Date': '2023-11-02', 'Distance': 150, 'Duration': 5, 'Savings': 200},
    {'Trip ID': 2, 'Start Date': '2023-11-03', 'End Date': '2023-11-04', 'Distance': 200, 'Duration': 6, 'Savings': 300},
    {'Trip ID': 3, 'Start Date': '2023-11-05', 'End Date': '2023-11-06', 'Distance': 180, 'Duration': 4, 'Savings': 250}
]

# Initialize session state    
if 'tabs' not in st.session_state:
    st.session_state.tabs = []  # Store tab data as a list of dictionaries
if 'selected_tab' not in st.session_state:
    st.session_state.selected_tab = None
if 'scenario_exclusions' not in st.session_state:
    st.session_state.scenario_exclusions = {}  # Track exclusions per scenario

def run_optimization(min_savings, max_distance, max_duration, excluded_trip_ids):
    filtered_data = [trip for trip in data if trip['Trip ID'] not in excluded_trip_ids]
    filtered_data = [trip for trip in filtered_data if trip['Savings'] >= min_savings and trip['Distance'] <= max_distance and trip['Duration'] <= max_duration]

    model = pulp.LpProblem("TripOptimization", pulp.LpMaximize)
    trips = [trip['Trip ID'] for trip in filtered_data]
    x = pulp.LpVariable.dicts("Trip", trips, cat=pulp.LpBinary)

    model += pulp.lpSum([trip['Savings'] * x[trip['Trip ID']] for trip in filtered_data]) - \
             pulp.lpSum([trip['Distance'] * x[trip['Trip ID']] for trip in filtered_data]) - \
             pulp.lpSum([trip['Duration'] * x[trip['Trip ID']] for trip in filtered_data])

    model += pulp.lpSum([x[trip['Trip ID']] for trip in filtered_data]) <= 2

    model.solve()

    results = {
        'Trip ID': [],
        'Selected': [],
        'Savings': [],
        'Distance': [],
        'Duration': []
    }

    for trip in filtered_data:
        results['Trip ID'].append(trip['Trip ID'])
        results['Selected'].append(x[trip['Trip ID']].value())
        results['Savings'].append(trip['Savings'])
        results['Distance'].append(trip['Distance'])
        results['Duration'].append(trip['Duration'])

    results_df = pd.DataFrame(results)

    excluded_data = [trip for trip in data if trip['Trip ID'] in excluded_trip_ids]
    excluded_df = pd.DataFrame(excluded_data)

    combined_df = pd.concat([results_df, excluded_df.rename(columns=lambda x: f"Excluded_{x}")], axis=1)

    return results_df, excluded_df, combined_df, pulp.LpStatus[model.status], pulp.value(model.objective)

# Sidebar for input
st.sidebar.header('Filter Criteria')

min_savings = st.sidebar.number_input('Minimum Savings', min_value=0, value=0, key='min_savings')
max_distance = st.sidebar.number_input('Maximum Distance', min_value=0, value=1000, key='max_distance')
max_duration = st.sidebar.number_input('Maximum Duration', min_value=0, value=1000, key='max_duration')

# Radio button to select tab
tab_titles = [tab['title'] for tab in st.session_state.tabs] if st.session_state.tabs else ['No Scenario']
selected_tab = st.sidebar.radio("Select Scenario", options=tab_titles)

# Update selected tab in session state
st.session_state.selected_tab = selected_tab

# Determine available exclusions based on the selected tab
if selected_tab and selected_tab != 'No Scenario':
    selected_tab_data = next((tab for tab in st.session_state.tabs if tab['title'] == selected_tab), None)
    if selected_tab_data:
        available_trips = [trip['Trip ID'] for trip in data]
        current_scenario_exclusions = [trip['Trip ID'] for trip in selected_tab_data['excluded_data'].to_dict('records')]
    else:
        available_trips = [trip['Trip ID'] for trip in data]
        current_scenario_exclusions = []
else:
    available_trips = [trip['Trip ID'] for trip in data]
    current_scenario_exclusions = []

# Multiselect widget for trip exclusions
# Show all available trips and pre-select the currently excluded ones
selected_excluded_trip_ids = st.sidebar.multiselect(
    'Select trips to exclude',
    options=available_trips,
    default=current_scenario_exclusions,
    key='exclude_trips'
)

# Update the session state with the selected exclusions for the current scenario
if selected_tab:
    st.session_state.scenario_exclusions[selected_tab] = list(set(selected_excluded_trip_ids))

# Run Scenario button
if st.sidebar.button('Run Scenario', key='run_scenario'):
    if selected_tab and selected_tab != 'No Scenario':
        # Fetch data from the selected tab and include exclusions
        selected_tab_data = next((tab for tab in st.session_state.tabs if tab['title'] == selected_tab), None)
        if selected_tab_data:
            previous_exclusions = [trip['Trip ID'] for trip in selected_tab_data['excluded_data'].to_dict('records')]
            combined_exclusions = list(set(previous_exclusions + selected_excluded_trip_ids))
            filtered_data = [trip for trip in selected_tab_data['filtered_data'] if trip['Trip ID'] not in combined_exclusions]
            filtered_data = [trip for trip in filtered_data if trip['Savings'] >= min_savings and trip['Distance'] <= max_distance and trip['Duration'] <= max_duration]
        else:
            filtered_data = data
    else:
        filtered_data = data

    # Apply filter criteria
    filtered_data = [trip for trip in filtered_data if trip['Savings'] >= min_savings and trip['Distance'] <= max_distance and trip['Duration'] <= max_duration]
    
    results_df, excluded_df, combined_df, status, total_savings = run_optimization(
        min_savings,
        max_distance,
        max_duration,
        st.session_state.scenario_exclusions.get(selected_tab, [])
    )

    # Add results to tabs at the beginning of the list
    tab_title = f"Scenario {len(st.session_state.tabs) + 1}"
    st.session_state.tabs.insert(0, {
        'title': tab_title,
        'filtered_data': filtered_data,
        'excluded_data': pd.DataFrame([trip for trip in data if trip['Trip ID'] in st.session_state.scenario_exclusions.get(selected_tab, [])]),
        'combined_df': combined_df,
        'status': status,
        'total_savings': total_savings
    })

    # Set the newly created tab as the selected tab
    st.session_state.selected_tab = tab_title

    # Force a rerun to ensure the new tab is selected
    st.rerun(scope="app")

# Display all tabs using st.tabs
if st.session_state.tabs:
    tab_titles = [tab['title'] for tab in st.session_state.tabs]
    if st.session_state.selected_tab not in tab_titles:
        st.session_state.selected_tab = tab_titles[0]  # Default to the first tab if the current one is not found

    selected_tab = st.session_state.selected_tab
    selected_tab_data = next((tab for tab in st.session_state.tabs if tab['title'] == selected_tab), None)
    if selected_tab_data:
        st.header(f"Results for {selected_tab}")
        st.write("Filtered Data (Excluding Specified Trips):")
        st.write(pd.DataFrame(selected_tab_data['filtered_data']))
        st.write("Excluded Trips:")
        st.write(pd.DataFrame(selected_tab_data['excluded_data']))
        st.write("Optimization Results:")
        st.write(pd.DataFrame(selected_tab_data['combined_df']))
        st.write(f"Status: {selected_tab_data['status']}")
        if selected_tab_data['status'] == 'Optimal':
            st.write(f"Total Savings: {selected_tab_data['total_savings']}")
        else:
            st.write("No feasible solution found.")
        
        csv = selected_tab_data['combined_df'].to_csv(index=False)
        st.download_button(
            label="Download Results as CSV", 
            data=csv, 
            file_name=f"{selected_tab}.csv", 
            mime='text/csv'
        )

