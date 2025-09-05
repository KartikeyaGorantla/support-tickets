import streamlit as st

if "notes" not in st.session_state:
    st.session_state.notes = []

# Input for new note
with st.form("add_note", clear_on_submit=True):
    new_note = st.text_area(" ", "")
    submitted = st.form_submit_button("Add Note")
    if submitted and new_note.strip():
        st.session_state.notes.append(new_note.strip())

for i, note in enumerate(st.session_state.notes):
    with st.container():
        st.markdown(
            f"""
            <div style="
                background-color:#262730;
                color: white;
                padding:15px;
                margin:10px;
                border-radius:10px;
                box-shadow:2px 2px 6px rgba(255,255,255,0.1);
                min-height:120px;
            ">
            <p>{note}</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        if st.button("❌ Delete", key=f"del_{i}"):
            st.session_state.notes.pop(i)
            st.rerun()
