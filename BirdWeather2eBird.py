"""
BirdWeather2eBird.py

Author: Spike Graham
Copyright (c) 2025 Spike Graham
All rights reserved.

This software is provided for personal, non-commercial use only.  
You may view and run this software for personal educational or non-profit purposes.

You may not:
- Use this software in any commercial or enterprise context.
- Distribute modified or unmodified versions.
- Sell or include this software as part of a paid or monetized service or product.
- Use this software in any for-profit capacity.

All rights are reserved by the author.
"""

import csv

from conf import config
from lib import core_processing
from lib import cli_support
from lib.validation import Validator, ValidationException

def process_and_validate_row(input_row, args, config, validator, logger):
    """
    Processes a single row from the input CSV, validates its fields,
    and prepares it for the output CSV.

    Args:
        input_row (dict): A dictionary representing a row from the input CSV.
        args: Command-line arguments.
        config: Configuration object.
        validator: Validator instance for validating data fields.
        logger: Logger instance.

    Returns:
        list: A list of validated data fields for the output CSV row, or None if critical errors occur.

    Notes:
        - This function assumes that the input_row is a dictionary with keys matching the expected CSV headers.
        - The function handles validation and logging of errors, returning None for rows that fail critical checks.
        - Individual field validations can be modified to throw exceptions or return default values as needed.
    """
    try:
        # 1. Common Name
        common_name = validator.validate_string(input_row.get("Common Name", ""), "Common Name", max_length=128)

        # 2. Genus & 3. Species (from Scientific Name)
        sci_name_raw = input_row.get("Scientific Name", "").strip()
        sci_parts = sci_name_raw.split(maxsplit=1) # Split into at most 2 parts
        
        raw_genus = sci_parts[0] if len(sci_parts) > 0 else ""
        raw_species = sci_parts[1] if len(sci_parts) > 1 else ""

        genus = validator.validate_string(raw_genus, "Genus", max_length=64)
        species = validator.validate_string(raw_species, "Species", max_length=64)

        # Requirement: Either common or scientific name is required.
        if not common_name and not (genus and species):
            logger.error(f"Row skipped: Neither Common Name nor full Scientific Name (Genus and Species) provided. Raw SciName: '{sci_name_raw}'")
            raise ValidationException("Neither Common Name nor Scientific Name provided.")

        # 4. Species Count
        # Assuming 'X' is the default if count is not a number, as per original script and eBird practice
        species_count_raw = input_row.get("Count", "present") # Assuming input CSV might have a 'Count' column #TODO
        species_count = validator.validate_species_count(species_count_raw, "Species Count")


        # 5. Species Comments
        species_comments = validator.validate_string(getattr(config, 'SPECIES_COMMENTS', ""), "Species Comments", max_length=4000)

        # 6. Location Name
        location_name = validator.validate_string(input_row.get("Station", ""), "Location Name", max_length=254, required=True, default="Unknown Location")
        if not location_name or location_name == "Unknown Location" and input_row.get("Station","") == "": # Check if it defaulted due to being empty and required
             logger.error(f"Row check: Location Name is required and was empty or became default. Original: '{input_row.get('Station', '')}'. Processed: '{location_name}'. This might lead to eBird rejection.")
             raise ValidationException("Location Name is required and was empty or defaulted.")

        # 7. Latitude & 8. Longitude
        latitude = validator.validate_latitude(input_row.get("Latitude"), "Latitude", required=True)
        longitude = validator.validate_longitude(input_row.get("Longitude"), "Longitude", required=True)
        if latitude is None or longitude is None: # validate_latitude/longitude return None on critical failure for required field
            logger.error(f"Row skipped: Latitude or Longitude is missing or invalid. Lat: '{input_row.get('Latitude')}', Lon: '{input_row.get('Longitude')}'")
            return None

        # 9. Observation Date & 10. Start Time
        # core_processing.parse_timestamp is assumed to exist and work.
        # Let's assume it returns date_str, time_str
        try:
            # Ensure 'Timestamp' key exists, provide a default if not, though it should ideally be present
            timestamp_raw = input_row.get("Timestamp")
            if not timestamp_raw:
                logger.error("Row skipped: 'Timestamp' field is missing in input_row.")
                raise ValidationException("Timestamp field is missing.")
            obs_date_raw, obs_time_raw = core_processing.parse_timestamp(timestamp_raw)
        except Exception as e:
            logger.error(f"Row skipped: Error parsing Observation Date timestamp '{input_row.get('Timestamp')}': {e}")
            raise ValidationException(f"Error parsing Observation Date timestamp: {e}")

        # Validate the parsed date and time
        # Protocol is needed for time validation (required for non-casual)
        # We validate protocol first, then use it for time validation.
        temp_protocol = validator.validate_string(args.protocol, "Protocol (pre-val)")

        obs_date = validator.validate_date_format(obs_date_raw, "Observation Date", required=True)
        obs_time = validator.validate_time_format(obs_time_raw, "Start Time", protocol=temp_protocol) # Pass protocol here
        
        if obs_date == "01/01/1900" and obs_date_raw != "01/01/1900": # Defaulted due to error
             logger.error(f"Row check: Observation Date is required and was invalid. Original: '{obs_date_raw}'. This might lead to eBird rejection.")
             raise ValidationException("Observation Date is required and was invalid.")

        # 11. State & 12. Country
        # Original script uses args.state_code and args.country_code
        # state, country = core_processing.get_location_codes(latitude, longitude)
        state = validator.validate_string(args.state_code, "State", max_length=3)
        country = validator.validate_string(args.country_code, "Country", max_length=2)

        # 13. Protocol #TODO deal with this and ordering
        # Validated from args.protocol
        protocol_choices = ["stationary", "traveling", "incidental", "historical", "casual", 'area'] # Added 'incidental' and 'historical', based on eBird documentation, even though it is not in the PDF spec
        # The original script listed (Stationary,Traveling,Incidental,Historical). PDF lists casual, stationary, traveling, area.
        # Combining and ensuring lowercase for validation.
        protocol = validator.validate_choice(args.protocol, "Protocol", choices=protocol_choices, required=True, default_val="casual")
        if not protocol: # If it's required and became empty string or None due to failed validation
            logger.error(f"Row processing halted: Protocol '{args.protocol}' is invalid or missing, and it's a required field.")
            return None # Or handle as a script-level error if protocol is fundamental

        # Re-validate time if protocol was determined after initial time validation and time is empty
        #TODO is this not already handled above?
        if not obs_time and protocol.lower() != "casual":
            obs_time = validator.validate_time_format(obs_time_raw, "Start Time (re-check)", protocol=protocol, default_time="12:00")
            if obs_time == "12:00" and not obs_time_raw: # Defaulted
                 logger.warning(f"Start Time defaulted for non-casual protocol '{protocol}' as it was initially empty.")


        # 14. Number of Observers
        # Validated from args.number_of_observers
        num_observers = validator.validate_number(args.number_of_observers, "Number of Observers", min_val=1, is_integer=True, required=False, default_val=1) # eBird often defaults to 1

        # 15. Duration
        # Validated from config.DURATION
        # PDF: 0 < x < 1440 (so 1 to 1439 minutes)
        duration_val = getattr(config, 'DURATION', None)
        duration = validator.validate_number(duration_val, "Duration", min_val=1, max_val=1439, is_integer=True, required=False) # Optional, eBird might default to 0 or null

        # 16. All Observations Reported?
        # Validated from config.ALL_OBS_REPORTED
        all_obs_reported_val = getattr(config, 'ALL_OBS_REPORTED', 'N')
        all_obs_reported = validator.validate_boolean_choice(all_obs_reported_val, "All Observations Reported?", default_val='N')

        # 17. Distance Covered (miles)
        # Validated from config.DISTANCE_COVERED
        # PDF: x > 0. Optional (DEFAULT NULL)
        # Only relevant for "traveling" protocol.
        distance_covered = None
        if protocol.lower() == "traveling":
            distance_val = getattr(config, 'DISTANCE_COVERED', None)
            distance_covered = validator.validate_number(distance_val, "Distance Covered", min_val=0, exclusive_min=True, required=False)

        # 18. Area Covered (acres)
        # Validated from config.AREA_COVERED
        # PDF: x > 0. Optional (DEFAULT NULL)
        # Only relevant for "area" protocol.
        area_covered = None
        if protocol.lower() == "area":
            area_val = getattr(config, 'AREA_COVERED', None)
            area_covered = validator.validate_number(area_val, "Area Covered", min_val=0, exclusive_min=True, required=False)

        # 19. Checklist Comments
        # Validated from args.comments
        checklist_comments = validator.validate_string(args.comments, "Checklist Comments", max_length=4000)

        # Assemble the validated row in the strict order required by eBird
        output_row = [
            common_name,
            genus,
            species,
            species_count,
            species_comments,
            location_name,
            latitude,
            longitude,
            obs_date,
            obs_time,
            state,
            country,
            protocol,
            num_observers,
            duration if duration is not None else "", # eBird expects empty string for optional null numbers sometimes, or just omit
            all_obs_reported,
            distance_covered if distance_covered is not None else "",
            area_covered if area_covered is not None else "",
            checklist_comments
        ]
        return output_row
    
    # Handle specific exceptions for validation and processing
    except ValidationException as ve:
        logger.error(f"Validation error processing row: {input_row}. Error: {ve}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error processing row: {input_row}. Error: {e}", exc_info=True)
        return None

