# EcoTrack local setup

EcoTrack is a local-first sustainability tracker with personal accounts, waste and recycling logs, estimated carbon tracking, charts, recommendations, and neighborhood pickup tools. The website, API, and SQLite database run on your computer; no external database account, JavaScript package install, or build step is needed.

## Requirements

- Python 3.10 or later

## Start the website

From the project directory, run:

```powershell
python app.py
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000). Stop the server with **Ctrl+C**.

The app stores its SQLite database at `%LOCALAPPDATA%\EcoTrack\ecotrack.db` on Windows. Set `ECOTRACK_DATA_DIR` to use a different data directory. Set `PORT` to change the default port (8000).

## Features

- Register, sign in/out, and update your name, email, and password. Passwords are salted and securely hashed; personal records are isolated per account.
- Dashboard with a personal sustainability progress score, carbon estimate, waste and recycling totals, six-month charts, recent activity, and tailored recommendations.
- Log, review, and delete categorized waste entries, including the amount recycled.
- Estimate carbon emissions for car and bus travel, electricity, and air travel. Each estimate uses a visible average factor; actual emissions vary.
- Review recycling guidance and track your diverted waste.
- Explore analytics by month, material, and activity; export your personal records to CSV.
- Continue to create neighborhood waste reports and manage collection schedules.

The sustainability score is a personal progress indicator, not an official environmental rating. The first run creates five waste categories. Set `ECOTRACK_DATA_DIR` to use an isolated database while testing.
