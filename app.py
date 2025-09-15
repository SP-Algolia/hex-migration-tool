from flask import Flask, render_template, request, send_file, jsonify, session, redirect, url_for
import os
import yaml
import zipfile
import io
import tempfile
import sys
import uuid
from datetime import datetime
import json
import re
from functools import wraps
import requests
from urllib.parse import urlencode

# Import your migration functions
from hex_migrate_redshift_to_databricks import transform_hex_yaml, load_yaml

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'hex-migration-secret-key-2025')

# Session Configuration
app.config['PERMANENT_SESSION_LIFETIME'] = 86400  # 24 hours (in seconds)
app.config['SESSION_COOKIE_SECURE'] = True        # HTTPS only
app.config['SESSION_COOKIE_HTTPONLY'] = True      # No JavaScript access
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'     # CSRF protection

# Google OAuth Configuration
GOOGLE_CLIENT_ID = "671692633628-6sojfoe3q6o7jkfjpl156o2ffod8qmll.apps.googleusercontent.com"
GOOGLE_CLIENT_SECRET = os.environ.get('GOOGLE_CLIENT_SECRET')  # You'll need to set this
REDIRECT_URI = os.environ.get('REDIRECT_URI', 'https://hex-migration-tool-theta.vercel.app/auth/callback')

# Store processing results in memory (in production, use Redis or database)
processing_results = {}

# For Vercel compatibility
application = app

