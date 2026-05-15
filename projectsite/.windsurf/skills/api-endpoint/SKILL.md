---
name: api-endpoint
description: Use this skill when creating new API endpoints or modifying existing ones
---

Instructions for the skill go here. Provide relative paths to other resources in the skill directory as needed.
When creating a new API endpoint:
1. Check existing urls.py and views.py first 
   to follow the same patterns in the project
2. Show me the plan (url, view, logic) — 
   wait for approval before coding
3. Always add proper error handling (try/except)
4. Always validate inputs before processing
5. Return consistent JSON response format:
   - Success: {"status": "success", "data": ...}
   - Error: {"status": "error", "message": ...}
6. Never expose sensitive data in the response
7. Tell me how to test the endpoint after