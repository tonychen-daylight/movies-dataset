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
min_savings1 = container1.number_input('Min Savings($)', min_value=0, value=0, key='min_savings1')
max_distance71 = container1.number_input('Max Distance7 (miles)', min_value=0, value=58000, key='max_distance71')
max_idle_time1 = container1.number_input('Max Idle Time (days)', min_value=0, value=1, key='max_idle_time1')
max_durations = container1.number_input('Max Duration (days)', min_value=0, value=8, key='max_durations')
#container1.button("Trip Matching", type="secondary")

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

def data_cleanup():
    # Load the CSV file
    #scsv = FilePicker1.files[0].readContents()
    #f = StringIO(scsv)
    #df = pd.read_csv(f)
    df_copy = st.session_state.trip_history
    st.write(df_copy)
    # Convert 'dispatch' and 'arrival' to datetime
    #df_copy["dispatch"] = pd.to_datetime(df_copy["dispatch"], errors="coerce")
    #df_copy["arrival"] = pd.to_datetime(df_copy["arrival"], errors="coerce")

    # Add 'WeekDay' column
    df_copy["WeekDay"] = df_copy["dispatch"].dt.day_name()
    return df_copy
    
def deduct_costs(df_copy):
    # Get unique origins and destinations
    origins = df_copy["origin"].unique().astype(str)
    destinations = df_copy["destination"].unique().astype(str)
    terminals = np.unique(
        np.concatenate((origins, destinations))
    )  # Includes both origins and destinations
    weeks = np.sort(df_copy["weeknumber"].unique())

    # Ded cost list initialization
    ded_cost_list = pd.DataFrame(columns=["origin", "destination", "DedCost"])

    # Filtering condition for ded cost average
    ded_cost_average_condition = df_copy["equipment"].isin(
        ["LTL-DED", "LTL-Fleet", "LTL-Wild"]
    )

    # Populate ded_cost_list with average costs
    for origin_each in terminals:
        for destination_each in terminals:
            if origin_each != destination_each:
                condition = (
                    (df_copy["origin"] == origin_each)
                    & (df_copy["destination"] == destination_each)
                    & ded_cost_average_condition
                )
                if condition.any():
                    get_avcost = df_copy.loc[condition, "cpm"].mean()
                else:
                    get_avcost = df_copy.loc[ded_cost_average_condition, "cpm"].mean()
                ded_cost_new_row = pd.DataFrame(
                    {
                        "origin": [origin_each],
                        "destination": [destination_each],
                        "DedCost": [get_avcost],
                    }
                )
                ded_cost_list = pd.concat(
                    [ded_cost_list, ded_cost_new_row], ignore_index=True
                )
    ded_costs = ded_cost_list
    return ded_costs