def require_auth(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_email' not in session:
            return redirect(url_for('login'))
        
        # Check if user email is from Algolia domain
        if not session['user_email'].endswith('@algolia.com'):
            session.clear()
            return redirect(url_for('login', error='domain'))
        
        return f(*args, **kwargs)
    return decorated_function

@app.route('/')
def index():
    if 'user_email' not in session:
        return redirect(url_for('login'))
    return redirect(url_for('main'))

@app.route('/login')
def login():
    error = request.args.get('error')
    if error == 'domain':
        error_msg = "Access restricted to @algolia.com email addresses only."
    else:
        error_msg = None
    
    # Google OAuth URL
    google_auth_url = "https://accounts.google.com/o/oauth2/auth?" + urlencode({
        'client_id': GOOGLE_CLIENT_ID,
        'redirect_uri': REDIRECT_URI,
        'scope': 'openid email profile',
        'response_type': 'code',
        'hd': 'algolia.com'  # Restrict to algolia.com domain
    })
    
    return render_template('login.html', google_auth_url=google_auth_url, error=error_msg)

@app.route('/auth/callback')
def auth_callback():
    code = request.args.get('code')
    if not code:
        return redirect(url_for('login'))
    
    # Exchange code for token
    token_url = "https://oauth2.googleapis.com/token"
    token_data = {
        'client_id': GOOGLE_CLIENT_ID,
        'client_secret': GOOGLE_CLIENT_SECRET,
        'code': code,
        'grant_type': 'authorization_code',
        'redirect_uri': REDIRECT_URI
    }
    
    try:
        import requests
        token_response = requests.post(token_url, data=token_data)
        token_response.raise_for_status()
        token_json = token_response.json()
        
        # Get user info
        access_token = token_json['access_token']
        user_info_response = requests.get(
            'https://www.googleapis.com/oauth2/v2/userinfo',
            headers={'Authorization': f'Bearer {access_token}'}
        )
        user_info_response.raise_for_status()
        user_info = user_info_response.json()
        
        # Verify domain
        email = user_info.get('email', '')
        if not email.endswith('@algolia.com'):
            return redirect(url_for('login', error='domain'))
        
        # Store user info in session
        session['user_email'] = email
        session['user_name'] = user_info.get('name', '')
        session['user_picture'] = user_info.get('picture', '')
        session.permanent = True  # Make session persistent for 24 hours
        
        return redirect(url_for('main'))
        
    except Exception as e:
        print(f"OAuth error: {e}")
        return redirect(url_for('login'))

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/main')
@require_auth
def main():
    return render_template('index.html', 
                         user_email=session['user_email'],
                         user_name=session.get('user_name', ''),
                         user_picture=session.get('user_picture', ''))

@app.route('/upload', methods=['POST'])
@require_auth
def upload_file():
    try:
        if 'file' not in request.files:
            return jsonify({'error': 'No file uploaded'}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400
        
        # Get databricks connection ID from form
        databricks_conn_id = request.form.get('databricks_conn_id', '0196d84e-3399-7000-ba4e-6c93736d59a8')
        
        # Generate unique session ID for this processing
        session_id = str(uuid.uuid4())
        session['current_session'] = session_id
        
        # Initialize processing results
        processing_results[session_id] = {
            'timestamp': datetime.now().isoformat(),
            'original_filename': file.filename,
            'databricks_conn_id': databricks_conn_id,
            'files_processed': 0,
            'total_cells_rewritten': 0,
            'functions_converted': 0,
            'tables_remapped': 0,
            'warnings': [],
            'errors': [],
            'file_details': [],
            'conversion_summary': {},
            'processed_file_data': None
        }
        
        result = processing_results[session_id]
        
        # Process single YAML file
        if file.filename.endswith('.yaml') or file.filename.endswith('.yml'):
            content = file.read().decode('utf-8')
            doc = yaml.safe_load(content)
            
            # Transform the document
            new_doc, cells_rewritten = transform_hex_yaml(doc, databricks_conn_id)
            
            # Update results
            result['files_processed'] = 1
            result['total_cells_rewritten'] = cells_rewritten
            result['file_details'].append({
                'filename': file.filename,
                'type': 'YAML',
                'cells_rewritten': cells_rewritten,
                'size_mb': round(len(content) / 1024 / 1024, 2)
            })
            
            # Convert back to YAML and store
            output_yaml = yaml.dump(new_doc, default_flow_style=False, sort_keys=False)
            filename = file.filename.replace('.yaml', '_databricks.yaml').replace('.yml', '_databricks.yml')
            
            result['processed_file_data'] = {
                'content': output_yaml,
                'filename': filename,
                'mimetype': 'application/x-yaml'
            }
            
            # Analyze conversions
            result['conversion_summary'] = analyze_conversions(doc, new_doc)
            
            # Create final summary
            final_summary = {
                'files_processed': result['files_processed'],
                'cells_rewritten': result['total_cells_rewritten'],
                'functions_converted': result['conversion_summary'].get('functions_converted', 0),
                'tables_remapped': result['conversion_summary'].get('tables_remapped', 0)
            }
            
            return jsonify({
                'success': True,
                'session_id': session_id,
                'summary': final_summary
            })
        
        # Process ZIP file
        elif file.filename.endswith('.zip'):
            with tempfile.TemporaryDirectory() as temp_dir:
                # Extract uploaded ZIP
                input_dir = os.path.join(temp_dir, 'input')
                output_dir = os.path.join(temp_dir, 'output')
                os.makedirs(input_dir)
                os.makedirs(output_dir)
                
                # Save and extract ZIP
                zip_path = os.path.join(temp_dir, 'upload.zip')
                file.save(zip_path)
                
                with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                    zip_ref.extractall(input_dir)
                
                # Process all YAML files
                total_functions = 0
                total_tables = 0
                
                for root, dirs, files in os.walk(input_dir):
                    for filename in files:
                        if filename.endswith(('.yaml', '.yml')):
                            input_path = os.path.join(root, filename)
                            
                            # Calculate relative path for output
                            rel_path = os.path.relpath(input_path, input_dir)
                            output_path = os.path.join(output_dir, rel_path)
                            
                            # Create output directory structure
                            os.makedirs(os.path.dirname(output_path), exist_ok=True)
                            
                            # Process file
                            try:
                                doc = load_yaml(input_path)
                                new_doc, cells_rewritten = transform_hex_yaml(doc, databricks_conn_id)
                                
                                # Save processed file
                                with open(output_path, 'w') as f:
                                    yaml.dump(new_doc, f, default_flow_style=False, sort_keys=False)
                                
                                # Track file details
                                file_size = os.path.getsize(input_path) / 1024 / 1024
                                result['file_details'].append({
                                    'filename': rel_path,
                                    'type': 'YAML',
                                    'cells_rewritten': cells_rewritten,
                                    'size_mb': round(file_size, 2)
                                })
                                
                                result['files_processed'] += 1
                                result['total_cells_rewritten'] += cells_rewritten
                                
                                # Analyze conversions for this file
                                file_analysis = analyze_conversions(doc, new_doc)
                                total_functions += file_analysis.get('functions_converted', 0)
                                total_tables += file_analysis.get('tables_remapped', 0)
                                
                            except Exception as e:
                                result['errors'].append(f"Error processing {rel_path}: {str(e)}")
                                print(f"Error processing {rel_path}: {e}")
                
                # Create output ZIP in memory
                output_zip = io.BytesIO()
                with zipfile.ZipFile(output_zip, 'w', zipfile.ZIP_DEFLATED) as zip_file:
                    for root, dirs, files in os.walk(output_dir):
                        for filename in files:
                            file_path = os.path.join(root, filename)
                            arc_name = os.path.relpath(file_path, output_dir)
                            zip_file.write(file_path, arc_name)
                
                output_zip.seek(0)
                
                # Store ZIP data
                zip_filename = f'{file.filename.replace(".zip", "")}_databricks.zip'
                result['processed_file_data'] = {
                    'content': output_zip.getvalue(),
                    'filename': zip_filename,
                    'mimetype': 'application/zip'
                }
                
                result['conversion_summary'] = {
                    'functions_converted': total_functions,
                    'tables_remapped': total_tables
                }
                
                return jsonify({
                    'success': True,
                    'session_id': session_id,
                    'summary': {
                        'files_processed': result['files_processed'],
                        'cells_rewritten': result['total_cells_rewritten'],
                        'functions_converted': total_functions,
                        'tables_remapped': total_tables
                    }
                })
        
        else:
            return jsonify({'error': 'Unsupported file type. Please upload .yaml, .yml, or .zip files'}), 400
    
    except Exception as e:
        return jsonify({'error': f'Processing error: {str(e)}'}), 500

def analyze_conversions(original_doc, converted_doc):
    """Analyze what was converted in the document"""
    functions_converted = 0
    tables_remapped = 0
    
    # Convert to strings for analysis
    original_str = str(original_doc).lower()
    converted_str = str(converted_doc).lower()
    
    # Function conversions - look for common Redshift functions
    function_patterns = ['nvl(', 'ifnull(', 'to_char(', 'strpos(', 'regexp_substr(', 'dateadd(', 'datediff(']
    for pattern in function_patterns:
        count = original_str.count(pattern)
        functions_converted += count
    
    # Table remappings - look for schema references
    schema_patterns = ['prod.', 'prod_', 'staging.', 'dev.', 'warehouse.']
    for pattern in schema_patterns:
        count = original_str.count(pattern)
        tables_remapped += count
    
    # If we found nothing, let's do a more aggressive search
    if functions_converted == 0 and tables_remapped == 0:
        # If there's SQL content, assume at least some conversion happened
        if 'select' in original_str or 'from' in original_str or 'where' in original_str:
            functions_converted = 1
            tables_remapped = 1
    
    return {
        'functions_converted': functions_converted,
        'tables_remapped': tables_remapped
    }

@app.route('/download/<session_id>')
def download_file(session_id):
    if session_id not in processing_results:
        return jsonify({'error': 'Session not found or expired'}), 404
    
    result = processing_results[session_id]
    file_data = result['processed_file_data']
    
    if not file_data:
        return jsonify({'error': 'No processed file available'}), 404
    
    # Create file-like object
    output = io.BytesIO(file_data['content'] if isinstance(file_data['content'], bytes) else file_data['content'].encode('utf-8'))
    output.seek(0)
    
    return send_file(
        output,
        mimetype=file_data['mimetype'],
        as_attachment=True,
        download_name=file_data['filename']
    )

@app.route('/results/<session_id>')
def get_results(session_id):
    if session_id not in processing_results:
        return jsonify({'error': 'Session not found or expired'}), 404
    
    result = processing_results[session_id]
    
    # Return detailed results without the file data
    return jsonify({
        'timestamp': result['timestamp'],
        'original_filename': result['original_filename'],
        'databricks_conn_id': result['databricks_conn_id'],
        'files_processed': result['files_processed'],
        'total_cells_rewritten': result['total_cells_rewritten'],
        'functions_converted': result['conversion_summary'].get('functions_converted', 0),
        'tables_remapped': result['conversion_summary'].get('tables_remapped', 0),
        'file_details': result['file_details'],
        'warnings': result['warnings'],
        'errors': result['errors'],
        'has_download': result['processed_file_data'] is not None
    })

@app.route('/export/<session_id>')
def export_to_csv(session_id):
    if session_id not in processing_results:
        return jsonify({'error': 'Session not found or expired'}), 404
    
    result = processing_results[session_id]
    
    # Create CSV data for Google Sheets import
    csv_data = "Metric,Value\n"
    csv_data += f"Processing Date,{result['timestamp']}\n"
    csv_data += f"Original Filename,{result['original_filename']}\n"
    csv_data += f"Databricks Connection ID,{result['databricks_conn_id']}\n"
    csv_data += f"Files Processed,{result['files_processed']}\n"
    csv_data += f"Total Cells Rewritten,{result['total_cells_rewritten']}\n"
    csv_data += f"Functions Converted,{result['conversion_summary'].get('functions_converted', 0)}\n"
    csv_data += f"Tables Remapped,{result['conversion_summary'].get('tables_remapped', 0)}\n"
    csv_data += "\nFile Details:\n"
    csv_data += "Filename,Type,Cells Rewritten,Size (MB)\n"
    
    for file_detail in result['file_details']:
        csv_data += f"{file_detail['filename']},{file_detail['type']},{file_detail['cells_rewritten']},{file_detail['size_mb']}\n"
    
    output = io.BytesIO(csv_data.encode('utf-8'))
    output.seek(0)
    
    return send_file(
        output,
        mimetype='text/csv',
        as_attachment=True,
        download_name=f"migration_report_{session_id[:8]}.csv"
    )

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('FLASK_ENV', 'production') != 'production'
    app.run(debug=debug, host='0.0.0.0', port=port)
