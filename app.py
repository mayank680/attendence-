"""Streamlit entry point for the Multimodal Attendance & Engagement Agent."""

import json
import logging
import tempfile
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

from config import (
    AUDIO_RMS_THRESHOLD,
    MAX_UPLOAD_SIZE_MB,
    VIDEO_SAMPLE_INTERVAL_SECONDS,
)
from database import db
from modules.analytics import attendance_history, attendance_summary
from modules.audio import analyze_audio
from modules.recommendations import generate_recommendations
from modules.vision import analyze_video, record_webcam_clip

LOGGER = logging.getLogger(__name__)
VIDEO_TYPES = ["mp4", "mov", "avi", "mkv"]
AUDIO_TYPES = ["wav", "flac", "ogg", "mp3", "m4a"]

st.set_page_config(
    page_title="Multimodal Attendance Agent",
    page_icon="📚",
    layout="wide",
)


def _show_error(message: str, exc: Exception) -> None:
    LOGGER.exception("Dashboard operation failed", exc_info=exc)
    st.error(message)


def _save_upload_temporarily(uploaded_file, allowed_extensions: list[str]) -> Path:
    suffix = Path(uploaded_file.name).suffix.lower().lstrip(".")
    if suffix not in allowed_extensions:
        raise ValueError(f"Unsupported file type. Accepted types: {', '.join(allowed_extensions)}.")
    content = uploaded_file.getvalue()
    if not content:
        raise ValueError("The uploaded file is empty.")
    if len(content) > MAX_UPLOAD_SIZE_MB * 1024 * 1024:
        raise ValueError(f"File is too large. Maximum size is {MAX_UPLOAD_SIZE_MB} MB.")
    temporary = tempfile.NamedTemporaryFile(
        prefix="attendance_upload_", suffix=f".{suffix}", delete=False
    )
    try:
        temporary.write(content)
        return Path(temporary.name)
    finally:
        temporary.close()


def _page_home(students, sessions, session_id):
    st.title("Multimodal Attendance & Engagement Agent")
    st.caption("Local-first classroom record keeping and session activity analysis.")
    if session_id is None:
        st.info("Create or select a session to see its attendance summary.")
    else:
        records = db.list_attendance(session_id)
        summary = attendance_summary(students, records)
        columns = st.columns(4)
        columns[0].metric("Registered students", summary["total"])
        columns[1].metric("Present", summary["present"])
        columns[2].metric("Absent", summary["absent"])
        columns[3].metric("Attendance recorded", f'{summary["percentage"]:.1f}%')
        if summary["missing"]:
            st.warning(f'{summary["missing"]} student record(s) still need a present/absent status.')
    st.subheader("Getting started")
    st.markdown(
        "1. Add students under **Student Management**.\n"
        "2. Create and select a class under **Session Management**.\n"
        "3. Record identity-based attendance manually. Video detections never assign names.\n"
        "4. Optionally analyze a permitted audio/video file and review the charts."
    )
    st.divider()
    st.subheader("Clearly labeled sample data")
    st.caption("Sample rows are fictional and marked [SAMPLE]. They can be removed without deleting real records.")
    left, right = st.columns(2)
    if left.button("Load sample data"):
        try:
            db.load_sample_data()
            st.success("Sample data loaded.")
            st.rerun()
        except Exception as exc:
            _show_error("Sample data could not be loaded. Check the local application log.", exc)
    if right.button("Remove sample data"):
        try:
            db.remove_sample_data()
            st.success("Sample data removed.")
            st.rerun()
        except Exception as exc:
            _show_error("Sample data could not be removed. Check the local application log.", exc)


