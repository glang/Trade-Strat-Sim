#!/bin/bash
# Script to start ThetaData terminal with environment variables

# This script is designed to be run from the project root directory

# Load environment variables from the root .env file
if [ -f ./.env ]; then
  export $(grep -v '^#' ./.env | xargs)
fi

# Check if variables are set
if [ -z "$THETADATA_USERNAME" ] || [ -z "$THETADATA_PASSWORD" ]; then
  echo "Error: THETADATA_USERNAME and THETADATA_PASSWORD must be set in .env file."
  exit 1
fi

# Define the path to the JAR file
JAR_FILE="./ThetaTerminal.jar"

if [ ! -f "$JAR_FILE" ]; then
    echo "Error: ThetaTerminal.jar not found in the project root."
    exit 1
fi

# Start the terminal
java -jar "$JAR_FILE" "$THETADATA_USERNAME" "$THETADATA_PASSWORD"