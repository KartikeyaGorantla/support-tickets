import streamlit as st
import pandas as pd
from datetime import datetime
import altair as alt
import streamlit_authenticator as stauth

# --- Page Configuration ---
st.set_page_config(
    page_title="Database To-Do List",
    page_icon="🔐",
    layout="centered"
)

# --- Turso Database Connection ---
conn = st.connection('turso', type='sql')

# --- Helper Functions for Database Operations ---
def init_db():
    """Creates the tasks table if it doesn't already exist."""
    with conn.session as s:
        s.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                Username TEXT NOT NULL,
                Task TEXT NOT NULL,
                Status TEXT,
                Priority TEXT,
                "Created At" DATETIME
            );
        """)
        s.commit()

def load_user_tasks(username):
    """Loads all tasks from the database for a specific user."""
    query = "SELECT rowid AS id, * FROM tasks WHERE Username = :username;"
    df = conn.query(query, ttl=0, params={"username": username})
    return df

# --- User Authentication ---
# The authenticator automatically handles the simplified credentials.
authenticator = stauth.Authenticate(
    st.secrets["credentials"],
    st.secrets["cookies"]["name"],
    st.secrets["cookies"]["key"],
    st.secrets["cookies"]["expiry_days"]
)

# The login function provides the username which we will use for display.
# The 'name' variable will be None, so we use 'username' instead.
name, authentication_status, username = authenticator.login()

# --- Main App Logic ---
if authentication_status:
    # Initialize the database table on the first successful login
    init_db()

    # Use 'username' for display as 'name' is no longer configured
    st.sidebar.write(f'Welcome *{username}*')
    authenticator.logout('Logout', 'sidebar')
    
    st.session_state.tasks_df = load_user_tasks(username)

    st.title(f"🔐 {username}'s To-Do List")
    st.write("Your tasks are securely saved to a cloud database.")
    st.write("---")

    # --- Add a New Task Section ---
    st.header("Add a New Task", divider="rainbow")
    with st.form("add_task_form", clear_on_submit=True):
        task_description = st.text_input("Task Description", placeholder="What do you need to do?")
        task_priority = st.selectbox("Priority", ["High", "Medium", "Low"])
        submitted = st.form_submit_button("Add Task")

    if submitted and task_description:
        with conn.session as s:
            s.execute(
                'INSERT INTO tasks (Username, Task, Status, Priority, "Created At") VALUES (:user, :desc, :status, :priority, :date);',
                params=dict(user=username, desc=task_description, status="To Do", priority=task_priority, date=datetime.now())
            )
            s.commit()
        st.rerun()

    st.write("---")
    
    # --- Task Display and Management ---
    df = st.session_state.tasks_df
    active_tasks = df[df["Status"] != "Done"].copy()
    completed_tasks = df[df["Status"] == "Done"].copy()
    
    st.header("Active Tasks", divider="rainbow")
    if not active_tasks.empty:
        # Simplified display for active tasks
        for index, row in active_tasks.iterrows():
            col1, col2 = st.columns([0.7, 0.3])
            with col1:
                st.write(f"**{row['Task']}** (Priority: {row['Priority']})")
            with col2:
                new_status = st.selectbox(
                    f"Status for task {row['id']}",
                    options=["To Do", "In Progress", "Done"],
                    index=["To Do", "In Progress", "Done"].index(row['Status']),
                    key=f"status_{row['id']}",
                    label_visibility="collapsed"
                )

            if new_status != row['Status']:
                with conn.session as s:
                    s.execute('UPDATE tasks SET Status = :status WHERE rowid = :id AND Username = :user;',
                              params=dict(status=new_status, id=row['id'], user=username))
                    s.commit()
                st.rerun()
    else:
        st.info("No active tasks.")
        
    st.header("Completed Tasks", divider="rainbow")
    if not completed_tasks.empty:
        for index, row in completed_tasks.iterrows():
            col1, col2, col3 = st.columns([0.6, 0.2, 0.2])
            with col1:
                st.markdown(f"~~_{row['Task']}_~~")
            with col2:
                if st.button("Undo", key=f"undo_{row['id']}"):
                    with conn.session as s:
                        s.execute('UPDATE tasks SET Status = "To Do" WHERE rowid = :id AND Username = :user;',
                                  params=dict(id=row['id'], user=username))
                        s.commit()
                    st.rerun()
            with col3:
                if st.button("❌ Delete", key=f"delete_completed_{row['id']}"):
                    with conn.session as s:
                        s.execute('DELETE FROM tasks WHERE rowid = :id AND Username = :user;',
                                  params=dict(id=row['id'], user=username))
                        s.commit()
                    st.rerun()
    else:
        st.info("No tasks have been completed yet.")
        
elif authentication_status is False:
    st.error('Username/password is incorrect')
elif authentication_status is None:
    st.title("🔐 Welcome to the Multi-User To-Do App")
    st.warning('Please enter your username and password')