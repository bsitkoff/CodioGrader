# Codio Autograder

A customizable autograder for Codio assignments that uses OpenAI and Notion for feedback and grade tracking.

## Quick Start

### 1. Initial Setup (In your assignment's root directory)
```bash
# Download the setup script
curl -O https://raw.githubusercontent.com/bsitkoff/CodioGrader/main/setup.sh
chmod +x setup.sh

# Run the setup script
./setup.sh

# Follow the prompts to:
# 1. Select assignment type (Python or Microbit)
# 2. Get config template and core files
```

### 2. Configure the Grader
1. Edit `.guides/secure/autograde_config.json`:
   - Update assignment name and description
   - Customize rubric and scoring
   - Adjust AI feedback prompts

2. Set up environment variables in Codio:
   - OpenAI is handled by Codio's BricksLLM
   - For Notion integration (optional):
     - NOTION_API_KEY
     - NOTION_GRADES_DATABASE_ID
     - NOTION_STUDENTS_DATABASE_ID

### 3. Test the Grader
```bash
cd .guides/secure
./launch_grader.sh
```

### 4. Update Grader (when needed)
```bash
./launch_grader.sh --update
```

## Features
- OpenAI-powered code evaluation
- Customizable rubric-based grading
- Notion integration for grade tracking (optional)
- Support for multiple assignment types
- Automatic feedback generation

## Configuration Templates

### Python Assignments
Uses `templates/python/config.json`:
- Function implementation scoring
- Output verification
- Code quality assessment
- Style checking

### Microbit Assignments
Uses `templates/microbit/config.json`:
- State management evaluation
- User input handling
- Hardware interaction
- Code organization

## Troubleshooting

### Common Issues
- OpenAI API errors: Check Codio BricksLLM setup
- Notion errors: Verify API keys and database IDs
- Enable debug logging: Set `DEBUG=1` in `.env`

### Getting Help
- Check the templates directory for example configurations
- Enable debug logging for detailed error messages
- Review Codio's documentation on autograding

## Updating
- Use `launch_grader.sh --update` to get the latest version
- Configuration files are preserved during updates
- New features and bug fixes are automatically included
