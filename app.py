from flask import Flask, jsonify
from flask_cors import CORS
import requests
import os
from dotenv import load_dotenv
from collections import defaultdict

app = Flask(__name__)
CORS(app)

# Load environment variables from .env file
load_dotenv()

# API configuration
API_BASE_URL = os.getenv("API_BASE_URL", "https://ogn-events.staging.origin.no")
API_KEY = os.getenv("API_KEY", "")

# Helper function to fetch data from external API
def fetch_api_data(endpoint, params=None, fetch_all_pages=True):
    headers = {
        "X-API-Key": API_KEY,
        "Content-Type": "application/json"
    }
    all_data = []
    
    if fetch_all_pages:
        page = 0
        size = 100  # Number of records per page
        while True:
            page_params = {"page": page, "size": size}
            if params:
                page_params.update(params)
            try:
                response = requests.get(f"{API_BASE_URL}/{endpoint}", headers=headers, params=page_params)
                response.raise_for_status()
                data = response.json()
                if not data:  # No more data to fetch
                    break
                all_data.extend(data)
                page += 1
            except requests.RequestException as e:
                print(f"Error fetching data from {endpoint}, page {page}: {e}")
                break
    else:
        # If not fetching all pages, just get the first page
        try:
            response = requests.get(f"{API_BASE_URL}/{endpoint}", headers=headers, params=params)
            response.raise_for_status()
            all_data = response.json()
        except requests.RequestException as e:
            print(f"Error fetching data from {endpoint}: {e}")
            all_data = []
    
    return all_data

# Helper function to calculate participants and vacant places for a SkillDay
def calculate_skillday_stats(skillday, events, attendees):
    event_ids = skillday.get("eventIds", [])
    participant_ids = set()
    total_open_spots = 0

    # Find events for this SkillDay and calculate stats
    for event in events:
        if event.get("eventId") in event_ids:
            total_open_spots += event.get("openSpots", 0)
            # Find attendees for this event
            for attendee in attendees:
                if event.get("eventId") in attendee.get("attendingEventIds", []):
                    participant_ids.add(attendee.get("attendeeId"))

    num_participants = len(participant_ids)
    return num_participants, total_open_spots

@app.route('/', methods=['GET'])
def home():
    return jsonify({"message": "Welcome to the SkillDays API backend"})

@app.route('/api/data', methods=['GET'])
def get_data():
    aggregated_data = []
    skilldays = fetch_api_data("api/skilldays")
    events = fetch_api_data("api/events")
    attendees = fetch_api_data("api/attendees")
    
    # Check if skilldays, events, and attendees are available
    if skilldays:
        for skillday in skilldays:
            skillday_id = skillday.get("skillDayId")
            skillday_name = skillday.get("name", f"SkillDay {skillday_id}")
            event_count = len(skillday.get("eventIds", []))
            aggregated_data.append({"label": skillday_name, "value": event_count})

    if events:
        for event in events:
            event_id = event.get("eventId")
            event_title = event.get("description", f"Event {event_id}")
            attendee_count = sum(
                1 for attendee in attendees
                if event_id in attendee.get("attendingEventIds", [])
            )
            aggregated_data.append({"label": event_title, "value": attendee_count})

    # Mock Data for demonstration purposes
    if not aggregated_data:
        aggregated_data = [
            {"label": "Item A", "value": 30},
            {"label": "Item B", "value": 50},
            {"label": "Item C", "value": 20},
            {"label": "Item D", "value": 70},
        ]

    return jsonify(aggregated_data)

