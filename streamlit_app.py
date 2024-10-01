import streamlit as st
from st_aggrid import AgGrid
import pygwalker as pyg
from pygwalker.api.streamlit import StreamlitRenderer
import pandas as pd
import pulp
import datetime
import requests
import numpy as np

st.set_page_config(page_title="Trip Optimization",
                   page_icon=":rocket:", 
                   layout="wide", 
                   initial_sidebar_state="expanded")

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

# Initialize session state    
if 'trip_history' not in st.session_state:
    st.session_state.last_updated = datetime.time(0,0)
    st.session_state.trip_history = []
if 'trips_matched' not in st.session_state:
    st.session_state.last_matched = datetime.time(0,0)
    st.session_state.trips_matched = []
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
    df_copy = []
    for item in st.session_state.trip_history:
        # Convert 'dispatch' and 'arrival' to datetime
        item["dispatch"] = pd.to_datetime(item["dispatch"], errors="coerce")
        item["arrival"] = pd.to_datetime(item["arrival"], errors="coerce")

        # Add 'WeekDay' column
        item["WeekDay"] = pd.to_datetime(item["dispatch"], errors="coerce").strftime('%A')
        df_copy.append(item)
        
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
    df_copy = pd.DataFrame(data_cleanup())
    #st.write(df_copy)
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
    #st.write(tripHistory)
    st.session_state.trip_history = tripHistory
    st.session_state.last_updated = datetime.datetime.now()

st.dataframe(st.session_state.trip_history, width=1000, height=400)
st.write("Last fetched:",  st.session_state.last_updated)
#st.divider()
available_trips_choose = [trip['trip_number'] for trip in st.session_state.trip_history]
#st.write(available_trips_choose)
selected_excluded_trip_ids_selected = container1.multiselect(
    'Select trips to exclude',
    options=available_trips_choose,
    default=[],
    key='exclude_trips_selected'
)
    
st.subheader("Trips Matched", divider=True)
if container1.button("Find Matching Trips", type="secondary"):
    #st.write("match button is clicked")
    start_date = "10-01-2023"
    matched_trips = trip_matching(min_distance1,max_distance1,min_savings1,max_distance71,max_idle_time1,max_durations,start_date)
    d = matched_trips.to_json(orient="records")
    #st.dataframe(matched_trips, width=1000, height=400)
    #st.write(matched_trips)
    st.session_state.trips_matched = matched_trips
    st.session_state.last_matched = datetime.datetime.now()
    #st.divider()

st.dataframe(st.session_state.trips_matched, width=1000, height=400)
#grid_return1 = AgGrid(st.session_state.trips_matched)
st.write("Last matched:",  st.session_state.last_matched)

st.sidebar.header('Step 3: Show Summary')
st.subheader("Loop List", divider=True)
container2 = st.sidebar.container(border=True)
if container2.button("Show Summary", type="secondary"):
  #walker = pyg.walk(st.session_state.trips_matched)
  loopList_copy = []
  for item in st.session_state.trips_matched:
    loopList_copy.append(item)

  st.write(st.session_state.trips_matched["Loop_Name"])
  
  loopList = [
    {'Loop Name': "ONT-EWR-DAL-Sunday-Tuesday-Thursday", 'Count Of Weeks': '1', 'Week Number': '36', 'Avg Loop Duration': 5.8},
    {'Loop Name': "ONT-EWR-DAL-Sunday-Tuesday-Friday", 'Count Of Weeks': '1', 'Week Number': '36', 'Avg Loop Duration': 5.7},
    {'Loop Name': "ONT-EWR-DAL-Saturday-Tuesday-Thursday", 'Count Of Weeks': '1', 'Week Number': '36', 'Avg Loop Duration': 7.0},
    {'Loop Name': "ONT-EWR-DAL-Saturday-Tuesday-Friday", 'Count Of Weeks': '1', 'Week Number': '36', 'Avg Loop Duration': 6.6},
    {'Loop Name': "EWR-DAL-ONT-Tuesday-Thursday-Saturday", 'Count Of Weeks': '1', 'Week Number': '36', 'Avg Loop Duration': 6.0},
    {'Loop Name': "EWR-DAL-ONT-Tuesday-Thursday-Saturday", 'Count Of Weeks': '1', 'Week Number': '36', 'Avg Loop Duration': 5.6},
    {'Loop Name': "EWR-DAL-ONT-Tuesday-Thursday-Friday", 'Count Of Weeks': '1', 'Week Number': '36', 'Avg Loop Duration': 5.6},
    {'Loop Name': "EWR-DAL-ONT-Tuesday-Friday-Sunday", 'Count Of Weeks': '2', 'Week Number': '36', 'Avg Loop Duration': 5.6},
    {'Loop Name': "", 'Count Of Weeks': '', 'Week Number': '35', 'Avg Loop Duration': 5.7},
    {'Loop Name': "EWR-DAL-ONT-Wednesday-Friday-Sunday", 'Count Of Weeks': '2', 'Week Number': '36', 'Avg Loop Duration': 5.6},
    {'Loop Name': "", 'Count Of Weeks': '', 'Week Number': '35', 'Avg Loop Duration': 5.7},
    {'Loop Name': "DAL-ONT-EWR-Thursday-Saturday-Tuesday", 'Count Of Weeks': '1', 'Week Number': '36', 'Avg Loop Duration': 5.6},
    {'Loop Name': "DAL-ONT-EWR-Friday-Sunday-Tuesday", 'Count Of Weeks': '1', 'Week Number': '36', 'Avg Loop Duration': 5.6},
    {'Loop Name': "MDW-CXIT-DAL-SFO-Tuesday-Thursday-Saturday", 'Count Of Weeks': '1', 'Week Number': '36', 'Avg Loop Duration': 5.6},
    {'Loop Name': "MIS-DAL-ONT-Wednesday-Friday-Sunday", 'Count Of Weeks': '1', 'Week Number': '36', 'Avg Loop Duration': 5.6}
  ]
  st.dataframe(loopList, width=1000, height=400)

  #AgGrid(st.session_state.trips_matched)
  st.subheader("Loop Detail", divider=True)
  loopDetail = [
    {'Loop Name': "ONT-EWR-DAL-Sunday-Tuesday-Thursday", 'Week Number': '36','TripNumber1': '309856', 'TripNumber2': '360987', 'TripNumber3': '3615243', 'Dispatch1 datetime': '6/1/2024 06:00 AM','Dispatch1 LHdow': 'Sunday','Carrier 1': 'MUSA LOGISTICS INC','Ave Trip 1 wait hours': '24','Dispatch2 datetime': '6/1/2024 06:00 AM','Dispatch2 LHdow': 'Tuesday','Carrier 2': 'MEDALLION TRANSPORT & LOGISTICS LLC','Ave Trip 2 wait hours': '24','Dispatch3 datetime': '6/1/2024 06:00 AM','Dispatch3 LHdow': 'Thursday','Carrier 3': 'ITF LLC','Ave Trip 3 wait hours': '24'}
  ]
  st.dataframe(loopDetail, width=1000, height=200)
  


