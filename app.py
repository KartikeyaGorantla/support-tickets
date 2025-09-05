import streamlit as st
import pandas as pd
from datetime import datetime
import altair as alt
import streamlit_authenticator as stauth
from streamlit_authenticator.utilities.exceptions import LoginError
from libsql_client import create_client_sync

# --- Page Config ---
st.set_page_config(
    page_title="Database To-Do List",
    page_icon="🔐",
    layout="wide",
    initial_sidebar_state="auto",
)


# --- Turso DB Connection ---
def get_client():
    """Return a cached DB client."""
    if "db_client" not in st.session_state:
        st.session_state.db_client = create_client_sync(
            url=st.secrets["turso"]["url"],
            auth_token=st.secrets["turso"]["token"]
        )
    return st.session_state.db_client

def close_client():
    """Close DB client when app shuts down."""
    if "db_client" in st.session_state:
        try:
            st.session_state.db_client.close()
        except Exception:
            pass

st.on_event("shutdown", close_client)

client = get_client()

def init_db():
    """Ensure tasks and notes tables exist."""
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

def load_user_tasks(username: str) -> pd.DataFrame:
    rows = client.execute(
        "SELECT rowid AS id, * FROM tasks WHERE Username = ?;",
        [username]
    ).rows
    return pd.DataFrame(rows, columns=["id", "Username", "Task", "Status", "Priority", "CreatedAt"]) if rows else pd.DataFrame(
        columns=["id", "Username", "Task", "Status", "Priority", "CreatedAt"]
    )

def load_user_notes(username: str) -> pd.DataFrame:
    rows = client.execute(
        "SELECT rowid AS id, * FROM notes WHERE Username = ? ORDER BY CreatedAt DESC;",
        [username]
    ).rows
    return pd.DataFrame(rows, columns=["id", "Username", "Note", "CreatedAt"]) if rows else pd.DataFrame(
        columns=["id", "Username", "Note", "CreatedAt"]
    )

# --- Authenticator ---
authenticator = stauth.Authenticate(
    st.secrets["credentials"].to_dict(),
    st.secrets["cookies"]["name"],
    st.secrets["cookies"]["key"],
)

# --- Login ---
if not st.session_state.get("authentication_status"):
    col1, col2, col3 = st.columns([0.5, 2, 0.5])
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
    authenticator.logout("Logout", "sidebar", width="stretch")
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
            st.rerun()

        # --- Load Tasks ---
        df = load_user_tasks(username)
        active_tasks = df[df["Status"] != "Done"].copy()
        completed_tasks = df[df["Status"] == "Done"].copy()

        st.subheader("Active Tasks", divider="rainbow")

        if not active_tasks.empty:
            active_tasks["Delete"] = False

            edited_active_tasks = st.data_editor(
                active_tasks,
                width="stretch",
                hide_index=True,
                column_order=("Task", "Status", "Priority", "CreatedAt", "Delete"),
                column_config={
                    "Task": st.column_config.TextColumn("Task Description", required=True),
                    "Status": st.column_config.SelectboxColumn("Status", options=["To Do", "In Progress", "Done"], required=True),
                    "Priority": st.column_config.SelectboxColumn("Priority", options=["High", "Medium", "Low"], required=True),
                    "CreatedAt": st.column_config.DatetimeColumn("Created At", format="D MMM YYYY, h:mm a", disabled=True),
                    "Delete": st.column_config.CheckboxColumn("Delete"),
                },
                key="active_tasks_editor"
            )

            # Handle updates
            for idx, row in edited_active_tasks.iterrows():
                orig = active_tasks.loc[idx]
                if row["Task"] != orig["Task"] or row["Priority"] != orig["Priority"] or row["Status"] != orig["Status"]:
                    client.execute(
                        "UPDATE tasks SET Task = ?, Priority = ?, Status = ? WHERE rowid = ? AND Username = ?;",
                        [row["Task"], row["Priority"], row["Status"], row["id"], username]
                    )
                    st.rerun()

            # Handle deletes
            deleted_indices = edited_active_tasks[edited_active_tasks["Delete"]].index
            if not deleted_indices.empty:
                for idx in deleted_indices:
                    client.execute(
                        "DELETE FROM tasks WHERE rowid = ? AND Username = ?;",
                        [edited_active_tasks.loc[idx, "id"], username]
                    )
                st.rerun()

        else:
            st.info("No active tasks. Add one above!")

        st.subheader("Completed Tasks", divider="rainbow")
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
                        st.rerun()
                with col3:
                    if st.button("❌ Delete", key=f"delete_{row['id']}"):
                        client.execute(
                            "DELETE FROM tasks WHERE rowid = ? AND Username = ?;",
                            [row["id"], username]
                        )
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
            new_note = st.text_input(" ", placeholder="What do you need to remember?")
            submitted = st.form_submit_button("Add Note")
            if submitted and new_note.strip():
                client.execute(
                    "INSERT INTO notes (Username, Note, CreatedAt) VALUES (?, ?, ?);",
                    [username, new_note.strip(), datetime.now().isoformat()]
                )
                st.rerun()

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
                    if st.button("❌ Delete", key=f"del_note_{row['id']}"):
                        client.execute(
                            "DELETE FROM notes WHERE rowid = ? AND Username = ?;",
                            [row["id"], username]
                        )
                        st.rerun()
        else:
            st.info("No notes yet. Add one above!")

    # --- Sidebar Stats ---
    with st.sidebar:
        st.header("📊 Task Statistics", divider="rainbow")
        if not df.empty:
            total_tasks = len(df)
            tasks_done = len(df[df["Status"] == "Done"])

            st.metric("Total Tasks", total_tasks)
            st.metric("✔️ Completed", tasks_done)
            st.metric("📝 To Do", len(df[df["Status"] == "To Do"]))
            st.metric("⏳ In Progress", len(df[df["Status"] == "In Progress"]))

            if total_tasks > 0:
                st.progress(tasks_done / total_tasks, text=f"{tasks_done/total_tasks:.0%} Complete")

            st.write("---")
            st.subheader("Priority Breakdown")
            priority_counts = df["Priority"].value_counts().reset_index()
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

            st.altair_chart(chart, width="stretch")
        else:
            st.write("No tasks to show statistics for.")
