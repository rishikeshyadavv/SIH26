import os
import random
import requests
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import xarray as xr
from src.database.db_client import init_db, insert_dataframe, get_connection

# Disable urllib3 SSL warnings
requests.packages.urllib3.disable_warnings()

def region_label(lat, lon):
    if -5 <= lat <= 5:
        return "Equatorial"
    if 10 <= lat <= 30 and 50 <= lon <= 80:
        return "Arabian Sea"
    if 0 <= lat <= 25 and 80 <= lon <= 100:
        return "Bay of Bengal"
    return "Other"

def generate_synthetic_data():
    print("Generating oceanographically accurate synthetic ARGO data as fallback...")
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
                if d <= 30:
                    temp = fl["temp_base"] - (d * 0.02)
                elif d <= 150:
                    temp = fl["temp_base"] - 0.6 - ((d - 30) * 0.08)
                else:
                    temp = 12.0 - ((d - 150) * 0.015)
                
                # Add minor noise
                temp += random.uniform(-0.15, 0.15)
                temp = max(4.0, temp)
                
                # Salinity profile
                if region == "Arabian Sea":
                    sal = fl["sal_base"] + (0.1 if d < 100 else -0.2)
                elif region == "Bay of Bengal":
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

def fetch_real_netcdf_float(wmo_id, dac_suggested):
    """
    Downloads and parses a real NetCDF file from the Ifremer GDAC.
    Retries different DAC directories if the suggested one fails.
    """
    dacs = [dac_suggested] + [d for d in ["incois", "aoml", "coriolis", "jma", "kordi", "meds", "bodc", "csio", "csiro"] if d != dac_suggested]
    temp_filename = f"temp_{wmo_id}_prof.nc"
    
    success = False
    downloaded_path = None
    
    for dac in dacs:
        url = f"https://data-argo.ifremer.fr/dac/{dac}/{wmo_id}/{wmo_id}_prof.nc"
        print(f"Trying to download: {url}")
        try:
            res = requests.get(url, verify=False, timeout=15)
            if res.status_code == 200:
                with open(temp_filename, "wb") as f:
                    f.write(res.content)
                print(f"Successfully downloaded {wmo_id}_prof.nc from DAC '{dac}'")
                downloaded_path = temp_filename
                success = True
                break
            else:
                print(f"Skipping {dac}: HTTP {res.status_code}")
        except Exception as e:
            print(f"Failed to fetch from DAC {dac}: {e}")
            
    if not success or not downloaded_path:
        raise ValueError(f"Could not download profile data for WMO float {wmo_id} from any DAC.")
        
    records = []
    try:
        with xr.open_dataset(downloaded_path) as ds:
            # Check dimensions
            n_prof = ds.sizes.get('N_PROF', 0)
            n_levels = ds.sizes.get('N_LEVELS', 0)
            print(f"Float {wmo_id}: Found {n_prof} profiles, {n_levels} vertical levels.")
            
            # Extract variables as numpy arrays
            platform_numbers = ds['PLATFORM_NUMBER'].values
            latitudes = ds['LATITUDE'].values
            longitudes = ds['LONGITUDE'].values
            julds = ds['JULD'].values
            pres = ds['PRES'].values
            temp = ds['TEMP'].values
            psal = ds['PSAL'].values
            
            # Limit profiles to last 15 profiles to keep database size optimal and relevant
            profile_indices = range(max(0, n_prof - 15), n_prof)
            
            for i in profile_indices:
                try:
                    # Platform number is typically bytes
                    p_bytes = platform_numbers[i]
                    float_id = p_bytes.decode('utf-8').strip() if isinstance(p_bytes, bytes) else str(p_bytes).strip()
                    
                    lat = float(latitudes[i])
                    lon = float(longitudes[i])
                    
                    if np.isnan(lat) or np.isnan(lon):
                        continue
                        
                    region = region_label(lat, lon)
                    date_str = pd.to_datetime(julds[i]).strftime("%Y-%m-%d")
                    
                    for j in range(n_levels):
                        p_val = float(pres[i, j])
                        t_val = float(temp[i, j])
                        s_val = float(psal[i, j])
                        
                        # Only ingest non-null surface/subsurface records (let's say up to 600m depth)
                        if np.isnan(p_val) or np.isnan(t_val) or np.isnan(s_val):
                            continue
                        if p_val < 0 or p_val > 600:
                            continue
                            
                        records.append({
                            "float_id": float_id,
                            "lat": round(lat, 4),
                            "lon": round(lon, 4),
                            "date": date_str,
                            "depth": round(p_val, 2),
                            "temperature": round(t_val, 2),
                            "salinity": round(s_val, 2),
                            "region": region
                        })
                except Exception as entry_err:
                    # Skip problematic profiles
                    continue
    finally:
        if os.path.exists(downloaded_path):
            try:
                os.remove(downloaded_path)
            except Exception as clean_err:
                print(f"Error removing temp file: {clean_err}")
                
    df = pd.DataFrame(records)
    print(f"Extracted {len(df)} records for float {wmo_id}")
    return df

def fetch_and_store():
    # Initialize the database (DuckDB / TimescaleDB)
    init_db()
    
    # 6 WMO Floats to ingest (real WMO platforms)
    floats_to_fetch = [
        {"id": "2902264", "dac": "incois"},
        {"id": "2902265", "dac": "incois"},
        {"id": "2902266", "dac": "incois"},
        {"id": "5904663", "dac": "aoml"},
        {"id": "5904664", "dac": "aoml"},
        {"id": "6900186", "dac": "coriolis"}
    ]
    
    all_data = []
    errors = []
    
    print("Attempting to ingest real ARGO NetCDF files from Ifremer GDAC...")
    for fl in floats_to_fetch:
        try:
            df = fetch_real_netcdf_float(fl["id"], fl["dac"])
            if not df.empty:
                all_data.append(df)
        except Exception as e:
            msg = f"Failed to fetch/parse real data for float {fl['id']}: {e}"
            print(msg)
            errors.append(msg)
            
    if all_data:
        # Concatenate and insert real data
        final_df = pd.concat(all_data, ignore_index=True)
        print(f"Ingesting {len(final_df)} rows of REAL oceanographic data...")
        insert_dataframe(final_df, "floats")
    else:
        print("Real data ingestion failed entirely. Falling back to synthetic generator...")
        synthetic_df = generate_synthetic_data()
        print(f"Ingesting {len(synthetic_df)} rows of synthetic data...")
        insert_dataframe(synthetic_df, "floats")
        
    # Verify count
    conn = get_connection()
    # Check table row count
    db_type = os.getenv("DB_TYPE", "duckdb").lower()
    if db_type == "postgres":
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM floats;")
        count = cur.fetchone()[0]
        cur.close()
    else:
        count = conn.execute("SELECT COUNT(*) FROM floats;").fetchone()[0]
    conn.close()
    
    print(f"ETL Complete. Total rows in floats database: {count}")

if __name__ == "__main__":
    fetch_and_store()
