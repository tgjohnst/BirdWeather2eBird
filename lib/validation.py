"""Validation module for eBird data fields.
This module provides a set of validation functions to ensure that the data fields conform to eBird's requirements, as outlined in Appendix A (PDF spec).
"""

import re

class ValidationException(Exception):
    """Custom exception for validation errors."""
    def __init__(self, message):
        super().__init__(message)
        self.message = message

class Validator:
    """
    A collection of methods for validating data fields based on eBird requirements.
    """

    def __init__(self, logger):
        """Initialize the Validator with a logger."""
        self.logger = logger

    def validate_string(self, value, field_name, max_length=None, required=False, default=""):
        """Validates a string field."""
        if not isinstance(value, str):
            value = str(value)  # Attempt to convert to string
        
        original_value = value
        value = value.strip()

        if required and not value:
            self.logger.warning(f"Validation failed for '{field_name}': Required field is empty. Original: '{original_value}'. Using default: '{default}'.")
            return default
        if max_length is not None and len(value) > max_length:
            self.logger.warning(f"Validation failed for '{field_name}': Value '{value}' exceeds max length {max_length}. Truncating.")
            return value[:max_length]
        return value

    def validate_number(self, value, field_name, min_val=None, max_val=None, is_integer=False, required=False, exclusive_min=False, exclusive_max=False, default_val=None):
        """Validates a numeric field."""
        if value is None or str(value).strip() == "":
            if required:
                self.logger.warning(f"Validation failed for '{field_name}': Required numeric field is empty. Using default: {default_val}.")
                return default_val
            return None

        try:
            num_value = float(value)
            if is_integer:
                if not num_value.is_integer():
                    self.logger.warning(f"Validation failed for '{field_name}': Value '{value}' is not a whole number. Attempting to use integer part.")
                    num_value = int(num_value)
                else:
                    num_value = int(num_value)
        except ValueError:
            self.logger.warning(f"Validation failed for '{field_name}': Value '{value}' is not a valid number. Using default: {default_val}.")
            return default_val

        if min_val is not None:
            if exclusive_min and num_value <= min_val:
                self.logger.warning(f"Validation failed for '{field_name}': Value {num_value} must be > {min_val}. Using default: {default_val}.")
                return default_val
            if not exclusive_min and num_value < min_val:
                self.logger.warning(f"Validation failed for '{field_name}': Value {num_value} must be >= {min_val}. Using default: {default_val}.")
                return default_val
        if max_val is not None:
            if exclusive_max and num_value >= max_val:
                self.logger.warning(f"Validation failed for '{field_name}': Value {num_value} must be < {max_val}. Using default: {default_val}.")
                return default_val
            if not exclusive_max and num_value > max_val:
                self.logger.warning(f"Validation failed for '{field_name}': Value {num_value} must be <= {max_val}. Using default: {default_val}.")
                return default_val
        return num_value

    def validate_species_count(self, value, field_name):
        """Validates Species Count. Allows 'present' or a number between 0 and 999999."""
        value_str = str(value).strip().upper()
        if value_str == "present":
            return "present"
        
        validated_num = self.validate_number(value, field_name, min_val=1, max_val=999998, is_integer=True, required=False)
        if validated_num is None:
            self.logger.warning(f"Validation for '{field_name}': Value '{value}' is not 'present' or a valid count. Defaulting to 'present'.")
            return "present"
        return validated_num

    def validate_latitude(self, value, field_name, required=True):
        """Validates Latitude: -90 to 90."""
        return self.validate_number(value, field_name, min_val=-90.0, max_val=90.0, required=required, default_val=0.0 if required else None)

    def validate_longitude(self, value, field_name, required=True):
        """Validates Longitude: -180 to 180."""
        return self.validate_number(value, field_name, min_val=-180.0, max_val=180.0, required=required, default_val=0.0 if required else None)

    def validate_date_format(self, value, field_name, date_format_regex=r"^\d{2}/\d{2}/\d{4}$", required=True, default_date="01/01/1900"):
        """Validates date string format MM/dd/yyyy."""
        value_str = str(value).strip()
        if not value_str:
            if required:
                self.logger.warning(f"Validation failed for '{field_name}': Required date field is empty. Using default: '{default_date}'.")
                return default_date
            return ""
        
        if not re.match(date_format_regex, value_str):
            self.logger.warning(f"Validation failed for '{field_name}': Date '{value_str}' is not in MM/dd/yyyy format.")
            if required:
                self.logger.error(f"CRITICAL: '{field_name}' ('{value_str}') does not match required format MM/dd/yyyy.")
            return value_str
        return value_str

    def validate_time_format(self, value, field_name, protocol, time_format_regex=r"^((0?[1-9]|1[0-2]):[0-5]\d\s?(AM|PM)|([01]\d|2[0-3]):[0-5]\d)$", default_time="12:00"):
        """Validates time string format HH:mm AM/PM or kk:mm. Required for non-casual."""
        value_str = str(value).strip()
        is_casual = protocol.lower() == "casual" if protocol else True

        if not value_str:
            if not is_casual:
                self.logger.warning(f"Validation failed for '{field_name}': Required for non-casual protocol '{protocol}', but is empty. Using default: '{default_time}'.")
                return default_time
            return ""

        if not re.match(time_format_regex, value_str, re.IGNORECASE):
            self.logger.warning(f"Validation failed for '{field_name}': Time '{value_str}' is not in a recognized HH:mm AM/PM or kk:mm format.")
            if not is_casual:
                self.logger.error(f"CRITICAL: '{field_name}' ('{value_str}') for non-casual protocol '{protocol}' does not match required time format.")
            return default_time
        return value_str

    def validate_choice(self, value, field_name, choices, required=False, case_sensitive=False, default_val=None):
        """Validates if value is one of the allowed choices."""
        value_str = str(value).strip()
        
        if not value_str:
            if required:
                self.logger.warning(f"Validation failed for '{field_name}': Required field is empty. Using default: '{default_val}'.")
                return default_val
            return default_val if default_val is not None else ""

        comparison_value = value_str if case_sensitive else value_str.lower()
        valid_choices = choices if case_sensitive else [c.lower() for c in choices]

        if comparison_value not in valid_choices:
            self.logger.warning(f"Validation failed for '{field_name}': Value '{value_str}' is not in allowed choices {choices}. Using default: '{default_val}'.")
            return default_val
        
        for choice in choices:
            if (choice.lower() == comparison_value and not case_sensitive) or (choice == comparison_value and case_sensitive):
                return choice
        return default_val

    def validate_boolean_choice(self, value, field_name, true_val='Y', false_val='N', required=False, default_val='N'):
        """Validates a boolean-like choice (e.g., Y/N)."""
        value_str = str(value).strip().upper()
        choices = [true_val.upper(), false_val.upper()]
        
        if not value_str:
            if required:
                self.logger.warning(f"Validation failed for '{field_name}': Required field is empty. Using default: '{default_val}'.")
                return default_val
            return default_val

        if value_str not in choices:
            self.logger.warning(f"Validation failed for '{field_name}': Value '{value_str}' is not one of '{true_val}' or '{false_val}'. Using default: '{default_val}'.")
            return default_val
        return value_str