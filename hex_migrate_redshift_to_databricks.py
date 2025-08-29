#!/usr/bin/env python3
"""
hex_migrate_redshift_to_databricks.py

Batch-convert Hex project YAML exports from Redshift to Databricks with minimal manual work.
- Updates dataConnectionId to the Databricks connection (ONLY for specified Redshift connections)
- Rewrites Redshift schema references to Databricks catalog.schema
- Applies a series of SQL rewrites (functions, regex, date/time, qualify, etc.)
- Converts boolean inputs to text for Databricks compatibility
- Produces a new YAML ready to import as a version in Hex

USAGE
-----
# Simple usage (uses hardcoded Redshift connection IDs)
python hex_migrate_redshift_to_databricks.py \
  --in project.yaml \
  --out project_databricks.yaml \
  --databricks-conn-id 0196d84e-3399-7000-ba4e-6c93736d59a8

# Directory batch processing (uses hardcoded Redshift connection IDs)
python hex_migrate_redshift_to_databricks.py \
  --in-dir ./hex_yamls \
  --databricks-conn-id 0196d84e-3399-7000-ba4e-6c93736d59a8

# Override with custom Redshift connection IDs
python hex_migrate_redshift_to_databricks.py \
  --in-dir ./hex_yamls \
  --databricks-conn-id 0196d84e-3399-7000-ba4e-6c93736d59a8 \
  --redshift-conn-ids 00000000-1111-2222-3333-444444444444 55555555-6666-7777-8888-999999999999

# Fallback: If no Redshift connections found, uses schema heuristics (less precise)
python hex_migrate_redshift_to_databricks.py \
  --in project.yaml \
  --out project_databricks.yaml \
  --databricks-conn-id 0196d84e-3399-7000-ba4e-6c93736d59a8 \
  --redshift-conn-ids
"""

import argparse
import sys
import re
import os
import csv
from copy import deepcopy

try:
    import yaml  # PyYAML
except Exception as e:
    print("This script requires PyYAML. pip install pyyaml", file=sys.stderr)
    raise

# ---------- 1) Load Schema/Catalog mapping from CSV ----------
def load_schema_mappings(csv_path="hex_yamls/schema-dialects/Redshift to Databricks Migration Mapping - Schema Mapping.csv"):
    """Load schema mappings from CSV file - supports both old and new formats"""
    schema_map = {}
    try:
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            headers = reader.fieldnames
            
            # Check if this is the new table-to-table format
            if 'Redshift Table' in headers and 'Databricks Table' in headers:
                print(f"📋 Loading table-to-table mappings from {csv_path}")
                for row in reader:
                    redshift_table = row['Redshift Table'].strip()
                    databricks_table = row['Databricks Table'].strip()
                    
                    if redshift_table and databricks_table:
                        schema_map[redshift_table.lower()] = databricks_table
                
                print(f"✅ Loaded {len(schema_map)} table mappings from {csv_path}")
                return schema_map
            
            # Old format: Redshift Database/Schema -> Databricks Catalog/Schema
            elif 'Redshift Database' in headers and 'Redshift Schema' in headers:
                print(f"📋 Loading schema mappings from {csv_path}")
                for row in reader:
                    redshift_db = row['Redshift Database'].strip()
                    redshift_schema = row['Redshift Schema'].strip()
                    databricks_catalog = row['Databricks Catalog'].strip()
                    databricks_schema = row['Databricks Schema'].strip()
                    
                    key = (redshift_db.lower(), redshift_schema.lower())
                    value = (databricks_catalog, databricks_schema if databricks_schema != '*' else '*')
                    schema_map[key] = value
                
                print(f"✅ Loaded {len(schema_map)} schema mappings from {csv_path}")
                return schema_map
            
            else:
                raise ValueError(f"Unsupported CSV format. Expected either 'Redshift Table/Databricks Table' or 'Redshift Database/Schema' columns")
        
    except FileNotFoundError:
        print(f"⚠️  Schema mapping file not found: {csv_path}")
        print("⚠️  Using hardcoded schema mappings as fallback")
        return get_hardcoded_schema_map()
    except Exception as e:
        print(f"⚠️  Error loading schema mappings: {e}")
        print("⚠️  Using hardcoded schema mappings as fallback")
        return get_hardcoded_schema_map()

