from flask import Flask, render_template, request, send_file, jsonify
import os
import yaml
import zipfile
import io
import tempfile
import sys

# Import your migration functions
from hex_migrate_redshift_to_databricks import transform_hex_yaml, load_yaml

app = Flask(__name__)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload_file():
    try:
        if 'file' not in request.files:
            return jsonify({'error': 'No file uploaded'}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400
        
        # Get databricks connection ID from form
        databricks_conn_id = request.form.get('databricks_conn_id', '0196d84e-3399-7000-ba4e-6c93736d59a8')
        
        # Process single YAML file
        if file.filename.endswith('.yaml') or file.filename.endswith('.yml'):
            content = file.read().decode('utf-8')
            doc = yaml.safe_load(content)
            
            # Transform the document
            new_doc, cells_rewritten = transform_hex_yaml(doc, databricks_conn_id)
            
            # Convert back to YAML
            output_yaml = yaml.dump(new_doc, default_flow_style=False, sort_keys=False)
            
            # Create response
            output = io.BytesIO()
            output.write(output_yaml.encode('utf-8'))
            output.seek(0)
            
            filename = file.filename.replace('.yaml', '_databricks.yaml').replace('.yml', '_databricks.yml')
            
            return send_file(
                output,
                mimetype='application/x-yaml',
                as_attachment=True,
                download_name=filename
            )
        
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
                total_files = 0
                total_cells = 0
                
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
                                
                                total_files += 1
                                total_cells += cells_rewritten
                                
                            except Exception as e:
                                print(f"Error processing {rel_path}: {e}")
                
                # Create output ZIP
                output_zip = io.BytesIO()
                with zipfile.ZipFile(output_zip, 'w', zipfile.ZIP_DEFLATED) as zip_file:
                    for root, dirs, files in os.walk(output_dir):
                        for filename in files:
                            file_path = os.path.join(root, filename)
                            arc_name = os.path.relpath(file_path, output_dir)
                            zip_file.write(file_path, arc_name)
                
                output_zip.seek(0)
                
                return send_file(
                    output_zip,
                    mimetype='application/zip',
                    as_attachment=True,
                    download_name=f'{file.filename.replace(".zip", "")}_databricks.zip'
                )
        
        else:
            return jsonify({'error': 'Unsupported file type. Please upload .yaml, .yml, or .zip files'}), 400
    
    except Exception as e:
        return jsonify({'error': f'Processing error: {str(e)}'}), 500

if __name__ == '__main__':
    app.run(debug=True, port=int(os.environ.get('PORT', 5000)))
