# Codio Grader Setup

## One-time Setup in Codio

1. **Configure your GitHub token** in Codio at the Course level:
   - Go to Course Settings → Environment
   - Click "Add variable"
   - Set:
     ```
     Name: GITHUB_TOKEN
     Value: your_github_token
     Scope: All assignments in this course
     Visibility: Instructors only
     ```

2. **Run this one-line command in each assignment's terminal** to set up the grader:

```bash
curl -fsSL https://raw.githubusercontent.com/bsitkoff/CodioGrader/main/.guides/secure/launch_grader.sh > .guides/secure/launch_grader.sh && chmod +x .guides/secure/launch_grader.sh && echo "Launcher installed at .guides/secure/launch_grader.sh"
```

3. **Configure the assignment** to use the launcher:
   - Go to Assignment Settings → Grade Weights
   - Choose "Script grading"
   - Set Custom script path to: `.guides/secure/launch_grader.sh`

## Troubleshooting

If you see errors about the GITHUB_TOKEN not being set:
- Verify the token is set at the Course level
- Check that the token has read access to the repository
- Test by running `echo $GITHUB_TOKEN` in a terminal

## Creating a Template Assignment

For efficiency, you can:
1. Set up one assignment completely with the grader
2. In Codio, use "Copy Assignment" for each new assignment
3. Update the assignment details and content as needed