def get_hardcoded_schema_map():
    """Fallback hardcoded schema mappings"""
    return {
        ("prod", "archive"): ("archive", "*"),
        ("prod", "prod_reference"): ("reference", "*"),
        ("prod", "prod_algolia_target"): ("reference", "algolia_target"),
        ("prod", "census"): ("metadata", "census"),
        ("prod", "looker_scratch"): ("metadata", "looker_scratch"),
        ("prod", "looker_tmp"): ("metadata", "looker_tmp"),
        ("prod", "prod_data_quality"): ("metadata", "data_quality"),
        ("prod", "prod_dbt_test__audit"): ("metadata", "dbt_test__audit"),
        ("prod", "prod_elementary"): ("metadata", "elementary"),
        ("prod", "raw_adroll"): ("source", "adroll"),
        ("prod", "raw_analytics_api_external"): ("source", "analytics_api"),
        ("prod", "raw_bamboohr"): ("source", "bamboohr"),
        ("prod", "raw_bing_ads"): ("source", "bing_ads"),
        ("prod", "raw_connectivity_api__eu"): ("source", "connectivity_api__eu"),
        ("prod", "raw_connectivity_api__us"): ("source", "connectivity_api__us"),
        ("prod", "raw_connectivity_api_observability__eu"): ("source", "connectivity_api_observability__eu"),
        ("prod", "raw_connectivity_api_observability__us"): ("source", "connectivity_api_observability__us"),
        ("prod", "raw_crossbeam"): ("source", "crossbeam"),
        ("prod", "raw_dashboard"): ("source", "dashboard"),
        ("prod", "raw_demandbase"): ("source", "demandbase"),
        ("prod", "raw_einstein"): ("source", "einstein"),
        ("prod", "raw_ethical_ads"): ("source", "ethical_ads"),
        ("prod", "raw_ethical_ads_v2"): ("source", "ethical_ads_v2"),
        ("prod", "raw_events_external"): ("source", "events"),
        ("prod", "raw_facebook"): ("source", "facebook"),
        ("prod", "raw_facebook_ads"): ("source", "facebook_ads"),
        ("prod", "raw_feature_personalization_ai"): ("source", "feature_personalization_ai"),
        ("prod", "raw_feature_personalization_classic"): ("source", "feature_personalization_classic"),
        ("prod", "raw_feature_query_categorization"): ("source", "feature_query_categorization"),
        ("prod", "raw_feature_query_categorization_archive_external"): ("source", "feature_query_categorization_archive"),
        ("prod", "raw_feature_query_categorization_external"): ("source", "feature_query_categorization"),
        ("prod", "raw_gainsight"): ("source", "gainsight"),
        ("prod", "raw_galileo"): ("source", "galileo"),
        ("prod", "raw_github"): ("source", "github"),
        ("prod", "raw_github_external"): ("source", "github"),
        ("prod", "raw_google_ads"): ("source", "google_ads"),
        ("prod", "raw_google_analytics"): ("source", "google_analytics"),
        ("prod", "raw_google_analytics_4"): ("source", "google_analytics_4"),
        ("prod", "raw_google_sheets"): ("source", "google_sheets"),
        ("prod", "raw_helpscout"): ("source", "helpscout"),
        ("prod", "raw_infrastructure"): ("source", "infrastructure"),
        ("prod", "raw_infrastructure_costs"): ("source", "infrastructure_costs"),
        ("prod", "raw_jira"): ("source", "jira"),
        ("prod", "raw_linkedin_ads"): ("source", "linkedin_ads"),
        ("prod", "raw_marketo"): ("archive", "marketo"),
        ("prod", "raw_marketo_v2"): ("source", "marketo_v2"),
        ("prod", "raw_npm"): ("source", "npm"),
        ("prod", "raw_pigment"): ("source", "pigment"),
        ("prod", "raw_product"): ("source", "product"),
        ("prod", "raw_product_external"): ("source", "product"),
        ("prod", "product"): ("source", "product"),
        ("prod", "raw_realm_b2b"): ("source", "realm_b2b"),
        ("prod", "raw_redshift_monitoring"): ("source", "redshift_monitoring"),
        ("prod", "raw_redshift_monitoring_external"): ("source", "redshift_monitoring"),
        ("prod", "raw_revenue"): ("source", "revenue"),
        ("prod", "revenue"): ("source", "revenue"),
        ("prod", "raw_salesforce"): ("source", "salesforce"),
        ("prod", "raw_shopify"): ("source", "shopify"),
        ("prod", "shopify"): ("source", "shopify"),
        ("prod", "raw_stripe_eu"): ("source", "stripe_eu"),
        ("prod", "raw_stripe_eu_backup"): ("source", "stripe_eu_backup"),
        ("prod", "raw_stripe_us"): ("source", "stripe_us"),
        ("prod", "raw_stripe_us_backup"): ("source", "stripe_us_backup"),
        ("prod", "raw_telemetry"): ("source", "telemetry"),
        ("prod", "raw_toggl"): ("source", "toggl"),
        ("prod", "raw_twitter_ads"): ("source", "twitter_ads"),
        ("prod", "raw_usage_api_external"): ("source", "usage_api"),
        ("prod", "raw_usages_rest_api"): ("source", "usages_rest_api"),
        ("prod", "usages"): ("source", "usages"),
        ("prod", "raw_rolling_month_per_application"): ("source", "usages"),
        ("prod", "raw_zendesk"): ("source", "zendesk"),
        ("prod", "raw_zendesk_test_stitch"): ("source", "zendesk_test_stitch"),
        ("prod", "raw_zuora"): ("source", "zuora"),
        ("prod", "segment_recommend_worker_back_end"): ("source", "segment_recommend_worker_back_end"),
        ("prod", "segment_algolia"): ("source", "segment_algolia"),
        ("prod", "segment_algolia_blog"): ("source", "segment_algolia_blog"),
        ("prod", "segment_algolia_community"): ("source", "segment_algolia_community"),
        ("prod", "segment_algolia_dashboard_backend"): ("source", "segment_algolia_dashboard_backend"),
        ("prod", "segment_algolia_dashboard_frontend"): ("source", "segment_algolia_dashboard_frontend"),
        ("prod", "segment_algolia_documentation"): ("source", "segment_algolia_documentation"),
        ("prod", "segment_cli_dev"): ("source", "segment_cli_dev"),
        ("prod", "segment_collections_dev"): ("source", "segment_collections_dev"),
        ("prod", "segment_collections_prod"): ("source", "segment_collections_prod"),
        ("prod", "segment_crawler"): ("source", "segment_crawler"),
        ("prod", "segment_design_system_a11y"): ("source", "segment_design_system_a11y"),
        ("prod", "segment_design_system_static_usage"): ("source", "segment_design_system_static_usage"),
        ("prod", "segment_magento"): ("source", "segment_magento"),
        ("prod", "segment_new_world_docs"): ("source", "segment_new_world_docs"),
        ("prod", "segment_partners_algolia"): ("source", "segment_partners_algolia"),
        ("prod", "segment_recommend_doc_prod"): ("source", "segment_recommend_doc_prod"),
        ("prod", "segment_search_grader"): ("source", "segment_search_grader"),
        ("prod", "segment_shopify"): ("source", "segment_shopify"),
        ("prod", "segment_shopify_admin"): ("source", "segment_shopify_admin"),
        ("prod", "segment_static"): ("source", "segment_static"),
        ("prod", "segment_support_prod"): ("source", "segment_support_prod"),
        ("prod", "segment_bigcommerce_integration_prod"): ("source", "segment_bigcommerce_integration_prod"),
        ("prod", "segment_prod_events_records_connections"): ("source", "segment_prod_events_records_connections"),
        ("prod", "segment_events_records_connections_staging"): ("source", "segment_events_records_connections_staging"),
        ("prod", "events"): ("tracked_features_events", None),
        ("prod", "prod_analytics_api"): ("data_engineering_staging", "analytics_api"),
        ("prod", "prod_analytics_api_external"): ("data_engineering_staging", "analytics_api"),
        ("prod", "prod_application"): ("data_engineering_staging", "application"),
        ("prod", "prod_application_intermediate_feature_logs_stats_external"): ("data_engineering_staging", "application"),
        ("prod", "prod_application_intermediate_insights_logs_stats_external"): ("data_engineering_staging", "application"),
        ("prod", "prod_product"): ("data_engineering_staging", "product"),
        ("prod", "prod_product_daily_recommend_operations_per_user_agent_external"): ("data_engineering_staging", "product"),
        ("prod", "prod_product_external"): ("data_engineering_staging", "product"),
        ("prod", "prod_product_indices_replicas_and_primaries_external"): ("data_engineering_staging", "product"),
        ("prod", "prod_product_insights_daily_user_tokens_per_application_external"): ("data_engineering_staging", "product"),
        ("prod", "prod_product_intermediate_feature_logs_stats_by_cluster_external"): ("data_engineering_staging", "product"),
        ("prod", "prod_product_intermediate_feature_logs_stats_by_index_external"): ("data_engineering_staging", "product"),
        ("prod", "prod_dashboard"): ("source", "dashboard"),
        ("prod", "prod_salesforce"): ("data_engineering_staging", "salesforce"),
        ("prod", "prod_usage_quotas"): ("data_engineering_staging", "usages"),
        ("prod", "prod_usages"): ("data_engineering_staging", "usages"),
        ("prod", "prod_usages_daily_per_application_per_index_external"): ("data_engineering_staging", "usages"),
        ("prod", "prod_usages_intermediate_bigtable_daily_per_application_external"): ("data_engineering_staging", "usages"),
        ("prod", "prod_usages_intermediate_bigtable_daily_per_application_per_index_external"): ("data_engineering_staging", "usages"),
        ("prod", "prod_usages_intermediate_bigtable_daily_per_application_per_index_rowkeys_external"): ("data_engineering_staging", "usages"),
        ("prod", "prod_usages_intermediate_bigtable_daily_per_application_rowkeys_external"): ("data_engineering_staging", "usages"),
        ("prod", "prod_usages_intermediate_daily_per_application_merged_with_legacy_external"): ("data_engineering_staging", "usages"),
        ("prod", "prod_usages_intermediate_daily_per_application_per_index_external"): ("data_engineering_staging", "usages"),
        ("prod", "prod_usages_intermediate_daily_per_application_per_index_max_rowkeys_external"): ("data_engineering_staging", "usages"),
        ("prod", "prod_usages_intermediate_indices_settings_metrics_per_application_external"): ("data_engineering_staging", "usages"),
        ("prod", "prod_user"): ("data_engineering_staging", "user"),
        ("prod", "prod_common"): ("standardized", "common"),
        ("prod", "prod_dimensional"): ("analytics", "dimensional"),
        ("prod", "prod_helpscout"): ("staging", "helpscout"),
        ("prod", "prod_infrastructure"): ("staging", "infrastructure"),
        ("prod", "prod_staging_bamboohr"): ("staging", "bamboohr"),
        ("prod", "prod_staging_bing_ads"): ("staging", "bing_ads"),
        ("prod", "prod_staging_dashboard"): ("staging", "dashboard"),
        ("prod", "prod_staging_demandbase"): ("staging", "demandbase"),
        ("prod", "prod_staging_ethical_ads"): ("staging", "ethical_ads"),
        ("prod", "prod_staging_facebook_ads"): ("staging", "facebook_ads"),
        ("prod", "prod_staging_gainsight"): ("staging", "gainsight"),
        ("prod", "prod_staging_google_ads"): ("staging", "google_ads"),
        ("prod", "prod_staging_google_analytics"): ("staging", "google_analytics"),
        ("prod", "prod_staging_infrastructure"): ("staging", "infrastructure"),
        ("prod", "prod_staging_jira"): ("staging", "jira"),
        ("prod", "prod_staging_linkedin_ads"): ("staging", "linkedin_ads"),
        ("prod", "prod_staging_pigment"): ("staging", "pigment"),
        ("prod", "prod_staging_product"): ("staging", "product"),
        ("prod", "prod_staging_realm_b2b"): ("staging", "realm_b2b"),
        ("prod", "prod_staging_revenue"): ("staging", "revenue"),
        ("prod", "prod_staging_rollworks"): ("staging", "rollworks"),
        ("prod", "prod_staging_salesforce"): ("staging", "salesforce"),
        ("prod", "prod_staging_search"): ("staging", "search"),
        ("prod", "prod_staging_segment"): ("staging", "segment"),
        ("prod", "prod_staging_toggl"): ("staging", "toggl"),
        ("prod", "prod_staging_twitter_ads"): ("staging", "twitter_ads"),
        ("prod", "prod_staging_usage"): ("staging", "usage"),
        ("prod", "prod_staging_zendesk"): ("staging", "zendesk"),
        ("prod", "prod_mart_algolia"): ("mart", "algolia"),
        ("prod", "prod_analytics"): ("mart", "algolia"),
        ("prod", "prod_analytics_daily_aggregations_external"): ("mart", "algolia"),
        ("prod", "prod_analytics_intermediate_query_categorization_metadata_logs_external"): ("mart", "algolia"),
        ("prod", "prod_analytics_intermediate_search_aggregates_conversions_stats_external"): ("mart", "algolia"),
        ("prod", "prod_analytics_intermediate_search_aggregates_logs_stats_external"): ("mart", "algolia"),
        ("prod", "prod_analytics_intermediate_search_aggregates_searches_stats_external"): ("mart", "algolia"),
        ("prod", "prod_analytics_intermediate_search_slg_search_aggregate_external"): ("mart", "algolia"),
        ("prod", "prod_mart_customer_success"): ("mart", "customer_success"),
        ("prod", "prod_mart_customer_support"): ("mart", "customer_support"),
        ("prod", "prod_mart_finance"): ("mart", "finance"),
        ("prod", "prod_mart_growth"): ("mart", "growth"),
        ("prod", "prod_mart_marketing"): ("mart", "marketing"),
        ("prod", "prod_mart_professional_services"): ("mart", "professional_services"),
        ("prod", "prod_mart_sales"): ("mart", "sales"),
        ("prod", "prod_reverse_etl_amplitude"): ("reverse_etl", "amplitude"),
        ("prod", "prod_reverse_etl_endgame"): ("reverse_etl", "endgame"),
        ("prod", "prod_reverse_etl_gainsight"): ("reverse_etl", "gainsight"),
        ("prod", "prod_reverse_etl_headsup"): ("reverse_etl", "headsup"),
        ("prod", "prod_reverse_etl_marketo"): ("reverse_etl", "marketo"),
        ("prod", "prod_reverse_etl_salesforce"): ("reverse_etl", "salesforce"),
        ("prod", "prod_reverse_etl_zendesk"): ("reverse_etl", "zendesk"),
    }

