import streamlit as st
import pandas as pd
import os
import requests
import re
import itertools
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

with st.sidebar:
    st.header("Select Data Files")
    if files:
        # Default to all files if less than 3, otherwise just the first one to avoid huge load interactions? 
        # Actually user wants to search AC_177 "as well", so likely wants all.
        # Let's default to all files for convenience as per user intent.
        selected_files = st.multiselect("Choose voter lists", files, default=files)
        
    else:
        st.error(f"No CSV/Excel files found in '{data_folder}' folder.")
        st.info("Please put any '2002 Voter list....csv' files inside the 'data' folder.")

if files and selected_files:
    # 2. Optimized Data Loading
    @st.cache_data(show_spinner="Loading data...", ttl="2h")
    def load_single_file(file_path):
        try:
            if file_path.endswith('.csv'):
                # dtype=str prevents #NAME? errors by treating all data as text
                return pd.read_csv(file_path, encoding='utf-8', dtype=str, low_memory=False)
            else:
                return pd.read_excel(file_path, dtype=str)
        except UnicodeDecodeError:
            # Fallback for older file encodings
            return pd.read_csv(file_path, encoding='latin1', dtype=str)

    # Load all selected files and concatenate
    dfs = []
    # Create a progress bar if loading multiple files might take time
    progress_text = "Loading selected files..."
    my_bar = st.progress(0, text=progress_text)
    
    for i, file_name in enumerate(selected_files):
        full_path = os.path.join(data_folder, file_name)
        dfs.append(load_single_file(full_path))
        my_bar.progress((i + 1) / len(selected_files), text=f"Loaded {file_name}")
    
    my_bar.empty()
    
    if dfs:
        df = pd.concat(dfs, ignore_index=True)
    else:
        df = pd.DataFrame()

    # 2b. Transliteration Function
    @st.cache_data(show_spinner=False)
    def transliterate_text(text, lang='kn', max_results=5):
        """
        Transliterates English text to Kannada using Google Input Tools API.
        Returns a list of top unique transliterations (up to max_results).
        """
        url = "https://inputtools.google.com/request"
        params = {
            'text': text,
            'itc': f'{lang}-t-i0-und',
            'num': max_results, # Candidates per word
            'cp': 0,
            'cs': 1,
            'ie': 'utf-8',
            'oe': 'utf-8',
            'app': 'demopage'
        }
        try:
            response = requests.get(url, params=params, timeout=5)
            if response.status_code == 200:
                result = response.json()
                if result[0] == 'SUCCESS':
                    # result[1] involves a list of [original, [suggestions], ...] for each token
                    token_suggestions = []
                    for item in result[1]:
                        # item[1] is the list of suggestions for this token
                        token_suggestions.append(item[1])
                    
                    # Generate combinations (e.g. "Ravi" + " " + "Kumar")
                    # We limit the cartesian product to avoid explosion
                    combinations = list(itertools.product(*token_suggestions))
                    
                    # Join tokens to form full phrases
                    transliterated_phrases = ["".join(combo) for combo in combinations]
                    
                    # Deduplicate and return top N
                    unique_phrases = list(dict.fromkeys(transliterated_phrases))
                    return unique_phrases[:max_results]
        except Exception as e:
            # Silently fail or log? For UI, maybe just return empty or original
            pass
        return [text]
    
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
                # Check for English input
                is_english = bool(re.search(r'[a-zA-Z]', search_term))
                search_variations = [search_term]

                if is_english:
                    with st.spinner('Transliterating...'):
                        transliterated = transliterate_text(search_term)
                        # If we got actual Kannada results (different from input), use them
                        if transliterated and transliterated != [search_term]:
                            search_variations = transliterated
                            st.info(f"🔎 Searching for Kannada variations: {', '.join(search_variations)}")
                
                # Search for ANY of the variations
                # We combine the masks for each variation with OR
                final_mask = pd.Series([False] * len(df))
                
                for term in search_variations:
                    keywords = term.split()
                    # term_mask assumes ALL keywords in this specific term must be present
                    term_mask = pd.Series([True] * len(df))
                    for keyword in keywords:
                        term_mask = term_mask & search_series.str.contains(keyword, na=False, case=False, regex=False)
                    
                    final_mask = final_mask | term_mask
                
                results = df[final_mask]
            
            # B. Fuzzy Search (Slower, handles typos)
            else:
                # Check for English input
                is_english = bool(re.search(r'[a-zA-Z]', search_term))
                target_term = search_term
                
                if is_english:
                    with st.spinner('Transliterating for fuzzy search...'):
                         transliterated = transliterate_text(search_term, max_results=1)
                         if transliterated:
                             target_term = transliterated[0]
                             st.info(f"Using primary transliteration for fuzzy search: {target_term}")

                # RapidFuzz extraction
                # This can be slow on 500k rows, so we proceed carefully.
                # We use process.extract to find matches with a score cutoff.
                # However, extract works on a list/series.
                
                # Limited to top 100 matches to prevent UI freeze if everything matches slightly
                matches = process.extract(
                    target_term, 
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
    st.warning("No data file selected. Please choose at least one file from the sidebar.")