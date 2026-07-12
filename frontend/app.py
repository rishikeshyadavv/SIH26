import streamlit as st
import requests
import pandas as pd
import plotly.express as px
import folium
from streamlit_folium import st_folium
import sqlite3
import os

# Page config
st.set_page_config(
    page_title="FloatChat 🌊 - Conversational ARGO Ocean Data Explorer",
    page_icon="🌊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# API configuration
API_URL = os.getenv("API_URL", "http://127.0.0.1:8000/ask")
DB_PATH = os.getenv("DB_PATH", "data/argo_data.db")

# Helper to fetch DB stats directly for the sidebar
def get_db_stats():
    try:
        if not os.path.exists(DB_PATH):
            return None
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        total_records = cursor.execute("SELECT COUNT(*) FROM floats;").fetchone()[0]
        unique_floats = cursor.execute("SELECT COUNT(DISTINCT float_id) FROM floats;").fetchone()[0]
        regions = cursor.execute("SELECT DISTINCT region FROM floats;").fetchall()
        regions_list = [r[0] for r in regions if r[0]]
        date_range = cursor.execute("SELECT MIN(date), MAX(date) FROM floats;").fetchone()
        conn.close()
        return {
            "total_records": total_records,
            "unique_floats": unique_floats,
            "regions": ", ".join(regions_list),
            "date_start": date_range[0],
            "date_end": date_range[1]
        }
    except Exception as e:
        return {"error": str(e)}

# Inject custom clean styling for a slight ocean touch
st.markdown("""
<style>
    .reportview-container {
        background: #0e1117;
    }
    .sidebar .sidebar-content {
        background: #161b22;
    }
    div.stButton > button:first-child {
        background-color: #0f62fe;
        color: white;
        border-radius: 6px;
        border: none;
    }
    div.stButton > button:first-child:hover {
        background-color: #0353e9;
        color: white;
    }
</style>
""", unsafe_allow_html=True)

# Main Title & Subtitle
st.title("🌊 FloatChat — Ask the Ocean Anything")
st.markdown("Interact with global ocean-monitoring ARGO floats using plain-English questions. Ask about temperatures, salinity profiles, and locations.")

# Initialize session state for messages and inputs
if "messages" not in st.session_state:
    st.session_state.messages = []
if "query_input" not in st.session_state:
    st.session_state.query_input = ""

# Sidebar
with st.sidebar:
    st.image("https://img.icons8.com/color/96/000000/sea-waves.png", width=80)
    st.header("FloatChat Control Panel")
    
    # Live DB stats
    stats = get_db_stats()
    if stats and "error" not in stats:
        st.markdown("### 📊 Database Statistics")
        st.markdown(f"**Total Records:** `{stats['total_records']}` rows")
        st.markdown(f"**Active Floats:** `{stats['unique_floats']}` floats")
        st.markdown(f"**Regions:** {stats['regions']}")
        st.markdown(f"**Temporal Coverage:** `{stats['date_start']}` to `{stats['date_end']}`")
    else:
        st.warning("Database stats unavailable.")
        
    st.markdown("---")
    st.markdown("### 💡 Quick Start Questions")
    
    # 4 interactive buttons in sidebar
    quick_questions = [
        "Show me the temperature profile of float 2902264",
        "What's the salinity in the Arabian Sea in January 2023?",
        "Compare salinity in the Arabian Sea vs Bay of Bengal",
        "Find nearest ARGO floats to lat 12, lon 65"
    ]
    
    for qq in quick_questions:
        if st.button(qq, use_container_width=True):
            st.session_state.query_input = qq

# Callback to process query
def process_query(question_text):
    if not question_text:
        return
        
    # Append user question to chat history
    st.session_state.messages.append({"role": "user", "content": question_text})
    
    # Send request to backend API
    with st.spinner("Analyzing data..."):
        try:
            res = requests.post(API_URL, json={"question": question_text}, timeout=15)
            if res.status_code == 200:
                api_res = res.json()
                st.session_state.messages.append({"role": "assistant", "data": api_res})
            else:
                st.session_state.messages.append({
                    "role": "assistant",
                    "data": {
                        "success": False,
                        "error": f"API returned error code {res.status_code}: {res.text}",
                        "sql": "No SQL generated"
                    }
                })
        except Exception as e:
            st.session_state.messages.append({
                "role": "assistant",
                "data": {
                    "success": False,
                    "error": f"Failed to connect to API backend: {e}",
                    "sql": "No SQL generated"
                }
            })

# Check if query was triggered via sidebar quick actions
if st.session_state.query_input:
    input_to_run = st.session_state.query_input
    st.session_state.query_input = ""  # Reset
    process_query(input_to_run)

# Render Chat History
for msg in st.session_state.messages:
    if msg["role"] == "user":
        with st.chat_message("user", avatar="👤"):
            st.write(msg["content"])
    else:
        with st.chat_message("assistant", avatar="🌊"):
            res = msg["data"]
            if not res.get("success"):
                st.error(f"❌ Error: {res.get('error')}")
                if res.get("sql"):
                    st.markdown("**Generated SQL:**")
                    st.code(res["sql"], language="sql")
                continue
                
            # Header info
            st.success("✅ Query executed successfully!")
            
            # Show SQL code block
            st.markdown("**Generated SQL Query:**")
            st.code(res["sql"], language="sql")
            
            # Convert raw records back to pandas dataframe
            df = pd.DataFrame(res["data"])
            
            if df.empty:
                st.warning("⚠️ No records matched this query.")
                continue
                
            # Create three tabs: Data Table, Charts, Map
            tab1, tab2, tab3 = st.tabs(["📋 Data Table", "📈 Dynamic Charts", "🗺️ Geospatial Map"])
            
            with tab1:
                st.markdown(f"Showing first 50 of **{len(df)}** rows matching your request.")
                st.dataframe(df.head(50), use_container_width=True)
                
            with tab2:
                # Vertical depth profile chart if depth and temperature/salinity are present
                has_depth = "depth" in df.columns
                has_temp = "temperature" in df.columns
                has_sal = "salinity" in df.columns
                
                if has_depth and (has_temp or has_sal):
                    # Separate profiles if multiple floats are in the query results
                    color_col = "float_id" if "float_id" in df.columns and df["float_id"].nunique() > 1 else None
                    
                    if has_temp and has_sal:
                        # Double-column plot
                        col1, col2 = st.columns(2)
                        with col1:
                            fig_temp = px.line(
                                df.sort_values(by="depth"), 
                                x="temperature", 
                                y="depth", 
                                color=color_col,
                                title="Temperature vs Depth Profile",
                                labels={"temperature": "Temperature (°C)", "depth": "Depth (m/dbar)"}
                            )
                            fig_temp.update_yaxes(autorange="reversed")  # Reverse Y-axis (depth goes down)
                            st.plotly_chart(fig_temp, use_container_width=True)
                            
                        with col2:
                            fig_sal = px.line(
                                df.sort_values(by="depth"), 
                                x="salinity", 
                                y="depth", 
                                color=color_col,
                                title="Salinity vs Depth Profile",
                                labels={"salinity": "Salinity (PSU)", "depth": "Depth (m/dbar)"}
                            )
                            fig_sal.update_yaxes(autorange="reversed")
                            st.plotly_chart(fig_sal, use_container_width=True)
                    elif has_temp:
                        fig_temp = px.line(
                            df.sort_values(by="depth"), 
                            x="temperature", 
                            y="depth", 
                            color=color_col,
                            title="Temperature vs Depth Profile",
                            labels={"temperature": "Temperature (°C)", "depth": "Depth (m)"}
                        )
                        fig_temp.update_yaxes(autorange="reversed")
                        st.plotly_chart(fig_temp, use_container_width=True)
                    elif has_sal:
                        fig_sal = px.line(
                            df.sort_values(by="depth"), 
                            x="salinity", 
                            y="depth", 
                            color=color_col,
                            title="Salinity vs Depth Profile",
                            labels={"salinity": "Salinity (PSU)", "depth": "Depth (m)"}
                        )
                        fig_sal.update_yaxes(autorange="reversed")
                        st.plotly_chart(fig_sal, use_container_width=True)
                else:
                    # Generic chart for other query structures (e.g. average salinity by region)
                    numeric_cols = df.select_dtypes(include=["number"]).columns
                    categorical_cols = df.select_dtypes(include=["object"]).columns
                    
                    if len(categorical_cols) > 0 and len(numeric_cols) > 0:
                        fig = px.bar(
                            df, 
                            x=categorical_cols[0], 
                            y=numeric_cols[0], 
                            title=f"{numeric_cols[0]} by {categorical_cols[0]}",
                            template="plotly_dark"
                        )
                        st.plotly_chart(fig, use_container_width=True)
                    else:
                        st.info("No profiling parameters (depth, temperature, salinity) found in output columns to chart.")

            with tab3:
                # Plot locations on Folium map if lat/lon exist
                if "lat" in df.columns and "lon" in df.columns:
                    # Drop NaN coordinates
                    map_df = df.dropna(subset=["lat", "lon"])
                    
                    if not map_df.empty:
                        # Find center coordinate
                        center_lat = map_df["lat"].mean()
                        center_lon = map_df["lon"].mean()
                        
                        m = folium.Map(location=[center_lat, center_lon], zoom_start=4)
                        
                        # Add markers for unique profiles (group by present identifiers to prevent clutter)
                        group_cols = [col for col in ["float_id", "lat", "lon", "date"] if col in map_df.columns]
                        if group_cols:
                            unique_locs = map_df.groupby(group_cols).first().reset_index()
                        else:
                            unique_locs = map_df
                        
                        for _, row in unique_locs.head(100).iterrows():
                            popup_html = f"<b>Coordinates:</b> {row['lat']:.4f}, {row['lon']:.4f}<br>"
                            if "float_id" in row:
                                popup_html = f"<b>Float ID:</b> {row['float_id']}<br>" + popup_html
                            if "date" in row:
                                popup_html += f"<b>Date:</b> {row['date']}<br>"
                            # Include temperature and salinity in popup if they exist in output
                            if "temperature" in row:
                                popup_html += f"<b>Temp:</b> {row['temperature']} °C<br>"
                            if "salinity" in row:
                                popup_html += f"<b>Salinity:</b> {row['salinity']} PSU<br>"
                                
                            folium.Marker(
                                location=[row["lat"], row["lon"]],
                                popup=folium.Popup(popup_html, max_width=300),
                                icon=folium.Icon(color="blue", icon="info-sign")
                            ).add_to(m)
                            
                        st_folium(m, width="100%", height=400, returned_objects=[])
                    else:
                        st.warning("Coordinate data contains only nulls.")
                else:
                    st.info("No spatial data (lat, lon) in output columns to plot on a map.")

# Chat input bar at bottom
user_input = st.chat_input("Ask a question about the ARGO float data...")
if user_input:
    process_query(user_input)
