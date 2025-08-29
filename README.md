# Hex to Databricks Migration Tool

This tool automatically migrates Hex project YAML exports from Redshift to Databricks.

## Your Configuration
- **Databricks Connection ID**: `0196d84e-3399-7000-ba4e-6c93736d59a8`

## Quick Start

### 1. Export Your Hex Projects
1. Go to your Hex workspace
2. Open each project you want to migrate
3. Click the project menu (three dots) → Export → Download as YAML
4. Save all YAML files to the `hex_yamls/` directory

### 2. Run the Migration
```bash
# Easy mode - guided script
./run_migration.sh

# Or manually:
# Single file
python3 hex_migrate_redshift_to_databricks.py \
  --in hex_yamls/my_project.yaml \
  --out hex_yamls/my_project_databricks.yaml \
  --databricks-conn-id 0196d84e-3399-7000-ba4e-6c93736d59a8

# Batch process all files
python3 hex_migrate_redshift_to_databricks.py \
  --in-dir hex_yamls \
  --databricks-conn-id 0196d84e-3399-7000-ba4e-6c93736d59a8
```

### 3. Import Back to Hex
1. Go to Hex workspace
2. Create new project or version
3. Import the `*_databricks.yaml` files

## What Gets Migrated

### Database References
- `prod.raw_salesforce.*` → `source.salesforce.*`
- `prod.prod_mart_sales.*` → `mart.sales.*`
- `prod.prod_staging_*` → `staging.*`
- And 180+ other schema mappings

### SQL Functions
- `NVL()` → `COALESCE()`
- `TO_CHAR()` → `date_format()`
- `DATEADD()` → `date_add()` / `date_sub()`
- `JSON_EXTRACT_PATH_TEXT()` → `get_json_object()`
- And many more...

### Connection Settings
- Updates `dataConnectionId` to your Databricks connection
- Updates `defaultDataConnectionId` 

## Files in This Directory

- `hex_migrate_redshift_to_databricks.py` - Main migration script
- `run_migration.sh` - Easy-to-use wrapper script
- `test_migration.py` - Test script to verify everything works
- `hex_yamls/` - Put your exported Hex YAML files here
- `README.md` - This file

## Testing

Run the test to verify everything is working:
```bash
python3 test_migration.py
```

## Troubleshooting

### No YAML files found
- Make sure you've exported your Hex projects as YAML
- Put the `.yaml` or `.yml` files in the `hex_yamls/` directory

### SQL not transforming correctly
- Check that your queries use `prod.schema.table` format
- Some complex SQL may require manual review (marked with TODO comments)

### Connection errors in Hex
- Verify your Databricks connection is active in Hex
- Double-check the connection ID: `0196d84e-3399-7000-ba4e-6c93736d59a8`

## Advanced Usage

### Target Specific Redshift Connections
If you know your Redshift connection IDs:
```bash
python3 hex_migrate_redshift_to_databricks.py \
  --in project.yaml \
  --databricks-conn-id 0196d84e-3399-7000-ba4e-6c93736d59a8 \
  --redshift-conn-ids old-redshift-id-1 old-redshift-id-2
```

### Manual Review Required
The script adds TODO comments for SQL that needs manual review:
- `QUALIFY` clauses (need to be rewritten as window subqueries)
- `JSON_PARSE()` functions (need schema specification)

## Support

If you encounter issues:
1. Check the console output for error messages
2. Review any TODO comments in the generated SQL
3. Test the migrated queries in a Databricks notebook first
4. Contact your data team for complex SQL transformations
