import redshift_connector
import pandas as pd
import numpy as np
import os
import streamlit as st

cwd = os.getcwd()

def trip_history(start_date, end_date):


    conn = redshift_connector.connect(
        host = 'rs.dev.dylt.com',
        database = 'dyltdw',
        port = 5439,
        user = 'svc_analytics',
        password = 'ytC8NBCQ'
    )

    cursor = conn.cursor()
    sql = f"""select vls.trip_number, 
        trip.origin_zone as Origin, 
        trip.destination_zone as Destination,
        date_part(week, ts.time_changed) as weeknumber,
        vls.distance, 
        vls.cost, 
        date_trunc('second', ts.time_changed) as Dispatch, 
        date_trunc('second', ts1.time_changed) as ARRIVAL, 
        vls.equipment, 
        vls.name as carrier,
        sched.ROUTE_DESCRIPTION,
        round((vls.cost / vls.distance)::decimal(10, 4), 2) as cpm
        from  dylt_imp.vendor_load_summary vls 
        left join dylt_imp.tripstat ts on vls.trip_number = ts.trip_number and ts.status = 'DISP'
        left join dylt_imp.tripstat ts1 on vls.trip_number = ts1.trip_number and ts1.status = 'ARRTERM'
        left join dylt_imp.trip trip on vls.trip_number = trip.trip_number
        LEFT JOIN dylt_imp.TRIP_SCHEDULES sched ON sched.SCHEDULE_ID = trip.SCHEDULE_ID
        where vls.status = 'Completed' 
        and ts.time_changed between '{start_date}' and '{end_date}'
        and vls.LOAD_SUMMARY_ID = (select max(load_summary_id) from dylt_imp.vendor_load_summary vls2 where vls2.TRIP_NUMBER = vls.TRIP_NUMBER)
        and equipment not like '%Shut%'
        and ts.TIME_CHANGED = (select min(ts2.time_changed) from dylt_imp.tripstat ts2 where ts2.status = 'DISP' and ts2.trip_number = ts.trip_number)
        and ts1.TIME_CHANGED = (select min(ts2.time_changed) from dylt_imp.tripstat ts2 where ts2.status = 'ARRTERM' and ts2.trip_number = ts1.trip_number)
        order by vls.trip_number"""

    cursor.execute(sql)

    result: pd.DataFrame = cursor.fetch_dataframe()

    #result.to_csv('trip_history.csv', index=False)
    st.write(result)
    return start_date

# =============================================================================
start_date = '01-01-2024'
end_date = '10-18-2024'
trip_history(start_date, end_date)
# =============================================================================
