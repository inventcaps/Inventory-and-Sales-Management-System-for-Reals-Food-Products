---
name: code-cleanup
description: Use this skill when I ask to clean, tidy up, or remove dead code in the codebase
---

Instructions for the skill go here. Provide relative paths to other resources in the skill directory as needed.
When cleaning up the codebase:
1. Never change any logic or functionality — 
   cleanup only, not refactor
2. List all the things to be cleaned first, 
   wait for my approval before touching anything
3. Clean one file at a time — do not bulk edit
4. What to look for:
   - Unused imports
   - Commented out dead code
   - Unused variables or functions
   - Duplicate code blocks
   - Inconsistent formatting
   - Console.log or print() debug statements
   - TODO comments that are already done
5. After each file, tell me what was removed
6. Never rename variables or functions — 
   only remove dead code
7. If unsure if code is used — ask me first, 
   never assume
8. Never clean or refactor code unless I explicitly 
ask for a cleanup. Focus only on the task at hand.