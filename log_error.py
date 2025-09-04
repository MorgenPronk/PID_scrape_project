def log_error(error_message, log_error_file="error_log.log"):
    """
    Log the error message to a specified log file.
    If the log file does not exist, it will be created.
    """
    # Ensure the log file exists or create it
    try:
        with open(log_error_file, "a") as error_file:
            error_file.write(error_message + "\n")
    except Exception as e:
        print(f"Failed to write to log file {log_error_file}: {e}")