@app.route('/api/statistics', methods=['GET'])
def get_statistics():
    skilldays = fetch_api_data("api/skilldays")
    events = fetch_api_data("api/events")
    attendees = fetch_api_data("api/attendees")

    # Initialize data structures
    dept_event_counts = defaultdict(int) # Count of events per department
    dept_participants = defaultdict(int) # Count of participants per department
    attendee_skillday_counts = defaultdict(set) # Count of SkillDays attended by each attendee
    responsible_event_counts = defaultdict(int) # Count of events per responsible person
    skillday_stats = [] # List to hold SkillDay statistics

    # Process SkillDays
    for skillday in skilldays:
        skillday_id = skillday.get("skillDayId")
        department = skillday.get("department", "Unknown")
        responsible_id = skillday.get("responsibleId")
        num_participants, open_spots = calculate_skillday_stats(skillday, events, attendees)
        
        # Find responsible person's email
        responsible = next(
            (a for a in attendees if a.get("attendeeId") == responsible_id),
            {"name": "Unknown", "email": "unknown@example.com"}
        )
        responsible_email = responsible.get("email", "unknown@example.com")
        responsible_name = responsible.get("name", "Unknown")

        # Update statistics
        skillday_stats.append({
            "id": skillday_id,
            "name": skillday.get("name", f"SkillDay {skillday_id}"),
            "participants": num_participants,
            "vacant_places": open_spots,
            "department": department
        })
        dept_participants[department] += num_participants
        responsible_event_counts[responsible_email] += len(skillday.get("eventIds", []))

        # Count events per department
        for event_id in skillday.get("eventIds", []):
            dept_event_counts[department] += 1

    # Process attendees for most SkillDays attended
    for attendee in attendees:
        attendee_id = attendee.get("attendeeId")
        for event in events:
            if event.get("eventId") in attendee.get("attendingEventIds", []):
                # Find SkillDay for this event
                for skillday in skilldays:
                    if event.get("eventId") in skillday.get("eventIds", []):
                        attendee_skillday_counts[attendee_id].add(skillday.get("skillDayId"))

    # Find most SkillDays attended
    most_attended = max(
        attendee_skillday_counts.items(),
        key=lambda x: len(x[1]), # Get the count of SkillDays attended
        default=(None, set())
    )
    most_attended_attendee = next(
        (a for a in attendees if a.get("attendeeId") == most_attended[0]),
        {"name": "None", "email": "none@example.com"}
    )

    # Find SkillDay with most participants
    most_participants_skillday = max(
        skillday_stats,
        key=lambda x: x["participants"],
        default={"name": "None", "participants": 0}
    )

    # Find SkillDays with least and most vacant places
    least_vacant_skillday = min(
        skillday_stats,
        key=lambda x: x["vacant_places"],
        default={"name": "None", "vacant_places": 0}
    )
    most_vacant_skillday = max(
        skillday_stats,
        key=lambda x: x["vacant_places"],
        default={"name": "None", "vacant_places": 0}
    )

    # Find department with most events
    most_events_dept = max(
        dept_event_counts.items(),
        key=lambda x: x[1],
        default=("None", 0)
    )

    # Find responsible person with most events
    most_responsible = max(
        responsible_event_counts.items(),
        key=lambda x: x[1],
        default=("none@example.com", 0)
    )

    return jsonify({
        "most_events_department": {
            "department": most_events_dept[0],
            "event_count": most_events_dept[1]
        },
        "most_participants_skillday": {
            "name": most_participants_skillday["name"],
            "participants": most_participants_skillday["participants"]
        },
        "most_attended_attendee": {
            "name": most_attended_attendee.get("name", "None"),
            "email": most_attended_attendee.get("email", "none@example.com"),
            "skillday_count": len(most_attended[1])
        },
        "department_participants": [
            {"department": dept, "participants": count}
            for dept, count in dept_participants.items()
        ],
        "most_events_group": {
            "department": most_events_dept[0],
            "event_count": most_events_dept[1]
        },
        "least_vacant_skillday": {
            "name": least_vacant_skillday["name"],
            "vacant_places": least_vacant_skillday["vacant_places"]
        },
        "most_vacant_skillday": {
            "name": most_vacant_skillday["name"],
            "vacant_places": most_vacant_skillday["vacant_places"]
        },
        "most_responsible_person": {
            "email": most_responsible[0],
            "event_count": most_responsible[1]
        }
    })

@app.route('/api/skilldays_list1', methods=['GET'])
def get_skilldays_list1():
    skilldays = fetch_api_data("api/skilldays")
    events = fetch_api_data("api/events")
    attendees = fetch_api_data("api/attendees")

    skillday_list = []
    for skillday in skilldays:
        num_participants, open_spots = calculate_skillday_stats(skillday, events, attendees)
        responsible_id = skillday.get("responsibleId")
        responsible = next(
            (a for a in attendees if a.get("attendeeId") == responsible_id),
            {"email": "unknown@example.com"}
        )
        skillday_list.append({
            "id": skillday.get("skillDayId"),
            "name": skillday.get("name", f"SkillDay {skillday.get('skillDayId')}"),
            "participants": num_participants,
            "responsible_email": responsible.get("email", "unknown@example.com"),
            "vacant_places": open_spots
        })

    return jsonify(skillday_list)

@app.route('/api/skilldays_list2', methods=['GET'])
def get_skilldays_list2():
    skilldays = fetch_api_data("api/skilldays")
    events = fetch_api_data("api/events")
    attendees = fetch_api_data("api/attendees")

    skillday_list = []
    for skillday in skilldays:
        num_participants, open_spots = calculate_skillday_stats(skillday, events, attendees)
        skillday_list.append({
            "id": skillday.get("skillDayId"),
            "name": skillday.get("name", f"SkillDay {skillday.get('skillDayId')}"),
            "participants": num_participants,
            "vacant_places": open_spots,
            "date": next(
                (e.get("date", "Unknown") for e in events if e.get("eventId") in skillday.get("eventIds", [])),
                "Unknown"
            )
        })

    return jsonify(skillday_list)

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=1337)