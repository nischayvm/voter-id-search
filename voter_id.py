import streamlit as st
import pandas as pd
import os
from rapidfuzz import process, fuzz

# Page configuration
st.set_page_config(page_title="Kannada Voter Search", layout="wide")

st.title("🗳️ Kannada Voter List Search Engine")
st.markdown("""
    This tool handles **500,000+ rows**. 
    It supports **Smart Search** (finds names in any order) and **Fuzzy Search** (handles typos).
""")

# 1. Sidebar for File Selection (Local Data)
data_folder = 'data'
if not os.path.exists(data_folder):
    os.makedirs(data_folder)

files = [f for f in os.listdir(data_folder) if f.endswith(('.csv', '.xlsx'))]

selected_file_path = None
with st.sidebar:
    st.header("Select Data File")
    if files:
        selected_file = st.selectbox("Choose a voter list", files)
        selected_file_path = os.path.join(data_folder, selected_file)
    else:
        st.error(f"No CSV/Excel files found in '{data_folder}' folder.")
        st.info("Please put any '2002 Voter list....csv' files inside the 'data' folder.")

if selected_file_path:
    # 2. Optimized Data Loading
    @st.cache_data(show_spinner="Indexing half a million rows...", ttl="2h")
    def load_data(file_path):
        try:
            if file_path.endswith('.csv'):
                # dtype=str prevents #NAME? errors by treating all data as text
                return pd.read_csv(file_path, encoding='utf-8', dtype=str, low_memory=False)
            else:
                return pd.read_excel(file_path, dtype=str)
        except UnicodeDecodeError:
            # Fallback for older file encodings
            return pd.read_csv(file_path, encoding='latin1', dtype=str)

    df = load_data(selected_file_path)
    
    # 3. Search Interface
    col1, col2 = st.columns([1, 2])
    
    with col1:
        # "All Columns" is the default and most useful mode
        columns_list = ["All Columns"] + list(df.columns)
        search_column = st.selectbox("Select Column to Search", columns_list)
        
        # Toggle for Fuzzy Search
        use_fuzzy = st.checkbox("Enable Fuzzy Search (Slower)", help="Use this if you can't find a name due to spelling mistakes or slight differences.")
        st.write(f"Total Records: {len(df):,}")

    with col2:
        search_term = st.text_input(f"Type Kannada Name (e.g., 'Shankrappa Hanagal')", key="search_box")

    # 4. Search Logic
    if search_term:
        with st.spinner('Searching 500,000+ records...'):
            results = pd.DataFrame()
            
            # Prepare search text: Normalize string logic
            # If searching "All Columns", we assume a concatenated string representation for each row
            if search_column == "All Columns":
                # For speed, we create a single "text_content" series to search against
                # We cache this operation inside a transient check or just compute it
                search_series = df.astype(str).agg(' '.join, axis=1)
            else:
                search_series = df[search_column].astype(str)

            # A. Smart Permutation Search (Fast, exact words)
            if not use_fuzzy:
                keywords = search_term.split()
                # Start with all true
                mask = pd.Series([True] * len(df))
                
                for keyword in keywords:
                    # Accumulate filters: must contain keyword1 AND keyword2 ...
                    mask = mask & search_series.str.contains(keyword, na=False, case=False, regex=False)
                
                results = df[mask]
            
            # B. Fuzzy Search (Slower, handles typos)
            else:
                # RapidFuzz extraction
                # This can be slow on 500k rows, so we proceed carefully.
                # We use process.extract to find matches with a score cutoff.
                # However, extract works on a list/series.
                
                # Limited to top 100 matches to prevent UI freeze if everything matches slightly
                matches = process.extract(
                    search_term, 
                    search_series, 
                    scorer=fuzz.token_sort_ratio, 
                    limit=100,
                    score_cutoff=70
                ) 
                # matches is a list of tuples: (match_string, score, index)
                if matches:
                     indices = [match[2] for match in matches]
                     results = df.iloc[indices]

        # 5. Display Results
        if not results.empty:
            st.success(f"✅ Found {len(results):,} matches out of {len(df):,} records.")
            st.dataframe(results, use_container_width=True)
            
            # Export Feature
            csv_data = results.to_csv(index=False).encode('utf-8-sig')
            st.download_button(
                label="📥 Download Search Results",
                data=csv_data,
                file_name=f"search_results_{search_term}.csv",
                mime='text/csv',
            )
        else:
            st.warning("No matching records found.")
            if not use_fuzzy:
                 st.info("Try enabling 'Fuzzy Search' if you suspect a spelling difference.")

    else:
        st.info("Showing a preview of the first 50 rows.")
        st.dataframe(df.head(50), use_container_width=True)

else:
    st.warning("No data file selected.")