# SnoMAP - SNOMED CT to ICD-10 Mapper

A Python client for interacting with the QCTS FHIR API to map SNOMED CT codes to ICD-10 codes, specifically designed for Emergency Department (ED) use cases.

## Created by
benson.choy@health.qld.gov.au

## Features

- FHIR-compliant API integration for terminology mapping
- OAuth2 authentication support
- Batch processing of SNOMED CT codes
- ICD-10 code mapping with validation
- Logging and error handling
- YAML-based configuration

## Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/yourusername/snomap.git
   cd snomap
   ```

2. Create and activate a virtual environment:
   ```bash
   # On Windows
   python -m venv .venv
   .venv\Scripts\activate

   # On macOS/Linux
   python3 -m venv .venv
   source .venv/bin/activate
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
   
   Or install individual packages:
   ```bash
   pip install requests pyyaml
   ```

## Setup

1. Configure your credentials:
   - Create a `cred.yml` file in the `snomap` directory
   - Add your FHIR server credentials:
     ```yaml
     client_id: "your_client_id"
     client_secret: "your_client_secret"
     token_endpoint: "your_oauth_token_endpoint"
     fhir_endpoint: "your_fhir_server_endpoint"
     ```

   The `cred.yml` file requires four parameters:
   - `client_id`: OAuth2 client identifier
   - `client_secret`: OAuth2 client secret
   - `token_endpoint`: Full URL of the OAuth2 token endpoint
   - `fhir_endpoint`: Base URL of the FHIR server

## Usage

SnoMAP uses the FHIR ConceptMap resource to perform standardized terminology mapping.

### Basic Usage

Map a single SNOMED CT code to ICD-10:
```bash
# Normal run - will skip if code already exists
python3 snomap.py --code 39065001

# Full refresh - will reprocess even if previously mapped
python3 snomap.py --code 39065001 --full-refresh
```

### Batch Processing

Map multiple SNOMED CT codes at once:
```bash
# Normal run - will skip existing codes
python3 snomap.py --batch input_codes.txt

# Full refresh - will clear output and process all codes
python3 snomap.py --batch input_codes.txt --full-refresh
```

The input file should contain one SNOMED CT code per line:
```text
39065001
73211009
35489007
```

### Error Handling

The program handles failed mappings in the following ways:

- Successful mappings are written to `output_codes.csv` with:
  - Unique ID
  - SNOMED CT code
  - ICD-10 code
  - Timestamp

- Failed mappings are written to `failed_codes.csv` with:
  - Unique ID
  - SNOMED CT code
  - Error message (either "No mapping found" or specific error details)
  - Timestamp

- All API responses (successful or failed) are saved as JSON files:
  ```bash
  output/json/{snomed_code}.json
  ```

### Processing Summary

After processing, the program displays statistics including:
- Total codes found
- Codes skipped (already mapped)
- Codes processed successfully
- Codes with errors/no mapping

### Output Files

The program generates three types of output:
1. `output_codes.csv` - Successful SNOMED CT to ICD-10 mappings
2. `failed_codes.csv` - Failed mapping attempts with error details
3. `output/json/*.json` - Raw API responses for each code processed

## Known Limitations
- Some SNOMED CT codes may not have direct ICD-10 mappings