def trip_matching(
    minDistance,
    maxDistance,
    minSaving,
    maxDistance7,
    maxidletime,
    max_duration,
    start_date,
):
    df_copy = data_cleanup()
    df_copy["weeknumber"] = (
        df_copy["dispatch"] - pd.to_datetime(start_date)
    ).dt.days // 7

    # Get unique origins and destinations
    origins = df_copy["origin"].unique().astype(str)
    destinations = df_copy["destination"].unique().astype(str)
    terminals = np.unique(
        np.concatenate((origins, destinations))
    )  # Includes both origins and destinations
    weeks = np.sort(df_copy["weeknumber"].unique())

    ded_costs = deduct_costs(df_copy)

    # Remove non-LTL-1way services
    df_copy = df_copy[df_copy["equipment"] == "LTL- 1way"]
    df_copy = df_copy.reset_index(drop=True)

    # Initialize Matched_Trips DataFrame
    Matched_Trips = pd.DataFrame(
        columns=[
            "WeekDay",
            "WeekDayMatch",
            "WeekDayMatch2",
            "WeekNumber",
            "WeekNumber_Match",
            "WeekNumber_Match2",
            "terminal1",
            "terminal2",
            "terminal3",
            "TripNumber1",
            "TripNumber2",
            "TripNumber3",
            "TotalDistance",
            "TripSchedule",
            "TotalOldCost",
            "TotalNewCost",
            "CostSaving",
            "TravelTime",
            "Dispatch1",
            "Arrival1",
            "Dispatch2",
            "Arrival2",
            "Dispatch3",
            "Arrival3",
            "TripSchedule1",
            "TripSchedule2",
            "TripSchedule3",
            "Carrier1",
            "Carrier2",
            "Carrier3",
        ]
    )

    row_nb = 1

    for w in range(len(weeks) - 1):
        week_now = weeks[w]
        week_n2 = weeks[w + 1]
        week_n3 = week_n2 + 1

        for i in range(len(origins)):
            origin_current = origins[i]

            for j in range(len(destinations)):
                destination_current = destinations[j]

                origin_destination_index = df_copy[
                    (df_copy["origin"] == origin_current)
                    & (df_copy["destination"] == destination_current)
                    & (df_copy["weeknumber"] == week_now)
                ].index.tolist()

                if (origin_current != destination_current) and (
                    len(origin_destination_index) > 0
                ):
                    for g in range(len(origin_destination_index)):
                        for h in range(len(terminals)):
                            trip2_index = df_copy[
                                (
                                    (df_copy["origin"] == destination_current)
                                    & (df_copy["destination"] == terminals[h])
                                )
                                & (
                                    (df_copy["weeknumber"] == week_now)
                                    | (df_copy["weeknumber"] == week_n2)
                                    | (df_copy["weeknumber"] == week_n3)
                                )
                            ].index
                            trip3_index = df_copy[
                                (
                                    (df_copy["origin"] == terminals[h])
                                    & (df_copy["destination"] == origin_current)
                                )
                                & (
                                    (df_copy["weeknumber"] == week_now)
                                    | (df_copy["weeknumber"] == week_n2)
                                    | (df_copy["weeknumber"] == week_n3)
                                )
                            ].index

                            trip2_options = len(trip2_index)
                            trip3_options = len(trip3_index)

                            cand_row = 0
                            if (
                                len(trip2_index) > 0
                                and len(trip3_index) > 0
                                and terminals[h]
                                not in [destination_current, origin_current]
                            ):
                                for t2 in range(trip2_options):
                                    for t3 in range(trip3_options):
                                        trip_nb1 = df_copy.loc[
                                            origin_destination_index[g], "trip_number"
                                        ]
                                        trip_nb2 = df_copy.loc[
                                            trip2_index[t2], "trip_number"
                                        ]
                                        trip_nb3 = df_copy.loc[
                                            trip3_index[t3], "trip_number"
                                        ]

                                        row_1 = df_copy[
                                            df_copy["trip_number"] == trip_nb1
                                        ].index[0]
                                        row_2 = df_copy[
                                            df_copy["trip_number"] == trip_nb2
                                        ].index[0]
                                        row_3 = df_copy[
                                            df_copy["trip_number"] == trip_nb3
                                        ].index[0]

                                        TotalDistance = (
                                            df_copy.loc[
                                                origin_destination_index[g], "distance"
                                            ]
                                            + df_copy.loc[trip2_index[t2], "distance"]
                                            + df_copy.loc[trip3_index[t3], "distance"]
                                        )
                                        # TripSchedule = df_copy.loc[row_1, 'route_description']
                                        TripSchedule = ""

                                        # Get costs of round trips vs one-ways
                                        cost_trip1 = ded_costs[
                                            (ded_costs["origin"] == origin_current)
                                            & (
                                                ded_costs["destination"]
                                                == destination_current
                                            )
                                        ]["DedCost"].values[0]
                                        cost_trip2 = ded_costs[
                                            (ded_costs["origin"] == destination_current)
                                            & (ded_costs["destination"] == terminals[h])
                                        ]["DedCost"].values[0]
                                        cost_trip3 = ded_costs[
                                            (ded_costs["origin"] == terminals[h])
                                            & (
                                                ded_costs["destination"]
                                                == origin_current
                                            )
                                        ]["DedCost"].values[0]

                                        total_cost_1way = (
                                            df_copy.loc[
                                                origin_destination_index[g], "distance"
                                            ]
                                            * df_copy.loc[g, "cpm"]
                                            + df_copy.loc[trip3_index[t3], "distance"]
                                            * df_copy.loc[trip3_index[t3], "cpm"]
                                            + df_copy.loc[trip2_index[t2], "distance"]
                                            * df_copy.loc[trip2_index[t2], "cpm"]
                                        )
                                        total_cost_loop = (
                                            df_copy.loc[
                                                origin_destination_index[g], "distance"
                                            ]
                                            * cost_trip1
                                            + df_copy.loc[trip2_index[t2], "distance"]
                                            * cost_trip2
                                            + df_copy.loc[trip3_index[t3], "distance"]
                                            * cost_trip3
                                        )

                                        tour_savings = total_cost_1way - total_cost_loop

                                        if (
                                            tour_savings > minSaving
                                            and TotalDistance < maxDistance7
                                        ):
                                            trip1_arrival = df_copy.loc[
                                                row_1, "arrival"
                                            ]
                                            trip2_dispatch = df_copy.loc[
                                                row_2, "dispatch"
                                            ]
                                            trip2_arrival = df_copy.loc[
                                                row_2, "arrival"
                                            ]
                                            trip3_dispatch = df_copy.loc[
                                                row_3, "dispatch"
                                            ]

                                            gap1 = (
                                                trip2_dispatch - trip1_arrival
                                            ).days + (
                                                trip2_dispatch - trip1_arrival
                                            ).seconds / 86400
                                            gap2 = (
                                                trip3_dispatch - trip2_arrival
                                            ).days + (
                                                trip3_dispatch - trip2_arrival
                                            ).seconds / 86400

                                            travel_days = (
                                                df_copy.loc[row_3, "arrival"]
                                                - df_copy.loc[row_1, "dispatch"]
                                            ).seconds / 86400 + (
                                                df_copy.loc[row_3, "arrival"]
                                                - df_copy.loc[row_1, "dispatch"]
                                            ).days
                                            if travel_days > 7:
                                                distance_limit = maxDistance7
                                            else:
                                                distance_limit = maxDistance

                                            if (
                                                gap1 >= 0
                                                and gap1 <= maxidletime
                                                and gap2 >= 0
                                                and gap2 <= maxidletime
                                            ):
                                                if (
                                                    TotalDistance >= minDistance
                                                    and TotalDistance <= distance_limit
                                                    and travel_days <= max_duration
                                                ):
                                                    # original_ser_hub = df_copy.loc[row_1, 'equipment']
                                                    # original_ser_prime = df_copy.loc[row_3, 'equipment']
                                                    # original_ser_2 = df_copy.loc[row_2, 'equipment']

                                                    WeekNumber_1 = df_copy.loc[
                                                        row_1, "weeknumber"
                                                    ]
                                                    WeekNumber_2 = df_copy.loc[
                                                        row_2, "weeknumber"
                                                    ]
                                                    WeekNumber_3 = df_copy.loc[
                                                        row_3, "weeknumber"
                                                    ]

                                                    weekday_1 = df_copy.loc[
                                                        row_1, "WeekDay"
                                                    ]
                                                    weekday_2 = df_copy.loc[
                                                        row_2, "WeekDay"
                                                    ]
                                                    weekday_3 = df_copy.loc[
                                                        row_3, "WeekDay"
                                                    ]

                                                    # TripSchedule_1 = df_copy.loc[row_1, 'route_description']
                                                    # TripSchedule_2 = df_copy.loc[row_2, 'route_description']
                                                    # TripSchedule_3 = df_copy.loc[row_3, 'route_description']

                                                    TripSchedule_1 = ""
                                                    TripSchedule_2 = ""
                                                    TripSchedule_3 = ""

                                                    Carrier_1 = df_copy.loc[
                                                        row_1, "carrier"
                                                    ]
                                                    Carrier_2 = df_copy.loc[
                                                        row_2, "carrier"
                                                    ]
                                                    Carrier_3 = df_copy.loc[
                                                        row_3, "carrier"
                                                    ]

                                                    # Add Linehaul day and Linehaul day of week here

                                                    terminal3 = terminals[h]

                                                    # Dates
                                                    dispatch1 = df_copy.loc[
                                                        row_1, "dispatch"
                                                    ].strftime("%m/%d/%Y %H:%M")
                                                    arrival1 = df_copy.loc[
                                                        row_3, "arrival"
                                                    ].strftime("%m/%d/%Y %H:%M")

                                                    dispatch2 = trip2_dispatch.strftime(
                                                        "%m/%d/%Y %H:%M"
                                                    )
                                                    arrival2 = trip1_arrival.strftime(
                                                        "%m/%d/%Y %H:%M"
                                                    )

                                                    dispatch3 = trip3_dispatch.strftime(
                                                        "%m/%d/%Y %H:%M"
                                                    )
                                                    arrival3 = trip2_arrival.strftime(
                                                        "%m/%d/%Y %H:%M"
                                                    )

                                                    Matched_Trips.loc[row_nb, :] = [
                                                        weekday_1,
                                                        weekday_2,
                                                        weekday_3,
                                                        WeekNumber_1,
                                                        WeekNumber_2,
                                                        WeekNumber_3,
                                                        origin_current,
                                                        destination_current,
                                                        terminal3,
                                                        trip_nb1,
                                                        trip_nb2,
                                                        trip_nb3,
                                                        TotalDistance,
                                                        TripSchedule,
                                                        total_cost_1way,
                                                        total_cost_loop,
                                                        tour_savings,
                                                        travel_days,
                                                        dispatch1,
                                                        arrival2,
                                                        dispatch2,
                                                        arrival3,
                                                        dispatch3,
                                                        arrival1,
                                                        TripSchedule_1,
                                                        TripSchedule_2,
                                                        TripSchedule_3,
                                                        Carrier_1,
                                                        Carrier_2,
                                                        Carrier_3,
                                                    ]

                                                    row_nb += 1

    # Set Linehaul day and waiting time
    Matched_Trips["dispatch1_LHday"] = pd.to_datetime(
        Matched_Trips["Dispatch1"]
    ) + pd.Timedelta(hours=17)
    Matched_Trips["dispatch2_LHday"] = pd.to_datetime(
        Matched_Trips["Dispatch2"]
    ) + pd.Timedelta(hours=17)
    Matched_Trips["dispatch3_LHday"] = pd.to_datetime(
        Matched_Trips["Dispatch3"]
    ) + pd.Timedelta(hours=17)
    Matched_Trips["dispatch1_LHdow"] = (
        pd.to_datetime(Matched_Trips["Dispatch1"]) + pd.Timedelta(hours=17)
    ).dt.day_name()
    Matched_Trips["dispatch2_LHdow"] = (
        pd.to_datetime(Matched_Trips["Dispatch2"]) + pd.Timedelta(hours=17)
    ).dt.day_name()
    Matched_Trips["dispatch3_LHdow"] = (
        pd.to_datetime(Matched_Trips["Dispatch3"]) + pd.Timedelta(hours=17)
    ).dt.day_name()
    Matched_Trips["Trip_1_wait_hours"] = (
        pd.to_datetime(Matched_Trips["Dispatch2"])
        - pd.to_datetime(Matched_Trips["Arrival1"])
    ) / pd.Timedelta(hours=1)
    Matched_Trips["Trip_2_wait_hours"] = (
        pd.to_datetime(Matched_Trips["Dispatch3"])
        - pd.to_datetime(Matched_Trips["Arrival2"])
    ) / pd.Timedelta(hours=1)
    Matched_Trips["Trip_3_wait_hours"] = (
        pd.to_datetime(Matched_Trips["Dispatch1"])
        + pd.Timedelta(days=7)
        - pd.to_datetime(Matched_Trips["Arrival3"])
    ) / pd.Timedelta(hours=1)
    Matched_Trips["WeekNumber_Adj"] = (
        (Matched_Trips["dispatch1_LHday"] - pd.to_datetime(start_date)).dt.days // 7
    ) + 1
    Matched_Trips["Loop_Name"] = (
        Matched_Trips["terminal1"]
        + "-"
        + Matched_Trips["terminal2"]
        + "-"
        + Matched_Trips["terminal3"]
        + "-"
        + Matched_Trips["dispatch1_LHdow"]
        + "-"
        + Matched_Trips["dispatch2_LHdow"]
        + "-"
        + Matched_Trips["dispatch3_LHdow"]
    )

    # Write Matched_Trips to CSV
    # Matched_Trips.to_csv("matched_trips.csv", index=True)
    return Matched_Trips
    
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

if container1.button("Find Matching Trips", type="secondary"):
    st.write("match button is clicked")
    start_date = "10-01-2023"
    #matched_trips = trip_matching(min_distance1,max_distance1,min_savings1,max_distance71,max_idle_time1,max_durations,start_date)
    #d = matched_trips.to_json(orient="records")
    #st.write(d)
    d= data_cleanup()
    st.write(d)

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