def main():
    args = cli_support.input_argparse()
    logger = cli_support.start_logging(config.log_file_path, config.log_level, config.tool_name)
    validator = validation.Validation(logger)

    logger.info('Running BirdWeather2eBird')
    logger.debug(f'Input File: {args.input_file}')
    logger.debug(f'Output File: {args.output_file}')
    
    processed_rows = 0
    written_rows = 0

    try:
        with open(args.input_file, newline="", encoding="utf-8") as infile, \
             open(args.output_file, "w", newline="", encoding="utf-8") as outfile:

            reader = csv.DictReader(infile)
            writer = csv.writer(outfile, lineterminator="\n")

            for i, row in enumerate(reader):
                processed_rows +=1
                logger.debug(f"Processing input row {i+1}: {row}")

                validated_output_row = process_and_validate_row(row, args, config, validator, logger)
                
                if validated_output_row:
                    # Ensure all elements are strings for CSV writer, handle None for numeric optional fields
                    final_row_for_csv = [str(field) if field is not None else "" for field in validated_output_row]
                    writer.writerow(final_row_for_csv)
                    written_rows += 1
                else:
                    logger.warning(f"Skipping row {i+1} due to critical validation errors or processing failure. Input: {row}")
                
    
    # Catch critical exceptions and log them
    except csv.Error as e:
        logger.error(f"Error processing CSV file: {e}")
        return
    except KeyError as e:
        logger.error(f"Missing required field in input file: {e}")
        return
    except OSError as e:
        logger.error(f"OS error: {e}")
        return
    except FileNotFoundError:
        logger.error(f"Error: Input file not found at {args.input_file}")
        return
    except Exception as e:
        logger.error(f"An unexpected error occurred during file processing: {e}", exc_info=True)
        return
    
    # If we reach this point, the file was processed successfully
    logger.info('BirdWeather2eBird ran Successfully!')
    logger.info(f'Processed {processed_rows} rows, successfully wrote {written_rows} rows to {args.output_file}.')

if __name__ == "__main__":
    main()
