# Multimodal Attendance & Engagement Agent

A beginner-friendly, local-first classroom record-keeping prototype. The dashboard combines
manual attendance, anonymous video person counts, local audio activity measurements, and
explainable rule-based recommendations. It does **not** recognize student identities from media
or claim to measure attention, emotion, learning, or engagement.

## Architecture

```text
Streamlit UI (app.py)
  ├── database/db.py          SQLite data access and CSV export
  ├── modules/vision.py       Anonymous OpenCV HOG detections
  ├── modules/audio.py        Librosa waveform RMS/activity analysis
  ├── modules/analytics.py    Attendance summaries and history (Pandas)
  └── modules/recommendations.py
                              Explainable threshold-based rules
config.py                     Paths, thresholds, logging configuration
tests/                        Pytest coverage of core logic and persistence
```

### Folder structure

```text
multimodal-attendance-agent/
├── app.py
├── config.py
├── requirements.txt
├── README.md
├── .gitignore
├── modules/
│   ├── __init__.py
│   ├── analytics.py
│   ├── audio.py
│   ├── recommendations.py
│   └── vision.py
├── database/
│   ├── __init__.py
│   └── db.py
├── tests/
│   ├── test_analytics.py
│   ├── test_audio.py
│   └── test_database.py
├── data/
│   └── .gitkeep
└── reports/
    └── .gitkeep
```

`data/attendance.db` and `reports/app.log` are created automatically when the app starts. The
database, logs, and media are excluded from Git. Set `ATTENDANCE_DB_PATH` to use a different local
database location.

## Requirements

- Windows 10/11 and Python 3.11 recommended (Python 3.10+).
- Visual Studio Code with the Microsoft Python extension.
- A working internet connection for the initial Python package installation. Core analysis runs
  locally after setup; no paid API or cloud service is used.

## Setup on Windows and VS Code

Open the project folder `multimodal-attendance-agent` in VS Code. In the VS Code terminal
(PowerShell), run:

```powershell
py -3.11 --version
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

If PowerShell blocks activation, either allow it for this terminal with
`Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` and activate again, or use the venv
interpreter directly:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m streamlit run app.py
```

In VS Code, choose **Python: Select Interpreter** and select `.venv\Scripts\python.exe`.
Initialize the database and launch the app:

```powershell
python -c "from database.db import initialize_database; initialize_database(); print('Database ready')"
streamlit run app.py
```

The database also initializes automatically on dashboard startup. Open the local URL printed by
Streamlit, usually `http://localhost:8501`.

## Using the application

1. Add students with a name and a local student code.
2. Create and select a class session in the sidebar.
3. Use **Attendance Recording** to mark present/absent or leave an entry unrecorded. Later changes
   update the same student/session record; duplicate rows are prevented.
4. Optionally upload a permitted video in **Video Analysis**. OpenCV's built-in HOG people detector
   samples frames and displays anonymous counts. It never writes attendance records.
5. Optionally upload audio in **Audio Analysis**. The app calculates duration, frame RMS activity,
   and estimated silence using the selected amplitude threshold. The numeric result is saved to
   the selected session; the raw uploaded file is removed after processing.
6. Review charts and threshold-based suggestions; export attendance CSV or a combined session JSON
   report.
7. **Load sample data** on the home screen for a clearly marked fictional dataset. Use **Remove
   sample data** to remove only rows identified as samples.

Supported media extensions are checked before processing. The upload limit is 100 MB by default
and can be changed in `config.py`.

## Features and boundaries

- **Attendance:** identities come from a roster and manual teacher input. Person detection is not
  identity verification, and this project does not implement face recognition or biometric
  enrollment.
- **Video:** upload a clip or explicitly record a short (up to 30-second) clip from the computer
  running Streamlit. OpenCV's built-in HOG detector runs on sampled frames. Counts are approximate
  and may miss or double-count people; there is no persistent identity tracking.