def _page_students():
    st.title("Student Management")
    st.caption("Store only a display name and local student code. No biometric data is collected.")
    with st.form("add_student_form", clear_on_submit=True):
        name = st.text_input("Student name")
        code = st.text_input("Student code")
        submitted = st.form_submit_button("Add student")
    if submitted:
        try:
            db.add_student(name, code)
            st.success("Student added.")
            st.rerun()
        except Exception as exc:
            _show_error("Student could not be added. Check the fields and local log.", exc)

    students = db.list_students()
    if not students:
        st.info("No students registered yet.")
        return
    st.subheader("Registered students")
    st.dataframe(
        pd.DataFrame(students)[["student_code", "name", "created_at"]],
        use_container_width=True,
        hide_index=True,
    )
    labels = {row["id"]: f'{row["student_code"]} — {row["name"]}' for row in students}
    selected_id = st.selectbox("Select a student to edit or remove", labels, format_func=labels.get)
    current = next(row for row in students if row["id"] == selected_id)
    with st.form("edit_student_form"):
        updated_name = st.text_input("Name", value=current["name"])
        updated_code = st.text_input("Code", value=current["student_code"])
        save = st.form_submit_button("Save student changes")
    if save:
        try:
            db.update_student(selected_id, updated_name, updated_code)
            st.success("Student updated.")
            st.rerun()
        except Exception as exc:
            _show_error("Student could not be updated. Check the fields and local log.", exc)
    if st.button("Delete selected student", type="secondary"):
        try:
            db.delete_student(selected_id)
            st.success("Student and associated attendance entries removed.")
            st.rerun()
        except Exception as exc:
            _show_error("Student could not be deleted. Check the local log.", exc)


