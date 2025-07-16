#!/bin/bash
# Script to start ThetaData terminal with environment variables

# Load environment variables from the root .env file
if [ -f ../.env ]; then
  export $(grep -v '^#' ../.env | xargs)
fi

# Check if variables are set
if [ -z "$THETADATA_USERNAME" ] || [ -z "$THETADATA_PASSWORD" ]; then
  echo "Error: THETADATA_USERNAME and THETADATA_PASSWORD must be set in .env file."
  exit 1
fi

# Start the terminal
java -jar ThetaTerminal.jar "$THETADATA_USERNAME" "$THETADATA_PASSWORD"
