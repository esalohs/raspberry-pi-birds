#!/bin/bash

set -e

PROFILE_NAME="bird-camera"

# Get outputs from Terraform
ACCESS_KEY=$(terraform output -raw access_key_id)
SECRET_KEY=$(terraform output -raw secret_access_key)

# Create .aws directory if it doesn't exist
mkdir -p ~/.aws

# Create credentials file if it doesn't exist
touch ~/.aws/credentials

# Append profile
cat >> ~/.aws/credentials << EOF

[$PROFILE_NAME]
aws_access_key_id = $ACCESS_KEY
aws_secret_access_key = $SECRET_KEY
EOF

echo "$PROFILE_NAME"