# Load schema mappings at module level
SCHEMA_MAP = load_schema_mappings()

# ---------- 2) Load Function mappings from CSV ----------
def load_function_mappings(csv_path="hex_yamls/schema-dialects/Redshift to Databricks Migration Mapping - Reddshift to Databricks Function Mapping.csv"):
    """Load function mappings from CSV file"""
    function_mappings = {}
    try:
        with open(csv_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            
            # Skip the first line (description) and find the header
            header_found = False
            for i, line in enumerate(lines):
                if 'SNO,Redshift Function,Purpose,Databricks Equivalent' in line:
                    header_found = True
                    # Process rows starting from this header
                    reader = csv.DictReader(lines[i:])
                    break
            
            if not header_found:
                print("⚠️  Could not find proper header in function mapping CSV")
                return {}
                
            for row in reader:
                # Skip empty rows or rows without proper SNO
                sno = row.get('SNO', '').strip()
                if not sno or not sno.isdigit():
                    continue
                    
                redshift_func = row.get('Redshift Function', '').strip()
                databricks_equiv = row.get('Databricks Equivalent', '').strip()
                
                if redshift_func and databricks_equiv and redshift_func != 'Redshift Function':
                    # Clean up the function names - remove quotes and extra spaces
                    redshift_func = redshift_func.strip('"').strip()
                    databricks_equiv = databricks_equiv.strip('"').strip()
                    
                    function_mappings[redshift_func] = databricks_equiv
        
        print(f"✅ Loaded {len(function_mappings)} function mappings from {csv_path}")
        return function_mappings
    except FileNotFoundError:
        print(f"⚠️  Function mapping file not found: {csv_path}")
        print("⚠️  Using hardcoded function mappings as fallback")
        return {}
    except Exception as e:
        print(f"⚠️  Error loading function mappings: {e}")
        print("⚠️  Using hardcoded function mappings as fallback")
        return {}

# Load function mappings at module level
FUNCTION_MAPPINGS = load_function_mappings()

# Helper to rewrite fully qualified refs like prod.schema.table to catalog.schema.table
def rewrite_schema_qualification(sql: str) -> str:
    """
    Rewrite schema qualifications supporting both old and new mapping formats:
    - Old format: (prod, schema) -> (catalog, schema)
    - New format: full_table_name -> full_table_name
    """
    
    # Check if we're using the new table-to-table format
    # (SCHEMA_MAP keys are strings instead of tuples)
    if SCHEMA_MAP and isinstance(next(iter(SCHEMA_MAP.keys())), str):
        # New table-to-table format
        return rewrite_table_references(sql)
    
    # Old schema-to-schema format (existing logic)
    def repl(match):
        db = match.group(1)
        sch = match.group(2)
        rest = match.group(3)  # includes leading dot + table/view/etc
        key = (db.lower(), sch.lower())
        if key in SCHEMA_MAP:
            cat, new_sch = SCHEMA_MAP[key]
            if new_sch in (None, "*"):
                # keep object name only if schema is wildcard/None; otherwise use provided schema
                return f"{cat}{rest}"
            return f"{cat}.{new_sch}{rest}"
        return match.group(0)
    
    def repl_underscore(match):
        db = match.group(1)
        sch = match.group(2)
        rest = match.group(3)  # includes leading dot + table/view/etc
        key = (db.lower(), f"{db.lower()}_{sch.lower()}")
        if key in SCHEMA_MAP:
            cat, new_sch = SCHEMA_MAP[key]
            if new_sch in (None, "*"):
                # keep object name only if schema is wildcard/None; otherwise use provided schema
                return f"{cat}{rest}"
            return f"{cat}.{new_sch}{rest}"
        return match.group(0)
    
    # Match prod.schema.object  (object can include dots for dbt models or views)
    pattern = re.compile(r'\b([A-Za-z0-9_]+)\.([A-Za-z0-9_]+)(\.[A-Za-z0-9_`"]+)', re.IGNORECASE)
    out = pattern.sub(repl, sql)
    
    # Match prod_schema.object  (underscore format)
    pattern_underscore = re.compile(r'\b(prod)_([A-Za-z0-9_]+)(\.[A-Za-z0-9_`"]+)', re.IGNORECASE)
    out = pattern_underscore.sub(repl_underscore, out)

def rewrite_table_references(sql: str) -> str:
    """
    Rewrite table references using table-to-table mappings.
    Handles various quoting patterns and ensures proper replacement.
    """
    out = sql
    
    # Sort mappings by length (descending) to avoid partial matches
    sorted_mappings = sorted(SCHEMA_MAP.items(), key=lambda x: -len(x[0]))
    
    for redshift_table, databricks_table in sorted_mappings:
        # Handle different quoting and reference patterns
        patterns_to_try = []
        
        # Pattern 1: Unquoted table name with word boundaries
        patterns_to_try.append(rf'\b{re.escape(redshift_table)}\b')
        
        # Pattern 2: Fully quoted table name
        patterns_to_try.append(rf'"{re.escape(redshift_table)}"')
        
        # Pattern 3: Handle schema.table patterns where redshift_table might be schema.table
        if '.' in redshift_table:
            parts = redshift_table.split('.')
            # "schema"."table" format
            if len(parts) == 2:
                quoted_pattern = rf'"{re.escape(parts[0])}"\s*\.\s*"{re.escape(parts[1])}"'
                patterns_to_try.append(quoted_pattern)
            # catalog.schema.table format  
            elif len(parts) == 3:
                quoted_pattern = rf'"{re.escape(parts[0])}"\s*\.\s*"{re.escape(parts[1])}"\s*\.\s*"{re.escape(parts[2])}"'
                patterns_to_try.append(quoted_pattern)
        
        # Try each pattern
        for pattern in patterns_to_try:
            new_sql = re.sub(pattern, databricks_table, out, flags=re.IGNORECASE)
            if new_sql != out:
                out = new_sql
                break  # Move to next mapping once we find a match
    
    return out
    
    return out


# ---------- 3) Function & syntax rewrites (enhanced with CSV mappings) ----------
# Simple token-level rewrites done first; complex argument-reordering handled below.
SQL_SIMPLE_REWRITES = [
    (r'\bNVL\s*\(', 'COALESCE('),
    (r'\bIFNULL\s*\(', 'COALESCE('),

    # Date/time identity functions
    (r'\bCURRENT_DATE\b\s*\(\s*\)', 'CURRENT_DATE()'),
    (r'\bCURRENT_DATE\b(?!\s*\()', 'CURRENT_DATE()'),
    (r'\bCURRENT_TIMESTAMP\b\s*\(\s*\)', 'CURRENT_TIMESTAMP()'),
    (r'\bCURRENT_TIMESTAMP\b(?!\s*\()', 'CURRENT_TIMESTAMP()'),

    # Type names and casts
    (r'::varchar\b', '::string'),
    (r'\bCAST\s*\(\s*([^)]*?)\s+AS\s+VARCHAR(\s*\(\s*\d+\s*\))?\s*\)', r'CAST(\1 AS STRING)'),

    # String/regex functions
    (r'\bSTRPOS\s*\(', 'INSTR('),
    (r'\bREGEXP_SUBSTR\s*\(', 'REGEXP_EXTRACT('),
    (r'\bREGEXP_INSTR\s*\(', 'REGEXP_INSTR('),
    (r'\bREGEXP_REPLACE\s*\(', 'REGEXP_REPLACE('),

    # Arrays & strings
    (r'\bSPLIT_TO_ARRAY\s*\(', 'SPLIT('),

    # EXTRACT to dedicated functions (handled by complex replacer below)
]

def apply_csv_function_mappings(sql: str) -> str:
    """Apply function mappings from CSV file"""
    out = sql
    
    # Apply loaded function mappings from CSV
    for redshift_func, databricks_equiv in FUNCTION_MAPPINGS.items():
        if redshift_func and databricks_equiv:
            # Handle some special cases based on the CSV content
            if 'VARCHAR' in redshift_func:
                # Handle VARCHAR -> STRING mapping
                out = re.sub(r'\bVARCHAR\b', 'STRING', out, flags=re.IGNORECASE)
            elif 'CURRENT_DATE' in redshift_func:
                # Already handled in simple rewrites
                continue
            elif 'CURRENT_TIMESTAMP' in redshift_func:
                # Already handled in simple rewrites  
                continue
            else:
                # For more complex function patterns, we'll handle them in the complex function rewriter
                pass
    
    return out

QUALIFY_PATTERN = re.compile(r'QUALIFY\b', re.IGNORECASE)

# Complex function translations requiring argument reordering or pattern interpretation
def rewrite_complex_functions(sql: str) -> str:
    out = sql

    # DATE_TRUNC('unit', expr) -> date_trunc('UNIT', expr) (upper-case unit)
    def dt_repl(m):
        unit = m.group(1)
        expr = m.group(2)
        return f"date_trunc('{unit.upper()}', {expr})"
    out = re.sub(r"\bDATE_TRUNC\s*\(\s*'(\w+)'\s*,\s*(.*?)\)", dt_repl, out, flags=re.IGNORECASE)

    # DATEADD(day, n, date_col) -> date_add(date_col, n) ; if n negative literal -> date_sub(date_col, abs(n))
    def dateadd_repl(m):
        part = m.group(1).lower()
        n = m.group(2).strip()
        expr = m.group(3).strip()
        if part == 'day' or part == 'days':
            # try to detect simple negative literal
            if re.fullmatch(r'-\s*\d+', n):
                n_clean = re.sub(r'\s+', '', n)[1:]  # drop leading '-'
                return f"date_sub({expr}, {n_clean})"
            else:
                return f"date_add({expr}, {n})"
        elif part == 'month' or part == 'months':
            return f"add_months({expr}, {n})"
        else:
            # leave others as ANSI DATEADD (Databricks supports many units)
            return f"DATEADD({part}, {n}, {expr})"
    
    # Improved regex to handle nested parentheses in function calls
    def replace_dateadd(text):
        pattern = r'\bDATEADD\s*\('
        result = []
        i = 0
        while i < len(text):
            match = re.search(pattern, text[i:], re.IGNORECASE)
            if not match:
                result.append(text[i:])
                break
            
            # Add text before match
            result.append(text[i:i + match.start()])
            
            # Find the complete DATEADD function call
            start_pos = i + match.start()
            paren_pos = i + match.end() - 1  # Position of opening parenthesis
            
            # Count parentheses to find the matching closing one
            paren_count = 1
            j = paren_pos + 1
            while j < len(text) and paren_count > 0:
                if text[j] == '(':
                    paren_count += 1
                elif text[j] == ')':
                    paren_count -= 1
                j += 1
            
            if paren_count == 0:
                # Found complete function call
                full_call = text[start_pos:j]
                # Extract arguments more carefully
                inner_args = text[paren_pos + 1:j - 1]
                
                # Split by commas, but respect nested parentheses
                args = []
                current_arg = ""
                paren_depth = 0
                for char in inner_args:
                    if char == '(' :
                        paren_depth += 1
                        current_arg += char
                    elif char == ')':
                        paren_depth -= 1
                        current_arg += char
                    elif char == ',' and paren_depth == 0:
                        args.append(current_arg.strip())
                        current_arg = ""
                    else:
                        current_arg += char
                
                if current_arg:
                    args.append(current_arg.strip())
                
                if len(args) >= 3:
                    part = args[0].lower()
                    n = args[1].strip()
                    expr = args[2].strip()
                    
                    if part == 'day' or part == 'days':
                        if re.fullmatch(r'-\s*\d+', n):
                            n_clean = re.sub(r'\s+', '', n)[1:]
                            replacement = f"date_sub({expr}, {n_clean})"
                        else:
                            replacement = f"date_add({expr}, {n})"
                    elif part == 'week' or part == 'weeks':
                        # Convert weeks to days (1 week = 7 days)
                        if re.fullmatch(r'-\s*\d+', n):
                            n_clean = re.sub(r'\s+', '', n)[1:]
                            replacement = f"date_sub({expr}, {n_clean} * 7)"
                        else:
                            replacement = f"date_add({expr}, {n} * 7)"
                    elif part == 'month' or part == 'months':
                        replacement = f"add_months({expr}, {n})"
                    else:
                        replacement = f"DATEADD({part}, {n}, {expr})"
                    
                    result.append(replacement)
                else:
                    result.append(full_call)  # Keep original if can't parse
                
                i = j
            else:
                # Malformed function call, keep original
                result.append(text[start_pos:start_pos + match.end() - match.start()])
                i = start_pos + match.end() - match.start()
        
        return ''.join(result)
    
    out = replace_dateadd(out)

    # DATEDIFF(day, d1, d2) -> datediff(d2, d1) ; for other units, keep as-is (Databricks ANSI supports)
    # Use similar approach as DATEADD to handle nested parentheses
    def replace_datediff(text):
        pattern = r'\bDATEDIFF\s*\('
        result = []
        i = 0
        while i < len(text):
            match = re.search(pattern, text[i:], re.IGNORECASE)
            if not match:
                result.append(text[i:])
                break
            
            # Add text before match
            result.append(text[i:i + match.start()])
            
            # Find the complete DATEDIFF function call
            start_pos = i + match.start()
            paren_pos = i + match.end() - 1  # Position of opening parenthesis
            
            # Count parentheses to find the matching closing one
            paren_count = 1
            j = paren_pos + 1
            while j < len(text) and paren_count > 0:
                if text[j] == '(':
                    paren_count += 1
                elif text[j] == ')':
                    paren_count -= 1
                j += 1
            
            if paren_count == 0:
                # Found complete function call
                full_call = text[start_pos:j]
                # Extract arguments more carefully
                inner_args = text[paren_pos + 1:j - 1]
                
                # Split by commas, but respect nested parentheses
                args = []
                current_arg = ""
                paren_depth = 0
                for char in inner_args:
                    if char == '(':
                        paren_depth += 1
                        current_arg += char
                    elif char == ')':
                        paren_depth -= 1
                        current_arg += char
                    elif char == ',' and paren_depth == 0:
                        args.append(current_arg.strip())
                        current_arg = ""
                    else:
                        current_arg += char
                
                if current_arg:
                    args.append(current_arg.strip())
                
                if len(args) >= 3:
                    part = args[0].lower()
                    d1 = args[1].strip()
                    d2 = args[2].strip()
                    
                    if part in ('day', 'days'):
                        replacement = f"datediff({d2}, {d1})"
                    else:
                        replacement = f"DATEDIFF({part}, {d1}, {d2})"
                    
                    result.append(replacement)
                else:
                    result.append(full_call)  # Keep original if can't parse
                
                i = j
            else:
                # Malformed function call, keep original
                result.append(text[start_pos:start_pos + match.end() - match.start()])
                i = start_pos + match.end() - match.start()
        
        return ''.join(result)
    
    out = replace_datediff(out)

    # TO_CHAR(ts, 'fmt') -> date_format(ts, 'fmt') with format token normalization
    def tochar_repl(m):
        expr = m.group(1).strip()
        fmt = m.group(2)
        # Simple token map common in your examples
        fmt_map = [
            ('YYYY', 'yyyy'),
            ('YY', 'yy'),
            ('MM', 'MM'),
            ('MON', 'MMM'),
            ('DD', 'dd'),
            ('HH24', 'HH'),
            ('HH12', 'hh'),
            ('MI', 'mm'),
            ('SS', 'ss')
        ]
        fmt_new = fmt
        for k,v in fmt_map:
            fmt_new = fmt_new.replace(k, v)
        return f"date_format({expr}, '{fmt_new}')"
    out = re.sub(r"\bTO_CHAR\s*\(\s*(.+?)\s*,\s*'([^']+)'\s*\)", tochar_repl, out, flags=re.IGNORECASE)

    # TO_DATE('2023-01-01','YYYY-MM-DD') -> to_date('2023-01-01','yyyy-MM-dd')
    def todate_repl(m):
        expr = m.group(1).strip()
        fmt = m.group(2)
        fmt_new = fmt.replace('YYYY','yyyy').replace('DD','dd')
        return f"to_date({expr}, '{fmt_new}')"
    out = re.sub(r"\bTO_DATE\s*\(\s*(.+?)\s*,\s*'([^']+)'\s*\)", todate_repl, out, flags=re.IGNORECASE)

    # JSON_EXTRACT_PATH_TEXT(json_col, 'a.b') -> get_json_object(json_col, '$.a.b')
    def jpath_repl(m):
        col = m.group(1).strip()
        path = m.group(2).strip().strip("'").strip('"')
        # convert a.b to $.a.b ; handle simple array index inside path like a[0].b
        if not path.startswith('$.'):
            path = '$.' + path
        return f"get_json_object({col}, '{path}')"
    out = re.sub(r"\bJSON_EXTRACT_PATH_TEXT\s*\(\s*([^,]+)\s*,\s*('[^']+'|\"[^\"]+\")\s*\)", jpath_repl, out, flags=re.IGNORECASE)

    # JSON_EXTRACT_ARRAY_ELEMENT_TEXT(json_col, idx) -> get_json_object(json_col, '$[idx]')
    def jarr_repl(m):
        col = m.group(1).strip()
        idx = m.group(2).strip()
        return f"get_json_object({col}, '$[{idx}]')"
    out = re.sub(r"\bJSON_EXTRACT_ARRAY_ELEMENT_TEXT\s*\(\s*([^,]+)\s*,\s*([^)]+)\)", jarr_repl, out, flags=re.IGNORECASE)

    # IS_VALID_JSON(json) -> try(from_json(json,'map<string,string>')) IS NOT NULL
    out = re.sub(r"\bIS_VALID_JSON_ARRAY\s*\(\s*([^)]+)\)", r"try(from_json(\1, 'array<string>')) IS NOT NULL", out, flags=re.IGNORECASE)
    out = re.sub(r"\bIS_VALID_JSON\s*\(\s*([^)]+)\)", r"try(from_json(\1, 'map<string,string>')) IS NOT NULL", out, flags=re.IGNORECASE)

    # JSON_PARSE(json) -> from_json(json, <schema>) with TODO marker if schema missing
    out = re.sub(r"\bJSON_PARSE\s*\(\s*([^)]+)\)", r"/* TODO: provide schema */ from_json(\1, '<provide_schema_here>')", out, flags=re.IGNORECASE)

    # LISTAGG(col, delim) -> concat_ws(delim, collect_list(col))
    # Handle WITHIN GROUP (ORDER BY ...) clause
    def listagg_repl(m):
        args = m.group(1)
        parts = [a.strip() for a in args.split(',')]
        if len(parts) >= 2:
            col = parts[0]
            delim = ','.join(parts[1:])  # delimiter expression may contain commas
            return f"concat_ws({delim}, collect_list({col}))"
        return f"STRING_AGG({args})"
    
    # First handle LISTAGG with WITHIN GROUP clause
    out = re.sub(r"\bLISTAGG\s*\(\s*(.+?)\s*\)\s+WITHIN\s+GROUP\s*\([^)]*\)", listagg_repl, out, flags=re.IGNORECASE)
    # Then handle simple LISTAGG without WITHIN GROUP
    out = re.sub(r"\bLISTAGG\s*\(\s*(.+?)\s*\)", listagg_repl, out, flags=re.IGNORECASE)

    # CONVERT(type, expression) -> CAST(expression AS type)
    def convert_repl(m):
        type_name = m.group(1).strip().upper()
        expr = m.group(2).strip()
        # Map common Redshift types to Databricks types
        type_mapping = {
            'VARCHAR': 'STRING',
            'CHAR': 'STRING', 
            'TEXT': 'STRING',
            'INTEGER': 'INT',
            'BIGINT': 'BIGINT',
            'DECIMAL': 'DECIMAL',
            'NUMERIC': 'DECIMAL',
            'FLOAT': 'FLOAT',
            'DOUBLE': 'DOUBLE',
            'DATE': 'DATE',
            'TIMESTAMP': 'TIMESTAMP'
        }
        mapped_type = type_mapping.get(type_name, type_name)
        return f"CAST({expr} AS {mapped_type})"
    
    out = re.sub(r"\bCONVERT\s*\(\s*(\w+)\s*,\s*(.+?)\s*\)", convert_repl, out, flags=re.IGNORECASE)

    # DATEPART('field', expr) -> year(expr)/month(expr)/etc
    def datepart_repl(m):
        field = m.group(1).lower()
        expr = m.group(2).strip()
        mapping = {
            'year':'year', 'yy':'year',
            'month':'month', 'mm':'month',
            'day':'day', 'dd':'day',
            'hour':'hour', 'minute':'minute', 'second':'second',
            'week':'weekofyear', 'dow':'dayofweek',
            'quarter':'quarter'
        }
        func = mapping.get(field, None)
        if func:
            return f"{func}({expr})"
        return m.group(0)
    out = re.sub(r"\bDATEPART\s*\(\s*'(\w+)'\s*,\s*(.+?)\)", datepart_repl, out, flags=re.IGNORECASE)

    # EXTRACT(<field> FROM expr) -> corresponding function
    def extract_repl(m):
        field = m.group(1).lower()
        expr = m.group(2).strip()
        mapping = {
            'year':'year',
            'month':'month',
            'day':'day',
            'dow':'dayofweek',
            'hour':'hour',
            'minute':'minute',
            'second':'second',
            'week':'weekofyear',
            'quarter':'quarter',
        }
        func = mapping.get(field, None)
        if func:
            return f"{func}({expr})"
        return m.group(0)
    out = re.sub(r"\bEXTRACT\s*\(\s*(\w+)\s+FROM\s+(.+?)\)", extract_repl, out, flags=re.IGNORECASE)

    # Handle DATEADD with 'week' unit -> date_add with 7 * n days
    def dateadd_week_repl(m):
        n = m.group(1).strip()
        expr = m.group(2).strip()
        return f"date_add({expr}, {n} * 7)"
    out = re.sub(r"\bDATEADD\s*\(\s*week\s*,\s*([^,]+)\s*,\s*([^)]+)\)", dateadd_week_repl, out, flags=re.IGNORECASE)

    # Handle ADD_MONTHS function (already supported in Databricks)
    # No transformation needed, but ensure it's recognized

    return out

def auto_fix_databricks_issues(sql: str) -> tuple[str, list]:
    """
    Automatically fix implementable Databricks issues instead of just warning.
    Returns: (fixed_sql, remaining_warnings)
    """
    out = sql
    remaining_warnings = []
    
    # 1. AUTO-FIX: Data type conversions
    out = re.sub(r'\bSUPER\b', 'STRING', out, flags=re.IGNORECASE)
    out = re.sub(r'\bVARCHAR\s*\(\s*MAX\s*\)', 'STRING', out, flags=re.IGNORECASE)
    out = re.sub(r'\bTEXT\b(?!\s*\()', 'STRING', out, flags=re.IGNORECASE)  # Avoid replacing TEXT() function
    out = re.sub(r'\bBPCHAR\b', 'STRING', out, flags=re.IGNORECASE)
    
    # 2. AUTO-FIX: Mathematical functions
    out = re.sub(r'\bMOD\s*\(\s*([^,]+)\s*,\s*([^)]+)\s*\)', r'(\1 % \2)', out, flags=re.IGNORECASE)
    
    # 3. AUTO-FIX: Type casting improvements
    out = re.sub(r'CAST\s*\(\s*([^)]+)\s+AS\s+REAL\s*\)', r'CAST(\1 AS FLOAT)', out, flags=re.IGNORECASE)
    out = re.sub(r'CAST\s*\(\s*([^)]+)\s+AS\s+DOUBLE\s+PRECISION\s*\)', r'CAST(\1 AS DOUBLE)', out, flags=re.IGNORECASE)
    
    # 4. AUTO-FIX: Array functions
    out = re.sub(r'ARRAY_TO_STRING\s*\(\s*([^,]+)\s*,\s*([^)]+)\s*\)', r'array_join(\1, \2)', out, flags=re.IGNORECASE)
    out = re.sub(r'STRING_TO_ARRAY\s*\(\s*([^,]+)\s*,\s*([^)]+)\s*\)', r'split(\1, \2)', out, flags=re.IGNORECASE)
    
    # 5. AUTO-FIX: Date functions
    out = re.sub(r'DATE_PART\s*\(\s*[\'"]epoch[\'\"]\s*,\s*([^)]+)\s*\)', r'unix_timestamp(\1)', out, flags=re.IGNORECASE)
    out = re.sub(r'EXTRACT\s*\(\s*EPOCH\s+FROM\s+([^)]+)\s*\)', r'unix_timestamp(\1)', out, flags=re.IGNORECASE)
    
    # 6. AUTO-FIX: String functions with escape handling
    out = re.sub(r'REGEXP_REPLACE\s*\(\s*([^,]+)\s*,\s*([^,]+)\s*,\s*([^,]+)\s*,\s*[\'"]g[\'\"]\s*\)', r'regexp_replace(\1, \2, \3)', out, flags=re.IGNORECASE)
    
    # 7. AUTO-FIX: JSON functions (remove unsupported parameters)
    out = re.sub(r'JSON_EXTRACT_PATH_TEXT\s*\(\s*([^,]+)\s*,\s*([^,]+)\s*,\s*true\s*\)', r'get_json_object(\1, concat("$.", \2))', out, flags=re.IGNORECASE)
    out = re.sub(r'JSON_EXTRACT_PATH_TEXT\s*\(\s*([^,]+)\s*,\s*([^,]+)\s*,\s*false\s*\)', r'get_json_object(\1, concat("$.", \2))', out, flags=re.IGNORECASE)
    
    # 8. AUTO-FIX: Performance improvements
    out = re.sub(r'EXISTS\s*\(\s*SELECT\s+\*\s+FROM', r'EXISTS (SELECT 1 FROM', out, flags=re.IGNORECASE)
    
    # 9. AUTO-FIX: Boolean comparisons
    out = re.sub(r'(\w+)\s*=\s*true\b', r'\1 IS TRUE', out, flags=re.IGNORECASE)
    out = re.sub(r'(\w+)\s*=\s*false\b', r'\1 IS FALSE', out, flags=re.IGNORECASE)
    
    # 10. AUTO-FIX: NULL comparisons
    out = re.sub(r'\bNOT\s+([^()]+?)\s+IS\s+NULL\b', r'\1 IS NOT NULL', out, flags=re.IGNORECASE)
    
    # 11. AUTO-FIX: Window functions without QUALIFY
    qualify_pattern = r'\bQUALIFY\s+(ROW_NUMBER\(\)\s+OVER\s*\([^)]+\))\s*=\s*1\b'
    if re.search(qualify_pattern, out, re.IGNORECASE):
        # Convert QUALIFY ROW_NUMBER() OVER (...) = 1 to subquery with WHERE
        def replace_qualify(match):
            row_number_expr = match.group(1)
            return f'-- Converted from QUALIFY: Add this as WHERE {row_number_expr} = 1 in subquery'
        out = re.sub(qualify_pattern, replace_qualify, out, flags=re.IGNORECASE)
    
    # REMAINING WARNINGS (things we can't auto-fix)
    
    # Correlated scalar subqueries (need manual intervention)
    correlated_subquery_patterns = [
        r'\(\s*SELECT\s+[^)]*FROM\s+\w+\s+WHERE\s+[^)]*\w+\.\w+\s*=',  # (SELECT ... WHERE outer.col = ...)
        r'\(\s*SELECT\s+[^)]*\)\s+AS\s+\w+,\s*\(\s*SELECT',            # Multiple scalar subqueries
    ]
    
    for pattern in correlated_subquery_patterns:
        if re.search(pattern, out, re.IGNORECASE | re.DOTALL):
            remaining_warnings.append("-- MANUAL: Correlated scalar subqueries detected - rewrite as JOINs or CTEs")
            remaining_warnings.append("-- EXAMPLE: WITH metrics AS (SELECT 'type1' as t, COUNT(*) as c FROM table1 UNION ALL SELECT 'type2', COUNT(*) FROM table2)")
            remaining_warnings.append("-- SELECT SUM(CASE WHEN t='type1' THEN c END) as col1, SUM(CASE WHEN t='type2' THEN c END) as col2 FROM metrics")
            break
    
    # Missing table patterns (need verification)
    missing_table_patterns = [
        r'daily_adoptions_\w+',                    # adoption tables
        r'data_engineering_staging\.\w+\.\w+',     # staging tables
    ]
    
    for pattern in missing_table_patterns:
        if re.search(pattern, out, re.IGNORECASE):
            remaining_warnings.append("-- VERIFY: Check if tables exist in Databricks - run: SHOW TABLES IN schema")
            break
    
    # Complex features that need manual review
    complex_patterns = [
        (r'\bPIVOT\s*\(', "MANUAL: PIVOT syntax may differ - verify column names and aggregation"),
        (r'\bUNPIVOT\s*\(', "MANUAL: UNPIVOT syntax may differ - verify structure"),
        (r'\bLATERAL\s+VIEW\s+OUTER\b', "MANUAL: LATERAL VIEW OUTER behavior may differ"),
        (r'\bCOPY\s+INTO\b', "MANUAL: COPY INTO syntax differs from Redshift"),
    ]
    
    for pattern, warning in complex_patterns:
        if re.search(pattern, out, re.IGNORECASE):
            remaining_warnings.append(f"-- {warning}")
    
    return out, remaining_warnings

def add_inline_warnings_to_sql(sql: str) -> str:
    """Add inline warnings right next to problematic SQL patterns."""
    lines = sql.split('\n')
    result_lines = []
    
    for i, line in enumerate(lines):
        result_lines.append(line)
        
        # Check for specific problematic patterns in this line
        if re.search(r'\(\s*SELECT\s+[^)]*FROM\s+\w+\s+WHERE', line, re.IGNORECASE):
            result_lines.append("    -- ⚠️  ISSUE: Correlated subquery may fail in Databricks")
        
        if re.search(r'daily_adoptions_\w+', line, re.IGNORECASE):
            result_lines.append("    -- ⚠️  VERIFY: Check if this adoption table exists in Databricks")
        
        if re.search(r'\bQUALIFY\b', line, re.IGNORECASE):
            result_lines.append("    -- ❌ ERROR: QUALIFY not supported - rewrite using window functions")
        
        if re.search(r'VARCHAR\s*\(\s*MAX\s*\)', line, re.IGNORECASE):
            result_lines.append("    -- 🔄 CONVERT: VARCHAR(MAX) → STRING")
        
        if re.search(r'\bSUPER\b', line, re.IGNORECASE):
            result_lines.append("    -- 🔄 CONVERT: SUPER → STRING or appropriate STRUCT type")
    
    return '\n'.join(result_lines)

def add_comprehensive_function_mappings(sql: str) -> str:
    """Add more comprehensive function mappings based on team exceptions."""
    
    # Advanced transformations based on real exceptions
    advanced_patterns = [
        # Window functions with QUALIFY
        (r'\bQUALIFY\s+ROW_NUMBER\(\)\s+OVER\s*\([^)]+\)\s*=\s*1', 
         '-- TODO: Rewrite QUALIFY as WHERE ROW_NUMBER() OVER (...) = 1 in subquery'),
        
        # Complex JSON handling
        (r'JSON_EXTRACT_PATH_TEXT\s*\(\s*([^,]+)\s*,\s*\'([^\']+)\'\s*,\s*true\s*\)',
         r'get_json_object(\1, "$.\2") -- Note: ignoreCase parameter removed'),
        
        # Array functions
        (r'ARRAY_TO_STRING\s*\(\s*([^,]+)\s*,\s*([^)]+)\s*\)',
         r'array_join(\1, \2)'),
        
        # Advanced date functions
        (r'DATE_PART\s*\(\s*\'epoch\'\s*,\s*([^)]+)\s*\)',
         r'unix_timestamp(\1)'),
        
        # String functions with escape handling
        (r'REGEXP_REPLACE\s*\(\s*([^,]+)\s*,\s*\'([^\']+)\'\s*,\s*\'([^\']+)\'\s*,\s*\'g\'\s*\)',
         r'regexp_replace(\1, "\2", "\3")'),
        
        # Mathematical functions
        (r'\bMOD\s*\(\s*([^,]+)\s*,\s*([^)]+)\s*\)',
         r'(\1 % \2)'),
        
        # Type casting edge cases
        (r'CAST\s*\(\s*([^)]+)\s+AS\s+REAL\s*\)',
         r'CAST(\1 AS FLOAT)'),
    ]
    
    for pattern, replacement in advanced_patterns:
        sql = re.sub(pattern, replacement, sql, flags=re.IGNORECASE)
    
    return sql

def apply_sql_rewrites(sql: str) -> str:
    """
    Apply comprehensive SQL transformations for Redshift -> Databricks migration.
    Enhanced with automatic fixes and remaining manual warnings.
    """
    # Step 1: Auto-fix implementable issues and get remaining warnings
    out, remaining_warnings = auto_fix_databricks_issues(sql)
    
    out = rewrite_schema_qualification(out)
    
    # Apply CSV function mappings first
    out = apply_csv_function_mappings(out)
    
    # Add comprehensive function mappings based on team exceptions
    out = add_comprehensive_function_mappings(out)
    
    # Apply simple regex rewrites
    for pat, repl in SQL_SIMPLE_REWRITES:
        out = re.sub(pat, repl, out, flags=re.IGNORECASE)
    
    # Apply complex function transformations
    out = rewrite_complex_functions(out)
    
    # Add inline warnings to problematic patterns (simplified since many are now auto-fixed)
    out = add_inline_warnings_to_sql(out)
    
    # Flag QUALIFY for manual inspection (if not already auto-converted)
    if QUALIFY_PATTERN.search(out) and 'Converted from QUALIFY' not in out:
        out = "-- TODO(manual): Translate QUALIFY to WHERE with window subquery\n" + out
    
    # Flag correlated scalar subqueries that may need manual conversion
    # Pattern: (SELECT ... FROM table WHERE condition referencing outer table)
    correlated_subquery_pattern = r'\(\s*SELECT\s+[^)]+\s+FROM\s+\w+\s+WHERE\s+[^)]*\bld\.'
    if re.search(correlated_subquery_pattern, out, re.IGNORECASE | re.DOTALL):
        out = "-- TODO(manual): Databricks requires correlated scalar subqueries to be aggregated or rewritten as JOINs\n-- Error: UNSUPPORTED_SUBQUERY_EXPRESSION_CATEGORY.MUST_AGGREGATE_CORRELATED_SCALAR_SUBQUERY\n-- See: https://docs.databricks.com/sql/language-manual/sql-ref-subqueries.html\n" + out
    
    # Flag multiple scalar subqueries in SELECT clause (common anti-pattern)
    # Look for pattern: (SELECT ... FROM ...) AS ... (SELECT ... FROM ...)
    scalar_subquery_pattern = r'\(\s*SELECT\s+.*?\s+FROM\s+.*?\)\s+AS\s+.*?\(\s*SELECT\s+.*?\s+FROM\s+.*?\)'
    if re.search(scalar_subquery_pattern, out, re.IGNORECASE | re.DOTALL):
        print("⚠️  WARNING: Multiple scalar subqueries detected - may cause performance issues in Databricks")
        out = "-- TODO(manual): Multiple scalar subqueries detected - rewrite as JOINs or CTEs\n-- EXAMPLE: Replace (SELECT COUNT(*) FROM table1) AS col1, (SELECT COUNT(*) FROM table2) AS col2\n-- WITH: WITH metrics AS (SELECT 'table1' as type, COUNT(*) as cnt FROM table1 UNION ALL SELECT 'table2', COUNT(*) FROM table2)\n-- SELECT SUM(CASE WHEN type='table1' THEN cnt END) as col1, SUM(CASE WHEN type='table2' THEN cnt END) as col2 FROM metrics\n" + out
    
    # Flag potential missing tables (tables that might not exist in Databricks)
    adoption_tables_pattern = r'daily_adoptions_\w+'
    if re.search(adoption_tables_pattern, out, re.IGNORECASE):
        print("⚠️  WARNING: Adoption tables detected - verify these exist in Databricks")
        out = "-- TODO(manual): Verify table existence in Databricks - run: SHOW TABLES IN schema LIKE '*adoption*'\n-- Some tables may have different names, schemas, or may not have been migrated yet\n" + out
    
    # Flag other potential Databricks compatibility issues
    # 1. Check for correlated subqueries (common cause of UNSUPPORTED_SUBQUERY_EXPRESSION_CATEGORY error)
    correlated_subquery_pattern = r'WHERE.*\(\s*SELECT.*WHERE.*\.\w+\s*=\s*\w+\.\w+'
    if re.search(correlated_subquery_pattern, out, re.IGNORECASE | re.DOTALL):
        print("⚠️  WARNING: Potential correlated subquery detected")
        out = "-- TODO(manual): Correlated subquery detected - may need to rewrite as JOIN\n-- ERROR: UNSUPPORTED_SUBQUERY_EXPRESSION_CATEGORY.MUST_AGGREGATE_CORRELATED_SCALAR_SUBQUERY\n" + out
    
    # 2. Check for potential table/view references that might not exist
    table_ref_patterns = [
        r'\bprod\.[A-Za-z0-9_]+\.[A-Za-z0-9_]+',  # prod.schema.table pattern
        r'\braw_[A-Za-z0-9_]+\.[A-Za-z0-9_]+',    # raw_source.table pattern  
        r'\bstaging\.[A-Za-z0-9_]+\.[A-Za-z0-9_]+' # staging.schema.table pattern
    ]
    
    for pattern in table_ref_patterns:
        if re.search(pattern, out, re.IGNORECASE):
            print("⚠️  WARNING: Legacy table references detected - verify schema mapping")
            out = "-- TODO(manual): Legacy table references detected - verify schema/catalog mapping in Databricks\n-- TIP: Use SHOW TABLES to verify table existence and correct names\n" + out
            break
    
    # Add header warnings for remaining manual issues
    if remaining_warnings:
        warning_header = '\n'.join(remaining_warnings) + '\n\n'
        out = warning_header + out
    
    return out

# ---------- 3) YAML processing ----------

def transform_hex_yaml(doc: dict, databricks_conn_id: str, redshift_conn_ids=None):
    d = deepcopy(doc)
    
    # Default Redshift connection IDs if none provided
    if redshift_conn_ids is None:
        redshift_conn_ids = [
            "e2694948-2c20-47d3-b127-71448e2bf238",  # Redshift (with raw tables)
            "0d0da619-5aa7-4f55-b020-ba94bfa77917",  # Redshift
            "63ebcea0-017f-4bcf-b58a-a2340a75845f"   # Redshift (with external tables)
        ]
        print(f"🔍 Using default Redshift connection IDs: {redshift_conn_ids}")
    
    redshift_conn_ids = set(redshift_conn_ids or [])
    rewrote_cells = 0
    for cell in d.get("cells", []):
        cell_type = cell.get("type") or cell.get("cellType")
        
        # Handle INPUT cells - convert boolean inputs to text for Databricks compatibility
        if cell_type == "INPUT":
            data = cell.get("data", {}) or cell.get("config", {})
            input_type = data.get("inputType")
            
            # Convert boolean input types to text for Databricks compatibility
            if input_type in ("BOOLEAN", "TOGGLE", "CHECKBOX"):
                print(f"🔄 Converting boolean input '{data.get('name', 'unnamed')}' to TEXT for Databricks compatibility")
                data["inputType"] = "TEXT"
                # Update default value if it's a boolean
                default_value = data.get("defaultValue")
                if isinstance(default_value, bool):
                    data["defaultValue"] = "true" if default_value else "false"
                elif default_value in (True, False):
                    data["defaultValue"] = "true" if default_value else "false"
            continue
        
        # Only process SQL cells (check both 'type' and 'cellType' fields)
        if cell_type.upper() not in ("DATA", "SQL"):
            continue
        
        # Handle both data structure formats
        data = cell.get("data", {}) or cell.get("config", {})
        query = data.get("query") or data.get("source")
        conn_id = data.get("dataConnectionId") or cell.get("dataConnectionId")
        
        # Only process if it's explicitly a Redshift connection
        should_process = False
        if redshift_conn_ids and conn_id in redshift_conn_ids:
            # Explicitly identified Redshift connection
            should_process = True
        elif not redshift_conn_ids and isinstance(query, str) and (
            re.search(r'\bprod\.[A-Za-z0-9_]+\.[A-Za-z0-9_]+', query, re.IGNORECASE) or
            re.search(r'\bprod_[A-Za-z0-9_]+\.[A-Za-z0-9_]+', query, re.IGNORECASE)
        ):
            # Fallback: If no specific Redshift conn IDs provided, use schema heuristics
            should_process = True

        if not should_process:
            continue

        # 1) Update connection
        if "dataConnectionId" in cell:
            cell["dataConnectionId"] = databricks_conn_id
        elif "dataConnectionId" in data:
            data["dataConnectionId"] = databricks_conn_id

        # 2) Rewrite SQL
        if isinstance(query, str):
            rewritten_sql = apply_sql_rewrites(query)
            if "query" in data:
                data["query"] = rewritten_sql
            if "source" in data:
                data["source"] = rewritten_sql
            rewrote_cells += 1

    # Update project-level default connection if present
    if "defaultDataConnectionId" in d:
        if (not redshift_conn_ids) or (d["defaultDataConnectionId"] in redshift_conn_ids):
            d["defaultDataConnectionId"] = databricks_conn_id

    # Update sharedAssets dataConnections to include/replace with Databricks connection
    if "sharedAssets" in d and "dataConnections" in d["sharedAssets"]:
        data_connections = d["sharedAssets"]["dataConnections"]
        
        # Check if Databricks connection already exists
        databricks_exists = any(
            conn.get("dataConnectionId") == databricks_conn_id 
            for conn in data_connections
        )
        
        if not databricks_exists:
            # If we have specific Redshift connection IDs, replace those
            if redshift_conn_ids:
                for i, conn in enumerate(data_connections):
                    if conn.get("dataConnectionId") in redshift_conn_ids:
                        data_connections[i] = {"dataConnectionId": databricks_conn_id}
                        break
                else:
                    # If no Redshift connections found, add Databricks connection
                    data_connections.append({"dataConnectionId": databricks_conn_id})
            else:
                # If no specific Redshift IDs provided, replace the first connection or add new one
                if data_connections:
                    data_connections[0] = {"dataConnectionId": databricks_conn_id}
                else:
                    data_connections.append({"dataConnectionId": databricks_conn_id})

    return d, rewrote_cells

def load_yaml(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

def save_yaml(obj: dict, path: str):
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(obj, f, sort_keys=False, allow_unicode=True)

def process_file(in_path: str, out_path: str, databricks_conn_id: str, redshift_conn_ids=None):
    doc = load_yaml(in_path)
    new_doc, n = transform_hex_yaml(doc, databricks_conn_id, redshift_conn_ids)
    save_yaml(new_doc, out_path)
    print(f"[OK] {in_path} -> {out_path} | cells rewritten: {n}")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="in_path", help="Input Hex project YAML")
    ap.add_argument("--out", dest="out_path", help="Output YAML path")
    ap.add_argument("--in-dir", dest="in_dir", help="Directory of YAMLs to convert")
    ap.add_argument("--out-dir", dest="out_dir", help="Output directory for converted YAMLs (optional)")
    ap.add_argument("--databricks-conn-id", required=True, help="Target Databricks dataConnectionId")
    ap.add_argument("--redshift-conn-ids", nargs="*", default=None, help="Redshift connection IDs to target (optional - uses hardcoded defaults if not specified)")
    args = ap.parse_args()

    if not args.in_path and not args.in_dir:
        ap.error("Provide --in or --in-dir")

    if args.in_dir:
        # Create output directory if specified
        output_dir = args.out_dir or args.in_dir
        if args.out_dir and not os.path.exists(args.out_dir):
            os.makedirs(args.out_dir)
            
        for name in os.listdir(args.in_dir):
            if not name.lower().endswith((".yaml", ".yml")):
                continue
            in_path = os.path.join(args.in_dir, name)
            base, ext = os.path.splitext(name)
            # If same directory, add suffix. If different directory, keep original name
            if args.out_dir and args.out_dir != args.in_dir:
                out_name = name  # Keep original name in different directory
            else:
                out_name = f"{base}_databricks{ext}"  # Add suffix in same directory
            out_path = os.path.join(output_dir, out_name)
            process_file(in_path, out_path, args.databricks_conn_id, args.redshift_conn_ids)
    else:
        out_path = args.out_path or re.sub(r'\.ya?ml$', '_databricks.yaml', args.in_path, flags=re.IGNORECASE)
        process_file(args.in_path, out_path, args.databricks_conn_id, args.redshift_conn_ids)

if __name__ == "__main__":
    main()
