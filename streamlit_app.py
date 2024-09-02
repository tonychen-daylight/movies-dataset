import streamlit as st
import pandas as pd
import pulp
import datetime
import requests

# Trip History
st.logo("data/dylt-logo-header.png",link="https://www.dylt.com/",
    icon_image="data/logo-sm.svg")
st.sidebar.header('Step 1:Trip History')
container = st.sidebar.container(border=True)
container.date_input("Start Date", datetime.date(2024, 6, 1))
container.date_input("End Date", datetime.datetime.now())
#container.button("Pull Strip", type="secondary")
  
# Trip Matching
st.sidebar.header('Step 2: Find Matching Trips')
container1 = st.sidebar.container(border=True)
min_distance1 = container1.number_input('Min Distance (miles)', min_value=0, value=2000, key='min_distance1')
max_distance1 = container1.number_input('Max Distance (miles)', min_value=0, value=58000, key='max_distance1')
#min_savings1 = container1.number_input('Min Savings($)', min_value=0, value=-100, key='min_savings1')
max_distance71 = container1.number_input('Max Distance7 (miles)', min_value=0, value=58000, key='max_distance71')
max_idle_time1 = container1.number_input('Max Idle Time (days)', min_value=0, value=1, key='max_idle_time1')
max_durations = container1.number_input('Max Duration (days)', min_value=0, value=8, key='max_durations')
container1.button("Trip Matching", type="secondary")

# Sample dataset
data = [
    {'Trip ID': 1, 'Start Date': '2023-11-01', 'End Date': '2023-11-02', 'Distance': 150, 'Duration': 5, 'Savings': 200},
    {'Trip ID': 2, 'Start Date': '2023-11-03', 'End Date': '2023-11-04', 'Distance': 200, 'Duration': 6, 'Savings': 300},
    {'Trip ID': 3, 'Start Date': '2023-11-05', 'End Date': '2023-11-06', 'Distance': 180, 'Duration': 4, 'Savings': 250}
]

# Initialize session state    
if 'trip_history' not in st.session_state:
    st.session_state.last_updated = datetime.time(0,0)
    st.session_state.trip_history = []
if 'tabs' not in st.session_state:
    st.session_state.tabs = []  # Store tab data as a list of dictionaries
if 'selected_tab' not in st.session_state:
    st.session_state.selected_tab = None
if 'scenario_exclusions' not in st.session_state:
    st.session_state.scenario_exclusions = {}  # Track exclusions per scenario
    
def getToken():
    url = "https://test-api.dylt.com/oauth/client_credential/accesstoken?grant_type=client_credentials"
    payload = "client_id=Dlcn9SvNNpk2JDGuAsujc2vCkhcSDGjZ&client_secret=ooQ2nWOSqT63AMcH"
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    response = requests.request("POST", url, headers=headers, data=payload)
    print(f'Token: {response.json().get("access_token")}')
    return response.json().get("access_token")
    
def getTripHstory(startDate, endDate):
    url = "https://Boomi-Elast-JHFRIO4ZPHFF-53644198.us-west-1.elb.amazonaws.com:9093/ws/simple/getTripHistory"
    payload = "<tripHistoryReq>\r\n <startDate>2024-06-01</startDate>\r\n <endDate>2024-06-10</endDate>\r\n</tripHistoryReq>"
    headers = {
      'Content-Type': 'application/xml'
    }

    response = requests.request("POST", url, headers=headers, data=payload)
    return (response.text)
    
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

# Get Trip History
st.header(":blue[Trip Optimization Dashboard]")
st.subheader("Trip History Information", divider=True)
if container.button("Get Trip History", type="secondary"):
    token =  getToken()
    #st.write(token)
    url = "https://dev-api.dylt.com/myDaylight/v1/shipments/tripHistory/06-01-2024"
    payload = {}
    headers = {
       'Authorization': 'Bearer ' + token
    }
    response = requests.request("GET", url, headers=headers, data=payload)
    tripHistory = response.json().get("items")
    st.session_state.trip_history = tripHistory
    st.session_state.last_updated = datetime.datetime.now()

st.dataframe(st.session_state.trip_history, width=1000, height=400)
st.write("Last fetched:",  st.session_state.last_updated)
st.divider()

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