- **Audio:** Librosa calculates RMS energy and thresholded active-frame percentage. No speech-to-text,
  speaker identification, or covert microphone recording is implemented.
- **Recommendations:** deterministic rules report incomplete attendance, attendance below a
  configurable threshold, and unusually low/high measured audio activity. They explain their
  reasons and do not infer student engagement.
- **Privacy:** media uploads are temporarily written to a local temp file and removed after
  analysis. The database retains roster details, attendance records, and numeric audio summaries.
  Remove records or the local database when retention is no longer appropriate.
- **Missing data:** the UI shows missing attendance rather than treating it as absent.

Before collecting classroom data, obtain appropriate student/institution consent and provide a
manual alternative. The code does not upload data to a cloud service. Protect the computer and
backups where student information is stored.

## Tests

The tests do not need a webcam, microphone, student data, or network access after dependencies are
installed. Audio tests synthesize a small local WAV file.

```powershell
python -m pytest -q
```

The suite covers attendance calculations and invalid inputs, missing records, recommendation
rules, SQLite initialization and CRUD, duplicate attendance correction, sample-data removal, and
audio duration/activity/invalid files.

## Logs and troubleshooting

- **`py` or Python not found:** install Python 3.11 and enable the Windows PATH option, or use the
  full Python executable path.
- **Wrong interpreter in VS Code:** select `.venv\Scripts\python.exe`, then reopen the terminal.
- **Activation is disabled:** use the process-scoped policy command above or invoke
  `.venv\Scripts\python.exe` directly.
- **Dependency install fails:** upgrade pip, confirm Python is 64-bit, then retry
  `pip install -r requirements.txt`. Some native wheels may require a compatible Python version.
- **Audio format cannot be decoded:** try WAV, FLAC, or OGG. Decoding depends on installed Librosa
  support and the input codec.
- **Video cannot be opened:** re-encode it to a common MP4/H.264 or AVI format and retry. HOG may be
  slow for large/high-resolution recordings.
- **Database path/permission error:** verify that the project or `ATTENDANCE_DB_PATH` location is
  writable. See `reports/app.log` for diagnostic details; the dashboard does not display raw
  exception details.
- **Port 8501 is busy:** run `streamlit run app.py --server.port 8502`.

## GitHub publishing

1. Check that `data/attendance.db`, real media, and private information are not staged. `.gitignore`
   excludes the database, logs, and common recording formats.
2. Create an empty GitHub repository without personal data.
3. From the project folder, run:

   ```powershell
   git init
   git add .
   git status
   git commit -m "Build multimodal attendance prototype"
   git branch -M main
   git remote add origin https://github.com/YOUR-USERNAME/YOUR-REPOSITORY.git
   git push -u origin main
   ```

4. Review the repository contents before pushing and never add student identifiers, credentials,
   recordings, or a populated database.

## Screenshots and college demonstration

For screenshots, launch the app with a few fictional sample rows, capture the Home Dashboard,
Attendance Recording, Analytics, and About & Privacy pages, then remove the sample data. Do not
include real student information in screenshots.

Suggested 3–5 minute demonstration:

1. Explain local storage and the privacy/consent boundary.
2. Add a fictional student, create a session, and mark attendance manually.
3. Show the calculated attendance percentage and an incomplete-record recommendation.
4. Upload a short synthetic or consented audio clip and explain the RMS threshold chart.
5. If time permits, analyze a consented video and show anonymous detections are not attendance.
6. Download the CSV and JSON reports, then explain model and measurement limitations.

## Future improvements

- Add a real tracker with explicit performance evaluation while retaining anonymous-by-default
  processing.
- Add configurable retention and deletion controls for all stored session data.
- Add database migrations and role-based access if the prototype is deployed beyond one local user.
- Add optional, separately consented speech transcription only after evaluating offline models and
  their privacy, accuracy, and hardware requirements.
- Add accessibility and localization improvements.