def _page_sessions():
    st.title("Session Management")
    with st.form("create_session_form", clear_on_submit=True):
        title = st.text_input("Session title")
        notes = st.text_area("Notes (optional)")
        submitted = st.form_submit_button("Create session")
    if submitted:
        try:
            db.create_session(title, notes)
            st.success("Session created.")
            st.rerun()
        except Exception as exc:
            _show_error("Session could not be created. Check the title and local log.", exc)
    sessions = db.list_sessions()
    if sessions:
        st.subheader("Sessions")
        st.dataframe(
            pd.DataFrame(sessions)[["title", "notes", "created_at"]],
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info("No sessions have been created.")


def _page_attendance(students, session_id):
    st.title("Attendance Recording")
    if session_id is None:
        st.info("Create and select a session first.")
        return
    if not students:
        st.info("Add students before recording attendance.")
        return
    current_records = {row["student_id"]: row for row in db.list_attendance(session_id)}
    with st.form("manual_attendance_form"):
        selections: dict[int, str] = {}
        for student in students:
            existing = current_records.get(student["id"], {}).get("status", "Not recorded")
            options = ["Not recorded", "present", "absent"]
            default_index = options.index(existing) if existing in options else 0
            selections[student["id"]] = st.selectbox(
                f'{student["student_code"]} — {student["name"]}',
                options,
                index=default_index,
                key=f'attendance_{student["id"]}',
            )
        submitted = st.form_submit_button("Save attendance")
    if submitted:
        try:
            for student_id, status in selections.items():
                if status == "Not recorded":
                    db.delete_attendance(session_id, student_id)
                else:
                    db.set_attendance(session_id, student_id, status)
            st.success("Attendance saved. Existing entries were updated where changed.")
            st.rerun()
        except Exception as exc:
            _show_error("Attendance could not be saved. Check the local log.", exc)
    summary = attendance_summary(students, db.list_attendance(session_id))
    st.info(
        f'Present: {summary["present"]} · Absent: {summary["absent"]} · '
        f'Not recorded: {summary["missing"]} · '
        f'Present / registered: {summary["percentage"]:.1f}%'
    )


def _page_video(session_id):
    st.title("Video Analysis")
    if session_id is None:
        st.info("Create and select a session before analyzing video.")
        return
    st.warning(
        "Consent required: record or upload video only with appropriate permission. "
        "This page detects anonymous people; it does not identify students or mark attendance."
    )
    interval = st.number_input(
        "Seconds between sampled frames",
        min_value=0.25,
        max_value=30.0,
        value=float(VIDEO_SAMPLE_INTERVAL_SECONDS),
        step=0.25,
    )
    source = st.radio("Video source", ["Upload a video", "Record from this computer's webcam"])
    uploaded = None
    if source == "Upload a video":
        uploaded = st.file_uploader("Upload a video", type=VIDEO_TYPES)
        should_process = uploaded is not None and st.button("Analyze anonymous people detections")
    else:
        st.caption(
            "The webcam belongs to the computer running this local Streamlit app. "
            "A temporary clip of at most 30 seconds is recorded only after you confirm and click."
        )
        consent = st.checkbox(
            "I have permission from people who may be recorded and want to capture a short clip."
        )
        clip_seconds = st.number_input(
            "Webcam clip length (seconds)", min_value=1, max_value=30, value=10
        )
        should_process = consent and st.button("Record clip and analyze")
    if not should_process:
        return
    path = None
    try:
        if source == "Upload a video":
            path = _save_upload_temporarily(uploaded, VIDEO_TYPES)
        else:
            temporary = tempfile.NamedTemporaryFile(
                prefix="attendance_webcam_", suffix=".avi", delete=False
            )
            path = Path(temporary.name)
            temporary.close()
            with st.spinner("Recording a short webcam clip locally..."):
                record_webcam_clip(path, duration_seconds=int(clip_seconds))
        with st.spinner("Sampling video and running the local OpenCV people detector..."):
            result = analyze_video(path, sample_interval_seconds=interval)
        db.add_video_analysis(
            session_id,
            "webcam" if source != "Upload a video" else "upload",
            result,
        )
        st.success(f'Processed {result["sample_count"]} sampled frame(s).')
        cols = st.columns(3)
        cols[0].metric("Maximum people detected in a sampled frame", result["maximum_people_detected"])
        cols[1].metric("Average per sampled frame", result["average_people_detected"])
        cols[2].metric("Video duration", f'{result["duration_seconds"]:.1f} s')
        if result["preview_jpeg"]:
            st.image(result["preview_jpeg"], caption="Unannotated sample frame; no identity processing.")
        st.plotly_chart(
            px.line(
                x=result["timestamps"],
                y=result["counts"],
                labels={"x": "Video time (seconds)", "y": "Anonymous detections"},
                title="People detections by sampled frame",
            ),
            use_container_width=True,
        )
        st.caption(
            "The built-in HOG detector can miss or overcount people. It does not track identities, "
            "measure attention, or create attendance records."
        )
    except Exception as exc:
        _show_error("Video analysis failed. Validate the file and check the local application log.", exc)
    finally:
        if path is not None:
            path.unlink(missing_ok=True)


def _page_audio(session_id):
    st.title("Audio Activity Analysis")
    st.warning(
        "Obtain permission before recording or uploading classroom audio. This local tool measures "
        "waveform activity only: it does not identify speakers, transcribe speech, or measure engagement."
    )
    if session_id is None:
        st.info("Create and select a session to save an analysis.")
        return
    threshold = st.slider(
        "RMS activity threshold (amplitude)",
        min_value=0.0,
        max_value=0.2,
        value=float(AUDIO_RMS_THRESHOLD),
        step=0.005,
    )
    uploaded = st.file_uploader("Upload audio", type=AUDIO_TYPES)
    if uploaded is None or not st.button("Analyze audio activity"):
        return
    path = None
    try:
        path = _save_upload_temporarily(uploaded, AUDIO_TYPES)
        with st.spinner("Analyzing audio locally..."):
            result = analyze_audio(path, rms_threshold=threshold)
            db.add_audio_analysis(session_id, uploaded.name, result)
        metrics = st.columns(3)
        metrics[0].metric("Duration", f'{result["duration_seconds"]:.2f} s')
        metrics[1].metric("Active audio", f'{result["active_percentage"]:.1f}%')
        metrics[2].metric("Estimated silence", f'{result["silence_seconds"]:.2f} s')
        st.plotly_chart(
            px.line(
                x=result["frame_times"],
                y=result["rms_values"],
                labels={"x": "Audio time (seconds)", "y": "RMS amplitude"},
                title="Audio waveform activity (frame RMS)",
            ).add_hline(y=threshold, line_dash="dash", annotation_text="Activity threshold"),
            use_container_width=True,
        )
        report = json.dumps(result, indent=2)
        st.download_button(
            "Download audio analysis report (JSON)",
            report,
            file_name="audio_analysis_report.json",
            mime="application/json",
        )
        st.success("Analysis saved to the selected local session.")
    except Exception as exc:
        _show_error("Audio analysis failed. Validate the file and check the local application log.", exc)
    finally:
        if path is not None:
            path.unlink(missing_ok=True)


def _page_analytics(students, sessions):
    st.title("Analytics & Charts")
    if not sessions:
        st.info("Create sessions and record attendance to populate analytics.")
        return
    records = db.list_attendance()
    history = attendance_history(sessions, records, total_students=len(students))
    if history.empty:
        st.info("There are no attendance records to chart.")
    else:
        st.plotly_chart(
            px.bar(
                history,
                x="session",
                y="attendance_percentage",
                hover_data=["present", "recorded", "incomplete"],
                range_y=[0, 100],
                title="Recorded attendance by session",
                labels={"attendance_percentage": "Present among current roster (%)"},
            ),
            use_container_width=True,
        )
        st.plotly_chart(
            px.line(
                history,
                x="session",
                y="present",
                markers=True,
                title="Present student count across sessions",
            ),
            use_container_width=True,
        )
        st.dataframe(history, use_container_width=True, hide_index=True)
    audio_rows = db.list_audio_analyses()
    if audio_rows:
        audio_frame = pd.DataFrame(audio_rows)
        st.plotly_chart(
            px.bar(
                audio_frame,
                x="analyzed_at",
                y="active_percentage",
                color="session_id",
                hover_data=["file_name", "duration_seconds"],
                title="Audio activity percentage by analysis",
                labels={"active_percentage": "Frames above RMS threshold (%)"},
            ),
            use_container_width=True,
        )
    else:
        st.info("No audio analyses have been saved.")
    video_rows = db.list_video_analyses()
    if video_rows:
        video_frame = pd.DataFrame(video_rows)
        st.plotly_chart(
            px.bar(
                video_frame,
                x="analyzed_at",
                y="maximum_people_detected",
                color="session_id",
                hover_data=["source", "duration_seconds", "sample_count"],
                title="Maximum anonymous detections per video analysis",
                labels={"maximum_people_detected": "Maximum people in a sampled frame"},
            ),
            use_container_width=True,
        )
    else:
        st.info("No video analyses have been saved.")


def _page_recommendations(students, session_id):
    st.title("AI Recommendations")
    st.caption("Recommendations are transparent threshold-based rules, not a trained AI model.")
    if session_id is None:
        st.info("Create and select a session to generate recommendations.")
        return
    attendance = attendance_summary(students, db.list_attendance(session_id))
    audio_rows = db.list_audio_analyses(session_id)
    audio = audio_rows[0] if audio_rows else None
    recommendations = generate_recommendations(attendance, audio)
    try:
        db.save_recommendations(session_id, recommendations)
    except Exception as exc:
        _show_error("Recommendations were calculated but could not be saved.", exc)
    for item in recommendations:
        with st.container(border=True):
            st.markdown(f'**{item["category"]}:** {item["message"]}')
            st.caption(f'Reason: {item["reason"]}')
    st.caption(
        "Audio levels and attendance are context signals only. The system does not infer a student's "
        "attention, emotion, learning, or engagement."
    )


def _page_reports():
    st.title("Reports & CSV Export")
    records = db.list_attendance()
    if records:
        export_frame = pd.DataFrame(records)[
            ["session_title", "student_code", "name", "status", "recorded_at"]
        ]
        st.dataframe(export_frame, use_container_width=True, hide_index=True)
        st.download_button(
            "Download attendance CSV",
            export_frame.to_csv(index=False).encode("utf-8-sig"),
            file_name="attendance_export.csv",
            mime="text/csv",
        )
    else:
        st.info("No attendance records are available to export.")
    sessions = db.list_sessions()
    audio_rows = db.list_audio_analyses()
    video_rows = db.list_video_analyses()
    if sessions:
        st.subheader("Session report")
        selected = st.selectbox(
            "Session report",
            sessions,
            format_func=lambda item: item["title"],
            key="report_session",
        )
        students = db.list_students()
        summary = attendance_summary(students, db.list_attendance(selected["id"]))
        report = {
            "session": selected,
            "attendance_summary": summary,
            "audio_analyses": [
                row for row in audio_rows if row["session_id"] == selected["id"]
            ],
            "video_analyses": [
                row for row in video_rows if row["session_id"] == selected["id"]
            ],
            "note": "Audio activity is not a measure of engagement or attention.",
        }
        st.download_button(
            "Download combined session report (JSON)",
            json.dumps(report, indent=2, default=str),
            file_name=f"session_{selected['id']}_report.json",
            mime="application/json",
        )


def _page_about():
    st.title("About & Privacy")
    st.markdown(
        """
        **Purpose:** locally manage manual attendance and inspect anonymous video detections and
        audio amplitude activity for a class session.

        **Privacy:** data is stored in a local SQLite database. Uploaded media is written to a
        temporary local file only while analyzed, then removed; raw media is not saved by the app.
        No cloud API is called. The database retains names, student codes, session attendance, and
        numeric audio summaries until you remove them.

        **Consent:** get the required consent and institutional approval before collecting classroom
        audio/video. Do not record secretly. Provide a manual alternative.

        **Limitations:** HOG person detection can be inaccurate and does not identify people.
        Audio RMS labels are threshold-dependent and cannot establish who spoke or whether anyone
        was engaged. Silence is not inattention. Recommendations are explainable rules, not
        validated learning or attention assessments.
        """
    )
    st.subheader("Local data handling")
    st.code("data/attendance.db   (excluded from Git)")
    st.caption("Delete student/session records in the dashboard or remove the local database file when appropriate.")


def main() -> None:
    try:
        db.initialize_database()
        students = db.list_students()
        sessions = db.list_sessions()
    except Exception as exc:
        LOGGER.exception("Could not start the dashboard database")
        st.error("The local database could not be opened. Check the configured path and reports/app.log.")
        st.stop()
        return

    st.sidebar.title("Navigation")
    page = st.sidebar.radio(
        "Open section",
        [
            "Home Dashboard",
            "Student Management",
            "Session Management",
            "Attendance Recording",
            "Video Analysis",
            "Audio Analysis",
            "Analytics and Charts",
            "AI Recommendations",
            "Reports and CSV Export",
            "About and Privacy",
        ],
    )
    session_id = None
    if sessions:
        selected_session = st.sidebar.selectbox(
            "Active session",
            sessions,
            format_func=lambda item: item["title"],
        )
        session_id = selected_session["id"]
    else:
        st.sidebar.info("Create a session to enable attendance and reports.")

    if page == "Home Dashboard":
        _page_home(students, sessions, session_id)
    elif page == "Student Management":
        _page_students()
    elif page == "Session Management":
        _page_sessions()
    elif page == "Attendance Recording":
        _page_attendance(students, session_id)
    elif page == "Video Analysis":
        _page_video(session_id)
    elif page == "Audio Analysis":
        _page_audio(session_id)
    elif page == "Analytics and Charts":
        _page_analytics(students, sessions)
    elif page == "AI Recommendations":
        _page_recommendations(students, session_id)
    elif page == "Reports and CSV Export":
        _page_reports()
    else:
        _page_about()


if __name__ == "__main__":
    main()
