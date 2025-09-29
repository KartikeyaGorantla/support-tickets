import streamlit as st
import pandas as pd
from datetime import datetime
import altair as alt
import streamlit_authenticator as stauth
from streamlit_authenticator.utilities.exceptions import LoginError
from libsql_client import create_client_sync

# --- Page Config ---
st.set_page_config(
    page_title="To-Do App",
    page_icon="📔",
    layout="wide",
    initial_sidebar_state="auto",
)

# --- Turso DB Connection ---
client = create_client_sync(
    url=st.secrets["turso"]["url"],
    auth_token=st.secrets["turso"]["token"]
)

# --- DB Setup ---
@st.cache_resource
def init_db():
    """Ensure tasks and notes tables exist (only runs once)."""
    client.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            Username TEXT NOT NULL,
            Task TEXT NOT NULL,
            Status TEXT,
            Priority TEXT,
            CreatedAt TEXT
        );
    """)
    client.execute("""
        CREATE TABLE IF NOT EXISTS notes (
            Username TEXT NOT NULL,
            Note TEXT NOT NULL,
            CreatedAt TEXT
        );
    """)

# --- Cached Queries ---
@st.cache_data(ttl=15)
def load_user_tasks(username: str) -> pd.DataFrame:
    rows = client.execute(
        "SELECT rowid AS id, * FROM tasks WHERE Username = ?;",
        [username]
    ).rows
    return (
        pd.DataFrame(rows, columns=["id", "Username", "Task", "Status", "Priority", "CreatedAt"])
        if rows else pd.DataFrame(columns=["id", "Username", "Task", "Status", "Priority", "CreatedAt"])
    )

@st.cache_data(ttl=15)
def load_user_notes(username: str) -> pd.DataFrame:
    rows = client.execute(
        "SELECT rowid AS id, * FROM notes WHERE Username = ? ORDER BY CreatedAt DESC;",
        [username]
    ).rows
    return (
        pd.DataFrame(rows, columns=["id", "Username", "Note", "CreatedAt"])
        if rows else pd.DataFrame(columns=["id", "Username", "Note", "CreatedAt"])
    )

def invalidate_cache():
    """Clear cached queries after DB writes."""
    load_user_tasks.clear()
    load_user_notes.clear()

# --- Authenticator ---
authenticator = stauth.Authenticate(
    st.secrets["credentials"].to_dict(),
    st.secrets["cookies"]["name"],
    st.secrets["cookies"]["key"],
)

# --- Login ---
if not st.session_state.get("authentication_status"):
    col1, col2, col3 = st.columns([1.5, 2, 1.5])
    with col2:
        try:
            authenticator.login(
                captcha=True,
                single_session=True,
                clear_on_submit=True
            )
        except LoginError as e:
            if "Captcha entered incorrectly" in str(e):
                st.error("Captcha is incorrect")
                st.stop()
        except Exception as e:
            st.error(f"Unexpected error during login: {e}")
            st.session_state["authentication_status"] = False
            st.stop()

        if st.session_state["authentication_status"] is False:
            st.error("Username/password is incorrect")
            st.stop()
        elif st.session_state["authentication_status"] is None:
            st.stop()
# --- App (only if logged in) ---
if st.session_state.get("authentication_status"):
    username = st.session_state["username"]
    init_db()
    authenticator.logout("Logout", "sidebar", use_container_width=True)
    st.title(f"Welcome {username}")

    main1, main2 = st.columns([7, 3])
    with main1:
        st.header("✅ To-Do List")
        # --- Add Task ---
        st.subheader("Add a New Task", divider="rainbow")
        with st.form("add_task_form", clear_on_submit=True):
            task_description = st.text_input("Task Description", placeholder="What do you need to do?")
            task_priority = st.selectbox("Priority", ["High", "Medium", "Low"])
            submitted = st.form_submit_button("Add Task")

        if submitted and task_description:
            client.execute(
                "INSERT INTO tasks (Username, Task, Status, Priority, CreatedAt) VALUES (?, ?, ?, ?, ?);",
                [username, task_description, "To Do", task_priority, datetime.now().isoformat()]
            )
            invalidate_cache()
            st.rerun()

        # --- Load Tasks ---
        df = load_user_tasks(username)
        active_tasks = df[df["Status"] != "Done"].copy()
        completed_tasks = df[df["Status"] == "Done"].copy()

        st.subheader("Active Tasks", divider="rainbow")

        if not active_tasks.empty:
            edited_active_tasks = st.data_editor(
                active_tasks,
                width="stretch",
                hide_index=True,
                column_order=("Task", "Status", "Priority", "CreatedAt"),
                column_config={
                    "Task": st.column_config.TextColumn("Task Description", required=True),
                    "Status": st.column_config.SelectboxColumn("Status", options=["To Do", "In Progress", "Done"], required=True),
                    "Priority": st.column_config.SelectboxColumn("Priority", options=["High", "Medium", "Low"], required=True),
                    "CreatedAt": st.column_config.DatetimeColumn("Created At", format="D MMM YYYY, h:mm a", disabled=True),
                },
                key="active_tasks_editor"
            )

            updated = False
            for idx, row in edited_active_tasks.iterrows():
                orig = active_tasks.loc[idx]
                if row["Task"] != orig["Task"] or row["Priority"] != orig["Priority"] or row["Status"] != orig["Status"]:
                    client.execute(
                        "UPDATE tasks SET Task = ?, Priority = ?, Status = ? WHERE rowid = ? AND Username = ?;",
                        [row["Task"], row["Priority"], row["Status"], row["id"], username]
                    )
                    updated = True
            if updated:
                invalidate_cache()
                st.rerun()
        else:
            st.info("No active tasks. Add one above!")

        with st.expander("✔️ Completed Tasks", expanded=False):
            if not completed_tasks.empty:
                for _, row in completed_tasks.iterrows():
                    col1, col2, col3 = st.columns([0.6, 0.2, 0.2])
                    with col1:
                        st.markdown(f"~~_{row['Task']}_~~")
                    with col2:
                        if st.button("Undo", key=f"undo_{row['id']}"):
                            client.execute(
                                "UPDATE tasks SET Status = 'To Do' WHERE rowid = ? AND Username = ?;",
                                [row["id"], username]
                            )
                            invalidate_cache()
                            st.rerun()
                    with col3:
                        if st.button("❌", key=f"delete_{row['id']}"):
                            client.execute(
                                "DELETE FROM tasks WHERE rowid = ? AND Username = ?;",
                                [row["id"], username]
                            )
                            invalidate_cache()
                            st.rerun()
            else:
                st.info("No tasks have been completed yet.")

    # --- Notes Section ---
    with main2:
        st.header("📝 Notes")
        st.subheader("Add a New Note", divider="rainbow")

        notes_df = load_user_notes(username)

        # Input for new note
        with st.form("add_note", clear_on_submit=True):
            new_note = st.text_area(" ", placeholder="What do you need to remember?")
            submitted = st.form_submit_button("Add Note")
            if submitted and new_note.strip():
                client.execute(
                    "INSERT INTO notes (Username, Note, CreatedAt) VALUES (?, ?, ?);",
                    [username, new_note.strip(), datetime.now().isoformat()]
                )
                invalidate_cache()
                st.rerun()

        with st.expander("Your Notes", expanded=True):
            if not notes_df.empty:
                for _, row in notes_df.iterrows():
                    with st.container():
                        st.markdown(
                            f"""
                            <div style="
                                background-color:#262730;
                                color: white;
                                padding:15px;
                                margin:10px;
                                border-radius:10px;
                                min-height:75px;
                            ">
                            <p>{row['Note']}</p>
                            </div>
                            """,
                            unsafe_allow_html=True,
                        )
                        if st.button("❌", key=f"del_note_{row['id']}"):
                            client.execute(
                                "DELETE FROM notes WHERE rowid = ? AND Username = ?;",
                                [row["id"], username]
                            )
                            invalidate_cache()
                            st.rerun()
            else:
                st.info("No notes yet. Add one above!")

    # --- Sidebar Stats ---
    with st.sidebar:
        st.header("📊 Task Statistics", divider="rainbow")
        if not df.empty:
            all_tasks_count = len(df)
            tasks_done = len(df[df["Status"] == "Done"])
            pending_tasks_count = all_tasks_count - tasks_done

            st.metric("Total Pending", pending_tasks_count)
            st.metric("📝 To Do", len(df[df["Status"] == "To Do"]))
            st.metric("⏳ In Progress", len(df[df["Status"] == "In Progress"]))
            st.metric("✔️ Completed", tasks_done)

            if all_tasks_count > 0:
                st.progress(tasks_done / all_tasks_count, text=f"{tasks_done/all_tasks_count:.0%} Complete")

            st.write("---")
            st.subheader("Priority Breakdown (Active Only)")

            # ✅ only count active tasks (exclude "Done")
            active_only = df[df["Status"] != "Done"]

            if not active_only.empty:
                priority_counts = active_only["Priority"].value_counts().reset_index()
                priority_counts.columns = ["Priority", "Count"]

                chart = alt.Chart(priority_counts).mark_bar(cornerRadius=5).encode(
                    x=alt.X("Count:Q", title="Number of Tasks"),
                    y=alt.Y("Priority:N", sort="-x"),
                    color=alt.Color(
                        "Priority:N",
                        scale=alt.Scale(
                            domain=["High", "Medium", "Low"],
                            range=["#e45756", "#f58518", "#54a24b"]
                        ),
                        legend=None
                    ),
                    tooltip=["Priority", "Count"]
                ).properties(title="Tasks by Priority")

                st.altair_chart(chart, use_container_width=True)
            else:
                st.write("No active tasks to show priority breakdown.")
        else:
            st.write("No tasks to show statistics for.")
