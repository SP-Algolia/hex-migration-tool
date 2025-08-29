import streamlit as st
import os
import yaml
import zipfile
import io
import tempfile
import sys

# Configure page
st.set_page_config(
    page_title="Hex → Databricks Migration Tool",
    page_icon="🚀",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for better styling with light/dark theme support
st.markdown("""
<style>
    /* Theme-aware CSS variables */
    :root {
        --primary-blue: #2E86AB;
        --primary-blue-light: #A23B72;
        --accent-orange: #F18F01;
        --accent-green: #C73E1D;
        --success-green: #28a745;
        --warning-yellow: #ffc107;
        --error-red: #dc3545;
        --info-blue: #17a2b8;
        
        /* Light theme colors */
        --bg-primary: #ffffff;
        --bg-secondary: #f8f9fa;
        --text-primary: #212529;
        --text-secondary: #6c757d;
        --border-light: #dee2e6;
        --shadow: rgba(0, 0, 0, 0.1);
    }
    
    /* Dark theme overrides */
    @media (prefers-color-scheme: dark) {
        :root {
            --bg-primary: #1e1e1e;
            --bg-secondary: #2d2d2d;
            --text-primary: #ffffff;
            --text-secondary: #b3b3b3;
            --border-light: #404040;
            --shadow: rgba(255, 255, 255, 0.1);
        }
    }
    
    /* Main header with gradient */
    .main-header {
        font-size: 2.8rem;
        font-weight: 700;
        background: linear-gradient(135deg, var(--primary-blue), var(--primary-blue-light));
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;
        text-align: center;
        margin-bottom: 2rem;
        text-shadow: 2px 2px 4px var(--shadow);
    }
    
    /* Step headers with modern styling */
    .step-header {
        font-size: 1.6rem;
        font-weight: 600;
        color: var(--accent-orange);
        margin-top: 2rem;
        margin-bottom: 1rem;
        padding-bottom: 0.5rem;
        border-bottom: 2px solid var(--accent-orange);
        position: relative;
    }
    
    .step-header::before {
        content: '';
        position: absolute;
        bottom: -2px;
        left: 0;
        width: 60px;
        height: 2px;
        background: var(--primary-blue);
    }
    
    /* Enhanced info boxes with better contrast and shadows */
    .success-box {
        background: linear-gradient(135deg, #d4edda, #c3e6cb);
        border: 1px solid var(--success-green);
        border-radius: 12px;
        padding: 1.5rem;
        margin: 1.5rem 0;
        box-shadow: 0 4px 6px var(--shadow);
        border-left: 4px solid var(--success-green);
    }
    
    .warning-box {
        background: linear-gradient(135deg, #fff3cd, #ffeaa7);
        border: 1px solid var(--warning-yellow);
        border-radius: 12px;
        padding: 1.5rem;
        margin: 1.5rem 0;
        box-shadow: 0 4px 6px var(--shadow);
        border-left: 4px solid var(--warning-yellow);
    }
    
    .info-box {
        background: linear-gradient(135deg, #e3f2fd, #bbdefb);
        border: 1px solid var(--info-blue);
        border-radius: 12px;
        padding: 1.5rem;
        margin: 1.5rem 0;
        box-shadow: 0 4px 6px var(--shadow);
        border-left: 4px solid var(--info-blue);
    }
    
    .error-box {
        background: linear-gradient(135deg, #f8d7da, #f1c2c7);
        border: 1px solid var(--error-red);
        border-radius: 12px;
        padding: 1.5rem;
        margin: 1.5rem 0;
        box-shadow: 0 4px 6px var(--shadow);
        border-left: 4px solid var(--error-red);
    }
    
    /* Dark theme specific overrides for boxes */
    @media (prefers-color-scheme: dark) {
        .success-box {
            background: linear-gradient(135deg, #1e3a1e, #2d4a2d);
            color: #c8e6c9;
        }
        
        .warning-box {
            background: linear-gradient(135deg, #3d3a1e, #4a442d);
            color: #fff3cd;
        }
        
        .info-box {
            background: linear-gradient(135deg, #1e2a3d, #2d3a4a);
            color: #bbdefb;
        }
        
        .error-box {
            background: linear-gradient(135deg, #3d1e1e, #4a2d2d);
            color: #f8d7da;
        }
    }
    
    /* Enhanced typography for better readability */
    .info-box h4, .success-box h4, .warning-box h4, .error-box h4 {
        margin-top: 0;
        margin-bottom: 1rem;
        font-weight: 600;
        font-size: 1.2rem;
    }
    
    .info-box ul, .success-box ul, .warning-box ul, .error-box ul {
        margin-bottom: 0;
        padding-left: 1.5rem;
    }
    
    .info-box li, .success-box li, .warning-box li, .error-box li {
        margin-bottom: 0.5rem;
        line-height: 1.5;
    }
    
    /* Button styling enhancements */
    .stButton > button {
        background: linear-gradient(135deg, var(--primary-blue), var(--primary-blue-light)) !important;
        color: white !important;
        border: none !important;
        border-radius: 8px !important;
        padding: 0.75rem 2rem !important;
        font-weight: 600 !important;
        box-shadow: 0 4px 6px var(--shadow) !important;
        transition: all 0.3s ease !important;
    }
    
    .stButton > button:hover {
        transform: translateY(-2px) !important;
        box-shadow: 0 6px 12px var(--shadow) !important;
    }
    
    /* Progress bar styling */
    .stProgress > div > div > div {
        background: linear-gradient(90deg, var(--primary-blue), var(--accent-orange)) !important;
    }
    
    /* File uploader styling */
    .stFileUploader > div {
        border: 2px dashed var(--primary-blue) !important;
        border-radius: 12px !important;
        padding: 2rem !important;
        background: var(--bg-secondary) !important;
        transition: all 0.3s ease !important;
    }
    
    .stFileUploader > div:hover {
        border-color: var(--accent-orange) !important;
        background: var(--bg-primary) !important;
    }
    
    /* Sidebar styling */
    .css-1d391kg {
        background: var(--bg-secondary) !important;
    }
    
    /* Radio button styling */
    .stRadio > div {
        background: var(--bg-secondary) !important;
        padding: 1rem !important;
        border-radius: 8px !important;
        border: 1px solid var(--border-light) !important;
    }
    
    /* Text input styling */
    .stTextInput > div > div > input {
        border: 2px solid var(--border-light) !important;
        border-radius: 8px !important;
        padding: 0.75rem !important;
        transition: border-color 0.3s ease !important;
    }
    
    .stTextInput > div > div > input:focus {
        border-color: var(--primary-blue) !important;
        box-shadow: 0 0 0 3px rgba(46, 134, 171, 0.1) !important;
    }
    
    /* Download button styling */
    .stDownloadButton > button {
        background: linear-gradient(135deg, var(--success-green), #20c997) !important;
        color: white !important;
        border: none !important;
        border-radius: 6px !important;
        padding: 0.5rem 1rem !important;
        font-weight: 500 !important;
        margin: 0.25rem !important;
        transition: all 0.3s ease !important;
    }
    
    .stDownloadButton > button:hover {
        transform: translateY(-1px) !important;
        box-shadow: 0 4px 8px var(--shadow) !important;
    }
    
    /* Expander styling */
    .streamlit-expanderHeader {
        background: var(--bg-secondary) !important;
        border-radius: 8px !important;
        border: 1px solid var(--border-light) !important;
    }
    
    /* Checkbox styling */
    .stCheckbox > label {
        background: var(--bg-secondary) !important;
        padding: 0.75rem !important;
        border-radius: 6px !important;
        border: 1px solid var(--border-light) !important;
        transition: all 0.3s ease !important;
    }
    
    .stCheckbox > label:hover {
        background: var(--bg-primary) !important;
        border-color: var(--primary-blue) !important;
    }
    
    /* Responsive design improvements */
    @media (max-width: 768px) {
        .main-header {
            font-size: 2.2rem;
        }
        
        .step-header {
            font-size: 1.4rem;
        }
        
        .info-box, .success-box, .warning-box, .error-box {
            padding: 1rem;
            margin: 1rem 0;
        }
    }
</style>
""", unsafe_allow_html=True)

def load_migration_functions():
    """Dynamically import migration functions to avoid startup issues"""
    try:
        # Add current directory to Python path
        current_dir = os.path.dirname(os.path.abspath(__file__))
        if current_dir not in sys.path:
            sys.path.insert(0, current_dir)
        
        from hex_migrate_redshift_to_databricks import process_file, load_yaml, save_yaml
        return process_file, load_yaml, save_yaml
    except Exception as e:
        st.error(f"❌ Could not load migration functions: {str(e)}")
        st.stop()

def main():
    # Header
    st.markdown('<div class="main-header">🚀 Hex → Databricks Migration Tool</div>', unsafe_allow_html=True)
    
    # Check if migration script exists
    migration_script = "hex_migrate_redshift_to_databricks.py"
    if not os.path.exists(migration_script):
        st.error(f"❌ Migration script '{migration_script}' not found in current directory!")
        st.stop()
    
    # Sidebar configuration
    st.sidebar.header("⚙️ Configuration")
    
    # Databricks connection ID input
    databricks_conn_id = st.sidebar.text_input(
        "Databricks Connection ID",
        value="0196d84e-3399-7000-ba4e-6c93736d59a8",
        help="Your Databricks data connection ID from Hex"
    )
    
    # Optional Redshift connection IDs
    st.sidebar.subheader("🔧 Advanced Options")
    use_custom_redshift = st.sidebar.checkbox("Use custom Redshift connection IDs")
    
    redshift_conn_ids = None
    if use_custom_redshift:
        redshift_id_1 = st.sidebar.text_input("Redshift Connection ID 1", value="e2694948-2c20-47d3-b127-71448e2bf238")
        redshift_id_2 = st.sidebar.text_input("Redshift Connection ID 2", value="0d0da619-5aa7-4f55-b020-ba94bfa77917")
        redshift_id_3 = st.sidebar.text_input("Redshift Connection ID 3", value="63ebcea0-017f-4bcf-b58a-a2340a75845f")
        redshift_conn_ids = [redshift_id_1, redshift_id_2, redshift_id_3]
    
    # Main content area
    col1, col2 = st.columns([3, 2])
    
    with col1:
        st.markdown('<div class="step-header">📁 Step 1: Upload Your Hex YAML Files</div>', unsafe_allow_html=True)
        
        # File upload options
        upload_option = st.radio(
            "Choose upload method:",
            ["Single YAML file", "Multiple YAML files", "ZIP archive"],
            horizontal=True
        )
        
        uploaded_files = []
        
        if upload_option == "Single YAML file":
            uploaded_file = st.file_uploader(
                "Upload a single Hex YAML file",
                type=['yaml', 'yml'],
                accept_multiple_files=False
            )
            if uploaded_file:
                uploaded_files = [uploaded_file]
                
        elif upload_option == "Multiple YAML files":
            uploaded_files = st.file_uploader(
                "Upload multiple Hex YAML files",
                type=['yaml', 'yml'],
                accept_multiple_files=True
            )
            
        elif upload_option == "ZIP archive":
            uploaded_zip = st.file_uploader(
                "Upload a ZIP file containing YAML files",
                type=['zip'],
                accept_multiple_files=False
            )
            if uploaded_zip:
                # Extract YAML files from ZIP
                with zipfile.ZipFile(uploaded_zip, 'r') as zip_ref:
                    yaml_files = [f for f in zip_ref.namelist() if f.endswith(('.yaml', '.yml'))]
                    if yaml_files:
                        st.success(f"Found {len(yaml_files)} YAML files in ZIP archive")
                        uploaded_files = []
                        for yaml_file in yaml_files:
                            file_content = zip_ref.read(yaml_file)
                            # Create a file-like object
                            file_obj = io.BytesIO(file_content)
                            file_obj.name = os.path.basename(yaml_file)
                            uploaded_files.append(file_obj)
                    else:
                        st.error("No YAML files found in ZIP archive")
        
        # Process files if uploaded
        if uploaded_files and databricks_conn_id:
            st.markdown('<div class="step-header">🔄 Step 2: Process Migration</div>', unsafe_allow_html=True)
            
            # Show file preview
            st.markdown(f"""
            <div class="info-box">
            <h4>📋 Ready to Process</h4>
            <p><strong>{len(uploaded_files)} file(s)</strong> uploaded and ready for migration:</p>
            <ul>
            {"".join(f"<li>📄 {file.name}</li>" for file in uploaded_files)}
            </ul>
            </div>
            """, unsafe_allow_html=True)
            
            if st.button("🚀 Start Migration", type="primary", use_container_width=True):
                process_migration(uploaded_files, databricks_conn_id, redshift_conn_ids)
    
    with col2:
        # Information panel
        st.markdown('<div class="step-header">ℹ️ Migration Features</div>', unsafe_allow_html=True)
        
        st.markdown("""
        <div class="info-box">
        <h4>🔧 Automatic Fixes Applied:</h4>
        <ul>
            <li><strong>SQL Functions:</strong> NVL → COALESCE, TO_CHAR → date_format</li>
            <li><strong>Data Types:</strong> SUPER → STRING, VARCHAR(MAX) → STRING</li>
            <li><strong>Date Functions:</strong> DATEADD → date_sub/date_add</li>
            <li><strong>Mathematical:</strong> MOD → % operator</li>
            <li><strong>JSON Functions:</strong> Redshift → Databricks syntax</li>
            <li><strong>Performance:</strong> Window function optimizations</li>
        </ul>
        </div>
        """, unsafe_allow_html=True)
        
        st.markdown("""
        <div class="warning-box">
        <h4>⚠️ Expected Warnings (Not Errors!)</h4>
        <p>These warnings are <strong>normal</strong> and indicate areas that need manual review:</p>
        <ul>
            <li><strong>Multiple scalar subqueries:</strong> May need performance optimization in Databricks</li>
            <li><strong>Legacy table references:</strong> Verify table names exist in your Databricks catalog</li>
            <li><strong>Adoption tables:</strong> Check if these specific tables are available</li>
            <li><strong>Correlated subqueries:</strong> May need to be rewritten as JOINs</li>
        </ul>
        <p><em>These don't prevent migration - they're guidance for manual cleanup!</em></p>
        </div>
        """, unsafe_allow_html=True)
        
        # Statistics
        if os.path.exists("hex_yamls/schema-dialects"):
            try:
                schema_csv = "hex_yamls/schema-dialects/Redshift to Databricks Migration Mapping - Schema Mapping.csv"
                function_csv = "hex_yamls/schema-dialects/Redshift to Databricks Migration Mapping - Reddshift to Databricks Function Mapping.csv"
                
                schema_count = 0
                function_count = 0
                
                if os.path.exists(schema_csv):
                    with open(schema_csv, 'r') as f:
                        schema_count = sum(1 for line in f) - 1  # Subtract header
                        
                if os.path.exists(function_csv):
                    with open(function_csv, 'r') as f:
                        function_count = sum(1 for line in f) - 1  # Subtract header
                
                st.markdown(f"""
                <div class="success-box">
                <h4>📊 Mapping Database:</h4>
                <ul>
                    <li><strong>Table Mappings:</strong> {schema_count:,}</li>
                    <li><strong>Function Mappings:</strong> {function_count}</li>
                    <li><strong>Connection IDs:</strong> 3 Redshift → 1 Databricks</li>
                </ul>
                </div>
                """, unsafe_allow_html=True)
            except:
                pass

def process_migration(uploaded_files, databricks_conn_id, redshift_conn_ids=None):
    """Process the migration for uploaded files"""
    
    # Load migration functions
    process_file, load_yaml, save_yaml = load_migration_functions()
    
    # Create temporary directory for processing
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_input_dir = os.path.join(temp_dir, "input")
        temp_output_dir = os.path.join(temp_dir, "output")
        os.makedirs(temp_input_dir)
        os.makedirs(temp_output_dir)
        
        # Save uploaded files to temp directory
        file_names = []
        for uploaded_file in uploaded_files:
            file_path = os.path.join(temp_input_dir, uploaded_file.name)
            st.info(f"💾 Saving {uploaded_file.name} to {file_path}")
            with open(file_path, 'wb') as f:
                if hasattr(uploaded_file, 'read'):
                    content = uploaded_file.read()
                    # Reset file pointer if it's a file object
                    if hasattr(uploaded_file, 'seek'):
                        uploaded_file.seek(0)
                    f.write(content)
                    st.info(f"📝 Wrote {len(content)} bytes")
                else:
                    content = uploaded_file.getvalue()
                    f.write(content)
                    st.info(f"📝 Wrote {len(content)} bytes")
            
            # Verify the file was saved correctly
            if os.path.exists(file_path):
                saved_size = os.path.getsize(file_path)
                st.success(f"✅ {uploaded_file.name} saved successfully ({saved_size} bytes)")
            else:
                st.error(f"❌ Failed to save {uploaded_file.name}")
                
            file_names.append(uploaded_file.name)
        
        # Progress tracking
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        try:
            # Process migration
            status_text.text("🔄 Starting migration process...")
            progress_bar.progress(0.1)
            
            # Debug information
            st.info(f"Processing {len(file_names)} file(s) with Databricks connection: {databricks_conn_id}")
            if redshift_conn_ids:
                st.info(f"Using custom Redshift connection IDs: {redshift_conn_ids}")
            else:
                st.info("Using default Redshift connection IDs")
            
            progress_bar.progress(0.3)
            status_text.text("🔧 Applying SQL transformations...")
            
            # Process each file directly using our migration functions
            output_files = []
            migration_log = []
            
            for i, file_name in enumerate(file_names):
                input_file = os.path.join(temp_input_dir, file_name)
                output_file = os.path.join(temp_output_dir, file_name)
                
                try:
                    # Use the process_file function directly
                    st.info(f"🔄 Processing file: {file_name}")
                    process_file(input_file, output_file, databricks_conn_id, redshift_conn_ids)
                    
                    # Check if output file was created
                    if not os.path.exists(output_file):
                        raise Exception(f"Output file was not created: {output_file}")
                    
                    # Check file size
                    file_size = os.path.getsize(output_file)
                    st.info(f"📄 Output file created: {file_size} bytes")
                    
                    # Read the processed file
                    with open(output_file, 'r', encoding='utf-8') as f:
                        content = f.read()
                        if not content.strip():
                            raise Exception("Output file is empty")
                        output_files.append((file_name, content))
                        st.success(f"✅ Successfully read {len(content)} characters from {file_name}")
                        
                    # Count transformations
                    warning_count = content.count('-- TODO(manual):')
                    auto_fix_count = content.count('Auto-fixed:') + content.count('Converted from')
                    fix_count = content.count('COALESCE') + content.count('date_format')
                    migration_log.append(f"✅ {file_name}: {auto_fix_count + fix_count} transformations, {warning_count} manual reviews needed")
                    
                except Exception as e:
                    error_msg = f"❌ {file_name}: Failed - {str(e)}"
                    st.error(error_msg)
                    migration_log.append(error_msg)
                    
                    # Log more details for debugging
                    st.expander(f"🔍 Error Details for {file_name}", expanded=False).code(f"""
File: {file_name}
Error Type: {type(e).__name__}
Error Message: {str(e)}
Input File Path: {input_file}
Output File Path: {output_file}
                    """, language="text")
                
                # Update progress (convert to 0.0-1.0 range)
                progress_value = 0.3 + (0.5 * (i + 1) / len(file_names))
                progress_bar.progress(progress_value)
            
            progress_bar.progress(0.9)
            status_text.text("📦 Preparing download...")
            
            progress_bar.progress(1.0)
            status_text.text("✅ Migration completed!")
            
            # Display results
            if output_files:
                st.markdown("""
                <div class="success-box">
                <h4>🎉 Migration Completed Successfully!</h4>
                <p>Your files have been processed and are ready for download.</p>
                </div>
                """, unsafe_allow_html=True)
                
                # Debug: Show what files we have
                st.info(f"📊 Ready for download: {len(output_files)} files")
                for fname, fcontent in output_files:
                    st.info(f"📄 {fname}: {len(fcontent)} characters")
                
                # Show migration summary
                with st.expander("📋 Migration Summary", expanded=True):
                    st.markdown("""
                    <div class="info-box">
                    <h4>ℹ️ Understanding the Results</h4>
                    <p><strong>✅ Success messages:</strong> Files processed successfully</p>
                    <p><strong>⚠️ Warnings:</strong> Areas that need manual review (not failures!)</p>
                    <p><strong>❌ Errors:</strong> Actual processing failures that prevent conversion</p>
                    </div>
                    """, unsafe_allow_html=True)
                    
                    for log_entry in migration_log:
                        if "✅" in log_entry:
                            st.success(log_entry)
                        elif "❌" in log_entry:
                            st.error(log_entry)
                        else:
                            st.info(log_entry)
                
                # Download options
                st.markdown('<div class="step-header">📥 Step 3: Download Results</div>', unsafe_allow_html=True)
                
                col1, col2 = st.columns(2)
                
                with col1:
                    # Individual file downloads
                    st.subheader("Individual Files")
                    for file_name, content in output_files:
                        st.download_button(
                            label=f"📄 {file_name}",
                            data=content,
                            file_name=f"databricks_{file_name}",
                            mime="text/yaml"
                        )
                
                with col2:
                    # ZIP download
                    st.subheader("Bulk Download")
                    zip_buffer = io.BytesIO()
                    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
                        for file_name, content in output_files:
                            zip_file.writestr(f"databricks_{file_name}", content)
                    
                    st.download_button(
                        label="📦 Download All Files (ZIP)",
                        data=zip_buffer.getvalue(),
                        file_name="hex_databricks_migration.zip",
                        mime="application/zip"
                    )
            else:
                st.markdown("""
                <div class="warning-box">
                <h4>⚠️ No Files Processed</h4>
                <p>No files were successfully processed. Please check the error messages above and try again.</p>
                </div>
                """, unsafe_allow_html=True)
            
        except Exception as e:
            st.markdown(f"""
            <div class="error-box">
            <h4>❌ Migration Failed</h4>
            <p><strong>Error:</strong> {str(e)}</p>
            </div>
            """, unsafe_allow_html=True)
            
            # Enhanced error details with better error handling
            with st.expander("🔍 Show Detailed Error Information", expanded=False):
                st.code(f"""
Error Type: {type(e).__name__}
Error Message: {str(e)}

Troubleshooting Tips:
1. Ensure your YAML files are valid Hex exports
2. Check that the Databricks connection ID is correct
3. Verify that the migration script files are present
4. Try with a smaller test file first

If the error persists, please check the terminal output for more details.
                """, language="text")
                
                # Safe exception display
                try:
                    import traceback
                    st.text("Full Stack Trace:")
                    st.code(traceback.format_exc(), language="python")
                except Exception as trace_error:
                    st.error(f"Could not display stack trace: {str(trace_error)}")
                    st.text(f"Original error: {str(e)}")

if __name__ == "__main__":
    main()
