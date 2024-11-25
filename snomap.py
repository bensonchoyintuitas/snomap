import yaml
import requests
from pathlib import Path
import logging
from typing import Optional, Dict, Any, List
import argparse
import csv
from datetime import datetime
import os
import json

class FHIRClient:
    def __init__(self, cred_file: str = "cred.yml"):
        self.logger = logging.getLogger(__name__)
        self.access_token = None
        self._load_credentials(cred_file)
        
    def _load_credentials(self, cred_file: str) -> None:
        """Load credentials from YAML file."""
        try:
            cred_path = Path(__file__).parent / cred_file
            with open(cred_path, 'r') as file:
                creds = yaml.safe_load(file)
                self.client_id = creds['client_id']
                self.client_secret = creds['client_secret']
                self.token_endpoint = creds['token_endpoint']
                self.fhir_endpoint = creds['fhir_endpoint']
        except Exception as e:
            self.logger.error(f"Error loading credentials: {str(e)}")
            raise

    def get_access_token(self) -> Optional[str]:
        """Obtain OAuth2 access token."""
        try:
            data = {
                'grant_type': 'client_credentials',
                'client_id': self.client_id,
                'client_secret': self.client_secret
            }
            
            response = requests.post(self.token_endpoint, data=data)
            response.raise_for_status()
            
            token_data = response.json()
            self.access_token = token_data.get('access_token')
            return self.access_token
            
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Error obtaining access token: {str(e)}")
            return None

    def make_fhir_request(self, resource_type: str, resource_id: Optional[str] = None, 
                         parameters: Optional[Dict[str, Any]] = None) -> Optional[Dict]:
        """Make a FHIR API request."""
        if not self.access_token:
            self.get_access_token()
            if not self.access_token:
                return None

        headers = {
            'Authorization': f'Bearer {self.access_token}',
            'Accept': 'application/fhir+json',
            'Content-Type': 'application/fhir+json'
        }

        # Construct the URL
        url = f"{self.fhir_endpoint}/{resource_type}"
        if resource_id:
            url = f"{url}/{resource_id}"

        try:
            # Use POST for batch translate operations
            if resource_type == "ConceptMap/$translate":
                # Create FHIR Parameters resource for single code or batch
                if 'coding' in parameters:
                    # Batch translate format
                    data = {
                        "resourceType": "Parameters",
                        "parameter": [
                            {
                                "name": "coding",
                                "valueCoding": coding
                            } for coding in parameters['coding']
                        ]
                    }
                else:
                    # Single code translate format
                    data = {
                        "resourceType": "Parameters",
                        "parameter": [
                            {
                                "name": "coding",
                                "valueCoding": {
                                    "system": parameters['system'],
                                    "code": parameters['code']
                                }
                            }
                        ]
                    }
                response = requests.post(url, headers=headers, json=data)
            else:
                response = requests.get(url, headers=headers, params=parameters)

            self.logger.info(f"Request URL: {response.url}")
            self.logger.info(f"Request Body: {data if 'data' in locals() else 'None'}")
            self.logger.info(f"Response Status: {response.status_code}")
            self.logger.info(f"Response Content: {response.text}")
            
            response.raise_for_status()
            return response.json()
            
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Error making FHIR request: {str(e)}")
            if hasattr(e, 'response'):
                self.logger.error(f"Response content: {e.response.text}")
                self.logger.error(f"Request headers: {e.response.request.headers}")
            return None

    def map_snomed_to_icd10(self, snomed_code: str) -> Optional[Dict]:
        """Map a SNOMED CT code to ICD-10 using FHIR ConceptMap."""
        parameters = {
            'code': snomed_code,
            'system': 'http://snomed.info/sct'
        }
        
        # Add debug logging
        self.logger.info(f"Mapping SNOMED CT code: {snomed_code}")
        self.logger.info(f"Parameters: {parameters}")
        
        return self.make_fhir_request(
            resource_type="ConceptMap/$translate",
            parameters=parameters
        )

    def map_snomed_codes_batch(self, snomed_codes: List[str]) -> Optional[Dict]:
        """Map multiple SNOMED CT codes to ICD-10 using FHIR ConceptMap batch translate."""
        parameters = {
            'coding': [
                {
                    'system': 'http://snomed.info/sct',
                    'code': code
                } for code in snomed_codes
            ]
        }
        
        # Add debug logging
        self.logger.info(f"Mapping SNOMED CT codes batch: {snomed_codes}")
        self.logger.info(f"Parameters: {parameters}")
        
        result = self.make_fhir_request(
            resource_type="ConceptMap/$translate",
            parameters=parameters
        )
        
        # Add response validation
        if result and 'parameter' in result:
            matches_count = sum(1 for param in result['parameter'] if param['name'] == 'match')
            self.logger.info(f"Received {matches_count} matches for {len(snomed_codes)} input codes")
            if matches_count != len(snomed_codes):
                self.logger.warning("Number of matches doesn't match number of input codes!")
        
        return result

def load_existing_mappings(output_file='output_codes.csv') -> Dict[str, str]:
    """Load existing SNOMED to ICD10 mappings from output file."""
    existing_mappings = {}
    try:
        if os.path.exists(output_file):
            with open(output_file, 'r', newline='') as csvfile:
                reader = csv.DictReader(csvfile)
                for row in reader:
                    existing_mappings[row['SNOMED']] = row['ICD10']
    except Exception as e:
        logging.error(f"Error loading existing mappings: {str(e)}")
    return existing_mappings

def get_last_id(output_file):
    """Get the last used ID from the CSV file"""
    try:
        if os.path.exists(output_file):
            with open(output_file, 'r', newline='') as csvfile:
                reader = csv.reader(csvfile)
                next(reader)  # Skip header
                last_id = 0
                for row in reader:
                    if row and row[0].isdigit():  # Ensure the ID column contains a number
                        last_id = int(row[0])
                return last_id
    except Exception as e:
        logging.error(f"Error reading last ID: {str(e)}")
    return 0

