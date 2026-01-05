import streamlit as st
import pandas as pd

# Page configuration
st.set_page_config(page_title="Kannada Voter Search", layout="wide")

st.title("🗳️ Kannada Voter List Search Engine")
st.markdown("""
    This tool handles **500,000+ rows** without crashing. 
    It fixes the **#NAME?** and **garbled text** issues found in Excel.
""")

# 1. Sidebar for File Upload
with st.sidebar:
    st.header("Upload Data")
    uploaded_file = st.file_uploader("Upload CSV or Excel file", type=['csv', 'xlsx'])
    st.info("Note: Large CSV files work faster than Excel files.")

if uploaded_file:
    # 2. Optimized Data Loading
    @st.cache_data(show_spinner="Indexing half a million rows...")
    def load_data(file):
        try:
            if file.name.endswith('.csv'):
                # dtype=str prevents #NAME? errors by treating all data as text
                # low_memory=False ensures the entire column is parsed correctly
                return pd.read_csv(file, encoding='utf-8', dtype=str, low_memory=False)
            else:
                return pd.read_excel(file, dtype=str)
        except UnicodeDecodeError:
            # Fallback for older file encodings
            return pd.read_csv(file, encoding='latin1', dtype=str)

    df = load_data(uploaded_file)
    
    # 3. Search Interface
    col1, col2 = st.columns([1, 3])
    
    with col1:
        # Added "All Columns" option to the list of columns
        columns_list = ["All Columns"] + list(df.columns)
        search_column = st.selectbox("Select Column to Search", columns_list)
        st.write(f"Total Records: {len(df):,}")

    with col2:
        search_term = st.text_input(f"Type Kannada Name (or part of a name) to search in {search_column}")

    # 4. Search Logic
    if search_term:
        # Vectorized string search is much faster than Excel's Ctrl+F
        # regex=False fixes the crash/error when searching for names with parentheses ()
        
        if search_column == "All Columns":
            # Search across the entire dataframe efficiently
            # We join all columns for each row into a single string and search that
            mask = df.apply(lambda x: x.astype(str).str.contains(search_term, na=False, case=False, regex=False)).any(axis=1)
            results = df[mask]
        else:
            results = df[df[search_column].str.contains(search_term, na=False, case=False, regex=False)]
        
        st.success(f"✅ Found {len(results):,} matches out of {len(df):,} records.")
        
        # Display Results
        st.dataframe(results, use_container_width=True)
        
        # 5. Export Feature
        if not results.empty:
            # utf-8-sig ensures the downloaded file opens correctly in Excel
            csv_data = results.to_csv(index=False).encode('utf-8-sig')
            st.download_button(
                label="📥 Download Search Results for Excel",
                data=csv_data,
                file_name=f"search_results_{search_term}.csv",
                mime='text/csv',
            )
    else:
        st.info("Showing a preview of the first 50 rows. Enter a name above to search.")
        st.dataframe(df.head(50), use_container_width=True)

else:
    st.warning("Please upload your voter list file to begin.")