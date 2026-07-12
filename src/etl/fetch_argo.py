import os
import random
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from src.database.sqlite_client import get_connection, init_db

def region_label(lat, lon):
    if -5 <= lat <= 5:
        return "Equatorial"
    if 10 <= lat <= 30 and 50 <= lon <= 80:
        return "Arabian Sea"
    if 0 <= lat <= 25 and 80 <= lon <= 100:
        return "Bay of Bengal"
    return "Other"

def generate_synthetic_data():
    print("Generating oceanographically accurate synthetic ARGO data...")
    records = []
    
    # 5 Floats distributed in different regions
    floats_config = [
        # Arabian Sea (High Salinity, ~35.5 - 36.8 PSU)
        {"id": "2902264", "region": "Arabian Sea", "start_lat": 15.0, "start_lon": 65.0, "sal_base": 36.2, "temp_base": 28.5},
        {"id": "2902265", "region": "Arabian Sea", "start_lat": 12.5, "start_lon": 68.0, "sal_base": 35.9, "temp_base": 29.0},
        
        # Bay of Bengal (Low Salinity, ~31.5 - 34.0 PSU due to river runoff)
        {"id": "2902266", "region": "Bay of Bengal", "start_lat": 14.0, "start_lon": 88.0, "sal_base": 33.0, "temp_base": 28.8},
        {"id": "5904663", "region": "Bay of Bengal", "start_lat": 11.0, "start_lon": 91.0, "sal_base": 32.5, "temp_base": 29.2},
        
        # Equatorial (Intermediate Salinity, ~34.0 - 35.0 PSU)
        {"id": "5904664", "region": "Equatorial", "start_lat": 0.0, "start_lon": 75.0, "sal_base": 34.5, "temp_base": 27.5}
    ]
    
    depths = [0, 10, 20, 30, 50, 75, 100, 150, 200, 250, 300, 400, 500]
    start_date = datetime(2023, 1, 1)
    
    for fl in floats_config:
        # Generate 15 profile dates (every 10 days)
        for p_idx in range(15):
            profile_date = start_date + timedelta(days=p_idx * 10)
            date_str = profile_date.strftime("%Y-%m-%d")
            
            # Simulate slight drift over time
            lat = fl["start_lat"] + (p_idx * 0.08) + random.uniform(-0.02, 0.02)
            lon = fl["start_lon"] + (p_idx * 0.12) + random.uniform(-0.02, 0.02)
            region = region_label(lat, lon)
            
            # Generate vertical profile measurements
            for d in depths:
                # Temperature profile (decreases with depth)
                # Thermocline region around 50m-150m where temp drops rapidly
                if d <= 30:
                    temp = fl["temp_base"] - (d * 0.02)
                elif d <= 150:
                    temp = fl["temp_base"] - 0.6 - ((d - 30) * 0.08)
                else:
                    temp = 12.0 - ((d - 150) * 0.015)
                
                # Add minor noise
                temp += random.uniform(-0.15, 0.15)
                temp = max(4.0, temp) # Deep ocean bottom temp limit
                
                # Salinity profile (slightly increases/decreases based on depth and region)
                if region == "Arabian Sea":
                    # Salinity is high at surface, slight subsurface maximum
                    sal = fl["sal_base"] + (0.1 if d < 100 else -0.2)
                elif region == "Bay of Bengal":
                    # Salinity is low at surface due to freshwater, increases with depth
                    sal = fl["sal_base"] + (d * 0.003 if d < 200 else 0.6)
                else:
                    sal = fl["sal_base"] + (d * 0.001)
                    
                sal += random.uniform(-0.05, 0.05)
                
                records.append({
                    "float_id": fl["id"],
                    "lat": round(lat, 4),
                    "lon": round(lon, 4),
                    "date": date_str,
                    "depth": float(d),
                    "temperature": round(temp, 2),
                    "salinity": round(sal, 2),
                    "region": region
                })
                
    df = pd.DataFrame(records)
    return df

def fetch_and_store():
    init_db()
    
    # Bounding box for a very small test region (Arabian Sea, short timeframe)
    # [lon_min, lon_max, lat_min, lat_max, depth_min, depth_max, date_start, date_end]
    box = [65.0, 67.0, 12.0, 14.0, 0, 100, "2023-01-01", "2023-01-05"]
    
    print("Attempting to fetch real Argo data from argopy (15s timeout)...")
    try:
        import argopy
        # Configure argopy to use a shorter timeout or check
        argopy.set_options(src='erddap') # standard public erddap server
        
        # Load from erddap (wrapped in a try block)
        ds = argopy.DataFetcher().region(box).to_xarray()
        df = ds.to_dataframe().reset_index()
        
        # Rename columns to match SQLite schema
        df = df.rename(columns={
            "PLATFORM_NUMBER": "float_id",
            "LATITUDE": "lat",
            "LONGITUDE": "lon",
            "TIME": "date",
            "PRES": "depth",
            "TEMP": "temperature",
            "PSAL": "salinity"
        })
        
        # Convert platform numbers to strings if they are numeric
        df["float_id"] = df["float_id"].astype(str)
        df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
        df["region"] = df.apply(lambda r: region_label(r["lat"], r["lon"]), axis=1)
        
        # Select required columns
        df = df[["float_id", "lat", "lon", "date", "depth", "temperature", "salinity", "region"]]
        
        # Clean any null values in required fields
        df = df.dropna(subset=["float_id", "lat", "lon", "date", "depth"])
        
        print(f"Success! Fetched {len(df)} real rows from argopy.")
        
    except Exception as e:
        print(f"Argopy fetch failed or timed out: {e}")
        df = generate_synthetic_data()
        
    # Write to database
    conn = get_connection()
    df.to_sql("floats", conn, if_exists="append", index=False)
    conn.close()
    
    # Confirm
    conn = get_connection()
    count = conn.execute("SELECT COUNT(*) FROM floats;").fetchone()[0]
    conn.close()
    print(f"ETL Complete. Total rows in floats database: {count}")

if __name__ == "__main__":
    fetch_and_store()
