#!/usr/bin/env bash
set -euo pipefail

# Detect if we're in .guides/secure, if not create it
if [[ ! "$PWD" =~ \.guides/secure$ ]]; then
    mkdir -p .guides/secure
    cd .guides/secure
fi

# Function to download a file from the repository
download_file() {
    local file=$1
    local url="https://raw.githubusercontent.com/bsitkoff/CodioGrader/main/$file"
    echo "Downloading $file..."
    curl -fsSL -o "$file" "$url"
}

# Function to select assignment type
select_type() {
    echo "Select assignment type:"
    echo "1) Python"
    echo "2) Microbit"
    read -p "Enter choice (1 or 2): " choice
    
    case $choice in
        1) echo "python";;
        2) echo "microbit";;
        *) echo "Invalid choice. Defaulting to python."; echo "python";;
    esac
}

echo "Setting up Codio Autograder..."

# Download core files
download_file "grader.py"
download_file "launch_grader.sh"
chmod +x launch_grader.sh

# Get assignment type
type=$(select_type)

# Download appropriate config template
config_template="templates/${type}/config.json"
download_file "$config_template"
mv "config.json" "autograde_config.json"

# Download .env template
download_file "templates/.env.template"
mv ".env.template" ".env"

echo "Setup complete! Next steps:"
echo "1. Edit autograde_config.json for your assignment"
echo "2. Update .env with your credentials"
echo "3. Test the grader with: ./launch_grader.sh"