def process_batch_codes(input_file, output_file='output_codes.csv', failed_file='failed_codes.csv', full_refresh=False):
    client = FHIRClient()
    os.makedirs('output/json', exist_ok=True)
    
    # Initialize counters
    total_codes = 0
    skipped_codes = 0
    processed_codes = 0
    error_codes = 0
    
    # Load existing mappings if not doing a full refresh
    existing_mappings = {} if full_refresh else load_existing_mappings(output_file)
    
    # Get the next ID number for successful mappings
    current_id = 1 if full_refresh else get_last_id(output_file) + 1
    
    # Get the next ID number for failed mappings
    failed_id = 1 if full_refresh else get_last_id(failed_file) + 1
    
    # Open output files in appropriate mode
    mode = 'w' if full_refresh else 'a'
    file_exists = os.path.exists(output_file)
    failed_exists = os.path.exists(failed_file)
    
    with open(output_file, mode, newline='') as csvfile, \
         open(failed_file, mode, newline='') as failedfile:
        writer = csv.writer(csvfile)
        failed_writer = csv.writer(failedfile)
        
        # Write headers if needed
        if full_refresh or not file_exists:
            writer.writerow(['ID', 'SNOMED', 'ICD10', 'TIMESTAMP'])
        if full_refresh or not failed_exists:
            failed_writer.writerow(['ID', 'SNOMED', 'ERROR', 'TIMESTAMP'])
        
        with open(input_file, 'r') as infile:
            for snomed_code in infile:
                snomed_code = snomed_code.strip()
                if not snomed_code:
                    continue
                
                total_codes += 1
                
                # Skip if code already exists and not doing full refresh
                if not full_refresh and snomed_code in existing_mappings:
                    skipped_codes += 1
                    logging.info(f"Skipping {snomed_code} - already mapped to {existing_mappings[snomed_code]}")
                    continue
                    
                try:
                    # Get the raw response
                    response = client.map_snomed_to_icd10(snomed_code)
                    
                    # Save JSON response
                    json_filename = f'output/json/{snomed_code}.json'
                    with open(json_filename, 'w') as f:
                        json.dump(response, f, indent=2)
                    
                    # Extract ICD10 code
                    icd10_code = extract_icd10_from_response(response)
                    
                    if icd10_code:  # Successful mapping
                        writer.writerow([
                            current_id,
                            snomed_code,
                            icd10_code,
                            datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                        ])
                        current_id += 1
                        processed_codes += 1
                        logging.info(f"Processed {snomed_code} -> {icd10_code}")
                    else:  # No mapping found
                        error_codes += 1
                        failed_writer.writerow([
                            failed_id,
                            snomed_code,
                            "No mapping found",
                            datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                        ])
                        failed_id += 1
                        logging.error(f"No mapping found for code {snomed_code}")
                    
                except Exception as e:
                    error_codes += 1
                    logging.error(f"Error processing code {snomed_code}: {str(e)}")
                    failed_writer.writerow([
                        failed_id,
                        snomed_code,
                        f"ERROR: {str(e)}",
                        datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    ])
                    failed_id += 1

    # Print summary statistics
    print("\nProcessing Summary:")
    print(f"Total codes found: {total_codes}")
    print(f"Codes skipped (already mapped): {skipped_codes}")
    print(f"Codes processed successfully: {processed_codes}")
    print(f"Codes with errors/no mapping: {error_codes}")

def extract_icd10_from_response(response):
    """Extract ICD-10 code from the FHIR response"""
    try:
        if not response or 'parameter' not in response:
            return ''

        # First check if there's a match at all
        result_param = next((p for p in response['parameter'] if p['name'] == 'result'), None)
        if not result_param or not result_param.get('valueBoolean', False):
            return ''

        # Find the match parameter
        match_param = next((p for p in response['parameter'] if p['name'] == 'match'), None)
        if not match_param or 'part' not in match_param:
            return ''

        # Look for concept parts with ICD-10 codes
        for part in match_param['part']:
            if (part.get('name') == 'concept' and 
                'valueCoding' in part and 
                part['valueCoding'].get('system') == 'http://hl7.org/fhir/sid/icd-10-am'):
                return part['valueCoding'].get('code', '')

        return ''  # Return empty string if no mapping found
        
    except Exception as e:
        logging.error(f"Error extracting ICD-10 code: {str(e)}")
        return ''

def main():
    parser = argparse.ArgumentParser(description='Map SNOMED CT codes to ICD-10')
    parser.add_argument('--batch', type=str, help='Input file containing SNOMED CT codes (one per line)')
    parser.add_argument('--code', type=str, help='Single SNOMED CT code to map')
    parser.add_argument('--full-refresh', action='store_true', help='Clear output file and process all codes')
    args = parser.parse_args()
    
    # Set up logging
    logging.basicConfig(level=logging.DEBUG)
    
    # Create FHIR client instance
    client = FHIRClient()
    
    if args.batch:
        # Process batch file
        process_batch_codes(args.batch, full_refresh=args.full_refresh)
        print(f"Results written to output_codes.csv")
    elif args.code:
        # Create a temporary file with the single code
        temp_file = 'temp_code.txt'
        with open(temp_file, 'w') as f:
            f.write(args.code)
        
        # Process as batch
        process_batch_codes(temp_file, full_refresh=args.full_refresh)
        
        # Clean up temp file
        os.remove(temp_file)
        print(f"Results written to output_codes.csv")
    else:
        parser.print_help()

if __name__ == "__main__":
    main() 